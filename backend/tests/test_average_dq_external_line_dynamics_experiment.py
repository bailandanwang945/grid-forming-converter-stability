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
    / "run_external_line_dynamics_audit.py"
)


class AverageDQExternalLineDynamicsExperimentTest(unittest.TestCase):
    def test_experiment_writes_fixed_json_and_twenty_five_rows(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "external_line_dynamics_experiment", ENTRYPOINT
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            json_path, csv_path = module.run_experiment(Path(directory))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(len(payload["cases"]), 5)
            self.assertEqual(
                len(csv_path.read_text(encoding="utf-8-sig").splitlines()),
                26,
            )


if __name__ == "__main__":
    unittest.main()
