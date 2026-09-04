"""Finite-grid screening for shaped multi-converter admittance responses.

This module implements the sampled algebraic part of the decentralized gain
and phase conditions.  It deliberately does not claim to evaluate the full
frequency-domain theorem or any of its dynamical prerequisites.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from backend.core.fig8_kernel import PhaseInterval, strict_sectorial_phase


_RESOLVED_BRANCH = "resolved-under-nearest-neighbor-assumption"


def _as_finite_complex(value: ArrayLike, name: str) -> NDArray[np.complex128]:
    array = np.asarray(value, dtype=np.complex128)
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values.")
    return array


def _validate_inputs(
    frequencies_hz: ArrayLike,
    shaped_converter_admittances: ArrayLike,
    shaped_network_admittance: ArrayLike,
    converter_ids: Sequence[str] | None,
    condition_limit: float,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.complex128],
    NDArray[np.complex128],
    list[str],
]:
    frequencies = np.asarray(frequencies_hz, dtype=float)
    if frequencies.ndim != 1 or frequencies.size == 0:
        raise ValueError("frequencies_hz must be a non-empty one-dimensional array.")
    if not np.all(np.isfinite(frequencies)):
        raise ValueError("frequencies_hz must contain only finite values.")
    if np.any(frequencies < 0) or np.any(np.diff(frequencies) <= 0):
        raise ValueError("frequencies_hz must be nonnegative and strictly increasing.")

    converters = _as_finite_complex(
        shaped_converter_admittances, "shaped_converter_admittances"
    )
    network = _as_finite_complex(
        shaped_network_admittance, "shaped_network_admittance"
    )
    if converters.ndim != 4 or converters.shape[2:] != (2, 2):
        raise ValueError(
            "shaped_converter_admittances must have shape "
            "(n_converters, n_frequencies, 2, 2)."
        )
    converter_count, frequency_count = converters.shape[:2]
    if converter_count == 0 or frequency_count != frequencies.size:
        raise ValueError(
            "The converter and frequency dimensions must be non-empty and consistent."
        )
    expected_network_size = 2 * converter_count
    if network.shape != (
        frequency_count,
        expected_network_size,
        expected_network_size,
    ):
        raise ValueError(
            "shaped_network_admittance must have shape "
            f"({frequency_count}, {expected_network_size}, {expected_network_size})."
        )

    if converter_ids is None:
        identifiers = [f"converter-{index + 1}" for index in range(converter_count)]
    else:
        identifiers = [str(value).strip() for value in converter_ids]
        if len(identifiers) != converter_count:
            raise ValueError("converter_ids must contain one identifier per converter.")
        if any(not value for value in identifiers) or len(set(identifiers)) != len(
            identifiers
        ):
            raise ValueError("converter_ids must be non-empty and unique.")

    if not np.isfinite(condition_limit) or condition_limit <= 0:
        raise ValueError("condition_limit must be finite and positive.")
    return frequencies, converters, network, identifiers


def _phase_intervals_and_inverse(
    converters: NDArray[np.complex128],
    network: NDArray[np.complex128],
    condition_limit: float,
) -> tuple[list[list[PhaseInterval]], list[float]]:
    response_intervals = [
        [strict_sectorial_phase(matrix) for matrix in response]
        for response in converters
    ]
    network_intervals: list[PhaseInterval] = []
    network_condition_numbers: list[float] = []
    for matrix in network:
        condition_number = float(np.linalg.cond(matrix, 2))
        network_condition_numbers.append(condition_number)
        if not np.isfinite(condition_number) or condition_number > condition_limit:
            network_intervals.append(
                PhaseInterval("numerical-pending", "network-inverse-ill-conditioned")
            )
            continue
        try:
            inverse = np.linalg.solve(matrix, np.eye(matrix.shape[0], dtype=complex))
        except np.linalg.LinAlgError:
            network_intervals.append(
                PhaseInterval("numerical-pending", "network-inverse-failure")
            )
            continue
        network_intervals.append(strict_sectorial_phase(inverse))
    response_intervals.append(network_intervals)
    return response_intervals, network_condition_numbers


def _unwrap_available_intervals(
    intervals: list[list[PhaseInterval]],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.object_], list[int | None]]:
    response_count = len(intervals)
    frequency_count = len(intervals[0])
    lower = np.full((response_count, frequency_count), np.nan)
    upper = np.full_like(lower, np.nan)
    status = np.full((response_count, frequency_count), "phase-unavailable", dtype=object)
    seed_indices: list[int | None] = []

    for response_index, response_intervals in enumerate(intervals):
        seed_index = next(
            (
                index
                for index, interval in enumerate(response_intervals)
                if interval.status == "resolved"
            ),
            None,
        )
        seed_indices.append(seed_index)
        if seed_index is None:
            continue

        previous_center = float(response_intervals[seed_index].center)
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
            shift_turns = round((previous_center - float(interval.center)) / (2 * np.pi))
            candidate_center = float(interval.center) + 2 * np.pi * shift_turns
            if abs(candidate_center - previous_center) >= 0.9 * np.pi - 1e-8:
                status[response_index, frequency_index] = "phase-branch-indeterminate"
                broken = True
                continue
            lower[response_index, frequency_index] = (
                float(interval.lower) + 2 * np.pi * shift_turns
            )
            upper[response_index, frequency_index] = (
                float(interval.upper) + 2 * np.pi * shift_turns
            )
            status[response_index, frequency_index] = _RESOLVED_BRANCH
            previous_center = candidate_center
    return lower, upper, status, seed_indices


def _signed_status(margin: float, tolerance: float) -> str:
    if margin > tolerance:
        return "pass"
    if margin < -tolerance:
        return "fail"
    return "indeterminate"


def _finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def evaluate_sampled_decentralized_condition(
    frequencies_hz: ArrayLike,
    shaped_converter_admittances: ArrayLike,
    shaped_network_admittance: ArrayLike,
    converter_ids: Sequence[str] | None = None,
    condition_limit: float = 1e12,
) -> dict[str, Any]:
    """Screen shaped device and network responses on a finite frequency grid.

    The converter input has one 2-by-2 global-dq port block per device.  The
    network input is the corresponding 2n-by-2n grounded nodal response.  Both
    inputs must already include the paper's admissible loop transformations.
    """

    frequencies, converters, network, identifiers = _validate_inputs(
        frequencies_hz,
        shaped_converter_admittances,
        shaped_network_admittance,
        converter_ids,
        condition_limit,
    )
    intervals, network_condition_numbers = _phase_intervals_and_inverse(
        converters, network, condition_limit
    )
    lower, upper, branch_status, seed_indices = _unwrap_available_intervals(intervals)

    gain_status: list[str] = []
    phase_status: list[str] = []
    coverage: list[str] = []
    active_constraint: list[str] = []
    gain_margin: list[float] = []
    gain_tolerance_scale: list[float] = []
    upper_phase_margin: list[float | None] = []
    lower_phase_margin: list[float | None] = []
    converter_phase_spread_margin: list[float | None] = []
    per_converter_upper_margin: list[list[float | None]] = []
    per_converter_lower_margin: list[list[float | None]] = []

    converter_count = converters.shape[0]
    network_interval_index = converter_count
    for frequency_index in range(frequencies.size):
        converter_gain = max(
            float(np.linalg.svd(converters[index, frequency_index], compute_uv=False)[0])
            for index in range(converter_count)
        )
        network_floor = float(
            np.linalg.svd(network[frequency_index], compute_uv=False)[-1]
        )
        margin = network_floor - converter_gain
        gain_scale = max(network_floor, converter_gain)
        gain = _signed_status(margin, 1e-10 * gain_scale)
        gain_status.append(gain)
        gain_margin.append(margin)
        gain_tolerance_scale.append(gain_scale)

        raw_intervals = [response[frequency_index] for response in intervals]
        upper_margins = [float("nan")] * converter_count
        lower_margins = [float("nan")] * converter_count
        spread_margin = float("nan")
        if any(interval.status == "not-applicable" for interval in raw_intervals):
            phase = "fail"
        elif any(interval.status != "resolved" for interval in raw_intervals):
            phase = "indeterminate"
        elif np.any(branch_status[:, frequency_index] != _RESOLVED_BRANCH):
            phase = "indeterminate"
        else:
            network_lower = lower[network_interval_index, frequency_index]
            network_upper = upper[network_interval_index, frequency_index]
            upper_margins = [
                float(np.pi - network_upper - upper[index, frequency_index])
                for index in range(converter_count)
            ]
            lower_margins = [
                float(lower[index, frequency_index] + np.pi + network_lower)
                for index in range(converter_count)
            ]
            spread_margin = float(
                np.pi
                - (
                    np.max(upper[:converter_count, frequency_index])
                    - np.min(lower[:converter_count, frequency_index])
                )
            )
            margins = [*upper_margins, *lower_margins, spread_margin]
            if all(value > 1e-10 for value in margins):
                phase = "pass"
            elif any(value < -1e-10 for value in margins):
                phase = "fail"
            else:
                phase = "indeterminate"
        phase_status.append(phase)
        per_converter_upper_margin.append([_finite_or_none(value) for value in upper_margins])
        per_converter_lower_margin.append([_finite_or_none(value) for value in lower_margins])
        upper_phase_margin.append(
            _finite_or_none(float(np.min(upper_margins)))
        )
        lower_phase_margin.append(
            _finite_or_none(float(np.min(lower_margins)))
        )
        converter_phase_spread_margin.append(_finite_or_none(spread_margin))

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

    counts = {
        "gain": {
            name: gain_status.count(name) for name in ("pass", "fail", "indeterminate")
        },
        "phase": {
            name: phase_status.count(name) for name in ("pass", "fail", "indeterminate")
        },
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

    converter_phase_seed = {
        identifier: (
            None
            if seed_indices[index] is None
            else {
                "index_zero_based": seed_indices[index],
                "frequency_hz": float(frequencies[seed_indices[index]]),
            }
        )
        for index, identifier in enumerate(identifiers)
    }
    return {
        "converter_ids": identifiers,
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
            "gain_tolerance_scale": gain_tolerance_scale,
            "upper_phase_margin": upper_phase_margin,
            "lower_phase_margin": lower_phase_margin,
            "converter_phase_spread_margin": converter_phase_spread_margin,
            "per_converter_upper_phase_margin": per_converter_upper_margin,
            "per_converter_lower_phase_margin": per_converter_lower_margin,
            "network_condition_number": network_condition_numbers,
            "gain_status": gain_status,
            "phase_status": phase_status,
            "coverage": coverage,
            "active_constraint": active_constraint,
        },
        "phase_seed": {
            "converters": converter_phase_seed,
            "network_inverse": (
                None
                if seed_indices[converter_count] is None
                else {
                    "index_zero_based": seed_indices[converter_count],
                    "frequency_hz": float(
                        frequencies[seed_indices[converter_count]]
                    ),
                }
            ),
            "provenance": "first-resolved-grid-point-principal-center",
        },
        "phase_method": "strict-sectorial-conservative-subset-with-seeded-unwrapping",
        "interpretation_boundary": (
            "本接口只筛查已经整形的端口导纳在有限频率网格上的代数条件；"
            "严格扇形性检验是论文准扇形条件的保守可执行子集。"
            "定理的动力学前提、频率端点和连续全频覆盖均未核验；"
            "未覆盖只能表述为未满足该充分判据，不能据此断言闭环失稳。"
        ),
    }
