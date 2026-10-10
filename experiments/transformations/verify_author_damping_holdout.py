"""Read-only consistency audit of saved damping holdout results.

This audits identities, poles and recorded classifications; it does not
independently recompute the gain/phase inequalities or validate the theorem.
"""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "results/automatic-transform-search/new-operating-points-01/comparison.json"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def audit(comparison, models, selection):
    require(comparison["status"] == models["status"] == "complete", "Incomplete result")
    require(comparison["theorem_status"] == "not-evaluated-by-sampled-api", "Scope changed")
    frozen = {name: row["candidate"] for name, row in selection["selected"].items()}
    require(comparison["frozen_candidates"] == frozen, "Candidates were not frozen")
    exported = {row["damping"]: row for row in models["cases"]}
    require(set(exported) == {.05, .1, .2, .35, .5}, "Unexpected model cases")
    require([r["damping"] for r in comparison["cases"]] == [.1, .2, .35], "Unexpected test cases")
    original_grid = exported[.05]["frequencies_hz"]
    require(len(original_grid) == 1000, "Incomplete grid")
    for row in exported.values():
        require(row["frequencies_hz"] == original_grid, "Different grids")
        require(row["network"] == exported[.05]["network"], "Network changed")
        for port in ("converter", "network"):
            for values in row[port].values():
                require(len(values) == 1000 and all(math.isfinite(v) for v in values), "Invalid response")
    summaries = []
    found = False
    for row in comparison["cases"]:
        model = exported[row["damping"]]
        poles = [complex(*pair) for pair in model["closed_loop_poles_per_second"]]
        zeros = [complex(*pair) for pair in model["return_zeros_per_second"]]
        dominant = max(p.real for p in poles)
        require(abs(dominant - row["dominant_real_per_second"]) < 1e-10, "Dominant root differs")
        require(abs(dominant - model["dominant_real_per_second"]) < 1e-10, "Export root differs")
        reference = "stable" if dominant < -1e-7 else "unstable" if dominant > 1e-7 else "numerical-pending"
        require(reference == row["closed_loop_reference"], "Wrong reference label")
        leading = [p for p in poles if abs(p.real - dominant) < 1e-9]
        mismatch = max(min(abs(p - z) for z in zeros) for p in leading)
        require(mismatch < 1e-7, "Dominant port-zero mismatch")
        counts = {}
        for name, metrics in row["strategies"].items():
            require(metrics["status"] == "sampled-only", "Rejected strategy not audited")
            require(metrics["point_count"] == 1000, "Incomplete evaluation")
            for kind in ("gain", "phase"):
                labels = metrics[kind + "_status"]
                require(len(labels) == 1000 and set(labels) <= {"pass", "fail", "indeterminate"}, "Invalid labels")
                actual = Counter(labels)
                require(all(actual[k] == metrics["counts"][kind][k] for k in ("pass", "fail", "indeterminate")), "Counts disagree")
            coverage = metrics["coverage"]
            expected = []
            for gain, phase in zip(metrics["gain_status"], metrics["phase_status"]):
                expected.append("both-pass" if gain == phase == "pass" else "gain-pass" if gain == "pass"
                                else "phase-pass" if phase == "pass" else "uncovered" if gain == phase == "fail"
                                else "indeterminate")
            require(coverage == expected, "Coverage disagrees with statuses")
            actual = Counter(coverage)
            require(actual["uncovered"] == metrics["counts"]["uncovered"], "Uncovered count differs")
            require(actual["indeterminate"] == metrics["counts"]["indeterminate_coverage"], "Pending count differs")
            margins = metrics["normalized_mixed_margin"]
            require(len(margins) == 1000 and all(math.isfinite(v) for v in margins), "Invalid margins")
            require(abs(min(margins) - metrics["score"]) < 1e-12, "Score differs")
            counts[name] = metrics["counts"]["uncovered"]
        for name in ("evolution", "random"):
            full = reference == "stable" and counts["baseline"] > 0 and counts[name] == 0
            full = full and row["strategies"][name]["counts"]["indeterminate_coverage"] == 0
            require(full == row["new_fully_covered_stable_case"][name], "Benefit flag differs")
            found |= full
        summaries.append({"damping": row["damping"], "reference": reference, "uncovered": counts})
    require(found == comparison["new_full_coverage_observed"], "Aggregate flag differs")
    decision = "retain-for-further-novelty-check" if found else "stop-as-core-innovation-candidate-in-tested-scope"
    require(comparison["decision"] == decision, "Wrong decision")
    return summaries


def main():
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    for name, expected in result["source_hashes"].items():
        path = (ROOT / name.replace("\\", "/")).resolve()
        require(path.is_relative_to(ROOT), "Source escapes project")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"Input drift: {name}")
    models = json.loads((RESULT.parent / "models.json").read_text(encoding="utf-8"))
    selection = json.loads((ROOT / "results/automatic-transform-search/run-2026-10-03-01/run.json").read_text(encoding="utf-8"))
    print(json.dumps({"status": "verified", "cases": audit(result, models, selection),
                      "scope": "source identity and saved result consistency, not independent inequality calculation"}, indent=2))


if __name__ == "__main__":
    main()
