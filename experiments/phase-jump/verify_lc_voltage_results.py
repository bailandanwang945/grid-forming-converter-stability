"""Independent reread of the declared-LC peak-voltage experiment.

No optimization evaluator is imported. Numerical feasibility is not hardware
qualification, an interval bound, or a global voltage-minimum proof.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import BSpline

from verify_constrained_ocp import ROOT, K, VG, polynomial_audit
from verify_lc_voltage_envelope import CF, X1, R1, hardware_audit
from verify_phase_one_refinement import endpoint_audit, combined_constraint_check

RESULT = ROOT / "results/phase-jump-power-feasibility/lc-voltage-envelope-2026-10-05/result.json"
TOL = 1e-7


def dense_check(knots, coefficients, case):
    """Direct spline equations, separate from the affine optimizer maps."""
    spline = BSpline(knots, np.asarray(coefficients), 5)
    end = float(knots[-1])
    times = np.unique(np.r_[np.linspace(0, .005, 2001), np.linspace(.005, end, 6001), knots])
    i, di = spline(times), spline(times, nu=1)
    v = VG+case["rt"]*i+case["lt"]*i@K.T+case["lt"]/case["wb"]*di
    poi = case["alpha"]*v+case["beta"]*VG+case["correction"]*i
    ip, vp, pm = float(np.max(np.linalg.norm(i, axis=1))), float(np.max(np.linalg.norm(v, axis=1))), float(np.min(np.sum(poi*i, axis=1)))
    return dict(grid_count=len(times), current_peak_pu=ip, voltage_peak_pu=vp, power_min_pu=pm,
                current_pass=bool(ip <= 1.3+TOL), voltage_pass=bool(vp <= np.linalg.norm(case["frozen"])+TOL),
                power_pass=bool(pm >= case["ppre"]-TOL))


def check_candidate(candidate, case, limit_i1):
    knots, coef = candidate["knots_s"], candidate["coefficients"]
    summary, segments = polynomial_audit(knots, coef, case)
    hardware, hsegments = hardware_audit(knots, coef, case)
    dense, endpoint = dense_check(knots, coef, case), endpoint_audit(knots, coef, case)
    _, _, _, original_pass, consistent = combined_constraint_check(summary, dense, endpoint, case, True)
    i1pass = hardware["inverter_current_peak_pu"] <= 1.3+TOL
    state_connection = max(hardware["endpoint_inverter_current_errors"].values()) <= TOL and hardware["endpoint_check"]["maximum_internal_i1_jump_pu"] <= TOL
    physical_pass = bool(original_pass and consistent and state_connection and (i1pass or not limit_i1))
    envelope = candidate.get("optimizer_voltage_envelope_pu")
    return dict(strategy_constraints_pass=physical_pass, inverter_current_pass=bool(i1pass),
        actual_voltage_peak_pu=hardware["inverter_voltage_peak_pu"], hardware_summary=hardware,
        polynomial_summary=summary, dense_check=dense, independent_endpoints=endpoint,
        epigraph_pass=None if envelope is None else hardware["inverter_voltage_peak_pu"] <= envelope+TOL,
        segments=segments, hardware_segments=hsegments)


def boundary_demands(case):
    """Necessary point demands only for a scheme including adjacent stages."""
    wb, lt, rt = case["wb"], case["lt"], case["rt"]
    i0, frozen, steady = [np.asarray(case[key]) for key in ["i0", "frozen", "iss"]]
    di0 = wb/lt*(frozen-VG-rt*i0)-wb*K@i0
    i1_before = i0+CF*K@frozen
    vi_before = frozen+R1*i1_before+X1*K@i1_before+X1/wb*di0
    vc_after = VG+rt*steady+lt*K@steady
    i1_after = steady+CF*K@vc_after
    vi_after = vc_after+R1*i1_after+X1*K@i1_after
    return dict(frozen_segment_join_voltage_pu=float(np.linalg.norm(vi_before)),
                sustained_steady_voltage_pu=float(np.linalg.norm(vi_after)),
                necessary_point_lower_bound_for_including_adjacent_stages_pu=float(max(np.linalg.norm(vi_before), np.linalg.norm(vi_after))),
                inverter_current_at_frozen_join_pu=float(np.linalg.norm(i1_before)),
                inverter_current_at_steady_pu=float(np.linalg.norm(i1_after)),
                scope="Pointwise necessary demands when including frozen stage and sustained final steady state; not a lower bound proved for only the 60-ms optimization interval")


def main(result_path=RESULT):
    path = Path(result_path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Result escapes project")
    target = path.parent/"independent-verification.json"
    if target.exists():
        raise FileExistsError(target)
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["status"] != "complete" or len(result["strategies"]) != 2:
        raise ValueError("Result is incomplete")
    for collection in ["source_hashes", "inherited_source_hashes"]:
        for name, expected in result[collection].items():
            p = (ROOT/name).resolve()
            if not p.is_relative_to(ROOT) or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                raise AssertionError(f"Frozen source mismatch: {name}")
    baseline = check_candidate(result["initial_audit"], result["case"], False)
    if not baseline["strategy_constraints_pass"]:
        raise AssertionError("Lost known initial feasible witness")
    rows = []
    for candidate in result["strategies"]:
        verified = check_candidate(candidate, result["case"], candidate["limit_inverter_current"])
        if candidate["strategy_constraints_pass"] != verified["strategy_constraints_pass"]:
            raise AssertionError("Final feasibility classification mismatch")
        converged = False
        if candidate["selected_phase"] != "last-infeasible-diagnostic":
            stage = next(s for s in candidate["rounds"][candidate["selected_round"]-1]["stages"] if s["phase"] == candidate["selected_phase"])
            if stage["coefficients"] != candidate["coefficients"]:
                raise AssertionError("Selected stage coefficient mismatch")
            converged = bool(candidate["selected_phase"] == "minimax-voltage" and stage["optimizer"]["success"] and verified["epigraph_pass"])
        verified.update(strategy=candidate["strategy"], limit_inverter_current=candidate["limit_inverter_current"],
                        selected_phase=candidate["selected_phase"], peak_optimizer_converged=converged,
                        lower_voltage_than_initial=bool(verified["strategy_constraints_pass"] and verified["actual_voltage_peak_pu"] < baseline["actual_voltage_peak_pu"]),
                        voltage_bound_interpretation="Feasible candidate peak gives a numerical upper bound on required voltage; not a global minimum")
        rows.append(verified)
    answer = dict(status="verified", result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), initial_feasible_witness=baseline,
        boundary_demands=boundary_demands(result["case"]), strategies=rows,
        scope="Declared LC hardware; independent equations, floating polynomial extrema and endpoint checks; no DC, modulation or closed-loop validation")
    target.write_text(json.dumps(answer, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    saved = json.loads(target.read_text(encoding="utf-8"))
    if saved["result_sha256"] != answer["result_sha256"]:
        raise AssertionError("Verification readback failed")
    print(json.dumps(dict(status=saved["status"], boundary_demands=saved["boundary_demands"],
        strategies=[{k:s[k] for k in ["strategy", "strategy_constraints_pass", "actual_voltage_peak_pu", "inverter_current_pass", "selected_phase", "peak_optimizer_converged"]} for s in rows])))


if __name__ == "__main__":
    main()
