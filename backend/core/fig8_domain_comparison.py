"""Load and validate the frozen Fig. 8 same-domain comparison evidence."""

from __future__ import annotations

import csv
import json
import sys
from functools import lru_cache
from pathlib import Path


CLASSIFICATIONS = (
    "criterion-covered-stable",
    "stable-not-covered",
    "unstable-not-covered",
    "numerical-pending",
    "consistency-violation",
)


def _bundled_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def comparison_root() -> Path:
    return (
        _bundled_root()
        / "results"
        / "comparison"
        / "fig8-damping-grid-strength"
    )


def _float(row: dict[str, str], name: str) -> float:
    try:
        return float(row[name])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid comparison column {name!r}.") from error


def _integer(row: dict[str, str], name: str) -> int:
    value = _float(row, name)
    if not value.is_integer():
        raise ValueError(f"Comparison column {name!r} must be integral.")
    return int(value)


@lru_cache(maxsize=1)
def load_fig8_domain_comparison() -> dict:
    """Return validated, JSON-ready comparison evidence."""

    root = comparison_root()
    summary_path = root / "summary.json"
    csv_path = root / "parameter_domain.csv"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    with csv_path.open(encoding="utf-8", newline="") as stream:
        raw_rows = list(csv.DictReader(stream))

    rows: list[dict] = []
    for raw in raw_rows:
        classification = raw.get("final_classification", "")
        if classification not in CLASSIFICATIONS:
            raise ValueError(f"Unknown comparison classification {classification!r}.")
        rows.append(
            {
                "impedance_scale_kappa": _float(raw, "impedance_scale_kappa"),
                "scr": _float(raw, "SCR"),
                "damping_d": _float(raw, "damping_D"),
                "maximum_real_pole_hz": _float(raw, "maximum_real_pole_Hz"),
                "dominant_oscillation_frequency_hz": _float(
                    raw, "dominant_oscillation_frequency_Hz"
                ),
                "closed_loop_reference": raw["closed_loop_reference"],
                "sampled_criterion_status": raw["sampled_criterion_status"],
                "classification": classification,
                "gain_pass_count": _integer(raw, "gain_pass_count"),
                "gain_fail_count": _integer(raw, "gain_fail_count"),
                "gain_indeterminate_count": _integer(
                    raw, "gain_indeterminate_count"
                ),
                "phase_pass_count": _integer(raw, "phase_pass_count"),
                "phase_fail_count": _integer(raw, "phase_fail_count"),
                "phase_indeterminate_count": _integer(
                    raw, "phase_indeterminate_count"
                ),
                "uncovered_frequency_count": _integer(
                    raw, "uncovered_frequency_count"
                ),
                "indeterminate_frequency_count": _integer(
                    raw, "indeterminate_frequency_count"
                ),
            }
        )

    kappa_values = [float(value) for value in summary["kappaGrid"]]
    damping_values = [float(value) for value in summary["dampingGrid"]]
    expected_points = len(kappa_values) * len(damping_values)
    if len(rows) != expected_points or len(rows) != summary["parameterPointCount"]:
        raise ValueError("Comparison grid dimensions do not match the row count.")
    if len({(row["impedance_scale_kappa"], row["damping_d"]) for row in rows}) != len(
        rows
    ):
        raise ValueError("Comparison parameter points are not unique.")

    actual_counts = {
        name: sum(row["classification"] == classification for row in rows)
        for name, classification in (
            ("criterionCoveredStable", "criterion-covered-stable"),
            ("stableNotCovered", "stable-not-covered"),
            ("unstableNotCovered", "unstable-not-covered"),
            ("numericalPending", "numerical-pending"),
            ("consistencyViolation", "consistency-violation"),
        )
    }
    if actual_counts != summary["classificationCounts"]:
        raise ValueError("Comparison summary counts do not match the CSV evidence.")
    if actual_counts["consistencyViolation"] != 0:
        raise ValueError("Criterion-covered points are not a subset of stable points.")

    return {
        "status": "completed",
        "analysis_mode": "author-fig8-same-model-damping-grid-strength-comparison",
        "axes": {
            "impedance_scale_kappa": kappa_values,
            "scr_by_kappa": [
                next(
                    row["scr"]
                    for row in rows
                    if row["impedance_scale_kappa"] == kappa
                )
                for kappa in kappa_values
            ],
            "damping_d": damping_values,
            "row_axis": "VSM damping D",
            "column_axis": "line impedance scale kappa (reported with SCR)",
        },
        "summary": summary,
        "rows": rows,
        "provenance": {
            "source_kind": "matlab-generated-pinned-author-model-evidence",
            "generator": (
                "experiments/comparison/run_fig8_parameter_domain_comparison.m"
            ),
            "source_workbook": summary["sourceWorkbook"],
            "portable_behavior": "read-only frozen evidence; no MATLAB required",
            "claim_boundary": summary["screeningBoundary"],
            "interpretation": summary["interpretation"],
            "closed_loop_boundary": summary["closedLoopBoundary"],
            "claim_boundary_zh": (
                "本结果仅为有限频率样本上的条件性筛查，不构成论文连续全频定理的证明；"
                "相位覆盖依赖已声明的最近邻分支假设。"
            ),
            "interpretation_zh": (
                "“参考稳定但判据未覆盖”用于量化固定模型与参数域内观察到的充分条件"
                "保守性；它不意味着系统失稳，也不否定论文定理。"
            ),
            "closed_loop_boundary_zh": (
                "闭环特征根是冻结作者模型上的有限精度参考，不是物理系统的绝对真值。"
            ),
        },
    }
