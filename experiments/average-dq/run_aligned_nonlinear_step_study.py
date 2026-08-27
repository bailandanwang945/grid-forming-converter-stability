"""Run the frozen three-point aligned nonlinear active-power step study."""

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
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.average_dq_nonlinear_step_study import (  # noqa: E402
    run_aligned_three_point_nonlinear_step_study,
)


JSON_FILENAME = "aligned_three_point_nonlinear_step.json"
CSV_FILENAME = "aligned_three_point_nonlinear_step_solver_summary.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "average-dq-nonlinear-step"


def build_payload(
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    payload = run_aligned_three_point_nonlinear_step_study(progress=progress)
    return {
        **payload,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entrypoint": (
            "experiments/average-dq/run_aligned_nonlinear_step_study.py"
        ),
    }


def _csv_text(payload: dict[str, Any]) -> str:
    stream = io.StringIO(newline="")
    fieldnames = [
        "scr",
        "damping_mathworks_pu_per_hz",
        "damping_team_native_pu_per_pu_frequency",
        "external_vendor_outcome",
        "team_pre_step_local_stability",
        "team_post_step_local_stability",
        "study_outcome",
        "solver_agreement",
        "solver_method",
        "solver_outcome",
        "solver_success",
        "event_name",
        "event_time_s",
        "completed_time_s",
        "sample_count",
        "nfev",
        "njev",
        "nlu",
        "elapsed_wall_time_s",
        "maximum_frequency_deviation_hz",
        "maximum_converter_current_pu",
        "maximum_grid_current_pu",
        "maximum_internal_voltage_pu",
        "active_power_settling_time_s",
        "frequency_settling_time_s",
        "final_frequency_error_pu",
        "final_active_power_error_pu",
        "final_angle_error_rad",
        "final_grid_current_error_pu",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for point in payload["points"]:
        for solver in point["solver_results"]:
            final_metrics = solver["final_metrics"] or {}
            writer.writerow(
                {
                    "scr": point["scr"],
                    "damping_mathworks_pu_per_hz": point[
                        "damping_mathworks_pu_per_hz"
                    ],
                    "damping_team_native_pu_per_pu_frequency": point[
                        "damping_team_native_pu_per_pu_frequency"
                    ],
                    "external_vendor_outcome": point["external_vendor_outcome"],
                    "team_pre_step_local_stability": point[
                        "team_pre_step_local_stability"
                    ],
                    "team_post_step_local_stability": point[
                        "team_post_step_local_stability"
                    ],
                    "study_outcome": point["study_outcome"],
                    "solver_agreement": point["solver_agreement"],
                    "solver_method": solver["method"],
                    "solver_outcome": solver["outcome"],
                    "solver_success": solver["solver_success"],
                    "event_name": solver["event_name"],
                    "event_time_s": solver["event_time_s"],
                    "completed_time_s": solver["completed_time_s"],
                    "sample_count": solver["sample_count"],
                    "nfev": solver["nfev"],
                    "njev": solver["njev"],
                    "nlu": solver["nlu"],
                    "elapsed_wall_time_s": solver["elapsed_wall_time_s"],
                    "maximum_frequency_deviation_hz": solver[
                        "maximum_frequency_deviation_hz"
                    ],
                    "maximum_converter_current_pu": solver[
                        "maximum_converter_current_pu"
                    ],
                    "maximum_grid_current_pu": solver[
                        "maximum_grid_current_pu"
                    ],
                    "maximum_internal_voltage_pu": solver[
                        "maximum_internal_voltage_pu"
                    ],
                    "active_power_settling_time_s": solver[
                        "active_power_settling_time_s"
                    ],
                    "frequency_settling_time_s": solver[
                        "frequency_settling_time_s"
                    ],
                    "final_frequency_error_pu": final_metrics.get(
                        "frequency_error_pu"
                    ),
                    "final_active_power_error_pu": final_metrics.get(
                        "active_power_error_pu"
                    ),
                    "final_angle_error_rad": final_metrics.get(
                        "angle_error_rad"
                    ),
                    "final_grid_current_error_pu": final_metrics.get(
                        "grid_current_error_pu"
                    ),
                }
            )
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


def run_experiment(
    output_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[Path, Path]:
    payload = build_payload(progress=progress)
    json_path = output_dir / JSON_FILENAME
    csv_path = output_dir / CSV_FILENAME
    _atomic_write(
        json_path,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )
    _atomic_write(csv_path, _csv_text(payload))
    return json_path, csv_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="运行平均值 dq 三点对齐非线性有功阶跃研究。"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录（默认：{DEFAULT_OUTPUT_DIR}）",
    )
    args = parser.parse_args(argv)
    json_path, csv_path = run_experiment(
        args.output_dir.resolve(),
        progress=lambda message: print(
            f"[GFM Nonlinear Step] {message}", flush=True
        ),
    )
    print("AVERAGE_DQ_ALIGNED_NONLINEAR_STEP_STUDY_OK")
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
