"""Recheck every fixed combination and fixed-cap stage; no new search."""
import hashlib
import json
from pathlib import Path

from verify_constrained_ocp import ROOT
from verify_lc_voltage_results import check_candidate

FILES = [ROOT / "results/phase-jump-power-feasibility/lc-trajectory-combination-2026-10-05.json",
         ROOT / "results/phase-jump-power-feasibility/lc-fixed-cap-feasibility-2026-10-05.json"]
OUT = ROOT / "results/phase-jump-power-feasibility/lc-followup-verification-2026-10-05.json"


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    reports = []
    for path in FILES:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["status"] != "complete":
            raise AssertionError("Execution record incomplete")
        for collection in ["source_hashes", "inherited_source_hashes"]:
            for name, expected in record[collection].items():
                p = (ROOT/name).resolve()
                if not p.is_relative_to(ROOT) or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                    raise AssertionError(f"Frozen source changed: {name}")
        candidates = record.get("candidates", record.get("rounds", []))
        rows = []
        for candidate in candidates:
            checked = check_candidate(candidate, record["case"], True)
            if checked["strategy_constraints_pass"] != candidate["audit"]["strategy_constraints_pass"]:
                raise AssertionError("Feasibility classification drift")
            actual = bool(checked["strategy_constraints_pass"] and checked["epigraph_pass"] is not False)
            rows.append(dict(identifier=candidate.get("lambda_value", candidate.get("round")),
                feasible=actual, power_min_pu=checked["polynomial_summary"]["minimum_power_pu"],
                voltage_peak_pu=checked["actual_voltage_peak_pu"],
                inverter_current_peak_pu=checked["hardware_summary"]["inverter_current_peak_pu"]))
        if any(r["feasible"] for r in rows):
            raise AssertionError("Unexpected feasible result: require updated explanation")
        reports.append(dict(path=str(path.relative_to(ROOT)), result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), rows=rows))
    result = dict(status="verified", script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  results=reports, scope="Re-read and numerical re-evaluation using the independent hardware checker, not a new independent physical method")
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    if json.loads(OUT.read_text(encoding="utf-8"))["status"] != "verified":
        raise AssertionError("Verification readback failed")
    print(json.dumps(dict(status="verified", counts=[len(r["rows"]) for r in reports], feasible=0)))


if __name__ == "__main__":
    main()
