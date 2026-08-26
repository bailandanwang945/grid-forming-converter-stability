from __future__ import annotations

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
    / "run_sienna_team_physical_modulation_lag.py"
)


class SiennaTeamPhysicalModulationLagExperimentTest(unittest.TestCase):
    def test_experiment_writes_json_and_csv(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "sienna_team_physical_modulation_lag_experiment", ENTRYPOINT
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary_directory:
            json_path, csv_path = module.run_experiment(
                Path(temporary_directory)
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(len(payload["points"]), 6)
            self.assertTrue(csv_path.read_text(encoding="utf-8-sig").startswith(
                "modulation_time_constant_s,"
            ))


if __name__ == "__main__":
    unittest.main()
