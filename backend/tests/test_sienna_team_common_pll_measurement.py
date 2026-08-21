from __future__ import annotations

import unittest

import numpy as np

from backend.core.sienna_team_common_pll_measurement import (
    CommonPllMeasurementError,
    common_pll_equilibrium,
    run_common_pll_measurement_audit,
    source_common_pll_rhs_in_team_coordinates,
    team_common_pll_rhs,
)


class SiennaTeamCommonPllMeasurementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = run_common_pll_measurement_audit()

    def test_four_cases_pass_equation_gates_without_forcing_pending_modes(self) -> None:
        self.assertEqual(self.audit["status"], "passed")
        self.assertEqual(len(self.audit["cases"]), 4)
        self.assertTrue(
            self.audit["hypothesis_tests"]["four_common_equations_match"]
        )
        self.assertFalse(self.audit["hypothesis_tests"]["named_modes_resolved"])
        self.assertEqual(
            self.audit["hypothesis_tests"][
                "measurement_position_effect_conclusion"
            ],
            "pending-because-a-named-mode-crosses-or-approaches-real-axis",
        )
        self.assertEqual(
            self.audit["cases"]["pcc__damping_on"]["continuation"]["status"],
            "pending",
        )

    def test_damping_off_is_a_structural_negative_control(self) -> None:
        self.assertTrue(
            self.audit["hypothesis_tests"][
                "damping_off_is_structural_negative_control"
            ]
        )
        for port in ("filter_capacitor", "pcc"):
            control = self.audit["cases"][f"{port}__damping_off"][
                "negative_control"
            ]
            self.assertLessEqual(
                control["pll_to_converter_feedback_max_abs_per_s"], 1.0e-8
            )

    def test_source_and_team_paths_match_away_from_equilibrium(self) -> None:
        state = common_pll_equilibrium(
            pll_voltage_port="filter_capacitor", damping_gain=400.0
        )
        probe = state + np.linspace(-2.0e-5, 2.0e-5, 18)
        team = team_common_pll_rhs(
            probe,
            (1.0, 0.0),
            pll_voltage_port="filter_capacitor",
            damping_gain=400.0,
        )
        source = source_common_pll_rhs_in_team_coordinates(
            probe,
            (1.0, 0.0),
            pll_voltage_port="filter_capacitor",
            damping_gain=400.0,
        )
        self.assertLess(float(np.linalg.norm(team - source, ord=np.inf)), 1.0e-8)

    def test_scope_rejects_causal_and_margin_overclaim(self) -> None:
        scope = self.audit["scope"]
        self.assertTrue(scope["common_intermediate_cases_only"])
        self.assertFalse(scope["whole_system_hopf_margin_claimed"])
        self.assertFalse(scope["paper_sufficient_condition_evaluated"])

    def test_invalid_voltage_port_and_damping_are_rejected(self) -> None:
        with self.assertRaises(CommonPllMeasurementError):
            common_pll_equilibrium(pll_voltage_port="terminal", damping_gain=0.0)
        with self.assertRaises(CommonPllMeasurementError):
            common_pll_equilibrium(pll_voltage_port="pcc", damping_gain=500.0)


if __name__ == "__main__":
    unittest.main()
