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
    / "run_sienna_team_inner_control_mapping.py"
)


def _load_entrypoint():
    specification = importlib.util.spec_from_file_location(
        "sienna_team_inner_control_experiment", ENTRYPOINT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"无法载入实验入口：{ENTRYPOINT}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class SiennaTeamInnerControlExperimentTest(unittest.TestCase):
    def test_artifact_preserves_partial_match_and_structural_gap(self) -> None:
        module = _load_entrypoint()
        with tempfile.TemporaryDirectory() as directory:
            output_path = module.run_experiment(Path(directory))
            self.assertEqual(output_path.name, "inner_control_mapping.json")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["pi_state_mapping"]["status"], "passed")
        self.assertFalse(
            payload["compensation_mapping"]["parameter_only_isomorphic"]
        )
        self.assertAlmostEqual(
            payload["compensation_mapping"][
                "parameter_only_aligned_max_abs_difference"
            ],
            0.003,
            places=12,
        )
        self.assertTrue(
            payload["compensation_mapping"]["structural_counterfactual_passed"]
        )
        self.assertFalse(
            payload["scope"]["structural_counterfactual_is_source_test08"]
        )


if __name__ == "__main__":
    unittest.main()
