"""Static-versus-dynamic external RL-line audit for the average-dq model."""

from __future__ import annotations

from math import isfinite, pi

import numpy as np
from numpy.typing import NDArray

from backend.core.average_dq_ablation import (
    ModalSignature,
    match_modes,
    modal_signature,
)
from backend.core.average_dq_model import (
    J,
    AverageDQLinearization,
    AverageDQModelError,
    build_average_dq_model,
    close_port_model_with_external_line,
    compare_with_quasisteady_reduction,
)
from backend.core.average_dq_presets import build_average_dq_verification_case
from backend.core.sienna_team_active_power_measurement_delay import (
    _band_mode,
    _match_payload,
    _pole_payload,
)
from backend.domain.network_models import ACLine


LINE_REACTANCE_LEVELS_PU = (0.05, 0.1, 0.2, 0.3, 0.5)
LINE_X_OVER_R = 15.0
LINE_DYNAMICS_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
BASELINE_LINE_REACTANCE_PU = 0.3


class ExternalLineDynamicsError(ValueError):
    """Raised when the bounded line-dynamics contract is invalid."""


def close_port_model_with_line_dynamics_fraction(
    linearization: AverageDQLinearization,
    line: ACLine,
    base_frequency_hz: float,
    dynamics_fraction: float,
) -> NDArray[np.float64]:
    """Close a device port with static-to-dynamic RL-line homotopy.

    ``dynamics_fraction=0`` gives the algebraic synchronous-frame line
    impedance. ``dynamics_fraction=1`` gives the complete external RL-line
    differential equation. Intermediate values are continuation coordinates,
    not physical line parameters.
    """

    fraction = float(dynamics_fraction)
    if not isfinite(fraction) or fraction < 0.0 or fraction > 1.0:
        raise ExternalLineDynamicsError(
            "line dynamics fraction must be finite and within [0, 1]"
        )
    if not isfinite(base_frequency_hz) or base_frequency_hz <= 0.0:
        raise ExternalLineDynamicsError(
            "base frequency must be finite and positive"
        )
    if line.reactance_pu <= 0.0:
        raise ExternalLineDynamicsError(
            "external line reactance must be positive"
        )

    omega_base = 2.0 * pi * base_frequency_hz
    network_state = (
        -omega_base * line.resistance_pu / line.reactance_pu * np.eye(2)
        - omega_base * J
    )
    network_voltage = -omega_base / line.reactance_pu * np.eye(2)
    device_a = linearization.device_state_matrix
    device_b = linearization.port_voltage_matrix
    current_c = linearization.port_current_state_matrix
    elimination_matrix = (
        fraction * current_c @ device_b - network_voltage
    )
    elimination_rhs = (
        network_state @ current_c - fraction * current_c @ device_a
    )
    try:
        voltage_feedback = np.linalg.solve(
            elimination_matrix, elimination_rhs
        )
    except np.linalg.LinAlgError as error:
        raise AverageDQModelError(
            "static-to-dynamic line elimination matrix is singular"
        ) from error
    closed = device_a + device_b @ voltage_feedback
    if not np.all(np.isfinite(closed)):
        raise AverageDQModelError(
            "static-to-dynamic line closure produced non-finite values"
        )
    return closed


def _fixed_case(line_reactance_pu: float):
    topology, parameters = build_average_dq_verification_case()
    line = topology.lines[0]
    line.reactance_pu = line_reactance_pu
    line.resistance_pu = line_reactance_pu / LINE_X_OVER_R
    return topology, parameters


def _tracked_points(
    matrices: list[NDArray[np.float64]],
    synchronous_anchor_per_s: complex,
) -> tuple[list[dict[str, object]], tuple[ModalSignature, ...]]:
    dynamic_matrix = matrices[-1]
    intermediate_value = _band_mode(dynamic_matrix, 4.0, 10.0)
    wide_value = _band_mode(dynamic_matrix, 15.0, 100.0)
    references = (
        modal_signature(dynamic_matrix, synchronous_anchor_per_s),
        modal_signature(dynamic_matrix, intermediate_value),
        modal_signature(dynamic_matrix, wide_value),
    )
    point_by_fraction: dict[float, dict[str, object]] = {}
    for index, (fraction, matrix) in enumerate(
        zip(
            reversed(LINE_DYNAMICS_FRACTIONS),
            reversed(matrices),
            strict=True,
        )
    ):
        if index == 0:
            signatures = references
            tracking = (
                {"status": "anchor", "reason": "dynamic-line-anchor"},
                {"status": "anchor", "reason": "dynamic-line-anchor"},
                {"status": "anchor", "reason": "dynamic-line-anchor"},
            )
        else:
            matches = match_modes(references, matrix)
            tracking = tuple(_match_payload(match) for match in matches)
            signatures = tuple(
                modal_signature(matrix, match.eigenvalue_per_s)
                for match in matches
            )
            references = tuple(
                signature if match.status == "matched" else reference
                for reference, signature, match in zip(
                    references, signatures, matches, strict=True
                )
            )
        eigenvalues = np.linalg.eigvals(matrix)
        point_by_fraction[fraction] = {
                "line_dynamics_fraction": fraction,
                "spectral_abscissa_per_s": float(np.max(eigenvalues.real)),
                "stable_by_eigenvalues": bool(np.max(eigenvalues.real) < 0.0),
                "low_frequency_mode": {
                    "pole": _pole_payload(signatures[0].eigenvalue_per_s),
                    "tracking": tracking[0],
                },
                "intermediate_frequency_mode": {
                    "pole": _pole_payload(signatures[1].eigenvalue_per_s),
                    "tracking": tracking[1],
                },
                "wide_frequency_mode": {
                    "pole": _pole_payload(signatures[2].eigenvalue_per_s),
                    "tracking": tracking[2],
                },
            }
    points = [point_by_fraction[value] for value in LINE_DYNAMICS_FRACTIONS]
    return points, references


def run_external_line_dynamics_audit() -> dict[str, object]:
    """Run the preregistered static/dynamic external-line comparison."""

    cases: list[dict[str, object]] = []
    dynamic_reassembly_max_difference = 0.0
    all_low_modes_resolved = True
    all_intermediate_modes_resolved = True
    all_wide_modes_resolved = True
    low_real_shift_magnitudes: list[float] = []

    for line_reactance in LINE_REACTANCE_LEVELS_PU:
        topology, parameters = _fixed_case(line_reactance)
        model = build_average_dq_model(topology, parameters)
        matrices = [
            close_port_model_with_line_dynamics_fraction(
                model.linearization,
                model.line,
                model.topology.base_values.frequency_hz,
                fraction,
            )
            for fraction in LINE_DYNAMICS_FRACTIONS
        ]
        independently_reassembled = close_port_model_with_external_line(
            model.linearization,
            model.line,
            model.topology.base_values.frequency_hz,
        )
        reassembly_difference = float(
            np.max(
                np.abs(
                    matrices[-1] - model.linearization.closed_state_matrix
                )
            )
        )
        independent_difference = float(
            np.max(np.abs(matrices[-1] - independently_reassembled))
        )
        dynamic_reassembly_max_difference = max(
            dynamic_reassembly_max_difference,
            reassembly_difference,
            independent_difference,
        )
        reduction = compare_with_quasisteady_reduction(model)
        points, _references = _tracked_points(
            matrices, reduction.matched_full_pole_per_s
        )
        low_mode_resolved = all(
            point["low_frequency_mode"]["tracking"]["status"]
            in {"anchor", "matched"}
            for point in points
        )
        wide_mode_resolved = all(
            point["wide_frequency_mode"]["tracking"]["status"]
            in {"anchor", "matched"}
            for point in points
        )
        intermediate_mode_resolved = all(
            point["intermediate_frequency_mode"]["tracking"]["status"]
            in {"anchor", "matched"}
            for point in points
        )
        all_low_modes_resolved = (
            all_low_modes_resolved and low_mode_resolved
        )
        all_wide_modes_resolved = (
            all_wide_modes_resolved and wide_mode_resolved
        )
        all_intermediate_modes_resolved = (
            all_intermediate_modes_resolved
            and intermediate_mode_resolved
        )
        static_low_real = points[0]["low_frequency_mode"]["pole"]["real_per_s"]
        dynamic_low_real = points[-1]["low_frequency_mode"]["pole"]["real_per_s"]
        low_real_shift = float(dynamic_low_real - static_low_real)
        low_real_shift_magnitudes.append(abs(low_real_shift))
        cases.append(
            {
                "line_reactance_pu": line_reactance,
                "line_resistance_pu": model.line.resistance_pu,
                "line_x_over_r": LINE_X_OVER_R,
                "operating_point_residual_inf": (
                    model.operating_point.closed_rhs_residual_inf
                ),
                "dynamic_reassembly_max_abs_difference_per_s": (
                    reassembly_difference
                ),
                "independent_dynamic_closure_difference_per_s": (
                    independent_difference
                ),
                "low_frequency_mode_resolved": low_mode_resolved,
                "intermediate_frequency_mode_resolved": (
                    intermediate_mode_resolved
                ),
                "wide_frequency_mode_resolved": wide_mode_resolved,
                "dynamic_minus_static_low_mode_real_per_s": low_real_shift,
                "points": points,
            }
        )

    baseline = next(
        case
        for case in cases
        if case["line_reactance_pu"] == BASELINE_LINE_REACTANCE_PU
    )
    baseline_shift = baseline[
        "dynamic_minus_static_low_mode_real_per_s"
    ]
    h2_supported = bool(
        baseline["low_frequency_mode_resolved"] and baseline_shift > 0.0
    )
    h3_supported = bool(
        all_low_modes_resolved
        and all(
            later > earlier
            for earlier, later in zip(
                low_real_shift_magnitudes,
                low_real_shift_magnitudes[1:],
                strict=True,
            )
        )
    )
    reassembly_gate = 2.0e-7
    passed = dynamic_reassembly_max_difference <= reassembly_gate
    return {
        "schema_version": "gfm-average-dq-external-line-dynamics/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "device_state_count": 16,
            "line_reactance_levels_pu": list(LINE_REACTANCE_LEVELS_PU),
            "line_x_over_r": LINE_X_OVER_R,
            "line_dynamics_fractions": list(LINE_DYNAMICS_FRACTIONS),
            "baseline_line_reactance_pu": BASELINE_LINE_REACTANCE_PU,
            "static_line_definition": "alpha=0 algebraic synchronous-frame impedance",
            "dynamic_line_definition": "alpha=1 complete external RL differential equation",
        },
        "verification_gates": {
            "dynamic_reassembly_max_abs_difference_per_s": reassembly_gate,
        },
        "dynamic_reassembly_observed_max_abs_difference_per_s": (
            dynamic_reassembly_max_difference
        ),
        "cases": cases,
        "hypothesis_tests": {
            "h1_dynamic_reassembly_passed": passed,
            "h2_baseline_dynamic_low_mode_moves_right": {
                "result": (
                    "supported-in-bounded-study"
                    if h2_supported
                    else "not-supported-in-bounded-study"
                ),
                "dynamic_minus_static_real_per_s": baseline_shift,
            },
            "h3_low_mode_shift_magnitude_increases_with_reactance": {
                "result": (
                    "supported-in-bounded-study"
                    if h3_supported
                    else (
                        "not-supported-in-bounded-study"
                        if all_low_modes_resolved
                        else "pending-because-a-named-mode-is-unresolved"
                    )
                ),
                "absolute_real_shifts_per_s": low_real_shift_magnitudes,
            },
        },
        "scope": {
            "team_average_dq_smib_only": True,
            "same_device_states_and_operating_point_within_each_case": True,
            "intermediate_alpha_values_are_physical_parameters": False,
            "sienna_or_chatterjee_geng_case_reproduced": False,
            "general_hopf_margin_claimed": False,
            "all_low_frequency_modes_resolved": all_low_modes_resolved,
            "all_intermediate_frequency_modes_resolved": (
                all_intermediate_modes_resolved
            ),
            "all_wide_frequency_modes_resolved": all_wide_modes_resolved,
            "intermediate_frequency_branch_is_posthoc_diagnostic": True,
            "statement": (
                "The audit isolates external-line electromagnetic dynamics in "
                "the team average-dq SMIB model. Classification differences, "
                "if any, remain bounded to the declared cases."
            ),
        },
    }
