"""Compile an electrical graph into global synchronous-dq network admittance.

The compiler stamps each in-service series-RL branch into a nodal matrix in
``[d, q]`` bus order, grounds ideal-voltage-source buses, and eliminates
passive internal buses by a Schur complement.  It returns sampled frequency
responses only; it does not solve a power flow or evaluate a stability
criterion.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Iterable

import numpy as np
from numpy.typing import ArrayLike, NDArray

from backend.domain.network_models import ACLine, NetworkTopology


J_DQ = np.array([[0.0, -1.0], [1.0, 0.0]], dtype=np.float64)


class DQNetworkCompilerError(ValueError):
    """Raised when a topology is outside the compiler's declared scope."""


class DQNetworkNumericalError(DQNetworkCompilerError):
    """Raised when a sampled matrix cannot be reduced reliably."""


@dataclass(frozen=True)
class DQNetworkCompilation:
    """Sampled nodal and port admittance with stable bus ordering metadata."""

    topology_id: str
    frequencies_hz: NDArray[np.float64]
    bus_ids: tuple[str, ...]
    port_bus_ids: tuple[str, ...]
    grounded_bus_ids: tuple[str, ...]
    eliminated_bus_ids: tuple[str, ...]
    nodal_admittance: NDArray[np.complex128]
    port_admittance: NDArray[np.complex128]
    eliminated_block_condition_numbers: NDArray[np.float64]
    active_line_ids: tuple[str, ...]


def _frequency_axis(frequencies_hz: ArrayLike) -> NDArray[np.float64]:
    raw = np.asarray(frequencies_hz)
    if np.iscomplexobj(raw):
        raise DQNetworkCompilerError("网络导纳采样频率必须为实数。")
    values = np.asarray(raw, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise DQNetworkCompilerError("网络导纳采样频率必须是一维非空数组。")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise DQNetworkCompilerError("网络导纳采样频率必须为有限非负数。")
    if np.any(np.diff(values) <= 0.0):
        raise DQNetworkCompilerError("网络导纳采样频率必须严格递增且不得重复。")
    return values


def series_rl_dq_admittance(
    line: ACLine,
    frequencies_hz: ArrayLike,
    base_frequency_hz: float,
) -> NDArray[np.complex128]:
    """Return ``v_from-v_to -> i_from`` for one synchronous-dq RL branch."""

    frequencies = _frequency_axis(frequencies_hz)
    if not np.isfinite(base_frequency_hz) or base_frequency_hz <= 0.0:
        raise DQNetworkCompilerError("网络基频必须为有限正数。")
    omega_base = 2.0 * pi * base_frequency_hz
    identity = np.eye(2, dtype=np.complex128)
    result = np.empty((frequencies.size, 2, 2), dtype=np.complex128)
    for index, frequency_hz in enumerate(frequencies):
        complex_frequency = 1j * 2.0 * pi * frequency_hz
        impedance = (
            line.resistance_pu
            + line.reactance_pu / omega_base * complex_frequency
        ) * identity + line.reactance_pu * J_DQ
        try:
            result[index] = np.linalg.solve(impedance, identity)
        except np.linalg.LinAlgError as error:
            raise DQNetworkNumericalError(
                f"线路 {line.id!r} 在 {frequency_hz:.9g} Hz 的 dq 阻抗矩阵奇异。"
            ) from error
    return result


def _line_shunt_admittance(
    line: ACLine,
    frequencies_hz: NDArray[np.float64],
    base_frequency_hz: float,
) -> NDArray[np.complex128]:
    """Return the total capacitive shunt admittance of a pi-equivalent line."""

    if line.shunt_susceptance_pu < 0.0:
        raise DQNetworkCompilerError(
            f"线路 {line.id!r} 的负并联电纳尚无明确元件类型，dq 网络编译器拒绝推断。"
        )
    omega_base = 2.0 * pi * base_frequency_hz
    identity = np.eye(2, dtype=np.complex128)
    return np.asarray(
        [
            line.shunt_susceptance_pu
            * ((1j * 2.0 * pi * frequency_hz / omega_base) * identity + J_DQ)
            for frequency_hz in frequencies_hz
        ],
        dtype=np.complex128,
    )


def assemble_nodal_dq_admittance(
    topology: NetworkTopology,
    frequencies_hz: ArrayLike,
) -> tuple[NDArray[np.float64], NDArray[np.complex128], tuple[str, ...]]:
    """Stamp all in-service line contributions into the full nodal matrix."""

    validated = NetworkTopology.model_validate(topology.model_dump(mode="python"))
    frequencies = _frequency_axis(frequencies_hz)
    bus_ids = tuple(bus.id for bus in validated.buses)
    bus_index = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    nodal = np.zeros(
        (frequencies.size, 2 * len(bus_ids), 2 * len(bus_ids)),
        dtype=np.complex128,
    )
    active_line_ids: list[str] = []
    for line in validated.lines:
        if not line.in_service:
            continue
        active_line_ids.append(line.id)
        series = series_rl_dq_admittance(
            line,
            frequencies,
            validated.base_values.frequency_hz,
        )
        shunt_half = 0.5 * _line_shunt_admittance(
            line,
            frequencies,
            validated.base_values.frequency_hz,
        )
        from_slice = slice(2 * bus_index[line.from_bus_id], 2 * bus_index[line.from_bus_id] + 2)
        to_slice = slice(2 * bus_index[line.to_bus_id], 2 * bus_index[line.to_bus_id] + 2)
        nodal[:, from_slice, from_slice] += series + shunt_half
        nodal[:, to_slice, to_slice] += series + shunt_half
        nodal[:, from_slice, to_slice] -= series
        nodal[:, to_slice, from_slice] -= series
    return frequencies, nodal, tuple(active_line_ids)


def _dq_indices(bus_ids: tuple[str, ...], selected_bus_ids: Iterable[str]) -> list[int]:
    positions = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    indices: list[int] = []
    for bus_id in selected_bus_ids:
        if bus_id not in positions:
            raise DQNetworkCompilerError(f"待处理母线 {bus_id!r} 不存在。")
        base = 2 * positions[bus_id]
        indices.extend((base, base + 1))
    return indices


def kron_reduce_dq(
    admittance: NDArray[np.complex128],
    bus_ids: tuple[str, ...],
    retained_bus_ids: Iterable[str],
    eliminated_bus_ids: Iterable[str],
    frequencies_hz: ArrayLike,
    *,
    condition_limit: float = 1.0e12,
) -> tuple[NDArray[np.complex128], NDArray[np.float64]]:
    """Reduce complete dq bus pairs with a numerically checked Schur complement."""

    frequencies = _frequency_axis(frequencies_hz)
    matrix = np.asarray(admittance, dtype=np.complex128)
    expected_shape = (frequencies.size, 2 * len(bus_ids), 2 * len(bus_ids))
    if matrix.shape != expected_shape:
        raise DQNetworkCompilerError(
            f"节点导纳矩阵形状应为 {expected_shape}，实际为 {matrix.shape}。"
        )
    if not np.isfinite(condition_limit) or condition_limit <= 1.0:
        raise DQNetworkCompilerError("Kron 约简条件数上限必须为大于1的有限数。")
    retained = tuple(retained_bus_ids)
    eliminated = tuple(eliminated_bus_ids)
    if not retained or len(set(retained)) != len(retained):
        raise DQNetworkCompilerError("保留母线列表必须非空且不得重复。")
    if len(set(eliminated)) != len(eliminated) or set(retained) & set(eliminated):
        raise DQNetworkCompilerError("保留母线与消去母线不得重复或交叠。")
    if set(retained) | set(eliminated) != set(bus_ids):
        raise DQNetworkCompilerError("保留母线与消去母线必须恰好覆盖当前矩阵的全部母线。")
    retained_indices = _dq_indices(bus_ids, retained)
    eliminated_indices = _dq_indices(bus_ids, eliminated)
    if not eliminated_indices:
        return matrix[:, retained_indices][:, :, retained_indices].copy(), np.ones(frequencies.size)

    reduced = np.empty(
        (frequencies.size, len(retained_indices), len(retained_indices)),
        dtype=np.complex128,
    )
    conditions = np.empty(frequencies.size, dtype=np.float64)
    for index, frequency_hz in enumerate(frequencies):
        sample = matrix[index]
        y_rr = sample[np.ix_(retained_indices, retained_indices)]
        y_re = sample[np.ix_(retained_indices, eliminated_indices)]
        y_er = sample[np.ix_(eliminated_indices, retained_indices)]
        y_ee = sample[np.ix_(eliminated_indices, eliminated_indices)]
        condition = float(np.linalg.cond(y_ee))
        conditions[index] = condition
        if not np.isfinite(condition) or condition > condition_limit:
            raise DQNetworkNumericalError(
                f"{frequency_hz:.9g} Hz 的内部母线导纳块条件数为 {condition:.6g}，"
                f"超过上限 {condition_limit:.6g}；Kron 约简结果数值待定。"
            )
        try:
            reduced[index] = y_rr - y_re @ np.linalg.solve(y_ee, y_er)
        except np.linalg.LinAlgError as error:
            raise DQNetworkNumericalError(
                f"{frequency_hz:.9g} Hz 的内部母线导纳块奇异，无法执行 Kron 约简。"
            ) from error
    return reduced, conditions


def compile_network_to_gfm_ports(
    topology: NetworkTopology,
    frequencies_hz: ArrayLike,
    *,
    condition_limit: float = 1.0e12,
) -> DQNetworkCompilation:
    """Ground ideal sources and compile the passive graph seen at GFM buses."""

    validated = NetworkTopology.model_validate(topology.model_dump(mode="python"))
    if validated.loads:
        raise DQNetworkCompilerError(
            "dq 网络编译器尚未定义静态负荷的频域增量导纳，不能忽略负荷后继续计算。"
        )
    port_bus_ids = tuple(item.bus_id for item in validated.grid_forming_converters)
    if not port_bus_ids:
        raise DQNetworkCompilerError("dq 网络编译器至少需要一个构网型变流器端口。")
    if len(set(port_bus_ids)) != len(port_bus_ids):
        raise DQNetworkCompilerError(
            "同一母线接有多台构网型变流器时需要显式端口展开；当前编译器拒绝合并设备端口。"
        )
    grounded_bus_ids = tuple(dict.fromkeys(item.bus_id for item in validated.infinite_buses))
    if not grounded_bus_ids:
        raise DQNetworkCompilerError("dq 网络编译器至少需要一个作为小信号地的无限大母线。")
    if set(port_bus_ids) & set(grounded_bus_ids):
        raise DQNetworkCompilerError("构网型变流器端口不能与小信号接地母线重合。")

    frequencies, nodal, active_line_ids = assemble_nodal_dq_admittance(
        validated,
        frequencies_hz,
    )
    bus_ids = tuple(bus.id for bus in validated.buses)
    ungrounded_bus_ids = tuple(
        bus_id for bus_id in bus_ids if bus_id not in set(grounded_bus_ids)
    )
    ungrounded_indices = _dq_indices(bus_ids, ungrounded_bus_ids)
    grounded_matrix = nodal[:, ungrounded_indices][:, :, ungrounded_indices]
    eliminated_bus_ids = tuple(
        bus_id for bus_id in ungrounded_bus_ids if bus_id not in set(port_bus_ids)
    )
    port_admittance, conditions = kron_reduce_dq(
        grounded_matrix,
        ungrounded_bus_ids,
        port_bus_ids,
        eliminated_bus_ids,
        frequencies,
        condition_limit=condition_limit,
    )
    return DQNetworkCompilation(
        topology_id=validated.id,
        frequencies_hz=frequencies,
        bus_ids=bus_ids,
        port_bus_ids=port_bus_ids,
        grounded_bus_ids=grounded_bus_ids,
        eliminated_bus_ids=eliminated_bus_ids,
        nodal_admittance=nodal,
        port_admittance=port_admittance,
        eliminated_block_condition_numbers=conditions,
        active_line_ids=active_line_ids,
    )
