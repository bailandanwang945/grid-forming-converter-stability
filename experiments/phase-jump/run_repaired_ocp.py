"""Remove analytically constant satisfied rows, keeping all physical checks."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from run_constrained_ocp import ROOT, SplineProblem, solve_once
from run_scaled_ocp import ScaledProblem

OUTPUT = ROOT / "results/phase-jump-power-feasibility/constrained-ocp-constant-repair-2026-10-05"
PLAN = ROOT / "results/phase-jump-power-feasibility/constant-row-repair-plan-2026-10-05.md"


class RepairedProblem(ScaledProblem):
    def __init__(self, base):
        super().__init__(base)
        m = base.train
        izero = np.max(np.abs(m["ij"]), axis=(1, 2)) == 0
        vzero = np.max(np.abs(m["vj"]), axis=(1, 2)) == 0
        self.keep = {False: ~np.concatenate((izero, vzero)),
                     True: ~np.concatenate((izero, vzero, izero & vzero))}
        self.removed = {}
        for hard in [False, True]:
            constant = base.constraints(base.x0, hard)[~self.keep[hard]]
            if np.any(constant < -1e-10):
                raise ValueError("An actually violated fixed constraint cannot be removed")
            # The full physical constraint set remains in base.check.
            self.removed[str(hard)] = dict(row_indices=np.where(~self.keep[hard])[0].tolist(),
                                          original_residuals=constant.tolist())

    def constraints(self, z, hard_power):
        return super().constraints(z, hard_power)[self.keep[hard_power]]

    def constraint_jacobian(self, z, hard_power):
        return super().constraint_jacobian(z, hard_power)[self.keep[hard_power]]


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    sources = [Path(__file__), PLAN, ROOT / "experiments/phase-jump/run_constrained_ocp.py",
               ROOT / "experiments/phase-jump/run_scaled_ocp.py", ROOT / "experiments/phase-jump/run_power_feasibility.py",
               ROOT / "results/phase-jump-power-feasibility/constrained-ocp-plan-2026-10-05.md",
               ROOT / "results/phase-jump-power-feasibility/constrained-ocp-2026-10-05/result.json",
               ROOT / "results/phase-jump-power-feasibility/constrained-ocp-scaled-2026-10-05/result.json",
               ROOT / "references/papers/Awal-et-al-2026-phase-jump-overload-arxiv-2607.07904v1.pdf"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    old = json.loads(sources[-3].read_text(encoding="utf-8"))
    for name, expected in old["source_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Frozen original changed: {name}")
    p = RepairedProblem(SplineProblem())
    OUTPUT.mkdir()
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, environment=old["environment"],
        case=old["case"], configuration=old["configuration"], diagnostics=p.diagnostics,
        removed_constant_rows=p.removed, initial_coefficients=p.coefficients(p.x0).tolist(), strategies=[],
        scope="constant satisfied constraint elimination and reversible scaling; full physical checks unchanged")

    def save():
        path = OUTPUT / "result.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Result readback failed")

    save()
    try:
        for hard in [False, True]:
            row = solve_once(p, hard)
            row["scaled_objective"] = row.pop("objective")
            row["objective"] = row["scaled_objective"] * p.scale
            result["strategies"].append(row)
            save()
            print(json.dumps({"strategy": row["strategy"], "optimizer": row["optimizer"], "dense": row["dense_check"]}), flush=True)
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:
            raise AssertionError("Input drift during repaired trial")
        result["status"] = "complete" if all(row["optimizer"]["termination"] == "optimizer-returned" for row in result["strategies"]) else "incomplete-budget"
        baseline, modified = result["strategies"]
        result["paired_evidence_observed"] = bool(baseline["dense_strategy_constraints_pass"] and not baseline["dense_check"]["power_pass"] and modified["dense_all_three_constraints_pass"])
    except Exception as exc:
        result["status"] = "execution-failed"
        result["failure"] = repr(exc)
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        save()
    print(json.dumps({"status": result["status"], "paired_evidence_observed": result["paired_evidence_observed"]}))


if __name__ == "__main__":
    main()
