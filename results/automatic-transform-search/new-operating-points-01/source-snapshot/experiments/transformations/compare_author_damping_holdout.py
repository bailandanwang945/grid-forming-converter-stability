"""Evaluate frozen transformations on actual regenerated author damping models."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from automatic_search import ROOT, Candidate, Evaluator, fit_rl_shunt, write_json

DATA = ROOT / "results/automatic-transform-search/new-operating-points-01/models.json"
SELECTION = ROOT / "results/automatic-transform-search/run-2026-10-03-01/run.json"
OUTPUT = DATA.parent / "comparison.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_response(fields):
    result = np.empty((1000, 2, 2), dtype=complex)
    for i in range(2):
        for j in range(2):
            prefix = f"m{i+1}{j+1}"
            result[:, i, j] = np.asarray(fields[prefix + "_real"]) + 1j * np.asarray(fields[prefix + "_imag"])
    if not np.all(np.isfinite(result)):
        raise ValueError("Nonfinite exported frequency response")
    return result


def decode_case(record):
    pole_pairs = np.asarray(record["closed_loop_poles_per_second"])
    return {"damping": record["damping"],
            "frequencies_hz": np.asarray(record["frequencies_hz"]),
            "converter": decode_response(record["converter"]),
            "network": decode_response(record["network"]),
            "poles_hz": (pole_pairs[:, 0] + 1j * pole_pairs[:, 1]) / (2 * np.pi)}


def baseline_check(exported, pinned):
    if len(exported["poles_hz"]) != len(pinned["poles_hz"]):
        raise AssertionError("Baseline pole count differs")
    residuals = {}
    for name in ("converter", "network"):
        relative = np.linalg.norm(exported[name] - pinned[name], axis=(1, 2)) / np.maximum(
            np.linalg.norm(pinned[name], axis=(1, 2)), 1e-30)
        residuals[name] = float(np.max(relative))
        if residuals[name] > 1e-8:
            raise AssertionError(f"Baseline {name} frequency response differs")
    relative_f = np.max(np.abs(exported["frequencies_hz"] - pinned["frequencies_hz"]) / pinned["frequencies_hz"])
    if relative_f > 1e-12:
        raise AssertionError("Frequency grids differ")
    p, q = exported["poles_hz"] * (2 * np.pi), pinned["poles_hz"] * (2 * np.pi)
    distances = np.abs(p[:, None] - q[None, :])
    pole_error = float(max(np.max(np.min(distances, axis=0)), np.max(np.min(distances, axis=1))))
    if pole_error > 1e-7:
        raise AssertionError("Baseline closed-loop pole sets differ")
    residuals.update(pole_maximum_nearest_difference_per_second=pole_error,
                     frequency_maximum_relative_difference=float(relative_f))
    return residuals


def run():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    started = time.monotonic()
    sources = [DATA, SELECTION, Path(__file__), ROOT / "experiments/transformations/export_author_damping_holdout.m",
               ROOT / "experiments/transformations/automatic_search.py", ROOT / "experiments/transformations/run_admissibility_pilot.py",
               ROOT / "backend/core/fig8_kernel.py", ROOT / "results/automatic-transform-search/new-operating-points-plan.md",
               ROOT / "external/cifelli-small-gain-phase/GridFormingVSI.m",
               ROOT / "external/cifelli-small-gain-phase/UserData_inf_bus_Fig_8.xlsm",
               *sorted((ROOT / "experiments/baseline/fixtures").glob("author_fig8*"))]
    before = {str(p.relative_to(ROOT)): digest(p) for p in sources}
    exported = json.loads(DATA.read_text(encoding="utf-8"))
    selected = json.loads(SELECTION.read_text(encoding="utf-8"))["selected"]
    if exported["status"] != "complete" or len(exported["cases"]) != 5:
        raise AssertionError("Model export did not complete")
    evaluator = Evaluator()
    if exported["fixture_operating_point"] != evaluator.manifest["derivedOperatingPoint"]:
        raise AssertionError("Operating point definition differs")
    if abs(exported["base_angular_frequency"] - evaluator.wbase) > 1e-10:
        raise AssertionError("Base frequency differs")
    if digest(ROOT / evaluator.manifest["sourceWorkbook"]).upper() != evaluator.manifest["sourceWorkbookSha256"]:
        raise AssertionError("Author workbook changed")
    records = {r["damping"]: r for r in exported["cases"]}
    if set(records) != {.05, .1, .2, .35, .5}:
        raise AssertionError("Unexpected physical scenario selection")
    checked = {}
    for damping, name in [(.05, "fig8_D_0p05"), (.5, "fig8_D_0p5")]:
        checked[name] = baseline_check(decode_case(records[damping]), evaluator.cases[name])
    output = {"status": "running", "source_hashes": before, "baseline_cross_checks": checked,
              "frozen_candidates": {k: v["candidate"] for k, v in selected.items()}, "cases": [],
              "scope": "new damping points, unchanged author physical model; sampled comparison only",
              "theorem_status": "not-evaluated-by-sampled-api"}
    try:
        for damping in [.1, .2, .35]:
            if time.monotonic() - started > 120:
                raise TimeoutError("Comparison budget exceeded")
            case = decode_case(records[damping])
            name = f"new_D_{damping}"
            evaluator.cases[name] = case
            evaluator.rl[name] = fit_rl_shunt(case["frequencies_hz"], case["network"], evaluator.wbase)
            dominant = float(np.max(case["poles_hz"].real) * (2 * np.pi))
            reference = "stable" if dominant < -1e-7 else "unstable" if dominant > 1e-7 else "numerical-pending"
            strategies = {}
            for strategy, choice in selected.items():
                metrics = evaluator.evaluate(Candidate(**choice["candidate"]), name, np.arange(1000))
                strategies[strategy] = metrics
                print(json.dumps({"D": damping, "strategy": strategy, "reference": reference,
                                  "status": metrics["status"], "counts": metrics.get("counts")}), flush=True)
                if reference == "unstable" and metrics["status"] == "sampled-only" and metrics["counts"]["uncovered"] == metrics["counts"]["indeterminate_coverage"] == 0:
                    raise AssertionError("Unstable reference has full sampled coverage: review required")
            added = {}
            base = strategies["baseline"]
            for strategy in ("evolution", "random"):
                candidate = strategies[strategy]
                added[strategy] = bool(reference == "stable" and base["status"] == candidate["status"] == "sampled-only"
                    and base["counts"]["uncovered"] > 0 and candidate["counts"]["uncovered"] == candidate["counts"]["indeterminate_coverage"] == 0)
            output["cases"].append({"damping": damping, "closed_loop_reference": reference,
                "dominant_real_per_second": dominant,
                "dominant_pole_zero_difference_per_second": records[damping]["dominant_pole_zero_difference_per_second"],
                "strategies": strategies, "new_fully_covered_stable_case": added})
            write_json(OUTPUT, output)
        if {str(p.relative_to(ROOT)): digest(p) for p in sources} != before:
            raise AssertionError("Frozen inputs changed during comparison")
        found = any(any(r["new_fully_covered_stable_case"].values()) for r in output["cases"])
        output.update(status="complete", elapsed_seconds=time.monotonic() - started,
                      new_full_coverage_observed=found,
                      decision="retain-for-further-novelty-check" if found else "stop-as-core-innovation-candidate-in-tested-scope")
        write_json(OUTPUT, output)
        reread = json.loads(OUTPUT.read_text(encoding="utf-8"))
        assert reread["status"] == "complete" and len(reread["cases"]) == 3
        print(json.dumps({"decision": output["decision"], "output": str(OUTPUT)}), flush=True)
    except Exception as exc:
        output.update(status="incomplete", error=f"{type(exc).__name__}: {exc}")
        write_json(OUTPUT, output)
        raise


if __name__ == "__main__":
    run()
