"""Shared active-power measurement dynamics for the Sienna/team comparison.

The original models do not share both the measurement port and measurement
dynamics.  This module therefore augments the already verified thirteen-state
common outer-loop cases with the same first-order active-power measurement
state on both equation paths.  It is a fourteen-state intermediate study, not
either original complete converter model.
"""

from __future__ import annotations

from math import isfinite, pi

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import root

from backend.core.average_dq_ablation import (
    ModalSignature,
    match_modes,
    modal_signature,
)
from backend.core.average_dq_model import J
from backend.core.sienna_team_common_outer_loop import (
    POWER_PORTS,
    CommonOuterLoopParameters,
    _finite_vector,
    _jacobian,
    _power,
    _rotation,
    _source_rhs,
    _validate,
    frozen_common_outer_loop_parameters,
    solve_common_outer_loop_equilibrium,
    team_common_outer_loop_rhs,
)


DELAY_LEVELS_S = (0.01, 0.025, 0.05, 0.1, 0.2)
TEAM_STATE_LABELS = (
    "angle_rad",
    "frequency_pu",
    "measured_active_power_pu",
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
    "measured_active_power_pu",
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


class ActivePowerMeasurementDelayError(ValueError):
    """Raised when the bounded delay-study contract is invalid."""


def _validate_delay(time_constant_s: float) -> float:
    value = float(time_constant_s)
    if not isfinite(value) or value <= 0.0 or value > 1.0:
        raise ActivePowerMeasurementDelayError(
            "active-power measurement time constant must be in (0, 1] s"
        )
    return value


def _without_active_power_state(state: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.concatenate((state[0:2], state[3:14]))


def _instantaneous_power_team(
    state: NDArray[np.float64],
    pcc_global: NDArray[np.float64],
    power_port: str,
) -> tuple[float, float]:
    theta = float(state[0])
    lcl_local = state[8:14]
    pcc_local = _rotation(-theta) @ pcc_global
    return _power(
        lcl_local[2:4], pcc_local, lcl_local[4:6], power_port
    )


def team_common_active_power_delay_rhs(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
    active_power_time_constant_s: float,
) -> NDArray[np.float64]:
    """Evaluate the fourteen-state common model in the moving team frame."""

    _validate(parameters, power_port)
    time_constant = _validate_delay(active_power_time_constant_s)
    state = _finite_vector(state_team, 14, "delayed team outer-loop state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    base_state = _without_active_power_state(state)
    base_derivative = team_common_outer_loop_rhs(
        base_state, pcc, parameters, power_port=power_port
    )
    active_power, _ = _instantaneous_power_team(state, pcc, power_port)
    derivative = np.empty(14, dtype=np.float64)
    derivative[0:2] = base_derivative[0:2]
    derivative[1] = (
        parameters.active_power_reference_pu
        - state[2]
        - parameters.frequency_droop_gain
        * (state[1] - parameters.frequency_reference_pu)
    ) / parameters.inertia_time_constant_s
    derivative[2] = (active_power - state[2]) / time_constant
    derivative[3:14] = base_derivative[2:13]
    return derivative


def _team_to_source_state(
    state_team: NDArray[np.float64], parameters: CommonOuterLoopParameters
) -> NDArray[np.float64]:
    theta = float(state_team[0])
    source = np.empty(14, dtype=np.float64)
    source[0:4] = state_team[0:4]
    source[4:6] = state_team[4:6] / parameters.inner.voltage_ki_per_s
    source[6:8] = state_team[6:8] / parameters.inner.current_ki_per_s
    source[8:14] = (
        np.kron(np.eye(3), _rotation(theta)) @ state_team[8:14]
    )
    return source


def source_common_active_power_delay_rhs_in_team_coordinates(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
    active_power_time_constant_s: float,
) -> NDArray[np.float64]:
    """Evaluate the independently augmented source path in team coordinates."""

    _validate(parameters, power_port)
    time_constant = _validate_delay(active_power_time_constant_s)
    team = _finite_vector(state_team, 14, "delayed team outer-loop state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    source = _team_to_source_state(team, parameters)
    base_source = _without_active_power_state(source)
    base_derivative = _source_rhs(base_source, pcc, parameters, power_port)
    active_power, _ = _power(
        source[10:12], pcc, source[12:14], power_port
    )
    source_derivative = np.empty(14, dtype=np.float64)
    source_derivative[0:2] = base_derivative[0:2]
    source_derivative[1] = (
        parameters.active_power_reference_pu
        - source[2]
        - parameters.frequency_droop_gain
        * (source[1] - parameters.frequency_reference_pu)
    ) / parameters.inertia_time_constant_s
    source_derivative[2] = (active_power - source[2]) / time_constant
    source_derivative[3:14] = base_derivative[2:13]

    theta = float(team[0])
    theta_derivative = float(source_derivative[0])
    rotation_transpose = _rotation(theta).T
    team_derivative = np.empty(14, dtype=np.float64)
    team_derivative[0:4] = source_derivative[0:4]
    team_derivative[4:6] = (
        parameters.inner.voltage_ki_per_s * source_derivative[4:6]
    )
    team_derivative[6:8] = (
        parameters.inner.current_ki_per_s * source_derivative[6:8]
    )
    for offset in (8, 10, 12):
        local_state = team[offset : offset + 2]
        team_derivative[offset : offset + 2] = (
            rotation_transpose @ source_derivative[offset : offset + 2]
            - theta_derivative * J @ local_state
        )
    return team_derivative


def _initial_guess(
    parameters: CommonOuterLoopParameters,
    power_port: str,
    pcc: NDArray[np.float64],
) -> NDArray[np.float64]:
    base = solve_common_outer_loop_equilibrium(
        parameters, power_port=power_port, pcc_voltage_global=pcc
    )
    guess = np.empty(14, dtype=np.float64)
    guess[0:2] = base[0:2]
    lcl_local = base[7:13]
    pcc_local = _rotation(-float(base[0])) @ pcc
    active_power, _ = _power(
        lcl_local[2:4], pcc_local, lcl_local[4:6], power_port
    )
    guess[2] = active_power
    guess[3:14] = base[2:13]
    return guess


def solve_common_active_power_delay_equilibrium(
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
    active_power_time_constant_s: float,
    pcc_voltage_global: ArrayLike = (1.0, 0.0),
) -> NDArray[np.float64]:
    """Solve one loaded fourteen-state common delayed-power equilibrium."""

    _validate(parameters, power_port)
    _validate_delay(active_power_time_constant_s)
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    solution = root(
        lambda state: team_common_active_power_delay_rhs(
            state,
            pcc,
            parameters,
            power_port=power_port,
            active_power_time_constant_s=active_power_time_constant_s,
        ),
        _initial_guess(parameters, power_port, pcc),
        method="hybr",
        options={"xtol": 1.0e-11, "maxfev": 5000},
    )
    residual = team_common_active_power_delay_rhs(
        solution.x,
        pcc,
        parameters,
        power_port=power_port,
        active_power_time_constant_s=active_power_time_constant_s,
    )
    residual_inf = float(np.linalg.norm(residual, ord=np.inf))
    if not solution.success or residual_inf > 1.0e-8:
        raise RuntimeError(
            "common active-power-delay equilibrium failed for "
            f"{power_port} at Tm={active_power_time_constant_s}: "
            f"{solution.message}; residual={residual_inf:.3e}"
        )
    return np.asarray(solution.x, dtype=np.float64)


def _pole_payload(value: complex) -> dict[str, float]:
    return {
        "real_per_s": float(value.real),
        "imag_per_s": float(value.imag),
        "frequency_hz": float(abs(value.imag) / (2.0 * pi)),
    }


def _band_mode(matrix: NDArray[np.float64], low_hz: float, high_hz: float) -> complex:
    eigenvalues = np.linalg.eigvals(matrix)
    candidates = [
        complex(value)
        for value in eigenvalues
        if value.imag > 1.0e-8
        and low_hz < value.imag / (2.0 * pi) < high_hz
    ]
    if len(candidates) != 1:
        raise ActivePowerMeasurementDelayError(
            f"expected one oscillatory mode in ({low_hz}, {high_hz}) Hz, "
            f"found {len(candidates)}"
        )
    return candidates[0]


def _match_payload(match) -> dict[str, object]:
    return {
        "status": match.status,
        "reason": match.reason,
        "right_mac": match.right_mac,
        "left_mac": match.left_mac,
        "combined_mac": match.combined_mac,
        "normalized_eigenvalue_distance": match.normalized_distance,
        "relative_candidate_margin": match.relative_confidence_margin,
        "condition_number": match.condition_number,
        "right_eigenpair_residual": match.right_residual,
        "left_eigenpair_residual": match.left_residual,
    }


def _point_matrices(
    parameters: CommonOuterLoopParameters,
    pcc: NDArray[np.float64],
    power_port: str,
    time_constant_s: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    equilibrium = solve_common_active_power_delay_equilibrium(
        parameters,
        power_port=power_port,
        active_power_time_constant_s=time_constant_s,
        pcc_voltage_global=pcc,
    )
    team_matrix = _jacobian(
        lambda state: team_common_active_power_delay_rhs(
            state,
            pcc,
            parameters,
            power_port=power_port,
            active_power_time_constant_s=time_constant_s,
        ),
        equilibrium,
    )
    source_matrix = _jacobian(
        lambda state: source_common_active_power_delay_rhs_in_team_coordinates(
            state,
            pcc,
            parameters,
            power_port=power_port,
            active_power_time_constant_s=time_constant_s,
        ),
        equilibrium,
    )
    return equilibrium, team_matrix, source_matrix


def _port_scan(
    parameters: CommonOuterLoopParameters,
    pcc: NDArray[np.float64],
    power_port: str,
) -> dict[str, object]:
    ideal_equilibrium = solve_common_outer_loop_equilibrium(
        parameters, power_port=power_port, pcc_voltage_global=pcc
    )
    ideal_matrix = _jacobian(
        lambda state: team_common_outer_loop_rhs(
            state, pcc, parameters, power_port=power_port
        ),
        ideal_equilibrium,
    )
    ideal_low = _band_mode(ideal_matrix, 2.0, 5.0)
    ideal_wide = _band_mode(ideal_matrix, 90.0, 130.0)
    points: list[dict[str, object]] = []
    references: tuple[ModalSignature, ModalSignature] | None = None
    baseline_values: tuple[complex, complex] | None = None

    for time_constant in DELAY_LEVELS_S:
        equilibrium, team_matrix, source_matrix = _point_matrices(
            parameters, pcc, power_port, time_constant
        )
        eigenvalues = np.linalg.eigvals(team_matrix)
        if references is None:
            positive = [complex(value) for value in eigenvalues if value.imag > 1.0e-8]
            low_value = min(positive, key=lambda value: abs(value - ideal_low))
            wide_value = min(positive, key=lambda value: abs(value - ideal_wide))
            low_signature = modal_signature(team_matrix, low_value)
            wide_signature = modal_signature(team_matrix, wide_value)
            references = (low_signature, wide_signature)
            baseline_values = (low_signature.eigenvalue_per_s, wide_signature.eigenvalue_per_s)
            match_rows = (
                {"status": "anchor", "reason": "closest-to-ideal-limit-pole"},
                {"status": "anchor", "reason": "closest-to-ideal-limit-pole"},
            )
        else:
            matches = match_modes(references, team_matrix)
            match_rows = tuple(_match_payload(match) for match in matches)
            references = tuple(
                modal_signature(team_matrix, match.eigenvalue_per_s)
                for match in matches
            )

        low_signature, wide_signature = references
        measured_pole = complex(
            min(eigenvalues, key=lambda value: abs(value + 1.0 / time_constant))
        )
        team_rhs = team_common_active_power_delay_rhs(
            equilibrium,
            pcc,
            parameters,
            power_port=power_port,
            active_power_time_constant_s=time_constant,
        )
        source_rhs = source_common_active_power_delay_rhs_in_team_coordinates(
            equilibrium,
            pcc,
            parameters,
            power_port=power_port,
            active_power_time_constant_s=time_constant,
        )
        points.append(
            {
                "active_power_time_constant_s": time_constant,
                "equilibrium_residual_inf": float(
                    np.linalg.norm(team_rhs, ord=np.inf)
                ),
                "rhs_difference_inf": float(
                    np.linalg.norm(team_rhs - source_rhs, ord=np.inf)
                ),
                "state_matrix_max_abs_difference_per_s": float(
                    np.max(np.abs(team_matrix - source_matrix))
                ),
                "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
                "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
                "low_frequency_mode": {
                    "pole": _pole_payload(low_signature.eigenvalue_per_s),
                    "tracking": match_rows[0],
                },
                "wide_frequency_mode": {
                    "pole": _pole_payload(wide_signature.eigenvalue_per_s),
                    "tracking": match_rows[1],
                },
                "measurement_associated_pole": _pole_payload(measured_pole),
            }
        )

    assert baseline_values is not None and references is not None
    low_displacement = float(
        abs(references[0].eigenvalue_per_s - baseline_values[0])
        / max(abs(baseline_values[0]), 1.0)
    )
    wide_displacement = float(
        abs(references[1].eigenvalue_per_s - baseline_values[1])
        / max(abs(baseline_values[1]), 1.0)
    )
    return {
        "ideal_thirteen_state_limit": {
            "low_frequency_mode": _pole_payload(ideal_low),
            "wide_frequency_mode": _pole_payload(ideal_wide),
        },
        "points": points,
        "endpoint_normalized_displacement_from_0p01s": {
            "low_frequency_mode": low_displacement,
            "wide_frequency_mode": wide_displacement,
        },
        "candidate_hypothesis_low_branch_moves_more": (
            low_displacement > wide_displacement
        ),
    }


def run_common_active_power_measurement_delay_audit() -> dict[str, object]:
    """Run the preregistered two-port delay scan and mismatch counterexample."""

    parameters = frozen_common_outer_loop_parameters()
    pcc = np.array([1.0, 0.0], dtype=np.float64)
    variants = {
        power_port: _port_scan(parameters, pcc, power_port)
        for power_port in POWER_PORTS
    }
    equilibrium, matched_matrix, _ = _point_matrices(
        parameters, pcc, "filter_capacitor", 0.1
    )
    mixed_matrix = _jacobian(
        lambda state: source_common_active_power_delay_rhs_in_team_coordinates(
            state,
            pcc,
            parameters,
            power_port="pcc",
            active_power_time_constant_s=0.1,
        ),
        equilibrium,
    )
    mixed_difference = float(np.max(np.abs(matched_matrix - mixed_matrix)))
    matrix_gate = 1.0e-5
    counterexample_minimum = 1.0
    all_points = [
        point
        for variant in variants.values()
        for point in variant["points"]
    ]
    all_tracking_matched = all(
        point[mode]["tracking"]["status"] in {"anchor", "matched"}
        for point in all_points
        for mode in ("low_frequency_mode", "wide_frequency_mode")
    )
    passed = (
        all(
            point["equilibrium_residual_inf"] <= 1.0e-8
            and point["rhs_difference_inf"] <= matrix_gate
            and point["state_matrix_max_abs_difference_per_s"] <= matrix_gate
            for point in all_points
        )
        and all_tracking_matched
        and mixed_difference >= counterexample_minimum
    )
    return {
        "schema_version": "gfm-sienna-team-active-power-delay/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "state_count": 14,
            "ideal_limit_state_count": 13,
            "team_state_labels": list(TEAM_STATE_LABELS),
            "source_state_labels": list(SOURCE_STATE_LABELS),
            "power_measurement_equation": "Tm * d(pm)/dt = p - pm",
            "delay_levels_s": list(DELAY_LEVELS_S),
            "team_declared_time_constant_s": 0.1,
            "pcc_voltage_global_pu": pcc.tolist(),
        },
        "verification_gates": {
            "equilibrium_residual_inf_max": 1.0e-8,
            "rhs_and_matrix_difference_max_per_s": matrix_gate,
            "mixed_power_port_difference_min_per_s": counterexample_minimum,
        },
        "variants": variants,
        "counterexample": {
            "change": (
                "team uses filter-capacitor power while the transformed source "
                "uses PCC power at Tm=0.1 s"
            ),
            "state_matrix_max_abs_difference_per_s": mixed_difference,
            "gate_rejected_mismatch": mixed_difference >= counterexample_minimum,
        },
        "hypothesis_test": {
            "hypothesis": (
                "active-power measurement delay moves the named low-frequency "
                "branch more than the named wide-frequency branch"
            ),
            "supported_in_both_port_conventions": all(
                variant["candidate_hypothesis_low_branch_moves_more"]
                for variant in variants.values()
            ),
            "result": (
                "supported-in-bounded-scan"
                if all(
                    variant["candidate_hypothesis_low_branch_moves_more"]
                    for variant in variants.values()
                )
                else "not-supported-in-bounded-scan"
            ),
        },
        "scope": {
            "source_baselines_modified": False,
            "team_original_model_modified": False,
            "common_intermediate_cases_only": True,
            "power_measurement_port_held_common_within_each_variant": True,
            "ideal_limit_force_matched_to_fourteen_state_spectrum": False,
            "whole_system_hopf_margin_claimed": False,
            "modulation_dynamics_compared": False,
            "pll_or_frequency_estimator_compared": False,
            "external_network_dynamics_compared": False,
            "paper_sufficient_condition_evaluated": False,
            "statement": (
                "The scan reports branch-specific motion in two fourteen-state "
                "common intermediate models. Because the wide-frequency branch "
                "is already in the right half-plane, these results are not a "
                "whole-system Hopf stability-margin study."
            ),
        },
    }
