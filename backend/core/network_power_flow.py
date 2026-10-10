"""Bounded positive-sequence power flow for editable network topologies.

The solver establishes a fundamental-frequency network operating point and a
global voltage-angle reference.  It is not a converter-internal equilibrium
solver and does not linearize any control or electromagnetic state model.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from backend.domain.network_models import LoadModel, NetworkTopology


class NetworkPowerFlowError(ValueError):
    """Raised when the case is outside the declared power-flow scope."""


class NetworkPowerFlowNumericalError(NetworkPowerFlowError):
    """Raised when no numerically acceptable operating point is found."""


@dataclass(frozen=True)
class LinePowerFlow:
    """Complex powers injected from both terminal buses into one line."""

    line_id: str
    from_bus_id: str
    to_bus_id: str
    from_power_pu: complex
    to_power_pu: complex
    active_loss_pu: float
    apparent_power_max_pu: float
    thermal_loading_ratio: float | None


@dataclass(frozen=True)
class NetworkPowerFlowSolution:
    """Accepted phasor operating point with residual and conditioning evidence."""

    topology_id: str
    bus_ids: tuple[str, ...]
    bus_types: tuple[str, ...]
    voltage_pu: NDArray[np.complex128]
    network_power_injection_pu: NDArray[np.complex128]
    specified_active_injection_pu: NDArray[np.float64]
    specified_reactive_injection_pu: NDArray[np.float64]
    gfm_ids: tuple[str, ...]
    gfm_reactive_power_pu: NDArray[np.float64]
    gfm_reactive_setpoint_mismatch_pu: NDArray[np.float64]
    slack_power_pu: complex
    line_flows: tuple[LinePowerFlow, ...]
    residual_inf_pu: float
    jacobian_condition_number: float
    function_evaluations: int
    active_line_ids: tuple[str, ...]


def _validate_scope(topology: NetworkTopology) -> NetworkTopology:
    validated = NetworkTopology.model_validate(topology.model_dump(mode="python"))
    if len(validated.infinite_buses) != 1:
        raise NetworkPowerFlowError(
            "基波正序潮流首版要求恰有一个无限大母线作为平衡节点。"
        )
    slack_bus_id = validated.infinite_buses[0].bus_id
    if validated.reference_bus_id != slack_bus_id:
        raise NetworkPowerFlowError(
            "reference_bus_id 必须与无限大母线所在节点一致，以唯一确定全局相角基准。"
        )
    gfm_bus_ids = [item.bus_id for item in validated.grid_forming_converters]
    if len(set(gfm_bus_ids)) != len(gfm_bus_ids):
        raise NetworkPowerFlowError(
            "同一母线接有多台构网型变流器时需要显式设备端口展开；潮流首版拒绝合并。"
        )
    if slack_bus_id in gfm_bus_ids:
        raise NetworkPowerFlowError(
            "构网型变流器端口不能与理想无限大母线共用同一平衡节点。"
        )
    return validated


def _assemble_fundamental_ybus(
    topology: NetworkTopology,
) -> tuple[NDArray[np.complex128], tuple[str, ...], tuple[str, ...]]:
    bus_ids = tuple(bus.id for bus in topology.buses)
    positions = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    ybus = np.zeros((len(bus_ids), len(bus_ids)), dtype=np.complex128)
    active_line_ids: list[str] = []
    for line in topology.lines:
        if not line.in_service:
            continue
        impedance = complex(line.resistance_pu, line.reactance_pu)
        if impedance == 0:
            raise NetworkPowerFlowError(f"线路 {line.id!r} 的基频串联阻抗为零。")
        series = 1.0 / impedance
        shunt_half = 0.5j * line.shunt_susceptance_pu
        from_index = positions[line.from_bus_id]
        to_index = positions[line.to_bus_id]
        ybus[from_index, from_index] += series + shunt_half
        ybus[to_index, to_index] += series + shunt_half
        ybus[from_index, to_index] -= series
        ybus[to_index, from_index] -= series
        active_line_ids.append(line.id)

    for load in topology.loads:
        if load.load_model is not LoadModel.CONSTANT_IMPEDANCE:
            continue
        # At |V|=1 p.u., Y=conj(S_load) consumes S_load=V*conj(YV).
        ybus[positions[load.bus_id], positions[load.bus_id]] += complex(
            load.active_power_pu, -load.reactive_power_pu
        )
    return ybus, bus_ids, tuple(active_line_ids)


def _specified_bus_powers(
    topology: NetworkTopology,
    bus_ids: tuple[str, ...],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    positions = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    active = np.zeros(len(bus_ids), dtype=np.float64)
    reactive = np.zeros(len(bus_ids), dtype=np.float64)
    for converter in topology.grid_forming_converters:
        active[positions[converter.bus_id]] += converter.active_power_setpoint_pu
    for load in topology.loads:
        if load.load_model is not LoadModel.CONSTANT_POWER:
            continue
        active[positions[load.bus_id]] -= load.active_power_pu
        reactive[positions[load.bus_id]] -= load.reactive_power_pu
    return active, reactive


def _line_flows(
    topology: NetworkTopology,
    voltage: NDArray[np.complex128],
    bus_ids: tuple[str, ...],
) -> tuple[LinePowerFlow, ...]:
    positions = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    flows: list[LinePowerFlow] = []
    for line in topology.lines:
        if not line.in_service:
            continue
        from_voltage = voltage[positions[line.from_bus_id]]
        to_voltage = voltage[positions[line.to_bus_id]]
        series = 1.0 / complex(line.resistance_pu, line.reactance_pu)
        shunt_half = 0.5j * line.shunt_susceptance_pu
        from_current = (from_voltage - to_voltage) * series + shunt_half * from_voltage
        to_current = (to_voltage - from_voltage) * series + shunt_half * to_voltage
        from_power = from_voltage * np.conj(from_current)
        to_power = to_voltage * np.conj(to_current)
        apparent_max = float(max(abs(from_power), abs(to_power)))
        loading = (
            None
            if line.thermal_limit_pu is None
            else apparent_max / line.thermal_limit_pu
        )
        flows.append(
            LinePowerFlow(
                line_id=line.id,
                from_bus_id=line.from_bus_id,
                to_bus_id=line.to_bus_id,
                from_power_pu=complex(from_power),
                to_power_pu=complex(to_power),
                active_loss_pu=float((from_power + to_power).real),
                apparent_power_max_pu=apparent_max,
                thermal_loading_ratio=loading,
            )
        )
    return tuple(flows)


def solve_network_power_flow(
    topology: NetworkTopology,
    *,
    residual_tolerance_pu: float = 1e-9,
    jacobian_condition_limit: float = 1e12,
    max_function_evaluations: int = 1000,
) -> NetworkPowerFlowSolution:
    """Solve the bounded PV/PQ positive-sequence network operating point."""

    validated = _validate_scope(topology)
    if not np.isfinite(residual_tolerance_pu) or residual_tolerance_pu <= 0:
        raise NetworkPowerFlowError("潮流残差门限必须为有限正数。")
    if not np.isfinite(jacobian_condition_limit) or jacobian_condition_limit <= 1:
        raise NetworkPowerFlowError("潮流雅可比条件数上限必须为大于1的有限数。")
    if max_function_evaluations < 1:
        raise NetworkPowerFlowError("潮流最大函数评价次数必须为正整数。")

    ybus, bus_ids, active_line_ids = _assemble_fundamental_ybus(validated)
    positions = {bus_id: index for index, bus_id in enumerate(bus_ids)}
    slack_source = validated.infinite_buses[0]
    slack_index = positions[slack_source.bus_id]
    gfm_by_bus = {item.bus_id: item for item in validated.grid_forming_converters}
    pv_indices = tuple(positions[bus_id] for bus_id in gfm_by_bus)
    non_slack_indices = tuple(
        index for index in range(len(bus_ids)) if index != slack_index
    )
    pq_indices = tuple(index for index in non_slack_indices if index not in pv_indices)
    specified_active, specified_reactive = _specified_bus_powers(validated, bus_ids)

    fixed_magnitude = np.ones(len(bus_ids), dtype=np.float64)
    fixed_magnitude[slack_index] = slack_source.voltage_magnitude_pu
    for bus_id, converter in gfm_by_bus.items():
        fixed_magnitude[positions[bus_id]] = converter.voltage_setpoint_pu
    slack_angle = slack_source.voltage_angle_deg * pi / 180.0

    def unpack(candidate: NDArray[np.float64]) -> NDArray[np.complex128]:
        angles = np.full(len(bus_ids), slack_angle, dtype=np.float64)
        magnitudes = fixed_magnitude.copy()
        angle_count = len(non_slack_indices)
        angles[list(non_slack_indices)] = candidate[:angle_count]
        if pq_indices:
            magnitudes[list(pq_indices)] = np.exp(candidate[angle_count:])
        return magnitudes * np.exp(1j * angles)

    def mismatch(candidate: NDArray[np.float64]) -> NDArray[np.float64]:
        voltage = unpack(candidate)
        calculated = voltage * np.conj(ybus @ voltage)
        active_mismatch = (
            specified_active[list(non_slack_indices)]
            - calculated.real[list(non_slack_indices)]
        )
        reactive_mismatch = (
            specified_reactive[list(pq_indices)]
            - calculated.imag[list(pq_indices)]
        )
        return np.concatenate((active_mismatch, reactive_mismatch))

    unknown_count = len(non_slack_indices) + len(pq_indices)
    initial = np.r_[
        np.full(len(non_slack_indices), slack_angle),
        np.zeros(len(pq_indices)),
    ]
    if unknown_count:
        lower = np.r_[
            np.full(len(non_slack_indices), -np.inf),
            np.full(len(pq_indices), np.log(0.2)),
        ]
        upper = np.r_[
            np.full(len(non_slack_indices), np.inf),
            np.full(len(pq_indices), np.log(2.0)),
        ]
        solved = least_squares(
            mismatch,
            initial,
            bounds=(lower, upper),
            jac="3-point",
            ftol=1e-12,
            xtol=1e-12,
            gtol=1e-12,
            max_nfev=max_function_evaluations,
        )
        residual = mismatch(solved.x)
        jacobian_condition = float(np.linalg.cond(solved.jac, 2))
        function_evaluations = int(solved.nfev)
        voltage = unpack(solved.x)
        solver_success = bool(solved.success)
    else:
        residual = np.empty(0, dtype=np.float64)
        jacobian_condition = 1.0
        function_evaluations = 0
        voltage = unpack(initial)
        solver_success = True

    residual_inf = float(np.max(np.abs(residual))) if residual.size else 0.0
    if not solver_success or residual_inf > residual_tolerance_pu:
        raise NetworkPowerFlowNumericalError(
            f"基波正序潮流未通过残差门：无穷范数为 {residual_inf:.6g} p.u.，"
            f"门限为 {residual_tolerance_pu:.6g} p.u.。"
        )
    if (
        not np.isfinite(jacobian_condition)
        or jacobian_condition > jacobian_condition_limit
    ):
        raise NetworkPowerFlowNumericalError(
            f"潮流雅可比条件数为 {jacobian_condition:.6g}，超过上限 "
            f"{jacobian_condition_limit:.6g}；工作点数值待定。"
        )

    network_power = voltage * np.conj(ybus @ voltage)
    constant_power_load = {
        bus_id: sum(
            (
                complex(load.active_power_pu, load.reactive_power_pu)
                for load in validated.loads
                if load.bus_id == bus_id
                and load.load_model is LoadModel.CONSTANT_POWER
            ),
            0j,
        )
        for bus_id in bus_ids
    }
    gfm_ids = tuple(item.id for item in validated.grid_forming_converters)
    gfm_reactive = np.asarray(
        [
            network_power[positions[item.bus_id]].imag
            + constant_power_load[item.bus_id].imag
            for item in validated.grid_forming_converters
        ],
        dtype=np.float64,
    )
    reactive_mismatch = np.asarray(
        [
            reactive - item.reactive_power_setpoint_pu
            for item, reactive in zip(
                validated.grid_forming_converters, gfm_reactive, strict=True
            )
        ],
        dtype=np.float64,
    )
    slack_power = complex(
        network_power[slack_index] + constant_power_load[slack_source.bus_id]
    )
    bus_types = tuple(
        "slack" if index == slack_index else "pv" if index in pv_indices else "pq"
        for index in range(len(bus_ids))
    )
    return NetworkPowerFlowSolution(
        topology_id=validated.id,
        bus_ids=bus_ids,
        bus_types=bus_types,
        voltage_pu=voltage,
        network_power_injection_pu=network_power,
        specified_active_injection_pu=specified_active,
        specified_reactive_injection_pu=specified_reactive,
        gfm_ids=gfm_ids,
        gfm_reactive_power_pu=gfm_reactive,
        gfm_reactive_setpoint_mismatch_pu=reactive_mismatch,
        slack_power_pu=slack_power,
        line_flows=_line_flows(validated, voltage, bus_ids),
        residual_inf_pu=residual_inf,
        jacobian_condition_number=jacobian_condition,
        function_evaluations=function_evaluations,
        active_line_ids=active_line_ids,
    )
