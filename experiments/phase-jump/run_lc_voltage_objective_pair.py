"""Same fixed objective and physical model, differing only in power floor."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from lc_connected_coordinates import ConnectedScaledProblem
from lc_conic_subproblem import solve
from lc_conic_voltage_objective import build_objective_subproblem
from run_constrained_ocp import ROOT, SplineProblem, T, grid
from run_lc_conic_feasibility import extrema_times
from run_scaled_ocp import ScaledProblem
from verify_constrained_ocp import replay
from verify_lc_voltage_objective_pair import audit_strategy

PLAN = ROOT/"results/phase-jump-power-feasibility/lc-connected-objective-pair-plan-2026-10-05.md"
SOURCE = ROOT/"results/phase-jump-power-feasibility/lc-connected-conic-2026-10-05/result.json"
OUTPUT = ROOT/"results/phase-jump-power-feasibility/lc-connected-objective-pair-2026-10-05"


def own_violation(audit, case, hard):
    p = audit["physical_audit"]["polynomial_summary"]
    h = audit["physical_audit"]["hardware_summary"]
    return float(max(0., p["current_peak_pu"]-1.3, p["voltage_peak_pu"]-np.linalg.norm(case["frozen"]),
                     h["inverter_current_peak_pu"]-1.3, h["inverter_voltage_peak_pu"]-1.2,
                     case["ppre"]-p["minimum_power_pu"] if hard else 0.))


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    inherited = {**source["source_hashes"], **source["inherited_source_hashes"]}
    for name, expected in inherited.items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Frozen input changed: {name}")
    files = [Path(__file__), PLAN, SOURCE]
    files += [ROOT/f"experiments/phase-jump/{name}.py" for name in [
        "lc_conic_voltage_objective", "lc_connected_coordinates", "lc_conic_subproblem", "power_inner_approximation",
        "run_constrained_ocp", "run_scaled_ocp", "run_lc_conic_feasibility", "verify_lc_voltage_objective_pair",
        "verify_lc_connected_conic", "verify_constrained_ocp", "verify_lc_voltage_results", "verify_phase_one_refinement"]]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    old = ScaledProblem(SplineProblem())
    coordinates = source["coordinate_data"]
    p = ConnectedScaledProblem(old, np.asarray(coordinates["anchor_original_scaled"]))
    # The already feasible seed itself satisfies the equalities, so reprojection
    # only changes it by floating error. Recover its connected coordinates.
    selected = next(s for s in source["steps"] if s["step"] == source["selected_step"])
    physical = np.asarray(selected["coefficients"])[old.base.free].ravel()
    original_z = np.linalg.solve(old.transform, physical-old.base.x0)
    seed = p.null_basis.T@(original_z-p.anchor)
    coord = dict(anchor_original_scaled=p.anchor.tolist(), nullspace=p.null_basis.tolist(),
                 original_transform=old.transform.tolist(), original_physical_origin=old.base.x0.tolist(),
                 free_coefficient_indices=old.base.free.tolist())
    initial_times = np.unique(np.r_[grid(), extrema_times(selected["audit"])])
    OUTPUT.mkdir()
    began = time.monotonic()
    result = dict(status="running", source_hashes=hashes, inherited_source_hashes=inherited,
                  case=source["case"], hardware=source["hardware"], environment=source["environment"],
                  coordinate_data=coord, configuration=dict(max_steps_per_strategy=8, seconds_per_strategy=60.,
                      solver_seconds=15., voltage_limit_pu=1.2, physical_tolerance=1e-7, same_seed_connected=seed.tolist(),
                      same_initial_constraint_times_s=initial_times.tolist(), objective="Original voltage tracking plus 1e-4 voltage-rate integral"), strategies=[])

    def save():
        result["elapsed_seconds"] = time.monotonic()-began
        path = OUTPUT/"result.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Objective pair readback failed")

    def candidate(z, step, ref, delta):
        row = dict(step=step, reference_connected=ref.tolist(), increment_connected=delta.tolist(),
                   coefficients=p.coefficients(z).tolist(), knots_s=(p.knots*T).tolist(),
                   optimizer_voltage_envelope_pu=1.2, objective=float(p.objective(z)*p.scale))
        return row

    save()
    try:
        for hard in [False, True]:
            z, times = seed.copy(), initial_times.copy()
            start, stagnation = time.monotonic(), 0
            initial = candidate(z, 0, z, np.zeros_like(z))
            initial["audit"] = audit_strategy(initial, result["case"], hard)
            if not initial["audit"]["numerically_feasible"]:
                raise AssertionError("Lost common feasible initial witness")
            strategy = dict(hard_power=hard, candidates=[initial], solver_stages=[], selected_step=0)
            result["strategies"].append(strategy)
            best_violation, previous_objective = 0., initial["objective"]
            for step in range(1, 9):
                remaining = 60.-(time.monotonic()-start)
                if remaining <= 0:
                    strategy["stop_reason"] = "strategy-time-budget-reached"
                    break
                sub = build_objective_subproblem(p, times, z, hard)
                remaining = 60.-(time.monotonic()-start)
                if remaining <= 0:
                    strategy["stop_reason"] = "assembly-reached-strategy-budget"
                    break
                delta, state = solve(sub, min(15., remaining))
                stage = dict(step=step, optimizer=state, diagnostics=sub.diagnostics, constraint_times_s=times.tolist())
                strategy["solver_stages"].append(stage)
                if delta is None:
                    strategy["stop_reason"] = "no-numerical-primal-candidate"
                    save()
                    break
                next_z = z+delta
                row = candidate(next_z, step, z, delta)
                row["optimizer"] = state
                strategy["candidates"].append(row)
                save()
                row["audit"] = audit_strategy(row, result["case"], hard)
                row["physical_violation_pu"] = own_violation(row["audit"], result["case"], hard)
                valid = row["audit"]["numerically_feasible"]
                save()
                print(json.dumps(dict(hard_power=hard, step=step, solver=state["status"], feasible=valid,
                    objective=row["objective"], Pmin=row["audit"]["physical_audit"]["polynomial_summary"]["minimum_power_pu"])), flush=True)
                if valid and abs(row["objective"]-previous_objective) <= 1e-8*max(1., abs(previous_objective)):
                    strategy["stop_reason"] = "feasible-objective-change-small"
                    break
                if not valid:
                    if row["physical_violation_pu"] < best_violation-1e-12:
                        best_violation, stagnation = row["physical_violation_pu"], 0
                    else:
                        stagnation += 1
                    if stagnation >= 3:
                        strategy["stop_reason"] = "three-steps-no-physical-improvement"
                        break
                else:
                    stagnation = 0
                previous_objective, z = row["objective"], next_z
                times = np.unique(np.r_[times, extrema_times(row["audit"]["physical_audit"])])
            else:
                strategy["stop_reason"] = "step-budget-reached"
            feasible = [row for row in strategy["candidates"] if row["audit"]["numerically_feasible"]]
            best = min(feasible, key=lambda row: row["objective"])
            strategy["selected_step"] = best["step"]
            strategy["selected_objective"] = best["objective"]
            strategy["selected_from_optimization"] = best["step"] != 0
            strategy["hypothetical_LC_replay"] = replay(best["knots_s"], best["coefficients"], result["case"], True)
            strategy["elapsed_seconds"] = time.monotonic()-start
            save()
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise AssertionError("Source drift during objective pair")
        result["status"] = "complete"
    except Exception as exc:
        result["status"], result["failure"] = "execution-failed", repr(exc)
        raise
    finally:
        save()
    print(json.dumps(dict(status=result["status"], selected_steps=[s["selected_step"] for s in result["strategies"]], elapsed_seconds=result["elapsed_seconds"])))


if __name__ == "__main__":
    main()
