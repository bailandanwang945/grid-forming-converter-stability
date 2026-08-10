from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = PROJECT_ROOT / "experiments" / "average-dq" / "run_modal_ablation.py"


def _load_entrypoint():
    specification = importlib.util.spec_from_file_location(
        "average_dq_modal_ablation_experiment", ENTRYPOINT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"无法载入实验入口：{ENTRYPOINT}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class AverageDQAblationExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_entrypoint()
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temporary_directory.name)
        cls.json_path, cls.csv_path = cls.module.run_experiment(cls.output_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_fixed_filenames_and_expected_counts(self) -> None:
        self.assertEqual(self.json_path.name, "modal_ablation_results.json")
        self.assertEqual(self.csv_path.name, "modal_ablation_points.csv")
        payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["summary"]["point_count"], 19)
        self.assertEqual(payload["summary"]["stability_counts"]["stable"], 5)
        self.assertEqual(payload["summary"]["stability_counts"]["unstable"], 14)
        self.assertEqual(len(payload["points"]), 19)
        self.assertEqual(payload["fixed_anchor"]["damping_coefficient_pu"], 60.0)
        self.assertEqual(payload["fixed_anchor"]["external_line_reactance_pu"], 0.1)

    def test_json_rejects_non_finite_constants_and_keeps_evidence(self) -> None:
        payload = json.loads(
            self.json_path.read_text(encoding="utf-8"),
            parse_constant=lambda value: self.fail(f"非法 JSON 数值：{value}"),
        )
        baseline = payload["points"][0]
        self.assertIn("rightmost_pole", baseline)
        self.assertIn("thresholds", baseline["extra_mode"])
        self.assertIn("thresholds", baseline["synchronous_mode"])
        self.assertIn("extra_group_participation", baseline)
        self.assertIn("residuals", baseline)
        self.assertTrue(payload["model_scope"]["tracking_boundary"])

    def test_csv_has_one_row_per_scenario(self) -> None:
        with self.csv_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 19)
        self.assertEqual(len({row["scenario_id"] for row in rows}), 19)
        self.assertTrue(all(row["damping_coefficient_pu"] == "60.0" for row in rows))
        self.assertTrue(all(row["line_reactance_pu"] == "0.1" for row in rows))


if __name__ == "__main__":
    unittest.main()
