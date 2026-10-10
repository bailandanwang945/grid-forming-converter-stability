"""Readback of a paired objective experiment, without optimization imports."""
import hashlib
import json
from pathlib import Path

from lc_connected_coordinates import endpoint_input_audit
from verify_constrained_ocp import ROOT
from verify_lc_connected_conic import verify_step_coordinates
from verify_lc_voltage_results import check_candidate
from verify_phase_one_refinement import combined_constraint_check

RESULT = ROOT/"results/phase-jump-power-feasibility/lc-connected-objective-pair-2026-10-05/result.json"


def audit_strategy(candidate, case, hard_power):
    audit = check_candidate(candidate, case, True)
    _, _, power_pass, original_pass, consistent = combined_constraint_check(
        audit["polynomial_summary"], audit["dense_check"], audit["independent_endpoints"], case, hard_power)
    h = audit["hardware_summary"]
    state_connection = max(h["endpoint_inverter_current_errors"].values()) <= 1e-7
    state_connection &= h["endpoint_check"]["maximum_internal_i1_jump_pu"] <= 1e-7
    endpoint = endpoint_input_audit(candidate["knots_s"], candidate["coefficients"], case)
    valid = bool(original_pass and consistent and audit["inverter_current_pass"] and audit["epigraph_pass"]
                 and state_connection and endpoint["input_endpoint_pass"])
    return dict(numerically_feasible=valid, power_floor_pass=power_pass, physical_audit=audit,
                input_endpoint_audit=endpoint, scope="Own strategy constraints; missing power floor is not baseline failure")


def main():
    target = RESULT.parent/"independent-verification.json"
    if target.exists():
        raise FileExistsError(target)
    record = json.loads(RESULT.read_text(encoding="utf-8"))
    if record["status"] != "complete" or len(record["strategies"]) != 2:
        raise ValueError("Incomplete objective pair")
    count = 0
    for key in ["source_hashes", "inherited_source_hashes"]:
        for name, expected in record[key].items():
            path = (ROOT/name).resolve()
            if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise AssertionError(f"Source identity mismatch: {name}")
            count += 1
    strategies = []
    for strategy in record["strategies"]:
        checked_rows = []
        for candidate in strategy["candidates"]:
            provenance = verify_step_coordinates(candidate, record["coordinate_data"])
            checked = audit_strategy(candidate, record["case"], strategy["hard_power"])
            if checked["numerically_feasible"] != candidate["audit"]["numerically_feasible"]:
                raise AssertionError("Candidate classification drift")
            checked_rows.append(dict(step=candidate["step"], coordinate_error=provenance, audit=checked))
        selected = next(row for row in checked_rows if row["step"] == strategy["selected_step"])
        if not selected["audit"]["numerically_feasible"]:
            raise AssertionError("Invalid selected candidate")
        strategies.append(dict(hard_power=strategy["hard_power"], selected_step=strategy["selected_step"], candidates=checked_rows))
    report = dict(status="verified", result_sha256=hashlib.sha256(RESULT.read_bytes()).hexdigest(),
                  verification_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  source_hash_comparisons=count, strategies=strategies,
                  scope="Every candidate's original constraints and coefficient provenance; no strict interval or optimality proof")
    target.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    if json.loads(target.read_text(encoding="utf-8"))["result_sha256"] != report["result_sha256"]:
        raise AssertionError("Verification readback failed")
    print(json.dumps(dict(status="verified", source_hash_comparisons=count,
                          candidate_counts=[len(s["candidates"]) for s in strategies])))


if __name__ == "__main__":
    main()
