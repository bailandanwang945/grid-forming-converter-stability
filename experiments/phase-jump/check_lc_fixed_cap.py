"""One bounded closest-trajectory repair under declared finite LC ratings."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from run_constrained_ocp import ROOT, SplineProblem, grid, T
from run_scaled_ocp import ScaledProblem
from run_lc_voltage_envelope import LCConstraintGrid
from verify_constrained_ocp import replay
from verify_lc_voltage_results import check_candidate, boundary_demands

PLAN = ROOT / "results/phase-jump-power-feasibility/lc-fixed-cap-feasibility-plan-2026-10-05.md"
SOURCE = ROOT / "results/phase-jump-power-feasibility/lc-voltage-envelope-2026-10-05/result.json"
OUT = ROOT / "results/phase-jump-power-feasibility/lc-fixed-cap-feasibility-2026-10-05.json"
VIMAX = 1.2


def candidate_times(candidate):
    a = candidate["segments"]
    b = candidate["hardware_segments"]
    return np.unique([r[k] for r in a for k in ["current_peak_at_s", "voltage_peak_at_s", "minimum_power_at_s"]]
                     + [r[k] for r in b for k in ["inverter_current_peak_at_s", "inverter_voltage_peak_at_s"]])


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    inherited = {**source["source_hashes"], **source["inherited_source_hashes"]}
    for name, expected in inherited.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Frozen source changed: {name}")
    files = [Path(__file__), PLAN, SOURCE] + [ROOT/f"experiments/phase-jump/{n}.py" for n in
            ["verify_lc_voltage_results", "verify_lc_voltage_envelope", "verify_phase_one_refinement", "verify_constrained_ocp"]]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    p = ScaledProblem(SplineProblem())
    original = source["strategies"][0]
    zref = np.linalg.solve(p.transform, np.asarray(original["coefficients"])[p.base.free].ravel()-p.base.x0)
    z = zref.copy()
    times = np.unique(np.r_[grid(True), candidate_times(original)])
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, inherited_source_hashes=inherited,
        environment=source["environment"], case=source["case"], hardware=source["hardware"],
        configuration=dict(inverter_voltage_limit_pu=VIMAX, inverter_current_limit_pu=1.3, tolerance=1e-7,
            max_rounds=3, max_iter=100, stage_seconds=15., optimization_seconds=50.,
            objective="squared distance from initial scaled coefficients", confirmation_scope="previously seen diagnostic grid"),
        boundary_demands=boundary_demands(source["case"]), rounds=[])

    def save():
        result["elapsed_seconds"] = time.monotonic()-started
        OUT.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(OUT.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Fixed-cap result readback failed")

    save()
    passing = None
    try:
        for n in range(3):
            if time.monotonic()-started > 50.:
                result["stop_reason"] = "optimization-total-budget-reached"
                break
            g = LCConstraintGrid(p, times, True, VIMAX)
            stage_start, accepted, history = time.monotonic(), z.copy(), []

            def budget():
                if time.monotonic() > min(started+50., stage_start+15.):
                    raise TimeoutError("Declared fixed-cap budget reached")

            def objective(x):
                budget()
                return float(np.dot(x-zref, x-zref))

            def gradient(x):
                budget()
                return 2*(x-zref)

            def constraints(x):
                budget()
                return g.epigraph_values(np.r_[x, 1.])

            def jacobian(x):
                budget()
                return g.epigraph_jac(np.r_[x, 1.])[:, :-1]

            def callback(x):
                nonlocal accepted
                accepted = x.copy()
                history.append(dict(iteration=len(history)+1, minimum_constraint=float(constraints(x).min())))
                budget()

            try:
                solution = minimize(objective, z, jac=gradient, method="SLSQP",
                    constraints=dict(type="ineq", fun=constraints, jac=jacobian), callback=callback,
                    options=dict(maxiter=100, ftol=1e-13, disp=False))
                z = solution.x
                state = dict(success=bool(solution.success), status=int(solution.status), message=str(solution.message), iterations=int(solution.nit))
            except TimeoutError as exc:
                z = accepted
                state = dict(success=False, status=None, message=str(exc), iterations=len(history))
            row = dict(round=n+1, optimizer=state, history=history, constraint_times_s=times.tolist(),
                coefficients=p.coefficients(z).tolist(), knots_s=(p.knots*T).tolist(), optimizer_voltage_envelope_pu=VIMAX,
                elapsed_seconds=time.monotonic()-stage_start)
            result["rounds"].append(row)
            save()
            row["audit"] = check_candidate(row, result["case"], True)
            save()
            valid = row["audit"]["strategy_constraints_pass"] and row["audit"]["epigraph_pass"]
            print(json.dumps(dict(round=n+1, feasible=valid, optimizer=state,
                minimum_power=row["audit"]["polynomial_summary"]["minimum_power_pu"],
                voltage=row["audit"]["actual_voltage_peak_pu"],
                i1=row["audit"]["hardware_summary"]["inverter_current_peak_pu"])), flush=True)
            if valid:
                passing = row
                result["stop_reason"] = "fixed-cap-numerically-feasible"
                break
            times = np.unique(np.r_[times, candidate_times(row["audit"])])
        else:
            result["stop_reason"] = "round-budget-reached"
        result["status"] = "complete"
        result["numerically_feasible"] = passing is not None
        if passing is not None:
            result["selected_round"] = passing["round"]
            # The old replay is a separate forward integration of prescribed vi.
            result["hypothetical_LC_replay"] = replay(passing["knots_s"], passing["coefficients"], result["case"], True)
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise AssertionError("Source drift during fixed-cap trial")
    except Exception as exc:
        result["status"], result["failure"] = "execution-failed", repr(exc)
        raise
    finally:
        save()
    print(json.dumps(dict(status=result["status"], numerically_feasible=result.get("numerically_feasible"), elapsed_seconds=result["elapsed_seconds"])))


if __name__ == "__main__":
    main()
