"""Write the fixed Sienna/team common PLL measurement-position evidence."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.sienna_team_common_pll_measurement import (  # noqa: E402
    run_common_pll_measurement_audit,
)


OUTPUT = ROOT / "results" / "sienna-team-isomorphism"


def main() -> None:
    payload = run_common_pll_measurement_audit()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT / "common_pll_measurement_position.json"
    csv_path = OUTPUT / "common_pll_measurement_position_cases.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "case_id",
                "pll_voltage_port",
                "damping_gain",
                "spectral_abscissa_per_s",
                "stable_by_eigenvalues",
                "low_real_per_s",
                "low_frequency_hz",
                "low_tracking_status",
                "wide_real_per_s",
                "wide_frequency_hz",
                "wide_tracking_status",
                "continuation_status",
            )
        )
        for case_id, case in payload["cases"].items():
            writer.writerow(
                (
                    case_id,
                    case["pll_voltage_port"],
                    case["damping_gain"],
                    case["spectral_abscissa_per_s"],
                    case["stable_by_eigenvalues"],
                    case["low_frequency_mode"]["pole"]["real_per_s"],
                    case["low_frequency_mode"]["pole"]["frequency_hz"],
                    case["low_frequency_mode"]["tracking"]["status"],
                    case["wide_frequency_mode"]["pole"]["real_per_s"],
                    case["wide_frequency_mode"]["pole"]["frequency_hz"],
                    case["wide_frequency_mode"]["tracking"]["status"],
                    case.get("continuation", {}).get("status", "not-applicable"),
                )
            )
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
