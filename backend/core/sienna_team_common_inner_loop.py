"""Two-path isomorphic intermediate cases for the common cascaded inner loop.

The source baselines remain unchanged.  This module builds two explicitly
labelled ten-state intermediate cases: both sides omit converter-resistance
feed-forward, or both sides include it.  Each case combines four cascaded PI
states with the six-state LCL plant and treats voltage reference plus PCC
voltage as external inputs.  Outer controls, PLL, active damping, modulation,
limits, and external-network dynamics remain outside the comparison.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import cos, pi, sin

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import linear_sum_assignment

from backend.core.average_dq_model import J
from backend.core.sienna_team_lcl_isomorphism import (
    CommonLCLParameters,
    sienna_lcl_rhs_global,
    team_lcl_rhs_local,
)


TEAM_STATE_LABELS = (
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
INPUT_LABELS = (
    "voltage_reference_d_pu",
    "voltage_reference_q_pu",
    "pcc_voltage_d_pu",
    "pcc_voltage_q_pu",
)


@dataclass(frozen=True)
class CommonInnerLoopParameters:
    frequency_hz: float
    voltage_kp: float
    voltage_ki_per_s: float
    current_kp: float
    current_ki_per_s: float
    converter_side_resistance_pu: float
    converter_side_reactance_pu: float
    filter_capacitor_susceptance_pu: float
    grid_side_resistance_pu: float
    grid_side_reactance_pu: float
    virtual_resistance_pu: float
    virtual_reactance_pu: float
    resistive_drop_feedforward_gain: float
    synchronous_frequency_pu: float = 1.0
    current_feedforward_gain: float = 1.0
    voltage_feedforward_gain: float = 1.0
    active_damping_gain: float = 0.0


def _validate(parameters: CommonInnerLoopParameters) -> None:
    values = np.asarray(list(asdict(parameters).values()), dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("common inner-loop parameters must be finite")
    if parameters.frequency_hz <= 0.0:
        raise ValueError("frequency must be positive")
    if parameters.voltage_ki_per_s <= 0.0 or parameters.current_ki_per_s <= 0.0:
        raise ValueError("PI integral gains must be positive")
    if (
        parameters.converter_side_reactance_pu <= 0.0
        or parameters.filter_capacitor_susceptance_pu <= 0.0
        or parameters.grid_side_reactance_pu <= 0.0
    ):
        raise ValueError("LCL reactances and susceptance must be positive")
    if (
        parameters.converter_side_resistance_pu < 0.0
        or parameters.grid_side_resistance_pu < 0.0
        or parameters.virtual_resistance_pu < 0.0
    ):
        raise ValueError("physical resistances cannot be negative")
    if parameters.active_damping_gain != 0.0:
        raise ValueError("common intermediate loop requires active damping disabled")


def _finite_vector(value: ArrayLike, length: int, name: str) -> NDArray[np.float64]:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (length,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite length-{length} vector")
    return vector


def _rotation(angle_rad: float) -> NDArray[np.float64]:
    return np.array(
        [[cos(angle_rad), -sin(angle_rad)], [sin(angle_rad), cos(angle_rad)]],
        dtype=np.float64,
    )


def _lcl_parameters(parameters: CommonInnerLoopParameters) -> CommonLCLParameters:
    return CommonLCLParameters(
        frequency_hz=parameters.frequency_hz,
        converter_side_resistance_pu=parameters.converter_side_resistance_pu,
        converter_side_reactance_pu=parameters.converter_side_reactance_pu,
        filter_capacitor_susceptance_pu=parameters.filter_capacitor_susceptance_pu,
        grid_side_resistance_pu=parameters.grid_side_resistance_pu,
        grid_side_reactance_pu=parameters.grid_side_reactance_pu,
        synchronous_frequency_pu=parameters.synchronous_frequency_pu,
    )


def _control_signals(
    voltage_integral_output: NDArray[np.float64],
    current_integral_output: NDArray[np.float64],
    lcl_local: NDArray[np.float64],
    inputs_local: NDArray[np.float64],
    parameters: CommonInnerLoopParameters,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
]:
    converter_current = lcl_local[0:2]
    capacitor_voltage = lcl_local[2:4]
    grid_current = lcl_local[4:6]
    voltage_reference = inputs_local[0:2]
    omega = parameters.synchronous_frequency_pu

    compensated_voltage_reference = (
        voltage_reference
        - parameters.virtual_resistance_pu * grid_current
        - parameters.virtual_reactance_pu * omega * J @ grid_current
    )
    voltage_error = compensated_voltage_reference - capacitor_voltage
    converter_current_reference = (
        parameters.current_feedforward_gain * grid_current
        + parameters.filter_capacitor_susceptance_pu
        * omega
        * J
        @ capacitor_voltage
        + parameters.voltage_kp * voltage_error
        + voltage_integral_output
    )
    current_error = converter_current_reference - converter_current
    converter_voltage_reference = (
        parameters.voltage_feedforward_gain * capacitor_voltage
        + parameters.resistive_drop_feedforward_gain
        * parameters.converter_side_resistance_pu
        * converter_current
        + parameters.converter_side_reactance_pu
        * omega
        * J
        @ converter_current
        + parameters.current_kp * current_error
        + current_integral_output
    )
    return voltage_error, current_error, converter_voltage_reference


def team_common_inner_loop_rhs(
    state_team: ArrayLike,
    inputs_local: ArrayLike,
    parameters: CommonInnerLoopParameters,
) -> NDArray[np.float64]:
    """Evaluate the team-coordinate ten-state common intermediate loop."""

    _validate(parameters)
    state = _finite_vector(state_team, 10, "team inner-loop state")
    inputs = _finite_vector(inputs_local, 4, "common inner-loop inputs")
    voltage_integral_output = state[0:2]
    current_integral_output = state[2:4]
    lcl_local = state[4:10]
    voltage_error, current_error, converter_voltage_reference = _control_signals(
        voltage_integral_output,
        current_integral_output,
        lcl_local,
        inputs,
        parameters,
    )
    derivative = np.empty(10, dtype=np.float64)
    derivative[0:2] = parameters.voltage_ki_per_s * voltage_error
    derivative[2:4] = parameters.current_ki_per_s * current_error
    derivative[4:10] = team_lcl_rhs_local(
        lcl_local,
        np.concatenate((converter_voltage_reference, inputs[2:4])),
        _lcl_parameters(parameters),
    )
    return derivative


def sienna_common_inner_loop_rhs(
    state_source: ArrayLike,
    inputs_local: ArrayLike,
    parameters: CommonInnerLoopParameters,
    *,
    angle_rad: float,
) -> NDArray[np.float64]:
    """Evaluate the source-coordinate ten-state common intermediate loop."""

    _validate(parameters)
    if not np.isfinite(angle_rad):
        raise ValueError("alignment angle must be finite")
    state = _finite_vector(state_source, 10, "source inner-loop state")
    inputs = _finite_vector(inputs_local, 4, "common inner-loop inputs")
    raw_voltage_integral = state[0:2]
    raw_current_integral = state[2:4]
    lcl_global = state[4:10]
    rotation = _rotation(angle_rad)
    lcl_transform = np.kron(np.eye(3), rotation)
    lcl_local = lcl_transform.T @ lcl_global
    voltage_error, current_error, converter_voltage_reference_local = (
        _control_signals(
            parameters.voltage_ki_per_s * raw_voltage_integral,
            parameters.current_ki_per_s * raw_current_integral,
            lcl_local,
            inputs,
            parameters,
        )
    )
    converter_voltage_global = rotation @ converter_voltage_reference_local
    pcc_voltage_global = rotation @ inputs[2:4]
    derivative = np.empty(10, dtype=np.float64)
    derivative[0:2] = voltage_error
    derivative[2:4] = current_error
    derivative[4:10] = sienna_lcl_rhs_global(
        lcl_global,
        np.concatenate((converter_voltage_global, pcc_voltage_global)),
        _lcl_parameters(parameters),
    )
    return derivative


def _linear_matrices(rhs) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    state_matrix = np.column_stack(
        [rhs(np.eye(10)[:, index], np.zeros(4)) for index in range(10)]
    )
    input_matrix = np.column_stack(
        [rhs(np.zeros(10), np.eye(4)[:, index]) for index in range(4)]
    )
    return state_matrix, input_matrix


def _state_transform(
    parameters: CommonInnerLoopParameters, angle_rad: float
) -> NDArray[np.float64]:
    rotation = _rotation(angle_rad)
    transform = np.zeros((10, 10), dtype=np.float64)
    transform[0:2, 0:2] = parameters.voltage_ki_per_s * np.eye(2)
    transform[2:4, 2:4] = parameters.current_ki_per_s * np.eye(2)
    transform[4:10, 4:10] = np.kron(np.eye(3), rotation.T)
    return transform


def _variant_audit(
    source_parameters: CommonInnerLoopParameters,
    team_parameters: CommonInnerLoopParameters,
    angle_rad: float,
) -> dict[str, object]:
    source_a, source_b = _linear_matrices(
        lambda state, inputs: sienna_common_inner_loop_rhs(
            state, inputs, source_parameters, angle_rad=angle_rad
        )
    )
    team_a, team_b = _linear_matrices(
        lambda state, inputs: team_common_inner_loop_rhs(
            state, inputs, team_parameters
        )
    )
    transform = _state_transform(source_parameters, angle_rad)
    source_a_team = transform @ source_a @ np.linalg.inv(transform)
    source_b_team = transform @ source_b
    matrix_difference = float(np.max(np.abs(team_a - source_a_team)))
    input_difference = float(np.max(np.abs(team_b - source_b_team)))

    team_probe_state = np.array(
        [0.12, -0.04, 0.18, -0.07, 0.41, -0.15, 1.02, 0.06, 0.36, -0.08]
    )
    probe_input = np.array([1.01, 0.02, 0.98, -0.03])
    source_probe_state = np.linalg.solve(transform, team_probe_state)
    source_probe_team = transform @ sienna_common_inner_loop_rhs(
        source_probe_state, probe_input, source_parameters, angle_rad=angle_rad
    )
    team_probe = team_common_inner_loop_rhs(
        team_probe_state, probe_input, team_parameters
    )
    probe_difference = float(np.max(np.abs(team_probe - source_probe_team)))
    eigenvalues = np.linalg.eigvals(team_a)
    tolerance = 1.0e-10
    return {
        "status": "passed"
        if max(matrix_difference, input_difference, probe_difference) <= tolerance
        else "failed",
        "resistive_drop_feedforward_gain": (
            team_parameters.resistive_drop_feedforward_gain
        ),
        "state_matrix_max_abs_difference_per_s": matrix_difference,
        "input_matrix_max_abs_difference_per_s": input_difference,
        "probe_rhs_max_abs_difference_per_s": probe_difference,
        "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
        "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
        "eigenvalues": [
            {
                "real_per_s": float(value.real),
                "imag_per_s": float(value.imag),
                "oscillation_frequency_hz": float(abs(value.imag) / (2.0 * pi)),
            }
            for value in sorted(eigenvalues, key=lambda item: (item.real, item.imag))
        ],
    }


def sienna_team_common_inner_loop_audit(
    base_parameters: CommonInnerLoopParameters,
    *,
    angle_rad: float,
) -> dict[str, object]:
    """Return both reversible structural variants and their spectral difference."""

    _validate(base_parameters)
    omit_parameters = replace(
        base_parameters, resistive_drop_feedforward_gain=0.0
    )
    include_parameters = replace(
        base_parameters, resistive_drop_feedforward_gain=1.0
    )
    omit = _variant_audit(omit_parameters, omit_parameters, angle_rad)
    include = _variant_audit(include_parameters, include_parameters, angle_rad)
    counterfactual = _variant_audit(
        replace(omit_parameters, current_feedforward_gain=0.99),
        omit_parameters,
        angle_rad,
    )
    omit_eigenvalues = np.array(
        [complex(row["real_per_s"], row["imag_per_s"]) for row in omit["eigenvalues"]]
    )
    include_eigenvalues = np.array(
        [
            complex(row["real_per_s"], row["imag_per_s"])
            for row in include["eigenvalues"]
        ]
    )
    cost = np.abs(omit_eigenvalues[:, None] - include_eigenvalues[None, :])
    rows, columns = linear_sum_assignment(cost)
    matched_displacement = cost[rows, columns]
    tolerance = 1.0e-10
    counterfactual_minimum = 1.0
    passed = (
        omit["status"] == "passed"
        and include["status"] == "passed"
        and counterfactual["state_matrix_max_abs_difference_per_s"]
        >= counterfactual_minimum
    )
    return {
        "schema_version": "gfm-sienna-team-common-inner-loop-audit/1.0",
        "status": "passed" if passed else "failed",
        "common_model": {
            "state_count": 10,
            "source_state_labels": list(SOURCE_STATE_LABELS),
            "team_state_labels": list(TEAM_STATE_LABELS),
            "input_count": 4,
            "input_labels": list(INPUT_LABELS),
            "alignment_angle_rad": angle_rad,
            "current_feedforward_gain": base_parameters.current_feedforward_gain,
            "voltage_feedforward_gain": base_parameters.voltage_feedforward_gain,
            "active_damping_gain": base_parameters.active_damping_gain,
        },
        "verification_gate": {
            "matrix_and_rhs_max_abs_difference_per_s": tolerance,
            "counterfactual_state_matrix_difference_min_per_s": (
                counterfactual_minimum
            ),
        },
        "variants": {
            "both_omit_resistive_drop_feedforward": omit,
            "both_include_resistive_drop_feedforward": include,
        },
        "structural_choice_sensitivity": {
            "maximum_matched_eigenvalue_displacement_per_s": float(
                np.max(matched_displacement)
            ),
            "spectral_abscissa_change_per_s": float(
                include["spectral_abscissa_per_s"] - omit["spectral_abscissa_per_s"]
            ),
            "stability_classification_changed": bool(
                include["stable_by_eigenvalues"] != omit["stable_by_eigenvalues"]
            ),
        },
        "counterfactual": {
            "change": "source current-feedforward gain changed from 1.0 to 0.99",
            "state_matrix_max_abs_difference_per_s": counterfactual[
                "state_matrix_max_abs_difference_per_s"
            ],
            "input_matrix_max_abs_difference_per_s": counterfactual[
                "input_matrix_max_abs_difference_per_s"
            ],
            "probe_rhs_max_abs_difference_per_s": counterfactual[
                "probe_rhs_max_abs_difference_per_s"
            ],
            "gate_rejected_mismatch": counterfactual["status"] == "failed",
        },
        "scope": {
            "source_baselines_modified": False,
            "both_intermediate_variants_isomorphic": passed,
            "outer_controls_compared": False,
            "pll_compared": False,
            "active_damping_compared": False,
            "modulation_or_limits_compared": False,
            "external_network_dynamics_compared": False,
            "statement": (
                "Both ten-state intermediate variants are equation-isomorphic "
                "after PI scaling and LCL coordinate rotation. Their spectral "
                "difference measures only the Rf*i_f compensation choice inside "
                "this bounded common model, not either original full system."
            ),
        },
    }
