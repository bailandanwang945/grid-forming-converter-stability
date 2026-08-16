from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = PROJECT_ROOT / "experiments" / "average-dq" / "run_modal_boundary.py"


def _load_entrypoint():
    specification = importlib.util.spec_from_file_location(
        "average_dq_modal_boundary_experiment", ENTRYPOINT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"无法载入实验入口：{ENTRYPOINT}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class AverageDQBoundaryExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_entrypoint()
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temporary_directory.name)
        cls.json_path, cls.csv_path = cls.module.run_experiment(cls.output_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_fixed_filenames_and_four_converged_boundaries(self) -> None:
        self.assertEqual(self.json_path.name, "modal_boundary_results.json")
        self.assertEqual(self.csv_path.name, "modal_boundary_trials.csv")
        payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        result = payload["result"]
        self.assertEqual(result["path_count"], 4)
        self.assertEqual(result["converged_extra_mode_boundaries"], 4)
        self.assertEqual(result["converged_overall_boundaries"], 4)
        self.assertEqual(result["agreeing_boundary_count"], 4)
        self.assertEqual(len(result["paths"]), 4)

    def test_json_keeps_numerical_contract_and_tracking_evidence(self) -> None:
        payload = json.loads(
            self.json_path.read_text(encoding="utf-8"),
            parse_constant=lambda value: self.fail(f"非法 JSON 数值：{value}"),
        )
        result = payload["result"]
        self.assertEqual(
            result["numerical_contract"]["factor_midpoint"],
            "geometric-log-scale",
        )
        self.assertEqual(
            result["numerical_contract"]["failed_tracking_policy"],
            "pending-not-forced",
        )
        first_trial = result["paths"][0]["trials"][0]
        self.assertIn("thresholds", first_trial["extra_mode"])
        self.assertIn("extra_mode_is_rightmost", first_trial)
        self.assertIn("不证明唯一因果", result["interpretation_boundary"])

    def test_csv_contains_every_calculated_trial_once_per_path_factor(self) -> None:
        payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        expected_count = sum(
            path["trial_count"] for path in payload["result"]["paths"]
        )
        with self.csv_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), expected_count)
        identities = {(row["path_id"], row["factor_value"]) for row in rows}
        self.assertEqual(len(identities), expected_count)
        self.assertTrue(all(row["calculation_status"] == "valid" for row in rows))


if __name__ == "__main__":
    unittest.main()
