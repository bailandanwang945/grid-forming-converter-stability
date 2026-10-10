"""Independent bounded verification; never imports the pilot implementation."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial as P

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.core.fig8_kernel import _build_shaped_responses  # noqa: E402


def matrix(s, v, r, x, wc, f0, phi=0.0):
    rotation = np.array([[np.cos(phi), -np.sin(phi)], [np.sin(phi), np.cos(phi)]])
    vd, vq = v * np.cos(phi), v * np.sin(phi)
    e = np.array([[vd, vq], [vq, -vd]])
    fj = np.array([[-vq, vd / v], [vd, vq / v]])
    w = np.array(
        [[r + s * x / (2 * np.pi * f0), -x], [x, r + s * x / (2 * np.pi * f0)]]
    ) / np.hypot(r, x)
    return (wc * fj + s * w @ np.linalg.inv(e)) / (s + wc), rotation


def determinant_coefficients(v, r, x, wc, f0):
    # Polynomial entries, not the proposed closed-form coefficients.
    scale = np.hypot(r, x) * v
    diagonal = P([0.0, r / scale, x / (2 * np.pi * f0) / scale])
    upper = P([wc, x / scale])
    lower = P([wc * v, x / scale])
    determinant = -diagonal * diagonal - upper * lower
    return (-determinant * scale**2).coef[::-1]


def main():
    source = ROOT / "results/transformation-admissibility-pilot/pilot.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    failures, checks, rotation_errors, production_errors = [], [], [], []
    source_hashes = {}
    for relative_path, recorded_hash in data["sourceHashes"].items():
        actual_hash = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        source_hashes[relative_path] = actual_hash
        if actual_hash != recorded_hash:
            failures.append({"reason": "source-hash-mismatch", "path": relative_path})
    for index, row in enumerate(data["rows"]):
        v, r, x, wc, f0 = [
            row[k] for k in ("V", "Rv", "Xv", "cutoffRadPerSecond", "f0Hz")
        ]
        coef = determinant_coefficients(v, r, x, wc, f0)
        coefficient_error = float(
            np.max(
                np.abs(coef - row["coefficientsDescending"])
                / np.maximum(np.abs(coef), 1e-300)
            )
        )
        # Rescale s by n/L before root finding; independent conditioning route.
        frequency_scale = np.hypot(r, x) / (x / (2 * np.pi * f0))
        scaled = coef * frequency_scale ** np.arange(4, -1, -1)
        roots = np.roots(scaled / scaled[0]) * frequency_scale
        maximum_real = float(np.max(roots.real))
        status = (
            "strict-lhp-zeros"
            if maximum_real < -1e-7
            else "rhp-zero"
            if maximum_real > 1e-7
            else "critical"
        )
        # Matrix determinant evaluated away from zeros and poles, in rotated frame.
        residuals = []
        for s in (complex(0.173, 2.91), complex(-0.43, 7.2), complex(1.3, -3.7)):
            base, _ = matrix(s, v, r, x, wc, f0)
            for phi in (0.47, -0.63):
                rotated, rotation = matrix(s, v, r, x, wc, f0, phi)
                rotation_errors.append(
                    float(
                        np.linalg.norm(rotated - rotation @ base)
                        / max(np.linalg.norm(base), 1e-300)
                    )
                )
                reference = -np.polyval(coef, s) / (
                    np.hypot(r, x) ** 2 * v**2 * (s + wc) ** 2
                )
                residuals.append(
                    float(
                        abs(np.linalg.det(rotated) - reference)
                        / max(abs(reference), 1e-300)
                    )
                )
        checks.append(
            {
                "row": index,
                "coefficientRelativeError": coefficient_error,
                "scaledRootStatus": status,
                "maxDeterminantRelativeError": max(residuals),
            }
        )
        if (
            coefficient_error > 1e-12
            or status != row["rootStatus"]
            or max(residuals) > 1e-10
        ):
            failures.append(
                {
                    "row": index,
                    "reason": "independent-coefficient-root-or-determinant-mismatch",
                }
            )
    frequencies = np.array([0.001, 0.2, 0.5, 1.0, 37.0, 1000.0])
    for v in (0.8, 1.0, 1.2):
        for phi in (0.0, 0.47, -0.63):
            vd, vq = v * np.cos(phi), v * np.sin(phi)
            manifest = {
                "derivedOperatingPoint": {"vd": vd, "vq": vq, "id": 0.0, "iq": 0.0},
                "baseAngularFrequency": 2 * np.pi * 50,
            }
            device = np.repeat(
                np.eye(2, dtype=complex)[None, :, :], len(frequencies), axis=0
            )
            network = np.zeros_like(device)
            result = _build_shaped_responses(frequencies, device, network, manifest)
            e = np.array([[vd, vq], [vq, -vd]])
            recovered = np.linalg.solve(e, result[0])
            for frequency, actual in zip(frequencies, recovered):
                expected, _ = matrix(
                    2j * np.pi * frequency, v, 0.01, 0.1, np.pi, 50, phi
                )
                production_errors.append(
                    float(
                        np.linalg.norm(actual - expected)
                        / max(np.linalg.norm(expected), 1e-300)
                    )
                )
    if max(production_errors) > 1e-12 or max(rotation_errors) > 1e-12:
        failures.append({"reason": "rotation-or-production-response-mismatch"})
    output = {
        "inputSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "verifierSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "verifiedSourceHashes": source_hashes,
        "rowCount": len(checks),
        "allChecksPassed": not failures,
        "maximumRotationRelativeError": max(rotation_errors),
        "maximumProductionRelativeError": max(production_errors),
        "productionComparedPointCount": len(production_errors),
        "rows": checks,
        "failures": failures,
        "reviewLimits": [
            "Checks zeros of specified F, not physical closed-loop poles.",
            "F itself is improper; properness of actual theorem ports must be checked separately.",
            "F inverse Hurwitz does not establish Jnet inverse Hurwitz or sectoriality.",
            "Global rotation invariance assumes isotropic W=aI+bJ and consistent E,FJ definitions.",
            "Author legacy normalized-magnitude FJ differs from absolute-magnitude corrected FJ when V!=1.",
            "No exhaustive novelty claim or continuous-frequency gain/phase certificate.",
        ],
    }
    destination = source.with_name("verification.json")
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    reread = json.loads(destination.read_text(encoding="utf-8"))
    assert reread["rowCount"] == 135
    print(
        json.dumps(
            {
                k: output[k]
                for k in (
                    "rowCount",
                    "allChecksPassed",
                    "maximumRotationRelativeError",
                    "maximumProductionRelativeError",
                    "productionComparedPointCount",
                )
            }
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
