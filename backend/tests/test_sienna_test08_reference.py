from __future__ import annotations

import unittest
from dataclasses import replace

import numpy as np
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.sienna_test08_reference import (
    FROZEN_INITIAL_STATE,
    STATE_LABELS,
    SiennaTest08Parameters,
    audit_sienna_test08_transcription,
    sienna_test08_audit_payload,
    sienna_test08_rhs,
    terminal_voltage_from_grid_current,
)
from backend.core.sienna_team_lcl_isomorphism import (
    CommonLCLParameters,
    sienna_team_common_lcl_audit,
)


class SiennaTest08ReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_frozen_state_and_network_reconstruct_upstream_initial_condition(self) -> None:
        self.assertEqual(len(STATE_LABELS), 19)
        self.assertEqual(FROZEN_INITIAL_STATE.shape, (19,))
        terminal_voltage = terminal_voltage_from_grid_current(
            FROZEN_INITIAL_STATE[17:19]
        )
        self.assertAlmostEqual(terminal_voltage.real, 0.9999994707586406, places=14)
        self.assertAlmostEqual(terminal_voltage.imag, 0.0010313084369410759, places=14)

    def test_source_transcription_reproduces_initial_residual(self) -> None:
        residual = sienna_test08_rhs(FROZEN_INITIAL_STATE)
        self.assertLess(np.linalg.norm(residual, ord=np.inf), 1.0e-8)

    def test_source_transcription_reproduces_frozen_19_eigenvalues(self) -> None:
        for relative_step in (2.0e-6, 1.0e-6, 5.0e-7):
            with self.subTest(relative_step=relative_step):
                audit = audit_sienna_test08_transcription(relative_step)
                self.assertLess(audit.matched_eigenvalue_l2_error_per_s, 1.0e-3)
                self.assertLess(audit.matched_eigenvalue_max_error_per_s, 2.0e-4)
                self.assertLess(max(audit.eigenvalues_per_s.real), 0.0)

    def test_frequency_base_discrepancy_is_preserved_as_a_counterexample(self) -> None:
        audit_50_hz = audit_sienna_test08_transcription(
            parameters=SiennaTest08Parameters(frequency_hz=50.0)
        )
        self.assertGreater(audit_50_hz.matched_eigenvalue_max_error_per_s, 1000.0)

    def test_payload_does_not_claim_julia_pscad_or_team_model_validation(self) -> None:
        payload = sienna_test08_audit_payload()
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["model_contract"]["state_count"], 19)
        self.assertLess(
            payload["results"]["matched_eigenvalue_l2_error_per_s"], 1.0e-3
        )
        self.assertGreater(
            payload["results"]["frequency_base_counterfactual"][
                "matched_eigenvalue_max_error_per_s"
            ],
            1000.0,
        )
        scope = payload["scope"]
        self.assertTrue(scope["source_equation_transcription_verified"])
        self.assertFalse(scope["julia_runtime_executed_on_this_machine"])
        self.assertFalse(scope["pscad_rerun"])
        self.assertFalse(scope["team_16_state_model_validated_by_this_audit"])
        self.assertTrue(scope["team_common_lcl_layer_compared"])
        self.assertFalse(scope["paper_sufficient_condition_evaluated"])

        common = payload["common_lcl_isomorphism"]
        self.assertEqual(common["status"], "passed")
        self.assertEqual(common["common_layer"]["state_count"], 6)
        self.assertLess(
            common["results"]["state_matrix_max_abs_difference_per_s"], 1.0e-10
        )
        self.assertGreater(
            common["results"]["counterfactual"][
                "state_matrix_max_abs_difference_per_s"
            ],
            1.0,
        )
        self.assertFalse(
            common["network_interface"]["included_in_common_lcl_gate"]
        )
        self.assertAlmostEqual(
            common["network_interface"]["network_reactance_pu_device_base"],
            0.0020625,
            places=12,
        )
        self.assertFalse(common["scope"]["full_state_dimensions_equal"])
        self.assertFalse(
            common["scope"]["full_model_eigenvalues_comparable_from_this_gate"]
        )

        inner = payload["inner_control_mapping"]
        self.assertEqual(inner["status"], "partial")
        self.assertEqual(inner["pi_state_mapping"]["status"], "passed")
        self.assertFalse(
            inner["compensation_mapping"]["parameter_only_isomorphic"]
        )
        self.assertAlmostEqual(
            inner["compensation_mapping"][
                "parameter_only_aligned_max_abs_difference"
            ],
            0.003,
            places=12,
        )
        self.assertFalse(
            inner["scope"]["test08_and_team_complete_inner_controls_isomorphic"]
        )
        self.assertTrue(scope["team_pi_state_scaling_compared"])
        self.assertFalse(scope["team_complete_inner_control_compared"])

        common_inner = payload["common_inner_loop"]
        self.assertEqual(common_inner["status"], "passed")
        self.assertEqual(common_inner["common_model"]["state_count"], 10)
        self.assertEqual(len(common_inner["variants"]), 2)
        self.assertTrue(
            common_inner["counterfactual"]["gate_rejected_mismatch"]
        )
        self.assertFalse(
            common_inner["structural_choice_sensitivity"][
                "stability_classification_changed"
            ]
        )
        self.assertTrue(scope["team_common_inner_loop_variants_compared"])

        active_damping = payload["common_active_damping"]
        self.assertEqual(active_damping["status"], "passed")
        self.assertTrue(
            active_damping["counterfactual"]["gate_rejected_mismatch"]
        )
        self.assertFalse(
            active_damping["hypothesis_test"][
                "supported_for_both_structural_paths"
            ]
        )
        for variant in active_damping["variants"].values():
            self.assertEqual(variant["with_active_damping"]["state_count"], 12)
            self.assertFalse(variant["stability_classification_changed"])
        self.assertTrue(scope["team_common_active_damping_variants_compared"])

        modal_fingerprint = payload["common_inner_loop_modal_fingerprint"]
        self.assertEqual(modal_fingerprint["status"], "passed")
        self.assertEqual(len(modal_fingerprint["variants"]), 4)
        baseline = modal_fingerprint["variants"]["10_state_omit_rfif"][
            "baseline_named_branch"
        ]
        self.assertGreater(
            baseline["group_participation_frozen_coordinates"][
                "grid_side_filter_current"
            ],
            0.6,
        )
        self.assertEqual(
            modal_fingerprint["variants"]["10_state_omit_rfif"][
                "sensitivity_ranking"
            ][0]["factor_name"],
            "grid_side_filter_reactance",
        )
        self.assertTrue(
            modal_fingerprint["tracking_counterexample"][
                "refinement_recovers_branch"
            ]
        )
        self.assertTrue(
            scope["team_common_inner_loop_modal_fingerprint_evaluated"]
        )

        common_outer = payload["common_outer_loop"]
        self.assertEqual(common_outer["status"], "passed")
        self.assertEqual(common_outer["model_contract"]["state_count"], 13)
        self.assertTrue(common_outer["counterexample"]["gate_rejected_mismatch"])
        self.assertFalse(
            common_outer["scope"]["power_measurement_port_originally_identical"]
        )
        self.assertTrue(scope["team_common_outer_loop_power_ports_compared"])

        delayed_power = payload["common_active_power_measurement_delay"]
        self.assertEqual(delayed_power["status"], "passed")
        self.assertEqual(delayed_power["model_contract"]["state_count"], 14)
        self.assertTrue(
            delayed_power["counterexample"]["gate_rejected_mismatch"]
        )
        self.assertTrue(
            delayed_power["hypothesis_test"][
                "supported_in_both_port_conventions"
            ]
        )
        self.assertTrue(
            scope["team_common_active_power_measurement_delay_compared"]
        )

        common_pll = payload["common_pll_measurement"]
        self.assertEqual(common_pll["status"], "passed")
        self.assertEqual(common_pll["model_contract"]["state_count"], 18)
        self.assertTrue(
            common_pll["hypothesis_tests"][
                "damping_off_is_structural_negative_control"
            ]
        )
        self.assertFalse(
            common_pll["hypothesis_tests"]["named_modes_resolved"]
        )
        self.assertTrue(
            scope["team_common_pll_measurement_position_compared"]
        )
        self.assertEqual(payload["common_modulation_delay"]["status"], "passed")
        self.assertEqual(payload["physical_modulation_lag"]["status"], "passed")
        self.assertEqual(payload["delay_approximation"]["status"], "passed")
        self.assertEqual(payload["external_line_dynamics"]["status"], "passed")
        readiness = payload["third_party_run_readiness"]
        self.assertEqual(readiness["status"], "not-ready")
        self.assertTrue(
            readiness["decisions"]["source_only_julia_baseline_may_be_run"]
        )
        self.assertFalse(
            readiness["decisions"][
                "root_by_root_cross_model_eigenvalue_comparison_ready"
            ]
        )
        self.assertEqual(len(readiness["blocking_conditions"]), 5)
        self.assertTrue(scope["team_common_local_dq_modulation_lag_compared"])
        self.assertTrue(scope["physical_frame_modulation_lag_compared"])
        self.assertTrue(scope["delay_realization_frequency_responses_compared"])
        self.assertTrue(scope["team_static_and_dynamic_external_line_compared"])

    def test_common_lcl_equivalence_is_invariant_to_alignment_angle(self) -> None:
        source = SiennaTest08Parameters()
        common = CommonLCLParameters(
            frequency_hz=source.frequency_hz,
            converter_side_resistance_pu=source.converter_side_resistance_pu,
            converter_side_reactance_pu=source.converter_side_reactance_pu,
            filter_capacitor_susceptance_pu=(
                source.filter_capacitor_susceptance_pu
            ),
            grid_side_resistance_pu=source.grid_side_resistance_pu,
            grid_side_reactance_pu=source.grid_side_reactance_pu,
        )
        for angle in (0.0, 0.1978641793142158, -1.2, np.pi):
            with self.subTest(angle=angle):
                audit = sienna_team_common_lcl_audit(
                    common,
                    common,
                    angle_rad=angle,
                    network_reactance_pu_system_base=(
                        source.network_reactance_pu_system_base
                    ),
                    system_base_power_mva=source.system_base_power_mva,
                    device_base_power_mva=source.device_base_power_mva,
                )
                self.assertEqual(audit["status"], "passed")
                self.assertLess(
                    audit["results"]["probe_rhs_max_abs_difference_per_s"],
                    1.0e-10,
                )

    def test_common_lcl_gate_rejects_a_parameter_mismatch(self) -> None:
        source = SiennaTest08Parameters()
        common = CommonLCLParameters(
            frequency_hz=source.frequency_hz,
            converter_side_resistance_pu=source.converter_side_resistance_pu,
            converter_side_reactance_pu=source.converter_side_reactance_pu,
            filter_capacitor_susceptance_pu=(
                source.filter_capacitor_susceptance_pu
            ),
            grid_side_resistance_pu=source.grid_side_resistance_pu,
            grid_side_reactance_pu=source.grid_side_reactance_pu,
        )
        mismatched_team = replace(common, grid_side_reactance_pu=0.21)
        audit = sienna_team_common_lcl_audit(
            common,
            mismatched_team,
            angle_rad=0.2,
            network_reactance_pu_system_base=(
                source.network_reactance_pu_system_base
            ),
            system_base_power_mva=source.system_base_power_mva,
            device_base_power_mva=source.device_base_power_mva,
        )
        self.assertEqual(audit["status"], "failed")
        self.assertGreater(
            audit["results"]["state_matrix_max_abs_difference_per_s"], 1.0
        )

    def test_api_recomputes_the_audit_with_the_same_claim_boundary(self) -> None:
        response = self.client.get("/api/reference/sienna-test08/audit")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(len(payload["results"]["computed_eigenvalues"]), 19)
        self.assertEqual(payload["common_lcl_isomorphism"]["status"], "passed")
        self.assertEqual(
            payload["inner_control_mapping"]["pi_state_mapping"]["status"],
            "passed",
        )
        self.assertFalse(
            payload["inner_control_mapping"]["scope"][
                "test08_and_team_complete_inner_controls_isomorphic"
            ]
        )
        self.assertEqual(payload["common_inner_loop"]["status"], "passed")
        self.assertEqual(payload["common_active_damping"]["status"], "passed")
        self.assertEqual(
            payload["common_inner_loop_modal_fingerprint"]["status"],
            "passed",
        )
        self.assertEqual(payload["common_outer_loop"]["status"], "passed")
        self.assertEqual(
            payload["common_active_power_measurement_delay"]["status"],
            "passed",
        )
        self.assertEqual(payload["common_pll_measurement"]["status"], "passed")
        self.assertEqual(payload["common_modulation_delay"]["status"], "passed")
        self.assertEqual(payload["physical_modulation_lag"]["status"], "passed")
        self.assertEqual(payload["delay_approximation"]["status"], "passed")
        self.assertEqual(payload["external_line_dynamics"]["status"], "passed")
        self.assertFalse(payload["scope"]["julia_runtime_executed_on_this_machine"])


if __name__ == "__main__":
    unittest.main()
