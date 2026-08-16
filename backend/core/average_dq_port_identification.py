r"""Nonlinear sinestream identification of the average-dq device admittance.

The converter-only port state matrix is not asymptotically stable for the
verification preset.  Consequently, prescribing PCC voltage and waiting for a
steady response is not a well-posed experiment.  This module instead excites
the stable converter--line--infinite-bus closed loop at the infinite-bus
voltage source.  Two independent global-dq trials provide PCC-voltage and
network-to-device-current phasor matrices, from which ``Y = I V^-1`` recovers
the converter port admittance.

The workflow mirrors the relevant MathWorks ``frest.Sinestream`` contract:
one frequency at a time, explicit settling periods, explicit measurement
periods, and a fixed number of samples per period.  The nonlinear ODE supplies
all response data; the local state matrix is read only after identification to
form the comparison target.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, pi
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.integrate import solve_ivp

from backend.core.average_dq_model import (
    AverageDQModel,
    AverageDQModelError,
    _closed_pcc_voltage_global,
    _closed_rhs,
    _device_current_global,
    _references,
)
from backend.core.reduced_order_model import StabilityStatus


DEFAULT_IDENTIFICATION_FREQUENCIES_HZ = (0.2, 2.0, 20.0)


@dataclass(frozen=True)
class PortIdentificationPoint:
    """One frequency of the nonlinear port-admittance comparison."""

    frequency_hz: float
    settling_periods: int
    measurement_periods: int
    samples_per_period: int
    solver_method: str
    identified_admittance_pu: NDArray[np.complex128]
    linearized_admittance_pu: NDArray[np.complex128]
    pcc_voltage_phasor_matrix_pu: NDArray[np.complex128]
    device_current_phasor_matrix_pu: NDArray[np.complex128]
    voltage_matrix_condition_number: float
    magnitude_relative_error: NDArray[np.float64]
    phase_error_deg: NDArray[np.float64]
    maximum_magnitude_relative_error: float
    maximum_phase_error_deg: float
    maximum_harmonic_residual_ratio: float
    passed: bool


@dataclass(frozen=True)
class PortIdentificationStudy:
    """Traceable fixed-frame nonlinear sinestream identification result."""

    points: tuple[PortIdentificationPoint, ...]
    source_amplitude_pu: float
    minimum_settling_time_s: float
    magnitude_error_limit: float
    phase_error_limit_deg: float
    harmonic_residual_limit: float
    voltage_matrix_condition_limit: float
    device_open_port_spectral_abscissa_per_s: float
    passed: bool
    identification_path: str = (
        "nonlinear-closed-loop-grid-source-injection-and-pcc-Y=I*inv(V)"
    )
    frame: str = "fixed-global-synchronous-dq"
    current_direction: str = "network-to-device-positive"


def _complex_value_as_dict(value: complex) -> dict[str, float]:
    return {
        "real": float(value.real),
        "imag": float(value.imag),
        "magnitude": float(abs(value)),
        "phase_deg": float(np.angle(value, deg=True)),
    }


def _complex_matrix_as_dict(
    values: NDArray[np.complex128],
) -> list[list[dict[str, float]]]:
    return [
        [_complex_value_as_dict(complex(value)) for value in row]
        for row in np.asarray(values)
    ]


def _point_as_dict(point: PortIdentificationPoint) -> dict[str, Any]:
    return {
        "frequency_hz": point.frequency_hz,
        "settling_periods": point.settling_periods,
        "measurement_periods": point.measurement_periods,
        "samples_per_period": point.samples_per_period,
        "solver_method": point.solver_method,
        "identified_admittance_pu": _complex_matrix_as_dict(
            point.identified_admittance_pu
        ),
        "linearized_admittance_pu": _complex_matrix_as_dict(
            point.linearized_admittance_pu
        ),
        "pcc_voltage_phasor_matrix_pu": _complex_matrix_as_dict(
            point.pcc_voltage_phasor_matrix_pu
        ),
        "device_current_phasor_matrix_pu": _complex_matrix_as_dict(
            point.device_current_phasor_matrix_pu
        ),
        "voltage_matrix_condition_number": (
            point.voltage_matrix_condition_number
        ),
        "magnitude_relative_error": point.magnitude_relative_error.tolist(),
        "phase_error_deg": point.phase_error_deg.tolist(),
        "maximum_magnitude_relative_error": (
            point.maximum_magnitude_relative_error
        ),
        "maximum_phase_error_deg": point.maximum_phase_error_deg,
        "maximum_harmonic_residual_ratio": (
            point.maximum_harmonic_residual_ratio
        ),
        "passed": point.passed,
    }


def evaluate_fixed_port_identification_verification(
    model: AverageDQModel,
) -> dict[str, Any]:
    """Run and serialize the frozen three-frequency verification contract."""

    study = identify_port_admittance_with_sinestream(model)
    half_amplitude = identify_port_admittance_with_sinestream(
        model,
        [2.0],
        source_amplitude_pu=0.5 * study.source_amplitude_pu,
    ).points[0]
    baseline_2hz = next(
        point for point in study.points if point.frequency_hz == 2.0
    )
    amplitude_difference = np.abs(
        half_amplitude.identified_admittance_pu
        - baseline_2hz.identified_admittance_pu
    ) / np.maximum(
        np.abs(baseline_2hz.identified_admittance_pu),
        np.finfo(np.float64).eps,
    )
    points = [_point_as_dict(point) for point in study.points]
    return {
        "summary": {
            "passed": study.passed,
            "frequency_count": len(study.points),
            "maximum_magnitude_relative_error": max(
                point.maximum_magnitude_relative_error
                for point in study.points
            ),
            "maximum_phase_error_deg": max(
                point.maximum_phase_error_deg for point in study.points
            ),
            "maximum_harmonic_residual_ratio": max(
                point.maximum_harmonic_residual_ratio
                for point in study.points
            ),
            "maximum_voltage_matrix_condition_number": max(
                point.voltage_matrix_condition_number
                for point in study.points
            ),
        },
        "contract": {
            "frequencies_hz": [point.frequency_hz for point in study.points],
            "source_amplitude_pu": study.source_amplitude_pu,
            "minimum_settling_time_s": study.minimum_settling_time_s,
            "measurement_periods": study.points[0].measurement_periods,
            "samples_per_period": study.points[0].samples_per_period,
            "magnitude_error_limit": study.magnitude_error_limit,
            "phase_error_limit_deg": study.phase_error_limit_deg,
            "harmonic_residual_limit": study.harmonic_residual_limit,
            "voltage_matrix_condition_limit": (
                study.voltage_matrix_condition_limit
            ),
            "frame": study.frame,
            "current_direction": study.current_direction,
        },
        "points": points,
        "amplitude_halving_check_at_2hz": {
            "baseline_amplitude_pu": study.source_amplitude_pu,
            "halved_amplitude_pu": 0.5 * study.source_amplitude_pu,
            "maximum_element_relative_difference": float(
                np.max(amplitude_difference)
            ),
            "halved_amplitude_point": _point_as_dict(half_amplitude),
        },
        "model_scope": {
            "claim_level": (
                "internal-nonlinear-versus-linear-software-verification"
            ),
            "physical_validation": False,
            "emt_validation": False,
            "paper_fig8_fixture": False,
            "statement": (
                "在团队定义的单机平均值 dq 校核算例和所测三个频点内，"
                "非线性闭环正弦辨识支持端口线性化实现的一致性；"
                "该结果不确认真实硬件或电磁暂态模型。"
            ),
        },
        "provenance": {
            "implementation": (
                "backend.core.average_dq_port_identification"
            ),
            "identification_path": study.identification_path,
            "device_open_port_spectral_abscissa_per_s": (
                study.device_open_port_spectral_abscissa_per_s
            ),
            "mathworks_release_checked": "R2024b",
            "mathworks_functions_checked": [
                "frestimate",
                "frest.Sinestream",
                "tfestimate",
            ],
            "randomness": "none-deterministic-ode-and-least-squares",
        },
    }


def estimate_fundamental_phasor(
    time_s: ArrayLike,
    samples: ArrayLike,
    frequency_hz: float,
) -> tuple[NDArray[np.complex128], float]:
    r"""Estimate ``Re{X exp(jwt)}`` phasors by harmonic least squares.

    A constant term is fitted together with cosine and sine terms.  The
    returned residual is the largest channel RMS residual divided by that
    channel's fitted fundamental RMS.  It exposes remaining transients,
    harmonics, and numerical noise instead of silently discarding them.
    """

    times = np.asarray(time_s, dtype=np.float64)
    values = np.asarray(samples, dtype=np.float64)
    if times.ndim != 1 or times.size < 8 or not np.all(np.isfinite(times)):
        raise AverageDQModelError("相量估计时刻必须是一维有限实数序列且至少含八点。")
    if np.any(np.diff(times) <= 0.0):
        raise AverageDQModelError("相量估计时刻必须严格递增。")
    if not np.isfinite(frequency_hz) or frequency_hz <= 0.0:
        raise AverageDQModelError("相量估计频率必须为有限正数。")
    if values.ndim == 1:
        values = values[:, None]
    if (
        values.ndim != 2
        or values.shape[0] != times.size
        or not np.all(np.isfinite(values))
    ):
        raise AverageDQModelError("相量估计样本必须与时刻等长且全部有限。")

    angle = 2.0 * pi * frequency_hz * times
    design = np.column_stack(
        (np.ones(times.size), np.cos(angle), np.sin(angle))
    )
    coefficients, *_unused = np.linalg.lstsq(design, values, rcond=None)
    phasors = coefficients[1] - 1j * coefficients[2]
    fitted = design @ coefficients
    residual_rms = np.sqrt(np.mean((values - fitted) ** 2, axis=0))
    fundamental_rms = np.sqrt(
        0.5 * (coefficients[1] ** 2 + coefficients[2] ** 2)
    )
    if np.any(fundamental_rms <= np.finfo(np.float64).eps):
        raise AverageDQModelError("相量估计的基波分量过小，无法定义归一化残差。")
    residual_ratio = float(np.max(residual_rms / fundamental_rms))
    return phasors.astype(np.complex128), residual_ratio


def identify_port_admittance_with_sinestream(
    model: AverageDQModel,
    frequencies_hz: ArrayLike = DEFAULT_IDENTIFICATION_FREQUENCIES_HZ,
    *,
    source_amplitude_pu: float = 1.0e-4,
    minimum_settling_time_s: float = 2.5,
    measurement_periods: int = 2,
    samples_per_period: int = 128,
    magnitude_error_limit: float = 0.01,
    phase_error_limit_deg: float = 1.0,
    harmonic_residual_limit: float = 0.02,
    voltage_matrix_condition_limit: float = 100.0,
    relative_tolerance: float = 1.0e-7,
    absolute_tolerance: float = 1.0e-9,
) -> PortIdentificationStudy:
    """Identify the 2x2 device admittance from nonlinear closed-loop trials."""

    frequencies = np.asarray(frequencies_hz, dtype=np.float64)
    if (
        frequencies.ndim != 1
        or frequencies.size == 0
        or not np.all(np.isfinite(frequencies))
        or np.any(frequencies <= 0.0)
        or np.any(np.diff(frequencies) <= 0.0)
    ):
        raise AverageDQModelError("辨识频率必须是严格递增、非空的有限正数序列。")
    positive_scalars = {
        "源电压扰动幅值": source_amplitude_pu,
        "最短暂态舍弃时间": minimum_settling_time_s,
        "幅值误差限值": magnitude_error_limit,
        "相位误差限值": phase_error_limit_deg,
        "谐波残差限值": harmonic_residual_limit,
        "电压相量矩阵条件数限值": voltage_matrix_condition_limit,
        "相对积分容差": relative_tolerance,
        "绝对积分容差": absolute_tolerance,
    }
    for label, value in positive_scalars.items():
        if not np.isfinite(value) or value <= 0.0:
            raise AverageDQModelError(f"{label}必须为有限正数。")
    if measurement_periods < 2:
        raise AverageDQModelError("辨识至少需要两个完整测量周期。")
    if samples_per_period < 32:
        raise AverageDQModelError("每周期采样点数不得少于 32。")
    if model.stability is not StabilityStatus.STABLE:
        raise AverageDQModelError("正弦稳态辨识要求闭环平均值模型渐近稳定。")

    device_spectral_abscissa = float(
        np.max(np.linalg.eigvals(model.linearization.device_state_matrix).real)
    )
    references = _references(model.converter)
    equilibrium_state = model.operating_point.state
    base_grid_voltage = model.operating_point.grid_voltage_global
    equilibrium_pcc_voltage = model.operating_point.pcc_voltage_global
    equilibrium_device_current = _device_current_global(equilibrium_state)
    linear_admittances = model.port_admittance(frequencies)
    points: list[PortIdentificationPoint] = []

    for frequency_hz, linear_admittance in zip(
        frequencies, linear_admittances, strict=True
    ):
        period_s = 1.0 / float(frequency_hz)
        settling_periods = max(
            1, int(ceil(minimum_settling_time_s / period_s))
        )
        measurement_start_s = settling_periods * period_s
        sample_count = measurement_periods * samples_per_period
        measurement_times = measurement_start_s + (
            np.arange(sample_count, dtype=np.float64)
            / (float(frequency_hz) * samples_per_period)
        )
        simulation_end_s = float(measurement_times[-1])
        voltage_columns: list[NDArray[np.complex128]] = []
        current_columns: list[NDArray[np.complex128]] = []
        residual_ratios: list[float] = []
        # The 2 Hz trial sits near a lightly damped closed-loop mode and is
        # markedly faster with BDF; the 20 Hz trial is faster with Radau.
        # Both are implicit variable-step solvers using the same tolerances.
        solver_method = "BDF" if frequency_hz <= 5.0 else "Radau"

        for axis in range(2):
            excitation_axis = np.eye(2, dtype=np.float64)[axis]

            def grid_voltage(time_s: float) -> NDArray[np.float64]:
                return base_grid_voltage + source_amplitude_pu * np.cos(
                    2.0 * pi * float(frequency_hz) * time_s
                ) * excitation_axis

            solution = solve_ivp(
                lambda time_s, state: _closed_rhs(
                    state,
                    grid_voltage(time_s),
                    references,
                    model.topology,
                    model.parameters,
                    model.converter,
                    model.line,
                ),
                (0.0, simulation_end_s),
                equilibrium_state,
                t_eval=measurement_times,
                method=solver_method,
                rtol=relative_tolerance,
                atol=absolute_tolerance,
                max_step=min(0.02, period_s / 24.0),
            )
            if not solution.success or solution.y.shape != (
                equilibrium_state.size,
                measurement_times.size,
            ):
                raise AverageDQModelError(
                    f"{frequency_hz:g} Hz、{('d', 'q')[axis]} 轴正弦辨识积分失败："
                    + str(solution.message)
                )
            states = solution.y.T
            pcc_voltage = np.asarray(
                [
                    _closed_pcc_voltage_global(
                        state,
                        grid_voltage(float(time_s)),
                        model.topology,
                        model.parameters,
                        model.line,
                    )
                    for time_s, state in zip(
                        measurement_times, states, strict=True
                    )
                ]
            )
            device_current = np.asarray(
                [_device_current_global(state) for state in states]
            )
            voltage_phasor, voltage_residual = estimate_fundamental_phasor(
                measurement_times,
                pcc_voltage - equilibrium_pcc_voltage,
                float(frequency_hz),
            )
            current_phasor, current_residual = estimate_fundamental_phasor(
                measurement_times,
                device_current - equilibrium_device_current,
                float(frequency_hz),
            )
            voltage_columns.append(voltage_phasor)
            current_columns.append(current_phasor)
            residual_ratios.extend((voltage_residual, current_residual))

        voltage_matrix = np.column_stack(voltage_columns).astype(np.complex128)
        current_matrix = np.column_stack(current_columns).astype(np.complex128)
        voltage_condition = float(np.linalg.cond(voltage_matrix))
        if (
            not np.isfinite(voltage_condition)
            or voltage_condition > voltage_matrix_condition_limit
        ):
            raise AverageDQModelError(
                f"{frequency_hz:g} Hz 的 PCC 电压相量矩阵条件数为 "
                f"{voltage_condition:.6g}，无法可靠反演端口导纳。"
            )
        identified_admittance = np.linalg.solve(
            voltage_matrix.T, current_matrix.T
        ).T
        linear_magnitude = np.abs(linear_admittance)
        if np.any(linear_magnitude <= np.finfo(np.float64).eps):
            raise AverageDQModelError(
                f"{frequency_hz:g} Hz 线性端口导纳含近零元素，"
                "当前逐元素相对误差定义不适用。"
            )
        magnitude_error = (
            np.abs(np.abs(identified_admittance) - linear_magnitude)
            / linear_magnitude
        )
        phase_error = np.abs(
            np.angle(identified_admittance / linear_admittance, deg=True)
        )
        maximum_magnitude_error = float(np.max(magnitude_error))
        maximum_phase_error = float(np.max(phase_error))
        maximum_residual = float(max(residual_ratios))
        point_passed = bool(
            maximum_magnitude_error < magnitude_error_limit
            and maximum_phase_error < phase_error_limit_deg
            and maximum_residual < harmonic_residual_limit
        )
        points.append(
            PortIdentificationPoint(
                frequency_hz=float(frequency_hz),
                settling_periods=settling_periods,
                measurement_periods=measurement_periods,
                samples_per_period=samples_per_period,
                solver_method=solver_method,
                identified_admittance_pu=identified_admittance,
                linearized_admittance_pu=linear_admittance,
                pcc_voltage_phasor_matrix_pu=voltage_matrix,
                device_current_phasor_matrix_pu=current_matrix,
                voltage_matrix_condition_number=voltage_condition,
                magnitude_relative_error=magnitude_error,
                phase_error_deg=phase_error,
                maximum_magnitude_relative_error=maximum_magnitude_error,
                maximum_phase_error_deg=maximum_phase_error,
                maximum_harmonic_residual_ratio=maximum_residual,
                passed=point_passed,
            )
        )

    return PortIdentificationStudy(
        points=tuple(points),
        source_amplitude_pu=source_amplitude_pu,
        minimum_settling_time_s=minimum_settling_time_s,
        magnitude_error_limit=magnitude_error_limit,
        phase_error_limit_deg=phase_error_limit_deg,
        harmonic_residual_limit=harmonic_residual_limit,
        voltage_matrix_condition_limit=voltage_matrix_condition_limit,
        device_open_port_spectral_abscissa_per_s=device_spectral_abscissa,
        passed=all(point.passed for point in points),
    )
