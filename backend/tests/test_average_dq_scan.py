from __future__ import annotations

import unittest

import numpy as np

from backend.core.average_dq_model import (
    build_average_dq_model,
    close_port_model_with_external_line,
)
from backend.core.average_dq_presets import build_average_dq_verification_case
from backend.core.average_dq_scan import (
    AverageDQScanError,
    scan_average_dq_damping_reactance,
)


class AverageDQScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.topology, self.parameters = build_average_dq_verification_case()

    def test_scan_exposes_full_reduced_agreement_and_strong_grid_disagreement(self):
        scan = scan_average_dq_damping_reactance(
            self.topology,
            self.parameters,
            damping_values_pu=[20.0, 40.0, 60.0],
            reactance_values_pu=[0.1, 0.3, 0.8],
        )

        self.assertEqual(scan.point_count, 9)
        self.assertEqual(
            scan.counts,
            {
                "valid": 9,
                "invalid": 0,
                "agreement": 8,
                "disagreement": 1,
                "full": {"stable": 5, "marginal": 0, "unstable": 4},
                "reduced": {"stable": 6, "marginal": 0, "unstable": 3},
            },
        )
        disagreement = scan.rows[2][0]
        self.assertEqual(disagreement.full_stability, "unstable")
        self.assertEqual(disagreement.reduced_stability, "stable")
        self.assertFalse(disagreement.stability_agreement)
        self.assertAlmostEqual(disagreement.full_dominant_real_per_s, 4.5864, places=3)
        self.assertAlmostEqual(disagreement.full_oscillation_frequency_hz, 5.719, places=3)
        self.assertAlmostEqual(disagreement.matched_full_mode_real_per_s, -1.140, places=3)
        self.assertAlmostEqual(disagreement.matched_full_mode_frequency_hz, 2.371, places=3)
        self.assertAlmostEqual(disagreement.reduced_dominant_real_per_s, -1.231, places=3)
        self.assertAlmostEqual(disagreement.reduced_oscillation_frequency_hz, 2.285, places=3)
        self.assertLess(disagreement.frequency_relative_error, 0.05)
        leading_states = {
            state for state, _ in disagreement.full_dominant_participation[:4]
        }
        self.assertIn("converter_current_d_pu", leading_states)
        self.assertIn("converter_current_q_pu", leading_states)

    def test_real_dominant_full_mode_keeps_stability_classification(self):
        scan = scan_average_dq_damping_reactance(
            self.topology,
            self.parameters,
            damping_values_pu=[500.0],
            reactance_values_pu=[0.3],
        )

        point = scan.rows[0][0]
        self.assertTrue(point.valid)
        self.assertEqual(point.full_stability, "stable")
        self.assertAlmostEqual(point.full_dominant_real_per_s, -1.932, places=3)
        self.assertAlmostEqual(point.full_oscillation_frequency_hz, 0.0, places=9)
        self.assertIsNotNone(point.matched_full_mode_frequency_hz)

    def test_scan_does_not_mutate_input_models(self):
        topology_before = self.topology.model_dump(mode="json")
        parameters_before = self.parameters.model_dump(mode="json")

        scan_average_dq_damping_reactance(
            self.topology,
            self.parameters,
            damping_values_pu=[20.0, 60.0],
            reactance_values_pu=[0.1, 0.8],
        )

        self.assertEqual(self.topology.model_dump(mode="json"), topology_before)
        self.assertEqual(self.parameters.model_dump(mode="json"), parameters_before)

    def test_axes_and_grid_size_are_bounded(self):
        with self.assertRaisesRegex(AverageDQScanError, "严格递增"):
            scan_average_dq_damping_reactance(
                self.topology,
                self.parameters,
                damping_values_pu=[20.0, 20.0],
                reactance_values_pu=[0.3],
            )
        with self.assertRaisesRegex(AverageDQScanError, "超过上限"):
            scan_average_dq_damping_reactance(
                self.topology,
                self.parameters,
                damping_values_pu=[20.0, 40.0, 60.0],
                reactance_values_pu=[0.1, 0.3, 0.8],
                maximum_points=8,
            )

    def test_disagreement_anchor_is_not_a_finite_difference_artifact(self):
        self.topology.grid_forming_converters[0].damping_coefficient_pu = 60.0
        self.topology.lines[0].reactance_pu = 0.1
        models = [
            build_average_dq_model(
                self.topology,
                self.parameters,
                relative_step=step,
            )
            for step in (1.0e-4, 5.0e-5, 2.5e-5)
        ]
        dominant = [
            max(model.poles_per_s, key=lambda pole: (pole.real, pole.imag))
            for model in models
        ]

        self.assertTrue(all(model.stability.value == "unstable" for model in models))
        self.assertLess(max(abs(pole - dominant[0]) for pole in dominant[1:]), 1.0e-6)
        model = models[-1]
        reconstructed = close_port_model_with_external_line(
            model.linearization,
            model.line,
            model.topology.base_values.frequency_hz,
        )
        self.assertLess(
            float(
                np.max(
                    np.abs(
                        reconstructed - model.linearization.closed_state_matrix
                    )
                )
            ),
            1.0e-6,
        )
        self.assertLess(model.operating_point.closed_rhs_residual_inf, 1.0e-9)


if __name__ == "__main__":
    unittest.main()
