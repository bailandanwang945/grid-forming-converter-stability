from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = (
    PROJECT_ROOT
    / "experiments"
    / "average-dq"
    / "run_common_inner_loop_modal_fingerprint.py"
)


def _load_entrypoint():
    specification = importlib.util.spec_from_file_location(
        "common_inner_loop_modal_fingerprint_experiment", ENTRYPOINT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"无法载入实验入口：{ENTRYPOINT}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class SiennaTeamInnerLoopModalFingerprintExperimentTest(unittest.TestCase):
    def test_experiment_writes_traceable_json_and_52_row_csv(self) -> None:
        module = _load_entrypoint()
        with tempfile.TemporaryDirectory() as temporary:
            json_path, csv_path = module.run_experiment(Path(temporary))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(len(rows), 52)
        self.assertEqual(
            sum(row["factor_name"] == "baseline" for row in rows), 4
        )
        self.assertTrue(all(row["tracking_status"] == "matched" for row in rows))
        self.assertIn("grid_side_filter_current_participation", rows[0])


if __name__ == "__main__":
    unittest.main()
