"""Bounded SOCP check in a narrower voltage-endpoint-matched spline set."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from lc_connected_coordinates import ConnectedScaledProblem, endpoint_input_audit
from lc_conic_subproblem import build_subproblem, solve
from run_constrained_ocp import ROOT, SplineProblem, T, grid
from run_lc_conic_feasibility import extrema_times, physical_violation
from run_scaled_ocp import ScaledProblem
from verify_constrained_ocp import replay
from verify_lc_voltage_results import check_candidate

PLAN = ROOT/"results/phase-jump-power-feasibility/lc-connected-conic-plan-2026-10-05.md"
SOURCE = ROOT/"results/phase-jump-power-feasibility/lc-conic-feasibility-2026-10-05/result.json"
OUTPUT = ROOT/"results/phase-jump-power-feasibility/lc-connected-conic-2026-10-05"
TOTAL_SECONDS, MAX_STEPS = 180., 12


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not source["numerically_feasible"]:
        raise ValueError("Endpoint experiment requires the preserved finite-cap feasible seed")
    inherited = {**source["source_hashes"], **source["inherited_source_hashes"]}
    for name, expected in inherited.items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Frozen input changed: {name}")
    files = [Path(__file__), PLAN, SOURCE]
    files += [ROOT/f"experiments/phase-jump/{name}.py" for name in [
        "lc_connected_coordinates", "lc_conic_subproblem", "power_inner_approximation", "run_constrained_ocp",
        "run_scaled_ocp", "run_lc_conic_feasibility", "run_lc_voltage_envelope", "verify_lc_voltage_results",
        "verify_lc_voltage_envelope", "verify_constrained_ocp", "verify_phase_one_refinement"]]
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    old_scaled = ScaledProblem(SplineProblem())
    old = next(row for row in source["steps"] if row["step"] == source["selected_step"])
    seed = np.linalg.solve(old_scaled.transform, np.asarray(old["coefficients"])[old_scaled.base.free].ravel()-old_scaled.base.x0)
    p = ConnectedScaledProblem(old_scaled, seed)
    z = p.x0.copy()
    original_endpoint = endpoint_input_audit(old["knots_s"], old["coefficients"], source["case"])
    initial_row = dict(coefficients=p.coefficients(z).tolist(), knots_s=(p.knots*T).tolist(), optimizer_voltage_envelope_pu=1.2)
    initial = check_candidate(initial_row, source["case"], True)
    initial_endpoint = endpoint_input_audit(initial_row["knots_s"], initial_row["coefficients"], source["case"])
    times = np.unique(np.r_[grid(), extrema_times(old["audit"]), extrema_times(initial)])
    OUTPUT.mkdir()
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, inherited_source_hashes=inherited,
        environment=source["environment"], case=source["case"], hardware=source["hardware"],
        configuration=dict(max_steps=MAX_STEPS, loop_seconds=TOTAL_SECONDS, solver_seconds=15., solver_max_iter=200,
                           inverter_voltage_limit_pu=1.2, inverter_current_limit_pu=1.3, physical_tolerance=1e-7,
                           proximal_regularization=1e-8, objective="slack + 1e-8*norm(connected scaled increment)^2",
                           scope="Four new scalar vi endpoint conditions; narrower feasible set; seen diagnostic scenario"),
        coordinate_data=dict(anchor_original_scaled=p.anchor.tolist(), nullspace=p.null_basis.tolist(),
                             original_transform=old_scaled.transform.tolist(),
                             original_physical_origin=old_scaled.base.x0.tolist(),
                             free_coefficient_indices=old_scaled.base.free.tolist(), diagnostics=p.diagnostics),
        original_seed_input_endpoints=original_endpoint, projected_initial_audit=initial,
        projected_initial_input_endpoints=initial_endpoint, steps=[])

    def save():
        result["elapsed_seconds"] = time.monotonic()-started
        path = OUTPUT/"result.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Connected result readback failed")

    save()
    passing, stagnation = None, 0
    best = physical_violation(initial, result["case"])
    try:
        for step in range(MAX_STEPS):
            remaining = TOTAL_SECONDS-(time.monotonic()-started)
            if remaining <= 0:
                result["stop_reason"] = "loop-budget-reached"
                break
            before = time.monotonic()
            sub = build_subproblem(p, times, z)
            remaining = TOTAL_SECONDS-(time.monotonic()-started)
            if remaining <= 0:
                result["stop_reason"] = "assembly-reached-loop-budget"
                break
            x, state = solve(sub, min(15., remaining))
            row = dict(step=step+1, optimizer=state, diagnostics=sub.diagnostics,
                       constraint_times_s=times.tolist(), reference_connected=z.tolist(), elapsed_seconds=time.monotonic()-before)
            result["steps"].append(row)
            if x is None:
                row["candidate_available"] = False
                result["stop_reason"] = "no-numerical-primal-candidate"
                save()
                break
            next_z = z+x[:-1]
            row.update(candidate_available=True, conic_slack=float(x[-1]), increment_connected=x[:-1].tolist(),
                       coefficients=p.coefficients(next_z).tolist(), knots_s=(p.knots*T).tolist(),
                       optimizer_voltage_envelope_pu=1.2,
                       minimum_cone_margin=min(r["margin"] for r in sub.residuals(x[:-1], x[-1])))
            save()
            row["audit"] = check_candidate(row, result["case"], True)
            row["input_endpoint_audit"] = endpoint_input_audit(row["knots_s"], row["coefficients"], result["case"])
            row["physical_violation_pu"] = physical_violation(row["audit"], result["case"])
            valid = bool(row["audit"]["strategy_constraints_pass"] and row["audit"]["epigraph_pass"]
                         and row["input_endpoint_audit"]["input_endpoint_pass"])
            row["numerically_feasible"] = valid
            save()
            print(json.dumps(dict(step=step+1, status=state["status"], slack=row["conic_slack"],
                                  violation=row["physical_violation_pu"], input_endpoint_pass=row["input_endpoint_audit"]["input_endpoint_pass"],
                                  feasible=valid)), flush=True)
            if valid:
                passing = row
                result["stop_reason"] = "original-constraints-and-input-endpoints-numerically-feasible"
                break
            if not row["input_endpoint_audit"]["input_endpoint_pass"]:
                result["stop_reason"] = "eliminated-input-endpoint-condition-failed-audit"
                break
            if row["physical_violation_pu"] < best-1e-12:
                best, stagnation = row["physical_violation_pu"], 0
            else:
                stagnation += 1
            if stagnation >= 3:
                result["stop_reason"] = "three-steps-no-physical-improvement"
                break
            z = next_z
            times = np.unique(np.r_[times, extrema_times(row["audit"])])
        else:
            result["stop_reason"] = "step-budget-reached"
        result["numerically_feasible"] = passing is not None
        if passing is not None:
            result["selected_step"] = passing["step"]
            result["hypothetical_LC_replay"] = replay(passing["knots_s"], passing["coefficients"], result["case"], True)
        if hashes != {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}:
            raise AssertionError("Source drift during connected trial")
        result["status"] = "complete"
    except Exception as exc:
        result["status"], result["failure"] = "execution-failed", repr(exc)
        raise
    finally:
        save()
    print(json.dumps(dict(status=result["status"], feasible=result.get("numerically_feasible"),
                         steps=len(result["steps"]), elapsed_seconds=result["elapsed_seconds"])))


if __name__ == "__main__":
    main()
