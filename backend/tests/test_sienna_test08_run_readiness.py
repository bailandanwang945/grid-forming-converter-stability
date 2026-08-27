from __future__ import annotations

import unittest

from backend.core.sienna_test08_run_readiness import (
    assess_sienna_test08_run_readiness,
)


class SiennaTest08RunReadinessTest(unittest.TestCase):
    def _assessment(self, **overrides: bool) -> dict[str, object]:
        inputs = {
            "source_transcription_verified": True,
            "common_lcl_equations_isomorphic": True,
            "pi_states_isomorphic_after_scaling": True,
            "common_static_network_equations_isomorphic": True,
            "common_loaded_operating_points_aligned": True,
            "complete_inner_controls_isomorphic": False,
            "original_power_measurement_ports_identical": False,
            "loaded_full_model_operating_points_aligned": False,
            "external_network_equations_isomorphic": False,
            "full_state_dimensions_equal": False,
        }
        inputs.update(overrides)
        return assess_sienna_test08_run_readiness(
            **inputs,
            source_state_count=19,
            team_state_count=16,
        )

    def test_current_model_contract_is_not_ready(self) -> None:
        payload = self._assessment()
        self.assertEqual(payload["status"], "not-ready")
        self.assertTrue(
            payload["decisions"]["source_only_julia_baseline_may_be_run"]
        )
        self.assertFalse(
            payload["decisions"][
                "root_by_root_cross_model_eigenvalue_comparison_ready"
            ]
        )
        self.assertEqual(
            payload["state_count_pair"],
            {"sienna_test08": 19, "team_average_dq": 16},
        )

    def test_all_unclosed_original_model_gates_are_reported(self) -> None:
        payload = self._assessment()
        self.assertEqual(
            set(payload["blocking_conditions"]),
            {
                "complete_inner_controls_isomorphic",
                "original_power_measurement_ports_identical",
                "loaded_full_model_operating_points_aligned",
                "external_network_equations_isomorphic",
                "full_state_dimensions_equal",
            },
        )

    def test_counterfactual_all_passed_contract_is_ready(self) -> None:
        payload = self._assessment(
            complete_inner_controls_isomorphic=True,
            original_power_measurement_ports_identical=True,
            loaded_full_model_operating_points_aligned=True,
            external_network_equations_isomorphic=True,
            full_state_dimensions_equal=True,
        )
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["blocking_conditions"], [])
        self.assertFalse(
            payload["decisions"][
                "julia_runtime_installation_required_by_this_gate"
            ]
        )


if __name__ == "__main__":
    unittest.main()
