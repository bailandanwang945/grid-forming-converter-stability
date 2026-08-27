"""Frozen three-point nonlinear step study for the aligned team GFM model.

The study targets the sole classification disagreement found in the fixed
MathWorks--team eight-point comparison.  It does not turn the team's
average-value ODE into the MathWorks model and does not classify solver
failure as physical instability.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from backend.core.average_dq_model import _closed_rhs
from backend.core.mathworks_team_comparison import (
    BASE_FREQUENCY_HZ,
    POST_STEP_ACTIVE_POWER_PU,
    PRE_STEP_ACTIVE_POWER_PU,
    build_aligned_team_case,
)


STUDY_ID = "average-dq-aligned-three-point-nonlinear-step-v1"
FIXED_SCR = 5.0
FIXED_DAMPING_MW_PU_PER_HZ = (0.6, 1.056, 2.0)
EXTERNAL_VENDOR_OUTCOMES = ("Unstable", "Unstable", "Stable")
SOLVER_METHODS = ("Radau", "LSODA")
DURATION_S = 8.0
SAMPLE_STEP_S = 0.01
RELATIVE_TOLERANCE = 1.0e-7
ABSOLUTE_TOLERANCE = 1.0e-9
TAIL_WINDOW_S = 0.5
FREQUENCY_BAND_PU = 1.0e-4
ACTIVE_POWER_BAND_PU = 1.0e-2
ANGLE_BAND_RAD = 1.0e-2
GRID_CURRENT_BAND_PU = 2.0e-2
FREQUENCY_DIAGNOSTIC_LIMIT_PU = 0.2
ANGLE_EXCURSION_LIMIT_RAD = float(np.pi)
ABSOLUTE_STATE_LIMIT = 100.0
MAXIMUM_CROSS_SOLVER_STATE_DIFFERENCE = 1.0e-4
MAXIMUM_CROSS_SOLVER_FREQUENCY_DIFFERENCE_HZ = 1.0e-5
MAXIMUM_CROSS_SOLVER_EVENT_TIME_DIFFERENCE_S = 1.0e-5
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULT_ROOT = PROJECT_ROOT / "results" / "average-dq-nonlinear-step"
FROZEN_JSON_FILENAME = "aligned_three_point_nonlinear_step.json"
FROZEN_JSON_SHA256 = (
    "b40b54b15cf3e6d7f32f2531bb1b7f3810867ed439130b6d174b545503736999"
)


class AverageDQNonlinearStepEvidenceError(RuntimeError):
    """Raised when the frozen nonlinear-step evidence cannot be trusted."""


@dataclass(frozen=True)
class _DiagnosticEvent:
    """Terminal event whose name is retained in the evidence payload."""

    name: str
    margin: Callable[[NDArray[np.float64]], float]
    terminal: bool = True
    direction: float = -1.0

    def __call__(self, _time_s: float, state: NDArray[np.float64]) -> float:
        return float(self.margin(state))


def _dominant_mode(model) -> dict[str, float]:
    pole = complex(max(model.poles_per_s, key=lambda item: (item.real, item.imag)))
    return {
        "real_per_s": float(pole.real),
        "oscillation_frequency_hz": float(abs(pole.imag) / (2.0 * np.pi)),
    }


def _settling_time(
    times: NDArray[np.float64],
    errors: NDArray[np.float64],
    band: float,
) -> float | None:
    outside = np.flatnonzero(np.abs(errors) > band)
    if outside.size == 0:
        return 0.0
    last_outside = int(outside[-1])
    if last_outside >= times.size - 1:
        return None
    return float(times[last_outside + 1])


def _simulate_solver(
    pre_model,
    post_model,
    method: str,
) -> dict[str, object]:
    times = np.linspace(
        0.0,
        DURATION_S,
        int(round(DURATION_S / SAMPLE_STEP_S)) + 1,
        dtype=np.float64,
    )
    state0 = pre_model.operating_point.state.copy()
    post_equilibrium = post_model.operating_point.state
    post_references = np.array(
        [
            POST_STEP_ACTIVE_POWER_PU,
            post_model.converter.reactive_power_setpoint_pu,
            post_model.converter.voltage_setpoint_pu,
        ],
        dtype=np.float64,
    )
    parameters = pre_model.parameters
    initial_angle = float(state0[0])
    events = (
        _DiagnosticEvent(
            "converter_current_limit",
            lambda state: parameters.diagnostic_current_limit_pu
            - float(np.linalg.norm(state[4:6])),
        ),
        _DiagnosticEvent(
            "grid_current_limit",
            lambda state: parameters.diagnostic_current_limit_pu
            - float(np.linalg.norm(state[8:10])),
        ),
        _DiagnosticEvent(
            "internal_voltage_limit",
            lambda state: parameters.diagnostic_internal_voltage_limit_pu
            - float(np.linalg.norm(state[14:16])),
        ),
        _DiagnosticEvent(
            "frequency_deviation_limit",
            lambda state: FREQUENCY_DIAGNOSTIC_LIMIT_PU - abs(float(state[1])),
        ),
        _DiagnosticEvent(
            "angle_excursion_limit",
            lambda state: ANGLE_EXCURSION_LIMIT_RAD
            - abs(float(state[0]) - initial_angle),
        ),
        _DiagnosticEvent(
            "absolute_state_limit",
            lambda state: ABSOLUTE_STATE_LIMIT
            - float(np.max(np.abs(state))),
        ),
    )
    start = perf_counter()
    solution = solve_ivp(
        lambda _time, state: _closed_rhs(
            state,
            pre_model.operating_point.grid_voltage_global,
            post_references,
            pre_model.topology,
            parameters,
            pre_model.converter,
            pre_model.line,
        ),
        (0.0, DURATION_S),
        state0,
        t_eval=times,
        method=method,
        rtol=RELATIVE_TOLERANCE,
        atol=ABSOLUTE_TOLERANCE,
        events=events,
    )
    elapsed = perf_counter() - start
    states = solution.y.T
    event_name = None
    event_time_s = None
    for event, event_times in zip(events, solution.t_events, strict=True):
        if event_times.size:
            event_name = event.name
            event_time_s = float(event_times[0])
            break

    if states.size == 0 or not np.all(np.isfinite(states)):
        outcome = "numerical_failure"
    elif event_name is not None:
        outcome = "departed_declared_diagnostic_range"
    elif not solution.success or float(solution.t[-1]) < DURATION_S - 1.0e-9:
        outcome = "numerical_failure"
    else:
        tail = solution.t >= DURATION_S - TAIL_WINDOW_S
        frequency_error = states[:, 1] - post_equilibrium[1]
        active_power_error = states[:, 2] - post_equilibrium[2]
        angle_error = states[:, 0] - post_equilibrium[0]
        grid_current_error = np.linalg.norm(
            states[:, 8:10] - post_equilibrium[8:10], axis=1
        )
        converged = bool(
            np.all(np.abs(frequency_error[tail]) <= FREQUENCY_BAND_PU)
            and np.all(np.abs(active_power_error[tail]) <= ACTIVE_POWER_BAND_PU)
            and np.all(np.abs(angle_error[tail]) <= ANGLE_BAND_RAD)
            and np.all(grid_current_error[tail] <= GRID_CURRENT_BAND_PU)
        )
        outcome = (
            "converged_within_horizon"
            if converged
            else "bounded_not_converged_within_horizon"
        )

    if states.size:
        frequency_error = states[:, 1] - post_equilibrium[1]
        active_power_error = states[:, 2] - post_equilibrium[2]
        angle_error = states[:, 0] - post_equilibrium[0]
        grid_current_error = np.linalg.norm(
            states[:, 8:10] - post_equilibrium[8:10], axis=1
        )
        final_state_error_inf = float(
            np.linalg.norm(states[-1] - post_equilibrium, ord=np.inf)
        )
        maximum_frequency_deviation_hz = float(
            np.max(np.abs(states[:, 1])) * BASE_FREQUENCY_HZ
        )
        maximum_converter_current_pu = float(
            np.max(np.linalg.norm(states[:, 4:6], axis=1))
        )
        maximum_grid_current_pu = float(
            np.max(np.linalg.norm(states[:, 8:10], axis=1))
        )
        maximum_internal_voltage_pu = float(
            np.max(np.linalg.norm(states[:, 14:16], axis=1))
        )
        settling_time_power_s = _settling_time(
            solution.t, active_power_error, ACTIVE_POWER_BAND_PU
        )
        settling_time_frequency_s = _settling_time(
            solution.t, frequency_error, FREQUENCY_BAND_PU
        )
        final_metrics = {
            "frequency_error_pu": float(frequency_error[-1]),
            "active_power_error_pu": float(active_power_error[-1]),
            "angle_error_rad": float(angle_error[-1]),
            "grid_current_error_pu": float(grid_current_error[-1]),
        }
    else:
        final_state_error_inf = None
        maximum_frequency_deviation_hz = None
        maximum_converter_current_pu = None
        maximum_grid_current_pu = None
        maximum_internal_voltage_pu = None
        settling_time_power_s = None
        settling_time_frequency_s = None
        final_metrics = None

    return {
        "method": method,
        "outcome": outcome,
        "solver_success": bool(solution.success),
        "solver_status": int(solution.status),
        "solver_message": str(solution.message),
        "completed_time_s": float(solution.t[-1]) if solution.t.size else 0.0,
        "event_name": event_name,
        "event_time_s": event_time_s,
        "sample_count": int(solution.t.size),
        "nfev": int(solution.nfev),
        "njev": int(solution.njev),
        "nlu": int(solution.nlu),
        "elapsed_wall_time_s": float(elapsed),
        "final_state_error_inf": final_state_error_inf,
        "maximum_frequency_deviation_hz": maximum_frequency_deviation_hz,
        "maximum_converter_current_pu": maximum_converter_current_pu,
        "maximum_grid_current_pu": maximum_grid_current_pu,
        "maximum_internal_voltage_pu": maximum_internal_voltage_pu,
        "active_power_settling_time_s": settling_time_power_s,
        "frequency_settling_time_s": settling_time_frequency_s,
        "final_metrics": final_metrics,
        "time_s": solution.t.tolist(),
        "states": states.tolist(),
    }


def run_aligned_three_point_nonlinear_step_study(
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Run the frozen three-point study with two independent stiff solvers.

    The optional callback reports deterministic start/completion boundaries for
    each expensive solve.  It does not change the equations, solver options or
    returned evidence.
    """

    points = []
    for damping_mw, external_outcome in zip(
        FIXED_DAMPING_MW_PU_PER_HZ,
        EXTERNAL_VENDOR_OUTCOMES,
        strict=True,
    ):
        pre_model = build_aligned_team_case(
            FIXED_SCR, damping_mw, PRE_STEP_ACTIVE_POWER_PU
        )
        post_model = build_aligned_team_case(
            FIXED_SCR, damping_mw, POST_STEP_ACTIVE_POWER_PU
        )
        solver_results = []
        for method in SOLVER_METHODS:
            if progress is not None:
                progress(f"start damping={damping_mw:g} method={method}")
            solver_result = _simulate_solver(pre_model, post_model, method)
            solver_results.append(solver_result)
            if progress is not None:
                progress(
                    f"done damping={damping_mw:g} method={method} "
                    f"outcome={solver_result['outcome']} nfev={solver_result['nfev']}"
                )
        solver_outcomes = [result["outcome"] for result in solver_results]
        solver_events = [result["event_name"] for result in solver_results]
        state_arrays = [
            np.asarray(result["states"], dtype=np.float64)
            for result in solver_results
        ]
        same_state_shape = state_arrays[0].shape == state_arrays[1].shape
        trajectory_difference = (
            float(np.max(np.abs(state_arrays[0] - state_arrays[1])))
            if same_state_shape and state_arrays[0].size
            else None
        )
        frequency_difference = abs(
            float(solver_results[0]["maximum_frequency_deviation_hz"])
            - float(solver_results[1]["maximum_frequency_deviation_hz"])
        )
        event_times = [result["event_time_s"] for result in solver_results]
        if event_times == [None, None]:
            event_time_difference = 0.0
        elif all(value is not None for value in event_times):
            event_time_difference = abs(float(event_times[0]) - float(event_times[1]))
        else:
            event_time_difference = None
        numerical_consistency = bool(
            trajectory_difference is not None
            and trajectory_difference <= MAXIMUM_CROSS_SOLVER_STATE_DIFFERENCE
            and frequency_difference
            <= MAXIMUM_CROSS_SOLVER_FREQUENCY_DIFFERENCE_HZ
            and event_time_difference is not None
            and event_time_difference
            <= MAXIMUM_CROSS_SOLVER_EVENT_TIME_DIFFERENCE_S
        )
        solver_agreement = bool(
            len(set(solver_outcomes)) == 1 and len(set(solver_events)) == 1
            and numerical_consistency
        )
        study_outcome = solver_outcomes[0] if solver_agreement else "numerical_pending"
        points.append(
            {
                "scr": FIXED_SCR,
                "damping_mathworks_pu_per_hz": damping_mw,
                "damping_team_native_pu_per_pu_frequency": (
                    damping_mw * BASE_FREQUENCY_HZ
                ),
                "external_vendor_outcome": external_outcome,
                "team_pre_step_local_stability": pre_model.stability.value,
                "team_post_step_local_stability": post_model.stability.value,
                "team_pre_step_dominant_mode": _dominant_mode(pre_model),
                "team_post_step_dominant_mode": _dominant_mode(post_model),
                "solver_agreement": solver_agreement,
                "solver_consistency": {
                    "same_sampled_state_shape": same_state_shape,
                    "maximum_sampled_state_absolute_difference": (
                        trajectory_difference
                    ),
                    "maximum_frequency_deviation_difference_hz": (
                        frequency_difference
                    ),
                    "event_time_difference_s": event_time_difference,
                    "passed": numerical_consistency,
                },
                "study_outcome": study_outcome,
                "solver_results": solver_results,
            }
        )

    disagreement_point = next(
        point
        for point in points
        if point["damping_mathworks_pu_per_hz"] == 1.056
    )
    return {
        "schema_version": "gfm-average-dq-nonlinear-step-study/1.0",
        "study_id": STUDY_ID,
        "status": "completed",
        "research_question": (
            "团队16状态平均值dq模型在MathWorks—团队八点比较的唯一分歧坐标上，"
            "是否会因0.6→0.8 p.u.有功阶跃表现出超出局部特征根判断的信息？"
        ),
        "contract": {
            "scr": FIXED_SCR,
            "damping_mathworks_pu_per_hz": list(FIXED_DAMPING_MW_PU_PER_HZ),
            "damping_conversion": "D_team = 50 * D_mathworks",
            "active_power_step_pu": [
                PRE_STEP_ACTIVE_POWER_PU,
                POST_STEP_ACTIVE_POWER_PU,
            ],
            "duration_s": DURATION_S,
            "sample_step_s": SAMPLE_STEP_S,
            "solver_methods": list(SOLVER_METHODS),
            "relative_tolerance": RELATIVE_TOLERANCE,
            "absolute_tolerance": ABSOLUTE_TOLERANCE,
            "tail_window_s": TAIL_WINDOW_S,
            "convergence_bands": {
                "frequency_deviation_pu": FREQUENCY_BAND_PU,
                "measured_active_power_pu": ACTIVE_POWER_BAND_PU,
                "angle_rad": ANGLE_BAND_RAD,
                "grid_current_pu": GRID_CURRENT_BAND_PU,
            },
            "diagnostic_exit_limits": {
                "frequency_deviation_pu": FREQUENCY_DIAGNOSTIC_LIMIT_PU,
                "angle_excursion_rad": ANGLE_EXCURSION_LIMIT_RAD,
                "absolute_state": ABSOLUTE_STATE_LIMIT,
                "current_and_internal_voltage": "preset diagnostic limits",
            },
            "cross_solver_consistency_limits": {
                "maximum_sampled_state_absolute_difference": (
                    MAXIMUM_CROSS_SOLVER_STATE_DIFFERENCE
                ),
                "maximum_frequency_deviation_difference_hz": (
                    MAXIMUM_CROSS_SOLVER_FREQUENCY_DIFFERENCE_HZ
                ),
                "maximum_event_time_difference_s": (
                    MAXIMUM_CROSS_SOLVER_EVENT_TIME_DIFFERENCE_S
                ),
            },
            "deterministic": True,
        },
        "points": points,
        "summary": {
            "point_count": len(points),
            "solver_agreement_count": sum(
                bool(point["solver_agreement"]) for point in points
            ),
            "outcome_counts": {
                outcome: sum(point["study_outcome"] == outcome for point in points)
                for outcome in sorted({str(point["study_outcome"]) for point in points})
            },
            "disagreement_coordinate_outcome": disagreement_point["study_outcome"],
            "interpretation": (
                "该结果只区分团队模型在固定阶跃下的收敛、未收敛、诊断域退出或"
                "数值待定；不得据此替代MathWorks供应商分类或物理稳定性结论。"
            ),
        },
        "scope": {
            "team_model_internal_nonlinear_verification": True,
            "same_full_model_as_mathworks": False,
            "emt_validation": False,
            "hardware_validation": False,
            "paper_sufficient_condition_evaluated": False,
            "solver_failure_is_physical_instability": False,
            "diagnostic_exit_is_physical_instability": False,
            "saturation_and_protection_modelled": False,
        },
    }


def load_frozen_aligned_nonlinear_step_evidence(
    result_root: Path = DEFAULT_RESULT_ROOT,
) -> dict[str, Any]:
    """Load the frozen full trace after checking its exact byte digest."""

    path = result_root / FROZEN_JSON_FILENAME
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise AverageDQNonlinearStepEvidenceError(
            f"缺少冻结的团队非线性阶跃产物：{path.name}。"
        ) from error
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != FROZEN_JSON_SHA256:
        raise AverageDQNonlinearStepEvidenceError(
            f"团队非线性阶跃产物 {path.name} 的 SHA-256 不匹配。"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AverageDQNonlinearStepEvidenceError(
            f"团队非线性阶跃产物 {path.name} 不是有效 JSON。"
        ) from error
    summary = payload.get("summary", {})
    scope = payload.get("scope", {})
    if (
        payload.get("schema_version")
        != "gfm-average-dq-nonlinear-step-study/1.0"
        or payload.get("status") != "completed"
        or summary.get("point_count") != 3
        or summary.get("solver_agreement_count") != 3
        or summary.get("disagreement_coordinate_outcome")
        != "converged_within_horizon"
        or scope.get("same_full_model_as_mathworks") is not False
        or scope.get("diagnostic_exit_is_physical_instability") is not False
    ):
        raise AverageDQNonlinearStepEvidenceError(
            "团队非线性阶跃冻结产物的结果或研究边界与固定契约不一致。"
        )
    return payload
