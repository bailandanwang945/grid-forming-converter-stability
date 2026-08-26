"""Shared local-dq first-order modulation lag for the Sienna/team bridge.

The study augments the verified fourteen-state common active-power-delay
model with the two modulation-voltage states already declared by the team's
average-dq model.  The source path retains those states in the controller's
local dq frame and rotates their output into the source model's global LCL
frame.  This is not a PWM model, a physical transport delay, or either
original complete converter model.
"""

from __future__ import annotations

from math import isfinite, pi

import numpy as np
from numpy.typing import ArrayLike, NDArray

from backend.core.average_dq_ablation import (
    ModalSignature,
    match_modes,
    modal_signature,
)
from backend.core.average_dq_model import J
from backend.core.sienna_team_active_power_measurement_delay import (
    SOURCE_STATE_LABELS as BASE_SOURCE_STATE_LABELS,
    TEAM_STATE_LABELS as BASE_TEAM_STATE_LABELS,
    _band_mode,
    _match_payload,
    _pole_payload,
    _point_matrices as active_power_point_matrices,
    _team_to_source_state as active_power_team_to_source_state,
    solve_common_active_power_delay_equilibrium,
    source_common_active_power_delay_rhs_in_team_coordinates,
    team_common_active_power_delay_rhs,
)
from backend.core.sienna_team_common_outer_loop import (
    CommonOuterLoopParameters,
    _control_signals,
    _finite_vector,
    _jacobian,
    _lcl_parameters,
    _rotation,
    frozen_common_outer_loop_parameters,
)
from backend.core.sienna_team_lcl_isomorphism import (
    sienna_lcl_rhs_global,
    team_lcl_rhs_local,
)


POWER_PORT = "pcc"
ACTIVE_POWER_TIME_CONSTANT_S = 0.1
TEAM_DECLARED_MODULATION_TIME_CONSTANT_S = 1.0e-3
MODULATION_LEVELS_S = (1.0e-4, 2.5e-4, 5.0e-4, 1.0e-3, 2.0e-3, 5.0e-3)
TEAM_STATE_LABELS = (
    *BASE_TEAM_STATE_LABELS,
    "modulation_voltage_d_pu_local_dq",
    "modulation_voltage_q_pu_local_dq",
)
SOURCE_STATE_LABELS = (
    *BASE_SOURCE_STATE_LABELS,
    "modulation_voltage_d_pu_local_control_dq",
    "modulation_voltage_q_pu_local_control_dq",
)


class CommonModulationDelayError(ValueError):
    """Raised when the bounded first-order modulation contract is invalid."""


def _validate_modulation_time_constant(time_constant_s: float) -> float:
    value = float(time_constant_s)
    if not isfinite(value) or value <= 0.0 or value > 1.0:
        raise CommonModulationDelayError(
            "modulation time constant must be finite and within (0, 1] s"
        )
    return value


def _team_converter_voltage_reference(
    state_team: NDArray[np.float64], parameters: CommonOuterLoopParameters
) -> NDArray[np.float64]:
    voltage_reference = parameters.voltage_reference_pu + (
        parameters.reactive_power_droop_gain
        * (parameters.reactive_power_reference_pu - float(state_team[3]))
    )
    return _control_signals(
        state_team[4:6],
        state_team[6:8],
        state_team[8:14],
        voltage_reference,
        float(state_team[1]),
        parameters.inner,
    )[2]


def _source_converter_voltage_reference(
    state_team: NDArray[np.float64], parameters: CommonOuterLoopParameters
) -> NDArray[np.float64]:
    source = active_power_team_to_source_state(state_team[:14], parameters)
    rotation_transpose = _rotation(float(state_team[0])).T
    lcl_local = np.kron(np.eye(3), rotation_transpose) @ source[8:14]
    voltage_reference = parameters.voltage_reference_pu + (
        parameters.reactive_power_droop_gain
        * (parameters.reactive_power_reference_pu - float(source[3]))
    )
    return _control_signals(
        parameters.inner.voltage_ki_per_s * source[4:6],
        parameters.inner.current_ki_per_s * source[6:8],
        lcl_local,
        voltage_reference,
        float(source[1]),
        parameters.inner,
    )[2]


def team_common_modulation_delay_rhs(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    modulation_time_constant_s: float,
) -> NDArray[np.float64]:
    """Evaluate the sixteen-state model in the team's moving local-dq frame."""

    time_constant = _validate_modulation_time_constant(
        modulation_time_constant_s
    )
    state = _finite_vector(state_team, 16, "common modulation state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    derivative = np.empty(16, dtype=np.float64)
    derivative[:14] = team_common_active_power_delay_rhs(
        state[:14],
        pcc,
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
    )
    pcc_local = _rotation(-float(state[0])) @ pcc
    derivative[8:14] = team_lcl_rhs_local(
        state[8:14],
        np.concatenate((state[14:16], pcc_local)),
        _lcl_parameters(parameters.inner, float(state[1])),
    )
    converter_voltage_reference = _team_converter_voltage_reference(
        state, parameters
    )
    derivative[14:16] = (
        converter_voltage_reference - state[14:16]
    ) / time_constant
    return derivative


def source_common_modulation_delay_rhs_in_team_coordinates(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    modulation_time_constant_s: float,
) -> NDArray[np.float64]:
    """Evaluate the independently augmented source path in team coordinates."""

    time_constant = _validate_modulation_time_constant(
        modulation_time_constant_s
    )
    state = _finite_vector(state_team, 16, "common modulation state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    derivative = np.empty(16, dtype=np.float64)
    derivative[:14] = source_common_active_power_delay_rhs_in_team_coordinates(
        state[:14],
        pcc,
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
    )

    source = active_power_team_to_source_state(state[:14], parameters)
    theta = float(state[0])
    rotation = _rotation(theta)
    source_lcl_derivative = sienna_lcl_rhs_global(
        source[8:14],
        np.concatenate((rotation @ state[14:16], pcc)),
        _lcl_parameters(parameters.inner, parameters.system_frequency_pu),
    )
    theta_derivative = float(derivative[0])
    for pair_index, offset in enumerate((8, 10, 12)):
        source_offset = 2 * pair_index
        derivative[offset : offset + 2] = (
            rotation.T
            @ source_lcl_derivative[source_offset : source_offset + 2]
            - theta_derivative * J @ state[offset : offset + 2]
        )

    converter_voltage_reference = _source_converter_voltage_reference(
        state, parameters
    )
    derivative[14:16] = (
        converter_voltage_reference - state[14:16]
    ) / time_constant
    return derivative


def solve_common_modulation_delay_equilibrium(
    parameters: CommonOuterLoopParameters,
    *,
    modulation_time_constant_s: float,
    pcc_voltage_global: ArrayLike = (1.0, 0.0),
) -> NDArray[np.float64]:
    """Construct and verify the loaded sixteen-state common equilibrium."""

    _validate_modulation_time_constant(modulation_time_constant_s)
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    base = solve_common_active_power_delay_equilibrium(
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
        pcc_voltage_global=pcc,
    )
    equilibrium = np.concatenate(
        (base, _team_converter_voltage_reference(base, parameters))
    )
    residuals = (
        team_common_modulation_delay_rhs(
            equilibrium,
            pcc,
            parameters,
            modulation_time_constant_s=modulation_time_constant_s,
        ),
        source_common_modulation_delay_rhs_in_team_coordinates(
            equilibrium,
            pcc,
            parameters,
            modulation_time_constant_s=modulation_time_constant_s,
        ),
    )
    if max(float(np.linalg.norm(value, ord=np.inf)) for value in residuals) > 1.0e-8:
        raise RuntimeError("common modulation equilibrium residual exceeds 1e-8")
    return equilibrium


def _point_matrices(
    parameters: CommonOuterLoopParameters,
    pcc: NDArray[np.float64],
    time_constant_s: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    equilibrium = solve_common_modulation_delay_equilibrium(
        parameters,
        modulation_time_constant_s=time_constant_s,
        pcc_voltage_global=pcc,
    )
    team_matrix = _jacobian(
        lambda state: team_common_modulation_delay_rhs(
            state,
            pcc,
            parameters,
            modulation_time_constant_s=time_constant_s,
        ),
        equilibrium,
    )
    source_matrix = _jacobian(
        lambda state: source_common_modulation_delay_rhs_in_team_coordinates(
            state,
            pcc,
            parameters,
            modulation_time_constant_s=time_constant_s,
        ),
        equilibrium,
    )
    return equilibrium, team_matrix, source_matrix


def _source_bypass_rhs_in_team_coordinates(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    modulation_time_constant_s: float,
) -> NDArray[np.float64]:
    """Deliberately retain the lag states while bypassing them at the LCL input."""

    time_constant = _validate_modulation_time_constant(
        modulation_time_constant_s
    )
    state = _finite_vector(state_team, 16, "common modulation state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    derivative = np.empty(16, dtype=np.float64)
    derivative[:14] = source_common_active_power_delay_rhs_in_team_coordinates(
        state[:14],
        pcc,
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
    )
    derivative[14:16] = (
        _source_converter_voltage_reference(state, parameters) - state[14:16]
    ) / time_constant
    return derivative


def _probe_state(equilibrium: NDArray[np.float64]) -> NDArray[np.float64]:
    return equilibrium + np.linspace(-3.0e-4, 3.0e-4, equilibrium.size)


def run_common_modulation_delay_audit() -> dict[str, object]:
    """Run the fixed first-order modulation scan and structural counterexample."""

    parameters = frozen_common_outer_loop_parameters()
    pcc = np.array([1.0, 0.0], dtype=np.float64)
    ideal_equilibrium, ideal_matrix, _ = active_power_point_matrices(
        parameters,
        pcc,
        POWER_PORT,
        ACTIVE_POWER_TIME_CONSTANT_S,
    )
    ideal_low = _band_mode(ideal_matrix, 1.0, 5.0)
    ideal_wide = _band_mode(ideal_matrix, 90.0, 130.0)
    points: list[dict[str, object]] = []
    references: tuple[ModalSignature, ModalSignature] | None = None
    baseline_values: tuple[complex, complex] | None = None

    omega_base = 2.0 * pi * parameters.inner.frequency_hz
    expected_lcl_input_block = (
        omega_base
        / parameters.inner.converter_side_reactance_pu
        * np.eye(2)
    )
    for time_constant in MODULATION_LEVELS_S:
        equilibrium, team_matrix, source_matrix = _point_matrices(
            parameters, pcc, time_constant
        )
        eigenvalues = np.linalg.eigvals(team_matrix)
        positive_modes = [
            complex(value) for value in eigenvalues if value.imag > 1.0e-8
        ]
        if references is None:
            low_value = min(
                positive_modes, key=lambda value: abs(value - ideal_low)
            )
            wide_candidates = [
                value for value in positive_modes if value != low_value
            ]
            wide_value = min(
                wide_candidates, key=lambda value: abs(value - ideal_wide)
            )
            references = (
                modal_signature(team_matrix, low_value),
                modal_signature(team_matrix, wide_value),
            )
            baseline_values = tuple(
                signature.eigenvalue_per_s for signature in references
            )
            tracking = (
                {
                    "status": "anchor",
                    "reason": "nearest-fourteen-state-ideal-limit-mode",
                },
                {
                    "status": "anchor",
                    "reason": "nearest-fourteen-state-ideal-limit-mode",
                },
            )
            point_signatures = references
        else:
            matches = match_modes(references, team_matrix)
            tracking = tuple(_match_payload(match) for match in matches)
            point_signatures = tuple(
                modal_signature(team_matrix, match.eigenvalue_per_s)
                for match in matches
            )
            if all(match.status == "matched" for match in matches):
                references = point_signatures

        team_rhs = team_common_modulation_delay_rhs(
            equilibrium,
            pcc,
            parameters,
            modulation_time_constant_s=time_constant,
        )
        source_rhs = source_common_modulation_delay_rhs_in_team_coordinates(
            equilibrium,
            pcc,
            parameters,
            modulation_time_constant_s=time_constant,
        )
        probe = _probe_state(equilibrium)
        probe_team_rhs = team_common_modulation_delay_rhs(
            probe,
            pcc,
            parameters,
            modulation_time_constant_s=time_constant,
        )
        probe_source_rhs = source_common_modulation_delay_rhs_in_team_coordinates(
            probe,
            pcc,
            parameters,
            modulation_time_constant_s=time_constant,
        )
        points.append(
            {
                "modulation_time_constant_s": time_constant,
                "dimensionless_ideal_wide_mode_delay": float(
                    abs(ideal_wide.imag) * time_constant
                ),
                "equilibrium_residual_inf": float(
                    np.linalg.norm(team_rhs, ord=np.inf)
                ),
                "equilibrium_rhs_difference_inf": float(
                    np.linalg.norm(team_rhs - source_rhs, ord=np.inf)
                ),
                "off_equilibrium_rhs_difference_inf": float(
                    np.linalg.norm(
                        probe_team_rhs - probe_source_rhs, ord=np.inf
                    )
                ),
                "state_matrix_max_abs_difference_per_s": float(
                    np.max(np.abs(team_matrix - source_matrix))
                ),
                "modulation_self_block_max_abs_error_per_s": float(
                    np.max(
                        np.abs(
                            team_matrix[14:16, 14:16]
                            + np.eye(2) / time_constant
                        )
                    )
                ),
                "modulation_to_lcl_input_block_max_abs_error_per_s": float(
                    np.max(
                        np.abs(
                            team_matrix[8:10, 14:16]
                            - expected_lcl_input_block
                        )
                    )
                ),
                "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
                "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
                "low_frequency_mode": {
                    "pole": _pole_payload(
                        point_signatures[0].eigenvalue_per_s
                    ),
                    "tracking": tracking[0],
                },
                "wide_frequency_mode": {
                    "pole": _pole_payload(
                        point_signatures[1].eigenvalue_per_s
                    ),
                    "tracking": tracking[1],
                },
            }
        )

    assert baseline_values is not None and references is not None
    all_modes_resolved = all(
        point[mode]["tracking"]["status"] in {"anchor", "matched"}
        for point in points
        for mode in ("low_frequency_mode", "wide_frequency_mode")
    )
    if all_modes_resolved:
        low_displacement = float(
            abs(references[0].eigenvalue_per_s - baseline_values[0])
            / max(abs(baseline_values[0]), 1.0)
        )
        wide_displacement = float(
            abs(references[1].eigenvalue_per_s - baseline_values[1])
            / max(abs(baseline_values[1]), 1.0)
        )
    else:
        low_displacement = None
        wide_displacement = None

    counterexample_time_constant = TEAM_DECLARED_MODULATION_TIME_CONSTANT_S
    counterexample_equilibrium, matched_matrix, _ = _point_matrices(
        parameters, pcc, counterexample_time_constant
    )
    bypass_matrix = _jacobian(
        lambda state: _source_bypass_rhs_in_team_coordinates(
            state,
            pcc,
            parameters,
            modulation_time_constant_s=counterexample_time_constant,
        ),
        counterexample_equilibrium,
    )
    bypass_difference = float(
        np.max(np.abs(matched_matrix - bypass_matrix))
    )

    equation_gate = 1.0e-5
    counterexample_minimum = 1.0
    all_equations_match = all(
        point["equilibrium_residual_inf"] <= 1.0e-8
        and point["equilibrium_rhs_difference_inf"] <= equation_gate
        and point["off_equilibrium_rhs_difference_inf"] <= equation_gate
        and point["state_matrix_max_abs_difference_per_s"] <= equation_gate
        and point["modulation_self_block_max_abs_error_per_s"] <= equation_gate
        and point["modulation_to_lcl_input_block_max_abs_error_per_s"]
        <= equation_gate
        for point in points
    )
    counterexample_rejected = bypass_difference >= counterexample_minimum
    passed = all_equations_match and counterexample_rejected
    hypothesis_supported = bool(
        all_modes_resolved
        and low_displacement is not None
        and wide_displacement is not None
        and wide_displacement > low_displacement
    )

    return {
        "schema_version": "gfm-sienna-team-common-modulation-delay/1.0",
        "status": "passed" if passed else "failed",
        "verification_summary": {
            "equation_and_counterexample_status": (
                "passed" if passed else "failed"
            ),
            "named_mode_tracking_status": (
                "resolved" if all_modes_resolved else "pending"
            ),
        },
        "model_contract": {
            "state_count": 16,
            "base_state_count": 14,
            "team_state_labels": list(TEAM_STATE_LABELS),
            "source_state_labels": list(SOURCE_STATE_LABELS),
            "power_measurement_port": POWER_PORT,
            "active_power_time_constant_s": ACTIVE_POWER_TIME_CONSTANT_S,
            "modulation_time_constant_levels_s": list(MODULATION_LEVELS_S),
            "team_declared_modulation_time_constant_s": (
                TEAM_DECLARED_MODULATION_TIME_CONSTANT_S
            ),
            "pcc_voltage_global_pu": pcc.tolist(),
            "modulation_equation": (
                "T_mod * d(v_mod,dq)/dt = v_command,dq - v_mod,dq"
            ),
            "modulation_state_frame": "converter-local control dq",
            "source_lcl_input_mapping": "v_mod,global = R(theta) * v_mod,dq",
        },
        "verification_gates": {
            "equilibrium_residual_inf_max": 1.0e-8,
            "rhs_matrix_and_structural_block_difference_max_per_s": (
                equation_gate
            ),
            "bypass_counterexample_difference_min_per_s": (
                counterexample_minimum
            ),
        },
        "ideal_fourteen_state_limit": {
            "equilibrium_state_count": int(ideal_equilibrium.size),
            "spectral_abscissa_per_s": float(
                np.max(np.linalg.eigvals(ideal_matrix).real)
            ),
            "low_frequency_mode": _pole_payload(ideal_low),
            "wide_frequency_mode": _pole_payload(ideal_wide),
            "force_matched_to_sixteen_state_spectrum": False,
        },
        "points": points,
        "endpoint_normalized_displacement_from_0p1ms": {
            "low_frequency_mode": low_displacement,
            "wide_frequency_mode": wide_displacement,
        },
        "counterexample": {
            "change": (
                "the transformed source retains the lag states but feeds the "
                "algebraic current-controller voltage command directly to the LCL"
            ),
            "modulation_time_constant_s": counterexample_time_constant,
            "state_matrix_max_abs_difference_per_s": bypass_difference,
            "gate_rejected_mismatch": counterexample_rejected,
        },
        "hypothesis_test": {
            "hypothesis": (
                "the local-dq first-order modulation lag moves the named wide "
                "LCL-inner-loop branch more than the low synchronization branch"
            ),
            "all_named_modes_resolved": all_modes_resolved,
            "result": (
                "supported-in-bounded-scan"
                if hypothesis_supported
                else (
                    "not-supported-in-bounded-scan"
                    if all_modes_resolved
                    else "pending-because-a-named-mode-is-unresolved"
                )
            ),
        },
        "scope": {
            "source_baselines_modified": False,
            "team_original_model_modified": False,
            "common_intermediate_case_only": True,
            "local_dq_first_order_lag_compared": True,
            "physical_pwm_or_transport_delay_compared": False,
            "pade_delay_approximation_compared": False,
            "pll_or_frequency_estimator_compared": False,
            "external_network_dynamics_compared": False,
            "whole_system_hopf_margin_claimed": False,
            "paper_sufficient_condition_evaluated": False,
            "statement": (
                "The scan isolates a local-control-dq first-order voltage lag "
                "inside a fixed-PCC common intermediate model. It is not a PWM "
                "transport delay, and the already-right-half-plane wide branch "
                "precludes a whole-system Hopf-margin claim."
            ),
        },
    }
