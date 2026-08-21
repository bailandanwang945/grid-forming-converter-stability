"""Equation-level isomorphism audit for the common Sienna/team LCL plant.

The team 16-state model and Sienna PSID Test 08 do not share the same outer
controls or state dimension.  They do, however, retain the same six physical
LCL states when the terminal/PCC voltage is treated as an external input.
This module checks that limited common layer after an explicit coordinate
rotation.  It deliberately excludes the network line, PLL, active damping,
power filters, PI states, and average-modulator dynamics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import cos, pi, sin

import numpy as np
from numpy.typing import ArrayLike, NDArray

from backend.core.average_dq_model import J


COMMON_STATE_LABELS = (
    "converter_current_d_pu",
    "converter_current_q_pu",
    "capacitor_voltage_d_pu",
    "capacitor_voltage_q_pu",
    "grid_current_d_pu",
    "grid_current_q_pu",
)
COMMON_INPUT_LABELS = (
    "converter_voltage_d_pu",
    "converter_voltage_q_pu",
    "pcc_voltage_d_pu",
    "pcc_voltage_q_pu",
)


@dataclass(frozen=True)
class CommonLCLParameters:
    """Common per-unit LCL parameters on the converter device base."""

    frequency_hz: float
    converter_side_resistance_pu: float
    converter_side_reactance_pu: float
    filter_capacitor_susceptance_pu: float
    grid_side_resistance_pu: float
    grid_side_reactance_pu: float
    synchronous_frequency_pu: float = 1.0


def _rotation(angle_rad: float) -> NDArray[np.float64]:
    return np.array(
        [[cos(angle_rad), -sin(angle_rad)], [sin(angle_rad), cos(angle_rad)]],
        dtype=np.float64,
    )


def _finite_vector(value: ArrayLike, length: int, name: str) -> NDArray[np.float64]:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (length,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite length-{length} vector")
    return vector


def _validate_parameters(parameters: CommonLCLParameters) -> None:
    values = np.asarray(list(asdict(parameters).values()), dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("common LCL parameters must be finite")
    if parameters.frequency_hz <= 0.0:
        raise ValueError("common LCL frequency must be positive")
    if (
        parameters.converter_side_reactance_pu <= 0.0
        or parameters.filter_capacitor_susceptance_pu <= 0.0
        or parameters.grid_side_reactance_pu <= 0.0
    ):
        raise ValueError("common LCL reactances and susceptance must be positive")
    if (
        parameters.converter_side_resistance_pu < 0.0
        or parameters.grid_side_resistance_pu < 0.0
    ):
        raise ValueError("common LCL resistances cannot be negative")


def team_lcl_rhs_local(
    state_local_dq: ArrayLike,
    inputs_local_dq: ArrayLike,
    parameters: CommonLCLParameters,
) -> NDArray[np.float64]:
    """Evaluate the LCL block using the team's local-dq vector convention."""

    _validate_parameters(parameters)
    state = _finite_vector(state_local_dq, 6, "team LCL state")
    inputs = _finite_vector(inputs_local_dq, 4, "team LCL inputs")
    converter_current = state[0:2]
    capacitor_voltage = state[2:4]
    grid_current = state[4:6]
    converter_voltage = inputs[0:2]
    pcc_voltage = inputs[2:4]
    omega_base = 2.0 * pi * parameters.frequency_hz
    omega_ratio = parameters.synchronous_frequency_pu

    derivative = np.empty(6, dtype=np.float64)
    derivative[0:2] = (
        omega_base
        / parameters.converter_side_reactance_pu
        * (
            converter_voltage
            - capacitor_voltage
            - parameters.converter_side_resistance_pu * converter_current
        )
        - omega_base * omega_ratio * J @ converter_current
    )
    derivative[2:4] = (
        omega_base
        / parameters.filter_capacitor_susceptance_pu
        * (converter_current - grid_current)
        - omega_base * omega_ratio * J @ capacitor_voltage
    )
    derivative[4:6] = (
        omega_base
        / parameters.grid_side_reactance_pu
        * (
            capacitor_voltage
            - pcc_voltage
            - parameters.grid_side_resistance_pu * grid_current
        )
        - omega_base * omega_ratio * J @ grid_current
    )
    return derivative


def sienna_lcl_rhs_global(
    state_global_ri: ArrayLike,
    inputs_global_ri: ArrayLike,
    parameters: CommonLCLParameters,
) -> NDArray[np.float64]:
    """Evaluate the source-transcribed Sienna LCL component equations."""

    _validate_parameters(parameters)
    state = _finite_vector(state_global_ri, 6, "Sienna LCL state")
    inputs = _finite_vector(inputs_global_ri, 4, "Sienna LCL inputs")
    i_f_r, i_f_i, v_c_r, v_c_i, i_g_r, i_g_i = state
    v_i_r, v_i_i, v_t_r, v_t_i = inputs
    omega_base = 2.0 * pi * parameters.frequency_hz
    omega = parameters.synchronous_frequency_pu
    r_f = parameters.converter_side_resistance_pu
    x_f = parameters.converter_side_reactance_pu
    b_c = parameters.filter_capacitor_susceptance_pu
    r_g = parameters.grid_side_resistance_pu
    x_g = parameters.grid_side_reactance_pu

    return np.array(
        [
            omega_base / x_f * (v_i_r - v_c_r - r_f * i_f_r + x_f * omega * i_f_i),
            omega_base / x_f * (v_i_i - v_c_i - r_f * i_f_i - x_f * omega * i_f_r),
            omega_base / b_c * (i_f_r - i_g_r + b_c * omega * v_c_i),
            omega_base / b_c * (i_f_i - i_g_i - b_c * omega * v_c_r),
            omega_base / x_g * (v_c_r - v_t_r - r_g * i_g_r + x_g * omega * i_g_i),
            omega_base / x_g * (v_c_i - v_t_i - r_g * i_g_i - x_g * omega * i_g_r),
        ],
        dtype=np.float64,
    )


def _linear_matrices(
    rhs,
    parameters: CommonLCLParameters,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    state_matrix = np.column_stack(
        [
            rhs(np.eye(6, dtype=np.float64)[:, index], np.zeros(4), parameters)
            for index in range(6)
        ]
    )
    input_matrix = np.column_stack(
        [
            rhs(np.zeros(6), np.eye(4, dtype=np.float64)[:, index], parameters)
            for index in range(4)
        ]
    )
    return state_matrix, input_matrix


def _comparison_metrics(
    source_parameters: CommonLCLParameters,
    team_parameters: CommonLCLParameters,
    angle_rad: float,
) -> dict[str, float]:
    if not np.isfinite(angle_rad):
        raise ValueError("coordinate alignment angle must be finite")
    team_a, team_b = _linear_matrices(team_lcl_rhs_local, team_parameters)
    source_a, source_b = _linear_matrices(sienna_lcl_rhs_global, source_parameters)
    rotation = _rotation(angle_rad)
    state_transform = np.kron(np.eye(3), rotation)
    input_transform = np.kron(np.eye(2), rotation)
    source_a_local = state_transform.T @ source_a @ state_transform
    source_b_local = state_transform.T @ source_b @ input_transform

    probe_state = np.array([0.41, -0.17, 1.03, 0.08, 0.36, -0.11])
    probe_input = np.array([1.12, -0.06, 0.99, 0.03])
    source_probe_local = state_transform.T @ sienna_lcl_rhs_global(
        state_transform @ probe_state,
        input_transform @ probe_input,
        source_parameters,
    )
    team_probe = team_lcl_rhs_local(probe_state, probe_input, team_parameters)
    return {
        "state_matrix_max_abs_difference_per_s": float(
            np.max(np.abs(team_a - source_a_local))
        ),
        "input_matrix_max_abs_difference_per_s": float(
            np.max(np.abs(team_b - source_b_local))
        ),
        "probe_rhs_max_abs_difference_per_s": float(
            np.max(np.abs(team_probe - source_probe_local))
        ),
    }


def sienna_team_common_lcl_audit(
    source_parameters: CommonLCLParameters,
    team_parameters: CommonLCLParameters,
    *,
    angle_rad: float,
    network_reactance_pu_system_base: float,
    system_base_power_mva: float,
    device_base_power_mva: float,
) -> dict[str, object]:
    """Return a bounded common-layer audit plus one deliberate mismatch test."""

    if (
        not np.isfinite(network_reactance_pu_system_base)
        or network_reactance_pu_system_base < 0.0
        or not np.isfinite(system_base_power_mva)
        or system_base_power_mva <= 0.0
        or not np.isfinite(device_base_power_mva)
        or device_base_power_mva <= 0.0
    ):
        raise ValueError("network/base quantities must be finite and physically valid")
    metrics = _comparison_metrics(source_parameters, team_parameters, angle_rad)
    counterfactual_team = replace(
        team_parameters,
        grid_side_reactance_pu=team_parameters.grid_side_reactance_pu * 1.01,
    )
    counterfactual = _comparison_metrics(
        source_parameters, counterfactual_team, angle_rad
    )
    tolerance = 1.0e-10
    counterfactual_minimum = 1.0
    passed = (
        max(metrics.values()) <= tolerance
        and counterfactual["state_matrix_max_abs_difference_per_s"]
        >= counterfactual_minimum
    )
    network_reactance_device_base = (
        network_reactance_pu_system_base
        * device_base_power_mva
        / system_base_power_mva
    )
    return {
        "schema_version": "gfm-sienna-team-common-lcl-audit/1.0",
        "status": "passed" if passed else "failed",
        "common_layer": {
            "state_count": 6,
            "state_labels": list(COMMON_STATE_LABELS),
            "input_count": 4,
            "input_labels": list(COMMON_INPUT_LABELS),
            "terminal_definition": "PCC voltage treated as an external input",
            "source_coordinates": "Sienna synchronous global real-imaginary frame",
            "team_coordinates": "team converter-local dq frame",
            "alignment_angle_rad": angle_rad,
        },
        "parameters": {
            "source": asdict(source_parameters),
            "team_intermediate_case": asdict(team_parameters),
        },
        "verification_gates": {
            "matrix_and_rhs_max_abs_difference_per_s": tolerance,
            "counterfactual_state_matrix_difference_min_per_s": (
                counterfactual_minimum
            ),
        },
        "results": {
            **metrics,
            "counterfactual": {
                "change": "team grid-side filter reactance multiplied by 1.01",
                **counterfactual,
            },
        },
        "network_interface": {
            "network_reactance_pu_system_base": network_reactance_pu_system_base,
            "network_reactance_pu_device_base": network_reactance_device_base,
            "included_in_common_lcl_gate": False,
            "reason": (
                "Sienna Test 08 represents the external network algebraically, "
                "whereas the team model retains an external RL line in the current "
                "differential equation. The common gate therefore stops at the PCC."
            ),
        },
        "scope": {
            "common_lcl_equations_isomorphic": passed,
            "full_state_dimensions_equal": False,
            "outer_controls_compared": False,
            "pll_or_active_damping_compared": False,
            "external_network_dynamics_compared": False,
            "full_model_eigenvalues_comparable_from_this_gate": False,
            "statement": (
                "Only the six-state LCL plant up to the PCC is shown equivalent "
                "after coordinate rotation. This is the first equation-level gate "
                "of an intermediate isomorphic case, not full-model validation."
            ),
        },
    }
