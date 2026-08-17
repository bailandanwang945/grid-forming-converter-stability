from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = PROJECT_ROOT / "results" / "mathworks-gfm-external-validation"
JSON_PATH = RESULT_ROOT / "mathworks_gfm_scr5_damping_transition.json"
CSV_PATH = RESULT_ROOT / "mathworks_gfm_scr5_damping_transition_trials.csv"


class MathWorksExternalTransitionArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(JSON_PATH.read_text(encoding="utf-8-sig"))

    def test_contract_uses_frozen_factorial_bracket_and_scope(self) -> None:
        source = self.payload["source"]
        contract = self.payload["contract"]
        scope = self.payload["scope"]

        self.assertEqual(
            self.payload["schemaVersion"],
            "gfm-mathworks-scr5-damping-transition/1.0",
        )
        self.assertEqual(source["releaseTag"], "23.2.1.4")
        self.assertEqual(
            source["commit"],
            "a65692b004637acb38b2f8c64db7dcf47efe24c7",
        )
        self.assertEqual(
            source["factorialArtifactSha256"],
            "90173e9ba8f9e554ff7058af2e004a741c37f4ed7340feb78064d045f0033fea",
        )
        self.assertEqual(contract["scr"], 5)
        self.assertEqual(contract["initialUnstableDampingPu"], 1.056)
        self.assertEqual(contract["initialStableDampingPu"], 2)
        self.assertEqual(contract["targetBracketWidthPu"], 0.02)
        self.assertEqual(contract["maximumIterations"], 6)
        self.assertEqual(contract["classificationFunction"], "FindTestOutCome")
        self.assertFalse(scope["closedLoopEigenvalueBoundary"])
        self.assertFalse(scope["continuousStabilityProof"])
        self.assertFalse(scope["projectTrackingTransitionTargetEstablished"])
        self.assertFalse(scope["paperSufficientConditionEvaluated"])

    def test_vendor_classification_and_tracking_gates_remain_distinct(self) -> None:
        result = self.payload["result"]
        trials = self.payload["trials"]

        self.assertEqual(len(trials), 6)
        expected_damping = [1.528, 1.292, 1.41, 1.351, 1.3215, 1.30675]
        for trial, expected in zip(trials, expected_damping, strict=True):
            self.assertAlmostEqual(
                trial["dampingCoefficientPu"],
                expected,
                places=12,
            )
        self.assertEqual(
            [trial["vendorOutcome"] for trial in trials],
            ["Stable", "Unstable", "Stable", "Stable", "Stable", "Unstable"],
        )
        self.assertTrue(all(trial["allReportedSignalsFinite"] for trial in trials))
        self.assertEqual(result["status"], "bracketed")
        self.assertAlmostEqual(result["unstableLowerDampingPu"], 1.30675, places=12)
        self.assertAlmostEqual(result["stableUpperDampingPu"], 1.3215, places=12)
        self.assertLessEqual(result["bracketWidthPu"], 0.02)
        self.assertTrue(result["testedClassificationMonotonic"])
        self.assertFalse(result["vendorStableUpperEndpointTrackingAcceptable"])
        self.assertTrue(result["vendorStableDoesNotImplyTrackingGate"])
        self.assertTrue(result["trackingGateTestedMonotonic"])
        self.assertAlmostEqual(
            result["trackingFailureLowerDampingPu"],
            1.3215,
            places=12,
        )
        self.assertAlmostEqual(
            result["trackingPassUpperDampingPu"],
            1.351,
            places=12,
        )
        self.assertFalse(result["trackingTargetWidthAchieved"])

    def test_csv_matches_json_and_checkpoint_is_not_a_final_artifact(self) -> None:
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))

        self.assertEqual(len(rows), 6)
        self.assertFalse(
            (RESULT_ROOT / "mathworks_gfm_scr5_damping_transition_checkpoint.json").exists()
        )
        for row, trial in zip(rows, self.payload["trials"], strict=True):
            self.assertEqual(row["vendorOutcome"], trial["vendorOutcome"])
            self.assertAlmostEqual(
                float(row["dampingCoefficientPu"]),
                trial["dampingCoefficientPu"],
                places=12,
            )
            self.assertAlmostEqual(
                float(row["frequencyMaximumDeviationHz"]),
                trial["frequencyMaximumDeviationHz"],
                places=12,
            )


if __name__ == "__main__":
    unittest.main()
