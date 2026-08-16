"""Generate the fixed sampled Fig. 8 sensitivity evidence."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.fig8_sensitivity import evaluate_fig8_sensitivity  # noqa: E402


OUTPUT_ROOT = PROJECT_ROOT / "results" / "fig8-sensitivity"
JSON_PATH = OUTPUT_ROOT / "sampled_sensitivity_results.json"
CSV_PATH = OUTPUT_ROOT / "sampled_sensitivity_rows.csv"


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _csv_rows(study: dict) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in study["cases"]:
        for name, setting_name in (
            ("frequency_density", "requested_point_count"),
            ("decision_tolerance", "gain_relative_tolerance"),
            (
                "common_matrix_scale",
                "common_post_transformation_matrix_scale",
            ),
        ):
            for result in case[name]:
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "damping_D": case["damping"],
                        "closed_loop_reference": case[
                            "closed_loop_reference"
                        ],
                        "study": name,
                        "setting": result[setting_name],
                        "sample_count": result["sample_count"],
                        "uncovered_count": result["uncovered_count"],
                        "indeterminate_coverage_count": result[
                            "indeterminate_coverage_count"
                        ],
                        "first_uncovered_frequency_Hz": result[
                            "first_uncovered_frequency_hz"
                        ],
                        "last_uncovered_frequency_Hz": result[
                            "last_uncovered_frequency_hz"
                        ],
                        "coverage_mismatch_count": result.get(
                            "coverage_mismatch_from_default",
                            result.get(
                                "coverage_mismatch_from_unit_scale", ""
                            ),
                        ),
                        "detects_uncovered_region": result.get(
                            "detects_uncovered_region", ""
                        ),
                        "unobserved_full_grid_uncovered_points": result.get(
                            "unobserved_full_grid_uncovered_points", ""
                        ),
                    }
                )
    return rows


def main() -> int:
    study = evaluate_fig8_sensitivity()
    artifact = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "entrypoint": "experiments/baseline/run_fig8_sampled_sensitivity.py",
        **study,
    }
    _atomic_text(
        JSON_PATH,
        json.dumps(
            artifact,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )

    rows = _csv_rows(study)
    fieldnames = list(rows[0])
    temporary = CSV_PATH.with_suffix(CSV_PATH.suffix + ".tmp")
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(CSV_PATH)
    print(
        "FIG8_SAMPLED_SENSITIVITY_OK "
        f"cases={len(study['cases'])} rows={len(rows)} "
        f"json={JSON_PATH} csv={CSV_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
