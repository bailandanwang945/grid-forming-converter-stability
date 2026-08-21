from __future__ import annotations

import unittest

import numpy as np

from backend.core.sienna_team_active_power_measurement_delay import (
    DELAY_LEVELS_S,
    ActivePowerMeasurementDelayError,
    run_common_active_power_measurement_delay_audit,
    solve_common_active_power_delay_equilibrium,
    source_common_active_power_delay_rhs_in_team_coordinates,
    team_common_active_power_delay_rhs,
)
from backend.core.sienna_team_common_outer_loop import (
    frozen_common_outer_loop_parameters,
)


class SiennaTeamActivePowerMeasurementDelayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parameters = frozen_common_outer_loop_parameters()
        cls.payload = run_common_active_power_measurement_delay_audit()

    def test_two_ports_and_all_preregistered_levels_pass(self) -> None:
        self.assertEqual(self.payload["status"], "passed")
        self.assertEqual(self.payload["model_contract"]["state_count"], 14)
        self.assertEqual(
            tuple(self.payload["model_contract"]["delay_levels_s"]),
            DELAY_LEVELS_S,
        )
        for variant in self.payload["variants"].values():
            self.assertEqual(len(variant["points"]), len(DELAY_LEVELS_S))
            for point in variant["points"]:
                self.assertLess(point["equilibrium_residual_inf"], 1.0e-8)
                self.assertLess(point["rhs_difference_inf"], 1.0e-8)
                self.assertLess(
                    point["state_matrix_max_abs_difference_per_s"], 1.0e-5
                )

    def test_source_and_team_paths_match_away_from_equilibrium(self) -> None:
        equilibrium = solve_common_active_power_delay_equilibrium(
            self.parameters,
            power_port="pcc",
            active_power_time_constant_s=0.1,
        )
        probe = equilibrium.copy()
        probe[[0, 1, 2, 3, 5, 9, 11, 13]] += np.array(
            [0.01, -0.002, 0.004, 0.003, -0.005, 0.004, -0.006, 0.002]
        )
        team = team_common_active_power_delay_rhs(
            probe,
            (1.0, 0.0),
            self.parameters,
            power_port="pcc",
            active_power_time_constant_s=0.1,
        )
        source = source_common_active_power_delay_rhs_in_team_coordinates(
            probe,
            (1.0, 0.0),
            self.parameters,
            power_port="pcc",
            active_power_time_constant_s=0.1,
        )
        self.assertLess(np.linalg.norm(team - source, ord=np.inf), 1.0e-9)

    def test_both_named_branches_are_tracked_without_reusing_a_candidate(self) -> None:
        for variant in self.payload["variants"].values():
            for point in variant["points"]:
                low = point["low_frequency_mode"]
                wide = point["wide_frequency_mode"]
                self.assertIn(low["tracking"]["status"], {"anchor", "matched"})
                self.assertIn(wide["tracking"]["status"], {"anchor", "matched"})
                self.assertLess(low["pole"]["frequency_hz"], 10.0)
                self.assertGreater(wide["pole"]["frequency_hz"], 80.0)
                self.assertNotEqual(
                    low["pole"]["imag_per_s"], wide["pole"]["imag_per_s"]
                )

    def test_mixed_port_counterexample_is_rejected(self) -> None:
        counterexample = self.payload["counterexample"]
        self.assertTrue(counterexample["gate_rejected_mismatch"])
        self.assertGreater(
            counterexample["state_matrix_max_abs_difference_per_s"], 100.0
        )

    def test_scope_does_not_relabel_branch_motion_as_hopf_margin(self) -> None:
        scope = self.payload["scope"]
        self.assertTrue(scope["common_intermediate_cases_only"])
        self.assertFalse(scope["whole_system_hopf_margin_claimed"])
        self.assertFalse(scope["external_network_dynamics_compared"])
        self.assertFalse(scope["paper_sufficient_condition_evaluated"])

    def test_invalid_delay_is_rejected(self) -> None:
        for value in (0.0, -0.1, float("inf")):
            with self.subTest(value=value), self.assertRaises(
                ActivePowerMeasurementDelayError
            ):
                solve_common_active_power_delay_equilibrium(
                    self.parameters,
                    power_port="pcc",
                    active_power_time_constant_s=value,
                )


if __name__ == "__main__":
    unittest.main()
