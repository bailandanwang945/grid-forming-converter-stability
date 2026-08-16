"""Bounded modal ablation study for the average-value dq anchor case.

The experiment is deliberately fixed to the ``D=60`` and external-line
``X=0.1 pu`` hierarchy-disagreement anchor.  It rebuilds every operating point
and linearisation, and it tracks modes by left/right eigenvector MAC together
with normalized eigenvalue distance.  Pole array positions are never used as
mode identities.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import exp, isfinite, pi, sqrt

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import eig
from scipy.optimize import linear_sum_assignment

from backend.core.average_dq_model import (
    STATE_LABELS,
    AverageDQModel,
    AverageDQModelError,
    build_average_dq_model,
    compare_with_quasisteady_reduction,
)
from backend.domain.average_dq_models import AverageDQGFMParameters
from backend.domain.network_models import NetworkTopology


ANCHOR_DAMPING_PU = 60.0
ANCHOR_LINE_REACTANCE_PU = 0.1
DEFAULT_MINIMUM_CONFIDENCE = 0.55
DEFAULT_MINIMUM_COMBINED_MAC = 0.35
DEFAULT_MINIMUM_INDIVIDUAL_MAC = 0.80
DEFAULT_MAXIMUM_NORMALIZED_DISTANCE = 0.30
DEFAULT_MAXIMUM_CONDITION_NUMBER = 1.0e8
DEFAULT_MAXIMUM_EIGENPAIR_RESIDUAL = 1.0e-10
DEFAULT_MINIMUM_RELATIVE_MARGIN = 0.20
MAXIMUM_REFINEMENT_DEPTH = 4
FACTOR_ORDER = (
    "voltage_pi",
    "current_pi",
    "modulator_time",
    "converter_side_reactance",
    "filter_capacitor",
    "grid_side_reactance",
    "qv_droop",
)

STATE_GROUPS = (
    ("outer", slice(0, 4)),
    ("lcl", slice(4, 10)),
    ("voltage_pi", slice(10, 12)),
    ("current_pi", slice(12, 14)),
    ("modulator", slice(14, 16)),
)


class AverageDQAblationError(ValueError):
    """Raised when the fixed ablation contract is not satisfied."""


@dataclass(frozen=True)
class ModalSignature:
    """Biorthogonal signature of one eigenmode in the frozen state basis."""

    eigenvalue_per_s: complex
    right_vector: NDArray[np.complex128]
    left_vector: NDArray[np.complex128]
    right_residual: float
    left_residual: float
    condition_number: float


@dataclass(frozen=True)
class ModeMatch:
    """Tracked mode and the evidence used to accept or defer the match."""

    reference_eigenvalue_per_s: complex
    eigenvalue_per_s: complex
    candidate_index: int
    right_mac: float
    left_mac: float
    combined_mac: float
    normalized_distance: float
    confidence: float
    second_best_confidence: float
    relative_confidence_margin: float
    condition_number: float
    right_residual: float
    left_residual: float
    path_steps: int
    path_label: str
    minimum_individual_mac_threshold: float
    maximum_normalized_distance_threshold: float
    maximum_condition_number_threshold: float
    maximum_eigenpair_residual_threshold: float
    minimum_relative_margin_threshold: float
    status: str
    reason: str


@dataclass(frozen=True)
class ResidualEvidence:
    algebraic_inf: float
    closed_rhs_inf: float
    device_rhs_inf: float
    active_power_balance_abs_pu: float


@dataclass(frozen=True)
class AblationPoint:
    scenario_id: str
    factors: tuple[tuple[str, float], ...]
    damping_coefficient_pu: float
    line_reactance_pu: float
    stability: str
    poles_per_s: tuple[complex, ...]
    rightmost_pole_per_s: complex
    extra_mode: ModeMatch
    synchronous_mode: ModeMatch
    extra_group_participation: tuple[tuple[str, float], ...]
    extra_mode_condition_number: float
    extra_right_eigenpair_residual: float
    extra_left_eigenpair_residual: float
    synchronous_group_participation: tuple[tuple[str, float], ...]
    synchronous_mode_condition_number: float
    synchronous_right_eigenpair_residual: float
    synchronous_left_eigenpair_residual: float
    reduced_poles_per_s: tuple[complex, ...]
    reduced_dominant_pole_per_s: complex
    synchronizing_stiffness_pu_per_rad: float
    synchronous_frequency_relative_error: float | None
    synchronous_decay_relative_error: float | None
    residuals: ResidualEvidence


@dataclass(frozen=True)
class AverageDQAblationStudy:
    topology_id: str
    parameter_set_id: str
    baseline_extra_mode_per_s: complex
    baseline_synchronous_mode_per_s: complex
    state_scaling: tuple[tuple[str, float], ...]
    state_scaling_scope: str
    points: tuple[AblationPoint, ...]

    @property
    def point_count(self) -> int:
        return len(self.points)


@dataclass(frozen=True)
class AnchorModeTrackingContext:
    """Frozen baseline and modal identities shared by bounded studies."""

    topology: NetworkTopology
    parameters: AverageDQGFMParameters
    baseline_model: AverageDQModel
    baseline_signatures: tuple[ModalSignature, ...]
    extra_reference_index: int
    synchronous_reference_index: int
    matching_kwargs: dict[str, float]


def _validate_matrix(state_matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    matrix = np.asarray(state_matrix, dtype=np.float64)
    if (
        matrix.ndim != 2
        or matrix.shape[0] != matrix.shape[1]
        or matrix.shape[0] == 0
        or not np.all(np.isfinite(matrix))
    ):
        raise AverageDQAblationError("状态矩阵必须是非空有限实方阵。")
    return matrix


def modal_signature(
    state_matrix: NDArray[np.float64], eigenvalue_per_s: complex
) -> ModalSignature:
    """Return the closest eigenpair signature without relying on array order."""

    matrix = _validate_matrix(state_matrix)
    target = complex(eigenvalue_per_s)
    if not isfinite(target.real) or not isfinite(target.imag):
        raise AverageDQAblationError("目标特征值必须有限。")
    eigenvalues, left_vectors, right_vectors = eig(matrix, left=True, right=True)
    index = int(np.argmin(np.abs(eigenvalues - target)))
    right = np.asarray(right_vectors[:, index], dtype=np.complex128)
    left = np.asarray(left_vectors[:, index], dtype=np.complex128)
    matrix_norm = max(float(np.linalg.norm(matrix, ord=2)), 1.0)
    right_residual = float(
        np.linalg.norm(matrix @ right - eigenvalues[index] * right)
        / (matrix_norm * np.linalg.norm(right))
    )
    left_residual = float(
        np.linalg.norm(
            matrix.conj().T @ left - np.conj(eigenvalues[index]) * left
        )
        / (matrix_norm * np.linalg.norm(left))
    )
    denominator = abs(np.vdot(left, right))
    condition_number = (
        float("inf")
        if denominator <= np.finfo(float).tiny
        else float(np.linalg.norm(left) * np.linalg.norm(right) / denominator)
    )
    return ModalSignature(
        eigenvalue_per_s=complex(eigenvalues[index]),
        right_vector=right,
        left_vector=left,
        right_residual=right_residual,
        left_residual=left_residual,
        condition_number=condition_number,
    )


def _mac(first: NDArray[np.complex128], second: NDArray[np.complex128]) -> float:
    denominator = float(np.vdot(first, first).real * np.vdot(second, second).real)
    if denominator <= 0.0 or not isfinite(denominator):
        return 0.0
    value = abs(np.vdot(first, second)) ** 2 / denominator
    return float(np.clip(value, 0.0, 1.0))


def _validate_matching_thresholds(
    *,
    minimum_confidence: float,
    minimum_combined_mac: float,
    minimum_individual_mac: float,
    maximum_normalized_distance: float,
    maximum_condition_number: float,
    maximum_eigenpair_residual: float,
    minimum_relative_margin: float,
) -> None:
    for value, label in (
        (minimum_confidence, "最小匹配置信度"),
        (minimum_combined_mac, "最小组合 MAC"),
        (minimum_individual_mac, "最小单侧 MAC"),
        (minimum_relative_margin, "最小相对候选间隔"),
    ):
        if not isfinite(value) or value < 0.0 or value > 1.0:
            raise AverageDQAblationError(f"{label}必须位于 [0,1]。")
    for value, label in (
        (maximum_normalized_distance, "最大归一化特征值距离"),
        (maximum_condition_number, "最大特征值条件数"),
        (maximum_eigenpair_residual, "最大特征对残差"),
    ):
        if not isfinite(value) or value <= 0.0:
            raise AverageDQAblationError(f"{label}必须为有限正数。")


def match_mode(
    reference: ModalSignature,
    state_matrix: NDArray[np.float64],
    *,
    minimum_confidence: float = DEFAULT_MINIMUM_CONFIDENCE,
    minimum_combined_mac: float = DEFAULT_MINIMUM_COMBINED_MAC,
    minimum_individual_mac: float = DEFAULT_MINIMUM_INDIVIDUAL_MAC,
    maximum_normalized_distance: float = DEFAULT_MAXIMUM_NORMALIZED_DISTANCE,
    maximum_condition_number: float = DEFAULT_MAXIMUM_CONDITION_NUMBER,
    maximum_eigenpair_residual: float = DEFAULT_MAXIMUM_EIGENPAIR_RESIDUAL,
    minimum_relative_margin: float = DEFAULT_MINIMUM_RELATIVE_MARGIN,
) -> ModeMatch:
    """Match a reference mode using both eigenvectors and eigenvalue distance."""

    candidates = _all_signatures(_validate_matrix(state_matrix))
    return _assign_signatures(
        (reference,),
        candidates,
        minimum_confidence=minimum_confidence,
        minimum_combined_mac=minimum_combined_mac,
        minimum_individual_mac=minimum_individual_mac,
        maximum_normalized_distance=maximum_normalized_distance,
        maximum_condition_number=maximum_condition_number,
        maximum_eigenpair_residual=maximum_eigenpair_residual,
        minimum_relative_margin=minimum_relative_margin,
    )[0]


def _modal_diagnostics(
    state_matrix: NDArray[np.float64], match: ModeMatch
) -> tuple[tuple[tuple[str, float], ...], float, float, float]:
    signature = modal_signature(state_matrix, match.eigenvalue_per_s)
    raw = np.abs(signature.right_vector * np.conj(signature.left_vector))
    total = float(np.sum(raw))
    if total <= 0.0 or not isfinite(total):
        raise AverageDQAblationError("模态参与因子无法归一化。")
    normalized = raw / total
    grouped = tuple(
        (name, float(np.sum(normalized[indices])))
        for name, indices in STATE_GROUPS
    )
    return (
        grouped,
        signature.condition_number,
        signature.right_residual,
        signature.left_residual,
    )


def _all_signatures(state_matrix: NDArray[np.float64]) -> tuple[ModalSignature, ...]:
    matrix = _validate_matrix(state_matrix)
    eigenvalues, left_vectors, right_vectors = eig(matrix, left=True, right=True)
    matrix_norm = max(float(np.linalg.norm(matrix, ord=2)), 1.0)
    signatures: list[ModalSignature] = []
    for index, eigenvalue in enumerate(eigenvalues):
        right = np.asarray(right_vectors[:, index], dtype=np.complex128)
        left = np.asarray(left_vectors[:, index], dtype=np.complex128)
        denominator = abs(np.vdot(left, right))
        condition_number = (
            float("inf")
            if denominator <= np.finfo(float).tiny
            else float(np.linalg.norm(left) * np.linalg.norm(right) / denominator)
        )
        signatures.append(
            ModalSignature(
                eigenvalue_per_s=complex(eigenvalue),
                right_vector=right,
                left_vector=left,
                right_residual=float(
                    np.linalg.norm(matrix @ right - eigenvalue * right)
                    / (matrix_norm * np.linalg.norm(right))
                ),
                left_residual=float(
                    np.linalg.norm(
                        matrix.conj().T @ left - np.conj(eigenvalue) * left
                    )
                    / (matrix_norm * np.linalg.norm(left))
                ),
                condition_number=condition_number,
            )
        )
    return tuple(signatures)


def _assign_signatures(
    references: tuple[ModalSignature, ...],
    candidates: tuple[ModalSignature, ...],
    *,
    minimum_confidence: float,
    minimum_combined_mac: float,
    minimum_individual_mac: float,
    maximum_normalized_distance: float,
    maximum_condition_number: float,
    maximum_eigenpair_residual: float,
    minimum_relative_margin: float,
) -> tuple[ModeMatch, ...]:
    """Assign candidate signatures one-to-one and evaluate independent gates."""

    _validate_matching_thresholds(
        minimum_confidence=minimum_confidence,
        minimum_combined_mac=minimum_combined_mac,
        minimum_individual_mac=minimum_individual_mac,
        maximum_normalized_distance=maximum_normalized_distance,
        maximum_condition_number=maximum_condition_number,
        maximum_eigenpair_residual=maximum_eigenpair_residual,
        minimum_relative_margin=minimum_relative_margin,
    )
    if not references or not candidates or len(references) > len(candidates):
        raise AverageDQAblationError("参考模态数量必须为正且不大于候选模态数量。")
    costs = np.empty((len(references), len(candidates)), dtype=np.float64)
    evidence: dict[tuple[int, int], tuple[float, float, float, float, float]] = {}
    for row, reference in enumerate(references):
        scale = max(abs(reference.eigenvalue_per_s), 1.0)
        for column, candidate in enumerate(candidates):
            right_mac = _mac(reference.right_vector, candidate.right_vector)
            left_mac = _mac(reference.left_vector, candidate.left_vector)
            combined_mac = sqrt(right_mac * left_mac)
            distance = float(
                abs(candidate.eigenvalue_per_s - reference.eigenvalue_per_s) / scale
            )
            confidence = 0.7 * combined_mac + 0.3 * exp(-distance)
            costs[row, column] = 1.0 - confidence
            evidence[(row, column)] = (
                right_mac,
                left_mac,
                combined_mac,
                distance,
                confidence,
            )
    rows, columns = linear_sum_assignment(costs)
    assigned: list[ModeMatch | None] = [None] * len(references)
    candidate_values = np.array(
        [item.eigenvalue_per_s for item in candidates], dtype=np.complex128
    )
    for row, column in zip(rows, columns, strict=True):
        right_mac, left_mac, combined_mac, distance, confidence = evidence[(row, column)]
        reasons: list[str] = []
        if right_mac < minimum_individual_mac:
            reasons.append("right-mac-below-threshold")
        if left_mac < minimum_individual_mac:
            reasons.append("left-mac-below-threshold")
        if combined_mac < minimum_combined_mac:
            reasons.append("combined-mac-below-threshold")
        if confidence < minimum_confidence:
            reasons.append("confidence-below-threshold")
        if distance > maximum_normalized_distance:
            reasons.append("eigenvalue-distance-above-threshold")
        condition_number = max(
            references[row].condition_number,
            candidates[column].condition_number,
        )
        if condition_number > maximum_condition_number:
            reasons.append("eigenvalue-condition-number-above-threshold")
        right_residual = max(
            references[row].right_residual,
            candidates[column].right_residual,
        )
        left_residual = max(
            references[row].left_residual,
            candidates[column].left_residual,
        )
        if max(right_residual, left_residual) > maximum_eigenpair_residual:
            reasons.append("eigenpair-residual-above-threshold")
        alternatives = [
            evidence[(row, item)][4]
            for item in range(len(candidates))
            if item != column
        ]
        second_best_confidence = max(alternatives, default=0.0)
        relative_margin = float(
            (confidence - second_best_confidence)
            / max(abs(confidence), np.finfo(float).eps)
        )
        if relative_margin < minimum_relative_margin:
            reasons.append("ambiguous-candidate-score")
        gaps = np.abs(candidate_values - candidate_values[column])
        gaps[column] = np.inf
        if float(np.min(gaps) / max(abs(candidate_values[column]), 1.0)) < 1.0e-7:
            reasons.append("near-degenerate-candidate")
        if abs(references[row].eigenvalue_per_s.imag) > 1.0e-7 and abs(candidate_values[column].imag) < 1.0e-7:
            reasons.append("real-axis-transition")
        if (
            abs(references[row].eigenvalue_per_s.imag) > 1.0e-7
            and references[row].eigenvalue_per_s.imag * candidate_values[column].imag
            < 0.0
        ):
            reasons.append("conjugate-branch-flip")
        assigned[row] = ModeMatch(
            reference_eigenvalue_per_s=references[row].eigenvalue_per_s,
            eigenvalue_per_s=complex(candidate_values[column]),
            candidate_index=int(column),
            right_mac=right_mac,
            left_mac=left_mac,
            combined_mac=combined_mac,
            normalized_distance=distance,
            confidence=confidence,
            second_best_confidence=second_best_confidence,
            relative_confidence_margin=relative_margin,
            condition_number=condition_number,
            right_residual=right_residual,
            left_residual=left_residual,
            path_steps=1,
            path_label="direct",
            minimum_individual_mac_threshold=minimum_individual_mac,
            maximum_normalized_distance_threshold=maximum_normalized_distance,
            maximum_condition_number_threshold=maximum_condition_number,
            maximum_eigenpair_residual_threshold=maximum_eigenpair_residual,
            minimum_relative_margin_threshold=minimum_relative_margin,
            status="pending" if reasons else "matched",
            reason=";".join(reasons) if reasons else "accepted",
        )
    if any(item is None for item in assigned):  # pragma: no cover
        raise RuntimeError("全谱指派未覆盖全部参考模态。")
    return tuple(item for item in assigned if item is not None)


def _assigned_mode_matches(
    references: tuple[ModalSignature, ...],
    state_matrix: NDArray[np.float64],
    *,
    minimum_confidence: float,
    minimum_combined_mac: float,
    minimum_individual_mac: float = DEFAULT_MINIMUM_INDIVIDUAL_MAC,
    maximum_normalized_distance: float = DEFAULT_MAXIMUM_NORMALIZED_DISTANCE,
    maximum_condition_number: float = DEFAULT_MAXIMUM_CONDITION_NUMBER,
    maximum_eigenpair_residual: float = DEFAULT_MAXIMUM_EIGENPAIR_RESIDUAL,
    minimum_relative_margin: float = DEFAULT_MINIMUM_RELATIVE_MARGIN,
) -> tuple[ModeMatch, ...]:
    """Assign the complete spectrum one-to-one before selecting named modes."""

    candidates = _all_signatures(state_matrix)
    if len(references) != len(candidates):
        raise AverageDQAblationError("参考谱与候选谱阶数不一致。")
    return _assign_signatures(
        references,
        candidates,
        minimum_confidence=minimum_confidence,
        minimum_combined_mac=minimum_combined_mac,
        minimum_individual_mac=minimum_individual_mac,
        maximum_normalized_distance=maximum_normalized_distance,
        maximum_condition_number=maximum_condition_number,
        maximum_eigenpair_residual=maximum_eigenpair_residual,
        minimum_relative_margin=minimum_relative_margin,
    )


def _dominant(poles: NDArray[np.complex128]) -> complex:
    maximum_real = float(np.max(poles.real))
    tolerance = 1.0e-10 * max(abs(maximum_real), 1.0)
    candidates = poles[np.abs(poles.real - maximum_real) <= tolerance]
    return complex(max(candidates, key=lambda value: value.imag))


def _relative_error(actual: float, reference: float) -> float | None:
    scale = abs(reference)
    if scale <= 1.0e-12:
        return None
    return float(abs(actual - reference) / scale)


def _scenario_definitions() -> tuple[tuple[str, tuple[tuple[str, float], ...]], ...]:
    definitions: list[tuple[str, tuple[tuple[str, float], ...]]] = [
        ("baseline", ()),
    ]
    for factor in (
        "voltage_pi",
        "current_pi",
        "modulator_time",
        "converter_side_reactance",
        "filter_capacitor",
        "grid_side_reactance",
    ):
        definitions.extend(
            (
                (f"{factor}__0p5", ((factor, 0.5),)),
                (f"{factor}__2", ((factor, 2.0),)),
            )
        )
    definitions.extend(
        (
            ("qv_droop__0", (("qv_droop", 0.0),)),
            ("qv_droop__2", (("qv_droop", 2.0),)),
        )
    )
    for voltage_scale, current_scale in (
        (0.5, 0.5),
        (0.5, 2.0),
        (2.0, 0.5),
        (2.0, 2.0),
    ):
        voltage_id = str(voltage_scale).replace(".", "p")
        current_id = str(current_scale).replace(".", "p")
        definitions.append(
            (
                f"voltage_pi__{voltage_id}__current_pi__{current_id}",
                (("voltage_pi", voltage_scale), ("current_pi", current_scale)),
            )
        )
    return tuple(definitions)


def _apply_factors(
    parameters: AverageDQGFMParameters,
    factors: tuple[tuple[str, float], ...],
) -> None:
    for factor, scale in factors:
        if factor == "voltage_pi":
            parameters.voltage_proportional_gain_pu *= scale
            parameters.voltage_integral_gain_per_s *= scale
        elif factor == "current_pi":
            parameters.current_proportional_gain_pu *= scale
            parameters.current_integral_gain_per_s *= scale
        elif factor == "modulator_time":
            parameters.modulation_time_constant_s *= scale
        elif factor == "converter_side_reactance":
            parameters.converter_side_reactance_pu *= scale
        elif factor == "filter_capacitor":
            parameters.filter_capacitor_susceptance_pu *= scale
        elif factor == "grid_side_reactance":
            parameters.grid_side_reactance_pu *= scale
        elif factor == "qv_droop":
            parameters.reactive_power_voltage_droop_pu *= scale
        else:  # pragma: no cover - definitions are module-owned and frozen.
            raise AverageDQAblationError(f"未知消融因素：{factor}。")


def _factor_tuple(values: dict[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple(
        (name, float(values[name]))
        for name in FACTOR_ORDER
        if name in values and abs(float(values[name]) - 1.0) > 1.0e-14
    )


def _build_factored_model(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    values: dict[str, float],
):
    varied_topology = topology.model_copy(deep=True)
    varied_parameters = parameters.model_copy(deep=True)
    _apply_factors(varied_parameters, _factor_tuple(values))
    return build_average_dq_model(varied_topology, varied_parameters)


def _matching_kwargs(
    *,
    minimum_confidence: float,
    minimum_combined_mac: float,
    minimum_individual_mac: float,
    maximum_normalized_distance: float,
    maximum_condition_number: float,
    maximum_eigenpair_residual: float,
    minimum_relative_margin: float,
) -> dict[str, float]:
    return {
        "minimum_confidence": minimum_confidence,
        "minimum_combined_mac": minimum_combined_mac,
        "minimum_individual_mac": minimum_individual_mac,
        "maximum_normalized_distance": maximum_normalized_distance,
        "maximum_condition_number": maximum_condition_number,
        "maximum_eigenpair_residual": maximum_eigenpair_residual,
        "minimum_relative_margin": minimum_relative_margin,
    }


def _named_matches_are_accepted(
    matches: tuple[ModeMatch, ...],
    extra_index: int,
    synchronous_index: int,
) -> bool:
    return (
        matches[extra_index].status == "matched"
        and matches[synchronous_index].status == "matched"
        and matches[extra_index].candidate_index
        != matches[synchronous_index].candidate_index
    )


def _midpoint_factors(
    start: dict[str, float], target: dict[str, float]
) -> dict[str, float]:
    keys = tuple(name for name in FACTOR_ORDER if name in start or name in target)
    return {
        name: 0.5 * (start.get(name, 1.0) + target.get(name, 1.0))
        for name in keys
    }


def _advance_with_refinement(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    current_values: dict[str, float],
    current_signatures: tuple[ModalSignature, ...],
    target_values: dict[str, float],
    *,
    extra_index: int,
    synchronous_index: int,
    depth: int,
    matching_kwargs: dict[str, float],
) -> tuple[
    tuple[ModalSignature, ...],
    tuple[ModeMatch, ...],
    tuple[ModeMatch, ...],
]:
    """Advance one continuation segment, inserting midpoints when gates fail."""

    try:
        target_model = _build_factored_model(topology, parameters, target_values)
    except AverageDQModelError as error:
        raise AverageDQAblationError(
            f"连续追踪无法重建工作点或线性化：{error}"
        ) from error
    candidates = _all_signatures(target_model.linearization.closed_state_matrix)
    matches = _assign_signatures(
        current_signatures,
        candidates,
        **matching_kwargs,
    )
    if (
        _named_matches_are_accepted(matches, extra_index, synchronous_index)
        or depth >= MAXIMUM_REFINEMENT_DEPTH
    ):
        reordered = tuple(candidates[item.candidate_index] for item in matches)
        return (
            reordered,
            (matches[extra_index],),
            (matches[synchronous_index],),
        )

    midpoint = _midpoint_factors(current_values, target_values)
    midpoint_signatures, extra_first, sync_first = _advance_with_refinement(
        topology,
        parameters,
        current_values,
        current_signatures,
        midpoint,
        extra_index=extra_index,
        synchronous_index=synchronous_index,
        depth=depth + 1,
        matching_kwargs=matching_kwargs,
    )
    final_signatures, extra_second, sync_second = _advance_with_refinement(
        topology,
        parameters,
        midpoint,
        midpoint_signatures,
        target_values,
        extra_index=extra_index,
        synchronous_index=synchronous_index,
        depth=depth + 1,
        matching_kwargs=matching_kwargs,
    )
    return (
        final_signatures,
        extra_first + extra_second,
        sync_first + sync_second,
    )


def _aggregate_match_history(
    reference: ModalSignature,
    history: tuple[ModeMatch, ...],
    path_label: str,
) -> ModeMatch:
    if not history:  # pragma: no cover - every public path has an endpoint.
        raise RuntimeError("模态连续追踪没有产生任何步进证据。")
    endpoint = history[-1]
    reasons: list[str] = []
    for item in history:
        if item.status == "pending":
            for reason in item.reason.split(";"):
                if reason and reason not in reasons:
                    reasons.append(reason)
    return ModeMatch(
        reference_eigenvalue_per_s=reference.eigenvalue_per_s,
        eigenvalue_per_s=endpoint.eigenvalue_per_s,
        candidate_index=endpoint.candidate_index,
        right_mac=min(item.right_mac for item in history),
        left_mac=min(item.left_mac for item in history),
        combined_mac=min(item.combined_mac for item in history),
        normalized_distance=max(item.normalized_distance for item in history),
        confidence=min(item.confidence for item in history),
        second_best_confidence=max(
            item.second_best_confidence for item in history
        ),
        relative_confidence_margin=min(
            item.relative_confidence_margin for item in history
        ),
        condition_number=max(item.condition_number for item in history),
        right_residual=max(item.right_residual for item in history),
        left_residual=max(item.left_residual for item in history),
        path_steps=len(history),
        path_label=path_label,
        minimum_individual_mac_threshold=(
            endpoint.minimum_individual_mac_threshold
        ),
        maximum_normalized_distance_threshold=(
            endpoint.maximum_normalized_distance_threshold
        ),
        maximum_condition_number_threshold=(
            endpoint.maximum_condition_number_threshold
        ),
        maximum_eigenpair_residual_threshold=(
            endpoint.maximum_eigenpair_residual_threshold
        ),
        minimum_relative_margin_threshold=(
            endpoint.minimum_relative_margin_threshold
        ),
        status="pending" if reasons else "matched",
        reason=";".join(reasons) if reasons else "accepted",
    )


def _combine_path_matches(first: ModeMatch, second: ModeMatch) -> ModeMatch:
    reasons: list[str] = []
    for item in (first, second):
        if item.status == "pending":
            for reason in item.reason.split(";"):
                if reason and reason not in reasons:
                    reasons.append(reason)
    endpoint_distance = abs(first.eigenvalue_per_s - second.eigenvalue_per_s) / max(
        abs(first.eigenvalue_per_s),
        abs(second.eigenvalue_per_s),
        1.0,
    )
    if endpoint_distance > 1.0e-7 and "path-dependent-identity" not in reasons:
        reasons.append("path-dependent-identity")
    return replace(
        first,
        right_mac=min(first.right_mac, second.right_mac),
        left_mac=min(first.left_mac, second.left_mac),
        combined_mac=min(first.combined_mac, second.combined_mac),
        normalized_distance=max(
            first.normalized_distance,
            second.normalized_distance,
        ),
        confidence=min(first.confidence, second.confidence),
        second_best_confidence=max(
            first.second_best_confidence,
            second.second_best_confidence,
        ),
        relative_confidence_margin=min(
            first.relative_confidence_margin,
            second.relative_confidence_margin,
        ),
        condition_number=max(first.condition_number, second.condition_number),
        right_residual=max(first.right_residual, second.right_residual),
        left_residual=max(first.left_residual, second.left_residual),
        path_steps=first.path_steps + second.path_steps,
        path_label=f"{first.path_label}|{second.path_label}",
        status="pending" if reasons else "matched",
        reason=";".join(reasons) if reasons else "accepted",
    )


def _trace_scenario_modes(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    baseline_signatures: tuple[ModalSignature, ...],
    factors: tuple[tuple[str, float], ...],
    *,
    extra_index: int,
    synchronous_index: int,
    matching_kwargs: dict[str, float],
) -> tuple[ModeMatch, ModeMatch]:
    target = dict(factors)
    orders = [tuple(name for name, _ in factors)]
    if len(factors) == 2:
        orders.append(tuple(reversed(orders[0])))
    if not orders[0]:
        orders = [tuple()]

    path_results: list[tuple[ModeMatch, ModeMatch]] = []
    for order in orders:
        current_values: dict[str, float] = {}
        current_signatures = baseline_signatures
        extra_history: tuple[ModeMatch, ...] = ()
        sync_history: tuple[ModeMatch, ...] = ()
        if not order:
            waypoints = ({},)
            path_label = "baseline-self-check"
        else:
            accumulated: dict[str, float] = {}
            waypoint_list: list[dict[str, float]] = []
            for name in order:
                accumulated = {**accumulated, name: target[name]}
                waypoint_list.append(dict(accumulated))
            waypoints = tuple(waypoint_list)
            path_label = "->".join(order)
        for waypoint in waypoints:
            current_signatures, extra_steps, sync_steps = _advance_with_refinement(
                topology,
                parameters,
                current_values,
                current_signatures,
                waypoint,
                extra_index=extra_index,
                synchronous_index=synchronous_index,
                depth=0,
                matching_kwargs=matching_kwargs,
            )
            current_values = dict(waypoint)
            extra_history += extra_steps
            sync_history += sync_steps
        path_results.append(
            (
                _aggregate_match_history(
                    baseline_signatures[extra_index],
                    extra_history,
                    path_label,
                ),
                _aggregate_match_history(
                    baseline_signatures[synchronous_index],
                    sync_history,
                    path_label,
                ),
            )
        )

    if len(path_results) == 1:
        return path_results[0]
    return (
        _combine_path_matches(path_results[0][0], path_results[1][0]),
        _combine_path_matches(path_results[0][1], path_results[1][1]),
    )


def prepare_anchor_mode_tracking(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    *,
    minimum_confidence: float = DEFAULT_MINIMUM_CONFIDENCE,
    minimum_combined_mac: float = DEFAULT_MINIMUM_COMBINED_MAC,
    minimum_individual_mac: float = DEFAULT_MINIMUM_INDIVIDUAL_MAC,
    maximum_normalized_distance: float = DEFAULT_MAXIMUM_NORMALIZED_DISTANCE,
    maximum_condition_number: float = DEFAULT_MAXIMUM_CONDITION_NUMBER,
    maximum_eigenpair_residual: float = DEFAULT_MAXIMUM_EIGENPAIR_RESIDUAL,
    minimum_relative_margin: float = DEFAULT_MINIMUM_RELATIVE_MARGIN,
) -> AnchorModeTrackingContext:
    """Freeze the hierarchy-disagreement anchor and its two named modes."""

    if not isinstance(topology, NetworkTopology):
        raise TypeError("topology 必须是经过校验的 NetworkTopology 实例。")
    if not isinstance(parameters, AverageDQGFMParameters):
        raise TypeError("parameters 必须是经过校验的 AverageDQGFMParameters 实例。")
    if len(topology.grid_forming_converters) != 1 or len(topology.lines) != 1:
        raise AverageDQAblationError("消融锚点要求恰有一台 GFM 和一条外部线路。")
    converter = topology.grid_forming_converters[0]
    line = topology.lines[0]
    if abs(float(converter.damping_coefficient_pu) - ANCHOR_DAMPING_PU) > 1.0e-12:
        raise AverageDQAblationError("消融锚点要求阻尼 D=60 pu。")
    if abs(line.reactance_pu - ANCHOR_LINE_REACTANCE_PU) > 1.0e-12:
        raise AverageDQAblationError("消融锚点要求外部线路 X=0.1 pu。")

    matching_kwargs = _matching_kwargs(
        minimum_confidence=minimum_confidence,
        minimum_combined_mac=minimum_combined_mac,
        minimum_individual_mac=minimum_individual_mac,
        maximum_normalized_distance=maximum_normalized_distance,
        maximum_condition_number=maximum_condition_number,
        maximum_eigenpair_residual=maximum_eigenpair_residual,
        minimum_relative_margin=minimum_relative_margin,
    )
    _validate_matching_thresholds(**matching_kwargs)

    baseline_topology = topology.model_copy(deep=True)
    baseline_parameters = parameters.model_copy(deep=True)
    baseline = build_average_dq_model(baseline_topology, baseline_parameters)
    baseline_reduction = compare_with_quasisteady_reduction(baseline)
    baseline_extra = _dominant(baseline.poles_per_s)
    if baseline_extra.real <= baseline.stability_tolerance_per_s:
        raise AverageDQAblationError("给定输入不是预期的额外模态失稳锚点。")
    baseline_sync = baseline_reduction.matched_full_pole_per_s
    baseline_signatures = _all_signatures(
        baseline.linearization.closed_state_matrix
    )
    extra_reference_index = int(
        np.argmin(
            [
                abs(signature.eigenvalue_per_s - baseline_extra)
                for signature in baseline_signatures
            ]
        )
    )
    sync_reference_index = int(
        np.argmin(
            [
                abs(signature.eigenvalue_per_s - baseline_sync)
                for signature in baseline_signatures
            ]
        )
    )
    return AnchorModeTrackingContext(
        topology=baseline_topology,
        parameters=baseline_parameters,
        baseline_model=baseline,
        baseline_signatures=baseline_signatures,
        extra_reference_index=extra_reference_index,
        synchronous_reference_index=sync_reference_index,
        matching_kwargs=matching_kwargs,
    )


def evaluate_anchor_factors(
    context: AnchorModeTrackingContext,
    factors: tuple[tuple[str, float], ...],
) -> tuple[AverageDQModel, ModeMatch, ModeMatch]:
    """Rebuild one factored case and track both named modes from the anchor."""

    if not isinstance(context, AnchorModeTrackingContext):
        raise TypeError("context 必须由 prepare_anchor_mode_tracking 构造。")
    factor_values: dict[str, float] = {}
    for name, value in factors:
        numeric = float(value)
        if name not in FACTOR_ORDER:
            raise AverageDQAblationError(f"未知消融因素：{name}。")
        if name in factor_values:
            raise AverageDQAblationError(f"消融因素 {name!r} 重复。")
        if not isfinite(numeric) or numeric < 0.0:
            raise AverageDQAblationError("消融倍率必须是有限非负数。")
        factor_values[name] = numeric
    canonical_factors = _factor_tuple(factor_values)
    try:
        model = _build_factored_model(
            context.topology,
            context.parameters,
            factor_values,
        )
    except AverageDQModelError as error:
        raise AverageDQAblationError(
            f"消融工况无法重建工作点或线性化：{error}"
        ) from error
    extra_match, sync_match = _trace_scenario_modes(
        context.topology,
        context.parameters,
        context.baseline_signatures,
        canonical_factors,
        extra_index=context.extra_reference_index,
        synchronous_index=context.synchronous_reference_index,
        matching_kwargs=context.matching_kwargs,
    )
    if extra_match.candidate_index == sync_match.candidate_index:
        extra_match = replace(
            extra_match,
            status="pending",
            reason="shared-candidate-with-synchronous-mode",
        )
        sync_match = replace(
            sync_match,
            status="pending",
            reason="shared-candidate-with-extra-mode",
        )
    return model, extra_match, sync_match


def run_average_dq_anchor_ablation(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    *,
    minimum_confidence: float = DEFAULT_MINIMUM_CONFIDENCE,
    minimum_combined_mac: float = DEFAULT_MINIMUM_COMBINED_MAC,
    minimum_individual_mac: float = DEFAULT_MINIMUM_INDIVIDUAL_MAC,
    maximum_normalized_distance: float = DEFAULT_MAXIMUM_NORMALIZED_DISTANCE,
    maximum_condition_number: float = DEFAULT_MAXIMUM_CONDITION_NUMBER,
    maximum_eigenpair_residual: float = DEFAULT_MAXIMUM_EIGENPAIR_RESIDUAL,
    minimum_relative_margin: float = DEFAULT_MINIMUM_RELATIVE_MARGIN,
) -> AverageDQAblationStudy:
    """Run the fixed 19-point ablation without mutating either input model."""

    context = prepare_anchor_mode_tracking(
        topology,
        parameters,
        minimum_confidence=minimum_confidence,
        minimum_combined_mac=minimum_combined_mac,
        minimum_individual_mac=minimum_individual_mac,
        maximum_normalized_distance=maximum_normalized_distance,
        maximum_condition_number=maximum_condition_number,
        maximum_eigenpair_residual=maximum_eigenpair_residual,
        minimum_relative_margin=minimum_relative_margin,
    )
    baseline = context.baseline_model
    baseline_reduction = compare_with_quasisteady_reduction(baseline)
    baseline_extra = _dominant(baseline.poles_per_s)
    baseline_sync = baseline_reduction.matched_full_pole_per_s

    points: list[AblationPoint] = []
    for scenario_id, factors in _scenario_definitions():
        model, extra_match, sync_match = evaluate_anchor_factors(
            context,
            factors,
        )
        reduction = compare_with_quasisteady_reduction(model)
        matrix = model.linearization.closed_state_matrix
        (
            extra_groups,
            extra_condition,
            extra_right_residual,
            extra_left_residual,
        ) = _modal_diagnostics(matrix, extra_match)
        (
            sync_groups,
            sync_condition,
            sync_right_residual,
            sync_left_residual,
        ) = _modal_diagnostics(matrix, sync_match)
        reduced_dominant = _dominant(reduction.reduced_poles_per_s)
        residuals = ResidualEvidence(
            algebraic_inf=float(
                np.linalg.norm(model.operating_point.algebraic_residual, ord=np.inf)
            ),
            closed_rhs_inf=model.operating_point.closed_rhs_residual_inf,
            device_rhs_inf=model.operating_point.device_rhs_residual_inf,
            active_power_balance_abs_pu=abs(
                model.operating_point.active_power_balance_residual_pu
            ),
        )
        points.append(
            AblationPoint(
                scenario_id=scenario_id,
                factors=factors,
                damping_coefficient_pu=float(
                    model.converter.damping_coefficient_pu
                ),
                line_reactance_pu=model.line.reactance_pu,
                stability=model.stability.value,
                poles_per_s=tuple(complex(value) for value in model.poles_per_s),
                rightmost_pole_per_s=_dominant(model.poles_per_s),
                extra_mode=extra_match,
                synchronous_mode=sync_match,
                extra_group_participation=extra_groups,
                extra_mode_condition_number=extra_condition,
                extra_right_eigenpair_residual=extra_right_residual,
                extra_left_eigenpair_residual=extra_left_residual,
                synchronous_group_participation=sync_groups,
                synchronous_mode_condition_number=sync_condition,
                synchronous_right_eigenpair_residual=sync_right_residual,
                synchronous_left_eigenpair_residual=sync_left_residual,
                reduced_poles_per_s=tuple(
                    complex(value) for value in reduction.reduced_poles_per_s
                ),
                reduced_dominant_pole_per_s=reduced_dominant,
                synchronizing_stiffness_pu_per_rad=(
                    reduction.synchronizing_stiffness_pu_per_rad
                ),
                synchronous_frequency_relative_error=_relative_error(
                    abs(sync_match.eigenvalue_per_s.imag) / (2.0 * pi),
                    abs(reduced_dominant.imag) / (2.0 * pi),
                ),
                synchronous_decay_relative_error=_relative_error(
                    sync_match.eigenvalue_per_s.real,
                    reduced_dominant.real,
                ),
                residuals=residuals,
            )
        )

    if len(points) != 19 or len({point.scenario_id for point in points}) != 19:
        raise RuntimeError("内部消融工况定义不再满足 19 个唯一工况。")
    return AverageDQAblationStudy(
        topology_id=baseline.topology.id,
        parameter_set_id=baseline.parameters.id,
        baseline_extra_mode_per_s=baseline_extra,
        baseline_synchronous_mode_per_s=baseline_sync,
        state_scaling=tuple((label, 1.0) for label in STATE_LABELS),
        state_scaling_scope=(
            "Only valid for the current per-unit states and delta_rad coordinate; "
            "participation values are not invariant to a future state rescaling."
        ),
        points=tuple(points),
    )
