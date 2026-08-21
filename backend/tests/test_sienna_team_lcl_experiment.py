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
    / "run_sienna_team_common_lcl_audit.py"
)


def _load_entrypoint():
    specification = importlib.util.spec_from_file_location(
        "sienna_team_common_lcl_experiment", ENTRYPOINT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"无法载入实验入口：{ENTRYPOINT}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class SiennaTeamCommonLCLExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_entrypoint()
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.output_path = cls.module.run_experiment(
            Path(cls.temporary_directory.name)
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_fixed_artifact_preserves_equivalence_and_counterexample(self) -> None:
        self.assertEqual(self.output_path.name, "common_lcl_isomorphism.json")
        payload = json.loads(
            self.output_path.read_text(encoding="utf-8"),
            parse_constant=lambda value: self.fail(f"非法 JSON 数值：{value}"),
        )
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["common_layer"]["state_count"], 6)
        self.assertLess(
            payload["results"]["state_matrix_max_abs_difference_per_s"],
            1.0e-10,
        )
        self.assertGreater(
            payload["results"]["counterfactual"][
                "state_matrix_max_abs_difference_per_s"
            ],
            1.0,
        )

    def test_artifact_stops_at_pcc_and_does_not_claim_full_model_equivalence(self) -> None:
        payload = json.loads(self.output_path.read_text(encoding="utf-8"))
        self.assertFalse(
            payload["network_interface"]["included_in_common_lcl_gate"]
        )
        self.assertFalse(payload["scope"]["full_state_dimensions_equal"])
        self.assertFalse(payload["scope"]["outer_controls_compared"])
        self.assertFalse(
            payload["scope"]["full_model_eigenvalues_comparable_from_this_gate"]
        )


if __name__ == "__main__":
    unittest.main()
