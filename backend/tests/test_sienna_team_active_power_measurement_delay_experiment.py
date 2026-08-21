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
    / "run_sienna_team_active_power_measurement_delay.py"
)


class SiennaTeamActivePowerMeasurementDelayExperimentTest(unittest.TestCase):
    def test_entrypoint_writes_traceable_json_and_csv(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "sienna_team_active_power_measurement_delay_experiment", ENTRYPOINT
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            json_path, csv_path = module.run_experiment(Path(directory))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(json_path.name, "common_active_power_measurement_delay.json")
            self.assertEqual(
                csv_path.name, "common_active_power_measurement_delay_points.csv"
            )
            self.assertEqual(len(csv_path.read_text(encoding="utf-8-sig").splitlines()), 11)


if __name__ == "__main__":
    unittest.main()
