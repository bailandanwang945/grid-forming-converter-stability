from __future__ import annotations

import unittest
from dataclasses import replace

from backend.core.sienna_team_inner_control_mapping import (
    CascadedPIParameters,
    sienna_team_inner_control_mapping_audit,
)


def _source_parameters() -> CascadedPIParameters:
    return CascadedPIParameters(
        voltage_kp=0.59,
        voltage_ki_per_s=736.0,
        current_kp=1.27,
        current_ki_per_s=14.3,
        filter_capacitor_susceptance_pu=0.074,
        converter_side_resistance_pu=0.003,
        converter_side_reactance_pu=0.08,
        current_feedforward_gain=0.0,
        voltage_feedforward_gain=0.0,
        active_damping_gain=0.2,
        resistive_drop_feedforward_gain=0.0,
    )


def _team_parameters() -> CascadedPIParameters:
    return replace(
        _source_parameters(),
        current_feedforward_gain=1.0,
        voltage_feedforward_gain=1.0,
        active_damping_gain=0.0,
        resistive_drop_feedforward_gain=1.0,
    )


class SiennaTeamInnerControlMappingTest(unittest.TestCase):
    def test_pi_states_are_isomorphic_after_integral_gain_scaling(self) -> None:
        audit = sienna_team_inner_control_mapping_audit(
            _source_parameters(), _team_parameters()
        )
        mapping = audit["pi_state_mapping"]
        self.assertEqual(mapping["status"], "passed")
        tolerance = audit["verification_gates"]["matrix_max_abs_difference"]
        self.assertLessEqual(
            mapping["state_input_matrix_max_abs_difference"], tolerance
        )
        self.assertLessEqual(
            mapping["state_output_matrix_max_abs_difference"], tolerance
        )
        self.assertLessEqual(
            mapping["proportional_matrix_max_abs_difference"], tolerance
        )
        self.assertTrue(audit["scope"]["pi_states_isomorphic_after_scaling"])

    def test_exposed_switch_alignment_leaves_resistive_feedforward_gap(self) -> None:
        audit = sienna_team_inner_control_mapping_audit(
            _source_parameters(), _team_parameters()
        )
        mapping = audit["compensation_mapping"]
        self.assertAlmostEqual(
            mapping["test08_to_team_max_abs_difference"], 1.2, places=12
        )
        self.assertAlmostEqual(
            mapping["parameter_only_aligned_max_abs_difference"],
            0.003,
            places=12,
        )
        self.assertFalse(mapping["parameter_only_isomorphic"])
        self.assertIn("+Rf*i_f", mapping["remaining_term"])
        self.assertFalse(
            audit["scope"]["test08_and_team_complete_inner_controls_isomorphic"]
        )

    def test_structural_counterfactual_closes_but_is_not_source_test08(self) -> None:
        audit = sienna_team_inner_control_mapping_audit(
            _source_parameters(), _team_parameters()
        )
        mapping = audit["compensation_mapping"]
        self.assertEqual(mapping["structural_counterfactual_max_abs_difference"], 0.0)
        self.assertTrue(mapping["structural_counterfactual_passed"])
        self.assertFalse(audit["scope"]["structural_counterfactual_is_source_test08"])

    def test_gain_or_state_definition_mismatch_fails_pi_gate(self) -> None:
        mismatched_team = replace(_team_parameters(), current_ki_per_s=15.0)
        audit = sienna_team_inner_control_mapping_audit(
            _source_parameters(), mismatched_team
        )
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["pi_state_mapping"]["status"], "failed")

    def test_noninvertible_integral_scaling_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "integral gains must be positive"):
            sienna_team_inner_control_mapping_audit(
                replace(_source_parameters(), voltage_ki_per_s=0.0),
                _team_parameters(),
            )


if __name__ == "__main__":
    unittest.main()
