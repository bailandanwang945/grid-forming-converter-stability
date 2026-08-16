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

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.average_dq_model import build_average_dq_model  # noqa: E402
from backend.core.average_dq_port_identification import (  # noqa: E402
    PortIdentificationPoint,
    identify_port_admittance_with_sinestream,
)
from backend.core.average_dq_presets import (  # noqa: E402
    PRESET_ID,
    build_average_dq_verification_case,
)


JSON_FILENAME = "port_sinestream_identification.json"
CSV_FILENAME = "port_sinestream_identification_elements.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results" / "average-dq-port-identification"


def _complex_value(value: complex) -> dict[str, float]:
    return {
        "real": float(value.real),
        "imag": float(value.imag),
        "magnitude": float(abs(value)),
        "phase_deg": float(np.angle(value, deg=True)),
    }


def _complex_matrix(values: np.ndarray) -> list[list[dict[str, float]]]:
    return [
        [_complex_value(complex(value)) for value in row]
        for row in np.asarray(values)
    ]


def _point_payload(point: PortIdentificationPoint) -> dict[str, Any]:
    return {
        "frequency_hz": point.frequency_hz,
        "settling_periods": point.settling_periods,
        "measurement_periods": point.measurement_periods,
        "samples_per_period": point.samples_per_period,
        "solver_method": point.solver_method,
        "identified_admittance_pu": _complex_matrix(
            point.identified_admittance_pu
        ),
        "linearized_admittance_pu": _complex_matrix(
            point.linearized_admittance_pu
        ),
        "pcc_voltage_phasor_matrix_pu": _complex_matrix(
            point.pcc_voltage_phasor_matrix_pu
        ),
        "device_current_phasor_matrix_pu": _complex_matrix(
            point.device_current_phasor_matrix_pu
        ),
        "voltage_matrix_condition_number": (
            point.voltage_matrix_condition_number
        ),
        "magnitude_relative_error": point.magnitude_relative_error.tolist(),
        "phase_error_deg": point.phase_error_deg.tolist(),
        "maximum_magnitude_relative_error": (
            point.maximum_magnitude_relative_error
        ),
        "maximum_phase_error_deg": point.maximum_phase_error_deg,
        "maximum_harmonic_residual_ratio": (
            point.maximum_harmonic_residual_ratio
        ),
        "passed": point.passed,
    }


def build_payload() -> dict[str, Any]:
    topology, parameters = build_average_dq_verification_case()
    model = build_average_dq_model(topology, parameters)
    study = identify_port_admittance_with_sinestream(model)
    half_amplitude = identify_port_admittance_with_sinestream(
        model,
        [2.0],
        source_amplitude_pu=0.5 * study.source_amplitude_pu,
    ).points[0]
    baseline_2hz = next(
        point for point in study.points if point.frequency_hz == 2.0
    )
    amplitude_halving_difference = np.abs(
        half_amplitude.identified_admittance_pu
        - baseline_2hz.identified_admittance_pu
    )
    amplitude_halving_relative_difference = amplitude_halving_difference / np.maximum(
        np.abs(baseline_2hz.identified_admittance_pu),
        np.finfo(np.float64).eps,
    )
    points = [_point_payload(point) for point in study.points]
    return {
        "run_id": "average-dq-three-frequency-port-sinestream-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entrypoint": (
            "experiments/average-dq/run_port_sinestream_identification.py"
        ),
        "preset_id": PRESET_ID,
        "summary": {
            "passed": study.passed,
            "frequency_count": len(study.points),
            "maximum_magnitude_relative_error": max(
                point.maximum_magnitude_relative_error
                for point in study.points
            ),
            "maximum_phase_error_deg": max(
                point.maximum_phase_error_deg for point in study.points
            ),
            "maximum_harmonic_residual_ratio": max(
                point.maximum_harmonic_residual_ratio
                for point in study.points
            ),
            "maximum_voltage_matrix_condition_number": max(
                point.voltage_matrix_condition_number
                for point in study.points
            ),
        },
        "contract": {
            "frequencies_hz": [point.frequency_hz for point in study.points],
            "source_amplitude_pu": study.source_amplitude_pu,
            "minimum_settling_time_s": study.minimum_settling_time_s,
            "measurement_periods": study.points[0].measurement_periods,
            "samples_per_period": study.points[0].samples_per_period,
            "magnitude_error_limit": study.magnitude_error_limit,
            "phase_error_limit_deg": study.phase_error_limit_deg,
            "harmonic_residual_limit": study.harmonic_residual_limit,
            "voltage_matrix_condition_limit": (
                study.voltage_matrix_condition_limit
            ),
            "frame": study.frame,
            "current_direction": study.current_direction,
        },
        "points": points,
        "amplitude_halving_check_at_2hz": {
            "baseline_amplitude_pu": study.source_amplitude_pu,
            "halved_amplitude_pu": 0.5 * study.source_amplitude_pu,
            "maximum_element_relative_difference": float(
                np.max(amplitude_halving_relative_difference)
            ),
            "halved_amplitude_point": _point_payload(half_amplitude),
        },
        "model_scope": {
            "claim_level": "internal-nonlinear-versus-linear-software-verification",
            "physical_validation": False,
            "emt_validation": False,
            "paper_fig8_fixture": False,
            "statement": (
                "在团队定义的单机平均值 dq 校核算例和所测三个频点内，"
                "非线性闭环正弦辨识支持端口线性化实现的一致性；"
                "该结果不确认真实硬件或电磁暂态模型。"
            ),
        },
        "provenance": {
            "implementation": (
                "backend.core.average_dq_port_identification"
            ),
            "identification_path": study.identification_path,
            "device_open_port_spectral_abscissa_per_s": (
                study.device_open_port_spectral_abscissa_per_s
            ),
            "mathworks_release_checked": "R2024b",
            "mathworks_functions_checked": [
                "frestimate",
                "frest.Sinestream",
                "tfestimate",
            ],
            "mathworks_workflow_reference": (
                "https://www.mathworks.com/help/releases/R2024b/slcontrol/ug/"
                "estimate-frequency-response-matlab-code.html"
            ),
            "mathworks_signal_reference": (
                "https://www.mathworks.com/help/releases/R2024b/slcontrol/"
                "generate-perturbation-signals.html"
            ),
            "randomness": "none-deterministic-ode-and-least-squares",
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
