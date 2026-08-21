"""Common active-damping extension of the Sienna/team inner-loop cases.

This module adds the same two capacitor-voltage low-pass states and damping
feedback to both explicitly labelled intermediate models.  It compares those
twelve-state models with the already verified ten-state, no-active-damping
paths.  Neither intermediate path is relabelled as an original source model.
"""

from __future__ import annotations

from dataclasses import replace
from math import pi

import numpy as np
from numpy.typing import ArrayLike, NDArray

from backend.core.sienna_team_common_inner_loop import (
    CommonInnerLoopParameters,
    _control_signals,
    _finite_vector,
    _lcl_parameters,
    _rotation,
    _validate,
    sienna_team_common_inner_loop_audit,
)
from backend.core.sienna_team_lcl_isomorphism import (
    sienna_lcl_rhs_global,
    team_lcl_rhs_local,
)


def _validate_active_damping(cutoff_rad_s: float, gain: float) -> None:
    if not np.isfinite(cutoff_rad_s) or cutoff_rad_s <= 0.0:
        raise ValueError("active-damping cutoff must be finite and positive")
    if not np.isfinite(gain) or gain < 0.0:
        raise ValueError("active-damping gain must be finite and nonnegative")


def team_common_active_damping_rhs(
    state_team: ArrayLike,
    inputs_local: ArrayLike,
    parameters: CommonInnerLoopParameters,
    *,
    active_damping_cutoff_rad_s: float,
    active_damping_gain: float,
) -> NDArray[np.float64]:
    """Evaluate the team-coordinate twelve-state active-damping intermediate."""

    _validate(parameters)
    _validate_active_damping(active_damping_cutoff_rad_s, active_damping_gain)
    state = _finite_vector(state_team, 12, "team active-damping state")
    inputs = _finite_vector(inputs_local, 4, "common active-damping inputs")
    voltage_integral_output = state[0:2]
    current_integral_output = state[2:4]
    damping_filter = state[4:6]
    lcl_local = state[6:12]
    voltage_error, current_error, converter_voltage_reference = _control_signals(
        voltage_integral_output,
        current_integral_output,
        lcl_local,
        inputs,
        parameters,
    )
    capacitor_voltage = lcl_local[2:4]
    converter_voltage_reference -= active_damping_gain * (
        capacitor_voltage - damping_filter
    )
    derivative = np.empty(12, dtype=np.float64)
    derivative[0:2] = parameters.voltage_ki_per_s * voltage_error
    derivative[2:4] = parameters.current_ki_per_s * current_error
    derivative[4:6] = active_damping_cutoff_rad_s * (
        capacitor_voltage - damping_filter
    )
    derivative[6:12] = team_lcl_rhs_local(
        lcl_local,
        np.concatenate((converter_voltage_reference, inputs[2:4])),
        _lcl_parameters(parameters),
    )
    return derivative


def sienna_common_active_damping_rhs(
    state_source: ArrayLike,
    inputs_local: ArrayLike,
    parameters: CommonInnerLoopParameters,
    *,
    angle_rad: float,
    active_damping_cutoff_rad_s: float,
    active_damping_gain: float,
) -> NDArray[np.float64]:
    """Evaluate the source-coordinate twelve-state active-damping intermediate."""

    _validate(parameters)
    _validate_active_damping(active_damping_cutoff_rad_s, active_damping_gain)
    if not np.isfinite(angle_rad):
        raise ValueError("alignment angle must be finite")
    state = _finite_vector(state_source, 12, "source active-damping state")
    inputs = _finite_vector(inputs_local, 4, "common active-damping inputs")
    raw_voltage_integral = state[0:2]
    raw_current_integral = state[2:4]
    damping_filter = state[4:6]
    lcl_global = state[6:12]
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
    capacitor_voltage = lcl_local[2:4]
    converter_voltage_reference_local -= active_damping_gain * (
        capacitor_voltage - damping_filter
    )
    derivative = np.empty(12, dtype=np.float64)
    derivative[0:2] = voltage_error
    derivative[2:4] = current_error
    derivative[4:6] = active_damping_cutoff_rad_s * (
        capacitor_voltage - damping_filter
    )
    derivative[6:12] = sienna_lcl_rhs_global(
        lcl_global,
        np.concatenate(
            (
                rotation @ converter_voltage_reference_local,
                rotation @ inputs[2:4],
            )
        ),
        _lcl_parameters(parameters),
    )
    return derivative


def _linear_matrices_12(rhs) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    state_matrix = np.column_stack(
        [rhs(np.eye(12)[:, index], np.zeros(4)) for index in range(12)]
    )
    input_matrix = np.column_stack(
        [rhs(np.zeros(12), np.eye(4)[:, index]) for index in range(4)]
    )
    return state_matrix, input_matrix


def team_common_active_damping_matrices(
    parameters: CommonInnerLoopParameters,
    *,
    active_damping_cutoff_rad_s: float,
    active_damping_gain: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the twelve-state team-coordinate ``A, B`` matrices."""

    _validate(parameters)
    _validate_active_damping(active_damping_cutoff_rad_s, active_damping_gain)
    return _linear_matrices_12(
        lambda state, inputs: team_common_active_damping_rhs(
            state,
            inputs,
            parameters,
            active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
            active_damping_gain=active_damping_gain,
        )
    )


def _state_transform_12(
    parameters: CommonInnerLoopParameters, angle_rad: float
) -> NDArray[np.float64]:
    transform = np.zeros((12, 12), dtype=np.float64)
    transform[0:2, 0:2] = parameters.voltage_ki_per_s * np.eye(2)
    transform[2:4, 2:4] = parameters.current_ki_per_s * np.eye(2)
    transform[4:6, 4:6] = np.eye(2)
    transform[6:12, 6:12] = np.kron(np.eye(3), _rotation(angle_rad).T)
    return transform


def _active_variant_audit(
    source_parameters: CommonInnerLoopParameters,
    team_parameters: CommonInnerLoopParameters,
    *,
    angle_rad: float,
    source_cutoff_rad_s: float,
    team_cutoff_rad_s: float,
    active_damping_gain: float,
) -> dict[str, object]:
    source_a, source_b = _linear_matrices_12(
        lambda state, inputs: sienna_common_active_damping_rhs(
            state,
            inputs,
            source_parameters,
            angle_rad=angle_rad,
            active_damping_cutoff_rad_s=source_cutoff_rad_s,
            active_damping_gain=active_damping_gain,
        )
    )
    team_a, team_b = _linear_matrices_12(
        lambda state, inputs: team_common_active_damping_rhs(
            state,
            inputs,
            team_parameters,
            active_damping_cutoff_rad_s=team_cutoff_rad_s,
            active_damping_gain=active_damping_gain,
        )
    )
    transform = _state_transform_12(source_parameters, angle_rad)
    source_a_team = transform @ source_a @ np.linalg.inv(transform)
    source_b_team = transform @ source_b
    a_difference = float(np.max(np.abs(team_a - source_a_team)))
    b_difference = float(np.max(np.abs(team_b - source_b_team)))
    team_probe_state = np.array(
        [
            0.12,
            -0.04,
            0.18,
            -0.07,
            1.01,
            0.03,
            0.41,
            -0.15,
            1.02,
            0.06,
            0.36,
            -0.08,
        ]
    )
    probe_input = np.array([1.01, 0.02, 0.98, -0.03])
    source_probe_state = np.linalg.solve(transform, team_probe_state)
    source_probe_team = transform @ sienna_common_active_damping_rhs(
        source_probe_state,
        probe_input,
        source_parameters,
        angle_rad=angle_rad,
        active_damping_cutoff_rad_s=source_cutoff_rad_s,
        active_damping_gain=active_damping_gain,
    )
    team_probe = team_common_active_damping_rhs(
        team_probe_state,
        probe_input,
        team_parameters,
        active_damping_cutoff_rad_s=team_cutoff_rad_s,
        active_damping_gain=active_damping_gain,
    )
    probe_difference = float(np.max(np.abs(team_probe - source_probe_team)))
    eigenvalues = np.linalg.eigvals(team_a)
    tolerance = 1.0e-10
    return {
        "status": "passed"
        if max(a_difference, b_difference, probe_difference) <= tolerance
        else "failed",
        "state_matrix_max_abs_difference_per_s": a_difference,
        "input_matrix_max_abs_difference_per_s": b_difference,
        "probe_rhs_max_abs_difference_per_s": probe_difference,
        "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
        "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
        "rightmost_eigenvalue": {
            "real_per_s": float(eigenvalues[np.argmax(eigenvalues.real)].real),
            "imag_per_s": float(eigenvalues[np.argmax(eigenvalues.real)].imag),
            "oscillation_frequency_hz": float(
                abs(eigenvalues[np.argmax(eigenvalues.real)].imag) / (2.0 * pi)
            ),
        },
    }


def sienna_team_common_active_damping_audit(
    base_parameters: CommonInnerLoopParameters,
    *,
    angle_rad: float,
    active_damping_cutoff_rad_s: float = 50.0,
    active_damping_gain: float = 0.2,
) -> dict[str, object]:
    """Compare no-damping and common-active-damping intermediate paths."""

    _validate(base_parameters)
    _validate_active_damping(active_damping_cutoff_rad_s, active_damping_gain)
    no_damping = sienna_team_common_inner_loop_audit(
        base_parameters, angle_rad=angle_rad
    )
    variants: dict[str, object] = {}
    for key, gain in (
        ("both_omit_resistive_drop_feedforward", 0.0),
        ("both_include_resistive_drop_feedforward", 1.0),
    ):
        parameters = replace(
            base_parameters, resistive_drop_feedforward_gain=gain
        )
        active = _active_variant_audit(
            parameters,
            parameters,
            angle_rad=angle_rad,
            source_cutoff_rad_s=active_damping_cutoff_rad_s,
            team_cutoff_rad_s=active_damping_cutoff_rad_s,
            active_damping_gain=active_damping_gain,
        )
        baseline = no_damping["variants"][key]
        variants[key] = {
            "without_active_damping": {
                "state_count": 10,
                "spectral_abscissa_per_s": baseline["spectral_abscissa_per_s"],
                "stable_by_eigenvalues": baseline["stable_by_eigenvalues"],
            },
            "with_active_damping": {"state_count": 12, **active},
            "spectral_abscissa_change_per_s": float(
                active["spectral_abscissa_per_s"]
                - baseline["spectral_abscissa_per_s"]
            ),
            "stability_classification_changed": bool(
                active["stable_by_eigenvalues"]
                != baseline["stable_by_eigenvalues"]
            ),
        }

    omit_parameters = replace(
        base_parameters, resistive_drop_feedforward_gain=0.0
    )
    counterfactual = _active_variant_audit(
        omit_parameters,
        omit_parameters,
        angle_rad=angle_rad,
        source_cutoff_rad_s=active_damping_cutoff_rad_s * 0.98,
        team_cutoff_rad_s=active_damping_cutoff_rad_s,
        active_damping_gain=active_damping_gain,
    )
    tolerance = 1.0e-10
    counterfactual_minimum = 0.5
    passed = all(
        variant["with_active_damping"]["status"] == "passed"
        for variant in variants.values()
    ) and (
        counterfactual["state_matrix_max_abs_difference_per_s"]
        >= counterfactual_minimum
    )
    return {
        "schema_version": "gfm-sienna-team-common-active-damping-audit/1.0",
        "status": "passed" if passed else "failed",
        "active_damping_contract": {
            "filter_state_count": 2,
            "cutoff_rad_s": active_damping_cutoff_rad_s,
            "gain": active_damping_gain,
            "feedback": "-kad * (v_capacitor - phi)",
            "filter_dynamics": "phi_dot = omega_ad * (v_capacitor - phi)",
        },
        "verification_gate": {
            "matrix_and_rhs_max_abs_difference_per_s": tolerance,
            "counterfactual_state_matrix_difference_min_per_s": (
                counterfactual_minimum
            ),
        },
        "variants": variants,
        "counterfactual": {
            "change": "source active-damping cutoff multiplied by 0.98",
            "state_matrix_max_abs_difference_per_s": counterfactual[
                "state_matrix_max_abs_difference_per_s"
            ],
            "probe_rhs_max_abs_difference_per_s": counterfactual[
                "probe_rhs_max_abs_difference_per_s"
            ],
            "gate_rejected_mismatch": counterfactual["status"] == "failed",
        },
        "hypothesis_test": {
            "hypothesis": (
                "adding the same Test 08 active-damping states is sufficient "
                "to change the fixed-input common-inner-loop classification"
            ),
            "supported_for_both_structural_paths": all(
                variant["stability_classification_changed"]
                for variant in variants.values()
            ),
        },
        "scope": {
            "source_baselines_modified": False,
            "team_original_model_modified": False,
            "common_active_damping_intermediate_only": True,
            "outer_controls_compared": False,
            "pll_compared": False,
            "modulation_or_limits_compared": False,
            "external_network_dynamics_compared": False,
            "statement": (
                "The same active-damping states are added only to both common "
                "intermediate models. Classification changes, if any, apply only "
                "to these fixed-input inner loops and do not establish causality "
                "for either original full system."
            ),
        },
    }
