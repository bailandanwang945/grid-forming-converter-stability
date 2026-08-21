"""Bounded modal fingerprint for the common Sienna/team inner-loop cases.

The fixed-input common models contain only PI, optional active-damping, and
LCL states.  Consequently this module does not make the tautological claim
that their rightmost mode is an "inner-loop mode".  Instead it asks a narrower
question: in the frozen team-coordinate state basis, is the approximately
100 Hz branch concentrated in identifiable LCL/control groups and does it
move continuously under pre-registered one-factor perturbations?

The result is diagnostic evidence for the intermediate models only.  It is
not a causal proof, a full-spectrum continuation, a stability boundary, or an
evaluation of either original complete converter model.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from math import isfinite, log, pi, sqrt

import numpy as np
from numpy.typing import NDArray

from backend.core.average_dq_ablation import (
    DEFAULT_MAXIMUM_CONDITION_NUMBER,
    DEFAULT_MAXIMUM_EIGENPAIR_RESIDUAL,
    DEFAULT_MAXIMUM_NORMALIZED_DISTANCE,
    DEFAULT_MINIMUM_COMBINED_MAC,
    DEFAULT_MINIMUM_CONFIDENCE,
    DEFAULT_MINIMUM_INDIVIDUAL_MAC,
    DEFAULT_MINIMUM_RELATIVE_MARGIN,
    ModalSignature,
    match_mode,
    modal_signature,
)
from backend.core.sienna_team_common_active_damping import (
    team_common_active_damping_matrices,
)
from backend.core.sienna_team_common_inner_loop import (
    CommonInnerLoopParameters,
    team_common_inner_loop_matrices,
)


FACTOR_LEVELS = (0.8, 1.2)
MAXIMUM_REFINEMENT_DEPTH = 4
CONTROL_PARTICIPATION_MINIMUM = 0.05
LCL_PARTICIPATION_MINIMUM = 0.50
REAL_SHIFT_EVIDENCE_MINIMUM_PER_S = 5.0

TEN_STATE_GROUPS = (
    ("voltage_pi", slice(0, 2)),
    ("current_pi", slice(2, 4)),
    ("converter_current", slice(4, 6)),
    ("capacitor_voltage", slice(6, 8)),
    ("grid_side_filter_current", slice(8, 10)),
)
TWELVE_STATE_GROUPS = (
    ("voltage_pi", slice(0, 2)),
    ("current_pi", slice(2, 4)),
    ("active_damping_filter", slice(4, 6)),
    ("converter_current", slice(6, 8)),
    ("capacitor_voltage", slice(8, 10)),
    ("grid_side_filter_current", slice(10, 12)),
)
COMMON_FACTORS = (
    "voltage_pi_joint_gain",
    "current_pi_joint_gain",
    "converter_side_filter_reactance",
    "filter_capacitor_susceptance",
    "grid_side_filter_reactance",
)
ACTIVE_DAMPING_FACTORS = (
    "active_damping_gain",
    "active_damping_cutoff",
)


class CommonInnerLoopModalFingerprintError(ValueError):
    """Raised when the bounded modal-fingerprint contract is invalid."""


def frozen_common_inner_loop_parameters() -> CommonInnerLoopParameters:
    """Map the fixed Test 08 component values into the common model."""

    from backend.core.sienna_test08_reference import SiennaTest08Parameters

    source = SiennaTest08Parameters()
    return CommonInnerLoopParameters(
        frequency_hz=source.frequency_hz,
        voltage_kp=source.voltage_kp,
        voltage_ki_per_s=source.voltage_ki,
        current_kp=source.current_kp,
        current_ki_per_s=source.current_ki,
        converter_side_resistance_pu=source.converter_side_resistance_pu,
        converter_side_reactance_pu=source.converter_side_reactance_pu,
        filter_capacitor_susceptance_pu=(
            source.filter_capacitor_susceptance_pu
        ),
        grid_side_resistance_pu=source.grid_side_resistance_pu,
        grid_side_reactance_pu=source.grid_side_reactance_pu,
        virtual_resistance_pu=source.virtual_resistance_pu,
        virtual_reactance_pu=source.virtual_reactance_pu,
        resistive_drop_feedforward_gain=0.0,
        synchronous_frequency_pu=source.system_frequency_pu,
    )


def _rightmost_positive_imaginary(matrix: NDArray[np.float64]) -> complex:
    eigenvalues = np.linalg.eigvals(matrix)
    candidates = eigenvalues[eigenvalues.imag > 1.0e-8]
    if candidates.size == 0:
        raise CommonInnerLoopModalFingerprintError(
            "the common model has no positive-imaginary oscillatory mode"
        )
    maximum_real = float(np.max(candidates.real))
    tolerance = 1.0e-10 * max(abs(maximum_real), 1.0)
    tied = candidates[np.abs(candidates.real - maximum_real) <= tolerance]
    return complex(max(tied, key=lambda value: value.imag))


def _group_participation(
    signature: ModalSignature,
    groups: tuple[tuple[str, slice], ...],
) -> dict[str, float]:
    raw = np.abs(signature.right_vector * np.conj(signature.left_vector))
    total = float(np.sum(raw))
    if not isfinite(total) or total <= 0.0:
        raise CommonInnerLoopModalFingerprintError(
            "modal participation cannot be normalized"
        )
    normalized = raw / total
    return {
        name: float(np.sum(normalized[index])) for name, index in groups
    }


def _eigenvalue_payload(value: complex) -> dict[str, float]:
    return {
        "real_per_s": float(value.real),
        "imag_per_s": float(value.imag),
        "oscillation_frequency_hz": float(abs(value.imag) / (2.0 * pi)),
    }


def _signature_payload(
    signature: ModalSignature,
    groups: tuple[tuple[str, slice], ...],
) -> dict[str, object]:
    participation = _group_participation(signature, groups)
    lcl_total = sum(
        participation[name]
        for name in (
            "converter_current",
            "capacitor_voltage",
            "grid_side_filter_current",
        )
    )
    control_total = participation["voltage_pi"] + participation["current_pi"]
    if "active_damping_filter" in participation:
        control_total += participation["active_damping_filter"]
    return {
        "eigenvalue": _eigenvalue_payload(signature.eigenvalue_per_s),
        "group_participation_frozen_coordinates": participation,
        "lcl_group_total": float(lcl_total),
        "control_state_group_total": float(control_total),
        "condition_number": signature.condition_number,
        "right_eigenpair_residual": signature.right_residual,
        "left_eigenpair_residual": signature.left_residual,
    }


def _apply_factor(
    parameters: CommonInnerLoopParameters,
    factor_name: str,
    factor: float,
    *,
    active_damping_gain: float,
    active_damping_cutoff_rad_s: float,
) -> tuple[CommonInnerLoopParameters, float, float]:
    if not isfinite(factor) or factor <= 0.0:
        raise CommonInnerLoopModalFingerprintError(
            "modal-fingerprint factors must be finite and positive"
        )
    updated = parameters
    gain = active_damping_gain
    cutoff = active_damping_cutoff_rad_s
    if factor_name == "voltage_pi_joint_gain":
        updated = replace(
            updated,
            voltage_kp=parameters.voltage_kp * factor,
            voltage_ki_per_s=parameters.voltage_ki_per_s * factor,
        )
    elif factor_name == "current_pi_joint_gain":
        updated = replace(
            updated,
            current_kp=parameters.current_kp * factor,
            current_ki_per_s=parameters.current_ki_per_s * factor,
        )
    elif factor_name == "converter_side_filter_reactance":
        updated = replace(
            updated,
            converter_side_reactance_pu=(
                parameters.converter_side_reactance_pu * factor
            ),
        )
    elif factor_name == "filter_capacitor_susceptance":
        updated = replace(
            updated,
            filter_capacitor_susceptance_pu=(
                parameters.filter_capacitor_susceptance_pu * factor
            ),
        )
    elif factor_name == "grid_side_filter_reactance":
        updated = replace(
            updated,
            grid_side_reactance_pu=parameters.grid_side_reactance_pu * factor,
        )
    elif factor_name == "active_damping_gain":
        gain *= factor
    elif factor_name == "active_damping_cutoff":
        cutoff *= factor
    else:
        raise CommonInnerLoopModalFingerprintError(
            f"unsupported modal-fingerprint factor: {factor_name}"
        )
    return updated, gain, cutoff


def _state_matrix(
    parameters: CommonInnerLoopParameters,
    *,
    state_count: int,
    active_damping_gain: float,
    active_damping_cutoff_rad_s: float,
) -> NDArray[np.float64]:
    if state_count == 10:
        return team_common_inner_loop_matrices(parameters)[0]
    if state_count == 12:
        return team_common_active_damping_matrices(
            parameters,
            active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
            active_damping_gain=active_damping_gain,
        )[0]
    raise CommonInnerLoopModalFingerprintError(
        "modal fingerprint supports only the common 10/12-state models"
    )


def _factored_matrix(
    parameters: CommonInnerLoopParameters,
    factor_name: str,
    factor: float,
    *,
    state_count: int,
    active_damping_gain: float,
    active_damping_cutoff_rad_s: float,
) -> NDArray[np.float64]:
    varied, gain, cutoff = _apply_factor(
        parameters,
        factor_name,
        factor,
        active_damping_gain=active_damping_gain,
        active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
    )
    return _state_matrix(
        varied,
        state_count=state_count,
        active_damping_gain=gain,
        active_damping_cutoff_rad_s=cutoff,
    )


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


def _trace_factor(
    reference: ModalSignature,
    parameters: CommonInnerLoopParameters,
    factor_name: str,
    start_factor: float,
    target_factor: float,
    *,
    state_count: int,
    active_damping_gain: float,
    active_damping_cutoff_rad_s: float,
    depth: int = 0,
) -> tuple[ModalSignature, list[dict[str, object]], str]:
    target_matrix = _factored_matrix(
        parameters,
        factor_name,
        target_factor,
        state_count=state_count,
        active_damping_gain=active_damping_gain,
        active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
    )
    match = match_mode(reference, target_matrix)
    step = {
        "from_factor": start_factor,
        "to_factor": target_factor,
        **_match_payload(match),
        "eigenvalue": _eigenvalue_payload(match.eigenvalue_per_s),
    }
    if match.status == "matched":
        endpoint = modal_signature(target_matrix, match.eigenvalue_per_s)
        return endpoint, [step], "matched"
    if depth >= MAXIMUM_REFINEMENT_DEPTH:
        endpoint = modal_signature(target_matrix, match.eigenvalue_per_s)
        return endpoint, [step], "pending"

    midpoint = sqrt(start_factor * target_factor)
    midpoint_signature, first_steps, first_status = _trace_factor(
        reference,
        parameters,
        factor_name,
        start_factor,
        midpoint,
        state_count=state_count,
        active_damping_gain=active_damping_gain,
        active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
        depth=depth + 1,
    )
    if first_status != "matched":
        return midpoint_signature, [step, *first_steps], "pending"
    endpoint, second_steps, second_status = _trace_factor(
        midpoint_signature,
        parameters,
        factor_name,
        midpoint,
        target_factor,
        state_count=state_count,
        active_damping_gain=active_damping_gain,
        active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
        depth=depth + 1,
    )
    return endpoint, [step, *first_steps, *second_steps], second_status


def _path_summary(
    baseline: ModalSignature,
    endpoint: ModalSignature,
    steps: list[dict[str, object]],
    status: str,
    groups: tuple[tuple[str, slice], ...],
) -> dict[str, object]:
    accepted = [step for step in steps if step["status"] == "matched"]
    evidence_steps = accepted if accepted else steps
    return {
        "status": status,
        "path_steps_including_rejected_direct_attempts": len(steps),
        "accepted_step_count": len(accepted),
        "endpoint": _signature_payload(endpoint, groups),
        "real_shift_from_baseline_per_s": float(
            endpoint.eigenvalue_per_s.real - baseline.eigenvalue_per_s.real
        ),
        "frequency_shift_from_baseline_hz": float(
            (abs(endpoint.eigenvalue_per_s.imag) - abs(baseline.eigenvalue_per_s.imag))
            / (2.0 * pi)
        ),
        "minimum_right_mac": float(
            min(float(step["right_mac"]) for step in evidence_steps)
        ),
        "minimum_left_mac": float(
            min(float(step["left_mac"]) for step in evidence_steps)
        ),
        "maximum_normalized_eigenvalue_distance": float(
            max(
                float(step["normalized_eigenvalue_distance"])
                for step in evidence_steps
            )
        ),
        "maximum_condition_number": float(
            max(float(step["condition_number"]) for step in evidence_steps)
        ),
        "maximum_eigenpair_residual": float(
            max(
                max(
                    float(step["right_eigenpair_residual"]),
                    float(step["left_eigenpair_residual"]),
                )
                for step in evidence_steps
            )
        ),
        "steps": steps,
    }


def _variant_fingerprint(
    parameters: CommonInnerLoopParameters,
    *,
    state_count: int,
    active_damping_gain: float,
    active_damping_cutoff_rad_s: float,
) -> dict[str, object]:
    groups = TEN_STATE_GROUPS if state_count == 10 else TWELVE_STATE_GROUPS
    baseline_matrix = _state_matrix(
        parameters,
        state_count=state_count,
        active_damping_gain=active_damping_gain,
        active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
    )
    baseline_value = _rightmost_positive_imaginary(baseline_matrix)
    baseline = modal_signature(baseline_matrix, baseline_value)
    factors = COMMON_FACTORS + (ACTIVE_DAMPING_FACTORS if state_count == 12 else ())
    paths: dict[str, dict[str, object]] = {}
    sensitivity: list[dict[str, object]] = []
    for factor_name in factors:
        endpoints: dict[float, ModalSignature] = {}
        factor_paths: dict[str, object] = {}
        for factor in FACTOR_LEVELS:
            endpoint, steps, status = _trace_factor(
                baseline,
                parameters,
                factor_name,
                1.0,
                factor,
                state_count=state_count,
                active_damping_gain=active_damping_gain,
                active_damping_cutoff_rad_s=active_damping_cutoff_rad_s,
            )
            endpoints[factor] = endpoint
            factor_paths[f"factor_{str(factor).replace('.', 'p')}"] = _path_summary(
                baseline, endpoint, steps, status, groups
            )
        lower = endpoints[FACTOR_LEVELS[0]].eigenvalue_per_s
        upper = endpoints[FACTOR_LEVELS[1]].eigenvalue_per_s
        log_span = log(FACTOR_LEVELS[1]) - log(FACTOR_LEVELS[0])
        sensitivity.append(
            {
                "factor_name": factor_name,
                "central_real_sensitivity_per_log_factor_per_s": float(
                    (upper.real - lower.real) / log_span
                ),
                "central_frequency_sensitivity_hz_per_log_factor": float(
                    (abs(upper.imag) - abs(lower.imag)) / (2.0 * pi * log_span)
                ),
                "maximum_absolute_real_shift_per_s": float(
                    max(
                        abs(lower.real - baseline.eigenvalue_per_s.real),
                        abs(upper.real - baseline.eigenvalue_per_s.real),
                    )
                ),
            }
        )
        paths[factor_name] = factor_paths
    sensitivity.sort(
        key=lambda row: float(row["maximum_absolute_real_shift_per_s"]),
        reverse=True,
    )
    all_matched = all(
        path[endpoint]["status"] == "matched"
        for path in paths.values()
        for endpoint in path
    )
    baseline_payload = _signature_payload(baseline, groups)
    pi_names = {"voltage_pi_joint_gain", "current_pi_joint_gain"}
    lcl_names = {
        "converter_side_filter_reactance",
        "filter_capacitor_susceptance",
        "grid_side_filter_reactance",
    }
    pi_shift = max(
        float(row["maximum_absolute_real_shift_per_s"])
        for row in sensitivity
        if row["factor_name"] in pi_names
    )
    lcl_shift = max(
        float(row["maximum_absolute_real_shift_per_s"])
        for row in sensitivity
        if row["factor_name"] in lcl_names
    )
    consistent = bool(
        all_matched
        and float(baseline_payload["lcl_group_total"])
        >= LCL_PARTICIPATION_MINIMUM
        and float(baseline_payload["control_state_group_total"])
        >= CONTROL_PARTICIPATION_MINIMUM
        and pi_shift >= REAL_SHIFT_EVIDENCE_MINIMUM_PER_S
        and lcl_shift >= REAL_SHIFT_EVIDENCE_MINIMUM_PER_S
    )
    return {
        "state_count": state_count,
        "resistive_drop_feedforward_gain": (
            parameters.resistive_drop_feedforward_gain
        ),
        "active_damping_gain": active_damping_gain if state_count == 12 else 0.0,
        "active_damping_cutoff_rad_s": (
            active_damping_cutoff_rad_s if state_count == 12 else None
        ),
        "baseline_named_branch": baseline_payload,
        "factor_paths": paths,
        "sensitivity_ranking": sensitivity,
        "all_pre_registered_endpoints_matched": all_matched,
        "candidate_interaction_evidence": {
            "status": "consistent" if consistent else "not-supported",
            "lcl_participation_minimum": LCL_PARTICIPATION_MINIMUM,
            "control_participation_minimum": CONTROL_PARTICIPATION_MINIMUM,
            "real_shift_evidence_minimum_per_s": (
                REAL_SHIFT_EVIDENCE_MINIMUM_PER_S
            ),
            "maximum_pi_factor_real_shift_per_s": pi_shift,
            "maximum_lcl_factor_real_shift_per_s": lcl_shift,
            "statement": (
                "Within the frozen intermediate model and state basis, the "
                "named branch has material LCL and control-state participation "
                "and responds to both PI and LCL one-factor perturbations. This "
                "supports an electrical-control interaction hypothesis but is "
                "not a unique causal attribution."
                if consistent
                else "The pre-registered evidence gates do not support the "
                "candidate electrical-control interaction in this variant."
            ),
        },
    }


def run_common_inner_loop_modal_fingerprint() -> dict[str, object]:
    """Recompute the fixed four-variant, one-factor modal fingerprint."""

    from backend.core.sienna_test08_reference import SiennaTest08Parameters

    base = frozen_common_inner_loop_parameters()
    source = SiennaTest08Parameters()
    variants: dict[str, object] = {}
    for state_count in (10, 12):
        for label, rfif_gain in (("omit_rfif", 0.0), ("include_rfif", 1.0)):
            key = f"{state_count}_state_{label}"
            variants[key] = _variant_fingerprint(
                replace(
                    base,
                    resistive_drop_feedforward_gain=rfif_gain,
                ),
                state_count=state_count,
                active_damping_gain=source.active_damping_gain,
                active_damping_cutoff_rad_s=(
                    source.active_damping_cutoff_rad_s
                ),
            )

    counter_parameters = replace(base, resistive_drop_feedforward_gain=0.0)
    counter_matrix = _state_matrix(
        counter_parameters,
        state_count=10,
        active_damping_gain=source.active_damping_gain,
        active_damping_cutoff_rad_s=source.active_damping_cutoff_rad_s,
    )
    counter_reference = modal_signature(
        counter_matrix, _rightmost_positive_imaginary(counter_matrix)
    )
    direct_matrix = _factored_matrix(
        counter_parameters,
        "grid_side_filter_reactance",
        5.0,
        state_count=10,
        active_damping_gain=source.active_damping_gain,
        active_damping_cutoff_rad_s=source.active_damping_cutoff_rad_s,
    )
    direct = match_mode(counter_reference, direct_matrix)
    refined_endpoint, refined_steps, refined_status = _trace_factor(
        counter_reference,
        counter_parameters,
        "grid_side_filter_reactance",
        1.0,
        5.0,
        state_count=10,
        active_damping_gain=source.active_damping_gain,
        active_damping_cutoff_rad_s=source.active_damping_cutoff_rad_s,
    )
    all_consistent = all(
        variant["candidate_interaction_evidence"]["status"] == "consistent"
        for variant in variants.values()
    )
    all_matched = all(
        variant["all_pre_registered_endpoints_matched"]
        for variant in variants.values()
    )
    counterfactual_passed = bool(
        direct.status == "pending"
        and refined_status == "matched"
        and len(refined_steps) > 1
    )
    passed = all_consistent and all_matched and counterfactual_passed
    return {
        "schema_version": "gfm-common-inner-loop-modal-fingerprint/1.0",
        "status": "passed" if passed else "failed",
        "source_contract": {
            "parameter_source": "Sienna PSID v0.16.2 Test 08 component values",
            "base_parameters": asdict(base),
            "factor_levels": list(FACTOR_LEVELS),
            "parameter_variation": (
                "one factor at a time; voltage/current PI Kp and Ki are scaled "
                "jointly; X1, Bc and X2 are filter parameters"
            ),
        },
        "matching_gates": {
            "minimum_confidence": DEFAULT_MINIMUM_CONFIDENCE,
            "minimum_combined_mac": DEFAULT_MINIMUM_COMBINED_MAC,
            "minimum_individual_mac": DEFAULT_MINIMUM_INDIVIDUAL_MAC,
            "maximum_normalized_eigenvalue_distance": (
                DEFAULT_MAXIMUM_NORMALIZED_DISTANCE
            ),
            "maximum_condition_number": DEFAULT_MAXIMUM_CONDITION_NUMBER,
            "maximum_eigenpair_residual": (
                DEFAULT_MAXIMUM_EIGENPAIR_RESIDUAL
            ),
            "minimum_relative_candidate_margin": (
                DEFAULT_MINIMUM_RELATIVE_MARGIN
            ),
            "maximum_refinement_depth": MAXIMUM_REFINEMENT_DEPTH,
        },
        "variants": variants,
        "tracking_counterexample": {
            "change": (
                "directly scale the grid-side filter reactance X2 from 1.0 to "
                "5.0 in the ten-state omit-Rfif path"
            ),
            "direct_jump": _match_payload(direct),
            "direct_jump_rejected": direct.status == "pending",
            "refined_path_status": refined_status,
            "refined_path_step_count_including_rejected_attempt": len(
                refined_steps
            ),
            "refined_endpoint": _signature_payload(
                refined_endpoint, TEN_STATE_GROUPS
            ),
            "refinement_recovers_branch": counterfactual_passed,
        },
        "hypothesis_test": {
            "hypothesis": (
                "the approximately 100 Hz branch in the frozen common models "
                "has material LCL and control-state participation and responds "
                "continuously to both PI and LCL one-factor perturbations"
            ),
            "consistent_in_all_four_variants": all_consistent,
            "result": (
                "supported-as-bounded-candidate-interaction"
                if all_consistent
                else "not-supported"
            ),
        },
        "scope": {
            "source_baselines_modified": False,
            "team_original_model_modified": False,
            "fixed_input_common_intermediate_only": True,
            "state_scaling": "identity in the frozen team-coordinate basis",
            "participation_invariant_to_future_state_rescaling": False,
            "full_spectrum_global_continuation": False,
            "outer_controls_compared": False,
            "pll_compared": False,
            "modulation_or_limits_compared": False,
            "external_network_dynamics_compared": False,
            "grid_strength_scanned": False,
            "grid_side_reactance_meaning": (
                "X2 is the grid-side LCL filter reactance, not external grid "
                "reactance and not SCR"
            ),
            "causal_attribution_established": False,
            "statement": (
                "The result identifies a tracked wide-frequency branch and "
                "bounded parameter associations inside four common fixed-input "
                "intermediate models. It does not establish a unique mechanism "
                "for either original converter, a continuous stability boundary, "
                "or a claim about the paper sufficient condition."
            ),
        },
    }
