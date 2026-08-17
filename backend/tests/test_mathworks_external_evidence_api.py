from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.mathworks_external_evidence import (
    MathWorksExternalEvidenceError,
    load_mathworks_external_evidence,
)


class MathWorksExternalEvidenceApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_endpoint_returns_hash_verified_read_only_summary(self) -> None:
        response = self.client.get("/api/evidence/mathworks-gfm")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(
            payload["summary"]["three_point_vendor_outcomes"],
            ["Stable", "Stable", "Unstable"],
        )
        self.assertEqual(payload["summary"]["factorial_stable_point_count"], 6)
        self.assertEqual(payload["summary"]["factorial_point_count"], 8)
        self.assertEqual(
            payload["summary"]["vendor_classification_bracket_pu"],
            [1.30675, 1.3215],
        )
        self.assertEqual(
            payload["summary"]["project_tracking_observed_bracket_pu"],
            [1.3215, 1.351],
        )
        self.assertFalse(payload["summary"]["project_tracking_target_achieved"])
        self.assertFalse(payload["scope"]["reruns_matlab_or_simulink"])
        self.assertFalse(payload["scope"]["closed_loop_eigenvalue_boundary"])
        self.assertFalse(payload["scope"]["paper_sufficient_condition_evaluated"])

    def test_missing_or_changed_artifacts_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(
                MathWorksExternalEvidenceError,
                "缺少冻结",
            ):
                load_mathworks_external_evidence(root)
