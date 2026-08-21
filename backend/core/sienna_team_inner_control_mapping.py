"""Bounded mapping audit for the Sienna/team cascaded PI controllers.

The two implementations store PI integrator states differently.  Sienna keeps
the raw error integral ``xi`` and multiplies it by ``Ki`` at the output, while
the team model stores the already-scaled integral contribution ``eta``.  The
state transformation ``eta = Ki * xi`` makes the four PI states equivalent.

That state equivalence does not make the complete inner controllers equal.
This module separately audits the voltage/current feed-forward, rotating-frame
decoupling, active-damping, and resistive-drop compensation terms so a partial
match cannot be mistaken for full controller isomorphism.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np
from numpy.typing import ArrayLike, NDArray

from backend.core.average_dq_model import J


@dataclass(frozen=True)
class CascadedPIParameters:
    """Per-unit gains and compensation parameters for the common audit."""

    voltage_kp: float
    voltage_ki_per_s: float
    current_kp: float
    current_ki_per_s: float
    filter_capacitor_susceptance_pu: float
    converter_side_resistance_pu: float
    converter_side_reactance_pu: float
    current_feedforward_gain: float
    voltage_feedforward_gain: float
    active_damping_gain: float
    synchronous_frequency_pu: float = 1.0
    resistive_drop_feedforward_gain: float = 0.0


def _validate(parameters: CascadedPIParameters) -> None:
    values = np.asarray(list(asdict(parameters).values()), dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("inner-control parameters must be finite")
    if parameters.voltage_ki_per_s <= 0.0 or parameters.current_ki_per_s <= 0.0:
        raise ValueError("PI integral gains must be positive for state isomorphism")
    if (
        parameters.filter_capacitor_susceptance_pu <= 0.0
        or parameters.converter_side_reactance_pu <= 0.0
    ):
        raise ValueError("filter susceptance and converter reactance must be positive")
    if parameters.converter_side_resistance_pu < 0.0:
        raise ValueError("converter resistance cannot be negative")


def _finite_vector(value: ArrayLike, length: int, name: str) -> NDArray[np.float64]:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (length,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite length-{length} vector")
    return vector


def _integral_state_transform(
    parameters: CascadedPIParameters,
) -> NDArray[np.float64]:
    return np.diag(
        [
            parameters.voltage_ki_per_s,
            parameters.voltage_ki_per_s,
            parameters.current_ki_per_s,
            parameters.current_ki_per_s,
        ]
    )


def _pi_output_matrices(
    parameters: CascadedPIParameters,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    proportional = np.diag(
        [
            parameters.voltage_kp,
            parameters.voltage_kp,
            parameters.current_kp,
            parameters.current_kp,
        ]
    )
    source_integral_output = _integral_state_transform(parameters)
    team_integral_output = np.eye(4, dtype=np.float64)
    return proportional, source_integral_output, team_integral_output


def _compensation_matrix(
    parameters: CascadedPIParameters,
) -> NDArray[np.float64]:
    """Map [ig, vc, if, phi] to [current-ref, converter-voltage-ref]."""

    matrix = np.zeros((4, 8), dtype=np.float64)
    omega = parameters.synchronous_frequency_pu
    matrix[0:2, 0:2] = parameters.current_feedforward_gain * np.eye(2)
    matrix[0:2, 2:4] = (
        parameters.filter_capacitor_susceptance_pu * omega * J
    )
    matrix[2:4, 2:4] = (
        parameters.voltage_feedforward_gain - parameters.active_damping_gain
    ) * np.eye(2)
    matrix[2:4, 4:6] = (
        parameters.resistive_drop_feedforward_gain
        * parameters.converter_side_resistance_pu
        * np.eye(2)
        + parameters.converter_side_reactance_pu * omega * J
    )
    matrix[2:4, 6:8] = parameters.active_damping_gain * np.eye(2)
    return matrix


def _matrix_max_difference(
    left: NDArray[np.float64], right: NDArray[np.float64]
) -> float:
    return float(np.max(np.abs(left - right)))


def sienna_team_inner_control_mapping_audit(
    source_parameters: CascadedPIParameters,
    team_parameters: CascadedPIParameters,
) -> dict[str, object]:
    """Audit PI-state isomorphism and disclose remaining compensation gaps."""

    _validate(source_parameters)
    _validate(team_parameters)
    source_transform = _integral_state_transform(source_parameters)
    team_transform = _integral_state_transform(team_parameters)
    source_kp, source_ki, _ = _pi_output_matrices(source_parameters)
    team_kp, _, team_identity = _pi_output_matrices(team_parameters)

    # Source coordinates: xdot=e, y=Kp*e+Ki*x.  Team coordinates eta=T*x:
    # etadot=T*e, y=Kp*e+eta.  These matrices test that explicit similarity.
    transformed_source_state_input = source_transform
    transformed_source_state_output = source_ki @ np.linalg.inv(source_transform)
    team_state_input = team_transform
    team_state_output = team_identity
    pi_state_input_difference = _matrix_max_difference(
        transformed_source_state_input, team_state_input
    )
    pi_state_output_difference = _matrix_max_difference(
        transformed_source_state_output, team_state_output
    )
    pi_proportional_difference = _matrix_max_difference(source_kp, team_kp)

    source_actual_compensation = _compensation_matrix(source_parameters)
    team_actual_compensation = _compensation_matrix(team_parameters)
    actual_compensation_difference = _matrix_max_difference(
        source_actual_compensation, team_actual_compensation
    )

    # Align every compensation switch exposed by Sienna Test 08.  A remaining
    # difference then identifies a structural term, not a forgotten switch.
    source_parameter_aligned = replace(
        source_parameters,
        current_feedforward_gain=team_parameters.current_feedforward_gain,
        voltage_feedforward_gain=team_parameters.voltage_feedforward_gain,
        active_damping_gain=team_parameters.active_damping_gain,
    )
    parameter_aligned_compensation = _compensation_matrix(source_parameter_aligned)
    parameter_aligned_difference = _matrix_max_difference(
        parameter_aligned_compensation, team_actual_compensation
    )

    source_structurally_aligned = replace(
        source_parameter_aligned,
        resistive_drop_feedforward_gain=(
            team_parameters.resistive_drop_feedforward_gain
        ),
    )
    structurally_aligned_difference = _matrix_max_difference(
        _compensation_matrix(source_structurally_aligned),
        team_actual_compensation,
    )

    probe = np.array([0.37, -0.09, 1.02, 0.07, 0.41, -0.12, 0.98, 0.03])
    parameter_aligned_probe_difference = float(
        np.max(
            np.abs(
                parameter_aligned_compensation @ probe
                - team_actual_compensation @ probe
            )
        )
    )
    tolerance = 1.0e-12
    pi_passed = (
        max(
            pi_state_input_difference,
            pi_state_output_difference,
            pi_proportional_difference,
        )
        <= tolerance
    )
    parameter_only_isomorphic = parameter_aligned_difference <= tolerance
    structural_counterfactual_passed = structurally_aligned_difference <= tolerance

    return {
        "schema_version": "gfm-sienna-team-inner-control-mapping-audit/1.0",
        "status": "partial" if pi_passed else "failed",
        "verification_gates": {
            "matrix_max_abs_difference": tolerance,
        },
        "pi_state_mapping": {
            "status": "passed" if pi_passed else "failed",
            "source_definition": "xi_dot = error; output = Kp*error + Ki*xi",
            "team_definition": "eta_dot = Ki*error; output = Kp*error + eta",
            "coordinate_transform": "eta = diag(Kiv,Kiv,Kic,Kic) * xi",
            "state_input_matrix_max_abs_difference": pi_state_input_difference,
            "state_output_matrix_max_abs_difference": pi_state_output_difference,
            "proportional_matrix_max_abs_difference": pi_proportional_difference,
        },
        "compensation_mapping": {
            "test08_to_team_max_abs_difference": actual_compensation_difference,
            "parameter_only_aligned_max_abs_difference": (
                parameter_aligned_difference
            ),
            "parameter_only_aligned_probe_max_abs_difference": (
                parameter_aligned_probe_difference
            ),
            "parameter_only_isomorphic": parameter_only_isomorphic,
            "structural_counterfactual_max_abs_difference": (
                structurally_aligned_difference
            ),
            "structural_counterfactual_passed": structural_counterfactual_passed,
            "remaining_term": (
                "team converter-side resistance feed-forward "
                "+Rf*i_f has no Test 08 VoltageModeControl gain"
            ),
        },
        "parameters": {
            "source_test08": asdict(source_parameters),
            "team_controller": asdict(team_parameters),
            "source_after_exposed_parameter_alignment": asdict(
                source_parameter_aligned
            ),
        },
        "scope": {
            "pi_states_isomorphic_after_scaling": pi_passed,
            "test08_and_team_complete_inner_controls_isomorphic": False,
            "parameter_only_alignment_sufficient": parameter_only_isomorphic,
            "structural_counterfactual_is_source_test08": False,
            "statement": (
                "The four cascaded PI states are equivalent after integral-state "
                "scaling. Test 08 and the team controller remain structurally "
                "different because the team voltage command includes Rf*i_f, "
                "which Test 08 does not expose as a compensation term."
            ),
        },
    }
