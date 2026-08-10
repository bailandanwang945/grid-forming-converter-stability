"""Damping--grid-reactance scans for the 16-state average-value dq model.

Every grid cell is rebuilt from a validated topology and parameter object.  The
scan compares the full 16-state closed-loop poles with a working-point-matched
three-state approximation.  It is a model-hierarchy experiment, not the paper
small-gain/small-phase theorem and not a universal SCR study.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite, pi
from typing import Iterable

import numpy as np

from backend.core.average_dq_model import (
    AverageDQModelError,
    STATE_LABELS,
    build_average_dq_model,
    compare_with_quasisteady_reduction,
)
from backend.domain.average_dq_models import AverageDQGFMParameters
from backend.domain.network_models import NetworkTopology


MAX_SCAN_POINTS = 100


class AverageDQScanError(ValueError):
    """Raised when a scan request is invalid before point calculations."""


@dataclass(frozen=True)
class AverageDQScanPoint:
    damping_coefficient_pu: float
    line_reactance_pu: float
    valid: bool
    full_stability: str | None
    reduced_stability: str | None
    stability_agreement: bool | None
    full_dominant_real_per_s: float | None
    full_oscillation_frequency_hz: float | None
    reduced_dominant_real_per_s: float | None
    reduced_oscillation_frequency_hz: float | None
    matched_full_mode_real_per_s: float | None
    matched_full_mode_frequency_hz: float | None
    synchronizing_stiffness_pu_per_rad: float | None
    frequency_relative_error: float | None
    real_part_relative_error: float | None
    matching_method: str | None
    full_dominant_participation: tuple[tuple[str, float], ...] | None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "damping_coefficient_pu": self.damping_coefficient_pu,
            "line_reactance_pu": self.line_reactance_pu,
            "valid": self.valid,
            "full_stability": self.full_stability,
            "reduced_stability": self.reduced_stability,
            "stability_agreement": self.stability_agreement,
            "full_dominant_real_per_s": self.full_dominant_real_per_s,
            "full_oscillation_frequency_hz": self.full_oscillation_frequency_hz,
            "reduced_dominant_real_per_s": self.reduced_dominant_real_per_s,
            "reduced_oscillation_frequency_hz": self.reduced_oscillation_frequency_hz,
            "matched_full_mode_real_per_s": self.matched_full_mode_real_per_s,
            "matched_full_mode_frequency_hz": self.matched_full_mode_frequency_hz,
            "synchronizing_stiffness_pu_per_rad": (
                self.synchronizing_stiffness_pu_per_rad
            ),
            "frequency_relative_error": self.frequency_relative_error,
            "real_part_relative_error": self.real_part_relative_error,
            "matching_method": self.matching_method,
            "full_dominant_participation": (
                [
                    {"state": state, "normalized_participation": value}
                    for state, value in self.full_dominant_participation
                ]
                if self.full_dominant_participation is not None
                else None
            ),
            "error": self.error,
        }


@dataclass(frozen=True)
class AverageDQDampingReactanceScan:
    topology_id: str
    parameter_set_id: str
    damping_values_pu: tuple[float, ...]
    reactance_values_pu: tuple[float, ...]
    rows: tuple[tuple[AverageDQScanPoint, ...], ...]

    @property
    def point_count(self) -> int:
        return len(self.damping_values_pu) * len(self.reactance_values_pu)

    @property
    def counts(self) -> dict:
        points = [point for row in self.rows for point in row]
        full = Counter(
            point.full_stability for point in points if point.full_stability is not None
        )
        reduced = Counter(
            point.reduced_stability
            for point in points
            if point.reduced_stability is not None
        )
        return {
            "valid": sum(point.valid for point in points),
            "invalid": sum(not point.valid for point in points),
            "agreement": sum(point.stability_agreement is True for point in points),
            "disagreement": sum(point.stability_agreement is False for point in points),
            "full": {
                "stable": full["stable"],
                "marginal": full["marginal"],
                "unstable": full["unstable"],
            },
            "reduced": {
                "stable": reduced["stable"],
                "marginal": reduced["marginal"],
                "unstable": reduced["unstable"],
            },
        }

    def as_dict(self) -> dict:
        return {
            "topology_id": self.topology_id,
            "parameter_set_id": self.parameter_set_id,
            "axes": {
                "damping_values_pu": list(self.damping_values_pu),
                "reactance_values_pu": list(self.reactance_values_pu),
                "row_axis": "damping_coefficient_pu",
                "column_axis": "line_reactance_pu",
            },
            "point_count": self.point_count,
            "counts": self.counts,
            "rows": [[point.as_dict() for point in row] for row in self.rows],
        }


def _validated_axis(
    values: Iterable[float],
    *,
    name: str,
    upper_bound: float,
) -> tuple[float, ...]:
    axis = tuple(float(value) for value in values)
    if not axis:
        raise AverageDQScanError(f"{name}轴至少需要一个取值。")
    if any(not isfinite(value) or value <= 0.0 or value > upper_bound for value in axis):
        raise AverageDQScanError(
            f"{name}轴取值必须是 (0, {upper_bound:g}] 内的有限数。"
        )
    if any(current <= previous for previous, current in zip(axis, axis[1:])):
        raise AverageDQScanError(f"{name}轴取值必须严格递增且不得重复。")
    return axis


def _dominant(poles: np.ndarray) -> complex:
    maximum_real = float(np.max(poles.real))
    tolerance = 1.0e-10 * max(1.0, abs(maximum_real))
    candidates = poles[np.abs(poles.real - maximum_real) <= tolerance]
    return complex(max(candidates, key=lambda value: value.imag))


def _classify(poles: np.ndarray, tolerance_per_s: float) -> str:
    maximum_real = float(np.max(poles.real))
    if maximum_real < -tolerance_per_s:
        return "stable"
    if maximum_real > tolerance_per_s:
        return "unstable"
    return "marginal"


def _dominant_participation(
    state_matrix: np.ndarray,
    dominant_pole: complex,
    *,
    maximum_states: int = 6,
) -> tuple[tuple[str, float], ...]:
    eigenvalues, right_vectors = np.linalg.eig(state_matrix)
    index = int(np.argmin(np.abs(eigenvalues - dominant_pole)))
    try:
        left_vectors = np.linalg.inv(right_vectors)
    except np.linalg.LinAlgError:
        return ()
    raw = np.abs(right_vectors[:, index] * left_vectors[index, :])
    total = float(np.sum(raw))
    if not np.isfinite(total) or total <= 0.0:
        return ()
    normalized = raw / total
    order = np.argsort(normalized)[::-1][:maximum_states]
    return tuple((STATE_LABELS[int(item)], float(normalized[item])) for item in order)


def scan_average_dq_damping_reactance(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    *,
    damping_values_pu: Iterable[float],
    reactance_values_pu: Iterable[float],
    maximum_points: int = MAX_SCAN_POINTS,
) -> AverageDQDampingReactanceScan:
    """Recompute an explicit full/reduced ``D``--line-``X`` parameter plane."""

    if not isinstance(topology, NetworkTopology):
        raise TypeError("topology 必须是已经校验的 NetworkTopology 实例。")
    if not isinstance(parameters, AverageDQGFMParameters):
        raise TypeError("parameters 必须是已经校验的 AverageDQGFMParameters 实例。")
    if not isinstance(maximum_points, int) or maximum_points <= 0:
        raise AverageDQScanError("maximum_points 必须是正整数。")

    baseline_topology = NetworkTopology.model_validate(
        topology.model_dump(mode="python")
    )
    baseline_parameters = AverageDQGFMParameters.model_validate(
        parameters.model_dump(mode="python")
    )
    build_average_dq_model(baseline_topology, baseline_parameters)
    damping_axis = _validated_axis(
        damping_values_pu,
        name="阻尼 D",
        upper_bound=1.0e4,
    )
    reactance_axis = _validated_axis(
        reactance_values_pu,
        name="线路电抗 X",
        upper_bound=100.0,
    )
    point_count = len(damping_axis) * len(reactance_axis)
    if point_count > maximum_points:
        raise AverageDQScanError(
            f"平均值 dq D–X 扫描共 {point_count} 个点，超过上限 {maximum_points}。"
        )

    rows: list[tuple[AverageDQScanPoint, ...]] = []
    for damping in damping_axis:
        row: list[AverageDQScanPoint] = []
        for reactance in reactance_axis:
            varied_topology = baseline_topology.model_copy(deep=True)
            varied_parameters = baseline_parameters.model_copy(deep=True)
            varied_topology.grid_forming_converters[0].damping_coefficient_pu = damping
            varied_topology.lines[0].reactance_pu = reactance
            try:
                model = build_average_dq_model(varied_topology, varied_parameters)
                reduction = compare_with_quasisteady_reduction(model)
                reduced_dominant = _dominant(reduction.reduced_poles_per_s)
                reduced_stability = _classify(
                    reduction.reduced_poles_per_s,
                    model.stability_tolerance_per_s,
                )
                full_dominant = reduction.full_dominant_pole_per_s
                matched_full = reduction.matched_full_pole_per_s
                row.append(
                    AverageDQScanPoint(
                        damping_coefficient_pu=damping,
                        line_reactance_pu=reactance,
                        valid=True,
                        full_stability=model.stability.value,
                        reduced_stability=reduced_stability,
                        stability_agreement=(
                            model.stability.value == reduced_stability
                        ),
                        full_dominant_real_per_s=float(full_dominant.real),
                        full_oscillation_frequency_hz=(
                            abs(float(full_dominant.imag)) / (2.0 * pi)
                        ),
                        reduced_dominant_real_per_s=float(reduced_dominant.real),
                        reduced_oscillation_frequency_hz=(
                            abs(float(reduced_dominant.imag)) / (2.0 * pi)
                        ),
                        matched_full_mode_real_per_s=float(matched_full.real),
                        matched_full_mode_frequency_hz=(
                            abs(float(matched_full.imag)) / (2.0 * pi)
                        ),
                        synchronizing_stiffness_pu_per_rad=(
                            reduction.synchronizing_stiffness_pu_per_rad
                        ),
                        frequency_relative_error=(
                            reduction.oscillation_frequency_relative_error
                        ),
                        real_part_relative_error=reduction.real_part_relative_error,
                        matching_method=reduction.matching_method,
                        full_dominant_participation=_dominant_participation(
                            model.linearization.closed_state_matrix,
                            full_dominant,
                        ),
                    )
                )
            except AverageDQModelError as exc:
                row.append(
                    AverageDQScanPoint(
                        damping_coefficient_pu=damping,
                        line_reactance_pu=reactance,
                        valid=False,
                        full_stability=None,
                        reduced_stability=None,
                        stability_agreement=None,
                        full_dominant_real_per_s=None,
                        full_oscillation_frequency_hz=None,
                        reduced_dominant_real_per_s=None,
                        reduced_oscillation_frequency_hz=None,
                        matched_full_mode_real_per_s=None,
                        matched_full_mode_frequency_hz=None,
                        synchronizing_stiffness_pu_per_rad=None,
                        frequency_relative_error=None,
                        real_part_relative_error=None,
                        matching_method=None,
                        full_dominant_participation=None,
                        error=str(exc),
                    )
                )
        rows.append(tuple(row))

    return AverageDQDampingReactanceScan(
        topology_id=baseline_topology.id,
        parameter_set_id=baseline_parameters.id,
        damping_values_pu=damping_axis,
        reactance_values_pu=reactance_axis,
        rows=tuple(rows),
    )
