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
    / "run_sienna_team_common_active_damping.py"
)


class SiennaTeamCommonActiveDampingExperimentTest(unittest.TestCase):
    def test_artifact_preserves_negative_hypothesis_result_and_scope(self) -> None:
        specification = importlib.util.spec_from_file_location(
            "sienna_team_common_active_damping_experiment", ENTRYPOINT
        )
        if specification is None or specification.loader is None:
            self.fail(f"无法载入实验入口：{ENTRYPOINT}")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output_path = module.run_experiment(Path(directory))
            self.assertEqual(
                output_path.name, "common_active_damping_comparison.json"
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "passed")
        self.assertTrue(payload["counterfactual"]["gate_rejected_mismatch"])
        self.assertFalse(
            payload["hypothesis_test"]["supported_for_both_structural_paths"]
        )
        self.assertFalse(payload["scope"]["source_baselines_modified"])
        self.assertFalse(payload["scope"]["team_original_model_modified"])


if __name__ == "__main__":
    unittest.main()
