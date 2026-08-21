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
    / "run_sienna_team_common_inner_loop.py"
)


class SiennaTeamCommonInnerLoopExperimentTest(unittest.TestCase):
    def test_fixed_artifact_preserves_both_paths_and_scope(self) -> None:
        specification = importlib.util.spec_from_file_location(
            "sienna_team_common_inner_loop_experiment", ENTRYPOINT
        )
        if specification is None or specification.loader is None:
            self.fail(f"无法载入实验入口：{ENTRYPOINT}")
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output_path = module.run_experiment(Path(directory))
            self.assertEqual(output_path.name, "common_inner_loop_variants.json")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(len(payload["variants"]), 2)
        self.assertTrue(payload["counterfactual"]["gate_rejected_mismatch"])
        self.assertFalse(
            payload["structural_choice_sensitivity"][
                "stability_classification_changed"
            ]
        )
        self.assertFalse(payload["scope"]["source_baselines_modified"])
        self.assertFalse(payload["scope"]["outer_controls_compared"])


if __name__ == "__main__":
    unittest.main()
