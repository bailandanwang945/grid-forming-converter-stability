from __future__ import annotations

from math import sqrt
from typing import Any

import numpy as np
from scipy.optimize import brentq

from backend.core.average_dq_model import build_average_dq_model
from backend.core.average_dq_presets import build_average_dq_verification_case
from backend.core.mathworks_external_evidence import (
    load_mathworks_external_evidence,
)


BASE_FREQUENCY_HZ = 50.0
X_BY_R = 5.0
PRE_STEP_ACTIVE_POWER_PU = 0.6
POST_STEP_ACTIVE_POWER_PU = 0.8
BOUNDARY_SCR = 5.0
BOUNDARY_LOWER_DAMPING_MW_PU_PER_HZ = 0.6
BOUNDARY_UPPER_DAMPING_MW_PU_PER_HZ = 1.056


def _source_impedance(scr: float, x_by_r: float = X_BY_R) -> tuple[float, float]:
    resistance = 1.0 / (scr * sqrt(1.0 + x_by_r**2))
    return resistance, x_by_r * resistance


def _team_case(
    scr: float,
    damping_mw_pu_per_hz: float,
    active_power_setpoint_pu: float,
):
    topology, parameters = build_average_dq_verification_case()
    resistance, reactance = _source_impedance(scr)
    topology.lines[0].resistance_pu = resistance
    topology.lines[0].reactance_pu = reactance
    topology.grid_forming_converters[0].active_power_setpoint_pu = (
        active_power_setpoint_pu
    )
    topology.grid_forming_converters[0].damping_coefficient_pu = (
        damping_mw_pu_per_hz * BASE_FREQUENCY_HZ
    )
    return build_average_dq_model(topology, parameters)


def _dominant_mode(model) -> dict[str, float]:
    pole = complex(max(model.poles_per_s, key=lambda value: (value.real, value.imag)))
    return {
        "real_per_s": float(pole.real),
        "oscillation_frequency_hz": float(abs(pole.imag) / (2.0 * np.pi)),
    }


def _spectral_abscissa(
    damping_mw_pu_per_hz: float,
    active_power_setpoint_pu: float,
) -> float:
    model = _team_case(
        BOUNDARY_SCR,
        damping_mw_pu_per_hz,
        active_power_setpoint_pu,
    )
    return float(np.max(model.poles_per_s.real))


def _team_boundary(active_power_setpoint_pu: float) -> dict[str, float]:
    root = brentq(
        lambda damping: _spectral_abscissa(damping, active_power_setpoint_pu),
        BOUNDARY_LOWER_DAMPING_MW_PU_PER_HZ,
        BOUNDARY_UPPER_DAMPING_MW_PU_PER_HZ,
        xtol=1.0e-10,
        rtol=1.0e-12,
        maxiter=100,
    )
    return {
        "active_power_setpoint_pu": active_power_setpoint_pu,
        "damping_mw_equivalent_pu_per_hz": float(root),
        "damping_team_native_pu_per_pu_frequency": float(
            root * BASE_FREQUENCY_HZ
        ),
        "spectral_abscissa_per_s": _spectral_abscissa(
            root,
            active_power_setpoint_pu,
        ),
    }


def evaluate_mathworks_team_comparison() -> dict[str, Any]:
    """Compare fixed external outcomes with aligned team-model pole classes.

    Only the named damping, source-impedance, frequency, and active-power
    coordinates are aligned. Other controller and plant parameters remain
    model-specific, so disagreement is a validation result rather than an
    implementation failure.
    """

    external_evidence = load_mathworks_external_evidence()
    external_factorial = external_evidence["studies"]["damping_factorial"]
    points = []
    for external_point in external_factorial["points"]:
        scr = float(external_point["scr"])
        damping_mw = float(external_point["dampingCoefficientPu"])
        pre_model = _team_case(scr, damping_mw, PRE_STEP_ACTIVE_POWER_PU)
        post_model = _team_case(scr, damping_mw, POST_STEP_ACTIVE_POWER_PU)
        pre_stability = pre_model.stability.value
        post_stability = post_model.stability.value
        external_stable = external_point["vendorOutcome"] == "Stable"
        team_endpoints_same_class = pre_stability == post_stability
        team_stable = pre_stability == "stable" and post_stability == "stable"
        agreement = team_endpoints_same_class and external_stable == team_stable
        resistance, reactance = _source_impedance(scr)
        points.append(
            {
                "scr": scr,
                "x_by_r": X_BY_R,
                "source_resistance_pu": resistance,
                "source_reactance_pu": reactance,
                "damping_mathworks_pu_per_hz": damping_mw,
                "damping_team_native_pu_per_pu_frequency": (
                    damping_mw * BASE_FREQUENCY_HZ
                ),
                "external_vendor_outcome": external_point["vendorOutcome"],
                "team_pre_step_stability": pre_stability,
                "team_post_step_stability": post_stability,
                "team_endpoints_same_class": team_endpoints_same_class,
                "classification_agreement": agreement,
                "team_pre_step_dominant_mode": _dominant_mode(pre_model),
                "team_post_step_dominant_mode": _dominant_mode(post_model),
            }
        )

    team_boundaries = [
        _team_boundary(PRE_STEP_ACTIVE_POWER_PU),
        _team_boundary(POST_STEP_ACTIVE_POWER_PU),
    ]
    external_transition = external_evidence["summary"][
        "vendor_classification_bracket_pu"
    ]
    agreement_count = sum(point["classification_agreement"] for point in points)
    disagreement_points = [
        {
            "scr": point["scr"],
            "damping_mathworks_pu_per_hz": point[
                "damping_mathworks_pu_per_hz"
            ],
            "external_vendor_outcome": point["external_vendor_outcome"],
            "team_pre_step_stability": point["team_pre_step_stability"],
            "team_post_step_stability": point["team_post_step_stability"],
        }
        for point in points
        if not point["classification_agreement"]
    ]

    return {
        "run_id": "mathworks-team-aligned-eight-point-comparison-v1",
        "status": "completed",
        "analysis_mode": "aligned-coordinate-cross-model-comparison",
        "mapping_contract": {
            "base_frequency_hz": BASE_FREQUENCY_HZ,
            "damping_mathworks_unit": "pu-power-per-Hz",
            "damping_team_native_unit": "pu-power-per-pu-frequency",
            "damping_conversion": "D_team = f_base * D_mathworks",
            "mathworks_model_gain_expression": "vsmDampingConst*powerFreq",
            "team_model_equation": "M*d(Delta_omega_pu)/dt = P_ref - P_meas - D_team*Delta_omega_pu",
            "source_impedance_definition": "abs(Z_source_pu)=1/SCR",
            "x_by_r": X_BY_R,
            "pre_step_active_power_pu": PRE_STEP_ACTIVE_POWER_PU,
            "post_step_active_power_pu": POST_STEP_ACTIVE_POWER_PU,
        },
        "summary": {
            "point_count": len(points),
            "classification_agreement_count": agreement_count,
            "classification_disagreement_count": len(points) - agreement_count,
            "all_team_pre_post_endpoint_classes_equal": all(
                point["team_endpoints_same_class"] for point in points
            ),
            "disagreement_points": disagreement_points,
            "interpretation": (
                "八个对齐坐标中七点分类一致，支持所测范围内控制—电网耦合的定性趋势；"
                "SCR=5、D=1.056 pu/Hz 处不一致，且定量过渡位置未复现。"
            ),
        },
        "points": points,
        "boundary_comparison": {
            "external_vendor_classification_bracket_pu_per_hz": (
                external_transition
            ),
            "team_local_eigenvalue_boundaries": team_boundaries,
            "external_and_team_boundaries_are_same_evidence_type": False,
            "external_lower_minus_team_boundary_pu_per_hz": [
                float(external_transition[0] - boundary["damping_mw_equivalent_pu_per_hz"])
                for boundary in team_boundaries
            ],
            "quantitative_transition_reproduced": False,
        },
        "provenance": {
            "external_evidence_run_id": external_evidence["run_id"],
            "external_source": external_evidence["source"],
            "team_preset_id": "average-dq-smib-verification",
            "team_model": "project-defined-16-state-average-value-dq-v1",
            "deterministic": True,
        },
        "scope": {
            "claim_level": "aligned-coordinate-eight-point-cross-model-screening",
            "external_classifier": "vendor nonlinear time-domain threshold classifier",
            "team_classifier": "local closed-loop eigenvalue spectral abscissa",
            "same_full_physical_model": False,
            "same_classifier": False,
            "same_controller_inner_loops": False,
            "nonlinear_team_step_completed": False,
            "paper_sufficient_condition_evaluated": False,
            "physical_hardware_validation": False,
            "statement": (
                "只对齐阻尼归一化、SCR、X/R、基频和有功工作点；"
                "七点一致不构成模型确认，一点不一致也不构成对任一模型的证伪。"
            ),
        },
    }
