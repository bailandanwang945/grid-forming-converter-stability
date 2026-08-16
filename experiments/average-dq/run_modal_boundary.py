"""Run and export four fixed average-dq one-factor stability boundaries."""

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

from backend.core.average_dq_boundary import (  # noqa: E402
    boundary_study_as_dict,
    run_average_dq_boundary_study,
)
from backend.core.average_dq_presets import (  # noqa: E402
    average_dq_ablation_anchor_metadata,
    build_average_dq_ablation_anchor_case,
)


JSON_FILENAME = "modal_boundary_results.json"
CSV_FILENAME = "modal_boundary_trials.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "average-dq-boundary"


def build_payload() -> dict[str, Any]:
    topology, parameters = build_average_dq_ablation_anchor_case()
    study = run_average_dq_boundary_study(topology, parameters)
    return {
        "run_id": "average-dq-fixed-anchor-one-factor-boundaries-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entrypoint": "experiments/average-dq/run_modal_boundary.py",
        "result": boundary_study_as_dict(study),
        "model_scope": {
            "claim_level": "fixed-team-average-dq-one-factor-boundaries-only",
            "paper_theorem_evaluated": False,
            "physical_validation": False,
            "causal_identification": False,
            "arbitrary_parameter_paths_supported": False,
            "statement": study.interpretation_boundary,
        },
        "provenance": {
            **average_dq_ablation_anchor_metadata(),
            "implementation": "backend.core.average_dq_boundary",
            "point_calculation": (
                "fresh-workpoint-and-central-difference-linearization"
            ),
            "continuation": "adaptive-modal-tracking-plus-log-bisection",
            "interpolation_used_for_reported_boundaries": False,
        },
    }


def _csv_text(payload: dict[str, Any]) -> str:
    stream = io.StringIO(newline="")
    fieldnames = [
        "path_id",
        "factor_name",
        "factor_value",
        "calculation_status",
        "stability",
        "spectral_abscissa_per_s",
        "rightmost_real_per_s",
        "rightmost_imag_per_s",
        "extra_real_per_s",
        "extra_imag_per_s",
        "extra_mode_status",
        "extra_mode_is_rightmost",
        "extra_right_mac",
        "extra_left_mac",
        "extra_normalized_distance",
        "extra_condition_number",
        "extra_right_residual",
        "extra_left_residual",
        "synchronous_real_per_s",
        "synchronous_imag_per_s",
        "algebraic_residual_inf",
        "closed_rhs_residual_inf",
        "active_power_balance_abs_pu",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for path in payload["result"]["paths"]:
        for trial in path["trials"]:
            rightmost = trial["rightmost_pole"] or {}
            extra = trial["extra_mode"] or {}
            extra_pole = extra.get("pole") or {}
            sync_pole = trial["synchronous_mode_pole"] or {}
            residuals = trial["residuals"]
            writer.writerow(
                {
                    "path_id": path["path_id"],
                    "factor_name": path["factor_name"],
                    "factor_value": trial["factor_value"],
                    "calculation_status": trial["calculation_status"],
                    "stability": trial["stability"],
                    "spectral_abscissa_per_s": trial[
                        "spectral_abscissa_per_s"
                    ],
                    "rightmost_real_per_s": rightmost.get("real_per_s"),
                    "rightmost_imag_per_s": rightmost.get("imag_per_s"),
                    "extra_real_per_s": extra_pole.get("real_per_s"),
                    "extra_imag_per_s": extra_pole.get("imag_per_s"),
                    "extra_mode_status": extra.get("status"),
                    "extra_mode_is_rightmost": trial[
                        "extra_mode_is_rightmost"
                    ],
                    "extra_right_mac": extra.get("minimum_step_right_mac"),
                    "extra_left_mac": extra.get("minimum_step_left_mac"),
                    "extra_normalized_distance": extra.get(
                        "maximum_step_normalized_eigenvalue_distance"
                    ),
                    "extra_condition_number": extra.get(
                        "maximum_eigenvalue_condition_number"
                    ),
                    "extra_right_residual": extra.get(
                        "maximum_right_eigenpair_residual"
                    ),
                    "extra_left_residual": extra.get(
                        "maximum_left_eigenpair_residual"
                    ),
                    "synchronous_real_per_s": sync_pole.get("real_per_s"),
                    "synchronous_imag_per_s": sync_pole.get("imag_per_s"),
                    "algebraic_residual_inf": residuals["algebraic_inf"],
                    "closed_rhs_residual_inf": residuals["closed_rhs_inf"],
                    "active_power_balance_abs_pu": residuals[
                        "active_power_balance_abs_pu"
                    ],
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


def run_experiment(output_dir: Path) -> tuple[Path, Path]:
    payload = build_payload()
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
        description="运行固定平均值 dq 锚点的四条一维临界边界。"
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
