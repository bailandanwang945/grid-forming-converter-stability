"""Portable reproduction kernel for the pinned Cifelli--Anta Fig. 8 fixture.

The implementation mirrors the tracked MATLAB sampled-screening pipeline:

1. load the released-workbook frequency-response fixture;
2. apply the corrected dynamic E/C/F loop-shaping transformation;
3. evaluate sampled small-gain and strict-sectorial phase conditions; and
4. keep finite-grid screening separate from theorem-level confirmation.

It intentionally does not interpolate between the two pinned damping cases.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import eigvalsh
from scipy.optimize import minimize_scalar


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_ROOT = PROJECT_ROOT / "experiments" / "baseline" / "fixtures"


@dataclass(frozen=True)
class PhaseInterval:
    status: str
    reason: str
    lower: float = float("nan")
    upper: float = float("nan")
    center: float = float("nan")
    width: float = float("nan")


def _matrix_from_row(row: dict[str, str], prefix: str) -> np.ndarray:
    return np.array(
        [
            [
                complex(float(row[f"{prefix}11_real"]), float(row[f"{prefix}11_imag"])),
                complex(float(row[f"{prefix}12_real"]), float(row[f"{prefix}12_imag"])),
            ],
            [
                complex(float(row[f"{prefix}21_real"]), float(row[f"{prefix}21_imag"])),
                complex(float(row[f"{prefix}22_real"]), float(row[f"{prefix}22_imag"])),
            ],
        ],
        dtype=np.complex128,
    )


def _load_fixture(fixture_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = json.loads(
        (fixture_root / "author_fig8_fixture_manifest.json").read_text(encoding="utf-8")
    )
    cases: dict[str, dict[str, Any]] = {}
    with (fixture_root / "author_fig8_raw_frequency_response.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            case = cases.setdefault(
                row["case_id"],
                {
                    "damping": float(row["damping_D"]),
                    "frequencies_hz": [],
                    "converter": [],
                    "network": [],
                    "poles_hz": [],
                },
            )
            case["frequencies_hz"].append(float(row["frequency_Hz"]))
            case["converter"].append(_matrix_from_row(row, "Yc"))
            case["network"].append(_matrix_from_row(row, "Ynet"))

    with (fixture_root / "author_fig8_spectrum.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        for row in csv.DictReader(stream):
            if row["value_type"] == "closed-loop-pole":
                cases[row["case_id"]]["poles_hz"].append(
                    complex(float(row["real_Hz"]), float(row["imag_Hz"]))
                )

    for case in cases.values():
        case["frequencies_hz"] = np.asarray(case["frequencies_hz"], dtype=float)
        case["converter"] = np.asarray(case["converter"], dtype=np.complex128)
        case["network"] = np.asarray(case["network"], dtype=np.complex128)
        case["poles_hz"] = np.asarray(case["poles_hz"], dtype=np.complex128)
    return manifest, cases


def _separation_margins_2x2(matrix: np.ndarray, theta: np.ndarray) -> np.ndarray:
    rotations = np.exp(-1j * theta)[:, None, None]
    rotated = rotations * matrix[None, :, :]
    hermitian = (rotated + np.swapaxes(rotated.conj(), 1, 2)) / 2
    diagonal_0 = hermitian[:, 0, 0].real
    diagonal_1 = hermitian[:, 1, 1].real
    off_diagonal = hermitian[:, 0, 1]
    radius = np.sqrt(
        (diagonal_0 - diagonal_1) ** 2 + 4 * np.abs(off_diagonal) ** 2
    )
    return (diagonal_0 + diagonal_1 - radius) / 2


def _separation_margin(matrix: np.ndarray, theta: float) -> float:
    rotated = np.exp(-1j * theta) * matrix
    hermitian = (rotated + rotated.conj().T) / 2
    return float(np.linalg.eigvalsh(hermitian)[0])


def classify_numerical_range(
    matrix: np.ndarray,
    *,
    num_angles: int = 1440,
    relative_tolerance: float = 1e-10,
) -> dict[str, Any]:
    """Classify strict sectoriality using rotated-Hermitian bounds."""

    scale = float(np.linalg.norm(matrix, 2))
    tolerance = relative_tolerance * scale
    if scale == 0:
        return {"classification": "degenerate", "theta": float("nan")}

    angle_step = 2 * np.pi / num_angles
    theta_grid = -np.pi + np.arange(num_angles) * angle_step
    if matrix.shape == (2, 2):
        margins = _separation_margins_2x2(matrix, theta_grid)
    else:
        margins = np.array([_separation_margin(matrix, value) for value in theta_grid])
    best_index = int(np.argmax(margins))
    grid_best = float(margins[best_index])
    best_margin = grid_best
    best_theta = float(theta_grid[best_index])

    refined = minimize_scalar(
        lambda value: -_separation_margin(matrix, value),
        bounds=(best_theta - angle_step, best_theta + angle_step),
        method="bounded",
        options={"xatol": 1e-12},
    )
    candidate_margin = float(-refined.fun)
    if candidate_margin > best_margin:
        best_margin = candidate_margin
        best_theta = float(refined.x)
    best_theta = (best_theta + np.pi) % (2 * np.pi) - np.pi

    grid_error_bound = 2 * np.sin(angle_step / 4) * scale
    lower_bound = best_margin
    upper_bound = max(best_margin, grid_best + grid_error_bound)
    if lower_bound > tolerance:
        classification = "strict-sectorial"
    elif upper_bound < -tolerance:
        classification = "non-sectorial"
    elif lower_bound >= -tolerance and upper_bound <= tolerance:
        classification = "boundary"
    else:
        classification = "indeterminate"
    return {
        "classification": classification,
        "theta": best_theta,
        "margin": best_margin,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "tolerance": tolerance,
        "scale": scale,
    }


def strict_sectorial_phase(matrix: np.ndarray) -> PhaseInterval:
    """Return canonical matrix phases only for certified strict sectoriality."""

    input_scale = float(np.max(np.r_[np.abs(matrix.real).ravel(), np.abs(matrix.imag).ravel()]))
    if input_scale == 0:
        return PhaseInterval("not-applicable", "degenerate")
    scaled = matrix / input_scale
    classification = classify_numerical_range(scaled)
    if classification["classification"] == "indeterminate":
        return PhaseInterval("numerical-pending", "classification-indeterminate")
    if classification["classification"] != "strict-sectorial":
        return PhaseInterval("not-applicable", classification["classification"])

    theta = float(classification["theta"])
    rotated = np.exp(-1j * theta) * scaled
    hermitian = (rotated + rotated.conj().T) / 2
    quadrature = (rotated - rotated.conj().T) / (2j)
    hermitian = (hermitian + hermitian.conj().T) / 2
    quadrature = (quadrature + quadrature.conj().T) / 2
    condition_number = float(np.linalg.cond(hermitian, 2))
    if not np.isfinite(condition_number) or condition_number > 1e12:
        return PhaseInterval("numerical-pending", "ill-conditioned-hermitian-part")
    try:
        tangent_values = eigvalsh(quadrature, hermitian)
    except np.linalg.LinAlgError:
        return PhaseInterval("numerical-pending", "generalized-eigenvalue-failure")
    relative_phases = np.sort(np.arctan(tangent_values.real))
    phases = theta + relative_phases
    center = float((phases[0] + phases[-1]) / 2)
    branch_shift = 2 * np.pi * np.floor((center + np.pi) / (2 * np.pi))
    phases = phases - branch_shift
    lower = float(phases[0])
    upper = float(phases[-1])
    return PhaseInterval(
        "resolved",
        "strict-sectorial",
        lower=lower,
        upper=upper,
        center=(lower + upper) / 2,
        width=upper - lower,
    )


def _build_shaped_responses(
    frequencies_hz: np.ndarray,
    converter: np.ndarray,
    network: np.ndarray,
    manifest: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    point = manifest["derivedOperatingPoint"]
    vd, vq, id_value, iq = (point[name] for name in ("vd", "vq", "id", "iq"))
    voltage = float(np.hypot(vd, vq))
    e_matrix = np.array([[vd, vq], [vq, -vd]], dtype=float)
    c_static = np.array([[id_value, iq], [-iq, id_value]], dtype=float)
    f_static = np.array(
        [[-vq, vd / voltage], [vd, vq / voltage]], dtype=float
    )

    cutoff = 2 * np.pi * 0.5
    low_pass = cutoff / (1j * 2 * np.pi * frequencies_hz + cutoff)
    high_pass = 1 - low_pass
    omega_base = float(manifest["baseAngularFrequency"])
    resistance, reactance = 0.01, 0.1
    inductance = reactance / omega_base
    normalization = float(np.hypot(resistance, reactance))

    shaped_converter = np.empty_like(converter)
    shaped_network = np.empty_like(network)
    transformation_condition = np.empty(frequencies_hz.size, dtype=float)
    interconnection_residual = np.empty(frequencies_hz.size, dtype=float)
    transformation_status = np.empty(frequencies_hz.size, dtype=object)
    e_inverse = np.linalg.inv(e_matrix)
    for index, frequency in enumerate(frequencies_hz):
        s_value = 1j * 2 * np.pi * frequency
        weighting = np.array(
            [
                [s_value * inductance + resistance, -reactance],
                [reactance, s_value * inductance + resistance],
            ],
            dtype=np.complex128,
        ) / normalization
        c_matrix = low_pass[index] * c_static
        f_matrix = (
            low_pass[index] * f_static
            + high_pass[index] * weighting @ e_inverse
        )
        shaped_converter[index] = (e_matrix @ converter[index] + c_matrix) @ f_matrix
        shaped_network[index] = (e_matrix @ network[index] - c_matrix) @ f_matrix
        transformation_condition[index] = np.linalg.cond(f_matrix, 2)
        expected_interconnection = e_matrix @ (
            converter[index] + network[index]
        ) @ f_matrix
        actual_interconnection = shaped_converter[index] + shaped_network[index]
        interconnection_residual[index] = np.linalg.norm(
            actual_interconnection - expected_interconnection, ord="fro"
        ) / max(np.linalg.norm(expected_interconnection, ord="fro"), 1.0)
        if (
            not np.isfinite(transformation_condition[index])
            or transformation_condition[index] > 1e12
            or interconnection_residual[index] > 1e-10
        ):
            transformation_status[index] = "numerical-pending"
        else:
            transformation_status[index] = "sampled-algebra-resolved"
    return (
        shaped_converter,
        shaped_network,
        transformation_condition,
        interconnection_residual,
        transformation_status,
    )


def _first_resolved_seed(responses: np.ndarray) -> tuple[float, int]:
    for index, response in enumerate(responses):
        phase = strict_sectorial_phase(response)
        if phase.status == "resolved":
            return phase.center, index
    raise RuntimeError("No strict-sectorial phase sample is available for branch seeding.")


def _unwrap_intervals(
    intervals: list[list[PhaseInterval]], seeds: list[tuple[float, int]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    response_count = len(intervals)
    frequency_count = len(intervals[0])
    lower = np.full((response_count, frequency_count), np.nan)
    upper = np.full_like(lower, np.nan)
    status = np.full((response_count, frequency_count), "", dtype=object)
    for response_index, response_intervals in enumerate(intervals):
        previous_center, seed_index = seeds[response_index]
        broken = False
        for frequency_index, interval in enumerate(response_intervals):
            if frequency_index < seed_index:
                status[response_index, frequency_index] = "phase-branch-indeterminate"
                continue
            if interval.status != "resolved":
                status[response_index, frequency_index] = "phase-unavailable"
                broken = True
                continue
            if broken:
                status[response_index, frequency_index] = "phase-branch-indeterminate"
                continue
            shift_turns = round((previous_center - interval.center) / (2 * np.pi))
            candidate = interval.center + 2 * np.pi * shift_turns
            if abs(candidate - previous_center) >= 0.9 * np.pi - 1e-8:
                status[response_index, frequency_index] = "phase-branch-indeterminate"
                broken = True
                continue
            lower[response_index, frequency_index] = interval.lower + 2 * np.pi * shift_turns
            upper[response_index, frequency_index] = interval.upper + 2 * np.pi * shift_turns
            status[response_index, frequency_index] = (
                "resolved-under-nearest-neighbor-assumption"
            )
            previous_center = candidate
    return lower, upper, status


def _signed_status(margin: float, tolerance: float) -> str:
    if margin > tolerance:
        return "pass"
    if margin < -tolerance:
        return "fail"
    return "indeterminate"


def _serializable_float(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


@lru_cache(maxsize=4)
def evaluate_fig8_case(
    case_id: str, fixture_root_text: str | None = None
) -> dict[str, Any]:
    """Evaluate one pinned damping case without requiring MATLAB."""

    fixture_root = Path(fixture_root_text) if fixture_root_text else DEFAULT_FIXTURE_ROOT
    manifest, cases = _load_fixture(fixture_root)
    if case_id not in cases:
        raise ValueError(f"Unknown pinned Fig. 8 case: {case_id}")
    case = cases[case_id]
    frequencies = case["frequencies_hz"]
    (
        converter,
        network,
        transform_condition,
        interconnection_residual,
        transformation_status,
    ) = _build_shaped_responses(frequencies, case["converter"], case["network"], manifest)
    network_inverse = np.linalg.inv(network)

    converter_intervals = [strict_sectorial_phase(value) for value in converter]
    network_intervals = [strict_sectorial_phase(value) for value in network_inverse]
    converter_seed = _first_resolved_seed(converter)
    network_seed = _first_resolved_seed(network_inverse)
    lower, upper, branch_status = _unwrap_intervals(
        [converter_intervals, network_intervals], [converter_seed, network_seed]
    )

    gain_status: list[str] = []
    phase_status: list[str] = []
    coverage: list[str] = []
    active_constraint: list[str] = []
    gain_margin: list[float] = []
    upper_phase_margin: list[float | None] = []
    lower_phase_margin: list[float | None] = []
    converter_phase_spread_margin: list[float | None] = []
    for index in range(frequencies.size):
        converter_gain = float(np.linalg.svd(converter[index], compute_uv=False)[0])
        network_gain_floor = float(np.linalg.svd(network[index], compute_uv=False)[-1])
        margin = network_gain_floor - converter_gain
        tolerance = 1e-10 * max(network_gain_floor, converter_gain)
        gain = _signed_status(margin, tolerance)
        gain_status.append(gain)
        gain_margin.append(margin)

        raw_converter = converter_intervals[index]
        raw_network = network_intervals[index]
        spread_margin = float("nan")
        if not np.isfinite(np.linalg.cond(network[index], 2)) or np.linalg.cond(network[index], 2) > 1e12:
            phase = "indeterminate"
            upper_margin = lower_margin = float("nan")
        elif raw_converter.status == "not-applicable" or raw_network.status == "not-applicable":
            phase = "fail"
            upper_margin = lower_margin = float("nan")
        elif raw_converter.status != "resolved" or raw_network.status != "resolved":
            phase = "indeterminate"
            upper_margin = lower_margin = float("nan")
        elif np.any(branch_status[:, index] != "resolved-under-nearest-neighbor-assumption"):
            phase = "indeterminate"
            upper_margin = lower_margin = float("nan")
        else:
            upper_margin = float(np.pi - upper[1, index] - upper[0, index])
            lower_margin = float(lower[0, index] + np.pi + lower[1, index])
            spread_margin = float(np.pi - (upper[0, index] - lower[0, index]))
            margins = (upper_margin, lower_margin, spread_margin)
            if all(value > 1e-10 for value in margins):
                phase = "pass"
            elif any(value < -1e-10 for value in margins):
                phase = "fail"
            else:
                phase = "indeterminate"
        phase_status.append(phase)
        upper_phase_margin.append(_serializable_float(upper_margin))
        lower_phase_margin.append(_serializable_float(lower_margin))
        converter_phase_spread_margin.append(_serializable_float(spread_margin))

        if gain == "pass" and phase == "pass":
            coverage.append("both-pass")
            active_constraint.append("both")
        elif gain == "pass":
            coverage.append("gain-pass")
            active_constraint.append("gain")
        elif phase == "pass":
            coverage.append("phase-pass")
            active_constraint.append("phase")
        elif gain == "fail" and phase == "fail":
            coverage.append("uncovered")
            active_constraint.append("gain-and-phase")
        else:
            coverage.append("indeterminate")
            active_constraint.append("numerical-boundary-or-prerequisite")

    poles = case["poles_hz"]
    dominant_real = float(np.max(poles.real))
    dominant_candidates = poles[np.isclose(poles.real, dominant_real, atol=1e-10)]
    dominant = dominant_candidates[int(np.argmax(dominant_candidates.imag))]
    counts = {
        "gain": {name: gain_status.count(name) for name in ("pass", "fail", "indeterminate")},
        "phase": {name: phase_status.count(name) for name in ("pass", "fail", "indeterminate")},
        "uncovered": coverage.count("uncovered"),
        "indeterminate_coverage": coverage.count("indeterminate"),
    }
    if counts["uncovered"]:
        sampled_status = "not-covered-on-grid-under-phase-branch-assumption"
    elif counts["indeterminate_coverage"]:
        sampled_status = "indeterminate"
    elif counts["gain"]["pass"] == frequencies.size:
        sampled_status = "gain-covered-on-grid"
    else:
        sampled_status = "covered-on-grid-under-phase-branch-assumption"

    return {
        "case_id": case_id,
        "damping": float(case["damping"]),
        "closed_loop_reference": "stable" if dominant_real <= 0 else "unstable",
        "dominant_pole_hz": {"real": float(dominant.real), "imag": abs(float(dominant.imag))},
        "counts": counts,
        "sampled_band_status": sampled_status,
        "theorem_status": "not-evaluated-by-sampled-api",
        "theorem_preconditions": {
            "status": "not-verified",
            "all_satisfied": False,
            "values": {
                "openLoopStable": False,
                "realRationalProper": False,
                "transformationWellDefined": False,
                "networkInverseStable": False,
                "noRhpCancellation": False,
                "endpointsCovered": False,
                "fullFrequencyCoverage": False,
            },
        },
        "frequency_scan": {
            "frequencies_hz": frequencies.tolist(),
            "gain_margin": gain_margin,
            "upper_phase_margin": upper_phase_margin,
            "lower_phase_margin": lower_phase_margin,
            "converter_phase_spread_margin": converter_phase_spread_margin,
            "gain_status": gain_status,
            "phase_status": phase_status,
            "coverage": coverage,
            "active_constraint": active_constraint,
            "transformation_condition_number": transform_condition.tolist(),
            "interconnection_residual": interconnection_residual.tolist(),
            "transformation_status": transformation_status.tolist(),
        },
        "phase_seed": {
            "converter_index_zero_based": converter_seed[1],
            "converter_frequency_hz": float(frequencies[converter_seed[1]]),
            "network_index_zero_based": network_seed[1],
            "network_frequency_hz": float(frequencies[network_seed[1]]),
            "provenance": "first-resolved-grid-point-principal-center",
        },
        "maximum_transformation_condition_number": float(np.max(transform_condition)),
        "maximum_interconnection_residual": float(np.max(interconnection_residual)),
        "provenance": {
            "fixture_id": manifest["fixtureId"],
            "author_tag": manifest["authorTag"],
            "author_commit": manifest["authorCommit"],
            "source_workbook_sha256": manifest["sourceWorkbookSha256"],
            "matlab_release_used_to_export_fixture": manifest["matlabRelease"],
            "python_method": "portable-seeded-strict-sectorial-screening-v1",
        },
        "interpretation_boundary": (
            "有限频率网格上的相位结论依赖显式种子和最近邻分支假设；"
            "七项论文定理前提均未核验；判据未覆盖不等于闭环必然失稳，"
            "有限网格结果也不等同于论文全频定理。"
        ),
    }


def available_fig8_cases() -> list[dict[str, Any]]:
    """Return the two cases that can be reproduced exactly by this kernel."""

    return [
        {"case_id": "fig8_D_0p05", "damping": 0.05, "label": "失稳低阻尼工况"},
        {"case_id": "fig8_D_0p5", "damping": 0.5, "label": "稳定高阻尼工况"},
    ]
