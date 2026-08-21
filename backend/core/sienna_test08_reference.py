"""Independent Python transcription of Sienna PSID Test 08.

The equations in this module follow the fixed ``PowerSimulationsDynamics.jl``
v0.16.2 component sources and the ``PowerSystemCaseBuilder.jl`` v2.6.0 Test 08
system definition.  It is a verification reference, not a product dependency
and not a claim that the Julia test has been executed on this machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, pi, sin

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import linear_sum_assignment

from backend.core.sienna_team_common_active_damping import (
    sienna_team_common_active_damping_audit,
)
from backend.core.sienna_team_inner_loop_modal_fingerprint import (
    run_common_inner_loop_modal_fingerprint,
)
from backend.core.sienna_team_common_outer_loop import (
    run_common_outer_loop_audit,
)
from backend.core.sienna_team_common_inner_loop import (
    CommonInnerLoopParameters,
    sienna_team_common_inner_loop_audit,
)
from backend.core.sienna_team_inner_control_mapping import (
    CascadedPIParameters,
    sienna_team_inner_control_mapping_audit,
)
from backend.core.sienna_team_lcl_isomorphism import (
    CommonLCLParameters,
    sienna_team_common_lcl_audit,
)


STATE_LABELS = (
    "theta_outer_rad",
    "omega_outer_pu",
    "measured_reactive_power_pu",
    "voltage_integrator_d",
    "voltage_integrator_q",
    "current_integrator_d",
    "current_integrator_q",
    "active_damping_filter_d_pu",
    "active_damping_filter_q_pu",
    "pll_voltage_d_pu",
    "pll_voltage_q_pu",
    "pll_integrator",
    "pll_angle_rad",
    "converter_current_real_pu",
    "converter_current_imag_pu",
    "filter_voltage_real_pu",
    "filter_voltage_imag_pu",
    "grid_current_real_pu",
    "grid_current_imag_pu",
)

FROZEN_INITIAL_STATE = np.array(
    [
        0.1978641793142158,
        1.0,
        0.04541511706491953,
        0.0006674495903061723,
        -0.00012674142328973991,
        0.0703325301924954,
        -0.006874509029034731,
        1.0042596418725966,
        -0.09824857969306856,
        1.0090541173324878,
        -1.3552527156068803e-23,
        0.0,
        0.1003426665815884,
        0.49251497972474095,
        0.07939915329276713,
        1.0039784714785935,
        0.10108135591344172,
        0.49999500006233566,
        0.005104746403351219,
    ],
    dtype=np.float64,
)

FROZEN_EIGENVALUES_PER_S = np.array(
    [
        -2285.9589650663725 - 6825.3997886670795j,
        -2285.9589650663725 + 6825.3997886670795j,
        -2095.818014258244 - 6533.140681149019j,
        -2095.818014258244 + 6533.140681149019j,
        -1595.4562252195476 - 233.8877642497275j,
        -1595.4562252195476 + 233.8877642497275j,
        -986.7365548177571 + 0.0j,
        -500.00000000000034 + 0.0j,
        -471.8999089077167 + 0.0j,
        -220.89110522830256 + 0.0j,
        -50.32121120551376 + 0.0j,
        -50.245608339393456 + 0.0j,
        -34.244848184557476 - 260.53071319880445j,
        -34.244848184557476 + 260.53071319880445j,
        -11.303322380605753 + 0.0j,
        -11.19036178279552 + 0.0j,
        -7.691789694217273 - 28.802262759948757j,
        -7.691789694217273 + 28.802262759948757j,
        -4.513698394541721 + 0.0j,
    ],
    dtype=np.complex128,
)


@dataclass(frozen=True)
class SiennaTest08Parameters:
    # The source-transcribed Jacobian matches the frozen Test 08 eigenvalues
    # only with the 60 Hz system base used by that result.  Substituting the
    # legacy RAW header's trailing 50 scales the fast electrical modes by 5/6.
    # This observed discrepancy remains explicit rather than being hidden in
    # a parameter fit.
    frequency_hz: float = 60.0
    system_base_power_mva: float = 100.0
    device_base_power_mva: float = 2.75
    infinite_bus_voltage_pu: complex = (
        1.0000099992980975 + 6.874931250857116e-8j
    )
    network_resistance_pu_system_base: float = 0.0
    network_reactance_pu_system_base: float = 0.075
    # PSID initialization updates the dynamic references to the solved internal
    # active/reactive power and voltage-controller reference.  The static RAW
    # generator remains a 0.5 p.u. terminal-power operating point.
    active_power_reference_pu: float = 0.502500210597568
    reactive_power_reference_pu: float = 0.04541511706491953
    voltage_reference_pu: float = 1.0229159793808522
    frequency_reference_pu: float = 1.0
    system_frequency_pu: float = 1.0
    inertia_time_constant_s: float = 2.0
    damping_gain: float = 400.0
    frequency_droop_gain: float = 20.0
    reactive_power_droop_gain: float = 0.2
    reactive_power_filter_cutoff_rad_s: float = 1000.0
    voltage_kp: float = 0.59
    voltage_ki: float = 736.0
    current_feedforward: float = 0.0
    virtual_resistance_pu: float = 0.0
    virtual_reactance_pu: float = 0.2
    current_kp: float = 1.27
    current_ki: float = 14.3
    voltage_feedforward: float = 0.0
    active_damping_cutoff_rad_s: float = 50.0
    active_damping_gain: float = 0.2
    pll_cutoff_rad_s: float = 500.0
    pll_kp: float = 0.084
    pll_ki: float = 4.69
    converter_side_resistance_pu: float = 0.003
    converter_side_reactance_pu: float = 0.08
    filter_capacitor_susceptance_pu: float = 0.074
    grid_side_resistance_pu: float = 0.01
    grid_side_reactance_pu: float = 0.2


@dataclass(frozen=True)
class SiennaTest08Audit:
    initial_residual_inf: float
    reconstructed_terminal_voltage: complex
    expected_terminal_voltage: complex
    terminal_voltage_error: float
    eigenvalues_per_s: NDArray[np.complex128]
    matched_eigenvalue_max_error_per_s: float
    matched_eigenvalue_l2_error_per_s: float


def _rotation(angle_rad: float) -> NDArray[np.float64]:
    return np.array(
        [[cos(angle_rad), -sin(angle_rad)], [sin(angle_rad), cos(angle_rad)]],
        dtype=np.float64,
    )


def terminal_voltage_from_grid_current(
    grid_current_device_pu: ArrayLike,
    parameters: SiennaTest08Parameters = SiennaTest08Parameters(),
) -> complex:
    """Eliminate the two-bus network using the Sienna current-base conversion."""

    current = np.asarray(grid_current_device_pu, dtype=np.float64)
    if current.shape != (2,) or not np.all(np.isfinite(current)):
        raise ValueError("grid current must be a finite two-vector")
    current_system_pu = (
        parameters.device_base_power_mva
        / parameters.system_base_power_mva
        * complex(float(current[0]), float(current[1]))
    )
    impedance = complex(
        parameters.network_resistance_pu_system_base,
        parameters.network_reactance_pu_system_base,
    )
    return parameters.infinite_bus_voltage_pu + impedance * current_system_pu


def sienna_test08_rhs(
    state: ArrayLike,
    parameters: SiennaTest08Parameters = SiennaTest08Parameters(),
) -> NDArray[np.float64]:
    """Evaluate the source-transcribed 19-state Test 08 vector field."""

    x = np.asarray(state, dtype=np.float64)
    if x.shape != (19,) or not np.all(np.isfinite(x)):
        raise ValueError("Sienna Test 08 state must be a finite length-19 vector")

    theta_outer, omega_outer, measured_q = x[0:3]
    voltage_integrator = x[3:5]
    current_integrator = x[5:7]
    active_damping_filter = x[7:9]
    pll_voltage = x[9:11]
    pll_integrator = float(x[11])
    pll_angle = float(x[12])
    converter_current_ri = x[13:15]
    filter_voltage_ri = x[15:17]
    grid_current_ri = x[17:19]

    omega_base = 2.0 * pi * parameters.frequency_hz
    terminal_voltage = terminal_voltage_from_grid_current(
        grid_current_ri, parameters
    )
    terminal_voltage_ri = np.array(
        [terminal_voltage.real, terminal_voltage.imag], dtype=np.float64
    )

    pll_rotation = _rotation(-pll_angle)
    filter_voltage_pll = pll_rotation @ filter_voltage_ri
    pll_error = atan2(float(pll_voltage[1]), float(pll_voltage[0]))
    pll_pi_output = parameters.pll_kp * pll_error + parameters.pll_ki * pll_integrator
    omega_pll = parameters.system_frequency_pu + pll_pi_output

    active_power = float(grid_current_ri @ filter_voltage_ri)
    reactive_power = float(
        -grid_current_ri[1] * filter_voltage_ri[0]
        + grid_current_ri[0] * filter_voltage_ri[1]
    )
    voltage_outer = parameters.voltage_reference_pu + (
        parameters.reactive_power_droop_gain
        * (parameters.reactive_power_reference_pu - measured_q)
    )

    control_rotation = _rotation(-theta_outer)
    grid_current_dq = control_rotation @ grid_current_ri
    converter_current_dq = control_rotation @ converter_current_ri
    filter_voltage_dq = control_rotation @ filter_voltage_ri
    voltage_reference_dq = np.array(
        [voltage_outer, 0.0], dtype=np.float64
    )
    voltage_reference_dq += np.array(
        [
            -parameters.virtual_resistance_pu * grid_current_dq[0]
            + omega_outer
            * parameters.virtual_reactance_pu
            * grid_current_dq[1],
            -parameters.virtual_resistance_pu * grid_current_dq[1]
            - omega_outer
            * parameters.virtual_reactance_pu
            * grid_current_dq[0],
        ],
        dtype=np.float64,
    )
    voltage_error = voltage_reference_dq - filter_voltage_dq
    voltage_pi = (
        parameters.voltage_kp * voltage_error
        + parameters.voltage_ki * voltage_integrator
    )
    converter_current_reference = voltage_pi + np.array(
        [
            -parameters.filter_capacitor_susceptance_pu
            * omega_outer
            * filter_voltage_dq[1]
            + parameters.current_feedforward * grid_current_dq[0],
            parameters.filter_capacitor_susceptance_pu
            * omega_outer
            * filter_voltage_dq[0]
            + parameters.current_feedforward * grid_current_dq[1],
        ],
        dtype=np.float64,
    )
    current_error = converter_current_reference - converter_current_dq
    current_pi = (
        parameters.current_kp * current_error
        + parameters.current_ki * current_integrator
    )
    converter_voltage_reference_dq = current_pi + np.array(
        [
            -omega_outer
            * parameters.converter_side_reactance_pu
            * converter_current_dq[1]
            + parameters.voltage_feedforward * filter_voltage_dq[0]
            - parameters.active_damping_gain
            * (filter_voltage_dq[0] - active_damping_filter[0]),
            omega_outer
            * parameters.converter_side_reactance_pu
            * converter_current_dq[0]
            + parameters.voltage_feedforward * filter_voltage_dq[1]
            - parameters.active_damping_gain
            * (filter_voltage_dq[1] - active_damping_filter[1]),
        ],
        dtype=np.float64,
    )
    converter_voltage_ri = _rotation(theta_outer) @ converter_voltage_reference_dq

    derivative = np.empty(19, dtype=np.float64)
    derivative[0] = omega_base * (
        omega_outer - parameters.system_frequency_pu
    )
    derivative[1] = (
        parameters.active_power_reference_pu
        - active_power
        - parameters.damping_gain * (omega_outer - omega_pll)
        - parameters.frequency_droop_gain
        * (omega_outer - parameters.frequency_reference_pu)
    ) / parameters.inertia_time_constant_s
    derivative[2] = parameters.reactive_power_filter_cutoff_rad_s * (
        reactive_power - measured_q
    )
    derivative[3:5] = voltage_error
    derivative[5:7] = current_error
    derivative[7:9] = parameters.active_damping_cutoff_rad_s * (
        filter_voltage_dq - active_damping_filter
    )
    derivative[9:11] = parameters.pll_cutoff_rad_s * (
        filter_voltage_pll - pll_voltage
    )
    derivative[11] = pll_error
    derivative[12] = omega_base * pll_pi_output

    rf = parameters.converter_side_resistance_pu
    xf = parameters.converter_side_reactance_pu
    bc = parameters.filter_capacitor_susceptance_pu
    rg = parameters.grid_side_resistance_pu
    xg = parameters.grid_side_reactance_pu
    omega_system = parameters.system_frequency_pu
    derivative[13] = omega_base / xf * (
        converter_voltage_ri[0]
        - filter_voltage_ri[0]
        - rf * converter_current_ri[0]
        + xf * omega_system * converter_current_ri[1]
    )
    derivative[14] = omega_base / xf * (
        converter_voltage_ri[1]
        - filter_voltage_ri[1]
        - rf * converter_current_ri[1]
        - xf * omega_system * converter_current_ri[0]
    )
    derivative[15] = omega_base / bc * (
        converter_current_ri[0]
        - grid_current_ri[0]
        + bc * omega_system * filter_voltage_ri[1]
    )
    derivative[16] = omega_base / bc * (
        converter_current_ri[1]
        - grid_current_ri[1]
        - bc * omega_system * filter_voltage_ri[0]
    )
    derivative[17] = omega_base / xg * (
        filter_voltage_ri[0]
        - terminal_voltage_ri[0]
        - rg * grid_current_ri[0]
        + xg * omega_system * grid_current_ri[1]
    )
    derivative[18] = omega_base / xg * (
        filter_voltage_ri[1]
        - terminal_voltage_ri[1]
        - rg * grid_current_ri[1]
        - xg * omega_system * grid_current_ri[0]
    )
    return derivative


def linearize_sienna_test08(
    state: ArrayLike = FROZEN_INITIAL_STATE,
    parameters: SiennaTest08Parameters = SiennaTest08Parameters(),
    relative_step: float = 1.0e-6,
) -> NDArray[np.float64]:
    """Central-difference the independent 19-state vector field."""

    x = np.asarray(state, dtype=np.float64)
    if x.shape != (19,) or not np.all(np.isfinite(x)):
        raise ValueError("linearization state must be a finite length-19 vector")
    if not np.isfinite(relative_step) or relative_step <= 0.0:
        raise ValueError("relative_step must be finite and positive")
    matrix = np.empty((19, 19), dtype=np.float64)
    for column in range(19):
        step = relative_step * max(1.0, abs(float(x[column])))
        upper = x.copy()
        lower = x.copy()
        upper[column] += step
        lower[column] -= step
        matrix[:, column] = (
            sienna_test08_rhs(upper, parameters)
            - sienna_test08_rhs(lower, parameters)
        ) / (2.0 * step)
    return matrix


def audit_sienna_test08_transcription(
    relative_step: float = 1.0e-6,
    parameters: SiennaTest08Parameters = SiennaTest08Parameters(),
) -> SiennaTest08Audit:
    """Compare the transcription with Sienna's frozen initial/eigenvalue data."""

    residual = sienna_test08_rhs(FROZEN_INITIAL_STATE, parameters)
    terminal_voltage = terminal_voltage_from_grid_current(
        FROZEN_INITIAL_STATE[17:19], parameters
    )
    expected_terminal_voltage = complex(
        0.9999994707586406, 0.0010313084369410759
    )
    matrix = linearize_sienna_test08(
        parameters=parameters, relative_step=relative_step
    )
    eigenvalues = np.linalg.eigvals(matrix).astype(np.complex128, copy=False)
    distances = np.abs(
        eigenvalues[:, np.newaxis]
        - FROZEN_EIGENVALUES_PER_S[np.newaxis, :]
    )
    row_index, column_index = linear_sum_assignment(distances)
    matched_errors = distances[row_index, column_index]
    return SiennaTest08Audit(
        initial_residual_inf=float(np.linalg.norm(residual, ord=np.inf)),
        reconstructed_terminal_voltage=terminal_voltage,
        expected_terminal_voltage=expected_terminal_voltage,
        terminal_voltage_error=float(abs(terminal_voltage - expected_terminal_voltage)),
        eigenvalues_per_s=eigenvalues,
        matched_eigenvalue_max_error_per_s=float(np.max(matched_errors)),
        matched_eigenvalue_l2_error_per_s=float(np.linalg.norm(matched_errors)),
    )


def sienna_test08_audit_payload() -> dict[str, object]:
    """Return a JSON-safe, claim-bounded audit of the fixed transcription."""

    audit = audit_sienna_test08_transcription()
    frequency_counterfactual = audit_sienna_test08_transcription(
        parameters=SiennaTest08Parameters(frequency_hz=50.0)
    )
    parameters = SiennaTest08Parameters()
    common_lcl_parameters = CommonLCLParameters(
        frequency_hz=parameters.frequency_hz,
        converter_side_resistance_pu=parameters.converter_side_resistance_pu,
        converter_side_reactance_pu=parameters.converter_side_reactance_pu,
        filter_capacitor_susceptance_pu=(
            parameters.filter_capacitor_susceptance_pu
        ),
        grid_side_resistance_pu=parameters.grid_side_resistance_pu,
        grid_side_reactance_pu=parameters.grid_side_reactance_pu,
        synchronous_frequency_pu=parameters.system_frequency_pu,
    )
    common_lcl_audit = sienna_team_common_lcl_audit(
        common_lcl_parameters,
        common_lcl_parameters,
        angle_rad=float(FROZEN_INITIAL_STATE[0]),
        network_reactance_pu_system_base=(
            parameters.network_reactance_pu_system_base
        ),
        system_base_power_mva=parameters.system_base_power_mva,
        device_base_power_mva=parameters.device_base_power_mva,
    )
    inner_control_mapping = sienna_team_inner_control_mapping_audit(
        CascadedPIParameters(
            voltage_kp=parameters.voltage_kp,
            voltage_ki_per_s=parameters.voltage_ki,
            current_kp=parameters.current_kp,
            current_ki_per_s=parameters.current_ki,
            filter_capacitor_susceptance_pu=(
                parameters.filter_capacitor_susceptance_pu
            ),
            converter_side_resistance_pu=(
                parameters.converter_side_resistance_pu
            ),
            converter_side_reactance_pu=parameters.converter_side_reactance_pu,
            current_feedforward_gain=parameters.current_feedforward,
            voltage_feedforward_gain=parameters.voltage_feedforward,
            active_damping_gain=parameters.active_damping_gain,
            synchronous_frequency_pu=parameters.system_frequency_pu,
            resistive_drop_feedforward_gain=0.0,
        ),
        CascadedPIParameters(
            voltage_kp=parameters.voltage_kp,
            voltage_ki_per_s=parameters.voltage_ki,
            current_kp=parameters.current_kp,
            current_ki_per_s=parameters.current_ki,
            filter_capacitor_susceptance_pu=(
                parameters.filter_capacitor_susceptance_pu
            ),
            converter_side_resistance_pu=(
                parameters.converter_side_resistance_pu
            ),
            converter_side_reactance_pu=parameters.converter_side_reactance_pu,
            current_feedforward_gain=1.0,
            voltage_feedforward_gain=1.0,
            active_damping_gain=0.0,
            synchronous_frequency_pu=parameters.system_frequency_pu,
            resistive_drop_feedforward_gain=1.0,
        ),
    )
    common_inner_parameters = CommonInnerLoopParameters(
        frequency_hz=parameters.frequency_hz,
        voltage_kp=parameters.voltage_kp,
        voltage_ki_per_s=parameters.voltage_ki,
        current_kp=parameters.current_kp,
        current_ki_per_s=parameters.current_ki,
        converter_side_resistance_pu=parameters.converter_side_resistance_pu,
        converter_side_reactance_pu=parameters.converter_side_reactance_pu,
        filter_capacitor_susceptance_pu=(
            parameters.filter_capacitor_susceptance_pu
        ),
        grid_side_resistance_pu=parameters.grid_side_resistance_pu,
        grid_side_reactance_pu=parameters.grid_side_reactance_pu,
        virtual_resistance_pu=parameters.virtual_resistance_pu,
        virtual_reactance_pu=parameters.virtual_reactance_pu,
        resistive_drop_feedforward_gain=0.0,
        synchronous_frequency_pu=parameters.system_frequency_pu,
    )
    common_inner_loop = sienna_team_common_inner_loop_audit(
        common_inner_parameters,
        angle_rad=float(FROZEN_INITIAL_STATE[0]),
    )
    common_active_damping = sienna_team_common_active_damping_audit(
        common_inner_parameters,
        angle_rad=float(FROZEN_INITIAL_STATE[0]),
        active_damping_cutoff_rad_s=parameters.active_damping_cutoff_rad_s,
        active_damping_gain=parameters.active_damping_gain,
    )
    common_inner_loop_modal_fingerprint = (
        run_common_inner_loop_modal_fingerprint()
    )
    common_outer_loop = run_common_outer_loop_audit()
    computed = sorted(
        (complex(value) for value in audit.eigenvalues_per_s),
        key=lambda value: (value.real, value.imag),
    )
    expected = sorted(
        (complex(value) for value in FROZEN_EIGENVALUES_PER_S),
        key=lambda value: (value.real, value.imag),
    )

    def _complex_rows(values: list[complex]) -> list[dict[str, float]]:
        return [
            {
                "real_per_s": float(value.real),
                "imag_per_s": float(value.imag),
                "oscillation_frequency_hz": float(abs(value.imag) / (2.0 * pi)),
            }
            for value in values
        ]

    return {
        "schema_version": "gfm-sienna-test08-source-transcription-audit/1.6",
        "benchmark_id": "sienna-psid-test08-v0.16.2-python-transcription-v1",
        "status": "passed"
        if (
            audit.initial_residual_inf < 1.0e-8
            and audit.terminal_voltage_error < 1.0e-10
            and audit.matched_eigenvalue_l2_error_per_s < 1.0e-3
            and common_lcl_audit["status"] == "passed"
            and inner_control_mapping["pi_state_mapping"]["status"] == "passed"
            and common_inner_loop["status"] == "passed"
            and common_active_damping["status"] == "passed"
            and common_inner_loop_modal_fingerprint["status"] == "passed"
            and common_outer_loop["status"] == "passed"
        )
        else "failed",
        "source_contract": {
            "power_simulations_dynamics_version": "v0.16.2",
            "power_simulations_dynamics_commit": (
                "dfb56d80b7a019b2d287f1da4d65157d6de134fa"
            ),
            "power_system_case_builder_version": "v2.6.0",
            "power_system_case_builder_commit": (
                "f11aa437e6cd3c982e3a6aedca290a43a9be7220"
            ),
            "power_systems_test_data_version": "4.0.6",
            "test_case": "psid_test_vsm_inverter / Test 08",
            "license": "BSD-3-Clause",
        },
        "model_contract": {
            "state_count": len(STATE_LABELS),
            "state_labels": list(STATE_LABELS),
            "system_frequency_hz_used_by_frozen_result": 60.0,
            "legacy_raw_header_frequency_hz": 50.0,
            "system_base_power_mva": 100.0,
            "device_base_power_mva": 2.75,
            "network_reactance_pu_system_base": 0.075,
            "static_terminal_active_power_pu_device_base": 0.5,
            "initialized_internal_active_power_reference_pu": (
                SiennaTest08Parameters().active_power_reference_pu
            ),
        },
        "verification_gates": {
            "initial_residual_inf_max": 1.0e-8,
            "terminal_voltage_error_max": 1.0e-10,
            "matched_eigenvalue_l2_error_per_s_max": 1.0e-3,
        },
        "results": {
            "initial_residual_inf": audit.initial_residual_inf,
            "terminal_voltage_error": audit.terminal_voltage_error,
            "matched_eigenvalue_max_error_per_s": (
                audit.matched_eigenvalue_max_error_per_s
            ),
            "matched_eigenvalue_l2_error_per_s": (
                audit.matched_eigenvalue_l2_error_per_s
            ),
            "computed_stable": bool(
                max(value.real for value in audit.eigenvalues_per_s) < 0.0
            ),
            "computed_eigenvalues": _complex_rows(computed),
            "upstream_expected_eigenvalues": _complex_rows(expected),
            "frequency_base_counterfactual": {
                "frequency_hz": 50.0,
                "matched_eigenvalue_max_error_per_s": (
                    frequency_counterfactual.matched_eigenvalue_max_error_per_s
                ),
                "interpretation": (
                    "Using 50 Hz scales the fast electrical modes by about 5/6 "
                    "and does not reproduce the frozen Test 08 spectrum."
                ),
            },
        },
        "common_lcl_isomorphism": common_lcl_audit,
        "inner_control_mapping": inner_control_mapping,
        "common_inner_loop": common_inner_loop,
        "common_active_damping": common_active_damping,
        "common_inner_loop_modal_fingerprint": (
            common_inner_loop_modal_fingerprint
        ),
        "common_outer_loop": common_outer_loop,
        "scope": {
            "source_equation_transcription_verified": True,
            "julia_runtime_executed_on_this_machine": False,
            "pscad_rerun": False,
            "upstream_pscad_trace_present_in_fixed_source": True,
            "team_16_state_model_validated_by_this_audit": False,
            "team_common_lcl_layer_compared": True,
            "team_pi_state_scaling_compared": True,
            "team_complete_inner_control_compared": False,
            "team_common_inner_loop_variants_compared": True,
            "team_common_active_damping_variants_compared": True,
            "team_common_inner_loop_modal_fingerprint_evaluated": True,
            "team_common_outer_loop_power_ports_compared": True,
            "mathworks_model_evaluated": False,
            "paper_sufficient_condition_evaluated": False,
            "statement": (
                "The Python transcription reproduces the upstream frozen initial "
                "condition and 19-eigenvalue regression. The common six-state LCL "
                "layer and PI-state scaling are compared separately; the original "
                "complete inner controls remain non-isomorphic. Two explicitly "
                "labelled common inner-loop variants are equation-isomorphic but "
                "are not either original full model. Their approximately 100 Hz "
                "branch is tracked separately under bounded one-factor changes; "
                "that diagnostic is not a causal attribution. Two loaded common "
                "outer-loop cases separately align the capacitor and PCC power "
                "ports; mixing those original port choices is rejected as a "
                "structural mismatch. This audit does not rerun Julia "
                "or PSCAD and does not validate the team's different 16-state model."
            ),
        },
    }
