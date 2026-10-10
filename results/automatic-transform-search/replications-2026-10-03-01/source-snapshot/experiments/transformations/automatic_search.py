"""Bounded numerical candidate search; never a physical stability oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.core import fig8_kernel as kernel  # noqa: E402
from run_admissibility_pilot import coefficients, cutoff_limit, root_status  # noqa: E402

BOUNDS = np.array([[.002, .08], [.03, .3], [.03, 8.]])
BASELINE = (.01, .1, .5)
TRACKED = [
    Path(__file__).resolve(),
    ROOT / "experiments/transformations/run_admissibility_pilot.py",
    ROOT / "backend/core/fig8_kernel.py",
    *sorted((ROOT / "experiments/baseline/fixtures").glob("author_fig8*")),
    ROOT / "results/automatic-transform-search/plan.md",
]


@dataclass(frozen=True)
class Candidate:
    resistance: float
    reactance: float
    cutoff_hz: float

    def validate(self):
        values = np.array(list(asdict(self).values()))
        if not np.all(np.isfinite(values)) or np.any(values <= 0):
            raise ValueError("Candidate parameters must be finite and positive")


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in TRACKED}


def fit_rl(frequencies, network, base_rad_s):
    """Verify that fixture impedance is Z0+s*L*I, not arbitrary networks."""
    impedance = np.linalg.inv(network)
    z0 = np.mean(impedance.real, axis=0)
    w = 2 * np.pi * frequencies
    l_values = np.r_[impedance[:, 0, 0].imag / w,
                     impedance[:, 1, 1].imag / w]
    inductance = float(np.mean(l_values))
    expected = z0[None] + 1j * w[:, None, None] * inductance * np.eye(2)
    residual = float(np.max(np.linalg.norm(impedance - expected, axis=(1, 2)) /
                            np.maximum(np.linalg.norm(impedance, axis=(1, 2)), 1)))
    r = float((z0[0, 0] + z0[1, 1]) / 2)
    x = inductance * base_rad_s
    shape = np.array([[r, -x], [x, r]])
    if residual > 1e-10 or np.linalg.norm(z0 - shape) > 1e-10 or r <= 0 or inductance <= 0:
        raise ValueError("Fixture is not the supported strictly passive single RL network")
    return z0, inductance, residual


def fit_rl_shunt(frequencies, network, base_rad_s):
    """Identify g*I+Zrl^-1 and reject unless every input point agrees."""
    s = 2j * np.pi * frequencies
    y11, y12 = network[:, 0, 0], network[:, 0, 1]
    if np.min(np.abs(y12)) < 1e-15:
        raise ValueError("RL/shunt identification is degenerate")
    design = np.column_stack([1 / y12, np.ones(len(s)), s])
    target = y11 / y12
    fitted = np.linalg.lstsq(np.vstack([design.real, design.imag]),
                             np.r_[target.real, target.imag], rcond=None)[0]
    g, r_x, l_x = fitted
    h = (r_x + s * l_x)**2 + 1
    x = float(np.vdot(h, 1 / y12).real / np.vdot(h, h).real)
    r, ln = float(r_x * x), float(l_x * x)
    z0 = np.array([[r, -x], [x, r]])
    z = z0[None] + s[:, None, None] * ln * np.eye(2)
    reconstructed = g * np.eye(2) + np.linalg.inv(z)
    residual = float(np.max(np.linalg.norm(network - reconstructed, axis=(1, 2)) /
                            np.maximum(np.linalg.norm(network, axis=(1, 2)), 1)))
    if (residual > 1e-10 or r <= 0 or ln <= 0 or g < 0 or
            abs(x - ln * base_rad_s) > 1e-9):
        raise ValueError("Fixture does not match supported RL plus conductance network")
    return z0, ln, float(g), residual


def n_coefficients(e, c, z0, inductance, wc):
    a = e - wc * inductance * c
    b = wc * (e - c @ z0)
    coef = np.array([
        np.linalg.det(a),
        a[0, 0] * b[1, 1] + b[0, 0] * a[1, 1]
        - a[0, 1] * b[1, 0] - b[0, 1] * a[1, 0],
        np.linalg.det(b),
    ])
    return coef, a, b


def network_n_coefficients(e, c, z0, inductance, conductance, wc):
    a2 = conductance * inductance * e
    a1 = e @ (conductance * z0 + np.eye(2)) + wc * conductance * inductance * e - wc * inductance * c
    a0 = wc * (e @ (conductance * z0 + np.eye(2)) - c @ z0)
    entries = [[Polynomial([a0[i, j], a1[i, j], a2[i, j]]) for j in range(2)] for i in range(2)]
    det = entries[0][0] * entries[1][1] - entries[0][1] * entries[1][0]
    leading = a2 if conductance > 0 else a1
    return np.asarray(det.coef[::-1]), (a0, a1, a2), leading


class Evaluator:
    def __init__(self):
        self.manifest, self.cases = kernel._load_fixture(kernel.DEFAULT_FIXTURE_ROOT)
        point = self.manifest["derivedOperatingPoint"]
        vd, vq, id_, iq = (point[n] for n in ("vd", "vq", "id", "iq"))
        self.v = float(np.hypot(vd, vq))
        self.e = np.array([[vd, vq], [vq, -vd]])
        self.c = np.array([[id_, iq], [-iq, id_]])
        self.fj = np.array([[-vq, vd / self.v], [vd, vq / self.v]])
        self.wbase = self.manifest["baseAngularFrequency"]
        self.rl = {}
        for name, case in self.cases.items():
            self.rl[name] = fit_rl_shunt(case["frequencies_hz"], case["network"], self.wbase)

    def prerequisites(self, candidate, case_id):
        candidate.validate()
        wc = 2 * np.pi * candidate.cutoff_hz
        limit = cutoff_limit(self.v, candidate.resistance, candidate.reactance,
                             self.wbase / (2 * np.pi))
        f_roots = np.roots(coefficients(self.v, candidate.resistance, candidate.reactance,
                                        wc, self.wbase / (2 * np.pi)))
        z0, ln, conductance, residual = self.rl[case_id]
        coef, _, a = network_n_coefficients(self.e, self.c, z0, ln, conductance, wc)
        g_roots = np.roots(coef)
        checks = {
            "f_zeros": root_status(f_roots),
            "g_zeros": root_status(g_roots),
            "proper_network_inverse_leading_matrix": bool(np.linalg.cond(a) < 1e10),
            "cutoff_limit_hz": float(limit / (2 * np.pi)),
            "f_max_root_real_per_s": float(max(f_roots.real)),
            "g_max_root_real_per_s": float(max(g_roots.real)),
            "network_fit_residual": residual,
            "network_conductance_pu": conductance,
        }
        reasons = [name for name in ("f_zeros", "g_zeros")
                   if checks[name] != "strict-lhp-zeros"]
        if not checks["proper_network_inverse_leading_matrix"]:
            reasons.append("proper_network_inverse_leading_matrix")
        checks["rejected_by"] = reasons
        return checks

    def shape(self, candidate, case_id, indices):
        candidate.validate()
        case = self.cases[case_id]
        freq = case["frequencies_hz"][indices]
        s = 2j * np.pi * freq
        wc = 2 * np.pi * candidate.cutoff_hz
        lp = wc / (s + wc)
        r, x = candidate.resistance, candidate.reactance
        w = np.empty((len(freq), 2, 2), dtype=complex)
        w[:, 0, 0] = w[:, 1, 1] = s * x / self.wbase + r
        w[:, 0, 1], w[:, 1, 0] = -x, x
        w /= np.hypot(r, x)
        f = lp[:, None, None] * self.fj + (1 - lp)[:, None, None] * w @ np.linalg.inv(self.e)
        c = lp[:, None, None] * self.c
        yc, yn = case["converter"][indices], case["network"][indices]
        jc = (self.e @ yc + c) @ f
        jn = (self.e @ yn - c) @ f
        expected = self.e @ (yc + yn) @ f
        residual = np.max(np.linalg.norm(jc + jn - expected, axis=(1, 2)) /
                          np.maximum(np.linalg.norm(expected, axis=(1, 2)), 1))
        return freq, jc, jn, float(residual), float(np.max(np.linalg.cond(f)))

    def evaluate(self, candidate, case_id, indices):
        checks = self.prerequisites(candidate, case_id)
        if checks["rejected_by"]:
            return {"status": "rejected", "checks": checks, "score": -2.}
        freq, jc, jn, residual, condition = self.shape(candidate, case_id, indices)
        if residual > 1e-10 or condition > 1e12:
            checks["rejected_by"].append("sampled_algebra_or_condition")
            return {"status": "rejected", "checks": checks, "score": -2.}
        inv = np.linalg.inv(jn)
        intervals = [[kernel.strict_sectorial_phase(m) for m in array] for array in (jc, inv)]
        seeds = []
        for group in intervals:
            resolved = next(((p.center, i) for i, p in enumerate(group) if p.status == "resolved"), None)
            seeds.append(resolved if resolved else (0., len(group)))
        lower, upper, branch = kernel._unwrap_intervals(intervals, seeds)
        gain, phase, coverage, quality = [], [], [], []
        for i in range(len(freq)):
            cg = np.linalg.svd(jc[i], compute_uv=False)[0]
            nf = np.linalg.svd(jn[i], compute_uv=False)[-1]
            gm = nf - cg
            gs = kernel._signed_status(gm, 1e-10 * max(nf, cg))
            normalized_gain = gm / max(nf + cg, 1e-300)
            p0, p1 = intervals[0][i], intervals[1][i]
            normalized_phase = -1.
            if np.linalg.cond(jn[i]) > 1e12:
                ps = "indeterminate"
            elif p0.status == "not-applicable" or p1.status == "not-applicable":
                ps = "fail"
            elif (p0.status != "resolved" or p1.status != "resolved" or
                  np.any(branch[:, i] != "resolved-under-nearest-neighbor-assumption")):
                ps = "indeterminate"
            else:
                margins = [np.pi - upper[1, i] - upper[0, i],
                           lower[0, i] + np.pi + lower[1, i],
                           np.pi - (upper[0, i] - lower[0, i])]
                normalized_phase = float(min(margins) / np.pi)
                ps = ("pass" if min(margins) > 1e-10 else
                      "fail" if min(margins) < -1e-10 else "indeterminate")
            cov = ("both-pass" if gs == ps == "pass" else "gain-pass" if gs == "pass"
                   else "phase-pass" if ps == "pass" else "uncovered" if gs == ps == "fail"
                   else "indeterminate")
            gain.append(gs)
            phase.append(ps)
            coverage.append(cov)
            quality.append(float(max(normalized_gain, normalized_phase)))
        return {"status": "sampled-only", "checks": checks, "score": min(quality),
                "point_count": len(freq), "counts": {
                    "gain": {v: gain.count(v) for v in ("pass", "fail", "indeterminate")},
                    "phase": {v: phase.count(v) for v in ("pass", "fail", "indeterminate")},
                    "uncovered": coverage.count("uncovered"),
                    "indeterminate_coverage": coverage.count("indeterminate")},
                "maximum_algebra_residual": residual, "maximum_f_condition": condition,
                "coverage": coverage, "gain_status": gain, "phase_status": phase,
                "normalized_mixed_margin": quality,
                "theorem_status": "not-evaluated-by-sampled-api"}


def random_candidate(rng):
    values = np.exp(rng.uniform(np.log(BOUNDS[:, 0]), np.log(BOUNDS[:, 1])))
    return Candidate(*map(float, values))


def mutate(parent, rng):
    values = np.exp(np.log(list(asdict(parent).values())) + rng.normal(0, .45, 3))
    return Candidate(*map(float, np.clip(values, BOUNDS[:, 0], BOUNDS[:, 1])))


def write_json(path, result):
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(output, budget_seconds=240):
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    fingerprint = hashes()
    evaluator = Evaluator()
    case_id = "fig8_D_0p5"
    count = len(evaluator.cases[case_id]["frequencies_hz"])
    development = np.unique(np.linspace(0, count - 1, 80).astype(int))
    holdout = np.setdiff1d(np.arange(count), development)
    result = {"status": "running", "seed": 20261003, "source_hashes": fingerprint,
              "development_indices": development.tolist(), "holdout_indices": holdout.tolist(),
              "target_case": case_id, "candidate_budget_per_strategy": 24, "records": [],
              "identified_network": {name: {"z0": values[0].tolist(),
                  "L_pu_seconds": values[1], "shunt_conductance_pu": values[2],
                  "maximum_frequency_response_residual": values[3]}
                  for name, values in evaluator.rl.items()},
              "limitations": ["frequency holdout is not independent physical scenarios",
                              "score is an analysis inequality margin, not physical stability margin",
                              "no continuous-frequency or complete theorem verification",
                              "no LLM calls; bounded numerical evolution only"]}

    def evaluate(candidate, strategy, generation):
        if time.monotonic() - start > budget_seconds:
            raise TimeoutError("Bounded research run exceeded time budget")
        if hashes() != fingerprint:
            raise RuntimeError("Frozen evaluator or input changed during run")
        metrics = evaluator.evaluate(candidate, case_id, development)
        record = {"id": len(result["records"]), "strategy": strategy, "generation": generation,
                  "candidate": asdict(candidate), "metrics": metrics}
        result["records"].append(record)
        write_json(output / "run.json", result)
        print(json.dumps({"candidate": record["id"], "strategy": strategy,
                          "status": metrics["status"], "score": metrics["score"]}), flush=True)
        return record

    try:
        baseline = evaluate(Candidate(*BASELINE), "baseline", 0)
        evolution_rng = np.random.default_rng(20261003)
        population = [baseline]
        for _ in range(6):
            population.append(evaluate(random_candidate(evolution_rng), "evolution", 0))
        for generation in range(1, 4):
            leaders = sorted(population, key=lambda r: r["metrics"]["score"], reverse=True)[:3]
            for j in range(6):
                parent = Candidate(**leaders[j % len(leaders)]["candidate"])
                population.append(evaluate(mutate(parent, evolution_rng), "evolution", generation))
        random_rng = np.random.default_rng(20261004)
        random_records = [evaluate(random_candidate(random_rng), "random", 0) for _ in range(24)]
        selected = {"baseline": baseline,
                    "evolution": max(population, key=lambda r: r["metrics"]["score"]),
                    "random": max([baseline, *random_records], key=lambda r: r["metrics"]["score"])}
        checks = {}
        for strategy, record in selected.items():
            candidate = Candidate(**record["candidate"])
            checks[strategy] = {"selected_id": record["id"], "candidate": record["candidate"],
                                "cases": {}}
            for name in evaluator.cases:
                if time.monotonic() - start > budget_seconds:
                    raise TimeoutError("Bounded validation exceeded time budget")
                full = evaluator.evaluate(candidate, name, np.arange(count))
                if full["status"] != "sampled-only":
                    raise AssertionError("Selected candidate failed full evaluation")
                full["holdout_minimum_margin"] = float(
                    np.min(np.asarray(full["normalized_mixed_margin"])[holdout]))
                poles = evaluator.cases[name]["poles_hz"]
                full["closed_loop_reference"] = "unstable" if max(poles.real) > 0 else "stable"
                full["unstable_reference_with_full_sampled_coverage"] = bool(
                    max(poles.real) > 0 and full["counts"]["uncovered"] == 0
                    and full["counts"]["indeterminate_coverage"] == 0)
                checks[strategy]["cases"][name] = full
            if strategy == "baseline":
                for name in evaluator.cases:
                    production = kernel.evaluate_fig8_case(name)
                    measured = checks[strategy]["cases"][name]
                    for field in ("coverage", "gain_status", "phase_status"):
                        if measured[field] != production["frequency_scan"][field]:
                            raise AssertionError("Baseline classifications differ from production")
                    if measured["counts"] != production["counts"]:
                        raise AssertionError("Baseline counts differ from production")
            print(json.dumps({"full_grid_checked": strategy}), flush=True)
        if hashes() != fingerprint:
            raise RuntimeError("Frozen inputs changed before finalization")
        result.update(status="complete", selected=checks, elapsed_seconds=time.monotonic() - start,
                      baseline_production_classifications_match=True)
        write_json(output / "run.json", result)
        reread = json.loads((output / "run.json").read_text(encoding="utf-8"))
        assert reread["status"] == "complete" and len(reread["records"]) == 49
        print(json.dumps({"output": str(output), "status": "complete",
                          "elapsed_seconds": result["elapsed_seconds"]}), flush=True)
    except Exception as exc:
        result.update(status="incomplete", error=f"{type(exc).__name__}: {exc}",
                      elapsed_seconds=time.monotonic() - start)
        write_json(output / "run.json", result)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-seconds", type=float, default=240)
    args = parser.parse_args()
    if not 0 < args.budget_seconds <= 600:
        parser.error("Budget must be in (0,600] seconds")
    run(args.output, args.budget_seconds)
