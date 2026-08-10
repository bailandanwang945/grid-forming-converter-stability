"""Auditable damping--line-reactance scans for the reduced-order VSM model.

The scan changes one selected VSM damping coefficient ``D`` and one selected
AC-line reactance ``X`` on a validated :class:`NetworkTopology`.  Every grid
cell is rebuilt through :func:`build_reduced_order_model`; no interpolated or
display-only stability labels are produced.

``X`` is the selected branch reactance in per unit.  It is deliberately not
renamed or interpreted as a universal short-circuit ratio (SCR).  Results are
only a parameter plane of the low-frequency angle--frequency--active-power
model and do not evaluate the paper's small-gain/small-phase theorem.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from backend.core.reduced_order_model import build_reduced_order_model
from backend.domain.network_models import NetworkTopology


MAX_SCAN_POINTS = 2500


class ReducedOrderScanError(ValueError):
    """Raised when a scan request is invalid or outside the model scope."""


@dataclass(frozen=True)
class DampingReactanceScanPoint:
    damping_coefficient_pu: float
    line_reactance_pu: float
    stability: str
    dominant_real_per_s: float
    dominant_real_hz: float
    oscillation_frequency_hz: float

    def as_dict(self) -> dict:
        return {
            "damping_coefficient_pu": self.damping_coefficient_pu,
            "line_reactance_pu": self.line_reactance_pu,
            "stability": self.stability,
            "dominant_real_per_s": self.dominant_real_per_s,
            "dominant_real_hz": self.dominant_real_hz,
            "oscillation_frequency_hz": self.oscillation_frequency_hz,
        }


@dataclass(frozen=True)
class DampingReactanceScan:
    topology_id: str
    target_vsm_id: str
    target_line_id: str
    damping_values_pu: tuple[float, ...]
    reactance_values_pu: tuple[float, ...]
    rows: tuple[tuple[DampingReactanceScanPoint, ...], ...]

    @property
    def point_count(self) -> int:
        return len(self.damping_values_pu) * len(self.reactance_values_pu)

    @property
    def stability_counts(self) -> dict[str, int]:
        counts = Counter(point.stability for row in self.rows for point in row)
        return {
            "stable": counts["stable"],
            "marginal": counts["marginal"],
            "unstable": counts["unstable"],
        }

    def as_dict(self) -> dict:
        return {
            "topology_id": self.topology_id,
            "target_vsm_id": self.target_vsm_id,
            "target_line_id": self.target_line_id,
            "axes": {
                "damping_values_pu": list(self.damping_values_pu),
                "reactance_values_pu": list(self.reactance_values_pu),
                "row_axis": "damping_coefficient_pu",
                "column_axis": "line_reactance_pu",
            },
            "point_count": self.point_count,
            "stability_counts": self.stability_counts,
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
        raise ReducedOrderScanError(f"{name} 轴至少需要一个取值。")
    if any(not isfinite(value) or value <= 0.0 or value > upper_bound for value in axis):
        raise ReducedOrderScanError(
            f"{name} 轴取值必须是 (0, {upper_bound:g}] 内的有限数。"
        )
    if any(current <= previous for previous, current in zip(axis, axis[1:])):
        raise ReducedOrderScanError(f"{name} 轴取值必须严格递增且不得重复。")
    return axis


def scan_damping_reactance(
    topology: NetworkTopology,
    *,
    target_vsm_id: str,
    target_line_id: str,
    damping_values_pu: Iterable[float],
    reactance_values_pu: Iterable[float],
    maximum_points: int = MAX_SCAN_POINTS,
) -> DampingReactanceScan:
    """Evaluate an explicit ``D``--``X`` grid without mutating ``topology``."""

    if not isinstance(topology, NetworkTopology):
        raise TypeError("topology 必须是已经校验的 NetworkTopology 实例。")
    if not isinstance(maximum_points, int) or maximum_points <= 0:
        raise ReducedOrderScanError("maximum_points 必须是正整数。")

    baseline = NetworkTopology.model_validate(topology.model_dump(mode="python"))
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
        raise ReducedOrderScanError(
            f"D–X 扫描网格共 {point_count} 个点，超过上限 {maximum_points}。"
        )

    vsm_indices = [
        index
        for index, converter in enumerate(baseline.grid_forming_converters)
        if converter.id == target_vsm_id
    ]
    if not vsm_indices:
        raise ReducedOrderScanError(f"目标 VSM {target_vsm_id!r} 不存在。")
    line_indices = [
        index for index, line in enumerate(baseline.lines) if line.id == target_line_id
    ]
    if not line_indices:
        raise ReducedOrderScanError(f"目标线路 {target_line_id!r} 不存在。")
    vsm_index = vsm_indices[0]
    line_index = line_indices[0]

    rows: list[tuple[DampingReactanceScanPoint, ...]] = []
    for damping in damping_axis:
        row: list[DampingReactanceScanPoint] = []
        for reactance in reactance_axis:
            varied = baseline.model_copy(deep=True)
            varied.grid_forming_converters[vsm_index].damping_coefficient_pu = damping
            varied.lines[line_index].reactance_pu = reactance
            model = build_reduced_order_model(varied)
            dominant = model.dominant_mode
            row.append(
                DampingReactanceScanPoint(
                    damping_coefficient_pu=damping,
                    line_reactance_pu=reactance,
                    stability=model.stability.value,
                    dominant_real_per_s=float(dominant.eigenvalue_per_s.real),
                    dominant_real_hz=float(dominant.pole_hz.real),
                    oscillation_frequency_hz=float(
                        dominant.oscillation_frequency_hz
                    ),
                )
            )
        rows.append(tuple(row))

    return DampingReactanceScan(
        topology_id=baseline.id,
        target_vsm_id=target_vsm_id,
        target_line_id=target_line_id,
        damping_values_pu=damping_axis,
        reactance_values_pu=reactance_axis,
        rows=tuple(rows),
    )
