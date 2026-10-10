"""Reversible Hessian scaling of the same fixed spline optimization problems."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.linalg import solve_triangular

from run_constrained_ocp import ROOT, SplineProblem, solve_once

OUTPUT = ROOT / "results/phase-jump-power-feasibility/constrained-ocp-scaled-2026-10-05"
PLAN = ROOT / "results/phase-jump-power-feasibility/scaled-ocp-plan-2026-10-05.md"


class ScaledProblem:
    def __init__(self, base):
        self.base = base
        for name in ("case", "knots", "times"):
            setattr(self, name, getattr(base, name))
        m = base.train
        h = 2 * np.einsum("m,man,mak->nk", base.weights, m["vj"], m["vj"])
        h += 2e-4 * np.einsum("m,man,mak->nk", base.weights, m["dvj"], m["dvj"])
        self.scale = base.objective(base.x0)
        if not np.isfinite(self.scale) or self.scale <= 0:
            raise ValueError("Invalid fixed objective scale")
        factor = np.linalg.cholesky(h)
        self.transform = np.sqrt(self.scale) * solve_triangular(factor.T, np.eye(base.nvar), lower=False)
        error = np.max(np.abs(self.transform.T @ h @ self.transform / self.scale - np.eye(base.nvar)))
        if error > 1e-7:
            raise AssertionError("Hessian scaling identity failed")
        self.x0 = np.zeros(base.nvar)
        self.diagnostics = dict(condition_number=float(np.linalg.cond(h)), eigenvalues=np.linalg.eigvalsh(h).tolist(),
                                scaling_identity_residual=float(error), objective_scale=self.scale,
                                transform=self.transform.tolist(), transform_is_invertible=True)

    def physical(self, z):
        return self.base.x0 + self.transform @ z

    def coefficients(self, z):
        return self.base.coefficients(self.physical(z))

    def objective(self, z):
        return self.base.objective(self.physical(z)) / self.scale

    def gradient(self, z):
        return self.transform.T @ self.base.gradient(self.physical(z)) / self.scale

    def constraints(self, z, hard_power):
        return self.base.constraints(self.physical(z), hard_power)

    def constraint_jacobian(self, z, hard_power):
        return self.base.constraint_jacobian(self.physical(z), hard_power) @ self.transform

    def check(self, z, times):
        return self.base.check(self.physical(z), times)


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    files = [Path(__file__), PLAN, ROOT / "experiments/phase-jump/run_constrained_ocp.py",
             ROOT / "experiments/phase-jump/run_power_feasibility.py",
             ROOT / "results/phase-jump-power-feasibility/constrained-ocp-plan-2026-10-05.md",
             ROOT / "results/phase-jump-power-feasibility/constrained-ocp-2026-10-05/result.json",
             ROOT / "references/papers/Awal-et-al-2026-phase-jump-overload-arxiv-2607.07904v1.pdf"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    original = json.loads(files[-2].read_text(encoding="utf-8"))
    for name, expected in original["source_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Original inputs changed: {name}")
    p = ScaledProblem(SplineProblem())
    OUTPUT.mkdir()
    started = time.monotonic()
    result = dict(status="running", source_hashes=hashes, environment=original["environment"],
        case=original["case"], configuration=original["configuration"], diagnostics=p.diagnostics,
        initial_coefficients=p.coefficients(p.x0).tolist(), strategies=[],
        scope="same physical problem with reversible numerical variable scaling; exploratory, not author parameter replication")

    def save():
        path = OUTPUT / "result.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8"))["source_hashes"] != hashes:
            raise AssertionError("Result readback mismatch")

    save()
    try:
        for hard in [False, True]:
            row = solve_once(p, hard)
            row["scaled_objective"] = row.pop("objective")
            row["objective"] = row["scaled_objective"] * p.scale
            result["strategies"].append(row)
            save()
            print(json.dumps({"strategy": row["strategy"], "optimizer": row["optimizer"], "dense": row["dense_check"]}), flush=True)
        if hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise AssertionError("Sources changed during scaled trial")
        result["status"] = "complete" if all(r["optimizer"]["termination"] == "optimizer-returned" for r in result["strategies"]) else "incomplete-budget"
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
