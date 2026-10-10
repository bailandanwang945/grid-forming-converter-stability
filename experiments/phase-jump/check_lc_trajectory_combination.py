"""Nine predeclared combinations; no optimizer and no tolerance changes."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from verify_constrained_ocp import ROOT
from verify_lc_voltage_results import check_candidate, boundary_demands

PLAN = ROOT / "results/phase-jump-power-feasibility/lc-trajectory-combination-plan-2026-10-05.md"
OLD = ROOT / "results/phase-jump-power-feasibility/phase-one-refinement-2026-10-05/result.json"
NEW = ROOT / "results/phase-jump-power-feasibility/lc-voltage-envelope-2026-10-05/result.json"
OUT = ROOT / "results/phase-jump-power-feasibility/lc-trajectory-combination-2026-10-05.json"
LAMBDAS = [0., .0001, .001, .01, .05, .1, .25, .5, 1.]


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    files = [Path(__file__), PLAN, OLD, NEW] + [ROOT/f"experiments/phase-jump/{name}.py" for name in
             ["verify_lc_voltage_results", "verify_lc_voltage_envelope", "verify_phase_one_refinement", "verify_constrained_ocp"]]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    older, newer = [json.loads(p.read_text(encoding="utf-8")) for p in [OLD, NEW]]
    inherited = {}
    for r in [older, newer]:
        for collection in ["source_hashes", "inherited_source_hashes"]:
            inherited.update(r[collection])
    for name, expected in inherited.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Frozen input changed: {name}")
    a, b = np.asarray(newer["strategies"][0]["coefficients"]), np.asarray(older["strategies"][1]["coefficients"])
    if older["strategies"][1]["knots_s"] != newer["strategies"][0]["knots_s"]:
        raise ValueError("Unequal spline spaces")
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, inherited_source_hashes=inherited,
                  case=newer["case"], hardware=newer["hardware"],
                  configuration=dict(lambdas=LAMBDAS, tolerance=1e-7, seconds=30., inverter_current_limit_pu=1.3),
                  boundary_demands=boundary_demands(newer["case"]), candidates=[])

    def save():
        result["elapsed_seconds"] = time.monotonic()-started
        OUT.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        if json.loads(OUT.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Combination readback failed")

    save()
    try:
        for lam in LAMBDAS:
            if time.monotonic()-started > 30.:
                result["status"] = "incomplete-budget"
                break
            candidate = dict(lambda_value=lam, knots_s=newer["strategies"][0]["knots_s"], coefficients=((1-lam)*a+lam*b).tolist())
            result["candidates"].append(candidate)
            save()
            candidate["audit"] = check_candidate(candidate, result["case"], True)
            save()
            print(json.dumps(dict(lambda_value=lam, feasible=candidate["audit"]["strategy_constraints_pass"],
                power=candidate["audit"]["polynomial_summary"]["minimum_power_pu"],
                voltage=candidate["audit"]["actual_voltage_peak_pu"],
                i1=candidate["audit"]["hardware_summary"]["inverter_current_peak_pu"])), flush=True)
        else:
            result["status"] = "complete"
        passing = [c for c in result["candidates"] if c.get("audit", {}).get("strategy_constraints_pass")]
        result["selected_lambda"] = min(passing, key=lambda c: c["audit"]["actual_voltage_peak_pu"])["lambda_value"] if passing else None
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise AssertionError("Source drift during combination audit")
    except Exception as exc:
        result["status"], result["failure"] = "execution-failed", repr(exc)
        raise
    finally:
        save()
    print(json.dumps(dict(status=result["status"], selected_lambda=result.get("selected_lambda"), elapsed_seconds=result["elapsed_seconds"])))


if __name__ == "__main__":
    main()
