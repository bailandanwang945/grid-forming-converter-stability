"""Physical-frame first-order modulation lag for the Sienna/team bridge.

This module keeps the same fourteen-state common converter used by the
measurement-delay study, but places the modulation lag in a physical
stationary voltage frame.  Expressed in the converter-local dq frame, the
two modulation states therefore include the rotational cross term

    d(v_mod,dq)/dt = (v_cmd,dq - v_mod,dq)/T_mod - omega * J v_mod,dq.

The cross term distinguishes this model from the component-wise local-dq lag
in ``sienna_team_common_modulation_delay``.  It remains a first-order average
model; it is not an exact transport delay or a switching model.
"""

from __future__ import annotations

from math import pi

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import root

from backend.core.average_dq_model import J
from backend.core.sienna_team_active_power_measurement_delay import (
    source_common_active_power_delay_rhs_in_team_coordinates,
    team_common_active_power_delay_rhs,
)
from backend.core.sienna_team_common_modulation_delay import (
    ACTIVE_POWER_TIME_CONSTANT_S,
    MODULATION_LEVELS_S,
    POWER_PORT,
    TEAM_DECLARED_MODULATION_TIME_CONSTANT_S,
    _probe_state,
    _source_converter_voltage_reference,
    _team_converter_voltage_reference,
    _validate_modulation_time_constant,
    solve_common_modulation_delay_equilibrium,
    team_common_modulation_delay_rhs,
)
from backend.core.sienna_team_common_outer_loop import (
    CommonOuterLoopParameters,
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


def team_physical_modulation_lag_rhs(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    modulation_time_constant_s: float,
) -> NDArray[np.float64]:
    """Evaluate the physical-frame lag in converter-local dq coordinates."""

    time_constant = _validate_modulation_time_constant(
        modulation_time_constant_s
    )
    state = _finite_vector(state_team, 16, "physical modulation state")
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
    voltage_reference = _team_converter_voltage_reference(state, parameters)
    omega_base = 2.0 * pi * parameters.inner.frequency_hz
    derivative[14:16] = (
        (voltage_reference - state[14:16]) / time_constant
        - omega_base * float(state[1]) * J @ state[14:16]
    )
    return derivative


def source_physical_modulation_lag_rhs_in_team_coordinates(
    state_team: ArrayLike,
    pcc_voltage_global: ArrayLike,
    parameters: CommonOuterLoopParameters,
    *,
    modulation_time_constant_s: float,
) -> NDArray[np.float64]:
    """Evaluate an independent global-frame realization, returned in team dq."""

    time_constant = _validate_modulation_time_constant(
        modulation_time_constant_s
    )
    state = _finite_vector(state_team, 16, "physical modulation state")
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    derivative = np.empty(16, dtype=np.float64)
    derivative[:14] = source_common_active_power_delay_rhs_in_team_coordinates(
        state[:14],
        pcc,
        parameters,
        power_port=POWER_PORT,
        active_power_time_constant_s=ACTIVE_POWER_TIME_CONSTANT_S,
    )

    theta = float(state[0])
    rotation = _rotation(theta)
    modulation_global = rotation @ state[14:16]
    source_lcl_derivative = sienna_lcl_rhs_global(
        np.kron(np.eye(3), rotation) @ state[8:14],
        np.concatenate((modulation_global, pcc)),
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

    voltage_reference_local = _source_converter_voltage_reference(
        state, parameters
    )
    omega_base = 2.0 * pi * parameters.inner.frequency_hz
    modulation_global_derivative = (
        (rotation @ voltage_reference_local - modulation_global)
        / time_constant
        - omega_base
        * parameters.system_frequency_pu
        * J
        @ modulation_global
    )
    derivative[14:16] = (
        rotation.T @ modulation_global_derivative
        - theta_derivative * J @ state[14:16]
    )
    return derivative


def solve_physical_modulation_lag_equilibrium(
    parameters: CommonOuterLoopParameters,
    *,
    modulation_time_constant_s: float,
    pcc_voltage_global: ArrayLike = (1.0, 0.0),
) -> NDArray[np.float64]:
    """Solve the loaded equilibrium because the rotational term shifts it."""

    _validate_modulation_time_constant(modulation_time_constant_s)
    pcc = _finite_vector(pcc_voltage_global, 2, "global PCC voltage")
    initial = solve_common_modulation_delay_equilibrium(
        parameters,
        modulation_time_constant_s=modulation_time_constant_s,
        pcc_voltage_global=pcc,
    )
    solution = root(
        lambda state: team_physical_modulation_lag_rhs(
            state,
            pcc,
            parameters,
            modulation_time_constant_s=modulation_time_constant_s,
        ),
        initial,
        method="lm",
        options={"ftol": 1.0e-13, "xtol": 1.0e-13, "gtol": 1.0e-13},
    )
    equilibrium = np.asarray(solution.x, dtype=np.float64)
    residual = float(
        np.linalg.norm(
            team_physical_modulation_lag_rhs(
                equilibrium,
                pcc,
                parameters,
                modulation_time_constant_s=modulation_time_constant_s,
            ),
            ord=np.inf,
        )
    )
    if not solution.success or residual > 1.0e-8:
        raise RuntimeError(
            "physical modulation equilibrium solve failed: "
            f"success={solution.success}, residual={residual:.3e}"
        )
    return equilibrium


def run_physical_modulation_frame_audit() -> dict[str, object]:
    """Compare equivalent realizations and non-equivalent lag placements."""

    parameters = frozen_common_outer_loop_parameters()
    pcc = np.array([1.0, 0.0], dtype=np.float64)
    points: list[dict[str, object]] = []
    maximum_matrix_difference = 0.0
    maximum_probe_difference = 0.0
    minimum_local_physical_difference = float("inf")

    for time_constant in MODULATION_LEVELS_S:
        equilibrium = solve_physical_modulation_lag_equilibrium(
            parameters,
            modulation_time_constant_s=time_constant,
            pcc_voltage_global=pcc,
        )
        team_matrix = _jacobian(
            lambda state: team_physical_modulation_lag_rhs(
                state,
                pcc,
                parameters,
                modulation_time_constant_s=time_constant,
            ),
            equilibrium,
        )
        source_matrix = _jacobian(
            lambda state: source_physical_modulation_lag_rhs_in_team_coordinates(
                state,
                pcc,
                parameters,
                modulation_time_constant_s=time_constant,
            ),
            equilibrium,
        )
        local_matrix = _jacobian(
            lambda state: team_common_modulation_delay_rhs(
                state,
                pcc,
                parameters,
                modulation_time_constant_s=time_constant,
            ),
            solve_common_modulation_delay_equilibrium(
                parameters,
                modulation_time_constant_s=time_constant,
                pcc_voltage_global=pcc,
            ),
        )
        probe = _probe_state(equilibrium)
        probe_difference = float(
            np.linalg.norm(
                team_physical_modulation_lag_rhs(
                    probe,
                    pcc,
                    parameters,
                    modulation_time_constant_s=time_constant,
                )
                - source_physical_modulation_lag_rhs_in_team_coordinates(
                    probe,
                    pcc,
                    parameters,
                    modulation_time_constant_s=time_constant,
                ),
                ord=np.inf,
            )
        )
        matrix_difference = float(np.max(np.abs(team_matrix - source_matrix)))
        local_physical_difference = float(
            np.max(np.abs(team_matrix - local_matrix))
        )
        maximum_matrix_difference = max(
            maximum_matrix_difference, matrix_difference
        )
        maximum_probe_difference = max(
            maximum_probe_difference, probe_difference
        )
        minimum_local_physical_difference = min(
            minimum_local_physical_difference, local_physical_difference
        )
        eigenvalues = np.linalg.eigvals(team_matrix)
        points.append(
            {
                "modulation_time_constant_s": time_constant,
                "equilibrium_residual_inf": float(
                    np.linalg.norm(
                        team_physical_modulation_lag_rhs(
                            equilibrium,
                            pcc,
                            parameters,
                            modulation_time_constant_s=time_constant,
                        ),
                        ord=np.inf,
                    )
                ),
                "off_equilibrium_rhs_difference_inf": probe_difference,
                "state_matrix_max_abs_difference_per_s": matrix_difference,
                "local_dq_vs_physical_matrix_difference_per_s": (
                    local_physical_difference
                ),
                "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
                "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
            }
        )

    equation_gate = 1.0e-5
    counterexample_minimum = 1.0
    passed = (
        maximum_matrix_difference <= equation_gate
        and maximum_probe_difference <= equation_gate
        and minimum_local_physical_difference >= counterexample_minimum
    )
    return {
        "schema_version": "gfm-sienna-team-physical-modulation-lag/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "state_count": 16,
            "modulation_time_constant_levels_s": list(MODULATION_LEVELS_S),
            "team_declared_modulation_time_constant_s": (
                TEAM_DECLARED_MODULATION_TIME_CONSTANT_S
            ),
            "team_local_equation": (
                "d(v_mod,dq)/dt=(v_cmd,dq-v_mod,dq)/T_mod "
                "- omega_base*frequency_pu*J*v_mod,dq"
            ),
            "source_global_equation": (
                "d(v_mod,global)/dt=(R(theta)*v_cmd,dq-v_mod,global)/T_mod "
                "- omega_base*system_frequency_pu*J*v_mod,global"
            ),
        },
        "verification_gates": {
            "equivalent_realization_difference_max_per_s": equation_gate,
            "non_equivalent_local_dq_difference_min_per_s": (
                counterexample_minimum
            ),
        },
        "maximum_state_matrix_difference_per_s": maximum_matrix_difference,
        "maximum_off_equilibrium_rhs_difference_inf": maximum_probe_difference,
        "minimum_local_dq_vs_physical_matrix_difference_per_s": (
            minimum_local_physical_difference
        ),
        "points": points,
        "scope": {
            "physical_frame_first_order_lag_compared": True,
            "local_dq_lag_used_as_non_equivalent_countermodel": True,
            "exact_transport_delay_compared": False,
            "pade_delay_approximation_compared": False,
            "switching_or_pwm_waveform_modeled": False,
            "statement": (
                "The audit establishes coordinate-equivalent realizations of "
                "one physical-frame first-order lag and rejects silent "
                "substitution by a component-wise local-dq lag."
            ),
        },
    }
