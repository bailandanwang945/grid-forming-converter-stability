r"""Transparent 16-state average-value dq model for one VSM and an infinite bus.

The model retains an LCL filter, cascaded dq voltage/current PI control, VSM
active-power/frequency dynamics, reactive-power/voltage droop, virtual
impedance, a first-order average modulator, and one external series RL line.

The grid-side filter inductor and external line carry the same current.  They
are combined only in the differential equation; the point-of-common-coupling
(PCC) voltage is reconstructed explicitly, so measured power remains at the
near end of the external line rather than being silently moved to the infinite
bus.  This is an average-value positive-sequence model, not an EMT or switching
model.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from typing import Callable

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.integrate import solve_ivp
from scipy.linalg import expm
from scipy.optimize import least_squares
from scipy.signal import find_peaks

from backend.core.reduced_order_model import StabilityStatus
from backend.domain.average_dq_models import AverageDQGFMParameters
from backend.domain.network_models import (
    ACLine,
    GFMControlMode,
    GridFormingConverter,
    InfiniteBus,
    NetworkTopology,
)


STATE_LABELS = (
    "delta_rad",
    "frequency_deviation_pu",
    "measured_active_power_pu",
    "measured_reactive_power_pu",
    "converter_current_d_pu",
    "converter_current_q_pu",
    "capacitor_voltage_d_pu",
    "capacitor_voltage_q_pu",
    "grid_current_d_pu",
    "grid_current_q_pu",
    "voltage_integrator_d_pu",
    "voltage_integrator_q_pu",
    "current_integrator_d_pu",
    "current_integrator_q_pu",
    "internal_voltage_d_pu",
    "internal_voltage_q_pu",
)

J = np.array([[0.0, -1.0], [1.0, 0.0]], dtype=np.float64)


class AverageDQModelError(ValueError):
    """Raised when a case is invalid or outside the model's explicit scope."""


@dataclass(frozen=True)
class AverageDQOperatingPoint:
    """Accepted equilibrium and its independent physical diagnostics."""

    state: NDArray[np.float64]
    grid_voltage_global: NDArray[np.float64]
    pcc_voltage_local: NDArray[np.float64]
    pcc_voltage_global: NDArray[np.float64]
    algebraic_residual: NDArray[np.float64]
    closed_rhs_residual_inf: float
    device_rhs_residual_inf: float
    active_power_balance_residual_pu: float
    converter_current_magnitude_pu: float
    grid_current_magnitude_pu: float
    internal_voltage_magnitude_pu: float


@dataclass(frozen=True)
class AverageDQLinearization:
    """Closed-loop and converter-port linearizations at one operating point."""

    closed_state_matrix: NDArray[np.float64]
    closed_grid_voltage_matrix: NDArray[np.float64]
    closed_reference_matrix: NDArray[np.float64]
    device_state_matrix: NDArray[np.float64]
    port_voltage_matrix: NDArray[np.float64]
    port_current_state_matrix: NDArray[np.float64]
    port_current_feedthrough: NDArray[np.float64]
    relative_step: float


@dataclass(frozen=True)
class AverageDQTimeResponse:
    """Nonlinear and exact-linear responses from the same initial condition."""

    time_s: NDArray[np.float64]
    nonlinear_states: NDArray[np.float64]
    linear_states: NDArray[np.float64]
    state_labels: tuple[str, ...] = STATE_LABELS


@dataclass(frozen=True)
class NonlinearModeEstimate:
    """Dominant oscillatory mode estimated only from nonlinear angle peaks."""

    oscillation_frequency_hz: float
    decay_rate_per_s: float
    peak_count: int
    first_peak_time_s: float
    last_peak_time_s: float


@dataclass(frozen=True)
class QuasiSteadyReductionComparison:
    """Working-point-matched three-state approximation of the full model."""

    synchronizing_stiffness_pu_per_rad: float
    reduced_state_matrix: NDArray[np.float64]
    reduced_poles_per_s: NDArray[np.complex128]
    full_dominant_pole_per_s: complex
    reduced_dominant_pole_per_s: complex
    oscillation_frequency_relative_error: float
    decay_rate_relative_error: float


@dataclass(frozen=True)
class AverageDQModel:
    """Assembled single-converter average-value model."""

    topology: NetworkTopology
    parameters: AverageDQGFMParameters
    converter: GridFormingConverter
    line: ACLine
    infinite_bus: InfiniteBus
    operating_point: AverageDQOperatingPoint
    linearization: AverageDQLinearization
    poles_per_s: NDArray[np.complex128]
    poles_hz: NDArray[np.complex128]
    stability: StabilityStatus
    stability_tolerance_per_s: float

    def port_admittance(self, frequencies_hz: ArrayLike) -> NDArray[np.complex128]:
        """Return device current admittance with network-to-device current positive."""

        frequencies = _real_vector(frequencies_hz, "频率")
        if np.any(frequencies < 0.0):
            raise AverageDQModelError("端口导纳频率必须非负。")
        linear = self.linearization
        identity = np.eye(linear.device_state_matrix.shape[0])
        response = np.empty((frequencies.size, 2, 2), dtype=np.complex128)
        for index, frequency_hz in enumerate(frequencies):
            frequency_rad_s = 2.0 * pi * frequency_hz
            try:
                state_response = np.linalg.solve(
                    1j * frequency_rad_s * identity - linear.device_state_matrix,
                    linear.port_voltage_matrix,
                )
            except np.linalg.LinAlgError as error:
                raise AverageDQModelError(
                    f"{frequency_hz:g} Hz 处端口导纳求解矩阵奇异。"
                ) from error
            response[index] = (
                linear.port_current_state_matrix @ state_response
                + linear.port_current_feedthrough
            )
        return response

    def nonlinear_linear_response(
        self,
        time_s: ArrayLike,
        *,
        initial_state: ArrayLike | None = None,
        relative_tolerance: float = 1.0e-9,
        absolute_tolerance: float = 1.0e-11,
    ) -> AverageDQTimeResponse:
        """Compare the nonlinear ODE and its exact local linearization."""

        times = _real_vector(time_s, "时域采样时刻")
        if times.size < 2 or times[0] < 0.0 or np.any(np.diff(times) <= 0.0):
            raise AverageDQModelError("时域采样时刻必须至少含两点、非负且严格递增。")
        if relative_tolerance <= 0.0 or absolute_tolerance <= 0.0:
            raise AverageDQModelError("积分容差必须为正数。")

        equilibrium = self.operating_point.state
        if initial_state is None:
            state0 = equilibrium.copy()
            state0[0] += 1.0e-5
        else:
            state0 = np.asarray(initial_state, dtype=np.float64)
            if state0.shape != equilibrium.shape or not np.all(np.isfinite(state0)):
                raise AverageDQModelError("初始状态必须是长度为 16 的有限实数向量。")

        references = _references(self.converter)
        grid_voltage = self.operating_point.grid_voltage_global
        solution = solve_ivp(
            lambda _time, state: _closed_rhs(
                state,
                grid_voltage,
                references,
                self.topology,
                self.parameters,
                self.converter,
                self.line,
            ),
            (float(times[0]), float(times[-1])),
            state0,
            t_eval=times,
            method="DOP853",
            rtol=relative_tolerance,
            atol=absolute_tolerance,
        )
        if not solution.success or solution.y.shape != (16, times.size):
            raise AverageDQModelError(
                "非线性平均值模型积分失败：" + str(solution.message)
            )
        nonlinear = solution.y.T
        perturbation0 = state0 - equilibrium
        linear = np.empty_like(nonlinear)
        for index, sample_time in enumerate(times):
            elapsed = float(sample_time - times[0])
            linear[index] = equilibrium + expm(
                self.linearization.closed_state_matrix * elapsed
            ) @ perturbation0
        if not np.all(np.isfinite(nonlinear)) or not np.all(np.isfinite(linear)):
            raise AverageDQModelError("时域响应出现 NaN 或无穷值。")
        return AverageDQTimeResponse(
            time_s=times,
            nonlinear_states=nonlinear,
            linear_states=linear,
        )


def _rotation(angle_rad: float) -> NDArray[np.float64]:
    return np.array(
        [[cos(angle_rad), -sin(angle_rad)], [sin(angle_rad), cos(angle_rad)]],
        dtype=np.float64,
    )


def estimate_nonlinear_angle_mode(
    response: AverageDQTimeResponse,
    equilibrium_angle_rad: float,
    *,
    minimum_peak_count: int = 4,
) -> NonlinearModeEstimate:
    """Estimate frequency and exponential decay from nonlinear positive peaks.

    This routine does not read the state matrix or its eigenvalues.  It is an
    internal response--pole cross-check, not an independent physical-model
    validation.
    """

    if minimum_peak_count < 3:
        raise AverageDQModelError("模态辨识至少需要三个正峰值。")
    angle_deviation = response.nonlinear_states[:, 0] - equilibrium_angle_rad
    maximum_amplitude = float(np.max(np.abs(angle_deviation)))
    if maximum_amplitude <= 0.0 or not np.isfinite(maximum_amplitude):
        raise AverageDQModelError("非线性相角响应没有可辨识振荡。")
    peak_indices, _ = find_peaks(
        angle_deviation,
        prominence=max(maximum_amplitude * 1.0e-7, 1.0e-14),
    )
    amplitudes = angle_deviation[peak_indices]
    keep = amplitudes > max(maximum_amplitude * 1.0e-7, 1.0e-14)
    peak_indices = peak_indices[keep]
    amplitudes = amplitudes[keep]
    if peak_indices.size < minimum_peak_count:
        raise AverageDQModelError(
            f"非线性相角响应仅识别到 {peak_indices.size} 个有效正峰值；"
            f"至少需要 {minimum_peak_count} 个。"
        )
    peak_times = response.time_s[peak_indices]
    periods = np.diff(peak_times)
    if np.any(periods <= 0.0):
        raise AverageDQModelError("相角峰值时刻不是严格递增序列。")
    frequency = 1.0 / float(np.median(periods))
    slope, _intercept = np.polyfit(peak_times, np.log(amplitudes), deg=1)
    decay_rate = -float(slope)
    if not np.isfinite(frequency) or not np.isfinite(decay_rate):
        raise AverageDQModelError("相角模态辨识产生非有限结果。")
    return NonlinearModeEstimate(
        oscillation_frequency_hz=frequency,
        decay_rate_per_s=decay_rate,
        peak_count=int(peak_indices.size),
        first_peak_time_s=float(peak_times[0]),
        last_peak_time_s=float(peak_times[-1]),
    )


def compare_with_quasisteady_reduction(
    model: AverageDQModel,
    *,
    angle_step_rad: float = 1.0e-5,
) -> QuasiSteadyReductionComparison:
    r"""Compare the full dominant mode with a matched three-state outer model.

    For each perturbed angle, the internal voltage magnitude is re-solved from
    the static Q--V droop equation while filter/controller dynamics are treated
    as quasi-steady.  The resulting ``K_delta = dp/d(delta)`` is inserted into
    the same VSM--active-power-measurement structure used by the low-frequency
    model.  This checks a model hierarchy; it does not assume the two models
    are exactly equivalent.
    """

    if not np.isfinite(angle_step_rad) or angle_step_rad <= 0.0:
        raise AverageDQModelError("同步刚度差分角度必须为有限正数。")
    converter = model.converter
    parameters = model.parameters
    line = model.line
    grid_voltage_global = model.operating_point.grid_voltage_global
    total_resistance = (
        parameters.grid_side_resistance_pu
        + line.resistance_pu
        + parameters.virtual_resistance_pu
    )
    total_reactance = (
        parameters.grid_side_reactance_pu
        + line.reactance_pu
        + parameters.virtual_reactance_pu
    )
    impedance = total_resistance * np.eye(2) + total_reactance * J
    voltage_reference = converter.voltage_setpoint_pu
    reactive_reference = converter.reactive_power_setpoint_pu
    droop = parameters.reactive_power_voltage_droop_pu

    def powers(angle: float, internal_magnitude: float) -> tuple[float, float]:
        grid_voltage_local = _rotation(-angle) @ grid_voltage_global
        current = np.linalg.solve(
            impedance,
            np.array([internal_magnitude, 0.0]) - grid_voltage_local,
        )
        pcc_voltage = (
            grid_voltage_local
            + line.resistance_pu * current
            + line.reactance_pu * J @ current
        )
        return float(pcc_voltage @ current), float(pcc_voltage @ J @ current)

    equilibrium_internal_magnitude = voltage_reference + droop * (
        reactive_reference - model.operating_point.state[3]
    )

    def active_power_at_angle(angle: float) -> float:
        solution = least_squares(
            lambda candidate: np.array(
                [
                    candidate[0]
                    - voltage_reference
                    - droop
                    * (reactive_reference - powers(angle, candidate[0])[1])
                ]
            ),
            np.array([equilibrium_internal_magnitude]),
            bounds=(np.array([0.1]), np.array([2.5])),
            xtol=1.0e-13,
            ftol=1.0e-13,
            gtol=1.0e-13,
            max_nfev=500,
        )
        if not solution.success or abs(float(solution.fun[0])) > 1.0e-10:
            raise AverageDQModelError("准稳态 Q–V 方程求解失败。")
        return powers(angle, float(solution.x[0]))[0]

    angle = float(model.operating_point.state[0])
    stiffness = (
        active_power_at_angle(angle + angle_step_rad)
        - active_power_at_angle(angle - angle_step_rad)
    ) / (2.0 * angle_step_rad)
    if not np.isfinite(stiffness) or stiffness <= 0.0:
        raise AverageDQModelError("工作点同步刚度不是有限正数。")
    omega_base = 2.0 * pi * model.topology.base_values.frequency_hz
    inertia = float(converter.virtual_inertia_s)
    damping = float(converter.damping_coefficient_pu)
    measurement_time = float(converter.active_power_measurement_time_constant_s)
    reduced_matrix = np.array(
        [
            [0.0, omega_base, 0.0],
            [0.0, -damping / inertia, -1.0 / inertia],
            [stiffness / measurement_time, 0.0, -1.0 / measurement_time],
        ],
        dtype=np.float64,
    )
    reduced_poles = np.sort_complex(np.linalg.eigvals(reduced_matrix)).astype(
        np.complex128
    )

    def dominant(poles: NDArray[np.complex128]) -> complex:
        maximum_real = float(np.max(poles.real))
        tolerance = 1.0e-10 * max(1.0, abs(maximum_real))
        candidates = poles[np.abs(poles.real - maximum_real) <= tolerance]
        return complex(max(candidates, key=lambda value: value.imag))

    full_dominant = dominant(model.poles_per_s)
    reduced_dominant = dominant(reduced_poles)
    full_frequency = abs(full_dominant.imag)
    reduced_frequency = abs(reduced_dominant.imag)
    if full_frequency <= 1.0e-12 or -full_dominant.real <= 1.0e-12:
        raise AverageDQModelError("当前主导模态不适合计算振荡频率或衰减率相对误差。")
    frequency_error = abs(reduced_frequency - full_frequency) / full_frequency
    decay_error = abs(reduced_dominant.real - full_dominant.real) / abs(
        full_dominant.real
    )
    return QuasiSteadyReductionComparison(
        synchronizing_stiffness_pu_per_rad=float(stiffness),
        reduced_state_matrix=reduced_matrix,
        reduced_poles_per_s=reduced_poles,
        full_dominant_pole_per_s=full_dominant,
        reduced_dominant_pole_per_s=reduced_dominant,
        oscillation_frequency_relative_error=float(frequency_error),
        decay_rate_relative_error=float(decay_error),
    )


def _real_vector(values: ArrayLike, label: str) -> NDArray[np.float64]:
    raw = np.asarray(values)
    if np.iscomplexobj(raw):
        raise AverageDQModelError(f"{label}必须为实数。")
    result = np.asarray(raw, dtype=np.float64)
    if result.ndim != 1 or result.size == 0 or not np.all(np.isfinite(result)):
        raise AverageDQModelError(f"{label}必须是一维非空有限数组。")
    return result


def _references(converter: GridFormingConverter) -> NDArray[np.float64]:
    return np.array(
        [
            converter.active_power_setpoint_pu,
            converter.reactive_power_setpoint_pu,
            converter.voltage_setpoint_pu,
        ],
        dtype=np.float64,
    )


def _unpack_state(
    state: NDArray[np.float64],
) -> tuple[float, float, float, float, NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    if state.shape != (16,) or not np.all(np.isfinite(state)):
        raise AverageDQModelError("平均值 dq 模型状态必须为长度 16 的有限实数向量。")
    return (
        float(state[0]),
        float(state[1]),
        float(state[2]),
        float(state[3]),
        state[4:6],
        state[6:8],
        state[8:10],
        state[10:12],
        state[12:14],
        state[14:16],
    )


def _controller_and_filter_rhs(
    state: NDArray[np.float64],
    terminal_voltage_local: NDArray[np.float64],
    grid_current_derivative: NDArray[np.float64],
    references: NDArray[np.float64],
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    converter: GridFormingConverter,
) -> NDArray[np.float64]:
    (
        _delta,
        frequency_deviation,
        measured_active_power,
        measured_reactive_power,
        converter_current,
        capacitor_voltage,
        grid_current,
        voltage_integrator,
        current_integrator,
        internal_voltage,
    ) = _unpack_state(state)
    active_reference, reactive_reference, voltage_reference = references
    omega_base = 2.0 * pi * topology.base_values.frequency_hz
    omega_ratio = 1.0 + frequency_deviation

    active_power = float(terminal_voltage_local @ grid_current)
    reactive_power = float(terminal_voltage_local @ J @ grid_current)
    voltage_magnitude_reference = voltage_reference + (
        parameters.reactive_power_voltage_droop_pu
        * (reactive_reference - measured_reactive_power)
    )
    capacitor_voltage_reference = np.array(
        [voltage_magnitude_reference, 0.0], dtype=np.float64
    )
    capacitor_voltage_reference -= parameters.virtual_resistance_pu * grid_current
    capacitor_voltage_reference -= (
        parameters.virtual_reactance_pu * omega_ratio * J @ grid_current
    )
    voltage_error = capacitor_voltage_reference - capacitor_voltage
    converter_current_reference = (
        grid_current
        + parameters.filter_capacitor_susceptance_pu
        * omega_ratio
        * J
        @ capacitor_voltage
        + parameters.voltage_proportional_gain_pu * voltage_error
        + voltage_integrator
    )
    current_error = converter_current_reference - converter_current
    internal_voltage_reference = (
        capacitor_voltage
        + parameters.converter_side_resistance_pu * converter_current
        + parameters.converter_side_reactance_pu
        * omega_ratio
        * J
        @ converter_current
        + parameters.current_proportional_gain_pu * current_error
        + current_integrator
    )

    derivative = np.empty(16, dtype=np.float64)
    derivative[0] = omega_base * frequency_deviation
    derivative[1] = (
        active_reference
        - measured_active_power
        - float(converter.damping_coefficient_pu) * frequency_deviation
    ) / float(converter.virtual_inertia_s)
    derivative[2] = (
        active_power - measured_active_power
    ) / float(converter.active_power_measurement_time_constant_s)
    derivative[3] = (
        reactive_power - measured_reactive_power
    ) / parameters.reactive_power_measurement_time_constant_s
    derivative[4:6] = (
        omega_base
        / parameters.converter_side_reactance_pu
        * (
            internal_voltage
            - capacitor_voltage
            - parameters.converter_side_resistance_pu * converter_current
        )
        - omega_base * omega_ratio * J @ converter_current
    )
    derivative[6:8] = (
        omega_base
        / parameters.filter_capacitor_susceptance_pu
        * (converter_current - grid_current)
        - omega_base * omega_ratio * J @ capacitor_voltage
    )
    derivative[8:10] = grid_current_derivative
    derivative[10:12] = parameters.voltage_integral_gain_per_s * voltage_error
    derivative[12:14] = parameters.current_integral_gain_per_s * current_error
    derivative[14:16] = (
        internal_voltage_reference - internal_voltage
    ) / parameters.modulation_time_constant_s
    return derivative


def _device_rhs(
    state: NDArray[np.float64],
    terminal_voltage_global: NDArray[np.float64],
    references: NDArray[np.float64],
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    converter: GridFormingConverter,
) -> NDArray[np.float64]:
    delta, frequency_deviation, *_rest = _unpack_state(state)
    capacitor_voltage = state[6:8]
    grid_current = state[8:10]
    terminal_voltage_local = _rotation(-delta) @ terminal_voltage_global
    omega_base = 2.0 * pi * topology.base_values.frequency_hz
    grid_current_derivative = (
        omega_base
        / parameters.grid_side_reactance_pu
        * (
            capacitor_voltage
            - terminal_voltage_local
            - parameters.grid_side_resistance_pu * grid_current
        )
        - omega_base * (1.0 + frequency_deviation) * J @ grid_current
    )
    return _controller_and_filter_rhs(
        state,
        terminal_voltage_local,
        grid_current_derivative,
        references,
        topology,
        parameters,
        converter,
    )


def _closed_rhs(
    state: NDArray[np.float64],
    grid_voltage_global: NDArray[np.float64],
    references: NDArray[np.float64],
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    converter: GridFormingConverter,
    line: ACLine,
) -> NDArray[np.float64]:
    delta, frequency_deviation, *_rest = _unpack_state(state)
    capacitor_voltage = state[6:8]
    grid_current = state[8:10]
    grid_voltage_local = _rotation(-delta) @ grid_voltage_global
    omega_base = 2.0 * pi * topology.base_values.frequency_hz
    total_resistance = parameters.grid_side_resistance_pu + line.resistance_pu
    total_reactance = parameters.grid_side_reactance_pu + line.reactance_pu
    grid_current_derivative = (
        omega_base
        / total_reactance
        * (capacitor_voltage - grid_voltage_local - total_resistance * grid_current)
        - omega_base * (1.0 + frequency_deviation) * J @ grid_current
    )
    # Reconstruct the near-end PCC voltage from the external line equation.
    terminal_voltage_local = (
        grid_voltage_local
        + line.resistance_pu * grid_current
        + line.reactance_pu
        / omega_base
        * (
            grid_current_derivative
            + omega_base * (1.0 + frequency_deviation) * J @ grid_current
        )
    )
    return _controller_and_filter_rhs(
        state,
        terminal_voltage_local,
        grid_current_derivative,
        references,
        topology,
        parameters,
        converter,
    )


def _device_current_global(state: NDArray[np.float64]) -> NDArray[np.float64]:
    delta = float(state[0])
    # Network-to-device current is the negative of converter injection.
    return -_rotation(delta) @ state[8:10]


def _validate_case(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
) -> tuple[NetworkTopology, GridFormingConverter, ACLine, InfiniteBus]:
    topology = NetworkTopology.model_validate(topology.model_dump(mode="python"))
    parameters = AverageDQGFMParameters.model_validate(
        parameters.model_dump(mode="python")
    )
    if topology.frame_convention_id != parameters.frame_convention_id:
        raise AverageDQModelError(
            "拓扑与平均值 dq 参数对象的坐标约定不一致。"
        )
    if len(topology.grid_forming_converters) != 1:
        raise AverageDQModelError("平均值 dq v1 仅支持一台构网型变流器。")
    if len(topology.lines) != 1:
        raise AverageDQModelError("平均值 dq v1 仅支持一条外部串联 RL 线路。")
    if len(topology.infinite_buses) != 1:
        raise AverageDQModelError("平均值 dq v1 仅支持一个无限大母线。")
    if topology.loads:
        raise AverageDQModelError("平均值 dq v1 尚不支持静态负荷或负荷动态。")
    converter = topology.grid_forming_converters[0]
    line = topology.lines[0]
    infinite_bus = topology.infinite_buses[0]
    if converter.control_mode is not GFMControlMode.VIRTUAL_SYNCHRONOUS_MACHINE:
        raise AverageDQModelError("平均值 dq v1 仅支持 VSM 有功—频率外环。")
    if converter.id != parameters.converter_id:
        raise AverageDQModelError("平均值 dq 参数对象的 converter_id 与拓扑不一致。")
    if converter.parameter_set_id != parameters.id:
        raise AverageDQModelError(
            "构网型变流器 parameter_set_id 必须指向本次平均值 dq 参数对象。"
        )
    relative_power_base_error = abs(
        converter.rated_apparent_power_va
        - topology.base_values.apparent_power_va
    ) / topology.base_values.apparent_power_va
    if relative_power_base_error > 1.0e-9:
        raise AverageDQModelError(
            "平均值 dq v1 要求设备额定容量与案例功率基值一致。"
        )
    bus_ids = {bus.id for bus in topology.buses}
    if len(bus_ids) != 2:
        raise AverageDQModelError("平均值 dq v1 的外部拓扑必须恰含两个节点。")
    if converter.bus_id == infinite_bus.bus_id:
        raise AverageDQModelError("VSM 与无限大母线不能连接在同一节点。")
    if {line.from_bus_id, line.to_bus_id} != {converter.bus_id, infinite_bus.bus_id}:
        raise AverageDQModelError("唯一线路必须直接连接 VSM 节点与无限大母线节点。")
    if topology.reference_bus_id != infinite_bus.bus_id:
        raise AverageDQModelError("参考节点必须是无限大母线所在节点。")
    if abs(line.shunt_susceptance_pu) > 0.0:
        raise AverageDQModelError("平均值 dq v1 要求外部线路并联电纳为零。")
    for bus in topology.buses:
        relative_voltage_base_error = abs(
            bus.nominal_voltage_v - topology.base_values.voltage_v
        ) / topology.base_values.voltage_v
        if relative_voltage_base_error > 1.0e-9:
            raise AverageDQModelError(
                "平均值 dq v1 要求节点标称电压与案例电压基值一致。"
            )
    return topology, converter, line, infinite_bus


def _operating_point(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    converter: GridFormingConverter,
    line: ACLine,
    infinite_bus: InfiniteBus,
) -> AverageDQOperatingPoint:
    grid_angle_rad = infinite_bus.voltage_angle_deg * pi / 180.0
    grid_voltage_global = infinite_bus.voltage_magnitude_pu * np.array(
        [cos(grid_angle_rad), sin(grid_angle_rad)], dtype=np.float64
    )
    references = _references(converter)
    active_reference, reactive_reference, voltage_reference = references
    total_resistance = (
        parameters.grid_side_resistance_pu
        + line.resistance_pu
        + parameters.virtual_resistance_pu
    )
    total_reactance = (
        parameters.grid_side_reactance_pu
        + line.reactance_pu
        + parameters.virtual_reactance_pu
    )
    impedance = total_resistance * np.eye(2) + total_reactance * J

    def quantities(candidate: NDArray[np.float64]) -> tuple[NDArray[np.float64], ...]:
        delta, voltage_internal = float(candidate[0]), float(candidate[1])
        grid_voltage_local = _rotation(-delta) @ grid_voltage_global
        source_voltage = np.array([voltage_internal, 0.0], dtype=np.float64)
        grid_current = np.linalg.solve(
            impedance, source_voltage - grid_voltage_local
        )
        pcc_voltage = (
            grid_voltage_local
            + line.resistance_pu * grid_current
            + line.reactance_pu * J @ grid_current
        )
        active_power = float(pcc_voltage @ grid_current)
        reactive_power = float(pcc_voltage @ J @ grid_current)
        residual = np.array(
            [
                active_power - active_reference,
                voltage_internal
                - voltage_reference
                - parameters.reactive_power_voltage_droop_pu
                * (reactive_reference - reactive_power),
            ],
            dtype=np.float64,
        )
        return residual, grid_current, pcc_voltage, grid_voltage_local

    approximate_angle = grid_angle_rad + np.clip(
        active_reference
        * max(total_reactance, 1.0e-6)
        / max(voltage_reference * infinite_bus.voltage_magnitude_pu, 1.0e-6),
        -0.8,
        0.8,
    )
    guesses = (
        np.array([approximate_angle, voltage_reference]),
        np.array([grid_angle_rad, voltage_reference]),
        np.array([approximate_angle + 0.2, voltage_reference]),
        np.array([approximate_angle - 0.2, voltage_reference]),
    )
    solutions = [
        least_squares(
            lambda candidate: quantities(candidate)[0],
            guess,
            bounds=(np.array([-pi, 0.1]), np.array([pi, 2.5])),
            xtol=1.0e-13,
            ftol=1.0e-13,
            gtol=1.0e-13,
            max_nfev=1000,
        )
        for guess in guesses
    ]
    solution = min(solutions, key=lambda item: np.linalg.norm(item.fun, ord=np.inf))
    algebraic_residual, grid_current, pcc_voltage_local, _grid_voltage_local = quantities(
        solution.x
    )
    if (
        not solution.success
        or not np.all(np.isfinite(solution.x))
        or float(np.linalg.norm(algebraic_residual, ord=np.inf)) > 1.0e-10
    ):
        raise AverageDQModelError(
            "平均值 dq 工作点求解失败或代数残差超过 1e-10 pu。"
        )

    delta, voltage_internal = float(solution.x[0]), float(solution.x[1])
    capacitor_voltage = (
        np.array([voltage_internal, 0.0], dtype=np.float64)
        - parameters.virtual_resistance_pu * grid_current
        - parameters.virtual_reactance_pu * J @ grid_current
    )
    converter_current = (
        grid_current
        + parameters.filter_capacitor_susceptance_pu * J @ capacitor_voltage
    )
    internal_voltage = (
        capacitor_voltage
        + parameters.converter_side_resistance_pu * converter_current
        + parameters.converter_side_reactance_pu * J @ converter_current
    )
    active_power = float(pcc_voltage_local @ grid_current)
    reactive_power = float(pcc_voltage_local @ J @ grid_current)
    state = np.concatenate(
        (
            np.array([delta, 0.0, active_power, reactive_power]),
            converter_current,
            capacitor_voltage,
            grid_current,
            np.zeros(4),
            internal_voltage,
        )
    ).astype(np.float64)
    closed_residual = _closed_rhs(
        state,
        grid_voltage_global,
        references,
        topology,
        parameters,
        converter,
        line,
    )
    pcc_voltage_global = _rotation(delta) @ pcc_voltage_local
    device_residual = _device_rhs(
        state,
        pcc_voltage_global,
        references,
        topology,
        parameters,
        converter,
    )
    power_balance_residual = float(
        internal_voltage @ converter_current
        - pcc_voltage_local @ grid_current
        - parameters.converter_side_resistance_pu
        * converter_current
        @ converter_current
        - parameters.grid_side_resistance_pu * grid_current @ grid_current
    )
    closed_norm = float(np.linalg.norm(closed_residual, ord=np.inf))
    device_norm = float(np.linalg.norm(device_residual, ord=np.inf))
    current_converter_norm = float(np.linalg.norm(converter_current))
    current_grid_norm = float(np.linalg.norm(grid_current))
    internal_voltage_norm = float(np.linalg.norm(internal_voltage))
    if closed_norm > 1.0e-9 or device_norm > 1.0e-9:
        raise AverageDQModelError(
            "工作点动态残差超过 1e-9 pu/s，拒绝继续稳定性分析。"
        )
    if abs(power_balance_residual) > 1.0e-8:
        raise AverageDQModelError(
            "工作点滤波器有功平衡残差超过 1e-8 pu。"
        )
    if max(current_converter_norm, current_grid_norm) > (
        parameters.diagnostic_current_limit_pu + 1.0e-10
    ):
        raise AverageDQModelError("工作点电流超过诊断限值，拒绝线性化。")
    if internal_voltage_norm > (
        parameters.diagnostic_internal_voltage_limit_pu + 1.0e-10
    ):
        raise AverageDQModelError("工作点内部电压超过诊断限值，拒绝线性化。")
    return AverageDQOperatingPoint(
        state=state,
        grid_voltage_global=grid_voltage_global,
        pcc_voltage_local=pcc_voltage_local,
        pcc_voltage_global=pcc_voltage_global,
        algebraic_residual=algebraic_residual,
        closed_rhs_residual_inf=closed_norm,
        device_rhs_residual_inf=device_norm,
        active_power_balance_residual_pu=power_balance_residual,
        converter_current_magnitude_pu=current_converter_norm,
        grid_current_magnitude_pu=current_grid_norm,
        internal_voltage_magnitude_pu=internal_voltage_norm,
    )


def _jacobian(
    function: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    point: NDArray[np.float64],
    relative_step: float,
) -> NDArray[np.float64]:
    if not np.isfinite(relative_step) or relative_step <= 0.0:
        raise AverageDQModelError("数值线性化相对步长必须为有限正数。")
    baseline = np.asarray(function(point), dtype=np.float64)
    result = np.empty((baseline.size, point.size), dtype=np.float64)
    for column in range(point.size):
        step = relative_step * max(1.0, abs(float(point[column])))
        positive = point.copy()
        negative = point.copy()
        positive[column] += step
        negative[column] -= step
        result[:, column] = (function(positive) - function(negative)) / (2.0 * step)
    if not np.all(np.isfinite(result)):
        raise AverageDQModelError("数值线性化产生 NaN 或无穷值。")
    return result


def linearize_average_dq_model(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    converter: GridFormingConverter,
    line: ACLine,
    operating_point: AverageDQOperatingPoint,
    *,
    relative_step: float = 1.0e-5,
) -> AverageDQLinearization:
    """Linearize both the directly closed system and the converter port."""

    state = operating_point.state
    references = _references(converter)
    grid_voltage = operating_point.grid_voltage_global
    terminal_voltage = operating_point.pcc_voltage_global
    closed_state = _jacobian(
        lambda candidate: _closed_rhs(
            candidate,
            grid_voltage,
            references,
            topology,
            parameters,
            converter,
            line,
        ),
        state,
        relative_step,
    )
    closed_grid = _jacobian(
        lambda candidate: _closed_rhs(
            state,
            candidate,
            references,
            topology,
            parameters,
            converter,
            line,
        ),
        grid_voltage,
        relative_step,
    )
    closed_reference = _jacobian(
        lambda candidate: _closed_rhs(
            state,
            grid_voltage,
            candidate,
            topology,
            parameters,
            converter,
            line,
        ),
        references,
        relative_step,
    )
    device_state = _jacobian(
        lambda candidate: _device_rhs(
            candidate,
            terminal_voltage,
            references,
            topology,
            parameters,
            converter,
        ),
        state,
        relative_step,
    )
    port_voltage = _jacobian(
        lambda candidate: _device_rhs(
            state,
            candidate,
            references,
            topology,
            parameters,
            converter,
        ),
        terminal_voltage,
        relative_step,
    )
    current_state = _jacobian(_device_current_global, state, relative_step)
    current_feedthrough = np.zeros((2, 2), dtype=np.float64)
    return AverageDQLinearization(
        closed_state_matrix=closed_state,
        closed_grid_voltage_matrix=closed_grid,
        closed_reference_matrix=closed_reference,
        device_state_matrix=device_state,
        port_voltage_matrix=port_voltage,
        port_current_state_matrix=current_state,
        port_current_feedthrough=current_feedthrough,
        relative_step=relative_step,
    )


def external_line_admittance(
    line: ACLine,
    frequency_hz: float,
    base_frequency_hz: float,
) -> NDArray[np.complex128]:
    """Return the analytic global-dq admittance of the external series RL line."""

    if not np.isfinite(frequency_hz) or frequency_hz < 0.0:
        raise AverageDQModelError("线路导纳频率必须为有限非负数。")
    if not np.isfinite(base_frequency_hz) or base_frequency_hz <= 0.0:
        raise AverageDQModelError("基频必须为有限正数。")
    complex_frequency = 1j * 2.0 * pi * frequency_hz
    impedance = (
        line.resistance_pu
        + line.reactance_pu / (2.0 * pi * base_frequency_hz) * complex_frequency
    ) * np.eye(2, dtype=np.complex128) + line.reactance_pu * J
    try:
        return np.linalg.inv(impedance).astype(np.complex128)
    except np.linalg.LinAlgError as error:
        raise AverageDQModelError("外部线路导纳矩阵奇异。") from error


def close_port_model_with_external_line(
    linearization: AverageDQLinearization,
    line: ACLine,
    base_frequency_hz: float,
) -> NDArray[np.float64]:
    r"""Reassemble the closed state matrix from the converter port model.

    For network-to-device current ``i_dev`` and a fixed infinite-bus voltage,
    the external line satisfies

    ``d i_dev/dt = -wb/Xn * v_pcc - wb*Rn/Xn * i_dev - wb*J*i_dev``.

    Equating this derivative with ``C(Ax+Bv)`` eliminates the PCC voltage and
    yields an independently assembled 16-state closed-loop matrix.  Agreement
    with the direct combined-branch linearization checks the PCC direction,
    dq rotation, line dynamics, and current sign in one invariant.
    """

    if not np.isfinite(base_frequency_hz) or base_frequency_hz <= 0.0:
        raise AverageDQModelError("基频必须为有限正数。")
    omega_base = 2.0 * pi * base_frequency_hz
    network_state = (
        -omega_base * line.resistance_pu / line.reactance_pu * np.eye(2)
        - omega_base * J
    )
    network_voltage = -omega_base / line.reactance_pu * np.eye(2)
    device_a = linearization.device_state_matrix
    device_b = linearization.port_voltage_matrix
    current_c = linearization.port_current_state_matrix
    elimination_matrix = current_c @ device_b - network_voltage
    elimination_rhs = network_state @ current_c - current_c @ device_a
    try:
        voltage_feedback = np.linalg.solve(elimination_matrix, elimination_rhs)
    except np.linalg.LinAlgError as error:
        raise AverageDQModelError(
            "端口模型与外部线路的电压消元矩阵奇异。"
        ) from error
    closed = device_a + device_b @ voltage_feedback
    if not np.all(np.isfinite(closed)):
        raise AverageDQModelError("端口互联组装产生 NaN 或无穷值。")
    return closed


def build_average_dq_model(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    *,
    relative_step: float = 1.0e-5,
    stability_tolerance_per_s: float = 1.0e-7,
) -> AverageDQModel:
    """Validate, solve, linearize, and classify the average-value dq model."""

    if (
        not np.isfinite(stability_tolerance_per_s)
        or stability_tolerance_per_s <= 0.0
    ):
        raise AverageDQModelError("稳定性分类容差必须为有限正数。")
    topology, converter, line, infinite_bus = _validate_case(topology, parameters)
    operating_point = _operating_point(
        topology, parameters, converter, line, infinite_bus
    )
    linearization = linearize_average_dq_model(
        topology,
        parameters,
        converter,
        line,
        operating_point,
        relative_step=relative_step,
    )
    poles = np.sort_complex(
        np.linalg.eigvals(linearization.closed_state_matrix)
    ).astype(np.complex128)
    maximum_real_part = float(np.max(poles.real))
    if maximum_real_part < -stability_tolerance_per_s:
        stability = StabilityStatus.STABLE
    elif maximum_real_part > stability_tolerance_per_s:
        stability = StabilityStatus.UNSTABLE
    else:
        stability = StabilityStatus.MARGINAL
    return AverageDQModel(
        topology=topology,
        parameters=parameters,
        converter=converter,
        line=line,
        infinite_bus=infinite_bus,
        operating_point=operating_point,
        linearization=linearization,
        poles_per_s=poles,
        poles_hz=poles / (2.0 * pi),
        stability=stability,
        stability_tolerance_per_s=stability_tolerance_per_s,
    )
