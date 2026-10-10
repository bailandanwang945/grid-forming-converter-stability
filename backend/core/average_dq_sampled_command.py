"""Opt-in experimental sampled dq-command comparisons.

This is not a digital-controller or physical PWM implementation. No experiment
results, fixed outcomes, or theorem evaluations enter the calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
from scipy.linalg import eig, expm

from backend.core.average_dq_model import AverageDQModel, J, STATE_LABELS

EXPECTED_STATE_LABELS = (
    "delta_rad",
    "frequency_deviation_pu",
    "measured_active_power_pu",
    "measured_reactive_power_pu",
    "converter_current_d_pu",
    "converter_current_q_pu",
    "capacitor_voltage_d_pu",
    "capacitor_voltage_q_pu",
    "grid_current_d_pu",
    "grid_current_q_pu",
    "voltage_integrator_d_pu",
    "voltage_integrator_q_pu",
    "current_integrator_d_pu",
    "current_integrator_q_pu",
    "internal_voltage_d_pu",
    "internal_voltage_q_pu",
)
HOLDING_FRAMES = ("local-control-dq", "global-synchronous-dq")
LABEL_TOLERANCE_PER_S = 1e-5
RESIDUAL_TOLERANCE = 1e-9
TINY_PERIOD_PENDING_S = 1e-8
ASSUMPTIONS = (
    "Experimental opt-in analysis of one declared 16-state average-value model.",
    "Only the modulation command envelope is sampled; PI, outer loops, filters and phase synthesis remain continuous.",
    "Local-control dq hold is not physical alpha-beta/abc hold; global-synchronous dq is also not a PWM implementation.",
    "Global held buffer uses equilibrium-aligned axes q=R(-delta*)*Delta(v_global).",
    "One-step delay applies the old complete held command snapshot and queues the current snapshot for the next cycle.",
    "Zero-order hold integration is exact for the declared linear plant under a constant input, not for digital hardware.",
    "The same-hold first-order lag tau=(delay_steps+0.5)*Ts is a low-frequency approximation, not an equivalent physical actuator.",
    "Stability labels use the complete spectrum, including two buffer modes for one-step delay.",
    "Numerical pending thresholds and step differences are diagnostics, not guaranteed eigenvalue error bounds.",
    "No switching, saturation, quantization, multirate execution, EMT or physical confirmation; no safe sampling-period prescription.",
    "Novelty has not been established; matrix exponential and sampled-feedback methods are existing methods.",
)


class SampledCommandError(ValueError):
    """A predictable invalid-model/input or uncomputable-matrix error."""


def _real_scalar(value, name, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise SampledCommandError(
            f"{name} must be a finite real scalar, not bool or complex"
        )
    result = float(value)
    if not np.isfinite(result) or (positive and result <= 0):
        raise SampledCommandError(
            f"{name} must be finite" + (" and positive" if positive else "")
        )
    return result


def _contains_forbidden(value, depth=0):
    if depth > 32:
        return True  # Bound recursion for cyclic/pathologically nested inputs.
    if isinstance(value, (bool, np.bool_, complex, np.complexfloating)):
        return True
    if isinstance(value, np.ndarray):
        # Reject object arrays wholesale instead of traversing arbitrarily large
        # nested object graphs. Numeric ndarray dtype already describes entries.
        return value.dtype.kind in "bcO"
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden(v, depth + 1) for v in value)
    return False


def _array(value, name, ndim=2):
    if _contains_forbidden(value):
        raise SampledCommandError(f"{name} cannot contain bool or complex entries")
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise SampledCommandError(f"{name} must be a rectangular real array") from error
    if raw.dtype.kind not in "fiu" or raw.ndim != ndim or 0 in raw.shape:
        raise SampledCommandError(
            f"{name} must be a nonempty real numeric {ndim}-dimensional array"
        )
    out = np.array(raw, dtype=float, copy=True)
    if not np.all(np.isfinite(out)):
        raise SampledCommandError(f"{name} must contain only finite values")
    return out


def _delay(value):
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, Integral)
        or value not in (0, 1)
    ):
        raise SampledCommandError("delay_steps must be integer 0 or 1, not bool")
    return int(value)


def _frame(value):
    if not isinstance(value, str) or value not in HOLDING_FRAMES:
        raise SampledCommandError(
            "holding_frame must be local-control-dq or global-synchronous-dq"
        )
    return value


def _plant(a0, b, f):
    a0, b, f = _array(a0, "a0"), _array(b, "b"), _array(f, "f")
    n = a0.shape[0]
    if a0.shape != (n, n) or b.shape[0] != n or f.shape != (b.shape[1], n):
        raise SampledCommandError("a0 must be nxn, b nxm and f mxn")
    return a0, b, f


@dataclass(frozen=True)
class SampledCommandMatrices:
    phi: np.ndarray
    E: np.ndarray
    Gamma: np.ndarray
    sampling_period_s: float
    delay_steps: int


def sampled_command_matrices(a0, b, f, sampling_period_s, *, delay_steps=0):
    """Generic finite-dimensional plant helper, including singular A0.

    Delay 1 has state [x, previous held input]; its bottom row queues F*x,
    not F*x_next and not a current-angle re-rotation of an old snapshot.
    """
    period = _real_scalar(sampling_period_s, "sampling_period_s", positive=True)
    delay = _delay(delay_steps)
    a0, b, f = _plant(a0, b, f)
    n, m = b.shape
    augmented = np.zeros((n + m, n + m))
    augmented[:n, :n] = a0
    augmented[:n, n:] = b
    try:
        with np.errstate(over="raise", invalid="raise"):
            transition = expm(augmented * period)
            e, gamma = transition[:n, :n], transition[:n, n:]
            phi = (
                e + gamma @ f
                if delay == 0
                else np.block([[e, gamma], [f, np.zeros((m, m))]])
            )
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SampledCommandError(
            "matrix exponential could not be evaluated finitely"
        ) from error
    if not np.all(np.isfinite(phi)):
        raise SampledCommandError("sampled transition contains nonfinite entries")
    return SampledCommandMatrices(phi.copy(), e.copy(), gamma.copy(), period, delay)


def first_order_command_lag_matrix(a0, b, f, tau_s):
    a0, b, f = _plant(a0, b, f)
    tau = _real_scalar(tau_s, "tau_s", positive=True)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            matrix = np.block([[a0, b], [f / tau, -np.eye(b.shape[1]) / tau]])
    except FloatingPointError as error:
        raise SampledCommandError(
            "lag time constant produces nonfinite coefficients"
        ) from error
    if not np.all(np.isfinite(matrix)):
        raise SampledCommandError("lag matrix contains nonfinite coefficients")
    return matrix


@dataclass(frozen=True)
class AverageDQCommandSplit:
    a0: np.ndarray
    b: np.ndarray
    f: np.ndarray
    C: np.ndarray
    original_matrix: np.ndarray
    original_tau_s: float
    holding_frame: str
    original_state_labels: tuple[str, ...]


def split_average_dq_sampled_command(
    model, *, holding_frame="local-control-dq", state_labels=None
):
    """Adapt only the declared AverageDQModel; shape-only mocks are rejected."""
    holding_frame = _frame(holding_frame)
    if type(model) is not AverageDQModel:
        raise SampledCommandError(
            "model must be the declared AverageDQModel, not a shape-only mock"
        )
    labels = STATE_LABELS if state_labels is None else state_labels
    if (
        not isinstance(labels, (tuple, list))
        or tuple(labels) != EXPECTED_STATE_LABELS
        or tuple(STATE_LABELS) != EXPECTED_STATE_LABELS
    ):
        raise SampledCommandError(
            "the declared 16-state labels/order are not supported"
        )
    matrix = _array(model.linearization.closed_state_matrix, "closed_state_matrix")
    state = _array(model.operating_point.state, "operating_point.state", 1)
    if matrix.shape != (16, 16) or state.shape != (16,):
        raise SampledCommandError(
            "declared model requires exactly 16 states in the supported order"
        )
    tau = _real_scalar(
        model.parameters.modulation_time_constant_s,
        "modulation_time_constant_s",
        positive=True,
    )
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            expected = -np.eye(2) / tau
    except FloatingPointError as error:
        raise SampledCommandError(
            "modulation_time_constant_s produces nonfinite coefficients"
        ) from error
    error = np.linalg.norm(matrix[14:, 14:] - expected) / max(
        1, np.linalg.norm(expected)
    )
    if error > 2e-7:
        raise SampledCommandError(
            "A22 must be -I/Tmod; unsupported direct modulation-state feedback"
        )
    residual = _real_scalar(
        model.operating_point.closed_rhs_residual_inf, "closed_rhs_residual_inf"
    )
    if abs(residual) > 1e-8:
        raise SampledCommandError(
            "operating-point residual exceeds the supported contract"
        )
    a0, b, f = matrix[:14, :14].copy(), matrix[:14, 14:].copy(), tau * matrix[14:, :14]
    c = np.zeros((2, 14))
    c[:, 0] = J @ state[14:]
    if holding_frame == "global-synchronous-dq":
        a0 = a0 - b @ c
        f = f + c
    return AverageDQCommandSplit(
        a0, b, f.copy(), c, matrix, tau, holding_frame, EXPECTED_STATE_LABELS
    )


def _compatible_comparison(model, comparison):
    split_average_dq_sampled_command(comparison)
    if model.topology.model_dump(mode="json") != comparison.topology.model_dump(
        mode="json"
    ) or model.parameters.model_dump(mode="json") != comparison.parameters.model_dump(
        mode="json"
    ):
        raise SampledCommandError(
            "comparison_model must have identical topology and controller parameters"
        )
    if not np.allclose(
        model.operating_point.state, comparison.operating_point.state, rtol=0, atol=1e-8
    ):
        raise SampledCommandError("comparison_model must have the same operating point")
    if not np.allclose(
        model.operating_point.grid_voltage_global,
        comparison.operating_point.grid_voltage_global,
        rtol=0,
        atol=1e-8,
    ):
        raise SampledCommandError("comparison_model must have the same grid voltage")
    step = _real_scalar(
        model.linearization.relative_step, "linearization.relative_step", positive=True
    )
    second = _real_scalar(
        comparison.linearization.relative_step,
        "comparison.relative_step",
        positive=True,
    )
    if step == second:
        raise SampledCommandError(
            "comparison_model must use a different finite-difference relative_step"
        )
    return step, second


def analyze_sampled_command_matrix(
    matrix, *, sampling_period_s=None, comparison_matrix=None
):
    """JSON-safe full-spectrum diagnostics; uncertainty is explicitly heuristic."""
    matrix = _array(matrix, "matrix")
    if matrix.shape[0] != matrix.shape[1]:
        raise SampledCommandError("matrix must be square")
    period = (
        None
        if sampling_period_s is None
        else _real_scalar(sampling_period_s, "sampling_period_s", positive=True)
    )
    try:
        values, vectors = eig(matrix)
        norm = max(1, float(np.linalg.norm(matrix, 2)))
        residual = max(
            float(
                np.linalg.norm(matrix @ vectors[:, k] - values[k] * vectors[:, k])
                / (norm * np.linalg.norm(vectors[:, k]))
            )
            for k in range(len(values))
        )
    except (ValueError, np.linalg.LinAlgError) as error:
        raise SampledCommandError("spectrum computation failed") from error
    if not np.all(np.isfinite(values)) or not np.isfinite(residual):
        raise SampledCommandError("spectrum computation produced nonfinite values")
    radius = float(max(abs(values))) if period is not None else None
    metric = (
        float(max(values.real))
        if period is None
        else (float(np.log(radius) / period) if radius > 0 else None)
    )
    if metric is not None and not np.isfinite(metric):
        metric = None
    reasons = []
    if residual > RESIDUAL_TOLERANCE:
        reasons.append("eigenpair-residual-above-threshold")
    if period is not None and period <= TINY_PERIOD_PENDING_S:
        reasons.append("tiny-period-growth-rate-numerically-unresolved")
    if metric is None:
        reasons.append("finite-growth-rate-unavailable")
    difference = None
    second_residual = None
    if comparison_matrix is not None:
        other = _array(comparison_matrix, "comparison_matrix")
        if other.shape != matrix.shape:
            raise SampledCommandError("comparison_matrix must have the same dimension")
        secondary = analyze_sampled_command_matrix(other, sampling_period_s=period)
        second_residual = secondary["maximum_eigenpair_relative_residual"]
        if second_residual > RESIDUAL_TOLERANCE:
            reasons.append("comparison-eigenpair-residual-above-threshold")
        if metric is not None and secondary["metric_per_s"] is not None:
            difference = abs(metric - secondary["metric_per_s"])
        else:
            reasons.append("comparison-growth-rate-unavailable")
    uncertainty = max(
        LABEL_TOLERANCE_PER_S, 0 if difference is None else 10 * difference
    )
    if metric is not None and abs(metric) <= uncertainty:
        reasons.append("near-boundary-within-diagnostic-uncertainty")
    order = np.lexsort((values.imag, values.real))
    return dict(
        spectrum=[[float(values[k].real), float(values[k].imag)] for k in order],
        dimension=len(values),
        metric_per_s=metric,
        metric_name="alpha" if period is None else "log_rho_over_Ts",
        metric_units="s^-1",
        spectral_radius=radius,
        maximum_eigenpair_relative_residual=residual,
        classification="numerical-pending"
        if reasons
        else ("stable" if metric < 0 else "unstable"),
        pending_reasons=reasons,
        step_check_status="step-check-not-provided"
        if comparison_matrix is None
        else "step-comparison-evaluated",
        step_metric_difference_per_s=difference,
        comparison_eigenpair_relative_residual=second_residual,
        label_uncertainty_per_s=uncertainty,
        numerical_uncertainty_kind="heuristic-not-a-root-error-guarantee",
    )


def compare_average_dq_sampled_command(
    model,
    sampling_period_s,
    *,
    holding_frame="local-control-dq",
    delay_steps=0,
    comparison_model=None,
    state_labels=None,
):
    """Explicit experimental comparison returning only JSON-safe data."""
    period = _real_scalar(sampling_period_s, "sampling_period_s", positive=True)
    delay = _delay(delay_steps)
    primary = split_average_dq_sampled_command(
        model, holding_frame=holding_frame, state_labels=state_labels
    )
    step = _real_scalar(
        model.linearization.relative_step, "linearization.relative_step", positive=True
    )
    tau = (delay + 0.5) * period

    def build(split):
        return dict(
            original_continuous_modulation=split.original_matrix,
            ideal_instantaneous=split.a0 + split.b @ split.f,
            same_hold_low_frequency_lag=first_order_command_lag_matrix(
                split.a0, split.b, split.f, tau
            ),
            sampled_command=sampled_command_matrices(
                split.a0, split.b, split.f, period, delay_steps=delay
            ).phi,
        )

    matrices = build(primary)
    secondary = None
    step_check = dict(
        status="step-check-not-provided",
        primary_relative_step=step,
        comparison_relative_step=None,
        interpretation="Diagnostic finite-difference comparison, not a guaranteed root error bound.",
    )
    if comparison_model is not None:
        step, second_step = _compatible_comparison(model, comparison_model)
        second = split_average_dq_sampled_command(
            comparison_model, holding_frame=holding_frame, state_labels=state_labels
        )
        secondary = build(second)
        step_check.update(
            status="step-comparison-evaluated", comparison_relative_step=second_step
        )
    references = {}
    for name, matrix in matrices.items():
        references[name] = analyze_sampled_command_matrix(
            matrix,
            sampling_period_s=period if name == "sampled_command" else None,
            comparison_matrix=None if secondary is None else secondary[name],
        )
        references[name]["name"] = name
        if name == "original_continuous_modulation":
            labels = list(EXPECTED_STATE_LABELS)
        elif name == "ideal_instantaneous" or (
            name == "sampled_command" and delay == 0
        ):
            labels = list(EXPECTED_STATE_LABELS[:14])
        elif name == "sampled_command":
            labels = list(EXPECTED_STATE_LABELS[:14]) + [
                "previous_held_command_d_pu",
                "previous_held_command_q_pu",
            ]
        else:
            labels = list(EXPECTED_STATE_LABELS[:14]) + [
                "same_hold_lag_command_d_pu",
                "same_hold_lag_command_q_pu",
            ]
        references[name]["state_labels"] = labels
    return dict(
        schema_version="average-dq-sampled-command-experimental/1.0",
        experimental=True,
        sampling_period_s=period,
        holding_frame=holding_frame,
        delay_steps=delay,
        phase_matched_tau_s=tau,
        original_continuous_tau_s=primary.original_tau_s,
        state_dimension=references["sampled_command"]["dimension"],
        original_state_labels=list(EXPECTED_STATE_LABELS),
        sampled_buffer_definition="none"
        if delay == 0
        else "previous complete held command in the declared holding frame; global buffer equilibrium-aligned",
        benchmark_coverage="within-tested-period-range-only"
        if 1e-4 <= period <= 2e-3
        else "not-yet-benchmark-covered",
        benchmark_coverage_note="Period coverage alone does not validate this operating point or establish physical validity.",
        theorem_status="not-evaluated-by-sampled-api",
        physical_validation_status="not-performed",
        step_check=step_check,
        references=references,
        assumptions=list(ASSUMPTIONS),
        limits=dict(
            tiny_period_pending_s=TINY_PERIOD_PENDING_S,
            label_tolerance_per_s=LABEL_TOLERANCE_PER_S,
            eigenpair_residual_tolerance=RESIDUAL_TOLERANCE,
            step_difference_multiplier=10,
        ),
    )
