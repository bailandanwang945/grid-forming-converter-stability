"""One budgeted sequential SOCP feasibility check; no global proof."""
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import scipy

from lc_conic_subproblem import build_subproblem, solve
from run_constrained_ocp import ROOT, SplineProblem, T, grid
from run_scaled_ocp import ScaledProblem
from verify_constrained_ocp import replay
from verify_lc_voltage_results import check_candidate

PLAN = ROOT/"results/phase-jump-power-feasibility/lc-conic-feasibility-plan-2026-10-05.md"
SOURCE = ROOT/"results/phase-jump-power-feasibility/lc-voltage-envelope-2026-10-05/result.json"
OUTPUT = ROOT/"results/phase-jump-power-feasibility/lc-conic-feasibility-2026-10-05"
TOTAL_SECONDS, MAX_STEPS = 180., 12


def extrema_times(audit):
    return np.unique([row[key] for row in audit["segments"] for key in
                      ["current_peak_at_s", "voltage_peak_at_s", "minimum_power_at_s"]]
                     + [row[key] for row in audit["hardware_segments"] for key in
                        ["inverter_current_peak_at_s", "inverter_voltage_peak_at_s"]])


def physical_violation(audit, case):
    p, h = audit["polynomial_summary"], audit["hardware_summary"]
    return float(max(0., p["current_peak_pu"]-1.3,
                     p["voltage_peak_pu"]-np.linalg.norm(case["frozen"]),
                     case["ppre"]-p["minimum_power_pu"],
                     h["inverter_current_peak_pu"]-1.3,
                     h["inverter_voltage_peak_pu"]-1.2))


def main():
    import clarabel

    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    inherited = {**source["source_hashes"], **source["inherited_source_hashes"]}
    for name, expected in inherited.items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Frozen input changed: {name}")
    files = [Path(__file__), PLAN, SOURCE, ROOT/"references/manifests/lc-conic-solver-2026-10-05.json"]
    files += [ROOT/f"experiments/phase-jump/{name}.py" for name in [
        "lc_conic_subproblem", "power_inner_approximation", "run_constrained_ocp", "run_scaled_ocp",
        "run_lc_voltage_envelope", "verify_lc_voltage_results", "verify_lc_voltage_envelope",
        "verify_constrained_ocp", "verify_phase_one_refinement"]]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    p = ScaledProblem(SplineProblem())
    old = source["strategies"][0]
    z = np.linalg.solve(p.transform, np.asarray(old["coefficients"])[p.base.free].ravel()-p.base.x0)
    initial = check_candidate(old, source["case"], True)
    times = np.unique(np.r_[grid(), extrema_times(initial)])
    OUTPUT.mkdir()
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, inherited_source_hashes=inherited,
        environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                         clarabel=clarabel.__version__, solver="CLARABEL-direct-SOCP", threads=1),
        case=source["case"], hardware=source["hardware"], initial_audit=initial,
        configuration=dict(max_steps=MAX_STEPS, loop_seconds=TOTAL_SECONDS, solver_seconds=15., solver_max_iter=200,
                           inverter_voltage_limit_pu=1.2, inverter_current_limit_pu=1.3,
                           physical_tolerance=1e-7, solver_tolerance=1e-10, proximal_regularization=1e-8,
                           objective="slack + 1e-8*norm(scaled increment)^2", confirmation_scope="seen diagnostic scenario"),
        steps=[])

    def save():
        result["elapsed_seconds"] = time.monotonic()-started
        target = OUTPUT/"result.json"
        target.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(target.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Conic result readback failed")

    save()
    passing, stagnation = None, 0
    best_violation = physical_violation(initial, result["case"])
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
                       constraint_times_s=times.tolist(), reference_scaled=z.tolist(),
                       elapsed_seconds=time.monotonic()-before)
            result["steps"].append(row)
            if x is None:
                row["candidate_available"] = False
                result["stop_reason"] = "no-numerical-primal-candidate"
                save()
                break
            next_z = z+x[:-1]
            row.update(candidate_available=True, conic_slack=float(x[-1]), increment_scaled=x[:-1].tolist(),
                       coefficients=p.coefficients(next_z).tolist(), knots_s=(p.knots*T).tolist(),
                       optimizer_voltage_envelope_pu=1.2,
                       minimum_cone_margin=min(r["margin"] for r in sub.residuals(x[:-1], x[-1])),
                       sampled_original_power_min_pu=float(np.min(sub.power.value(next_z))))
            save()  # Preserve the numerical candidate before its independent audit.
            row["audit"] = check_candidate(row, result["case"], True)
            row["physical_violation_pu"] = physical_violation(row["audit"], result["case"])
            valid = bool(row["audit"]["strategy_constraints_pass"] and row["audit"]["epigraph_pass"])
            row["numerically_feasible"] = valid
            save()
            print(json.dumps(dict(step=step+1, status=state["status"], slack=row["conic_slack"],
                                  violation=row["physical_violation_pu"], feasible=valid)), flush=True)
            if valid:
                passing = row
                result["stop_reason"] = "original-constraints-numerically-feasible"
                break
            if row["physical_violation_pu"] < best_violation-1e-12:
                best_violation, stagnation = row["physical_violation_pu"], 0
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
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise AssertionError("Source drift during conic trial")
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
