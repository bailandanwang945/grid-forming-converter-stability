from __future__ import annotations

import unittest

import numpy as np
from numpy.testing import assert_allclose

from backend.core.average_dq_external_line_dynamics import (
    ExternalLineDynamicsError,
    close_port_model_with_line_dynamics_fraction,
    run_external_line_dynamics_audit,
)
from backend.core.average_dq_model import (
    build_average_dq_model,
    close_port_model_with_external_line,
)
from backend.core.average_dq_presets import build_average_dq_verification_case


class AverageDQExternalLineDynamicsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = run_external_line_dynamics_audit()

    def test_dynamic_endpoint_reassembles_direct_model(self) -> None:
        self.assertEqual(self.audit["status"], "passed")
        self.assertTrue(
            self.audit["hypothesis_tests"]["h1_dynamic_reassembly_passed"]
        )
        self.assertLess(
            self.audit[
                "dynamic_reassembly_observed_max_abs_difference_per_s"
            ],
            2.0e-7,
        )

    def test_static_endpoint_matches_direct_algebraic_feedback(self) -> None:
        topology, parameters = build_average_dq_verification_case()
        model = build_average_dq_model(topology, parameters)
        calculated = close_port_model_with_line_dynamics_fraction(
            model.linearization,
            model.line,
            model.topology.base_values.frequency_hz,
            0.0,
        )
        impedance = (
            model.line.resistance_pu * np.eye(2)
            + model.line.reactance_pu
            * np.array([[0.0, -1.0], [1.0, 0.0]])
        )
        expected = (
            model.linearization.device_state_matrix
            - model.linearization.port_voltage_matrix
            @ impedance
            @ model.linearization.port_current_state_matrix
        )
        assert_allclose(calculated, expected, atol=2.0e-12)

    def test_complete_endpoint_matches_existing_independent_closure(self) -> None:
        topology, parameters = build_average_dq_verification_case()
        model = build_average_dq_model(topology, parameters)
        calculated = close_port_model_with_line_dynamics_fraction(
            model.linearization,
            model.line,
            model.topology.base_values.frequency_hz,
            1.0,
        )
        expected = close_port_model_with_external_line(
            model.linearization,
            model.line,
            model.topology.base_values.frequency_hz,
        )
        assert_allclose(calculated, expected, atol=2.0e-12)

    def test_modes_are_not_force_matched(self) -> None:
        for case in self.audit["cases"]:
            for point in case["points"]:
                for mode in (
                    "low_frequency_mode",
                    "intermediate_frequency_mode",
                    "wide_frequency_mode",
                ):
                    self.assertIn(
                        point[mode]["tracking"]["status"],
                        {"anchor", "matched", "pending"},
                    )
        self.assertFalse(self.audit["scope"]["general_hopf_margin_claimed"])
        self.assertFalse(
            self.audit["scope"]["sienna_or_chatterjee_geng_case_reproduced"]
        )
        self.assertTrue(
            self.audit["scope"]["all_low_frequency_modes_resolved"]
        )
        self.assertFalse(
            self.audit["scope"]["all_wide_frequency_modes_resolved"]
        )
        self.assertTrue(
            self.audit["scope"]["all_intermediate_frequency_modes_resolved"]
        )
        self.assertTrue(
            self.audit["scope"][
                "intermediate_frequency_branch_is_posthoc_diagnostic"
            ]
        )

    def test_preregistered_direction_and_monotonicity_are_separate(self) -> None:
        hypotheses = self.audit["hypothesis_tests"]
        self.assertEqual(
            hypotheses["h2_baseline_dynamic_low_mode_moves_right"]["result"],
            "supported-in-bounded-study",
        )
        self.assertEqual(
            hypotheses[
                "h3_low_mode_shift_magnitude_increases_with_reactance"
            ]["result"],
            "not-supported-in-bounded-study",
        )

    def test_invalid_fraction_is_rejected(self) -> None:
        topology, parameters = build_average_dq_verification_case()
        model = build_average_dq_model(topology, parameters)
        for fraction in (-0.1, 1.1, float("inf")):
            with self.subTest(fraction=fraction), self.assertRaises(
                ExternalLineDynamicsError
            ):
                close_port_model_with_line_dynamics_fraction(
                    model.linearization,
                    model.line,
                    model.topology.base_values.frequency_hz,
                    fraction,
                )


if __name__ == "__main__":
    unittest.main()
