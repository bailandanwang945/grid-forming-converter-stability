"""Bounded one-factor stability-boundary continuation for the dq anchor.

The study refines four sign-changing intervals identified by the fixed
19-point ablation.  It separately solves for the tracked extra mode crossing
and the full 16-state spectral-abscissa crossing.  A mode match that does not
pass the frozen gates is reported as pending rather than forced through the
boundary solver.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log, pi

import numpy as np

from backend.core.average_dq_ablation import (
    AnchorModeTrackingContext,
    AverageDQAblationError,
    ModeMatch,
    evaluate_anchor_factors,
    prepare_anchor_mode_tracking,
)
from backend.domain.average_dq_models import AverageDQGFMParameters
from backend.domain.network_models import NetworkTopology


DEFAULT_FACTOR_RELATIVE_TOLERANCE = 1.0e-5
DEFAULT_REAL_PART_TOLERANCE_PER_S = 1.0e-5
DEFAULT_MAXIMUM_ITERATIONS = 40


class AverageDQBoundaryError(ValueError):
    """Raised when a boundary-study input or fixed contract is invalid."""


@dataclass(frozen=True)
class BoundaryPathDefinition:
    path_id: str
    factor_name: str
    label_zh: str
    endpoint_factor: float


BOUNDARY_PATHS = (
    BoundaryPathDefinition(
        path_id="voltage-pi-boundary",
        factor_name="voltage_pi",
        label_zh="电压 PI 同比例增益",
        endpoint_factor=2.0,
    ),
    BoundaryPathDefinition(
        path_id="current-pi-boundary",
        factor_name="current_pi",
        label_zh="电流 PI 同比例增益",
        endpoint_factor=2.0,
    ),
    BoundaryPathDefinition(
        path_id="converter-side-reactance-boundary",
        factor_name="converter_side_reactance",
        label_zh="变流器侧滤波电抗 X1",
        endpoint_factor=0.5,
    ),
    BoundaryPathDefinition(
        path_id="grid-side-reactance-boundary",
        factor_name="grid_side_reactance",
        label_zh="网侧滤波电抗 X2",
        endpoint_factor=2.0,
    ),
)


@dataclass(frozen=True)
class BoundaryTrial:
    factor_value: float
    calculation_status: str
    reason: str
    stability: str | None
    spectral_abscissa_per_s: float | None
    rightmost_pole_per_s: complex | None
    extra_mode_per_s: complex | None
    synchronous_mode_per_s: complex | None
    extra_mode_status: str
    synchronous_mode_status: str
    extra_mode_is_rightmost: bool | None
    extra_match: ModeMatch | None
    algebraic_residual_inf: float | None
    closed_rhs_residual_inf: float | None
    active_power_balance_abs_pu: float | None


@dataclass(frozen=True)
class ScalarBoundaryEstimate:
    metric: str
    status: str
    reason: str
    factor_value: float | None
    initial_interval: tuple[float, float]
    final_interval: tuple[float, float] | None
    real_part_per_s: float | None
    iterations: int


@dataclass(frozen=True)
class BoundaryPathResult:
    definition: BoundaryPathDefinition
    extra_mode_boundary: ScalarBoundaryEstimate
    overall_stability_boundary: ScalarBoundaryEstimate
    boundaries_agree: bool | None
    relative_boundary_difference: float | None
    mode_handoff_observed: bool
    trials: tuple[BoundaryTrial, ...]


@dataclass(frozen=True)
class AverageDQBoundaryStudy:
    topology_id: str
    parameter_set_id: str
    anchor_damping_coefficient_pu: float
    anchor_external_line_reactance_pu: float
    factor_relative_tolerance: float
    real_part_tolerance_per_s: float
    maximum_iterations: int
    paths: tuple[BoundaryPathResult, ...]
    interpretation_boundary: str


def _dominant(poles: np.ndarray) -> complex:
    values = np.asarray(poles, dtype=np.complex128)
    maximum_real = float(np.max(values.real))
    tolerance = 1.0e-10 * max(abs(maximum_real), 1.0)
    candidates = values[np.abs(values.real - maximum_real) <= tolerance]
    return complex(max(candidates, key=lambda value: value.imag))


def _same_mode(first: complex, second: complex) -> bool:
    scale = max(abs(first), abs(second), 1.0)
    return abs(first - second) / scale <= 1.0e-7


class _PathEvaluator:
    def __init__(
        self,
        context: AnchorModeTrackingContext,
        definition: BoundaryPathDefinition,
    ) -> None:
        self.context = context
        self.definition = definition
        self.cache: dict[float, BoundaryTrial] = {}

    def evaluate(self, factor_value: float) -> BoundaryTrial:
        factor = float(factor_value)
        if factor in self.cache:
            return self.cache[factor]
        try:
            model, extra_match, synchronous_match = evaluate_anchor_factors(
                self.context,
                ((self.definition.factor_name, factor),),
            )
        except AverageDQAblationError as error:
            trial = BoundaryTrial(
                factor_value=factor,
                calculation_status="numerical-pending",
                reason=str(error),
                stability=None,
                spectral_abscissa_per_s=None,
                rightmost_pole_per_s=None,
                extra_mode_per_s=None,
                synchronous_mode_per_s=None,
                extra_mode_status="pending",
                synchronous_mode_status="pending",
                extra_mode_is_rightmost=None,
                extra_match=None,
                algebraic_residual_inf=None,
                closed_rhs_residual_inf=None,
                active_power_balance_abs_pu=None,
            )
            self.cache[factor] = trial
            return trial

        rightmost = _dominant(model.poles_per_s)
        extra = extra_match.eigenvalue_per_s
        algebraic_inf = float(
            np.linalg.norm(model.operating_point.algebraic_residual, ord=np.inf)
        )
        trial = BoundaryTrial(
            factor_value=factor,
            calculation_status="valid",
            reason="accepted",
            stability=model.stability.value,
            spectral_abscissa_per_s=float(rightmost.real),
            rightmost_pole_per_s=rightmost,
            extra_mode_per_s=extra,
            synchronous_mode_per_s=synchronous_match.eigenvalue_per_s,
            extra_mode_status=extra_match.status,
            synchronous_mode_status=synchronous_match.status,
            extra_mode_is_rightmost=_same_mode(extra, rightmost),
            extra_match=extra_match,
            algebraic_residual_inf=algebraic_inf,
            closed_rhs_residual_inf=(
                model.operating_point.closed_rhs_residual_inf
            ),
            active_power_balance_abs_pu=abs(
                model.operating_point.active_power_balance_residual_pu
            ),
        )
        self.cache[factor] = trial
        return trial


def _metric_value(trial: BoundaryTrial, metric: str) -> float | None:
    if trial.calculation_status != "valid":
        return None
    if metric == "extra-mode-real-part":
        if trial.extra_mode_status != "matched" or trial.extra_mode_per_s is None:
            return None
        return float(trial.extra_mode_per_s.real)
    if metric == "spectral-abscissa":
        return trial.spectral_abscissa_per_s
    raise RuntimeError(f"未知边界指标：{metric}。")


def _sign(value: float, tolerance: float) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def _relative_interval_width(lower: float, upper: float) -> float:
    return abs(upper - lower) / max(abs(lower), abs(upper), 1.0e-12)


def _solve_scalar_boundary(
    evaluator: _PathEvaluator,
    metric: str,
    first_factor: float,
    second_factor: float,
    *,
    factor_relative_tolerance: float,
    real_part_tolerance_per_s: float,
    maximum_iterations: int,
) -> ScalarBoundaryEstimate:
    lower = min(first_factor, second_factor)
    upper = max(first_factor, second_factor)
    initial_interval = (lower, upper)
    lower_trial = evaluator.evaluate(lower)
    upper_trial = evaluator.evaluate(upper)
    lower_value = _metric_value(lower_trial, metric)
    upper_value = _metric_value(upper_trial, metric)
    if lower_value is None or upper_value is None:
        return ScalarBoundaryEstimate(
            metric=metric,
            status="pending",
            reason="endpoint-calculation-or-mode-tracking-pending",
            factor_value=None,
            initial_interval=initial_interval,
            final_interval=None,
            real_part_per_s=None,
            iterations=0,
        )
    lower_sign = _sign(lower_value, real_part_tolerance_per_s)
    upper_sign = _sign(upper_value, real_part_tolerance_per_s)
    if lower_sign == 0:
        return ScalarBoundaryEstimate(
            metric=metric,
            status="converged",
            reason="lower-endpoint-within-real-part-tolerance",
            factor_value=lower,
            initial_interval=initial_interval,
            final_interval=(lower, lower),
            real_part_per_s=lower_value,
            iterations=0,
        )
    if upper_sign == 0:
        return ScalarBoundaryEstimate(
            metric=metric,
            status="converged",
            reason="upper-endpoint-within-real-part-tolerance",
            factor_value=upper,
            initial_interval=initial_interval,
            final_interval=(upper, upper),
            real_part_per_s=upper_value,
            iterations=0,
        )
    if lower_sign == upper_sign:
        return ScalarBoundaryEstimate(
            metric=metric,
            status="unbracketed",
            reason="initial-endpoints-have-the-same-sign",
            factor_value=None,
            initial_interval=initial_interval,
            final_interval=initial_interval,
            real_part_per_s=None,
            iterations=0,
        )

    last_factor: float | None = None
    last_value: float | None = None
    for iteration in range(1, maximum_iterations + 1):
        midpoint = exp(0.5 * (log(lower) + log(upper)))
        midpoint_trial = evaluator.evaluate(midpoint)
        midpoint_value = _metric_value(midpoint_trial, metric)
        if midpoint_value is None:
            return ScalarBoundaryEstimate(
                metric=metric,
                status="pending",
                reason="midpoint-calculation-or-mode-tracking-pending",
                factor_value=None,
                initial_interval=initial_interval,
                final_interval=(lower, upper),
                real_part_per_s=None,
                iterations=iteration,
            )
        last_factor = midpoint
        last_value = midpoint_value
        midpoint_sign = _sign(midpoint_value, real_part_tolerance_per_s)
        if midpoint_sign == 0:
            return ScalarBoundaryEstimate(
                metric=metric,
                status="converged",
                reason="real-part-tolerance-met",
                factor_value=midpoint,
                initial_interval=initial_interval,
                final_interval=(lower, upper),
                real_part_per_s=midpoint_value,
                iterations=iteration,
            )
        if midpoint_sign == lower_sign:
            lower = midpoint
            lower_value = midpoint_value
            lower_sign = midpoint_sign
        else:
            upper = midpoint
            upper_value = midpoint_value
            upper_sign = midpoint_sign
        if _relative_interval_width(lower, upper) <= factor_relative_tolerance:
            estimate = exp(0.5 * (log(lower) + log(upper)))
            estimate_trial = evaluator.evaluate(estimate)
            estimate_value = _metric_value(estimate_trial, metric)
            if estimate_value is None:
                return ScalarBoundaryEstimate(
                    metric=metric,
                    status="pending",
                    reason="final-estimate-calculation-or-mode-tracking-pending",
                    factor_value=None,
                    initial_interval=initial_interval,
                    final_interval=(lower, upper),
                    real_part_per_s=None,
                    iterations=iteration,
                )
            return ScalarBoundaryEstimate(
                metric=metric,
                status="converged",
                reason="factor-interval-tolerance-met",
                factor_value=estimate,
                initial_interval=initial_interval,
                final_interval=(lower, upper),
                real_part_per_s=estimate_value,
                iterations=iteration,
            )

    return ScalarBoundaryEstimate(
        metric=metric,
        status="maximum-iterations",
        reason="maximum-iterations-reached-before-tolerance",
        factor_value=last_factor,
        initial_interval=initial_interval,
        final_interval=(lower, upper),
        real_part_per_s=last_value,
        iterations=maximum_iterations,
    )


def _boundaries_agree(
    first: ScalarBoundaryEstimate,
    second: ScalarBoundaryEstimate,
    tolerance: float,
) -> tuple[bool | None, float | None]:
    if (
        first.status != "converged"
        or second.status != "converged"
        or first.factor_value is None
        or second.factor_value is None
    ):
        return None, None
    relative_difference = abs(first.factor_value - second.factor_value) / max(
        abs(first.factor_value),
        abs(second.factor_value),
        1.0e-12,
    )
    first_interval = first.final_interval
    second_interval = second.final_interval
    intervals_overlap = bool(
        first_interval
        and second_interval
        and max(first_interval[0], second_interval[0])
        <= min(first_interval[1], second_interval[1])
    )
    return intervals_overlap or relative_difference <= 2.0 * tolerance, float(
        relative_difference
    )


def run_average_dq_boundary_study(
    topology: NetworkTopology,
    parameters: AverageDQGFMParameters,
    *,
    factor_relative_tolerance: float = DEFAULT_FACTOR_RELATIVE_TOLERANCE,
    real_part_tolerance_per_s: float = DEFAULT_REAL_PART_TOLERANCE_PER_S,
    maximum_iterations: int = DEFAULT_MAXIMUM_ITERATIONS,
) -> AverageDQBoundaryStudy:
    """Trace four frozen one-factor boundaries without mutating the inputs."""

    if (
        not isfinite(factor_relative_tolerance)
        or factor_relative_tolerance <= 0.0
        or factor_relative_tolerance > 0.1
    ):
        raise AverageDQBoundaryError(
            "倍率相对容差必须位于 (0, 0.1]。"
        )
    if (
        not isfinite(real_part_tolerance_per_s)
        or real_part_tolerance_per_s <= 0.0
        or real_part_tolerance_per_s > 0.1
    ):
        raise AverageDQBoundaryError(
            "实部容差必须位于 (0, 0.1] s^-1。"
        )
    if maximum_iterations < 1 or maximum_iterations > 80:
        raise AverageDQBoundaryError("最大迭代次数必须位于 [1, 80]。")

    context = prepare_anchor_mode_tracking(topology, parameters)
    results: list[BoundaryPathResult] = []
    for definition in BOUNDARY_PATHS:
        evaluator = _PathEvaluator(context, definition)
        extra_boundary = _solve_scalar_boundary(
            evaluator,
            "extra-mode-real-part",
            1.0,
            definition.endpoint_factor,
            factor_relative_tolerance=factor_relative_tolerance,
            real_part_tolerance_per_s=real_part_tolerance_per_s,
            maximum_iterations=maximum_iterations,
        )
        overall_boundary = _solve_scalar_boundary(
            evaluator,
            "spectral-abscissa",
            1.0,
            definition.endpoint_factor,
            factor_relative_tolerance=factor_relative_tolerance,
            real_part_tolerance_per_s=real_part_tolerance_per_s,
            maximum_iterations=maximum_iterations,
        )
        agree, difference = _boundaries_agree(
            extra_boundary,
            overall_boundary,
            factor_relative_tolerance,
        )
        trials = tuple(
            evaluator.cache[key] for key in sorted(evaluator.cache)
        )
        mode_handoff = any(
            trial.calculation_status == "valid"
            and trial.extra_mode_is_rightmost is False
            for trial in trials
        )
        results.append(
            BoundaryPathResult(
                definition=definition,
                extra_mode_boundary=extra_boundary,
                overall_stability_boundary=overall_boundary,
                boundaries_agree=agree,
                relative_boundary_difference=difference,
                mode_handoff_observed=mode_handoff,
                trials=trials,
            )
        )

    anchor_converter = context.topology.grid_forming_converters[0]
    anchor_line = context.topology.lines[0]
    return AverageDQBoundaryStudy(
        topology_id=context.topology.id,
        parameter_set_id=context.parameters.id,
        anchor_damping_coefficient_pu=float(
            anchor_converter.damping_coefficient_pu
        ),
        anchor_external_line_reactance_pu=anchor_line.reactance_pu,
        factor_relative_tolerance=float(factor_relative_tolerance),
        real_part_tolerance_per_s=float(real_part_tolerance_per_s),
        maximum_iterations=int(maximum_iterations),
        paths=tuple(results),
        interpretation_boundary=(
            "仅描述团队16状态平均值dq单机模型在四条冻结单因素路径上的"
            "数值边界；不证明唯一因果、全参数域单调性、论文定理边界，"
            "也不构成EMT或硬件稳定性确认。"
        ),
    )


def pole_to_record(value: complex | None) -> dict[str, float] | None:
    """Return the common traceable pole representation used by adapters."""

    if value is None:
        return None
    return {
        "real_per_s": float(value.real),
        "imag_per_s": float(value.imag),
        "real_hz": float(value.real / (2.0 * pi)),
        "oscillation_frequency_hz": float(abs(value.imag) / (2.0 * pi)),
    }


def _mode_match_to_record(match: ModeMatch | None) -> dict[str, object] | None:
    if match is None:
        return None
    return {
        "pole": pole_to_record(match.eigenvalue_per_s),
        "reference_pole": pole_to_record(match.reference_eigenvalue_per_s),
        "status": match.status,
        "reason": match.reason,
        "path_label": match.path_label,
        "cumulative_tracking_steps": match.path_steps,
        "minimum_step_right_mac": match.right_mac,
        "minimum_step_left_mac": match.left_mac,
        "minimum_step_combined_mac": match.combined_mac,
        "maximum_step_normalized_eigenvalue_distance": (
            match.normalized_distance
        ),
        "minimum_step_local_candidate_margin": (
            match.relative_confidence_margin
        ),
        "maximum_eigenvalue_condition_number": match.condition_number,
        "maximum_right_eigenpair_residual": match.right_residual,
        "maximum_left_eigenpair_residual": match.left_residual,
        "thresholds": {
            "minimum_individual_mac": match.minimum_individual_mac_threshold,
            "maximum_normalized_eigenvalue_distance": (
                match.maximum_normalized_distance_threshold
            ),
            "maximum_eigenvalue_condition_number": (
                match.maximum_condition_number_threshold
            ),
            "maximum_eigenpair_residual": (
                match.maximum_eigenpair_residual_threshold
            ),
            "minimum_local_candidate_margin": (
                match.minimum_relative_margin_threshold
            ),
        },
    }


def _estimate_to_record(estimate: ScalarBoundaryEstimate) -> dict[str, object]:
    return {
        "metric": estimate.metric,
        "status": estimate.status,
        "reason": estimate.reason,
        "factor_value": estimate.factor_value,
        "initial_interval": list(estimate.initial_interval),
        "final_interval": (
            list(estimate.final_interval)
            if estimate.final_interval is not None
            else None
        ),
        "real_part_per_s": estimate.real_part_per_s,
        "iterations": estimate.iterations,
    }


def boundary_study_as_dict(study: AverageDQBoundaryStudy) -> dict[str, object]:
    """Serialize the complete study without dropping pending evidence."""

    paths: list[dict[str, object]] = []
    for path in study.paths:
        trials: list[dict[str, object]] = []
        for trial in path.trials:
            trials.append(
                {
                    "factor_value": trial.factor_value,
                    "calculation_status": trial.calculation_status,
                    "reason": trial.reason,
                    "stability": trial.stability,
                    "spectral_abscissa_per_s": (
                        trial.spectral_abscissa_per_s
                    ),
                    "rightmost_pole": pole_to_record(
                        trial.rightmost_pole_per_s
                    ),
                    "extra_mode": _mode_match_to_record(trial.extra_match),
                    "synchronous_mode_pole": pole_to_record(
                        trial.synchronous_mode_per_s
                    ),
                    "synchronous_mode_status": trial.synchronous_mode_status,
                    "extra_mode_is_rightmost": trial.extra_mode_is_rightmost,
                    "residuals": {
                        "algebraic_inf": trial.algebraic_residual_inf,
                        "closed_rhs_inf": trial.closed_rhs_residual_inf,
                        "active_power_balance_abs_pu": (
                            trial.active_power_balance_abs_pu
                        ),
                    },
                }
            )
        paths.append(
            {
                "path_id": path.definition.path_id,
                "factor_name": path.definition.factor_name,
                "label_zh": path.definition.label_zh,
                "baseline_factor": 1.0,
                "screening_endpoint_factor": (
                    path.definition.endpoint_factor
                ),
                "extra_mode_boundary": _estimate_to_record(
                    path.extra_mode_boundary
                ),
                "overall_stability_boundary": _estimate_to_record(
                    path.overall_stability_boundary
                ),
                "boundaries_agree": path.boundaries_agree,
                "relative_boundary_difference": (
                    path.relative_boundary_difference
                ),
                "mode_handoff_observed": path.mode_handoff_observed,
                "trial_count": len(trials),
                "trials": trials,
            }
        )
    return {
        "topology_id": study.topology_id,
        "parameter_set_id": study.parameter_set_id,
        "fixed_anchor": {
            "damping_coefficient_pu": (
                study.anchor_damping_coefficient_pu
            ),
            "external_line_reactance_pu": (
                study.anchor_external_line_reactance_pu
            ),
            "state_definition": "fixed-16-state-per-unit-and-delta-rad-basis",
        },
        "numerical_contract": {
            "factor_midpoint": "geometric-log-scale",
            "factor_relative_tolerance": study.factor_relative_tolerance,
            "real_part_tolerance_per_s": study.real_part_tolerance_per_s,
            "maximum_iterations": study.maximum_iterations,
            "failed_tracking_policy": "pending-not-forced",
        },
        "path_count": len(paths),
        "converged_extra_mode_boundaries": sum(
            path.extra_mode_boundary.status == "converged"
            for path in study.paths
        ),
        "converged_overall_boundaries": sum(
            path.overall_stability_boundary.status == "converged"
            for path in study.paths
        ),
        "agreeing_boundary_count": sum(
            path.boundaries_agree is True for path in study.paths
        ),
        "paths": paths,
        "interpretation_boundary": study.interpretation_boundary,
    }
