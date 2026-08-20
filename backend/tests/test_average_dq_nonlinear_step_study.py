from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.average_dq_nonlinear_step_study import (
    AverageDQNonlinearStepEvidenceError,
    load_frozen_aligned_nonlinear_step_evidence,
    run_aligned_three_point_nonlinear_step_study,
)


class AverageDQNonlinearStepStudyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_aligned_three_point_nonlinear_step_study()
        cls.points = {
            point["damping_mathworks_pu_per_hz"]: point
            for point in cls.result["points"]
        }
        cls.client = TestClient(app)

    def test_contract_freezes_three_aligned_coordinates_and_two_solvers(self) -> None:
        contract = self.result["contract"]
        self.assertEqual(contract["scr"], 5.0)
        self.assertEqual(contract["damping_mathworks_pu_per_hz"], [0.6, 1.056, 2.0])
        self.assertEqual(contract["active_power_step_pu"], [0.6, 0.8])
        self.assertEqual(contract["solver_methods"], ["Radau", "LSODA"])
        self.assertEqual(contract["duration_s"], 8.0)
        self.assertTrue(contract["deterministic"])

    def test_three_points_separate_diagnostic_exit_and_convergence(self) -> None:
        self.assertEqual(
            self.points[0.6]["study_outcome"],
            "departed_declared_diagnostic_range",
        )
        self.assertEqual(
            self.points[1.056]["study_outcome"],
            "converged_within_horizon",
        )
        self.assertEqual(
            self.points[2.0]["study_outcome"],
            "converged_within_horizon",
        )
        self.assertEqual(self.result["summary"]["solver_agreement_count"], 3)
        self.assertEqual(
            self.result["summary"]["disagreement_coordinate_outcome"],
            "converged_within_horizon",
        )

    def test_radau_and_lsoda_meet_disclosed_consistency_gates(self) -> None:
        limits = self.result["contract"]["cross_solver_consistency_limits"]
        for point in self.result["points"]:
            consistency = point["solver_consistency"]
            self.assertTrue(point["solver_agreement"])
            self.assertTrue(consistency["same_sampled_state_shape"])
            self.assertTrue(consistency["passed"])
            self.assertLessEqual(
                consistency["maximum_sampled_state_absolute_difference"],
                limits["maximum_sampled_state_absolute_difference"],
            )
            self.assertLessEqual(
                consistency["maximum_frequency_deviation_difference_hz"],
                limits["maximum_frequency_deviation_difference_hz"],
            )
            self.assertLessEqual(
                consistency["event_time_difference_s"],
                limits["maximum_event_time_difference_s"],
            )

    def test_mismatch_point_converges_without_becoming_external_validation(self) -> None:
        mismatch = self.points[1.056]
        self.assertEqual(mismatch["external_vendor_outcome"], "Unstable")
        self.assertEqual(mismatch["team_pre_step_local_stability"], "stable")
        self.assertEqual(mismatch["team_post_step_local_stability"], "stable")
        for solver in mismatch["solver_results"]:
            self.assertIsNone(solver["event_name"])
            self.assertEqual(solver["completed_time_s"], 8.0)
            self.assertLess(solver["maximum_frequency_deviation_hz"], 0.16)
            self.assertEqual(solver["active_power_settling_time_s"], 1.82)
            self.assertEqual(solver["frequency_settling_time_s"], 2.11)
            self.assertLess(
                abs(solver["final_metrics"]["active_power_error_pu"]),
                1.0e-6,
            )
        scope = self.result["scope"]
        self.assertFalse(scope["same_full_model_as_mathworks"])
        self.assertFalse(scope["emt_validation"])
        self.assertFalse(scope["hardware_validation"])
        self.assertFalse(scope["diagnostic_exit_is_physical_instability"])

    def test_frozen_json_and_csv_preserve_complete_evidence(self) -> None:
        root = Path(__file__).resolve().parents[2]
        result_root = root / "results" / "average-dq-nonlinear-step"
        json_path = result_root / "aligned_three_point_nonlinear_step.json"
        csv_path = result_root / "aligned_three_point_nonlinear_step_solver_summary.csv"
        self.assertEqual(
            hashlib.sha256(json_path.read_bytes()).hexdigest(),
            "b40b54b15cf3e6d7f32f2531bb1b7f3810867ed439130b6d174b545503736999",
        )
        self.assertEqual(
            hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            "896dcc6d781dbed2e3482d0f727e0b70de2feabb0574afbcf7c199ba5072d1e3",
        )
        frozen = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(frozen["summary"]["solver_agreement_count"], 3)
        self.assertEqual(
            frozen["summary"]["disagreement_coordinate_outcome"],
            "converged_within_horizon",
        )
        with csv_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 6)
        self.assertEqual({row["solver_method"] for row in rows}, {"Radau", "LSODA"})

    def test_api_loads_hash_verified_trace_and_rejects_tampering(self) -> None:
        response = self.client.get("/api/evidence/average-dq-aligned-nonlinear-step")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["solver_agreement_count"], 3)
        self.assertEqual(len(payload["points"]), 3)
        self.assertEqual(len(payload["points"][1]["solver_results"][0]["states"]), 801)

        root = Path(__file__).resolve().parents[2]
        source = (
            root
            / "results"
            / "average-dq-nonlinear-step"
            / "aligned_three_point_nonlinear_step.json"
        )
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / source.name
            changed.write_bytes(source.read_bytes() + b" ")
            with self.assertRaises(AverageDQNonlinearStepEvidenceError):
                load_frozen_aligned_nonlinear_step_evidence(Path(directory))


if __name__ == "__main__":
    unittest.main()
