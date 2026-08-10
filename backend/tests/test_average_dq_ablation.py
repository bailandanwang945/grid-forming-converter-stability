from __future__ import annotations

import unittest

import numpy as np

from backend.core.average_dq_ablation import (
    AverageDQAblationError,
    ModalSignature,
    match_mode,
    modal_signature,
    run_average_dq_anchor_ablation,
)
from backend.core.average_dq_presets import build_average_dq_verification_case


class AverageDQAblationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.topology, self.parameters = build_average_dq_verification_case()
        self.topology.lines[0].reactance_pu = 0.1
        self.topology.grid_forming_converters[0].damping_coefficient_pu = 60.0

    def run_study(self):
        return run_average_dq_anchor_ablation(self.topology, self.parameters)

    def test_fixed_anchor_and_nineteen_unique_points(self):
        study = self.run_study()

        self.assertEqual(study.point_count, 19)
        self.assertEqual(len({point.scenario_id for point in study.points}), 19)
        self.assertTrue(
            all(point.damping_coefficient_pu == 60.0 for point in study.points)
        )
        self.assertTrue(
            all(point.line_reactance_pu == 0.1 for point in study.points)
        )
        self.assertAlmostEqual(study.baseline_extra_mode_per_s.real, 4.5864, places=3)
        self.assertAlmostEqual(study.baseline_extra_mode_per_s.imag, 35.934, places=3)
        self.assertAlmostEqual(
            study.baseline_synchronous_mode_per_s.real, -1.140, places=3
        )
        self.assertAlmostEqual(
            study.baseline_synchronous_mode_per_s.imag, 14.898, places=3
        )

    def test_expected_screening_outcomes_and_evidence(self):
        study = self.run_study()
        points = {point.scenario_id: point for point in study.points}

        self.assertEqual(points["qv_droop__0"].stability, "unstable")
        self.assertEqual(points["voltage_pi__2"].stability, "stable")
        self.assertEqual(points["current_pi__2"].stability, "stable")
        self.assertTrue(
            all(point.extra_mode.status == "matched" for point in study.points)
        )
        self.assertTrue(
            all(
                point.synchronous_mode.status == "matched"
                for point in study.points
            )
        )
        self.assertGreater(points["voltage_pi__2"].extra_mode.path_steps, 1)
        self.assertLessEqual(
            points["voltage_pi__2"].extra_mode.normalized_distance,
            points[
                "voltage_pi__2"
            ].extra_mode.maximum_normalized_distance_threshold,
        )
        two_path = points[
            "voltage_pi__2p0__current_pi__2p0"
        ].extra_mode
        self.assertIn("|", two_path.path_label)
        self.assertGreater(two_path.path_steps, 2)
        baseline = points["baseline"]
        self.assertEqual(len(baseline.poles_per_s), 16)
        self.assertEqual(len(baseline.reduced_poles_per_s), 3)
        self.assertEqual(len(study.state_scaling), 16)
        self.assertTrue(all(scale == 1.0 for _, scale in study.state_scaling))
        self.assertEqual(baseline.extra_mode.status, "matched")
        self.assertEqual(baseline.synchronous_mode.status, "matched")
        self.assertAlmostEqual(
            sum(value for _, value in baseline.extra_group_participation),
            1.0,
            places=12,
        )
        self.assertTrue(np.isfinite(baseline.extra_mode_condition_number))
        self.assertLess(baseline.extra_right_eigenpair_residual, 1.0e-12)
        self.assertLess(baseline.extra_left_eigenpair_residual, 1.0e-12)
        self.assertLess(baseline.residuals.algebraic_inf, 1.0e-10)
        self.assertLess(baseline.residuals.closed_rhs_inf, 1.0e-9)
        self.assertLess(baseline.residuals.device_rhs_inf, 1.0e-9)
        self.assertLess(baseline.residuals.active_power_balance_abs_pu, 1.0e-8)

    def test_inputs_are_not_mutated_and_wrong_anchor_is_rejected(self):
        topology_before = self.topology.model_dump(mode="json")
        parameters_before = self.parameters.model_dump(mode="json")

        self.run_study()

        self.assertEqual(self.topology.model_dump(mode="json"), topology_before)
        self.assertEqual(self.parameters.model_dump(mode="json"), parameters_before)
        self.topology.lines[0].reactance_pu = 0.3
        with self.assertRaisesRegex(AverageDQAblationError, "X=0.1"):
            self.run_study()
        self.topology.lines[0].reactance_pu = 0.1
        with self.assertRaisesRegex(AverageDQAblationError, r"\[0,1\]"):
            run_average_dq_anchor_ablation(
                self.topology,
                self.parameters,
                minimum_confidence=1.1,
            )

    def test_mode_matching_uses_signatures_not_eigenvalue_array_positions(self):
        reference_matrix = np.diag([20.0, 1.0])
        reference = modal_signature(reference_matrix, 1.0)
        # The tracked pole is deliberately the second returned diagonal entry.
        candidate_matrix = np.diag([10.0, 1.05])

        match = match_mode(reference, candidate_matrix)

        self.assertAlmostEqual(match.eigenvalue_per_s.real, 1.05, places=12)
        self.assertNotAlmostEqual(match.eigenvalue_per_s.real, 10.0, places=6)
        self.assertEqual(match.status, "matched")

    def test_low_confidence_match_can_be_marked_pending(self):
        reference = modal_signature(np.diag([2.0, 1.0]), 1.0)

        match = match_mode(
            reference,
            np.diag([100.0, 200.0]),
            minimum_confidence=0.9,
        )

        self.assertEqual(match.status, "pending")
        self.assertIn("confidence-below-threshold", match.reason)

    def test_mac_is_invariant_to_eigenvector_phase_and_scale(self):
        reference = modal_signature(np.diag([2.0, 1.0]), 1.0)
        rescaled = ModalSignature(
            eigenvalue_per_s=reference.eigenvalue_per_s,
            right_vector=3.0j * reference.right_vector,
            left_vector=-0.25j * reference.left_vector,
            right_residual=reference.right_residual,
            left_residual=reference.left_residual,
            condition_number=reference.condition_number,
        )

        match = match_mode(rescaled, np.diag([2.0, 1.0]))

        self.assertAlmostEqual(match.eigenvalue_per_s.real, 1.0, places=12)
        self.assertAlmostEqual(match.right_mac, 1.0, places=12)
        self.assertAlmostEqual(match.left_mac, 1.0, places=12)
        self.assertEqual(match.status, "matched")


if __name__ == "__main__":
    unittest.main()
