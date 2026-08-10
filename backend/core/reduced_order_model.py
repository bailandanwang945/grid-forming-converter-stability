r"""Low-frequency angle--frequency--active-power reduced-order model.

This module is intentionally narrower than a converter ``dq``-admittance or
electromagnetic-transient model.  It linearises active-power transfer at a flat
voltage profile, forms the network stiffness from ``1 / X``, grounds ideal
infinite-bus nodes, and eliminates non-dynamic buses by Kron reduction.

For every virtual-synchronous-machine (VSM) converter, the state equations are

.. math::

   \dot\delta &= \omega_b\,\Delta\omega_{pu},\\
   M\,\dot{\Delta\omega}_{pu} &= -D\,\Delta\omega_{pu}-\Delta p_m,\\
   T_p\,\dot{\Delta p_m} &= K_{red}\delta-\Delta p_m.

Line resistance and shunt susceptance, reactive-power/voltage coupling,
converter inner loops, saturation, and electromagnetic transients are not
represented.  Results therefore apply only to this stated low-frequency
reduced-order model.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from math import pi
from typing import Iterable

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.linalg import expm

from backend.domain.network_models import GFMControlMode, NetworkTopology


MODEL_ASSUMPTIONS = (
    "线路有功同步刚度按平坦电压工作点的 1/X 标幺值构造。",
    "无限大母线的增量相角固定为零；无动态母线通过 Kron 消元约去。",
    "频率状态采用标幺频率偏差 Δω_pu，且 δ̇=ω_bΔω_pu；M、D、T_p 分别采用秒、"
    "标幺和秒的契约量纲。",
    "线路电阻、并联电纳、无功—电压耦合、静态负荷及其动态、变流器内环、限幅与电磁暂态均被忽略。",
    "当前平坦工作点内核不使用 P/Q 设定值、负荷 P/Q、无限大母线幅值和相角；这些字段仅完成拓扑契约校验与报告留痕。",
)


class ReducedOrderModelError(ValueError):
    """Raised when a valid topology is outside this model's applicability."""


class StabilityStatus(str, Enum):
    """Eigenvalue-based classification for the reduced state matrix."""

    STABLE = "stable"
    MARGINAL = "marginal"
    UNSTABLE = "unstable"


@dataclass(frozen=True)
class DominantMode:
    """Rightmost state-matrix mode and its engineering interpretation."""

    eigenvalue_per_s: complex
    pole_hz: complex
    oscillation_frequency_hz: float
    damping_ratio: float | None


@dataclass(frozen=True)
class LinearTimeResponse:
    """Zero-input response to a specified initial state."""

    time_s: NDArray[np.float64]
    states: NDArray[np.float64]
    state_labels: tuple[str, ...]


@dataclass(frozen=True)
class ReducedOrderModel:
    """Assembled low-frequency model and derived modal quantities."""

    topology_id: str
    vsm_ids: tuple[str, ...]
    state_labels: tuple[str, ...]
    state_matrix: NDArray[np.float64]
    poles_per_s: NDArray[np.complex128]
    poles_hz: NDArray[np.complex128]
    dominant_mode: DominantMode
    stability: StabilityStatus
    synchronous_stiffness_matrix: NDArray[np.float64]
    stability_tolerance_per_s: float
    assumptions: tuple[str, ...] = MODEL_ASSUMPTIONS

    def linear_time_response(
        self,
        time_s: ArrayLike,
        initial_state: ArrayLike | None = None,
    ) -> LinearTimeResponse:
        """Return the exact continuous-time free response ``exp(A t) x(0)``.

        When ``initial_state`` is omitted, the first VSM receives a 1 mrad
        initial angle displacement and all remaining states start from zero.
        This default is a numerical probe, not a physical disturbance model.
        """

        raw_time = np.asarray(time_s)
        if np.iscomplexobj(raw_time):
            raise ReducedOrderModelError("时域采样时刻必须为实数。")
        times = np.asarray(raw_time, dtype=np.float64)
        if times.ndim != 1 or times.size == 0:
            raise ReducedOrderModelError("时域采样时刻必须是一维非空数组。")
        if not np.all(np.isfinite(times)):
            raise ReducedOrderModelError("时域采样时刻不能包含 NaN 或无穷值。")
        if times[0] < 0.0 or np.any(np.diff(times) < 0.0):
            raise ReducedOrderModelError("时域采样时刻必须非负且单调不减。")

        state_count = self.state_matrix.shape[0]
        if initial_state is None:
            x0 = np.zeros(state_count, dtype=np.float64)
            x0[0] = 1.0e-3
        else:
            raw_state = np.asarray(initial_state)
            if np.iscomplexobj(raw_state):
                raise ReducedOrderModelError("初始状态必须为实数。")
            x0 = np.asarray(raw_state, dtype=np.float64)
            if x0.shape != (state_count,):
                raise ReducedOrderModelError(
                    f"初始状态长度应为 {state_count}，实际形状为 {x0.shape}。"
                )
            if not np.all(np.isfinite(x0)):
                raise ReducedOrderModelError("初始状态不能包含 NaN 或无穷值。")

        states = np.empty((times.size, state_count), dtype=np.float64)
        for index, sample_time in enumerate(times):
            states[index, :] = expm(self.state_matrix * sample_time) @ x0
        if not np.all(np.isfinite(states)):
            raise ReducedOrderModelError(
                "线性时域响应发生数值溢出；请缩短仿真时长或减小初始扰动。"
            )

        return LinearTimeResponse(
            time_s=times,
            states=states,
            state_labels=self.state_labels,
        )


def _validated_copy(topology: NetworkTopology) -> NetworkTopology:
    if not isinstance(topology, NetworkTopology):
        raise TypeError("topology 必须是经过校验的 NetworkTopology 实例。")
    # Re-run cross-field checks in case a nested model was assigned after the
    # original topology object had been created.
    return NetworkTopology.model_validate(topology.model_dump(mode="python"))


def _kron_reduced_stiffness(
    topology: NetworkTopology,
    dynamic_bus_ids: tuple[str, ...],
    grounded_bus_ids: set[str],
) -> NDArray[np.float64]:
    bus_ids = tuple(bus.id for bus in topology.buses)
    bus_index = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    laplacian = np.zeros((len(bus_ids), len(bus_ids)), dtype=np.float64)

    for line in topology.lines:
        from_index = bus_index[line.from_bus_id]
        to_index = bus_index[line.to_bus_id]
        susceptance = 1.0 / line.reactance_pu
        laplacian[from_index, from_index] += susceptance
        laplacian[to_index, to_index] += susceptance
        laplacian[from_index, to_index] -= susceptance
        laplacian[to_index, from_index] -= susceptance

    dynamic_indices = [bus_index[bus_id] for bus_id in dynamic_bus_ids]
    interior_bus_ids = tuple(
        bus_id
        for bus_id in bus_ids
        if bus_id not in grounded_bus_ids and bus_id not in dynamic_bus_ids
    )
    interior_indices = [bus_index[bus_id] for bus_id in interior_bus_ids]

    stiffness_dynamic = laplacian[np.ix_(dynamic_indices, dynamic_indices)]
    if interior_indices:
        dynamic_to_interior = laplacian[np.ix_(dynamic_indices, interior_indices)]
        interior_to_dynamic = laplacian[np.ix_(interior_indices, dynamic_indices)]
        stiffness_interior = laplacian[np.ix_(interior_indices, interior_indices)]
        try:
            eliminated = np.linalg.solve(stiffness_interior, interior_to_dynamic)
        except np.linalg.LinAlgError as error:
            raise ReducedOrderModelError(
                "无动态母线的同步刚度子矩阵奇异；网络可能含未接地岛屿，无法执行 Kron 消元。"
            ) from error
        reduced = stiffness_dynamic - dynamic_to_interior @ eliminated
    else:
        reduced = stiffness_dynamic

    reduced = 0.5 * (reduced + reduced.T)
    stiffness_eigenvalues = np.linalg.eigvalsh(reduced)
    stiffness_scale = max(float(np.max(np.abs(stiffness_eigenvalues))), 1.0)
    if float(np.min(stiffness_eigenvalues)) <= 1.0e-12 * stiffness_scale:
        raise ReducedOrderModelError(
            "接地后的同步刚度矩阵不是正定矩阵；网络可能含未接入无限大母线的电气岛。"
        )
    return reduced


def _state_labels(vsm_ids: Iterable[str]) -> tuple[str, ...]:
    ids = tuple(vsm_ids)
    return tuple(
        [*(f"delta_rad:{vsm_id}" for vsm_id in ids)]
        + [*(f"delta_omega_pu:{vsm_id}" for vsm_id in ids)]
        + [*(f"delta_p_m_pu:{vsm_id}" for vsm_id in ids)]
    )


def build_reduced_order_model(
    topology: NetworkTopology,
    *,
    stability_tolerance_per_s: float = 1.0e-8,
) -> ReducedOrderModel:
    """Assemble and analyse the stated low-frequency VSM network model."""

    if not np.isfinite(stability_tolerance_per_s) or stability_tolerance_per_s <= 0:
        raise ReducedOrderModelError("稳定性分类容差必须是有限正数。")

    topology = _validated_copy(topology)
    converters = tuple(sorted(topology.grid_forming_converters, key=lambda item: item.id))
    if not converters:
        raise ReducedOrderModelError("当前降阶模型至少需要一台构网型变流器。")

    unsupported = tuple(
        converter.id
        for converter in converters
        if converter.control_mode is not GFMControlMode.VIRTUAL_SYNCHRONOUS_MACHINE
    )
    if unsupported:
        raise ReducedOrderModelError(
            "当前低频降阶模型仅支持 virtual_synchronous_machine 控制；"
            "不支持的构网型变流器为："
            + "、".join(unsupported)
            + "。"
        )

    if not topology.infinite_buses:
        raise ReducedOrderModelError(
            "当前接地降阶模型需要至少一个无限大母线；纯孤岛系统含公共旋转模态，"
            "须先另行约去角度参考后再建模。"
        )

    dynamic_bus_ids = tuple(converter.bus_id for converter in converters)
    repeated_dynamic_nodes = sorted(
        bus_id
        for bus_id, count in Counter(dynamic_bus_ids).items()
        if count > 1
    )
    if repeated_dynamic_nodes:
        raise ReducedOrderModelError(
            "当前模型不支持多台 VSM 直接并接在同一无阻抗节点；涉及节点："
            + "、".join(repeated_dynamic_nodes)
            + "。"
        )

    grounded_bus_ids = {source.bus_id for source in topology.infinite_buses}
    if topology.reference_bus_id not in grounded_bus_ids:
        raise ReducedOrderModelError(
            "当前接地降阶模型要求 reference_bus_id 指向无限大母线所在节点；"
            f"当前参考节点为 {topology.reference_bus_id!r}。"
        )
    grounded_dynamic_nodes = sorted(set(dynamic_bus_ids) & grounded_bus_ids)
    if grounded_dynamic_nodes:
        raise ReducedOrderModelError(
            "VSM 动态相角不能与理想无限大母线约束在同一节点；涉及节点："
            + "、".join(grounded_dynamic_nodes)
            + "。"
        )

    stiffness = _kron_reduced_stiffness(
        topology,
        dynamic_bus_ids=dynamic_bus_ids,
        grounded_bus_ids=grounded_bus_ids,
    )

    inertia = np.array(
        [converter.virtual_inertia_s for converter in converters], dtype=np.float64
    )
    damping = np.array(
        [converter.damping_coefficient_pu for converter in converters],
        dtype=np.float64,
    )
    measurement_time = np.array(
        [
            converter.active_power_measurement_time_constant_s
            for converter in converters
        ],
        dtype=np.float64,
    )

    converter_count = len(converters)
    state_matrix = np.zeros(
        (3 * converter_count, 3 * converter_count), dtype=np.float64
    )
    delta = slice(0, converter_count)
    frequency = slice(converter_count, 2 * converter_count)
    measured_power = slice(2 * converter_count, 3 * converter_count)

    omega_base = 2.0 * pi * topology.base_values.frequency_hz
    state_matrix[delta, frequency] = omega_base * np.eye(converter_count)
    state_matrix[frequency, frequency] = -np.diag(damping / inertia)
    state_matrix[frequency, measured_power] = -np.diag(1.0 / inertia)
    state_matrix[measured_power, delta] = np.diag(1.0 / measurement_time) @ stiffness
    state_matrix[measured_power, measured_power] = -np.diag(
        1.0 / measurement_time
    )

    poles_per_s = np.sort_complex(np.linalg.eigvals(state_matrix)).astype(
        np.complex128
    )
    poles_hz = poles_per_s / (2.0 * pi)
    maximum_real_part = float(np.max(poles_per_s.real))
    if maximum_real_part < -stability_tolerance_per_s:
        stability = StabilityStatus.STABLE
    elif maximum_real_part > stability_tolerance_per_s:
        stability = StabilityStatus.UNSTABLE
    else:
        stability = StabilityStatus.MARGINAL

    dominant_tie_tolerance = 1.0e-12 * max(abs(maximum_real_part), 1.0)
    candidate_indices = np.flatnonzero(
        np.abs(poles_per_s.real - maximum_real_part) <= dominant_tie_tolerance
    )
    dominant_index = max(candidate_indices, key=lambda index: poles_per_s[index].imag)
    dominant_eigenvalue = complex(poles_per_s[dominant_index])
    dominant_magnitude = abs(dominant_eigenvalue)
    damping_ratio = (
        None
        if dominant_magnitude <= stability_tolerance_per_s
        else -dominant_eigenvalue.real / dominant_magnitude
    )
    dominant_mode = DominantMode(
        eigenvalue_per_s=dominant_eigenvalue,
        pole_hz=dominant_eigenvalue / (2.0 * pi),
        oscillation_frequency_hz=abs(dominant_eigenvalue.imag) / (2.0 * pi),
        damping_ratio=damping_ratio,
    )

    vsm_ids = tuple(converter.id for converter in converters)
    return ReducedOrderModel(
        topology_id=topology.id,
        vsm_ids=vsm_ids,
        state_labels=_state_labels(vsm_ids),
        state_matrix=state_matrix,
        poles_per_s=poles_per_s,
        poles_hz=poles_hz,
        dominant_mode=dominant_mode,
        stability=stability,
        synchronous_stiffness_matrix=stiffness,
        stability_tolerance_per_s=stability_tolerance_per_s,
    )
