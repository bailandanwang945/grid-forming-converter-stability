"""Shared Kaura-PLL measurement-position study for the Sienna/team bridge.

The study augments the verified fourteen-state common active-power-delay model
with the four Test-08 Kaura PLL states.  Both equation paths receive the same
PLL and damping equations.  It remains an intermediate model, not either
original complete converter.
"""

from __future__ import annotations

from math import atan2, pi

import numpy as np
from numpy.typing import ArrayLike, NDArray

from backend.core.average_dq_ablation import (
    ModalSignature,
    match_modes,
    modal_signature,
)
from backend.core.sienna_team_active_power_measurement_delay import (
    _point_matrices,
    _pole_payload,
    _team_to_source_state,
    solve_common_active_power_delay_equilibrium,
    source_common_active_power_delay_rhs_in_team_coordinates,
    team_common_active_power_delay_rhs,
)
from backend.core.sienna_team_common_outer_loop import (
    _finite_vector,
    _jacobian,
    _rotation,
    frozen_common_outer_loop_parameters,
)


PLL_VOLTAGE_PORTS = ("filter_capacitor", "pcc")
POWER_PORT = "pcc"
ACTIVE_POWER_TIME_CONSTANT_S = 0.1
PLL_CUTOFF_RAD_S = 500.0
PLL_KP = 0.084
PLL_KI = 4.69
DAMPING_LEVELS = (0.0, 400.0)
CONTINUATION_DAMPING_LEVELS = (50.0, 100.0, 200.0, 300.0, 400.0)


class CommonPllMeasurementError(ValueError):
    """Raised when the frozen common PLL contract is violated."""


def _validate_voltage_port(voltage_port: str) -> None:
    if voltage_port not in PLL_VOLTAGE_PORTS:
        raise CommonPllMeasurementError(
            f"PLL voltage port must be one of {PLL_VOLTAGE_PORTS}"
        )


def _validate_damping_gain(damping_gain: float) -> None:
    if not np.isfinite(damping_gain) or not 0.0 <= damping_gain <= 400.0:
        raise CommonPllMeasurementError(
            "damping gain must be finite and within [0, 400]"
        )


def _pll_voltage_global_from_team(
    state: NDArray[np.float64],
    pcc: NDArray[np.float64],
    voltage_port: str,
) -> NDArray[np.float64]:
    if voltage_port == "pcc":
        return pcc
    return _rotation(float(state[0])) @ state[10:12]


def _pll_voltage_global_from_source(
    state: NDArray[np.float64],
    pcc: NDArray[np.float64],
    voltage_port: str,
) -> NDArray[np.float64]:
    if voltage_port == "pcc":
        return pcc
    parameters = frozen_common_outer_loop_parameters()
    source = _team_to_source_state(state[:14], parameters)
    return source[10:12]


def _pll_derivative(
    pll_state: NDArray[np.float64],
    measured_voltage_global: NDArray[np.float64],
    frequency_hz: float,
) -> tuple[NDArray[np.float64], float]:
    filtered_voltage = pll_state[0:2]
    integral = float(pll_state[2])
    angle = float(pll_state[3])
    measured_pll = _rotation(-angle) @ measured_voltage_global
    error = atan2(float(filtered_voltage[1]), float(filtered_voltage[0]))
    pi_output = PLL_KP * error + PLL_KI * integral
    derivative = np.empty(4, dtype=np.float64)
    derivative[0:2] = PLL_CUTOFF_RAD_S * (
        measured_pll - filtered_voltage
    )
    derivative[2] = error
    derivative[3] = 2.0 * pi * frequency_hz * pi_output
    return derivative, 1.0 + pi_output


def team_common_pll_rhs(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    *,
    pll_voltage_port: str,
    damping_gain: float,
) -> NDArray[np.float64]:
    """Evaluate the eighteen-state common model through the team path."""

    _validate_voltage_port(pll_voltage_port)
    _validate_damping_gain(damping_gain)
    parameters = frozen_common_outer_loop_parameters()
    state = _finite_vector(state_team, 18, "common PLL state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    derivative = np.empty(18, dtype=np.float64)
    derivative[:14] = team_common_active_power_delay_rhs(
        state[:14],
        pcc,
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
    )
    pll_derivative, pll_frequency = _pll_derivative(
        state[14:18],
        _pll_voltage_global_from_team(state, pcc, pll_voltage_port),
        parameters.inner.frequency_hz,
    )
    derivative[1] -= damping_gain * (state[1] - pll_frequency) / (
        parameters.inertia_time_constant_s
    )
    derivative[14:18] = pll_derivative
    return derivative


def source_common_pll_rhs_in_team_coordinates(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    *,
    pll_voltage_port: str,
    damping_gain: float,
) -> NDArray[np.float64]:
    """Evaluate the independently augmented source path in team coordinates."""

    _validate_voltage_port(pll_voltage_port)
    _validate_damping_gain(damping_gain)
    parameters = frozen_common_outer_loop_parameters()
    state = _finite_vector(state_team, 18, "common PLL state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    derivative = np.empty(18, dtype=np.float64)
    derivative[:14] = source_common_active_power_delay_rhs_in_team_coordinates(
        state[:14],
        pcc,
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
    )
    pll_derivative, pll_frequency = _pll_derivative(
        state[14:18],
        _pll_voltage_global_from_source(state, pcc, pll_voltage_port),
        parameters.inner.frequency_hz,
    )
    derivative[1] -= damping_gain * (state[1] - pll_frequency) / (
        parameters.inertia_time_constant_s
    )
    derivative[14:18] = pll_derivative
    return derivative


def common_pll_equilibrium(
    *, pll_voltage_port: str, damping_gain: float
) -> NDArray[np.float64]:
    """Construct and verify the loaded synchronous equilibrium."""

    _validate_voltage_port(pll_voltage_port)
    parameters = frozen_common_outer_loop_parameters()
    pcc = np.array([1.0, 0.0], dtype=np.float64)
    base = solve_common_active_power_delay_equilibrium(
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
        pcc_voltage_global=pcc,
    )
    voltage = _pll_voltage_global_from_team(
        np.concatenate((base, np.zeros(4))), pcc, pll_voltage_port
    )
    angle = atan2(float(voltage[1]), float(voltage[0]))
    pll_voltage = _rotation(-angle) @ voltage
    state = np.concatenate((base, pll_voltage, np.array([0.0, angle])))
    residual = team_common_pll_rhs(
        state,
        pcc,
        pll_voltage_port=pll_voltage_port,
        damping_gain=damping_gain,
    )
    if float(np.linalg.norm(residual, ord=np.inf)) > 1.0e-8:
        raise RuntimeError("common PLL equilibrium residual exceeds 1e-8")
    return state


def _mode_near(
    matrix: NDArray[np.float64], target: complex
) -> ModalSignature:
    candidates = [
        complex(value)
        for value in np.linalg.eigvals(matrix)
        if value.imag > 1.0e-8
    ]
    return modal_signature(matrix, min(candidates, key=lambda value: abs(value - target)))


def _case(
    voltage_port: str,
    damping_gain: float,
    references: tuple[ModalSignature, ModalSignature] | None,
) -> tuple[dict[str, object], tuple[ModalSignature, ModalSignature]]:
    parameters = frozen_common_outer_loop_parameters()
    pcc = np.array([1.0, 0.0], dtype=np.float64)
    equilibrium = common_pll_equilibrium(
        pll_voltage_port=voltage_port, damping_gain=damping_gain
    )
    team_matrix = _jacobian(
        lambda state: team_common_pll_rhs(
            state,
            pcc,
            pll_voltage_port=voltage_port,
            damping_gain=damping_gain,
        ),
        equilibrium,
    )
    source_matrix = _jacobian(
        lambda state: source_common_pll_rhs_in_team_coordinates(
            state,
            pcc,
            pll_voltage_port=voltage_port,
            damping_gain=damping_gain,
        ),
        equilibrium,
    )
    _, base_matrix, _ = _point_matrices(
        parameters, pcc, POWER_PORT, ACTIVE_POWER_TIME_CONSTANT_S
    )
    base_values = [
        complex(value) for value in np.linalg.eigvals(base_matrix) if value.imag > 0
    ]
    base_low = min(base_values, key=lambda value: abs(value.imag / (2 * pi) - 2.2))
    base_wide = min(base_values, key=lambda value: abs(value.imag / (2 * pi) - 111.6))
    if references is None:
        signatures = (
            _mode_near(team_matrix, base_low),
            _mode_near(team_matrix, base_wide),
        )
        tracking = (
            {"status": "anchor", "reason": "nearest-fourteen-state-mode"},
            {"status": "anchor", "reason": "nearest-fourteen-state-mode"},
        )
    else:
        matches = match_modes(references, team_matrix)
        signatures = tuple(
            modal_signature(team_matrix, match.eigenvalue_per_s)
            for match in matches
        )
        tracking = tuple(
            {
                "status": match.status,
                "reason": match.reason,
                "right_mac": match.right_mac,
                "left_mac": match.left_mac,
                "normalized_eigenvalue_distance": match.normalized_distance,
                "condition_number": match.condition_number,
            }
            for match in matches
        )
    team_rhs = team_common_pll_rhs(
        equilibrium,
        pcc,
        pll_voltage_port=voltage_port,
        damping_gain=damping_gain,
    )
    source_rhs = source_common_pll_rhs_in_team_coordinates(
        equilibrium,
        pcc,
        pll_voltage_port=voltage_port,
        damping_gain=damping_gain,
    )
    eigenvalues = np.linalg.eigvals(team_matrix)
    return (
        {
            "pll_voltage_port": voltage_port,
            "damping_gain": damping_gain,
            "equilibrium_residual_inf": float(np.linalg.norm(team_rhs, ord=np.inf)),
            "rhs_difference_inf": float(np.linalg.norm(team_rhs - source_rhs, ord=np.inf)),
            "state_matrix_max_abs_difference_per_s": float(
                np.max(np.abs(team_matrix - source_matrix))
            ),
            "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
            "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
            "low_frequency_mode": {
                "pole": _pole_payload(signatures[0].eigenvalue_per_s),
                "tracking": tracking[0],
            },
            "wide_frequency_mode": {
                "pole": _pole_payload(signatures[1].eigenvalue_per_s),
                "tracking": tracking[1],
            },
            "negative_control": {
                "base_submatrix_max_abs_difference_per_s": float(
                    np.max(np.abs(team_matrix[:14, :14] - base_matrix))
                ),
                "pll_to_converter_feedback_max_abs_per_s": float(
                    np.max(np.abs(team_matrix[:14, 14:18]))
                ),
            },
        },
        signatures,
    )


def _trace_to_damping(
    voltage_port: str,
    start_damping: float,
    target_damping: float,
    references: tuple[ModalSignature, ModalSignature],
    *,
    remaining_depth: int = 7,
) -> tuple[
    dict[str, object],
    tuple[ModalSignature, ModalSignature],
    list[dict[str, object]],
    bool,
]:
    case, candidate_references = _case(
        voltage_port, target_damping, references
    )
    resolved = all(
        case[mode]["tracking"]["status"] == "matched"
        for mode in ("low_frequency_mode", "wide_frequency_mode")
    )
    attempt = {
        "from_damping_gain": start_damping,
        "to_damping_gain": target_damping,
        "resolved": resolved,
        "low_mode_status": case["low_frequency_mode"]["tracking"]["status"],
        "low_mode_reason": case["low_frequency_mode"]["tracking"]["reason"],
        "wide_mode_status": case["wide_frequency_mode"]["tracking"]["status"],
        "wide_mode_reason": case["wide_frequency_mode"]["tracking"]["reason"],
    }
    if resolved or remaining_depth == 0:
        return case, candidate_references, [attempt], resolved

    midpoint = 0.5 * (start_damping + target_damping)
    middle_case, middle_references, middle_history, middle_resolved = (
        _trace_to_damping(
            voltage_port,
            start_damping,
            midpoint,
            references,
            remaining_depth=remaining_depth - 1,
        )
    )
    if not middle_resolved:
        return case, references, [attempt, *middle_history], False
    end_case, end_references, end_history, end_resolved = _trace_to_damping(
        voltage_port,
        midpoint,
        target_damping,
        middle_references,
        remaining_depth=remaining_depth - 1,
    )
    return (
        end_case,
        end_references,
        [attempt, *middle_history, *end_history],
        end_resolved,
    )


def run_common_pll_measurement_audit() -> dict[str, object]:
    """Run the preregistered two-position by two-damping common PLL study."""

    cases: dict[str, dict[str, object]] = {}
    off_references: dict[str, tuple[ModalSignature, ModalSignature]] = {}
    for voltage_port in PLL_VOLTAGE_PORTS:
        off, references = _case(voltage_port, 0.0, None)
        cases[f"{voltage_port}__damping_off"] = off
        off_references[voltage_port] = references
        on, _, history, resolved = _trace_to_damping(
            voltage_port, 0.0, 400.0, references
        )
        on["continuation"] = {
            "status": "resolved" if resolved else "pending",
            "adaptive_bisection_max_depth": 7,
            "attempt_count": len(history),
            "attempts": history,
        }
        cases[f"{voltage_port}__damping_on"] = on

    equation_gate = 1.0e-5
    negative_gate = 1.0e-8
    all_equations_match = all(
        case["equilibrium_residual_inf"] <= 1.0e-8
        and case["rhs_difference_inf"] <= equation_gate
        and case["state_matrix_max_abs_difference_per_s"] <= equation_gate
        for case in cases.values()
    )
    negative_control_passed = all(
        cases[f"{port}__damping_off"]["negative_control"][
            "base_submatrix_max_abs_difference_per_s"
        ]
        <= negative_gate
        and cases[f"{port}__damping_off"]["negative_control"][
            "pll_to_converter_feedback_max_abs_per_s"
        ]
        <= negative_gate
        for port in PLL_VOLTAGE_PORTS
    )
    all_tracking_resolved = all(
        case[mode]["tracking"]["status"] in {"anchor", "matched"}
        for case in cases.values()
        for mode in ("low_frequency_mode", "wide_frequency_mode")
    )
    low_position_difference = (
        abs(
            cases["filter_capacitor__damping_on"]["low_frequency_mode"]["pole"][
                "real_per_s"
            ]
            - cases["pcc__damping_on"]["low_frequency_mode"]["pole"][
                "real_per_s"
            ]
        )
        if all_tracking_resolved
        else None
    )
    passed = all_equations_match and negative_control_passed
    return {
        "schema_version": "gfm-sienna-team-common-pll-measurement/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "state_count": 18,
            "base_state_count": 14,
            "power_measurement_port": POWER_PORT,
            "active_power_time_constant_s": ACTIVE_POWER_TIME_CONSTANT_S,
            "pll_voltage_ports": list(PLL_VOLTAGE_PORTS),
            "pll_cutoff_rad_s": PLL_CUTOFF_RAD_S,
            "pll_kp": PLL_KP,
            "pll_ki": PLL_KI,
            "damping_levels": list(DAMPING_LEVELS),
            "damping_equation": "-kd * (omega_vsm - omega_pll) / Ta",
        },
        "verification_gates": {
            "equilibrium_residual_inf_max": 1.0e-8,
            "rhs_and_matrix_difference_max_per_s": equation_gate,
            "negative_control_max_per_s": negative_gate,
        },
        "cases": cases,
        "hypothesis_tests": {
            "four_common_equations_match": all_equations_match,
            "damping_off_is_structural_negative_control": negative_control_passed,
            "named_modes_resolved": all_tracking_resolved,
            "damping_on_low_mode_real_part_position_difference_per_s": (
                float(low_position_difference)
                if low_position_difference is not None
                else None
            ),
            "measurement_position_effect_conclusion": (
                "resolved"
                if all_tracking_resolved
                else "pending-because-a-named-mode-crosses-or-approaches-real-axis"
            ),
        },
        "scope": {
            "source_baselines_modified": False,
            "team_original_model_modified": False,
            "common_intermediate_cases_only": True,
            "pll_measurement_position_and_damping_separated": True,
            "pll_gain_scan_performed": False,
            "whole_system_hopf_margin_claimed": False,
            "modulation_or_external_network_dynamics_compared": False,
            "paper_sufficient_condition_evaluated": False,
            "statement": (
                "The four cases isolate PLL voltage measurement position from "
                "the VSM damping feedback switch. They do not establish a "
                "unique PLL mechanism or a whole-system stability margin."
            ),
        },
    }
