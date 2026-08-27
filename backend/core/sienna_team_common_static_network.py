"""Loaded common outer-loop model closed by the shared static network."""

from __future__ import annotations

from math import cos, sin

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import root

from backend.core.sienna_team_common_outer_loop import (
    POWER_PORTS,
    CommonOuterLoopParameters,
    frozen_common_outer_loop_parameters,
    solve_common_outer_loop_equilibrium,
    source_common_outer_loop_rhs_in_team_coordinates,
    team_common_outer_loop_rhs,
)
from backend.core.sienna_team_static_network_mapping import (
    source_static_terminal_voltage,
    team_static_terminal_voltage,
)


def _finite_state(value: ArrayLike) -> NDArray[np.float64]:
    state = np.asarray(value, dtype=np.float64)
    if state.shape != (13,) or not np.all(np.isfinite(state)):
        raise ValueError("common static-network state must be a finite length-13 vector")
    return state


def _rotation(angle_rad: float) -> NDArray[np.float64]:
    return np.array(
        [[cos(angle_rad), -sin(angle_rad)], [sin(angle_rad), cos(angle_rad)]],
        dtype=np.float64,
    )


def _grid_current_global(state: NDArray[np.float64]) -> NDArray[np.float64]:
    return _rotation(float(state[0])) @ state[11:13]


def _complex_vector(value: complex) -> NDArray[np.float64]:
    return np.array([value.real, value.imag], dtype=np.float64)


def team_common_static_network_rhs(
    state_team: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
) -> NDArray[np.float64]:
    """Close the team-coordinate path through the shared static network."""

    state = _finite_state(state_team)
    converter_to_network = _grid_current_global(state)
    pcc = team_static_terminal_voltage(-converter_to_network)
    return team_common_outer_loop_rhs(
        state,
        _complex_vector(pcc),
        parameters,
        power_port=power_port,
    )


def source_common_static_network_rhs_in_team_coordinates(
    state_team: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    power_port: str,
) -> NDArray[np.float64]:
    """Close the source-coordinate path and return its team-coordinate derivative."""

    state = _finite_state(state_team)
    converter_to_network = _grid_current_global(state)
    pcc = source_static_terminal_voltage(converter_to_network)
    return source_common_outer_loop_rhs_in_team_coordinates(
        state,
        _complex_vector(pcc),
        parameters,
        power_port=power_port,
    )


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


def _solve_equilibrium(
    parameters: CommonOuterLoopParameters,
    power_port: str,
) -> NDArray[np.float64]:
    guess = solve_common_outer_loop_equilibrium(
        parameters,
        power_port=power_port,
        pcc_voltage_global=(1.0, 0.0),
    )
    solution = root(
        lambda state: team_common_static_network_rhs(
            state, parameters, power_port=power_port
        ),
        guess,
        method="hybr",
        options={"xtol": 1.0e-11, "maxfev": 5000},
    )
    residual = team_common_static_network_rhs(
        solution.x, parameters, power_port=power_port
    )
    if not solution.success or np.linalg.norm(residual, ord=np.inf) > 1.0e-8:
        raise RuntimeError(
            "common static-network equilibrium failed for "
            f"{power_port}: {solution.message}; "
            f"residual={np.linalg.norm(residual, ord=np.inf):.3e}"
        )
    return np.asarray(solution.x, dtype=np.float64)


def run_common_static_network_audit() -> dict[str, object]:
    """Verify two independent equation paths at loaded network equilibria."""

    parameters = frozen_common_outer_loop_parameters()
    variants: dict[str, object] = {}
    maximum_matrix_difference = 0.0
    maximum_probe_difference = 0.0
    maximum_residual = 0.0
    minimum_network_effect = float("inf")
    for power_port in POWER_PORTS:
        equilibrium = _solve_equilibrium(parameters, power_port)

        def team_rhs(state: NDArray[np.float64]) -> NDArray[np.float64]:
            return team_common_static_network_rhs(
                state, parameters, power_port=power_port
            )

        def source_rhs(state: NDArray[np.float64]) -> NDArray[np.float64]:
            return source_common_static_network_rhs_in_team_coordinates(
                state, parameters, power_port=power_port
            )

        team_matrix = _jacobian(team_rhs, equilibrium)
        source_matrix = _jacobian(source_rhs, equilibrium)
        fixed_pcc_matrix = _jacobian(
            lambda state: team_common_outer_loop_rhs(
                state,
                (1.0, 0.0),
                parameters,
                power_port=power_port,
            ),
            equilibrium,
        )
        probe = equilibrium.copy()
        probe[0] += 0.013
        probe[9] -= 0.017
        probe[12] += 0.021
        residual = float(np.linalg.norm(team_rhs(equilibrium), ord=np.inf))
        probe_difference = float(
            np.linalg.norm(team_rhs(probe) - source_rhs(probe), ord=np.inf)
        )
        matrix_difference = float(
            np.max(np.abs(team_matrix - source_matrix))
        )
        network_effect = float(np.max(np.abs(team_matrix - fixed_pcc_matrix)))
        eigenvalues = np.linalg.eigvals(team_matrix)
        maximum_residual = max(maximum_residual, residual)
        maximum_probe_difference = max(maximum_probe_difference, probe_difference)
        maximum_matrix_difference = max(
            maximum_matrix_difference, matrix_difference
        )
        minimum_network_effect = min(minimum_network_effect, network_effect)
        pcc = source_static_terminal_voltage(_grid_current_global(equilibrium))
        variants[power_port] = {
            "equilibrium_residual_inf": residual,
            "off_equilibrium_rhs_difference_inf": probe_difference,
            "state_matrix_max_abs_difference_per_s": matrix_difference,
            "static_network_effect_max_abs_per_s": network_effect,
            "pcc_voltage_pu": [float(pcc.real), float(pcc.imag)],
            "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
            "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
        }

    equation_gate = 1.0e-5
    residual_gate = 1.0e-8
    network_effect_gate = 1.0e-3
    passed = bool(
        maximum_residual <= residual_gate
        and maximum_probe_difference <= equation_gate
        and maximum_matrix_difference <= equation_gate
        and minimum_network_effect >= network_effect_gate
    )
    return {
        "schema_version": "gfm-sienna-team-common-static-network/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "state_count": 13,
            "network_state_count": 0,
            "power_ports": list(POWER_PORTS),
            "network_realization": "static algebraic two-bus network",
        },
        "verification_gates": {
            "equilibrium_residual_inf_max": residual_gate,
            "rhs_and_matrix_difference_max_per_s": equation_gate,
            "static_network_effect_min_per_s": network_effect_gate,
        },
        "verification_summary": {
            "maximum_equilibrium_residual_inf": maximum_residual,
            "maximum_off_equilibrium_rhs_difference_inf": (
                maximum_probe_difference
            ),
            "maximum_state_matrix_difference_per_s": (
                maximum_matrix_difference
            ),
            "minimum_static_network_effect_per_s": minimum_network_effect,
        },
        "variants": variants,
        "scope": {
            "common_loaded_operating_points_aligned": passed,
            "common_static_network_coupling_included": True,
            "source_or_team_original_full_model_replaced": False,
            "original_dynamic_line_isomorphism_claimed": False,
            "original_full_model_eigenvalues_comparable": False,
            "statement": (
                "The audit closes two thirteen-state common intermediate "
                "models through the verified algebraic two-bus network. It "
                "does not replace the team's dynamic RL line or align all "
                "states of either original full model."
            ),
        },
    }
