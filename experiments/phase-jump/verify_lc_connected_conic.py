"""Original LC equations plus direct input endpoint and coordinate readback."""
import hashlib
import json
from pathlib import Path

import numpy as np

from lc_connected_coordinates import endpoint_input_audit
from verify_constrained_ocp import ROOT
from verify_lc_voltage_results import check_candidate

RESULT = ROOT/"results/phase-jump-power-feasibility/lc-connected-conic-2026-10-05/result.json"


def verify_step_coordinates(step, data):
    ref = np.asarray(step["reference_connected"])
    delta = np.asarray(step["increment_connected"])
    original = np.asarray(data["anchor_original_scaled"])+np.asarray(data["nullspace"]) @ (ref+delta)
    expected = np.asarray(data["original_physical_origin"])+np.asarray(data["original_transform"]) @ original
    actual = np.asarray(step["coefficients"])[data["free_coefficient_indices"]].ravel()
    if actual.shape != expected.shape or not np.all(np.isfinite(actual)):
        raise ValueError("Malformed saved coefficients")
    error = float(np.max(np.abs(actual-expected)))
    if error > 1e-10:
        raise AssertionError("Connected coordinate/coefficients provenance mismatch")
    return error


def main():
    target = RESULT.parent/"independent-verification.json"
    if target.exists():
        raise FileExistsError(target)
    record = json.loads(RESULT.read_text(encoding="utf-8"))
    if record["status"] != "complete":
        raise ValueError("Incomplete connected result")
    count = 0
    for key in ["source_hashes", "inherited_source_hashes"]:
        for name, expected in record[key].items():
            source = (ROOT/name).resolve()
            if not source.is_relative_to(ROOT) or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
                raise AssertionError(f"Source identity mismatch: {name}")
            count += 1
    rows = []
    for step in record["steps"]:
        if not step["candidate_available"]:
            rows.append(dict(step=step["step"], candidate_available=False))
            continue
        error = verify_step_coordinates(step, record["coordinate_data"])
        checked = check_candidate(step, record["case"], True)
        endpoint = endpoint_input_audit(step["knots_s"], step["coefficients"], record["case"])
        valid = bool(checked["strategy_constraints_pass"] and checked["epigraph_pass"] and endpoint["input_endpoint_pass"])
        if valid != step["numerically_feasible"]:
            raise AssertionError("Physical classification drift")
        rows.append(dict(step=step["step"], candidate_available=True, numerically_feasible=valid,
                         coordinate_readback_error=error, physical_audit=checked, input_endpoint_audit=endpoint))
    if record["numerically_feasible"]:
        selected = next(row for row in rows if row["step"] == record["selected_step"])
        if not selected.get("numerically_feasible"):
            raise AssertionError("Selected step failed original checks")
    report = dict(status="verified", result_sha256=hashlib.sha256(RESULT.read_bytes()).hexdigest(),
                  verification_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  source_hash_comparisons=count, numerically_feasible=record["numerically_feasible"], steps=rows,
                  scope="Physical equation/extremum readback and direct BSpline vi endpoint checks; not a strict interval proof or real hardware measurement")
    target.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    if json.loads(target.read_text(encoding="utf-8"))["result_sha256"] != report["result_sha256"]:
        raise AssertionError("Verification readback failed")
    print(json.dumps({key:report[key] for key in ["status", "source_hash_comparisons", "numerically_feasible"]}))


if __name__ == "__main__":
    main()
