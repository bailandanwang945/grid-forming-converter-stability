from __future__ import annotations

import csv
import json
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "sienna-team-isomorphism"


class SiennaTeamCommonPllMeasurementExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        runpy.run_path(
            str(
                ROOT
                / "experiments"
                / "average-dq"
                / "run_sienna_team_common_pll_measurement.py"
            ),
            run_name="__main__",
        )

    def test_json_preserves_pending_mode_without_failing_equation_gate(self) -> None:
        payload = json.loads(
            (RESULTS / "common_pll_measurement_position.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["status"], "passed")
        self.assertFalse(payload["hypothesis_tests"]["named_modes_resolved"])
        self.assertEqual(
            payload["cases"]["pcc__damping_on"]["continuation"]["status"],
            "pending",
        )

    def test_csv_has_one_row_per_preregistered_case(self) -> None:
        with (RESULTS / "common_pll_measurement_position_cases.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            {row["continuation_status"] for row in rows},
            {"not-applicable", "resolved", "pending"},
        )


if __name__ == "__main__":
    unittest.main()
