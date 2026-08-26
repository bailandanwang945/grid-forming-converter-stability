"""Write the fixed Sienna/team local-dq first-order modulation evidence."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_team_common_modulation_delay import (  # noqa: E402
    run_common_modulation_delay_audit,
)


def run_experiment(output_dir: Path) -> tuple[Path, Path]:
    payload = run_common_modulation_delay_audit()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "common_modulation_delay.json"
    csv_path = output_dir / "common_modulation_delay_points.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "modulation_time_constant_s",
                "dimensionless_ideal_wide_mode_delay",
                "spectral_abscissa_per_s",
                "stable_by_eigenvalues",
                "low_mode_real_per_s",
                "low_mode_frequency_hz",
                "low_mode_tracking_status",
                "wide_mode_real_per_s",
                "wide_mode_frequency_hz",
                "wide_mode_tracking_status",
                "off_equilibrium_rhs_difference_inf",
                "state_matrix_max_abs_difference_per_s",
            ),
        )
        writer.writeheader()
        for point in payload["points"]:
            writer.writerow(
                {
                    "modulation_time_constant_s": point[
                        "modulation_time_constant_s"
                    ],
                    "dimensionless_ideal_wide_mode_delay": point[
                        "dimensionless_ideal_wide_mode_delay"
                    ],
                    "spectral_abscissa_per_s": point[
                        "spectral_abscissa_per_s"
                    ],
                    "stable_by_eigenvalues": point["stable_by_eigenvalues"],
                    "low_mode_real_per_s": point["low_frequency_mode"][
                        "pole"
                    ]["real_per_s"],
                    "low_mode_frequency_hz": point["low_frequency_mode"][
                        "pole"
                    ]["frequency_hz"],
                    "low_mode_tracking_status": point[
                        "low_frequency_mode"
                    ]["tracking"]["status"],
                    "wide_mode_real_per_s": point["wide_frequency_mode"][
                        "pole"
                    ]["real_per_s"],
                    "wide_mode_frequency_hz": point["wide_frequency_mode"][
                        "pole"
                    ]["frequency_hz"],
                    "wide_mode_tracking_status": point[
                        "wide_frequency_mode"
                    ]["tracking"]["status"],
                    "off_equilibrium_rhs_difference_inf": point[
                        "off_equilibrium_rhs_difference_inf"
                    ],
                    "state_matrix_max_abs_difference_per_s": point[
                        "state_matrix_max_abs_difference_per_s"
                    ],
                }
            )
    if payload["status"] != "passed":
        raise RuntimeError("common first-order modulation audit failed")
    return json_path, csv_path


def main() -> None:
    output_dir = PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    json_path, csv_path = run_experiment(output_dir)
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
