from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.mathworks_team_comparison import (
    evaluate_mathworks_team_comparison,
    source_impedance_from_scr,
)


class MathWorksTeamComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = evaluate_mathworks_team_comparison()
        cls.client = TestClient(app)

    def test_mapping_contract_is_dimensionally_explicit(self) -> None:
        mapping = self.result["mapping_contract"]
        self.assertEqual(mapping["base_frequency_hz"], 50.0)
        self.assertEqual(
            mapping["damping_conversion"],
            "D_team = f_base * D_mathworks",
        )
        self.assertEqual(
            mapping["mathworks_model_gain_expression"],
            "vsmDampingConst*powerFreq",
        )
        self.assertEqual(mapping["x_by_r"], 5.0)
        self.assertEqual(mapping["pre_step_active_power_pu"], 0.6)
        self.assertEqual(mapping["post_step_active_power_pu"], 0.8)

    def test_public_scr_mapping_rejects_nonphysical_inputs(self) -> None:
        resistance, reactance = source_impedance_from_scr(5.0, 5.0)
        self.assertAlmostEqual((resistance**2 + reactance**2) ** 0.5, 0.2)
        self.assertAlmostEqual(reactance / resistance, 5.0)
        for scr, x_by_r in ((0.0, 5.0), (-1.0, 5.0), (5.0, 0.0)):
            with self.assertRaises(ValueError):
                source_impedance_from_scr(scr, x_by_r)

    def test_eight_point_comparison_preserves_the_single_disagreement(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(summary["point_count"], 8)
        self.assertEqual(summary["classification_agreement_count"], 7)
        self.assertEqual(summary["classification_disagreement_count"], 1)
        self.assertTrue(summary["all_team_pre_post_endpoint_classes_equal"])
        self.assertEqual(
            summary["disagreement_points"],
            [
                {
                    "scr": 5.0,
                    "damping_mathworks_pu_per_hz": 1.056,
                    "external_vendor_outcome": "Unstable",
                    "team_pre_step_stability": "stable",
                    "team_post_step_stability": "stable",
                }
            ],
        )

    def test_boundary_difference_is_reported_without_calling_it_error(self) -> None:
        boundary = self.result["boundary_comparison"]
        self.assertEqual(
            boundary["external_vendor_classification_bracket_pu_per_hz"],
            [1.30675, 1.3215],
        )
        roots = boundary["team_local_eigenvalue_boundaries"]
        self.assertAlmostEqual(
            roots[0]["damping_mw_equivalent_pu_per_hz"],
            0.7586000105,
            places=8,
        )
        self.assertAlmostEqual(
            roots[1]["damping_mw_equivalent_pu_per_hz"],
            0.7560116930,
            places=8,
        )
        self.assertFalse(boundary["external_and_team_boundaries_are_same_evidence_type"])
        self.assertFalse(boundary["quantitative_transition_reproduced"])
        self.assertFalse(self.result["scope"]["same_full_physical_model"])
        self.assertFalse(self.result["scope"]["same_classifier"])

    def test_api_recomputes_the_fixed_comparison_and_keeps_scope(self) -> None:
        response = self.client.get("/api/evidence/mathworks-team-comparison")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["classification_agreement_count"], 7)
        self.assertEqual(payload["summary"]["classification_disagreement_count"], 1)
        self.assertFalse(
            payload["boundary_comparison"]["quantitative_transition_reproduced"]
        )
        self.assertTrue(payload["scope"]["nonlinear_team_step_completed"])
        self.assertEqual(
            payload["scope"]["nonlinear_team_step_study_id"],
            "average-dq-aligned-three-point-nonlinear-step-v1",
        )

    def test_frozen_json_csv_and_hashes_match_recomputation(self) -> None:
        root = Path(__file__).resolve().parents[2]
        result_root = root / "results" / "mathworks-team-comparison"
        json_path = result_root / "mathworks_team_aligned_comparison.json"
        csv_path = result_root / "mathworks_team_aligned_points.csv"
        self.assertEqual(
            hashlib.sha256(json_path.read_bytes()).hexdigest(),
            "2c1082339b41d9b615dfc3ee638005a550fbd96f43efcae396c9285fc0138116",
        )
        self.assertEqual(
            hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            "6922603e9757739116017266b771580651113736ffc3bdf38d263af5149aa205",
        )
        frozen = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(frozen, self.result)
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 8)
        self.assertEqual(
            sum(row["classification_agreement"] == "True" for row in rows),
            7,
        )
