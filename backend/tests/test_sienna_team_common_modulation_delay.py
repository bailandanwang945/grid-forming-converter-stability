from __future__ import annotations

import unittest

import numpy as np

from backend.core.sienna_team_common_modulation_delay import (
    MODULATION_LEVELS_S,
    TEAM_DECLARED_MODULATION_TIME_CONSTANT_S,
    CommonModulationDelayError,
    run_common_modulation_delay_audit,
    solve_common_modulation_delay_equilibrium,
    source_common_modulation_delay_rhs_in_team_coordinates,
    team_common_modulation_delay_rhs,
)
from backend.core.sienna_team_common_outer_loop import (
    frozen_common_outer_loop_parameters,
)


class SiennaTeamCommonModulationDelayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parameters = frozen_common_outer_loop_parameters()
        cls.audit = run_common_modulation_delay_audit()

    def test_all_fixed_levels_pass_equation_and_structural_gates(self) -> None:
        self.assertEqual(self.audit["status"], "passed")
        self.assertEqual(
            self.audit["verification_summary"][
                "equation_and_counterexample_status"
            ],
            "passed",
        )
        self.assertEqual(
            self.audit["verification_summary"]["named_mode_tracking_status"],
            "resolved",
        )
        self.assertEqual(self.audit["model_contract"]["state_count"], 16)
        self.assertEqual(self.audit["model_contract"]["base_state_count"], 14)
        self.assertEqual(
            tuple(
                self.audit["model_contract"][
                    "modulation_time_constant_levels_s"
                ]
            ),
            MODULATION_LEVELS_S,
        )
        for point in self.audit["points"]:
            self.assertLess(point["equilibrium_residual_inf"], 1.0e-8)
            self.assertLess(
                point["off_equilibrium_rhs_difference_inf"], 1.0e-8
            )
            self.assertLess(
                point["state_matrix_max_abs_difference_per_s"], 1.0e-5
            )
            self.assertLess(
                point["modulation_self_block_max_abs_error_per_s"],
                1.0e-5,
            )
            self.assertLess(
                point[
                    "modulation_to_lcl_input_block_max_abs_error_per_s"
                ],
                1.0e-5,
            )

    def test_source_and_team_paths_match_away_from_equilibrium(self) -> None:
        equilibrium = solve_common_modulation_delay_equilibrium(
            self.parameters,
            modulation_time_constant_s=(
                TEAM_DECLARED_MODULATION_TIME_CONSTANT_S
            ),
        )
        probe = equilibrium + np.linspace(-3.0e-4, 3.0e-4, 16)
        team = team_common_modulation_delay_rhs(
            probe,
            (1.0, 0.0),
            self.parameters,
            modulation_time_constant_s=(
                TEAM_DECLARED_MODULATION_TIME_CONSTANT_S
            ),
        )
        source = source_common_modulation_delay_rhs_in_team_coordinates(
            probe,
            (1.0, 0.0),
            self.parameters,
            modulation_time_constant_s=(
                TEAM_DECLARED_MODULATION_TIME_CONSTANT_S
            ),
        )
        self.assertLess(float(np.linalg.norm(team - source, ord=np.inf)), 1.0e-9)

    def test_equilibrium_is_invariant_across_positive_lag_levels(self) -> None:
        equilibria = [
            solve_common_modulation_delay_equilibrium(
                self.parameters, modulation_time_constant_s=time_constant
            )
            for time_constant in MODULATION_LEVELS_S
        ]
        for equilibrium in equilibria[1:]:
            np.testing.assert_allclose(equilibrium, equilibria[0], atol=1.0e-12)

    def test_named_branches_are_jointly_tracked_without_candidate_reuse(self) -> None:
        self.assertTrue(
            self.audit["hypothesis_test"]["all_named_modes_resolved"]
        )
        for point in self.audit["points"]:
            low = point["low_frequency_mode"]
            wide = point["wide_frequency_mode"]
            self.assertIn(low["tracking"]["status"], {"anchor", "matched"})
            self.assertIn(wide["tracking"]["status"], {"anchor", "matched"})
            self.assertLess(low["pole"]["frequency_hz"], 5.0)
            self.assertGreater(wide["pole"]["frequency_hz"], 50.0)
            self.assertNotEqual(
                low["pole"]["imag_per_s"], wide["pole"]["imag_per_s"]
            )

    def test_bypass_counterexample_is_rejected(self) -> None:
        counterexample = self.audit["counterexample"]
        self.assertTrue(counterexample["gate_rejected_mismatch"])
        self.assertGreater(
            counterexample["state_matrix_max_abs_difference_per_s"], 1000.0
        )

    def test_bounded_hypothesis_is_supported_without_margin_overclaim(self) -> None:
        displacement = self.audit[
            "endpoint_normalized_displacement_from_0p1ms"
        ]
        self.assertGreater(
            displacement["wide_frequency_mode"],
            displacement["low_frequency_mode"],
        )
        self.assertEqual(
            self.audit["hypothesis_test"]["result"],
            "supported-in-bounded-scan",
        )
        scope = self.audit["scope"]
        self.assertTrue(scope["local_dq_first_order_lag_compared"])
        self.assertFalse(scope["physical_pwm_or_transport_delay_compared"])
        self.assertFalse(scope["whole_system_hopf_margin_claimed"])
        self.assertFalse(scope["paper_sufficient_condition_evaluated"])
        self.assertFalse(
            self.audit["ideal_fourteen_state_limit"][
                "force_matched_to_sixteen_state_spectrum"
            ]
        )

    def test_invalid_modulation_time_constant_is_rejected(self) -> None:
        for value in (0.0, -0.1, float("inf"), 1.1):
            with self.subTest(value=value), self.assertRaises(
                CommonModulationDelayError
            ):
                solve_common_modulation_delay_equilibrium(
                    self.parameters, modulation_time_constant_s=value
                )


if __name__ == "__main__":
    unittest.main()
