from __future__ import annotations

import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = PROJECT_ROOT / "results" / "fig8-sensitivity"


class Fig8SensitivityExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [
                sys.executable,
                "experiments/baseline/run_fig8_sampled_sensitivity.py",
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.payload = json.loads(
            (RESULT_ROOT / "sampled_sensitivity_results.json").read_text(
                encoding="utf-8"
            )
        )
        with (
            RESULT_ROOT / "sampled_sensitivity_rows.csv"
        ).open(encoding="utf-8", newline="") as stream:
            cls.rows = list(csv.DictReader(stream))

    def test_artifacts_have_fixed_names_and_complete_rows(self) -> None:
        self.assertEqual(len(self.rows), 34)
        self.assertEqual(
            {(row["case_id"], row["study"]) for row in self.rows},
            {
                (case_id, study)
                for case_id in ("fig8_D_0p05", "fig8_D_0p5")
                for study in (
                    "frequency_density",
                    "decision_tolerance",
                    "common_matrix_scale",
                )
            },
        )

    def test_json_preserves_counterexample_and_claim_boundaries(self) -> None:
        unstable = next(
            case
            for case in self.payload["cases"]
            if case["case_id"] == "fig8_D_0p05"
        )
        nine_points = next(
            row
            for row in unstable["frequency_density"]
            if row["requested_point_count"] == 9
        )
        self.assertFalse(nine_points["detects_uncovered_region"])
        self.assertEqual(nine_points["unobserved_full_grid_uncovered_points"], 75)
        scope = self.payload["model_scope"]
        self.assertFalse(scope["continuous_frequency_coverage_proved"])
        self.assertFalse(scope["paper_theorem_evaluated"])
        self.assertIn("不生成新的频率响应", scope["statement"])


if __name__ == "__main__":
    unittest.main()
