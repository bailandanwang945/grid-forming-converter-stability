"""Common VSM/Q-V outer-loop closure for the Sienna/team comparison.

The original implementations do not measure power at the same electrical
port.  This module therefore preserves both baselines and constructs two
explicitly labelled thirteen-state intermediate cases: both sides measure at
the filter-capacitor port, or both sides measure at the PCC.  The team active-
power measurement and modulation delays are taken in their declared ideal
limits; Sienna PLL damping is disabled.  Neither intermediate case is an
original complete model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import cos, pi, sin

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import root

from backend.core.average_dq_model import J
from backend.core.sienna_team_common_inner_loop import (
    CommonInnerLoopParameters,
)
from backend.core.sienna_team_lcl_isomorphism import (
    CommonLCLParameters,
    sienna_lcl_rhs_global,
    team_lcl_rhs_local,
)


POWER_PORTS = ("filter_capacitor", "pcc")
TEAM_STATE_LABELS = (
    "angle_rad",
    "frequency_pu",
    "measured_reactive_power_pu",
    "voltage_integral_output_d_pu",
    "voltage_integral_output_q_pu",
    "current_integral_output_d_pu",
    "current_integral_output_q_pu",
    "converter_current_d_pu",
    "converter_current_q_pu",
    "capacitor_voltage_d_pu",
    "capacitor_voltage_q_pu",
    "grid_current_d_pu",
    "grid_current_q_pu",
)
SOURCE_STATE_LABELS = (
    "theta_outer_rad",
    "omega_outer_pu",
    "measured_reactive_power_pu",
    "voltage_error_integral_d",
    "voltage_error_integral_q",
    "current_error_integral_d",
    "current_error_integral_q",
    "converter_current_real_pu",
    "converter_current_imag_pu",
    "capacitor_voltage_real_pu",
    "capacitor_voltage_imag_pu",
    "grid_current_real_pu",
    "grid_current_imag_pu",
)


@dataclass(frozen=True)
class CommonOuterLoopParameters:
    inner: CommonInnerLoopParameters
    inertia_time_constant_s: float
    frequency_droop_gain: float
    reactive_power_droop_gain: float
    reactive_power_filter_cutoff_rad_s: float
    active_power_reference_pu: float
    reactive_power_reference_pu: float
    voltage_reference_pu: float
    system_frequency_pu: float = 1.0
    frequency_reference_pu: float = 1.0


def frozen_common_outer_loop_parameters() -> CommonOuterLoopParameters:
    """Return the fixed Test 08 values mapped to the common outer loop."""

    from backend.core.sienna_test08_reference import SiennaTest08Parameters

    source = SiennaTest08Parameters()
    inner = CommonInnerLoopParameters(
        frequency_hz=source.frequency_hz,
        voltage_kp=source.voltage_kp,
        voltage_ki_per_s=source.voltage_ki,
        current_kp=source.current_kp,
        current_ki_per_s=source.current_ki,
        converter_side_resistance_pu=source.converter_side_resistance_pu,
        converter_side_reactance_pu=source.converter_side_reactance_pu,
        filter_capacitor_susceptance_pu=(
            source.filter_capacitor_susceptance_pu
        ),
        grid_side_resistance_pu=source.grid_side_resistance_pu,
        grid_side_reactance_pu=source.grid_side_reactance_pu,
        virtual_resistance_pu=source.virtual_resistance_pu,
        virtual_reactance_pu=source.virtual_reactance_pu,
        resistive_drop_feedforward_gain=0.0,
        synchronous_frequency_pu=source.system_frequency_pu,
    )
    return CommonOuterLoopParameters(
        inner=inner,
        inertia_time_constant_s=source.inertia_time_constant_s,
        frequency_droop_gain=source.frequency_droop_gain,
        reactive_power_droop_gain=source.reactive_power_droop_gain,
        reactive_power_filter_cutoff_rad_s=(
            source.reactive_power_filter_cutoff_rad_s
        ),
        active_power_reference_pu=source.active_power_reference_pu,
        reactive_power_reference_pu=source.reactive_power_reference_pu,
        voltage_reference_pu=source.voltage_reference_pu,
        system_frequency_pu=source.system_frequency_pu,
        frequency_reference_pu=source.frequency_reference_pu,
    )


def _rotation(angle_rad: float) -> NDArray[np.float64]:
    return np.array(
        [[cos(angle_rad), -sin(angle_rad)], [sin(angle_rad), cos(angle_rad)]],
        dtype=np.float64,
    )


def _validate(parameters: CommonOuterLoopParameters, power_port: str) -> None:
    if power_port not in POWER_PORTS:
        raise ValueError(f"power_port must be one of {POWER_PORTS}")
    scalar_values = np.asarray(
        [
            parameters.inertia_time_constant_s,
            parameters.frequency_droop_gain,
            parameters.reactive_power_droop_gain,
            parameters.reactive_power_filter_cutoff_rad_s,
            parameters.active_power_reference_pu,
            parameters.reactive_power_reference_pu,
            parameters.voltage_reference_pu,
            parameters.system_frequency_pu,
            parameters.frequency_reference_pu,
        ],
        dtype=np.float64,
    )
    inner_values = np.asarray(list(asdict(parameters.inner).values()), dtype=np.float64)
    if not np.all(np.isfinite(scalar_values)) or not np.all(np.isfinite(inner_values)):
        raise ValueError("common outer-loop parameters must be finite")
    if parameters.inertia_time_constant_s <= 0.0:
        raise ValueError("inertia time constant must be positive")
    if parameters.reactive_power_filter_cutoff_rad_s <= 0.0:
        raise ValueError("reactive-power filter cutoff must be positive")
    if parameters.inner.active_damping_gain != 0.0:
        raise ValueError("the thirteen-state outer-loop gate excludes active damping")


def _finite_vector(value: ArrayLike, length: int, name: str) -> NDArray[np.float64]:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (length,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite length-{length} vector")
    return vector


def _lcl_parameters(
    inner: CommonInnerLoopParameters, frequency_pu: float
) -> CommonLCLParameters:
    return CommonLCLParameters(
        frequency_hz=inner.frequency_hz,
        converter_side_resistance_pu=inner.converter_side_resistance_pu,
        converter_side_reactance_pu=inner.converter_side_reactance_pu,
        filter_capacitor_susceptance_pu=inner.filter_capacitor_susceptance_pu,
        grid_side_resistance_pu=inner.grid_side_resistance_pu,
        grid_side_reactance_pu=inner.grid_side_reactance_pu,
        synchronous_frequency_pu=frequency_pu,
    )


def _power(
    capacitor_voltage: NDArray[np.float64],
    pcc_voltage: NDArray[np.float64],
    grid_current: NDArray[np.float64],
    power_port: str,
) -> tuple[float, float]:
    voltage = capacitor_voltage if power_port == "filter_capacitor" else pcc_voltage
    return float(voltage @ grid_current), float(voltage @ J @ grid_current)


def _control_signals(
    voltage_integral_output: NDArray[np.float64],
    current_integral_output: NDArray[np.float64],
    lcl_local: NDArray[np.float64],
    voltage_reference_magnitude: float,
    frequency_pu: float,
    inner: CommonInnerLoopParameters,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    converter_current = lcl_local[0:2]
    capacitor_voltage = lcl_local[2:4]
    grid_current = lcl_local[4:6]
    voltage_reference = np.array([voltage_reference_magnitude, 0.0])
    compensated_voltage_reference = (
        voltage_reference
        - inner.virtual_resistance_pu * grid_current
        - inner.virtual_reactance_pu * frequency_pu * J @ grid_current
    )
    voltage_error = compensated_voltage_reference - capacitor_voltage
    converter_current_reference = (
        inner.current_feedforward_gain * grid_current
        + inner.filter_capacitor_susceptance_pu
        * frequency_pu
        * J
        @ capacitor_voltage
        + inner.voltage_kp * voltage_error
        + voltage_integral_output
    )
    current_error = converter_current_reference - converter_current
    converter_voltage_reference = (
        inner.voltage_feedforward_gain * capacitor_voltage
        + inner.resistive_drop_feedforward_gain
        * inner.converter_side_resistance_pu
        * converter_current
        + inner.converter_side_reactance_pu
        * frequency_pu
        * J
        @ converter_current
        + inner.current_kp * current_error
        + current_integral_output
    )
    return voltage_error, current_error, converter_voltage_reference


def team_common_outer_loop_rhs(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
) -> NDArray[np.float64]:
    """Evaluate the thirteen-state common model in the moving team frame."""

    _validate(parameters, power_port)
    state = _finite_vector(state_team, 13, "team outer-loop state")
    pcc_global = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    theta, frequency_pu, measured_q = state[0:3]
    voltage_integral_output = state[3:5]
    current_integral_output = state[5:7]
    lcl_local = state[7:13]
    pcc_local = _rotation(-theta) @ pcc_global
    active_power, reactive_power = _power(
        lcl_local[2:4], pcc_local, lcl_local[4:6], power_port
    )
    voltage_reference = parameters.voltage_reference_pu + (
        parameters.reactive_power_droop_gain
        * (parameters.reactive_power_reference_pu - measured_q)
    )
    voltage_error, current_error, converter_voltage_reference = _control_signals(
        voltage_integral_output,
        current_integral_output,
        lcl_local,
        voltage_reference,
        frequency_pu,
        parameters.inner,
    )
    omega_base = 2.0 * pi * parameters.inner.frequency_hz
    derivative = np.empty(13, dtype=np.float64)
    derivative[0] = omega_base * (frequency_pu - parameters.system_frequency_pu)
    derivative[1] = (
        parameters.active_power_reference_pu
        - active_power
        - parameters.frequency_droop_gain
        * (frequency_pu - parameters.frequency_reference_pu)
    ) / parameters.inertia_time_constant_s
    derivative[2] = parameters.reactive_power_filter_cutoff_rad_s * (
        reactive_power - measured_q
    )
    derivative[3:5] = parameters.inner.voltage_ki_per_s * voltage_error
    derivative[5:7] = parameters.inner.current_ki_per_s * current_error
    derivative[7:13] = team_lcl_rhs_local(
        lcl_local,
        np.concatenate((converter_voltage_reference, pcc_local)),
        _lcl_parameters(parameters.inner, frequency_pu),
    )
    return derivative


def _team_to_source_state(
    state_team: NDArray[np.float64], parameters: CommonOuterLoopParameters
) -> NDArray[np.float64]:
    theta = float(state_team[0])
    source = np.empty(13, dtype=np.float64)
    source[0:3] = state_team[0:3]
    source[3:5] = state_team[3:5] / parameters.inner.voltage_ki_per_s
    source[5:7] = state_team[5:7] / parameters.inner.current_ki_per_s
    rotation = _rotation(theta)
    source[7:13] = np.kron(np.eye(3), rotation) @ state_team[7:13]
    return source


def _source_rhs(
    state_source: NDArray[np.float64],
    pcc_global: NDArray[np.float64],
    parameters: CommonOuterLoopParameters,
    power_port: str,
) -> NDArray[np.float64]:
    theta, frequency_pu, measured_q = state_source[0:3]
    rotation = _rotation(theta)
    lcl_global = state_source[7:13]
    lcl_local = np.kron(np.eye(3), rotation.T) @ lcl_global
    active_power, reactive_power = _power(
        lcl_global[2:4], pcc_global, lcl_global[4:6], power_port
    )
    voltage_reference = parameters.voltage_reference_pu + (
        parameters.reactive_power_droop_gain
        * (parameters.reactive_power_reference_pu - measured_q)
    )
    voltage_error, current_error, converter_voltage_reference_local = (
        _control_signals(
            parameters.inner.voltage_ki_per_s * state_source[3:5],
            parameters.inner.current_ki_per_s * state_source[5:7],
            lcl_local,
            voltage_reference,
            frequency_pu,
            parameters.inner,
        )
    )
    omega_base = 2.0 * pi * parameters.inner.frequency_hz
    derivative = np.empty(13, dtype=np.float64)
    derivative[0] = omega_base * (frequency_pu - parameters.system_frequency_pu)
    derivative[1] = (
        parameters.active_power_reference_pu
        - active_power
        - parameters.frequency_droop_gain
        * (frequency_pu - parameters.frequency_reference_pu)
    ) / parameters.inertia_time_constant_s
    derivative[2] = parameters.reactive_power_filter_cutoff_rad_s * (
        reactive_power - measured_q
    )
    derivative[3:5] = voltage_error
    derivative[5:7] = current_error
    converter_voltage_global = rotation @ converter_voltage_reference_local
    derivative[7:13] = sienna_lcl_rhs_global(
        lcl_global,
        np.concatenate((converter_voltage_global, pcc_global)),
        _lcl_parameters(parameters.inner, parameters.system_frequency_pu),
    )
    return derivative


def source_common_outer_loop_rhs_in_team_coordinates(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
) -> NDArray[np.float64]:
    """Evaluate the source equations and transform their derivative to team coordinates."""

    _validate(parameters, power_port)
    team = _finite_vector(state_team, 13, "team outer-loop state")
    pcc_global = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    source = _team_to_source_state(team, parameters)
    source_derivative = _source_rhs(source, pcc_global, parameters, power_port)
    theta = float(team[0])
    theta_derivative = float(source_derivative[0])
    rotation_transpose = _rotation(theta).T
    team_derivative = np.empty(13, dtype=np.float64)
    team_derivative[0:3] = source_derivative[0:3]
    team_derivative[3:5] = (
        parameters.inner.voltage_ki_per_s * source_derivative[3:5]
    )
    team_derivative[5:7] = (
        parameters.inner.current_ki_per_s * source_derivative[5:7]
    )
    for offset in (7, 9, 11):
        local_state = team[offset : offset + 2]
        team_derivative[offset : offset + 2] = (
            rotation_transpose @ source_derivative[offset : offset + 2]
            - theta_derivative * J @ local_state
        )
    return team_derivative


def _initial_guess(parameters: CommonOuterLoopParameters) -> NDArray[np.float64]:
    from backend.core.sienna_test08_reference import FROZEN_INITIAL_STATE

    source = FROZEN_INITIAL_STATE
    theta = float(source[0])
    guess = np.empty(13, dtype=np.float64)
    guess[0:3] = source[0:3]
    guess[3:5] = parameters.inner.voltage_ki_per_s * source[3:5]
    guess[5:7] = parameters.inner.current_ki_per_s * source[5:7]
    guess[7:13] = (
        np.kron(np.eye(3), _rotation(theta).T) @ source[13:19]
    )
    return guess


def solve_common_outer_loop_equilibrium(
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
    pcc_voltage_global: ArrayLike = (1.0, 0.0),
) -> NDArray[np.float64]:
    """Solve the loaded equilibrium of a fixed common-port intermediate case."""

    _validate(parameters, power_port)
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    solution = root(
        lambda state: team_common_outer_loop_rhs(
            state, pcc, parameters, power_port=power_port
        ),
        _initial_guess(parameters),
        method="hybr",
        options={"xtol": 1.0e-11, "maxfev": 5000},
    )
    residual = team_common_outer_loop_rhs(
        solution.x, pcc, parameters, power_port=power_port
    )
    if not solution.success or float(np.linalg.norm(residual, ord=np.inf)) > 1.0e-8:
        raise RuntimeError(
            f"common outer-loop equilibrium failed for {power_port}: "
            f"{solution.message}; residual={np.linalg.norm(residual, ord=np.inf):.3e}"
        )
    return np.asarray(solution.x, dtype=np.float64)


def _jacobian(rhs, state: NDArray[np.float64]) -> NDArray[np.float64]:
    columns: list[NDArray[np.float64]] = []
    for index in range(state.size):
        step = 1.0e-6 * max(abs(float(state[index])), 1.0)
        plus = state.copy()
        minus = state.copy()
        plus[index] += step
        minus[index] -= step
        columns.append((rhs(plus) - rhs(minus)) / (2.0 * step))
    return np.column_stack(columns)


def run_common_outer_loop_audit() -> dict[str, object]:
    """Recompute both common power-port conventions and a mixed-port counterexample."""

    base = frozen_common_outer_loop_parameters()
    pcc = np.array([1.0, 0.0], dtype=np.float64)
    variants: dict[str, object] = {}
    for power_port in POWER_PORTS:
        equilibrium = solve_common_outer_loop_equilibrium(
            base, power_port=power_port, pcc_voltage_global=pcc
        )
        def team_rhs(state: NDArray[np.float64]) -> NDArray[np.float64]:
            return team_common_outer_loop_rhs(
                state, pcc, base, power_port=power_port
            )

        def source_rhs(state: NDArray[np.float64]) -> NDArray[np.float64]:
            return source_common_outer_loop_rhs_in_team_coordinates(
                state, pcc, base, power_port=power_port
            )
        team_matrix = _jacobian(team_rhs, equilibrium)
        source_matrix = _jacobian(source_rhs, equilibrium)
        eigenvalues = np.linalg.eigvals(team_matrix)
        positive_modes = sorted(
            (complex(value) for value in eigenvalues if value.imag > 1.0e-8),
            key=lambda value: value.imag,
        )
        variants[power_port] = {
            "equilibrium_residual_inf": float(
                np.linalg.norm(team_rhs(equilibrium), ord=np.inf)
            ),
            "rhs_difference_inf": float(
                np.linalg.norm(team_rhs(equilibrium) - source_rhs(equilibrium), ord=np.inf)
            ),
            "state_matrix_max_abs_difference_per_s": float(
                np.max(np.abs(team_matrix - source_matrix))
            ),
            "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
            "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
            "oscillatory_modes": [
                {
                    "real_per_s": float(value.real),
                    "imag_per_s": float(value.imag),
                    "frequency_hz": float(value.imag / (2.0 * pi)),
                }
                for value in positive_modes
            ],
            "equilibrium": {
                label: float(value)
                for label, value in zip(TEAM_STATE_LABELS, equilibrium, strict=True)
            },
        }

    equilibrium = solve_common_outer_loop_equilibrium(
        base, power_port="filter_capacitor", pcc_voltage_global=pcc
    )
    matched_matrix = _jacobian(
        lambda state: team_common_outer_loop_rhs(
            state, pcc, base, power_port="filter_capacitor"
        ),
        equilibrium,
    )
    mixed_matrix = _jacobian(
        lambda state: source_common_outer_loop_rhs_in_team_coordinates(
            state, pcc, base, power_port="pcc"
        ),
        equilibrium,
    )
    mixed_difference = float(np.max(np.abs(matched_matrix - mixed_matrix)))
    gate = 1.0e-5
    counterexample_minimum = 1.0
    passed = all(
        variant["equilibrium_residual_inf"] <= 1.0e-8
        and variant["rhs_difference_inf"] <= gate
        and variant["state_matrix_max_abs_difference_per_s"] <= gate
        for variant in variants.values()
    ) and mixed_difference >= counterexample_minimum
    return {
        "schema_version": "gfm-sienna-team-common-outer-loop/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "state_count": 13,
            "team_state_labels": list(TEAM_STATE_LABELS),
            "source_state_labels": list(SOURCE_STATE_LABELS),
            "pcc_voltage_global_pu": pcc.tolist(),
            "ideal_limits": {
                "team_active_power_measurement_delay_s": 0.0,
                "team_modulation_delay_s": 0.0,
                "sienna_pll_damping_gain": 0.0,
            },
            "parameter_mapping": {
                "team_virtual_inertia_s": "Sienna Ta",
                "team_damping_coefficient_pu": "Sienna komega",
                "team_reactive_measurement_time_s": "1 / Sienna omega_f",
            },
        },
        "verification_gates": {
            "equilibrium_residual_inf_max": 1.0e-8,
            "rhs_and_matrix_difference_max_per_s": gate,
            "mixed_power_port_difference_min_per_s": counterexample_minimum,
        },
        "variants": variants,
        "counterexample": {
            "change": (
                "team uses filter-capacitor power while the transformed source "
                "uses PCC power at the same loaded equilibrium"
            ),
            "state_matrix_max_abs_difference_per_s": mixed_difference,
            "gate_rejected_mismatch": mixed_difference >= counterexample_minimum,
        },
        "scope": {
            "source_baselines_modified": False,
            "team_original_model_modified": False,
            "common_intermediate_cases_only": True,
            "loaded_equilibrium": True,
            "power_measurement_port_originally_identical": False,
            "active_power_measurement_dynamics_compared": False,
            "modulation_dynamics_compared": False,
            "pll_damping_compared": False,
            "active_damping_compared": False,
            "external_network_dynamics_compared": False,
            "statement": (
                "The two thirteen-state cases close the common VSM, Q-V and "
                "inner-loop equations under separately declared shared power "
                "ports. They are not either original full model. A mixed power "
                "port is a rejected structural mismatch, not a parameter error."
            ),
        },
    }
