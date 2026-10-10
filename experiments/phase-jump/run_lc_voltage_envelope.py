"""Bounded minimax inverter-voltage search for a declared LC model.

Feasible peaks are upper bounds on required voltage, never optimality proofs.
Old experiment sources and artifacts are kept immutable.
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from run_constrained_ocp import ROOT, T, TOL, SplineProblem, grid
from run_phase_one_refinement import ConstraintGrid
from run_power_feasibility import K
from run_scaled_ocp import ScaledProblem
from verify_constrained_ocp import polynomial_audit, replay
from verify_phase_one_refinement import endpoint_audit, combined_constraint_check

PLAN = ROOT / "results/phase-jump-power-feasibility/lc-voltage-envelope-plan-2026-10-05.md"
OUTPUT = ROOT / "results/phase-jump-power-feasibility/lc-voltage-envelope-2026-10-05"
PREVIOUS = ROOT / "results/phase-jump-power-feasibility/phase-one-refinement-2026-10-05/result.json"
CF, X1, R1 = .02, .1, .01
MAX_ROUNDS, MAX_ITER_FEAS, MAX_ITER_PEAK = 4, 200, 300
SECONDS_FEAS, SECONDS_PEAK, TOTAL_SECONDS = 10., 20., 240.


def lc_matrices(base, times):
    """Affine i1 and vi maps in original free-coefficient coordinates."""
    c, m = base.case, base.matrices(times)
    b = [base.basis(np.asarray(times)/T, nu=j)/T**j for j in [1, 2, 3]]
    offsets = [bj @ base.fixed for bj in b]
    jac = [np.stack([np.kron(row[base.free], np.eye(2)) for row in bj]) for bj in b]
    ddv0 = c["rt"]*offsets[1] + c["lt"]*(offsets[1] @ K.T) + c["lt"]/c["wb"]*offsets[2]
    ddvj = c["rt"]*jac[1] + c["lt"]*np.einsum("ab,mbn->man", K, jac[1]) + c["lt"]/c["wb"]*jac[2]
    i10 = m["i0"] + CF/c["wb"]*m["dv0"] + CF*(m["v0"] @ K.T)
    i1j = m["ij"] + CF/c["wb"]*m["dvj"] + CF*np.einsum("ab,mbn->man", K, m["vj"])
    di10 = offsets[0] + CF/c["wb"]*ddv0 + CF*(m["dv0"] @ K.T)
    di1j = jac[0] + CF/c["wb"]*ddvj + CF*np.einsum("ab,mbn->man", K, m["dvj"])
    vi0 = m["v0"] + R1*i10 + X1*(i10 @ K.T) + X1/c["wb"]*di10
    vij = m["vj"] + R1*i1j + X1*np.einsum("ab,mbn->man", K, i1j) + X1/c["wb"]*di1j
    return dict(i10=i10, i1j=i1j, vi0=vi0, vij=vij)


class LCConstraintGrid:
    def __init__(self, scaled, times, limit_i1, voltage_scale):
        self.scaled, self.times = scaled, np.asarray(times)
        self.original = ConstraintGrid(scaled, times, True)
        self.mat = lc_matrices(scaled.base, times)
        self.limit_i1, self.voltage_scale = limit_i1, float(voltage_scale)
        zero = np.max(np.abs(self.mat["i1j"]), axis=(1, 2)) == 0
        self.i1keep = ~zero
        raw = self.i1values(scaled.x0, filtered=False)
        if limit_i1 and np.any(raw[zero] < -1e-10):
            raise ValueError("Fixed inverter-current endpoint violates declared limit")
        self.removed_i1 = dict(indices=np.where(zero)[0].tolist(), residuals=raw[zero].tolist())

    def fields(self, z):
        x = self.scaled.physical(z)
        return tuple(self.mat[key+"0"] + np.einsum("man,n->ma", self.mat[key+"j"], x)
                     for key in ["i1", "vi"])

    def i1values(self, z, filtered=True):
        i1, _ = self.fields(z)
        g = 1.-np.sum(i1*i1, axis=1)/1.3**2
        return g[self.i1keep] if filtered else g

    def i1jac(self, z):
        i1, _ = self.fields(z)
        jac = -2*np.einsum("ma,man->mn", i1, self.mat["i1j"]) @ self.scaled.transform / 1.3**2
        return jac[self.i1keep]

    def physical_values(self, z):
        return np.r_[self.original.values(z), self.i1values(z)] if self.limit_i1 else self.original.values(z)

    def physical_jac(self, z):
        return np.vstack([self.original.jacobian(z), self.i1jac(z)]) if self.limit_i1 else self.original.jacobian(z)

    def epigraph_values(self, y):
        z, q = y[:-1], y[-1]
        _, vi = self.fields(z)
        return np.r_[self.physical_values(z), q-np.sum(vi*vi, axis=1)/self.voltage_scale**2]

    def epigraph_jac(self, y):
        z = y[:-1]
        _, vi = self.fields(z)
        first = np.column_stack((self.physical_jac(z), np.zeros(len(self.physical_values(z)))))
        last = -2*np.einsum("ma,man->mn", vi, self.mat["vij"]) @ self.scaled.transform / self.voltage_scale**2
        return np.vstack([first, np.column_stack((last, np.ones(len(last))))])


def solve_stage(constraints, z, feasibility, deadline):
    started = time.monotonic()
    if feasibility:
        y0 = np.r_[z, max(0., -float(constraints.physical_values(z).min()))+1e-8]

        def con(y):
            return constraints.physical_values(y[:-1])+y[-1]

        def jac(y):
            a = constraints.physical_jac(y[:-1])
            return np.column_stack((a, np.ones(len(a))))
    else:
        _, vi = constraints.fields(z)
        y0 = np.r_[z, float(np.max(np.sum(vi*vi, axis=1)))/constraints.voltage_scale**2+1e-8]
        con, jac = constraints.epigraph_values, constraints.epigraph_jac
    duration = SECONDS_FEAS if feasibility else SECONDS_PEAK
    accepted, history = y0.copy(), []

    def budget():
        if time.monotonic() > min(started+duration, deadline):
            raise TimeoutError("Declared stage or optimization total budget reached")

    def objective(y):
        budget()
        return float(y[-1])

    def gradient(y):
        budget()
        return np.r_[np.zeros(len(y)-1), 1.]

    def bounded(fn):
        def call(y):
            budget()
            return fn(y)
        return call

    def callback(y):
        nonlocal accepted
        accepted = y.copy()
        history.append(dict(iteration=len(history)+1, scalar_variable=float(y[-1]),
                            minimum_optimizer_constraint=float(con(y).min())))
        budget()

    try:
        solved = minimize(objective, y0, jac=gradient, method="SLSQP",
            bounds=[(None, None)]*len(z)+[(0., None)],
            constraints=dict(type="ineq", fun=bounded(con), jac=bounded(jac)), callback=callback,
            options=dict(maxiter=MAX_ITER_FEAS if feasibility else MAX_ITER_PEAK, ftol=1e-11, disp=False))
        y = solved.x
        state = dict(success=bool(solved.success), status=int(solved.status), message=str(solved.message),
                     iterations=int(solved.nit), termination="optimizer-returned")
    except TimeoutError as exc:
        y = accepted
        state = dict(success=False, status=None, message=str(exc), iterations=len(history), termination="budget-exceeded")
    return y[:-1], dict(phase="feasibility" if feasibility else "minimax-voltage", scalar_variable=float(y[-1]),
        scalar_meaning="normalized constraint slack" if feasibility else "squared voltage envelope / fixed voltage scale squared",
        optimizer=state, history=history, elapsed_seconds=time.monotonic()-started,
        minimum_unrelaxed_physical_constraint=float(constraints.physical_values(y[:-1]).min()))


def audit(scaled, z, limit_i1, envelope=None):
    from verify_lc_voltage_envelope import hardware_audit
    coef, knots = scaled.coefficients(z), scaled.knots*T
    summary, segments = polynomial_audit(knots, coef, scaled.case)
    hardware, hsegments = hardware_audit(knots, coef, scaled.case)
    dense = scaled.check(z, grid(True))
    end = endpoint_audit(knots, coef, scaled.case)
    _, _, _, physical_pass, consistent = combined_constraint_check(summary, dense, end, scaled.case, True)
    lcgrid = LCConstraintGrid(scaled, grid(True), limit_i1, 1.)
    i1, vi = lcgrid.fields(z)
    dense_i1, dense_vi = float(np.max(np.linalg.norm(i1, axis=1))), float(np.max(np.linalg.norm(vi, axis=1)))
    hardware_consistent = bool(dense_i1 <= hardware["inverter_current_peak_pu"]+TOL
        and dense_vi <= hardware["inverter_voltage_peak_pu"]+TOL)
    i1pass = hardware["inverter_current_peak_pu"] <= 1.3+TOL and dense_i1 <= 1.3+TOL
    i1endpass = max(hardware["endpoint_inverter_current_errors"].values()) <= TOL
    valid = bool(physical_pass and consistent and hardware_consistent and i1endpass and (i1pass or not limit_i1))
    epass = None if envelope is None else bool(hardware["inverter_voltage_peak_pu"] <= envelope+TOL and dense_vi <= envelope+TOL)
    return dict(coefficients=coef.tolist(), knots_s=knots.tolist(), polynomial_summary=summary, segments=segments,
        hardware_summary=hardware, hardware_segments=hsegments, dense_check=dense, independent_endpoints=end,
        dense_inverter_current_peak_pu=dense_i1, dense_inverter_voltage_peak_pu=dense_vi,
        strategy_constraints_pass=valid, inverter_current_pass=bool(i1pass), hardware_representations_consistent=hardware_consistent,
        optimizer_voltage_envelope_pu=envelope, epigraph_pass=epass)


def run_strategy(scaled, z0, limit_i1, voltage_scale, deadline, checkpoint):
    z, times = z0.copy(), scaled.times.copy()
    rows, feasible = [], []
    last = None
    stop = "round-budget-reached"
    for number in range(MAX_ROUNDS):
        if time.monotonic() > deadline:
            stop = "optimization-total-budget-reached"
            break
        constraints = LCConstraintGrid(scaled, times, limit_i1, voltage_scale)
        row = dict(round=number+1, constraint_times_s=times.tolist(), stages=[],
                   removed_original_rows=constraints.original.removed, removed_i1_rows=constraints.removed_i1)
        rows.append(row)
        audits = []
        for phase in [True, False]:
            if time.monotonic() > deadline:
                break
            if not phase and constraints.physical_values(z).min() < -1e-8:
                row["peak_stage_skipped"] = "unrelaxed sampled constraints not satisfied"
                break
            z, stage = solve_stage(constraints, z, phase, deadline)
            stage["coefficients"] = scaled.coefficients(z).tolist()
            row["stages"].append(stage)
            checkpoint(dict(limit_inverter_current=limit_i1, rounds=rows))
            envelope = None if phase else np.sqrt(max(0., stage["scalar_variable"]))*voltage_scale
            last = audit(scaled, z, limit_i1, envelope)
            stage["audit"] = last
            audits.append(last)
            checkpoint(dict(limit_inverter_current=limit_i1, rounds=rows))
            if last["strategy_constraints_pass"]:
                feasible.append((z.copy(), last, number+1, stage["phase"]))
        if last is None:
            last = audit(scaled, z, limit_i1)
        if rows[-1]["stages"] and rows[-1]["stages"][-1]["phase"] == "minimax-voltage" and last["strategy_constraints_pass"] and last["epigraph_pass"]:
            stop = "numerically-feasible-peak-candidate"
            row["added_constraint_times_s"] = []
            checkpoint(dict(limit_inverter_current=limit_i1, rounds=rows))
            break
        keys = ["current_peak_at_s", "voltage_peak_at_s", "minimum_power_at_s"]
        hkeys = ["inverter_voltage_peak_at_s"] + (["inverter_current_peak_at_s"] if limit_i1 else [])
        extra = [r[k] for a in audits for r in a["segments"] for k in keys]
        extra += [r[k] for a in audits for r in a["hardware_segments"] for k in hkeys]
        new = np.unique(np.r_[times, extra])
        added = np.setdiff1d(new, times)
        row["added_constraint_times_s"] = added.tolist()
        print(json.dumps(dict(limit_i1=limit_i1, round=number+1, power=last["polynomial_summary"]["minimum_power_pu"],
             voltage_peak=last["hardware_summary"]["inverter_voltage_peak_pu"],
             inverter_current=last["hardware_summary"]["inverter_current_peak_pu"], added_points=len(added))), flush=True)
        checkpoint(dict(limit_inverter_current=limit_i1, rounds=rows))
        if not len(added):
            stop = "no-new-extremum-times"
            break
        times = new
    if last is None:
        last = audit(scaled, z, limit_i1)
    selected_round, selected_phase = len(rows), "last-infeasible-diagnostic"
    if feasible:
        z, last, selected_round, selected_phase = min(feasible, key=lambda item: item[1]["hardware_summary"]["inverter_voltage_peak_pu"])
    result = dict(strategy="with-inverter-current-limit" if limit_i1 else "without-inverter-current-limit",
        limit_inverter_current=limit_i1, stop_reason=stop, rounds=rows, feasible_candidate_count=len(feasible),
        selected_round=selected_round, selected_phase=selected_phase, **last)
    if result["strategy_constraints_pass"]:
        result["hypothetical_LC_replay"] = replay(scaled.knots*T, scaled.coefficients(z), scaled.case, True)
    return result


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    inherited = {**previous["source_hashes"], **previous["inherited_source_hashes"]}
    for name, expected in inherited.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Prior frozen source changed: {name}")
    files = [Path(__file__), PLAN, PREVIOUS, PREVIOUS.parent/"independent-verification.json"] + [
        ROOT/f"experiments/phase-jump/{name}.py" for name in ["verify_lc_voltage_envelope", "verify_phase_one_refinement"]]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    verified = json.loads((PREVIOUS.parent/"independent-verification.json").read_text(encoding="utf-8"))
    if verified["result_sha256"] != hashes[str(PREVIOUS.relative_to(ROOT))] or not verified["converged_voltage_objective_pair_observed"]:
        raise AssertionError("Prior independent verification mismatch")
    scaled = ScaledProblem(SplineProblem())
    old = previous["strategies"][1]
    x = np.asarray(old["coefficients"])[scaled.base.free].ravel()
    z0 = np.linalg.solve(scaled.transform, x-scaled.base.x0)
    if np.max(np.abs(scaled.coefficients(z0)-np.asarray(old["coefficients"]))) > 1e-12:
        raise AssertionError("Warm-start endpoint/coefficients mismatch")
    voltage_scale = old["polynomial_summary"]["hypothetical_inverter_voltage_peak_pu"]
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, inherited_source_hashes=inherited,
        environment=previous["environment"], case=previous["case"],
        hardware=dict(Cf_pu=CF, X1_pu=X1, R1_pu=R1, Rf_pu=0., inverter_current_limit_pu=1.3,
                      parameter_status="declared diagnostic hardware, not author hardware"),
        configuration=dict(max_rounds=MAX_ROUNDS, feasible_maxiter=MAX_ITER_FEAS, peak_maxiter=MAX_ITER_PEAK,
                           feasible_stage_seconds=SECONDS_FEAS, peak_stage_seconds=SECONDS_PEAK,
                           optimization_total_seconds=TOTAL_SECONDS, tolerance=TOL, fixed_voltage_scale_pu=voltage_scale,
                           initial_source="previous independently verified hard-power candidate", spline_space_unchanged=True),
        initial_coefficients=old["coefficients"], initial_audit=audit(scaled, z0, False), strategies=[])
    OUTPUT.mkdir()

    def save():
        result["elapsed_seconds"] = time.monotonic()-started
        path = OUTPUT/"result.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Result readback failed")

    def checkpoint(active):
        result["active_trial"] = active
        save()

    save()
    try:
        for limit in [False, True]:
            result["strategies"].append(run_strategy(scaled, z0, limit, voltage_scale, started+TOTAL_SECONDS, checkpoint))
            result.pop("active_trial", None)
            save()
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise AssertionError("Source drift during experiment")
        result["status"] = "complete"
    except Exception as exc:
        result["status"], result["failure"] = "execution-failed", repr(exc)
        raise
    finally:
        save()
    print(json.dumps(dict(status=result["status"], elapsed_seconds=result["elapsed_seconds"], strategies=[dict(
        strategy=s["strategy"], feasible=s["strategy_constraints_pass"], selected_phase=s["selected_phase"],
        voltage_peak=s["hardware_summary"]["inverter_voltage_peak_pu"],
        inverter_current_peak=s["hardware_summary"]["inverter_current_peak_pu"], stop=s["stop_reason"])
        for s in result["strategies"]])), flush=True)


if __name__ == "__main__":
    main()
