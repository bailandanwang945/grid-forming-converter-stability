"""Write the fixed exact-delay, first-order-lag, and Padé evidence."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.delay_approximation_audit import (  # noqa: E402
    run_delay_approximation_audit,
)


def run_experiment(output_dir: Path) -> tuple[Path, Path]:
    payload = run_delay_approximation_audit()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "delay_approximation_audit.json"
    csv_path = output_dir / "delay_approximation_named_points.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fieldnames = [
            "mode",
            "frequency_hz",
            "dimensionless_omega_delay",
            "realization",
            "magnitude",
            "phase_deg",
            "magnitude_error",
            "phase_error_deg_against_exact",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for mode, point in payload["named_frequency_comparison"].items():
            realizations = {
                "exact_transport_delay": point["exact_transport_delay"],
                "local_dq_first_order_lag": point[
                    "local_dq_first_order_lag"
                ],
                **{
                    f"pade_order_{order}": response
                    for order, response in point["pade"].items()
                },
            }
            for realization, response in realizations.items():
                writer.writerow(
                    {
                        "mode": mode,
                        "frequency_hz": point["frequency_hz"],
                        "dimensionless_omega_delay": point[
                            "dimensionless_omega_delay"
                        ],
                        "realization": realization,
                        **response,
                    }
                )
    if payload["status"] != "passed":
        raise RuntimeError("delay approximation audit failed")
    return json_path, csv_path


def main() -> None:
    output_dir = PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    json_path, csv_path = run_experiment(output_dir)
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
