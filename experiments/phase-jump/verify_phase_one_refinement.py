"""Re-read fixed candidates without importing their optimization evaluator."""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import BSpline

from verify_constrained_ocp import ROOT, K, VG, polynomial_audit

RESULT = ROOT / "results/phase-jump-power-feasibility/phase-one-refinement-2026-10-05/result.json"
TOL = 1e-7


def combined_constraint_check(summary, dense, endpoint, case, hard_power):
    """Require both numerical representations, never only the roots."""
    iok = summary["current_peak_pu"] <= 1.3 + TOL and dense["current_pass"]
    vok = summary["voltage_peak_pu"] <= np.linalg.norm(case["frozen"]) + TOL and dense["voltage_pass"]
    pok = summary["minimum_power_pu"] >= case["ppre"] - TOL and dense["power_pass"]
    representation_consistent = (dense["current_peak_pu"] <= summary["current_peak_pu"] + TOL
        and dense["voltage_peak_pu"] <= summary["voltage_peak_pu"] + TOL
        and dense["power_min_pu"] >= summary["minimum_power_pu"] - TOL)
    valid = bool(iok and vok and endpoint["passed"] and representation_consistent and (pok or not hard_power))
    return bool(iok), bool(vok), bool(pok), valid, bool(representation_consistent)


def endpoint_audit(knots, coefficients, case):
    spline = BSpline(knots, np.asarray(coefficients), 5)
    t0, tf = float(knots[0]), float(knots[-1])
    wb, lt, rt = case["wb"], case["lt"], case["rt"]
    frozen, initial, steady = [np.asarray(case[name]) for name in ["frozen", "i0", "iss"]]
    a = -wb*rt/lt*np.eye(2)-wb*K
    di0 = a @ initial + wb/lt*(frozen-VG)

    def v(t):
        i = spline(t)
        return VG + rt*i + lt*K@i + lt/wb*spline(t, nu=1)

    def dv(t):
        di = spline(t, nu=1)
        return rt*di + lt*K@di + lt/wb*spline(t, nu=2)

    residuals = dict(start_i=float(np.linalg.norm(spline(t0)-initial)),
        end_i=float(np.linalg.norm(spline(tf)-steady)),
        start_di=float(np.linalg.norm(spline(t0, nu=1)-di0)),
        end_di=float(np.linalg.norm(spline(tf, nu=1))),
        start_ddi=float(np.linalg.norm(spline(t0, nu=2)-a@di0)),
        end_ddi=float(np.linalg.norm(spline(tf, nu=2))),
        start_v=float(np.linalg.norm(v(t0)-frozen)),
        end_v=float(np.linalg.norm(v(tf)-(VG+rt*steady+lt*K@steady))),
        start_dv=float(np.linalg.norm(dv(t0))), end_dv=float(np.linalg.norm(dv(tf))))
    physical_keys = ["start_i", "end_i", "start_v", "end_v", "start_dv", "end_dv"]
    return dict(residuals=residuals, passed=bool(all(residuals[k] <= TOL for k in physical_keys)),
        units={k: "p.u./s^2" if k.endswith("ddi") else "p.u./s" if k.endswith("di") or k.endswith("dv") else "p.u." for k in residuals},
        checked_keys=physical_keys,
        scope="Independent current, capacitor-voltage and voltage-derivative endpoint match; raw current derivatives retained with units")


def main(result_path=RESULT):
    result_path = Path(result_path).resolve()
    if not result_path.is_relative_to(ROOT):
        raise ValueError("Result path escapes project")
    target = result_path.parent / "independent-verification.json"
    if target.exists():
        raise FileExistsError(target)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result["status"] != "complete" or len(result["strategies"]) != 2:
        raise ValueError("Comparison not complete")
    for collection in ["source_hashes", "inherited_source_hashes"]:
        for name, expected in result[collection].items():
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise AssertionError(f"Frozen source mismatch: {name}")
    rows = []
    for candidate in result["strategies"]:
        summary, segments = polynomial_audit(candidate["knots_s"], candidate["coefficients"], result["case"])
        end = endpoint_audit(candidate["knots_s"], candidate["coefficients"], result["case"])
        iok, vok, pok, valid, consistent = combined_constraint_check(summary, candidate["dense_check"], end,
                                                                    result["case"], candidate["hard_power_constraint"])
        if valid != candidate["strategy_constraints_pass"]:
            raise AssertionError("Independent feasibility classification differs")
        if candidate["selected_phase"] != "last-infeasible-diagnostic":
            selected = next(s for s in candidate["rounds"][candidate["selected_round"]-1]["stages"]
                            if s["phase"] == candidate["selected_phase"])
            if selected["audit"]["coefficients"] != candidate["coefficients"]:
                raise AssertionError("Selected stage coefficient provenance mismatch")
            optimized = bool(candidate["selected_phase"] == "voltage-objective" and selected["optimizer"]["success"])
        else:
            optimized = False
        rows.append(dict(strategy=candidate["strategy"], strategy_constraints_pass=valid,
                         current_pass=bool(iok), voltage_pass=bool(vok), power_pass=bool(pok),
                         selected_voltage_objective_solver_converged=optimized,
                         representations_consistent=consistent,
                         polynomial_summary=summary, segments=segments, independent_endpoints=end))
    baseline, modified = rows
    feasible_pair = bool(baseline["strategy_constraints_pass"] and not baseline["power_pass"] and modified["strategy_constraints_pass"])
    answer = dict(status="verified", result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), strategies=rows,
        feasible_trajectory_pair_observed=feasible_pair,
        converged_voltage_objective_pair_observed=bool(feasible_pair and baseline["selected_voltage_objective_solver_converged"] and modified["selected_voltage_objective_solver_converged"]),
        scope="Floating polynomial extrema and independently recomputed endpoints; not global optimality, interval proof or hardware qualification")
    target.write_text(json.dumps(answer, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    saved = json.loads(target.read_text(encoding="utf-8"))
    if saved["result_sha256"] != answer["result_sha256"]:
        raise AssertionError("Verification readback failed")
    print(json.dumps({k: v for k, v in answer.items() if k != "strategies"}))
    for row in rows:
        print(json.dumps({k: v for k, v in row.items() if k not in ["segments", "independent_endpoints"]}))


if __name__ == "__main__":
    main()
