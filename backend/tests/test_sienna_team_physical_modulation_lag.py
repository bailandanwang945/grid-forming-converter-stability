from __future__ import annotations

import unittest

import numpy as np

from backend.core.sienna_team_common_modulation_delay import MODULATION_LEVELS_S
from backend.core.sienna_team_common_outer_loop import (
    frozen_common_outer_loop_parameters,
)
from backend.core.sienna_team_physical_modulation_lag import (
    run_physical_modulation_frame_audit,
    solve_physical_modulation_lag_equilibrium,
    source_physical_modulation_lag_rhs_in_team_coordinates,
    team_physical_modulation_lag_rhs,
)


class SiennaTeamPhysicalModulationLagTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = run_physical_modulation_frame_audit()

    def test_equivalent_coordinate_realizations_pass(self) -> None:
        self.assertEqual(self.audit["status"], "passed")
        self.assertLess(
            self.audit["maximum_state_matrix_difference_per_s"], 1.0e-5
        )
        self.assertLess(
            self.audit["maximum_off_equilibrium_rhs_difference_inf"], 1.0e-5
        )

    def test_local_dq_lag_is_rejected_as_equivalent_model(self) -> None:
        self.assertGreater(
            self.audit[
                "minimum_local_dq_vs_physical_matrix_difference_per_s"
            ],
            1.0,
        )

    def test_equilibrium_requires_nonzero_rotational_balance(self) -> None:
        parameters = frozen_common_outer_loop_parameters()
        for time_constant in MODULATION_LEVELS_S:
            equilibrium = solve_physical_modulation_lag_equilibrium(
                parameters,
                modulation_time_constant_s=time_constant,
            )
            team = team_physical_modulation_lag_rhs(
                equilibrium,
                (1.0, 0.0),
                parameters,
                modulation_time_constant_s=time_constant,
            )
            source = source_physical_modulation_lag_rhs_in_team_coordinates(
                equilibrium,
                (1.0, 0.0),
                parameters,
                modulation_time_constant_s=time_constant,
            )
            self.assertLess(float(np.linalg.norm(team, ord=np.inf)), 1.0e-8)
            self.assertLess(float(np.linalg.norm(team - source, ord=np.inf)), 1.0e-8)

    def test_scope_does_not_overclaim_pwm_or_transport_delay(self) -> None:
        scope = self.audit["scope"]
        self.assertTrue(scope["physical_frame_first_order_lag_compared"])
        self.assertFalse(scope["exact_transport_delay_compared"])
        self.assertFalse(scope["pade_delay_approximation_compared"])
        self.assertFalse(scope["switching_or_pwm_waveform_modeled"])


if __name__ == "__main__":
    unittest.main()
