"""Bounded Phase-I and constraint-time refinement in a frozen spline space.

Slack is diagnostic, never a relaxation of the final physical checks.
Polynomial roots are floating-point checks, not certified interval bounds.
"""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from run_constrained_ocp import DEGREE, ROOT, T, TOL, SplineProblem, grid
from run_scaled_ocp import ScaledProblem
from run_power_feasibility import VG
from verify_constrained_ocp import polynomial_audit, replay

PLAN = ROOT / "results/phase-jump-power-feasibility/phase-one-refinement-plan-2026-10-05.md"
OUTPUT = ROOT / "results/phase-jump-power-feasibility/phase-one-refinement-2026-10-05"
MAX_ROUNDS = 4
MAX_ITER = 200
STAGE_SECONDS = 10.
TOTAL_SECONDS = 180.


class ConstraintGrid:
    """Constraint grid separate from the immutable objective quadrature."""
    def __init__(self, scaled, times, hard_power):
        self.scaled = scaled
        self.base = scaled.base
        self.times = np.asarray(times)
        self.hard_power = hard_power
        self.mat = self.base.matrices(self.times)
        c = self.base.case
        n = len(self.times)
        self.scales = np.repeat([1.3**2, np.dot(c["frozen"], c["frozen"])]
                                + ([c["ppre"]] if hard_power else []), n)
        izero = np.max(np.abs(self.mat["ij"]), axis=(1, 2)) == 0
        vzero = np.max(np.abs(self.mat["vj"]), axis=(1, 2)) == 0
        constant = np.concatenate([izero, vzero] + ([izero & vzero] if hard_power else []))
        self.keep = ~constant
        fixed = self.raw(scaled.x0)[constant]
        if np.any(fixed < -1e-10):
            raise ValueError("Violated fixed physical constraint")
        self.removed = dict(indices=np.where(constant)[0].tolist(), residuals=fixed.tolist())

    def raw(self, z):
        c = self.base.case
        i, v, _ = self.base.fields(self.scaled.physical(z), self.mat)
        parts = [1.3**2 - np.sum(i*i, axis=1),
                 np.dot(c["frozen"], c["frozen"]) - np.sum(v*v, axis=1)]
        if self.hard_power:
            poi = c["alpha"]*v + c["beta"]*VG + c["correction"]*i
            parts.append(np.sum(poi*i, axis=1) - c["ppre"])
        return np.concatenate(parts)

    def values(self, z):
        return (self.raw(z) / self.scales)[self.keep]

    def jacobian(self, z):
        c = self.base.case
        i, v, _ = self.base.fields(self.scaled.physical(z), self.mat)
        ij, vj = self.mat["ij"], self.mat["vj"]
        parts = [-2*np.einsum("ma,man->mn", i, ij), -2*np.einsum("ma,man->mn", v, vj)]
        if self.hard_power:
            poi = c["alpha"]*v + c["beta"]*VG + c["correction"]*i
            pj = c["alpha"]*vj + c["correction"]*ij
            parts.append(np.einsum("ma,man->mn", poi, ij) + np.einsum("ma,man->mn", i, pj))
        return ((np.vstack(parts) @ self.scaled.transform) / self.scales[:, None])[self.keep]

    def slack_values(self, y):
        return self.values(y[:-1]) + y[-1]

    def slack_jacobian(self, y):
        jac = self.jacobian(y[:-1])
        return np.column_stack((jac, np.ones(len(jac))))


def audit_candidate(scaled, z, hard_power):
    coef = scaled.coefficients(z)
    summary, segments = polynomial_audit(scaled.knots*T, coef, scaled.case)
    dense = scaled.check(z, grid(True))
    current = summary["current_peak_pu"] <= 1.3 + TOL
    voltage = summary["voltage_peak_pu"] <= np.linalg.norm(scaled.case["frozen"]) + TOL
    power = summary["minimum_power_pu"] >= scaled.case["ppre"] - TOL
    valid = bool(current and voltage and dense["endpoint_pass"] and (power or not hard_power))
    return dict(coefficients=coef.tolist(), objective=scaled.objective(z)*scaled.scale,
                dense_check=dense, polynomial_summary=summary, segments=segments,
                current_pass=bool(current), voltage_pass=bool(voltage), power_pass=bool(power),
                strategy_constraints_pass=valid, all_three_constraints_pass=bool(valid and power))


def refinement_points(segments, hard_power):
    keys = ["current_peak_at_s", "voltage_peak_at_s"]
    if hard_power:
        keys.append("minimum_power_at_s")
    return np.unique([row[key] for row in segments for key in keys])


def run_stage(scaled, constraints, z, phase_one, deadline):
    start = time.monotonic()
    if phase_one:
        initial = np.r_[z, max(0., -float(constraints.values(z).min())) + 1e-8]
        fun = lambda y: float(y[-1])
        grad = lambda y: np.r_[np.zeros(len(y)-1), 1.]
        con, jac = constraints.slack_values, constraints.slack_jacobian
        bounds = [(None, None)]*len(z) + [(0., None)]
    else:
        initial = z.copy()
        fun, grad = scaled.objective, scaled.gradient
        con, jac = constraints.values, constraints.jacobian
        bounds = None
    accepted = initial.copy()
    history = []

    def budget():
        if time.monotonic() > min(start + STAGE_SECONDS, deadline):
            raise TimeoutError("Declared stage/total budget reached")

    def bounded(fn):
        def call(y):
            budget()
            return fn(y)
        return call

    def callback(y):
        nonlocal accepted
        accepted = y.copy()
        history.append(dict(iteration=len(history)+1, objective=float(fun(y)),
                            minimum_optimizer_constraint=float(con(y).min())))
        budget()

    try:
        solved = minimize(bounded(fun), initial, jac=bounded(grad), method="SLSQP", bounds=bounds,
                          constraints=dict(type="ineq", fun=bounded(con), jac=bounded(jac)),
                          callback=callback, options=dict(maxiter=MAX_ITER, ftol=1e-11, disp=False))
        y = solved.x
        state = dict(success=bool(solved.success), status=int(solved.status), message=str(solved.message),
                     iterations=int(solved.nit), termination="optimizer-returned")
    except TimeoutError as exc:
        y = accepted
        state = dict(success=False, status=None, message=str(exc), iterations=len(history),
                     termination="budget-exceeded-last-accepted-iterate")
    out_z = y[:-1] if phase_one else y
    return out_z, dict(phase="feasibility" if phase_one else "voltage-objective", optimizer=state,
        slack=float(y[-1]) if phase_one else None, elapsed_seconds=time.monotonic()-start,
        minimum_unrelaxed_normalized_constraint=float(constraints.values(out_z).min()), history=history)


def solve_strategy(scaled, hard_power, deadline, checkpoint):
    z = scaled.x0.copy()
    times = scaled.times.copy()
    rounds, feasible = [], []
    last = None
    stop = "round-budget-reached"
    for number in range(MAX_ROUNDS):
        if time.monotonic() >= deadline:
            stop = "total-budget-reached"
            break
        constraints = ConstraintGrid(scaled, times, hard_power)
        row = dict(round=number+1, constraint_times_s=times.tolist(), removed_constant_rows=constraints.removed,
                   stages=[])
        rounds.append(row)
        audits = []
        z, stage = run_stage(scaled, constraints, z, True, deadline)
        last = audit_candidate(scaled, z, hard_power)
        stage["audit"] = last
        row["stages"].append(stage)
        audits.append(last)
        checkpoint(dict(hard_power_constraint=hard_power, rounds=rounds))
        if last["strategy_constraints_pass"]:
            feasible.append((z.copy(), last, number+1, "feasibility"))
        sampled = scaled.check(z, times)
        sampled_valid = sampled["current_pass"] and sampled["voltage_pass"] and sampled["endpoint_pass"] and (sampled["power_pass"] or not hard_power)
        if sampled_valid and time.monotonic() < deadline:
            z, stage = run_stage(scaled, constraints, z, False, deadline)
            last = audit_candidate(scaled, z, hard_power)
            stage["audit"] = last
            row["stages"].append(stage)
            audits.append(last)
            checkpoint(dict(hard_power_constraint=hard_power, rounds=rounds))
            if last["strategy_constraints_pass"]:
                feasible.append((z.copy(), last, number+1, "voltage-objective"))
        if last["strategy_constraints_pass"]:
            stop = "candidate-passed-strategy-constraints"
            row["added_constraint_times_s"] = []
            checkpoint(dict(hard_power_constraint=hard_power, rounds=rounds))
            break
        new = np.unique(np.r_[times, *[refinement_points(a["segments"], hard_power) for a in audits]])
        added = np.setdiff1d(new, times)
        row["added_constraint_times_s"] = added.tolist()
        print(json.dumps(dict(strategy="with-power-floor" if hard_power else "voltage-only",
                              round=number+1, phases=[s["phase"] for s in row["stages"]],
                              minimum_power=last["polynomial_summary"]["minimum_power_pu"],
                              current_peak=last["polynomial_summary"]["current_peak_pu"],
                              added_points=len(added))), flush=True)
        checkpoint(dict(hard_power_constraint=hard_power, rounds=rounds))
        if not len(added):
            stop = "no-new-extremum-times"
            break
        times = new
    if last is None:
        last = audit_candidate(scaled, z, hard_power)
    selected_phase = "last-infeasible-diagnostic"
    selected_round = len(rounds)
    if feasible:
        z, last, selected_round, selected_phase = min(feasible, key=lambda item: item[1]["objective"])
    result = dict(strategy="with-power-floor" if hard_power else "voltage-only", hard_power_constraint=hard_power,
                  stop_reason=stop, rounds=rounds, feasible_candidate_count=len(feasible),
                  selected_round=selected_round, selected_phase=selected_phase,
                  knots_s=(scaled.knots*T).tolist(), degree=DEGREE, **last)
    if last["all_three_constraints_pass"]:
        result["independent_RL_replay"] = replay(scaled.knots*T, scaled.coefficients(z), scaled.case)
        result["hypothetical_LC_replay"] = replay(scaled.knots*T, scaled.coefficients(z), scaled.case, True)
    return result


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    files = [Path(__file__), PLAN] + [ROOT / f"experiments/phase-jump/{name}.py" for name in
        ["run_constrained_ocp", "run_scaled_ocp", "run_repaired_ocp", "run_power_feasibility", "verify_constrained_ocp"]]
    previous_path = ROOT / "results/phase-jump-power-feasibility/constrained-ocp-constant-repair-2026-10-05/result.json"
    files.append(previous_path)
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    for name, expected in previous["source_hashes"].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Frozen source changed: {name}")
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    scaled = ScaledProblem(SplineProblem())
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, inherited_source_hashes=previous["source_hashes"],
                  case=previous["case"], environment=previous["environment"],
                  configuration=dict(max_rounds=MAX_ROUNDS, max_iter=MAX_ITER, stage_seconds=STAGE_SECONDS,
                      total_seconds=TOTAL_SECONDS, check_tolerance=TOL, fixed_objective_configuration=previous["configuration"],
                      phase_one="min s subject to normalized g(z)+s>=0, s>=0", degree=DEGREE,
                      objective_quadrature_unchanged=True, spline_space_unchanged=True), strategies=[])
    OUTPUT.mkdir()

    def save():
        result["elapsed_seconds"] = time.monotonic()-started
        path = OUTPUT/"result.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Result readback failed")

    save()
    def checkpoint(active):
        result["active_trial"] = active
        save()

    try:
        for hard in [False, True]:
            result["strategies"].append(solve_strategy(scaled, hard, started+TOTAL_SECONDS, checkpoint))
            result.pop("active_trial", None)
            save()
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise AssertionError("Source drift during computation")
        baseline, modified = result["strategies"]
        result["paired_evidence_observed"] = bool(baseline["strategy_constraints_pass"] and not baseline["power_pass"] and modified["all_three_constraints_pass"])
        result["status"] = "complete"
    except Exception as exc:
        result["status"] = "execution-failed"
        result["failure"] = repr(exc)
        raise
    finally:
        save()
    print(json.dumps(dict(status=result["status"], elapsed_seconds=result["elapsed_seconds"],
                         paired_evidence_observed=result["paired_evidence_observed"],
                         strategies=[dict(strategy=r["strategy"], stop=r["stop_reason"],
                            feasible=r["strategy_constraints_pass"], summary=r["polynomial_summary"]) for r in result["strategies"]])), flush=True)


if __name__ == "__main__":
    main()
