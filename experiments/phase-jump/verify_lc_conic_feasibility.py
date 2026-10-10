"""Read back all SOCP candidates and recheck original physical equations."""
import hashlib
import json
from pathlib import Path

from verify_constrained_ocp import ROOT
from verify_lc_voltage_results import check_candidate

RESULT = ROOT/"results/phase-jump-power-feasibility/lc-conic-feasibility-2026-10-05/result.json"


def verify(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Result escapes project")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["status"] != "complete":
        raise ValueError("Incomplete result")
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
        if step["optimizer_voltage_envelope_pu"] != record["configuration"]["inverter_voltage_limit_pu"]:
            raise AssertionError("Voltage cap mismatch")
        checked = check_candidate(step, record["case"], True)
        valid = bool(checked["strategy_constraints_pass"] and checked["epigraph_pass"])
        if valid != step["numerically_feasible"]:
            raise AssertionError("Physical classification drift")
        rows.append(dict(step=step["step"], candidate_available=True, numerically_feasible=valid,
                         optimizer_status=step["optimizer"]["status"], physical_audit=checked))
    if record["numerically_feasible"]:
        selected = next(row for row in rows if row["step"] == record["selected_step"])
        if not selected.get("numerically_feasible"):
            raise AssertionError("Selected step failed original checks")
        saved = next(step for step in record["steps"] if step["step"] == record["selected_step"])
        if saved["coefficients"] != record["steps"][record["selected_step"]-1]["coefficients"]:
            raise AssertionError("Selected coefficients mismatch")
    return dict(status="verified", result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                verification_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                source_hash_comparisons=count, numerically_feasible=record["numerically_feasible"],
                steps=rows, scope="Original dq equations, endpoints, dense checks and floating segment extrema; not an independent physical experiment or exact interval proof")


def main():
    target = RESULT.parent/"independent-verification.json"
    if target.exists():
        raise FileExistsError(target)
    report = verify(RESULT)
    target.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    if json.loads(target.read_text(encoding="utf-8"))["result_sha256"] != report["result_sha256"]:
        raise AssertionError("Verification readback failed")
    print(json.dumps({key:report[key] for key in ["status", "source_hash_comparisons", "numerically_feasible"]}))


if __name__ == "__main__":
    main()
