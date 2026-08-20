from __future__ import annotations

import unittest

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
        self.assertFalse(scope["paper_sufficient_condition_evaluated"])

    def test_api_recomputes_the_audit_with_the_same_claim_boundary(self) -> None:
        response = self.client.get("/api/reference/sienna-test08/audit")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(len(payload["results"]["computed_eigenvalues"]), 19)
        self.assertFalse(payload["scope"]["julia_runtime_executed_on_this_machine"])


if __name__ == "__main__":
    unittest.main()
