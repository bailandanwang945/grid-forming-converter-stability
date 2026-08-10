"""Run and export the fixed 19-point average-dq modal ablation study."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.average_dq_ablation import (  # noqa: E402
    ModeMatch,
    run_average_dq_anchor_ablation,
)
from backend.core.average_dq_presets import (  # noqa: E402
    average_dq_ablation_anchor_metadata,
    build_average_dq_ablation_anchor_case,
)


JSON_FILENAME = "modal_ablation_results.json"
CSV_FILENAME = "modal_ablation_points.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "average-dq-ablation"
TRACKING_BOUNDARY = (
    "局部候选间隔不是全局指派唯一性证明；参与度只作当前固定状态坐标下的"
    "模态诊断。19点结果不证明唯一因果、全参数域单调性、硬件或电磁暂态系统稳定性。"
)


def _pole(value: complex) -> dict[str, float]:
    return {
        "real_per_s": float(value.real),
        "imag_per_s": float(value.imag),
        "real_hz": float(value.real / (2.0 * 3.141592653589793)),
        "imag_hz": float(value.imag / (2.0 * 3.141592653589793)),
    }


def _tracking(match: ModeMatch) -> dict[str, Any]:
    return {
        "pole": _pole(match.eigenvalue_per_s),
        "reference_pole": _pole(match.reference_eigenvalue_per_s),
        "status": match.status,
        "reason": match.reason,
        "candidate_index_is_internal_only": True,
        "path_label": match.path_label,
        "cumulative_tracking_steps": match.path_steps,
        "minimum_step_right_mac": match.right_mac,
        "minimum_step_left_mac": match.left_mac,
        "minimum_step_combined_mac": match.combined_mac,
        "maximum_step_normalized_eigenvalue_distance": match.normalized_distance,
        "minimum_step_confidence": match.confidence,
        "maximum_step_second_candidate_confidence": match.second_best_confidence,
        "minimum_step_local_candidate_margin": match.relative_confidence_margin,
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
            "minimum_local_candidate_margin": match.minimum_relative_margin_threshold,
        },
    }


def _point_payload(point: Any) -> dict[str, Any]:
    return {
        "scenario_id": point.scenario_id,
        "factors": dict(point.factors),
        "damping_coefficient_pu": point.damping_coefficient_pu,
        "line_reactance_pu": point.line_reactance_pu,
        "stability": point.stability,
        "rightmost_pole": _pole(point.rightmost_pole_per_s),
        "poles": [_pole(value) for value in point.poles_per_s],
        "extra_mode": _tracking(point.extra_mode),
        "synchronous_mode": _tracking(point.synchronous_mode),
        "extra_group_participation": dict(point.extra_group_participation),
        "synchronous_group_participation": dict(
            point.synchronous_group_participation
        ),
        "residuals": {
            "algebraic_inf": point.residuals.algebraic_inf,
            "closed_rhs_inf": point.residuals.closed_rhs_inf,
            "device_rhs_inf": point.residuals.device_rhs_inf,
            "active_power_balance_abs_pu": (
                point.residuals.active_power_balance_abs_pu
            ),
        },
    }


def build_payload() -> dict[str, Any]:
    topology, parameters = build_average_dq_ablation_anchor_case()
    study = run_average_dq_anchor_ablation(topology, parameters)
    points = [_point_payload(point) for point in study.points]
    stability_counts = {
        label: sum(point["stability"] == label for point in points)
        for label in ("stable", "marginal", "unstable")
    }
    extra_counts = {
        label: sum(point["extra_mode"]["status"] == label for point in points)
        for label in ("matched", "pending")
    }
    synchronous_counts = {
        label: sum(point["synchronous_mode"]["status"] == label for point in points)
        for label in ("matched", "pending")
    }
    return {
        "run_id": "average-dq-fixed-anchor-modal-ablation-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entrypoint": "experiments/average-dq/run_modal_ablation.py",
        "fixed_anchor": {
            "damping_coefficient_pu": 60.0,
            "external_line_reactance_pu": 0.1,
            "state_definition": "fixed-16-state-per-unit-and-delta-rad-basis",
            "topology_id": study.topology_id,
            "parameter_set_id": study.parameter_set_id,
        },
        "summary": {
            "point_count": study.point_count,
            "stability_counts": stability_counts,
            "extra_mode_tracking_counts": extra_counts,
            "synchronous_mode_tracking_counts": synchronous_counts,
        },
        "baseline": {
            "extra_mode": _pole(study.baseline_extra_mode_per_s),
            "synchronous_mode": _pole(study.baseline_synchronous_mode_per_s),
        },
        "state_scaling": dict(study.state_scaling),
        "state_scaling_scope": study.state_scaling_scope,
        "points": points,
        "model_scope": {
            "claim_level": "fixed-team-average-dq-ablation-only",
            "tracking_boundary": TRACKING_BOUNDARY,
            "paper_theorem_evaluated": False,
            "physical_validation": False,
            "causal_identification": False,
        },
        "provenance": {
            **average_dq_ablation_anchor_metadata(),
            "implementation": "backend.core.average_dq_ablation",
            "point_calculation": "fresh-workpoint-and-central-difference-linearization",
            "interpolation_used_for_reported_points": False,
        },
    }


def _csv_text(points: list[dict[str, Any]]) -> str:
    stream = io.StringIO(newline="")
    fieldnames = [
        "scenario_id", "factors_json", "damping_coefficient_pu",
        "line_reactance_pu", "stability", "rightmost_real_per_s",
        "rightmost_imag_per_s", "extra_real_per_s", "extra_imag_per_s",
        "extra_tracking_status", "extra_tracking_reason", "extra_path_label",
        "extra_right_mac", "extra_left_mac", "extra_normalized_distance",
        "synchronous_real_per_s", "synchronous_imag_per_s",
        "synchronous_tracking_status", "synchronous_tracking_reason",
        "synchronous_path_label", "extra_group_participation_json",
        "synchronous_group_participation_json", "algebraic_residual_inf",
        "closed_rhs_residual_inf", "device_rhs_residual_inf",
        "active_power_balance_abs_pu",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for point in points:
        writer.writerow({
            "scenario_id": point["scenario_id"],
            "factors_json": json.dumps(point["factors"], ensure_ascii=False, sort_keys=True, allow_nan=False),
            "damping_coefficient_pu": point["damping_coefficient_pu"],
            "line_reactance_pu": point["line_reactance_pu"],
            "stability": point["stability"],
            "rightmost_real_per_s": point["rightmost_pole"]["real_per_s"],
            "rightmost_imag_per_s": point["rightmost_pole"]["imag_per_s"],
            "extra_real_per_s": point["extra_mode"]["pole"]["real_per_s"],
            "extra_imag_per_s": point["extra_mode"]["pole"]["imag_per_s"],
            "extra_tracking_status": point["extra_mode"]["status"],
            "extra_tracking_reason": point["extra_mode"]["reason"],
            "extra_path_label": point["extra_mode"]["path_label"],
            "extra_right_mac": point["extra_mode"]["minimum_step_right_mac"],
            "extra_left_mac": point["extra_mode"]["minimum_step_left_mac"],
            "extra_normalized_distance": point["extra_mode"]["maximum_step_normalized_eigenvalue_distance"],
            "synchronous_real_per_s": point["synchronous_mode"]["pole"]["real_per_s"],
            "synchronous_imag_per_s": point["synchronous_mode"]["pole"]["imag_per_s"],
            "synchronous_tracking_status": point["synchronous_mode"]["status"],
            "synchronous_tracking_reason": point["synchronous_mode"]["reason"],
            "synchronous_path_label": point["synchronous_mode"]["path_label"],
            "extra_group_participation_json": json.dumps(point["extra_group_participation"], sort_keys=True, allow_nan=False),
            "synchronous_group_participation_json": json.dumps(point["synchronous_group_participation"], sort_keys=True, allow_nan=False),
            "algebraic_residual_inf": point["residuals"]["algebraic_inf"],
            "closed_rhs_residual_inf": point["residuals"]["closed_rhs_inf"],
            "device_rhs_residual_inf": point["residuals"]["device_rhs_inf"],
            "active_power_balance_abs_pu": point["residuals"]["active_power_balance_abs_pu"],
        })
    return stream.getvalue()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def run_experiment(output_dir: Path) -> tuple[Path, Path]:
    payload = build_payload()
    json_path = output_dir / JSON_FILENAME
    csv_path = output_dir / CSV_FILENAME
    json_text = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    _atomic_write(json_path, json_text)
    _atomic_write(csv_path, _csv_text(payload["points"]))
    return json_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="运行固定 D=60、X=0.1 p.u. 的 19 点平均值 dq 模态消融。"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录（默认：{DEFAULT_OUTPUT_DIR}）",
    )
    args = parser.parse_args(argv)
    json_path, csv_path = run_experiment(args.output_dir.resolve())
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
