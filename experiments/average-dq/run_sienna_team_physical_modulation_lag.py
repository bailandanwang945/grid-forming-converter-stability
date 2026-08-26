"""Write the fixed physical-frame modulation-lag comparison evidence."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_team_physical_modulation_lag import (  # noqa: E402
    run_physical_modulation_frame_audit,
)


def run_experiment(output_dir: Path) -> tuple[Path, Path]:
    payload = run_physical_modulation_frame_audit()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "physical_modulation_lag.json"
    csv_path = output_dir / "physical_modulation_lag_points.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "modulation_time_constant_s",
                "spectral_abscissa_per_s",
                "stable_by_eigenvalues",
                "equilibrium_residual_inf",
                "off_equilibrium_rhs_difference_inf",
                "state_matrix_max_abs_difference_per_s",
                "local_dq_vs_physical_matrix_difference_per_s",
            ),
        )
        writer.writeheader()
        writer.writerows(payload["points"])
    if payload["status"] != "passed":
        raise RuntimeError("physical modulation-frame audit failed")
    return json_path, csv_path


def main() -> None:
    output_dir = PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    json_path, csv_path = run_experiment(output_dir)
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
