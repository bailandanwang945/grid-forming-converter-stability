"""Exploratory check of zeros of one analysis transformation, not plant poles."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial as Poly

ROOT = Path(__file__).resolve().parents[2]
ROOT_TOL = 1e-7


def validate(v, resistance, reactance, base_hz):
    values = np.asarray([v, resistance, reactance, base_hz], dtype=float)
    if not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError("V, Rv, Xv and f0 must all be finite and strictly positive.")


def cutoff_limit(v, resistance, reactance, base_hz=50.0):
    validate(v, resistance, reactance, base_hz)
    inductance = reactance / (2 * np.pi * base_hz)
    norm = np.hypot(resistance, reactance)
    return (
        2
        * resistance
        * reactance
        * norm
        * (v + 1)
        / (inductance * v * (reactance**2 * (v + 1) ** 2 + 4 * resistance**2 * v))
    )


def coefficients(v, resistance, reactance, cutoff_rad_s, base_hz=50.0):
    validate(v, resistance, reactance, base_hz)
    if not np.isfinite(cutoff_rad_s) or cutoff_rad_s <= 0:
        raise ValueError("cutoff must be finite and strictly positive.")
    inductance = reactance / (2 * np.pi * base_hz)
    norm = np.hypot(resistance, reactance)
    return np.array(
        [
            inductance**2,
            2 * resistance * inductance,
            norm**2,
            cutoff_rad_s * reactance * norm * v * (v + 1),
            cutoff_rad_s**2 * norm**2 * v**3,
        ]
    )


def direct_determinant(v, resistance, reactance, cutoff_rad_s, base_hz=50.0):
    """Build entries of the numerator of F independently, then expand det."""
    validate(v, resistance, reactance, base_hz)
    inductance = reactance / (2 * np.pi * base_hz)
    norm = np.hypot(resistance, reactance)
    s = Poly([0.0, 1.0])
    a = s * Poly([resistance, inductance]) / (norm * v)
    b = Poly([cutoff_rad_s]) + s * reactance / (norm * v)
    c = Poly([cutoff_rad_s * v]) + s * reactance / (norm * v)
    d = -a
    result = -(a * d - b * c) * norm**2 * v**2
    return np.asarray(result.coef[::-1], dtype=float)


def routh_status(coef):
    """Quartic Hurwitz test, independent of closed-form cutoff limit."""
    a4, a3, a2, a1, a0 = np.asarray(coef, dtype=float)
    if a4 <= 0 or not np.all(np.isfinite(coef)):
        raise ValueError(
            "A finite quartic with positive leading coefficient is required."
        )
    d2 = a3 * a2 - a4 * a1
    terms = [a3 * a2 * a1, a4 * a1**2, a3**2 * a0]
    d3 = terms[0] - terms[1] - terms[2]
    m2 = d2 / max(abs(a3 * a2) + abs(a4 * a1), 1e-300)
    m3 = d3 / max(sum(abs(t) for t in terms), 1e-300)
    tol = 1e-10
    if min(a3, a2, a1, a0) <= 0 or m2 < -tol or m3 < -tol:
        label = "rhp-zero"
    elif abs(m2) <= tol or abs(m3) <= tol:
        label = "critical"
    else:
        label = "strict-lhp-zeros"
    return label, float(m2), float(m3)


def root_status(roots):
    largest = float(np.max(np.asarray(roots).real))
    return (
        "strict-lhp-zeros"
        if largest < -ROOT_TOL
        else "rhp-zero"
        if largest > ROOT_TOL
        else "critical"
    )


def f_matrix(s, v, resistance, reactance, cutoff_rad_s, base_hz=50.0):
    validate(v, resistance, reactance, base_hz)
    inductance = reactance / (2 * np.pi * base_hz)
    norm = np.hypot(resistance, reactance)
    e_inverse = np.diag([1 / v, -1 / v])
    fj = np.array([[0.0, 1.0], [v, 0.0]])
    weighting = (
        np.array(
            [
                [s * inductance + resistance, -reactance],
                [reactance, s * inductance + resistance],
            ]
        )
        / norm
    )
    return (cutoff_rad_s * fj + s * weighting @ e_inverse) / (s + cutoff_rad_s)


def complex_pairs(values):
    return [[float(z.real), float(z.imag)] for z in values]


def diagnostic():
    v, resistance, reactance = 1.0, 0.01, 0.1
    frequencies = np.geomspace(1e-3, 1e4, 1000)
    output = []
    for cutoff_hz in (0.5, 5.0):
        wc = 2 * np.pi * cutoff_hz
        conditions, minimum = [], []
        for freq in frequencies:
            singular = np.linalg.svd(
                f_matrix(2j * np.pi * freq, v, resistance, reactance, wc),
                compute_uv=False,
            )
            conditions.append(float(singular[0] / singular[-1]))
            minimum.append(float(singular[-1]))
        roots = np.roots(coefficients(v, resistance, reactance, wc))
        record = {
            "cutoffHz": cutoff_hz,
            "fZeroStatus": root_status(roots),
            "fZerosPerSecond": complex_pairs(roots),
            "sampleCount": 1000,
            "sampleFrequencyBoundsHz": [1e-3, 1e4],
            "sampledMaximumConditionNumber": max(conditions),
            "sampledMinimumSingularValue": min(minimum),
            "rhpZeroProbes": [],
        }
        for z in roots[roots.real > ROOT_TOL]:

            def bracket(s):
                # Diagnostic convention P=V*Id, Q=-V*Iq, hence Id=.5,Iq=-.1.
                # Network Y maps voltage to network current; translation is -C.
                rn, xn, ln = 0.02, 0.3, 0.3 / (2 * np.pi * 50)
                zn = np.array([[rn + s * ln, -xn], [xn, rn + s * ln]])
                yn = np.linalg.inv(zn)
                e = np.diag([v, -v])
                c = np.array([[0.5, -0.1], [0.1, 0.5]])
                return e @ yn - wc / (s + wc) * c

            ff = f_matrix(z, v, resistance, reactance, wc)
            bb = bracket(z)
            jj = bb @ ff
            sj = np.linalg.svd(jj, compute_uv=False)
            inverse_norms = []
            for epsilon in (1e-3, 1e-4, 1e-5):
                s = z + epsilon
                jnear = bracket(s) @ f_matrix(s, v, resistance, reactance, wc)
                inverse_norms.append(float(np.linalg.norm(np.linalg.inv(jnear), 2)))
            record["rhpZeroProbes"].append(
                {
                    "zeroPerSecond": complex_pairs([z])[0],
                    "bracketConditionNumber": float(np.linalg.cond(bb)),
                    "jnetRelativeMinimumSingularValue": float(sj[-1] / sj[0]),
                    "realOffsetsPerSecond": [1e-3, 1e-4, 1e-5],
                    "jnetInverseNormAtOffsets": inverse_norms,
                    "successiveInverseNormRatios": [
                        inverse_norms[1] / inverse_norms[0],
                        inverse_norms[2] / inverse_norms[1],
                    ],
                }
            )
        output.append(record)
    return output


def run():
    rows = []
    for v, resistance, reactance, ratio in itertools.product(
        (0.8, 1.0, 1.2), (0.001, 0.01, 0.1), (0.01, 0.1, 0.3), (0.2, 0.8, 1.0, 1.2, 2.0)
    ):
        limit = cutoff_limit(v, resistance, reactance)
        wc = limit * ratio
        coef = coefficients(v, resistance, reactance, wc)
        direct = direct_determinant(v, resistance, reactance, wc)
        relative_error = float(
            np.max(np.abs(coef - direct) / np.maximum(np.abs(coef), 1e-300))
        )
        roots = np.roots(direct)
        routh, m2, m3 = routh_status(coef)
        root_label = root_status(roots)
        predicted = (
            "strict-lhp-zeros"
            if ratio < 1
            else "critical"
            if ratio == 1
            else "rhp-zero"
        )
        polynomial_residuals = [
            float(
                abs(np.polyval(direct, z))
                / max(np.polyval(np.abs(direct), abs(z)), 1e-300)
            )
            for z in roots
        ]
        rows.append(
            {
                "V": v,
                "Rv": resistance,
                "Xv": reactance,
                "f0Hz": 50.0,
                "cutoffRatioToLimit": ratio,
                "cutoffRadPerSecond": wc,
                "cutoffHz": wc / (2 * np.pi),
                "limitHz": limit / (2 * np.pi),
                "coefficientsDescending": coef.tolist(),
                "directDeterminantCoefficientsDescending": direct.tolist(),
                "coefficientMaximumRelativeError": relative_error,
                "fZerosPerSecond": complex_pairs(roots),
                "maximumZeroRealPartPerSecond": float(max(roots.real)),
                "maximumScaledPolynomialResidual": max(polynomial_residuals),
                "analyticStatus": predicted,
                "routhStatus": routh,
                "rootStatus": root_label,
                "routhNormalizedDelta2": m2,
                "routhNormalizedDelta3": m3,
                "agreement": predicted == routh == root_label,
            }
        )
    source_paths = (
        "backend/core/fig8_kernel.py",
        "external/cifelli-small-gain-phase/dec_conditions_inf_bus.m",
    )
    result = {
        "scope": "Zeros of the analysis transformation F, NOT converter closed-loop poles.",
        "limitations": [
            "F inverse stability is only one necessary admissibility check.",
            "No physical closed-loop stability, sectoriality, internal-stability or continuum frequency certificate is established.",
            "Jnet diagnostic operating point is constructed, not the author's workbook point.",
            "Imaginary-axis invertibility is checked on a finite grid only.",
            "Rv=0 and Xv=0 are excluded degenerate families.",
        ],
        "correctedMatrices": {
            "E": "V diag(1,-1)",
            "FJ": "[[0,1],[V,0]]",
            "WNormalization": "sqrt(Rv^2+Xv^2)",
        },
        "rootRealPartTolerancePerSecond": ROOT_TOL,
        "sourceHashes": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths
        },
        "rowCount": len(rows),
        "statusCounts": {
            s: sum(r["rootStatus"] == s for r in rows)
            for s in ("strict-lhp-zeros", "critical", "rhp-zero")
        },
        "allThreeRoutesAgree": all(r["agreement"] for r in rows),
        "rows": rows,
        "diagnosticConvention": "V=1,P=.5,Q=.1; P=V Id,Q=-V Iq; Ynet=Znet^-1; Jnet=(E Ynet-h C)F; line R=.02,X=.3.",
        "diagnostics": diagnostic(),
    }
    assert result["rowCount"] == 135 and result["allThreeRoutesAgree"]
    assert max(r["coefficientMaximumRelativeError"] for r in rows) < 1e-12
    output = ROOT / "results/transformation-admissibility-pilot/pilot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    reread = json.loads(output.read_text(encoding="utf-8"))
    assert reread["rowCount"] == 135 and reread["allThreeRoutesAgree"]
    print(
        json.dumps(
            {
                "output": str(output),
                "rowCount": result["rowCount"],
                "statusCounts": result["statusCounts"],
                "allThreeRoutesAgree": True,
            }
        )
    )
    return result


if __name__ == "__main__":
    run()
