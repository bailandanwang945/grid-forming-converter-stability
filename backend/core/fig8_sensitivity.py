"""Sensitivity study for the pinned, sampled Fig. 8 screening result.

The study deliberately reuses the 1000 author-fixture samples.  Frequency
density rows are retrospective subgrids, not newly evaluated transfer-function
samples, and therefore cannot establish continuous-frequency coverage.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterable

import numpy as np

from backend.core.fig8_kernel import evaluate_fig8_case


FREQUENCY_POINT_COUNTS = (9, 15, 31, 63, 125, 250, 500, 1000)
DECISION_TOLERANCES = (1.0e-12, 1.0e-10, 1.0e-8, 1.0e-6)
COMMON_MATRIX_SCALES = (1.0e-9, 1.0e-6, 1.0, 1.0e6, 1.0e9)
CASE_IDS = ("fig8_D_0p05", "fig8_D_0p5")


class Fig8SensitivityError(ValueError):
    """Raised when the fixed sensitivity contract is violated."""


def _signed_status(margin: float, tolerance: float) -> str:
    if margin > tolerance:
        return "pass"
    if margin < -tolerance:
        return "fail"
    return "indeterminate"


def _sample_indices(full_count: int, requested_count: int) -> np.ndarray:
    if requested_count < 2 or requested_count > full_count:
        raise Fig8SensitivityError(
            "频率子网格点数必须位于 [2, 原始网格点数]。"
        )
    indices = np.unique(
        np.rint(np.linspace(0, full_count - 1, requested_count)).astype(int)
    )
    if indices.size != requested_count:
        raise Fig8SensitivityError("频率子网格索引发生重复。")
    return indices


def _phase_status(
    scan: dict[str, Any], index: int, phase_tolerance_rad: float
) -> str:
    margins = (
        scan["upper_phase_margin"][index],
        scan["lower_phase_margin"][index],
        scan["converter_phase_spread_margin"][index],
    )
    if any(value is None for value in margins):
        return str(scan["phase_status"][index])
    values = tuple(float(value) for value in margins)
    if all(value > phase_tolerance_rad for value in values):
        return "pass"
    if any(value < -phase_tolerance_rad for value in values):
        return "fail"
    return "indeterminate"


def _coverage(gain_status: str, phase_status: str) -> str:
    if gain_status == "pass" and phase_status == "pass":
        return "both-pass"
    if gain_status == "pass":
        return "gain-pass"
    if phase_status == "pass":
        return "phase-pass"
    if gain_status == "fail" and phase_status == "fail":
        return "uncovered"
    return "indeterminate"


def _classify_indices(
    scan: dict[str, Any],
    indices: Iterable[int],
    *,
    gain_relative_tolerance: float,
    phase_tolerance_rad: float,
    common_matrix_scale: float = 1.0,
) -> dict[str, Any]:
    if (
        not np.isfinite(gain_relative_tolerance)
        or gain_relative_tolerance <= 0.0
        or not np.isfinite(phase_tolerance_rad)
        or phase_tolerance_rad <= 0.0
    ):
        raise Fig8SensitivityError("判定容差必须为有限正数。")
    if not np.isfinite(common_matrix_scale) or common_matrix_scale <= 0.0:
        raise Fig8SensitivityError("共同矩阵尺度必须为有限正数。")

    selected = np.asarray(tuple(indices), dtype=int)
    frequencies = np.asarray(scan["frequencies_hz"], dtype=float)[selected]
    gain_status: list[str] = []
    phase_status: list[str] = []
    coverage: list[str] = []
    for index in selected:
        gain = _signed_status(
            float(scan["gain_margin"][index]) * common_matrix_scale,
            gain_relative_tolerance
            * float(scan["gain_tolerance_scale"][index])
            * common_matrix_scale,
        )
        phase = _phase_status(scan, int(index), phase_tolerance_rad)
        gain_status.append(gain)
        phase_status.append(phase)
        coverage.append(_coverage(gain, phase))

    uncovered_indices = np.flatnonzero(np.asarray(coverage) == "uncovered")
    return {
        "sample_count": int(selected.size),
        "gain_counts": {
            name: gain_status.count(name)
            for name in ("pass", "fail", "indeterminate")
        },
        "phase_counts": {
            name: phase_status.count(name)
            for name in ("pass", "fail", "indeterminate")
        },
        "uncovered_count": coverage.count("uncovered"),
        "indeterminate_coverage_count": coverage.count("indeterminate"),
        "first_uncovered_frequency_hz": (
            float(frequencies[uncovered_indices[0]])
            if uncovered_indices.size
            else None
        ),
        "last_uncovered_frequency_hz": (
            float(frequencies[uncovered_indices[-1]])
            if uncovered_indices.size
            else None
        ),
        "coverage": coverage,
    }


def _case_sensitivity(case_id: str) -> dict[str, Any]:
    baseline = evaluate_fig8_case(case_id)
    scan = baseline["frequency_scan"]
    frequencies = np.asarray(scan["frequencies_hz"], dtype=float)
    full_indices = np.arange(frequencies.size)
    reconstructed = _classify_indices(
        scan,
        full_indices,
        gain_relative_tolerance=1.0e-10,
        phase_tolerance_rad=1.0e-10,
    )
    baseline_coverage = list(scan["coverage"])
    baseline_uncovered_indices = set(
        np.flatnonzero(np.asarray(baseline_coverage) == "uncovered").tolist()
    )

    density_rows: list[dict[str, Any]] = []
    for requested_count in FREQUENCY_POINT_COUNTS:
        indices = _sample_indices(frequencies.size, requested_count)
        row = _classify_indices(
            scan,
            indices,
            gain_relative_tolerance=1.0e-10,
            phase_tolerance_rad=1.0e-10,
        )
        selected_uncovered = baseline_uncovered_indices.intersection(
            indices.tolist()
        )
        row.update(
            {
                "requested_point_count": requested_count,
                "maximum_log10_frequency_step": float(
                    np.max(np.diff(np.log10(frequencies[indices])))
                ),
                "detects_uncovered_region": row["uncovered_count"] > 0,
                "observed_full_grid_uncovered_points": len(
                    selected_uncovered
                ),
                "unobserved_full_grid_uncovered_points": (
                    len(baseline_uncovered_indices) - len(selected_uncovered)
                ),
            }
        )
        row.pop("coverage")
        density_rows.append(row)

    tolerance_rows: list[dict[str, Any]] = []
    for tolerance in DECISION_TOLERANCES:
        row = _classify_indices(
            scan,
            full_indices,
            gain_relative_tolerance=tolerance,
            phase_tolerance_rad=tolerance,
        )
        row.update(
            {
                "gain_relative_tolerance": tolerance,
                "phase_tolerance_rad": tolerance,
                "coverage_mismatch_from_default": sum(
                    left != right
                    for left, right in zip(
                        row["coverage"], baseline_coverage, strict=True
                    )
                ),
            }
        )
        row.pop("coverage")
        tolerance_rows.append(row)

    scale_rows: list[dict[str, Any]] = []
    for scale in COMMON_MATRIX_SCALES:
        row = _classify_indices(
            scan,
            full_indices,
            gain_relative_tolerance=1.0e-10,
            phase_tolerance_rad=1.0e-10,
            common_matrix_scale=scale,
        )
        row.update(
            {
                "common_post_transformation_matrix_scale": scale,
                "coverage_mismatch_from_unit_scale": sum(
                    left != right
                    for left, right in zip(
                        row["coverage"], baseline_coverage, strict=True
                    )
                ),
            }
        )
        row.pop("coverage")
        scale_rows.append(row)

    return {
        "case_id": case_id,
        "damping": baseline["damping"],
        "closed_loop_reference": baseline["closed_loop_reference"],
        "baseline": {
            "frequency_point_count": int(frequencies.size),
            "frequency_minimum_hz": float(frequencies[0]),
            "frequency_maximum_hz": float(frequencies[-1]),
            "uncovered_count": baseline["counts"]["uncovered"],
            "indeterminate_coverage_count": baseline["counts"][
                "indeterminate_coverage"
            ],
            "reconstructed_coverage_mismatch_count": sum(
                left != right
                for left, right in zip(
                    reconstructed["coverage"], baseline_coverage, strict=True
                )
            ),
        },
        "frequency_density": density_rows,
        "decision_tolerance": tolerance_rows,
        "common_matrix_scale": scale_rows,
    }


@lru_cache(maxsize=1)
def evaluate_fig8_sensitivity() -> dict[str, Any]:
    """Return deterministic sensitivity evidence for both pinned cases."""

    cases = [_case_sensitivity(case_id) for case_id in CASE_IDS]
    return {
        "status": "completed",
        "analysis_mode": "retrospective-sampled-fig8-sensitivity-v1",
        "cases": cases,
        "summary": {
            "baseline_reconstruction_exact": all(
                case["baseline"]["reconstructed_coverage_mismatch_count"]
                == 0
                for case in cases
            ),
            "common_scale_invariant_on_tested_range": all(
                row["coverage_mismatch_from_unit_scale"] == 0
                for case in cases
                for row in case["common_matrix_scale"]
            ),
            "stable_case_remains_covered_in_all_tested_settings": all(
                row["uncovered_count"] == 0
                for case in cases
                if case["closed_loop_reference"] == "stable"
                for study in (
                    "frequency_density",
                    "decision_tolerance",
                    "common_matrix_scale",
                )
                for row in case[study]
            ),
        },
        "experiment_contract": {
            "frequency_point_counts": list(FREQUENCY_POINT_COUNTS),
            "decision_tolerances": list(DECISION_TOLERANCES),
            "common_matrix_scales": list(COMMON_MATRIX_SCALES),
            "frequency_sampling_method": (
                "rounded-equal-index-subgrid-including-both-endpoints"
            ),
            "randomness": "none-deterministic",
            "failure_conditions": [
                "default full-grid reconstruction differs from pinned kernel",
                "stable pinned case gains an uncovered sample",
                "positive common scale changes a sampled classification",
            ],
        },
        "model_scope": {
            "claim_level": "retrospective-finite-grid-sensitivity-only",
            "statement": (
                "频率密度实验只对子采样作者1000点夹具，不生成新的频率响应；"
                "容差实验只改变已解析裕度的最终判定门；共同尺度是整形后矩阵"
                "表示的正数缩放，不是物理参数扰动。"
            ),
            "continuous_frequency_coverage_proved": False,
            "paper_theorem_evaluated": False,
            "physical_model_perturbed": False,
        },
    }
