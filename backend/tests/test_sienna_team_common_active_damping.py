from __future__ import annotations

import unittest

from backend.core.sienna_team_common_active_damping import (
    sienna_team_common_active_damping_audit,
)
from backend.core.sienna_team_common_inner_loop import CommonInnerLoopParameters


def _parameters() -> CommonInnerLoopParameters:
    return CommonInnerLoopParameters(
        frequency_hz=60.0,
        voltage_kp=0.59,
        voltage_ki_per_s=736.0,
        current_kp=1.27,
        current_ki_per_s=14.3,
        converter_side_resistance_pu=0.003,
        converter_side_reactance_pu=0.08,
        filter_capacitor_susceptance_pu=0.074,
        grid_side_resistance_pu=0.01,
        grid_side_reactance_pu=0.2,
        virtual_resistance_pu=0.0,
        virtual_reactance_pu=0.2,
        resistive_drop_feedforward_gain=0.0,
    )


class SiennaTeamCommonActiveDampingTest(unittest.TestCase):
    def test_both_active_damping_paths_are_equation_isomorphic(self) -> None:
        audit = sienna_team_common_active_damping_audit(
            _parameters(), angle_rad=0.1978641793142158
        )
        self.assertEqual(audit["status"], "passed")
        tolerance = audit["verification_gate"][
            "matrix_and_rhs_max_abs_difference_per_s"
        ]
        for variant in audit["variants"].values():
            active = variant["with_active_damping"]
            self.assertEqual(active["state_count"], 12)
            self.assertEqual(active["status"], "passed")
            self.assertLessEqual(
                active["state_matrix_max_abs_difference_per_s"], tolerance
            )
            self.assertLessEqual(
                active["input_matrix_max_abs_difference_per_s"], tolerance
            )
            self.assertLessEqual(
                active["probe_rhs_max_abs_difference_per_s"], tolerance
            )

    def test_cutoff_counterexample_is_rejected(self) -> None:
        audit = sienna_team_common_active_damping_audit(
            _parameters(), angle_rad=0.2
        )
        self.assertTrue(audit["counterfactual"]["gate_rejected_mismatch"])
        self.assertGreaterEqual(
            audit["counterfactual"]["state_matrix_max_abs_difference_per_s"],
            0.5,
        )

    def test_active_damping_is_not_sufficient_to_change_tested_classification(self) -> None:
        audit = sienna_team_common_active_damping_audit(
            _parameters(), angle_rad=0.2
        )
        self.assertFalse(
            audit["hypothesis_test"]["supported_for_both_structural_paths"]
        )
        for variant in audit["variants"].values():
            self.assertFalse(variant["without_active_damping"]["stable_by_eigenvalues"])
            self.assertFalse(variant["with_active_damping"]["stable_by_eigenvalues"])
            self.assertFalse(variant["stability_classification_changed"])
            self.assertGreater(variant["spectral_abscissa_change_per_s"], 0.0)

    def test_scope_does_not_relabel_intermediate_as_original_model(self) -> None:
        scope = sienna_team_common_active_damping_audit(
            _parameters(), angle_rad=0.2
        )["scope"]
        self.assertFalse(scope["source_baselines_modified"])
        self.assertFalse(scope["team_original_model_modified"])
        self.assertTrue(scope["common_active_damping_intermediate_only"])
        self.assertFalse(scope["outer_controls_compared"])

    def test_invalid_cutoff_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cutoff must be finite and positive"):
            sienna_team_common_active_damping_audit(
                _parameters(), angle_rad=0.2, active_damping_cutoff_rad_s=0.0
            )


if __name__ == "__main__":
    unittest.main()
