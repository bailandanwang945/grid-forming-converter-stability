from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.mathworks_team_comparison import (  # noqa: E402
    evaluate_mathworks_team_comparison,
)


OUTPUT_ROOT = PROJECT_ROOT / "results" / "mathworks-team-comparison"
JSON_PATH = OUTPUT_ROOT / "mathworks_team_aligned_comparison.json"
CSV_PATH = OUTPUT_ROOT / "mathworks_team_aligned_points.csv"


def main() -> None:
    result = evaluate_mathworks_team_comparison()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    fieldnames = [
        "scr",
        "x_by_r",
        "source_resistance_pu",
        "source_reactance_pu",
        "damping_mathworks_pu_per_hz",
        "damping_team_native_pu_per_pu_frequency",
        "external_vendor_outcome",
        "team_pre_step_stability",
        "team_post_step_stability",
        "classification_agreement",
        "team_pre_step_dominant_real_per_s",
        "team_pre_step_frequency_hz",
        "team_post_step_dominant_real_per_s",
        "team_post_step_frequency_hz",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for point in result["points"]:
            writer.writerow(
                {
                    "scr": point["scr"],
                    "x_by_r": point["x_by_r"],
                    "source_resistance_pu": point["source_resistance_pu"],
                    "source_reactance_pu": point["source_reactance_pu"],
                    "damping_mathworks_pu_per_hz": point[
                        "damping_mathworks_pu_per_hz"
                    ],
                    "damping_team_native_pu_per_pu_frequency": point[
                        "damping_team_native_pu_per_pu_frequency"
                    ],
                    "external_vendor_outcome": point["external_vendor_outcome"],
                    "team_pre_step_stability": point["team_pre_step_stability"],
                    "team_post_step_stability": point["team_post_step_stability"],
                    "classification_agreement": point["classification_agreement"],
                    "team_pre_step_dominant_real_per_s": point[
                        "team_pre_step_dominant_mode"
                    ]["real_per_s"],
                    "team_pre_step_frequency_hz": point[
                        "team_pre_step_dominant_mode"
                    ]["oscillation_frequency_hz"],
                    "team_post_step_dominant_real_per_s": point[
                        "team_post_step_dominant_mode"
                    ]["real_per_s"],
                    "team_post_step_frequency_hz": point[
                        "team_post_step_dominant_mode"
                    ]["oscillation_frequency_hz"],
                }
            )
    print("MATHWORKS_TEAM_CROSS_MODEL_COMPARISON_OK")
    print(JSON_PATH)
    print(CSV_PATH)


if __name__ == "__main__":
    main()
