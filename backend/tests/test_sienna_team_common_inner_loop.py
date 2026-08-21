from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np

from backend.core.sienna_team_common_inner_loop import (
    CommonInnerLoopParameters,
    sienna_team_common_inner_loop_audit,
)


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


class SiennaTeamCommonInnerLoopTest(unittest.TestCase):
    def test_both_reversible_structural_variants_are_isomorphic(self) -> None:
        audit = sienna_team_common_inner_loop_audit(
            _parameters(), angle_rad=0.1978641793142158
        )
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["common_model"]["state_count"], 10)
        tolerance = audit["verification_gate"][
            "matrix_and_rhs_max_abs_difference_per_s"
        ]
        for variant in audit["variants"].values():
            self.assertEqual(variant["status"], "passed")
            self.assertLessEqual(
                variant["state_matrix_max_abs_difference_per_s"], tolerance
            )
            self.assertLessEqual(
                variant["input_matrix_max_abs_difference_per_s"], tolerance
            )
            self.assertLessEqual(
                variant["probe_rhs_max_abs_difference_per_s"], tolerance
            )

    def test_equivalence_is_invariant_to_alignment_angle(self) -> None:
        for angle in (0.0, -0.7, np.pi):
            with self.subTest(angle=angle):
                audit = sienna_team_common_inner_loop_audit(
                    _parameters(), angle_rad=float(angle)
                )
                self.assertEqual(audit["status"], "passed")

    def test_feedforward_counterexample_is_rejected(self) -> None:
        audit = sienna_team_common_inner_loop_audit(_parameters(), angle_rad=0.2)
        counterfactual = audit["counterfactual"]
        self.assertTrue(counterfactual["gate_rejected_mismatch"])
        self.assertGreater(
            counterfactual["state_matrix_max_abs_difference_per_s"], 1.0
        )

    def test_structural_choice_changes_spectrum_but_not_tested_classification(self) -> None:
        audit = sienna_team_common_inner_loop_audit(_parameters(), angle_rad=0.2)
        sensitivity = audit["structural_choice_sensitivity"]
        self.assertGreater(
            sensitivity["maximum_matched_eigenvalue_displacement_per_s"], 1.0
        )
        self.assertGreater(abs(sensitivity["spectral_abscissa_change_per_s"]), 1.0)
        self.assertFalse(sensitivity["stability_classification_changed"])
        for variant in audit["variants"].values():
            self.assertFalse(variant["stable_by_eigenvalues"])
        self.assertFalse(audit["scope"]["source_baselines_modified"])
        self.assertFalse(audit["scope"]["outer_controls_compared"])

    def test_nonzero_active_damping_is_outside_common_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "active damping disabled"):
            sienna_team_common_inner_loop_audit(
                replace(_parameters(), active_damping_gain=0.2), angle_rad=0.2
            )


if __name__ == "__main__":
    unittest.main()
