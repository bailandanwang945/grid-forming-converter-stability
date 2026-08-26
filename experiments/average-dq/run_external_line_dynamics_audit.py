"""Write the fixed static-versus-dynamic external-line evidence."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.average_dq_external_line_dynamics import (  # noqa: E402
    run_external_line_dynamics_audit,
)


def run_experiment(output_dir: Path) -> tuple[Path, Path]:
    payload = run_external_line_dynamics_audit()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "external_line_dynamics.json"
    csv_path = output_dir / "external_line_dynamics_points.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "line_reactance_pu",
                "line_resistance_pu",
                "line_dynamics_fraction",
                "spectral_abscissa_per_s",
                "stable_by_eigenvalues",
                "low_mode_real_per_s",
                "low_mode_frequency_hz",
                "low_mode_tracking_status",
                "intermediate_mode_real_per_s",
                "intermediate_mode_frequency_hz",
                "intermediate_mode_tracking_status",
                "wide_mode_real_per_s",
                "wide_mode_frequency_hz",
                "wide_mode_tracking_status",
            ),
        )
        writer.writeheader()
        for case in payload["cases"]:
            for point in case["points"]:
                writer.writerow(
                    {
                        "line_reactance_pu": case["line_reactance_pu"],
                        "line_resistance_pu": case["line_resistance_pu"],
                        "line_dynamics_fraction": point[
                            "line_dynamics_fraction"
                        ],
                        "spectral_abscissa_per_s": point[
                            "spectral_abscissa_per_s"
                        ],
                        "stable_by_eigenvalues": point[
                            "stable_by_eigenvalues"
                        ],
                        "low_mode_real_per_s": point[
                            "low_frequency_mode"
                        ]["pole"]["real_per_s"],
                        "low_mode_frequency_hz": point[
                            "low_frequency_mode"
                        ]["pole"]["frequency_hz"],
                        "low_mode_tracking_status": point[
                            "low_frequency_mode"
                        ]["tracking"]["status"],
                        "intermediate_mode_real_per_s": point[
                            "intermediate_frequency_mode"
                        ]["pole"]["real_per_s"],
                        "intermediate_mode_frequency_hz": point[
                            "intermediate_frequency_mode"
                        ]["pole"]["frequency_hz"],
                        "intermediate_mode_tracking_status": point[
                            "intermediate_frequency_mode"
                        ]["tracking"]["status"],
                        "wide_mode_real_per_s": point[
                            "wide_frequency_mode"
                        ]["pole"]["real_per_s"],
                        "wide_mode_frequency_hz": point[
                            "wide_frequency_mode"
                        ]["pole"]["frequency_hz"],
                        "wide_mode_tracking_status": point[
                            "wide_frequency_mode"
                        ]["tracking"]["status"],
                    }
                )
    if payload["status"] != "passed":
        raise RuntimeError("external-line dynamics audit failed")
    return json_path, csv_path


def main() -> None:
    output_dir = PROJECT_ROOT / "results" / "average-dq-external-line"
    json_path, csv_path = run_experiment(output_dir)
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
