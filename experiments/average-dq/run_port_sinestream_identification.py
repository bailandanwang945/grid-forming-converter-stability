"""Run and export the three-frequency nonlinear port-identification study."""

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

from backend.core.average_dq_model import build_average_dq_model  # noqa: E402
from backend.core.average_dq_port_identification import (  # noqa: E402
    evaluate_fixed_port_identification_verification,
)
from backend.core.average_dq_presets import (  # noqa: E402
    PRESET_ID,
    build_average_dq_verification_case,
)


JSON_FILENAME = "port_sinestream_identification.json"
CSV_FILENAME = "port_sinestream_identification_elements.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "average-dq-port-identification"


def build_payload() -> dict[str, Any]:
    topology, parameters = build_average_dq_verification_case()
    model = build_average_dq_model(topology, parameters)
    verification = evaluate_fixed_port_identification_verification(model)
    return {
        "run_id": "average-dq-three-frequency-port-sinestream-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entrypoint": (
            "experiments/average-dq/run_port_sinestream_identification.py"
        ),
        "preset_id": PRESET_ID,
        "summary": verification["summary"],
        "contract": verification["contract"],
        "points": verification["points"],
        "amplitude_halving_check_at_2hz": verification[
            "amplitude_halving_check_at_2hz"
        ],
        "model_scope": verification["model_scope"],
        "provenance": {
            **verification["provenance"],
            "mathworks_workflow_reference": (
                "https://www.mathworks.com/help/releases/R2024b/slcontrol/ug/"
                "estimate-frequency-response-matlab-code.html"
            ),
            "mathworks_signal_reference": (
                "https://www.mathworks.com/help/releases/R2024b/slcontrol/"
                "generate-perturbation-signals.html"
            ),
        },
    }


def _csv_text(payload: dict[str, Any]) -> str:
    stream = io.StringIO(newline="")
    fieldnames = [
        "frequency_hz",
        "row",
        "column",
        "identified_real",
        "identified_imag",
        "identified_magnitude",
        "identified_phase_deg",
        "linearized_real",
        "linearized_imag",
        "linearized_magnitude",
        "linearized_phase_deg",
        "magnitude_relative_error",
        "phase_error_deg",
        "voltage_matrix_condition_number",
        "maximum_harmonic_residual_ratio",
        "solver_method",
        "passed",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for point in payload["points"]:
        for row in range(2):
            for column in range(2):
                identified = point["identified_admittance_pu"][row][column]
                linearized = point["linearized_admittance_pu"][row][column]
                writer.writerow(
                    {
                        "frequency_hz": point["frequency_hz"],
                        "row": row,
                        "column": column,
                        "identified_real": identified["real"],
                        "identified_imag": identified["imag"],
                        "identified_magnitude": identified["magnitude"],
                        "identified_phase_deg": identified["phase_deg"],
                        "linearized_real": linearized["real"],
                        "linearized_imag": linearized["imag"],
                        "linearized_magnitude": linearized["magnitude"],
                        "linearized_phase_deg": linearized["phase_deg"],
                        "magnitude_relative_error": point[
                            "magnitude_relative_error"
                        ][row][column],
                        "phase_error_deg": point["phase_error_deg"][row][column],
                        "voltage_matrix_condition_number": point[
                            "voltage_matrix_condition_number"
                        ],
                        "maximum_harmonic_residual_ratio": point[
                            "maximum_harmonic_residual_ratio"
                        ],
                        "solver_method": point["solver_method"],
                        "passed": point["passed"],
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
        description="运行平均值 dq 三频点非线性端口正弦辨识。"
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
