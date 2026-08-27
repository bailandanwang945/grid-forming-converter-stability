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
    / "run_sienna_team_common_static_network.py"
)


class SiennaTeamCommonStaticNetworkExperimentTest(unittest.TestCase):
    def test_experiment_preserves_two_loaded_intermediate_cases(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "common_static_network_experiment", ENTRYPOINT
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output_path = module.run_experiment(Path(directory))
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(
                set(payload["variants"]), {"filter_capacitor", "pcc"}
            )
            self.assertFalse(
                payload["scope"]["original_full_model_eigenvalues_comparable"]
            )


if __name__ == "__main__":
    unittest.main()
