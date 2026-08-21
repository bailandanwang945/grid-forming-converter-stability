from __future__ import annotations

import unittest

from backend.core.sienna_team_inner_loop_modal_fingerprint import (
    CommonInnerLoopModalFingerprintError,
    _apply_factor,
    frozen_common_inner_loop_parameters,
    run_common_inner_loop_modal_fingerprint,
)


class SiennaTeamInnerLoopModalFingerprintTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = run_common_inner_loop_modal_fingerprint()

    def test_four_fixed_variants_pass_pre_registered_gates(self) -> None:
        self.assertEqual(self.payload["status"], "passed")
        self.assertEqual(len(self.payload["variants"]), 4)
        self.assertTrue(
            self.payload["hypothesis_test"]["consistent_in_all_four_variants"]
        )
        for variant in self.payload["variants"].values():
            self.assertTrue(variant["all_pre_registered_endpoints_matched"])
            self.assertEqual(
                variant["candidate_interaction_evidence"]["status"],
                "consistent",
            )

    def test_named_branch_is_about_100_hz_and_participation_is_normalized(self) -> None:
        for key, variant in self.payload["variants"].items():
            with self.subTest(variant=key):
                baseline = variant["baseline_named_branch"]
                frequency = baseline["eigenvalue"]["oscillation_frequency_hz"]
                self.assertGreater(frequency, 95.0)
                self.assertLess(frequency, 110.0)
                participation = baseline[
                    "group_participation_frozen_coordinates"
                ]
                self.assertAlmostEqual(sum(participation.values()), 1.0, places=12)
                self.assertGreater(
                    participation["grid_side_filter_current"], 0.60
                )
                self.assertGreater(participation["voltage_pi"], 0.10)
                self.assertLess(baseline["condition_number"], 1.0e8)
                self.assertLess(
                    max(
                        baseline["right_eigenpair_residual"],
                        baseline["left_eigenpair_residual"],
                    ),
                    1.0e-10,
                )

    def test_active_damping_state_has_small_participation_in_frozen_basis(self) -> None:
        for key in ("12_state_omit_rfif", "12_state_include_rfif"):
            participation = self.payload["variants"][key][
                "baseline_named_branch"
            ]["group_participation_frozen_coordinates"]
            self.assertLess(participation["active_damping_filter"], 0.01)

    def test_grid_side_filter_reactance_is_top_local_real_part_sensitivity(self) -> None:
        for key, variant in self.payload["variants"].items():
            with self.subTest(variant=key):
                self.assertEqual(
                    variant["sensitivity_ranking"][0]["factor_name"],
                    "grid_side_filter_reactance",
                )
                self.assertGreater(
                    variant["sensitivity_ranking"][0][
                        "maximum_absolute_real_shift_per_s"
                    ],
                    25.0,
                )

    def test_large_direct_jump_is_rejected_and_refinement_recovers_branch(self) -> None:
        counterexample = self.payload["tracking_counterexample"]
        self.assertTrue(counterexample["direct_jump_rejected"])
        self.assertTrue(counterexample["refinement_recovers_branch"])
        self.assertEqual(counterexample["refined_path_status"], "matched")
        self.assertGreater(
            counterexample[
                "refined_path_step_count_including_rejected_attempt"
            ],
            1,
        )

    def test_scope_does_not_relabel_x2_as_grid_strength_or_claim_causality(self) -> None:
        scope = self.payload["scope"]
        self.assertFalse(scope["grid_strength_scanned"])
        self.assertIn("not SCR", scope["grid_side_reactance_meaning"])
        self.assertFalse(scope["causal_attribution_established"])
        self.assertFalse(scope["outer_controls_compared"])
        self.assertFalse(scope["participation_invariant_to_future_state_rescaling"])

    def test_invalid_factor_contract_is_rejected(self) -> None:
        parameters = frozen_common_inner_loop_parameters()
        with self.assertRaises(CommonInnerLoopModalFingerprintError):
            _apply_factor(
                parameters,
                "unknown",
                1.0,
                active_damping_gain=0.2,
                active_damping_cutoff_rad_s=50.0,
            )
        with self.assertRaises(CommonInnerLoopModalFingerprintError):
            _apply_factor(
                parameters,
                "voltage_pi_joint_gain",
                0.0,
                active_damping_gain=0.2,
                active_damping_cutoff_rad_s=50.0,
            )


if __name__ == "__main__":
    unittest.main()
