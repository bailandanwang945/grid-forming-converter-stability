from __future__ import annotations

import unittest

import numpy as np

from backend.core.sienna_team_common_outer_loop import (
    frozen_common_outer_loop_parameters,
    run_common_outer_loop_audit,
    solve_common_outer_loop_equilibrium,
    source_common_outer_loop_rhs_in_team_coordinates,
    team_common_outer_loop_rhs,
)


class SiennaTeamCommonOuterLoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parameters = frozen_common_outer_loop_parameters()
        cls.payload = run_common_outer_loop_audit()

    def test_two_shared_power_ports_close_the_thirteen_state_equations(self) -> None:
        self.assertEqual(self.payload["status"], "passed")
        self.assertEqual(self.payload["model_contract"]["state_count"], 13)
        self.assertEqual(set(self.payload["variants"]), {"filter_capacitor", "pcc"})
        for variant in self.payload["variants"].values():
            self.assertLess(variant["equilibrium_residual_inf"], 1.0e-8)
            self.assertLess(variant["rhs_difference_inf"], 1.0e-8)
            self.assertLess(
                variant["state_matrix_max_abs_difference_per_s"], 1.0e-5
            )

    def test_loaded_equilibria_meet_the_fixed_active_power_reference(self) -> None:
        for port in ("filter_capacitor", "pcc"):
            equilibrium = solve_common_outer_loop_equilibrium(
                self.parameters, power_port=port
            )
            self.assertGreater(abs(float(equilibrium[0])), 0.1)
            self.assertAlmostEqual(float(equilibrium[1]), 1.0, places=10)
            self.assertGreater(np.linalg.norm(equilibrium[11:13]), 0.4)

    def test_source_and_team_rhs_match_away_from_equilibrium(self) -> None:
        equilibrium = solve_common_outer_loop_equilibrium(
            self.parameters, power_port="pcc"
        )
        probe = equilibrium.copy()
        probe[[0, 1, 2, 4, 8, 10, 12]] += np.array(
            [0.01, -0.002, 0.003, -0.005, 0.004, -0.006, 0.002]
        )
        team = team_common_outer_loop_rhs(
            probe, (1.0, 0.0), self.parameters, power_port="pcc"
        )
        source = source_common_outer_loop_rhs_in_team_coordinates(
            probe, (1.0, 0.0), self.parameters, power_port="pcc"
        )
        self.assertLess(np.linalg.norm(team - source, ord=np.inf), 1.0e-9)

    def test_mixed_power_measurement_ports_are_rejected(self) -> None:
        counterexample = self.payload["counterexample"]
        self.assertTrue(counterexample["gate_rejected_mismatch"])
        self.assertGreater(
            counterexample["state_matrix_max_abs_difference_per_s"], 100.0
        )

    def test_outer_loop_adds_low_frequency_and_retains_wide_frequency_modes(self) -> None:
        for variant in self.payload["variants"].values():
            frequencies = [mode["frequency_hz"] for mode in variant["oscillatory_modes"]]
            self.assertTrue(any(2.0 < frequency < 5.0 for frequency in frequencies))
            self.assertTrue(any(90.0 < frequency < 130.0 for frequency in frequencies))

    def test_scope_does_not_relabel_intermediate_as_original_model(self) -> None:
        scope = self.payload["scope"]
        self.assertTrue(scope["common_intermediate_cases_only"])
        self.assertFalse(scope["power_measurement_port_originally_identical"])
        self.assertFalse(scope["external_network_dynamics_compared"])
        self.assertFalse(scope["active_damping_compared"])

    def test_invalid_power_port_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "power_port"):
            solve_common_outer_loop_equilibrium(
                self.parameters, power_port="unspecified"
            )


if __name__ == "__main__":
    unittest.main()
