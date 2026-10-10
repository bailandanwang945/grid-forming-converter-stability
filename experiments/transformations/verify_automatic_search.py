"""Independent read-only audit of the first bounded transformation search."""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial as Poly

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import automatic_search as search  # noqa: E402

RUN = ROOT / "results/automatic-transform-search/run-2026-10-03-01/run.json"
OUT = ROOT / "results/automatic-transform-search/verification.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def root_label(roots):
    maximum = float(np.max(roots.real))
    return "strict-lhp-zeros" if maximum < -1e-7 else "rhp-zero" if maximum > 1e-7 else "critical"


def routh(coef):
    a4, a3, a2, a1, a0 = coef / coef[0]
    d2 = a3 * a2 - a4 * a1
    d3 = a3 * a2 * a1 - a4 * a1**2 - a3**2 * a0
    return bool(min(a3, a2, a1, a0, d2, d3) > 0)


def compare_polynomials(left, right):
    error = float(np.max(np.abs(left - right)) / max(np.max(np.abs(left)), 1e-300))
    require(error < 1e-11, f"Polynomial coefficient discrepancy: {error}")
    lr, rr = np.roots(left), np.roots(right)
    root_error = min(float(np.max(np.abs(lr - rr[list(p)]))) for p in itertools.permutations(range(4)))
    root_error /= max(float(np.max(np.abs(lr))), 1)
    require(root_error < 1e-9, f"Polynomial root discrepancy: {root_error}")
    require(routh(left) == bool(np.all(lr.real < 0)), "Routh/root sign disagreement")
    return lr, error, root_error


def audit():
    result = json.loads(RUN.read_text(encoding="utf-8"))
    require(result["status"] == "complete", "Search did not complete")
    hashes = {name: sha(ROOT / name) for name in result["source_hashes"]}
    mismatches = {name: {"saved": saved, "current": hashes[name]}
                  for name, saved in result["source_hashes"].items() if hashes[name] != saved}
    plan_name = "results\\automatic-transform-search\\plan.md"
    require(not (set(mismatches) - {plan_name}), "A frozen numerical dependency changed")
    if plan_name in mismatches:
        content = (ROOT / plan_name).read_bytes()
        begin = content.index("### 首轮后追加探索，不伪装预先指定".encode("utf-8"))
        end = content.index("### 运行前修订：网络模型范围".encode("utf-8"), begin)
        recovered = content[:begin] + content[end:]
        require(hashlib.sha256(recovered).hexdigest() == result["source_hashes"][plan_name],
                "Plan amendment is not exactly the documented post-run insertion")
        reconstructed_path = RUN.parent / "plan-at-run-reconstructed.md"
        require(reconstructed_path.read_bytes() == recovered, "Saved reconstructed plan bytes differ")
        mismatches[plan_name]["status"] = "documented-post-run-plan-amendment"
        mismatches[plan_name]["original_content_reconstructed_hash_matches"] = True
        mismatches[plan_name]["reconstructed_copy"] = str(reconstructed_path.relative_to(ROOT))
        mismatches[plan_name]["copy_provenance"] = "Post-run reconstruction by removal of known later insertion; not a contemporaneous snapshot."
    fixture = ROOT / "experiments/baseline/fixtures"
    manifest = json.loads((fixture / "author_fig8_fixture_manifest.json").read_text(encoding="utf-8"))
    point = manifest["derivedOperatingPoint"]
    require(point["vq"] == 0 and point["vd"] > 0, "Audit formula expects aligned voltage")
    v, id_, iq = (point[k] for k in ("vd", "id", "iq"))
    i2 = id_**2 + iq**2
    e = np.diag([v, -v])
    c = np.array([[id_, iq], [-iq, id_]])
    wb = float(manifest["baseAngularFrequency"])
    require(abs(wb - 2 * np.pi * 50) < 1e-10, "Unexpected base frequency")
    g, rn, xn, ln = .5, .5, 1., 1. / wb
    z0 = np.array([[rn, -xn], [xn, rn]])
    cases = {}
    with (fixture / "author_fig8_raw_frequency_response.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            frequency = float(row["frequency_Hz"])
            y = np.array([[complex(float(row[f"Ynet{i}{j}_real"]), float(row[f"Ynet{i}{j}_imag"]))
                           for j in (1, 2)] for i in (1, 2)])
            reconstructed = g * np.eye(2) + np.linalg.inv(z0 + 2j * np.pi * frequency * ln * np.eye(2))
            error = float(np.linalg.norm(y - reconstructed) / max(np.linalg.norm(y), 1))
            require(error < 1e-11, "Known RL/shunt representation differs from CSV")
            cases.setdefault(row["case_id"], []).append(error)
    for name, errors in cases.items():
        require(len(errors) == 1000, "Unexpected case point count")
        identified = result["identified_network"][name]
        require(np.max(np.abs(np.array(identified["z0"]) - z0)) < 1e-9, "Identified Z0 mismatch")
        require(abs(identified["L_pu_seconds"] - ln) < 1e-11, "Identified L mismatch")
        require(abs(identified["shunt_conductance_pu"] - g) < 1e-9, "Identified g mismatch")

    checks = []
    for record in result["records"]:
        candidate = record["candidate"]
        rv, xv, wc = candidate["resistance"], candidate["reactance"], 2 * np.pi * candidate["cutoff_hz"]
        lv, norm = xv / wb, np.hypot(rv, xv)
        s = Poly([0., 1.])
        a = s * Poly([rv, lv]) / (norm * v)
        b = Poly([wc]) + s * xv / (norm * v)
        d = Poly([wc * v]) + s * xv / (norm * v)
        f_direct = (-a * a - b * d).coef[::-1] * (-norm**2 * v**2)
        f_implemented = search.coefficients(v, rv, xv, wc, wb / (2 * np.pi))
        fr, fe, fre = compare_polynomials(f_direct, f_implemented)
        h, beta, h2 = 1 + g * rn, g * ln, (1 + g * rn)**2 + g**2 * xn**2
        n_closed = np.array([
            v**2 * beta**2,
            2 * v**2 * (beta * h + wc * beta**2),
            v**2 * (h2 + 4 * wc * beta * h + wc**2 * beta**2) - wc**2 * i2 * ln**2,
            v**2 * (2 * wc * h2 + 2 * wc**2 * beta * h) - 2 * wc**2 * i2 * rn * ln,
            wc**2 * (v**2 * h2 - i2 * (rn**2 + xn**2)),
        ])
        n_implemented, matrices, leading = search.network_n_coefficients(e, c, z0, ln, g, wc)
        nr, ne, nre = compare_polynomials(n_closed, -n_implemented)
        require(np.max(np.abs(leading - g * ln * e)) < 1e-14, "Wrong leading N matrix")
        require(np.linalg.cond(leading) < 1e10, "Leading N matrix is singular")
        for probe in (0., 1j, 10 + 100j):
            n_matrix = (probe + wc) * e @ (g * (z0 + probe * ln * np.eye(2)) + np.eye(2)) - wc * c @ (z0 + probe * ln * np.eye(2))
            assembled = sum(matrix * probe**k for k, matrix in enumerate(matrices))
            require(np.linalg.norm(n_matrix - assembled) / max(np.linalg.norm(n_matrix), 1) < 1e-12, "N matrix expansion mismatch")
            require(abs(np.polyval(n_closed, probe) + np.linalg.det(n_matrix)) / max(abs(np.polyval(n_closed, probe)), 1) < 1e-10, "N determinant identity mismatch")
        saved = record["metrics"]["checks"]
        require(saved["f_zeros"] == root_label(fr), "Saved F root class mismatch")
        require(saved["g_zeros"] == root_label(nr), "Saved G root class mismatch")
        expected_rejections = [name for name, label in (("f_zeros", root_label(fr)), ("g_zeros", root_label(nr))) if label != "strict-lhp-zeros"]
        require(saved["rejected_by"] == expected_rejections, "Saved rejection reasons differ")
        for name, roots in (("f", fr), ("g", nr)):
            require(abs(saved[f"{name}_max_root_real_per_s"] - float(max(roots.real))) < 1e-7, "Saved root maximum mismatch")
        # At infinity F~s*(Lv/n)*E^-1 and G~gE, so s*J^-1~n/(gLv)*I.
        high_s = 1e12
        z = z0 + high_s * ln * np.eye(2)
        gs = e @ (g * np.eye(2) + np.linalg.inv(z)) - wc / (high_s + wc) * c
        fj = np.array([[0., 1.], [v, 0.]])
        weight = np.array([[rv + high_s * lv, -xv], [xv, rv + high_s * lv]]) / norm
        fs = (wc * fj + high_s * weight @ np.linalg.inv(e)) / (high_s + wc)
        limiting = norm / (g * lv) * np.eye(2)
        asymptotic_error = float(np.linalg.norm(high_s * np.linalg.inv(gs @ fs) - limiting) / np.linalg.norm(limiting))
        require(asymptotic_error < 1e-6, "Strict properness asymptotic differs")
        checks.append({"id": record["id"], "strategy": record["strategy"], "f_class": root_label(fr), "g_class": root_label(nr),
                       "f_coefficient_error": fe, "n_coefficient_error": ne, "f_root_error": fre, "n_root_error": nre,
                       "inverse_high_frequency_error": asymptotic_error})

    require(len(checks) == 49, "Unexpected number of candidate records")
    dev, hold = set(result["development_indices"]), set(result["holdout_indices"])
    require(len(dev) == 80 and len(hold) == 920 and not dev & hold and dev | hold == set(range(1000)), "Invalid frequency partition")
    selections = {}
    for strategy, item in result["selected"].items():
        require(result["records"][item["selected_id"]]["candidate"] == item["candidate"], "Selected candidate mismatch")
        selections[strategy] = {name: {"score": metrics["score"], "uncovered": metrics["counts"]["uncovered"],
                                     "indeterminate": metrics["counts"]["indeterminate_coverage"]}
                               for name, metrics in item["cases"].items()}
        stable = item["cases"]["fig8_D_0p5"]
        require(stable["counts"]["uncovered"] == stable["counts"]["indeterminate_coverage"] == 0, "Stable fixture coverage changed")
        for metrics in item["cases"].values():
            margins = np.array(metrics["normalized_mixed_margin"])
            require(abs(float(min(margins)) - metrics["score"]) < 1e-14, "Stored minimum margin mismatch")
            require(abs(float(min(margins[sorted(hold)])) - metrics["holdout_minimum_margin"]) < 1e-14, "Holdout minimum mismatch")
            require(metrics["theorem_status"] == "not-evaluated-by-sampled-api", "Theorem status was upgraded")
            require(not metrics["unstable_reference_with_full_sampled_coverage"], "Unstable fixture incorrectly fully covered")
    require({name: sha(ROOT / name) for name in hashes} == hashes, "Sources changed during verification")
    return {"status": "verified-with-scope-limits", "source_hashes_match": not mismatches,
            "numerical_dependency_hashes_match": True, "source_amendments": mismatches, "source_hashes": hashes,
            "audit_history": ["First strict-all-hashes audit exited nonzero on post-run plan revision; revision now independently checked by recovering original bytes."],
            "run_sha256": sha(RUN), "verification_script_sha256": sha(Path(__file__)),
            "network": {"g": g, "R": rn, "X": xn, "L": ln, "checked_rows": sum(map(len, cases.values())),
                        "maximum_direct_csv_residual": max(map(max, cases.values()))},
            "candidate_checks": checks, "selected_results": selections,
            "limits": ["Metric is an analysis inequality margin, not a physical stability margin.",
                       "Stable author fixture already has full sampled coverage at baseline; no stable-domain expansion demonstrated.",
                       "Frequency holdout is not independent scenarios; one search seed does not establish strategy superiority.",
                       "Continuous-frequency theorem and converter transformed stability were not verified.",
                       "Network parameters are a verified CSV representation, not workbook parameter provenance.",
                       "This audit checks polynomial prerequisites and stored metric consistency, not an independent recomputation of all gain/phase values."]}


if __name__ == "__main__":
    try:
        evidence = audit()
    except Exception as exc:
        OUT.write_text(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, indent=2) + "\n", encoding="utf-8")
        raise
    OUT.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    require(json.loads(OUT.read_text(encoding="utf-8"))["status"] == "verified-with-scope-limits", "Output readback failed")
    print(json.dumps({"status": evidence["status"], "checked_rows": 2000, "checked_candidates": 49, "output": str(OUT)}))
