from __future__ import annotations

import unittest

from backend.core.sienna_team_common_static_network import (
    run_common_static_network_audit,
)


class SiennaTeamCommonStaticNetworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = run_common_static_network_audit()

    def test_two_loaded_common_cases_pass_equation_gates(self) -> None:
        self.assertEqual(self.payload["status"], "passed")
        self.assertEqual(
            set(self.payload["variants"]), {"filter_capacitor", "pcc"}
        )
        summary = self.payload["verification_summary"]
        self.assertLessEqual(summary["maximum_equilibrium_residual_inf"], 1.0e-8)
        self.assertLessEqual(
            summary["maximum_off_equilibrium_rhs_difference_inf"], 1.0e-5
        )
        self.assertLessEqual(
            summary["maximum_state_matrix_difference_per_s"], 1.0e-5
        )

    def test_static_network_is_observable_in_the_linearization(self) -> None:
        self.assertGreaterEqual(
            self.payload["verification_summary"][
                "minimum_static_network_effect_per_s"
            ],
            1.0e-3,
        )

    def test_scope_remains_an_intermediate_model(self) -> None:
        scope = self.payload["scope"]
        self.assertTrue(scope["common_loaded_operating_points_aligned"])
        self.assertTrue(scope["common_static_network_coupling_included"])
        self.assertFalse(scope["original_dynamic_line_isomorphism_claimed"])
        self.assertFalse(scope["original_full_model_eigenvalues_comparable"])


if __name__ == "__main__":
    unittest.main()
