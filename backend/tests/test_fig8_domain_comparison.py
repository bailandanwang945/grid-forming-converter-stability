from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.fig8_domain_comparison import load_fig8_domain_comparison


class Fig8DomainComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_frozen_evidence_is_internally_consistent(self) -> None:
        result = load_fig8_domain_comparison()
        counts = result["summary"]["classificationCounts"]
        self.assertEqual(len(result["rows"]), 176)
        self.assertEqual(counts["criterionCoveredStable"], 45)
        self.assertEqual(counts["stableNotCovered"], 96)
        self.assertEqual(counts["unstableNotCovered"], 35)
        self.assertEqual(counts["numericalPending"], 0)
        self.assertEqual(counts["consistencyViolation"], 0)
        self.assertTrue(
            result["summary"]["criterionCoveredSubsetOfReferenceStable"]
        )

    def test_anchor_points_match_pinned_fig8_fixture(self) -> None:
        anchor = load_fig8_domain_comparison()["summary"]["anchorEvidence"]
        self.assertLess(anchor["damping005ConverterMaxAbsError"], 1.0e-9)
        self.assertLess(anchor["damping05ConverterMaxAbsError"], 1.0e-9)
        self.assertEqual(anchor["damping005MaximumRealPoleErrorHz"], 0)
        self.assertEqual(anchor["damping05MaximumRealPoleErrorHz"], 0)

    def test_api_exposes_claim_boundary_and_axes(self) -> None:
        response = self.client.get("/api/comparison/fig8-domain")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["axes"]["impedance_scale_kappa"]), 11)
        self.assertEqual(len(body["axes"]["damping_d"]), 16)
        self.assertIn("not a theorem-level", body["provenance"]["claim_boundary"])
        self.assertEqual(
            body["provenance"]["portable_behavior"],
            "read-only frozen evidence; no MATLAB required",
        )

    def test_printable_report_states_conservatism_without_reversing_logic(self) -> None:
        response = self.client.get("/api/reports/fig8-domain")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("参考稳定但判据未覆盖", response.text)
        self.assertIn("未覆盖不等于失稳", response.text)
        self.assertIn(">45<", response.text)
        self.assertIn(">96<", response.text)


if __name__ == "__main__":
    unittest.main()
