from __future__ import annotations

import csv
import json
import math
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = PROJECT_ROOT / "results" / "mathworks-gfm-external-validation"
JSON_PATH = RESULT_ROOT / "mathworks_gfm_scr_step_study.json"
CSV_PATH = RESULT_ROOT / "mathworks_gfm_scr_step_points.csv"


class MathWorksExternalArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(JSON_PATH.read_text(encoding="utf-8-sig"))

    def test_frozen_source_contract_and_scope_are_preserved(self) -> None:
        source = self.payload["source"]
        contract = self.payload["contract"]
        scope = self.payload["scope"]

        self.assertEqual(
            self.payload["schemaVersion"],
            "gfm-mathworks-external-scr-step/1.0",
        )
        self.assertEqual(source["releaseTag"], "23.2.1.4")
        self.assertEqual(
            source["commit"],
            "a65692b004637acb38b2f8c64db7dcf47efe24c7",
        )
        self.assertEqual(
            source["modelSha256"],
            "9cd2abfd5699e92336ceb335414403cb29826da7a4f7ab3abafd581d96c6fac4",
        )
        self.assertEqual(
            source["conditionSha256"],
            "66632a96de03f438bf63ef51afa8d80fcf720cb520431d64f3f8e6756e632823",
        )
        self.assertEqual(source["matlabRelease"], "2024b")
        self.assertEqual(contract["scrValues"], [1.5, 2.5, 5])
        self.assertEqual(contract["xByR"], 5)
        self.assertEqual(contract["activePowerMethod"], "Virtual Synchronous Machine")
        self.assertEqual(contract["currentLimitMethod"], "Virtual Impedance")
        self.assertFalse(scope["physicalHardwareValidation"])
        self.assertFalse(scope["paperSufficientConditionEvaluated"])
        self.assertFalse(scope["causalMechanismIdentified"])
        self.assertFalse(scope["continuousScrBoundaryEstablished"])

    def test_three_points_reject_the_frozen_monotonic_hypothesis(self) -> None:
        points = self.payload["points"]
        hypothesis = self.payload["hypothesis"]

        self.assertEqual(len(points), 3)
        self.assertEqual([point["scr"] for point in points], [1.5, 2.5, 5])
        self.assertTrue(all(point["allReportedSignalsFinite"] for point in points))
        self.assertEqual(
            [point["vendorOutcome"] for point in points],
            ["Stable", "Stable", "Unstable"],
        )
        self.assertAlmostEqual(points[0]["activePowerSettlingTimeS"], 0.6467, places=4)
        self.assertAlmostEqual(points[1]["activePowerSettlingTimeS"], 0.4688, places=4)
        self.assertIsNone(points[2]["activePowerSettlingTimeS"])
        self.assertAlmostEqual(
            points[2]["frequencyMaximumDeviationHz"],
            184.821472500677,
            places=6,
        )
        self.assertAlmostEqual(
            points[2]["activePowerFinalAbsoluteErrorPu"],
            0.513580896168343,
            places=9,
        )
        self.assertFalse(hypothesis["frequencyDeviationMonotonicImprovement"])
        self.assertFalse(hypothesis["settlingTimeMonotonicImprovement"])
        self.assertFalse(hypothesis["allPointsVendorStable"])
        self.assertFalse(hypothesis["supported"])

    def test_csv_matches_json_points(self) -> None:
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))

        self.assertEqual(len(rows), 3)
        self.assertEqual([float(row["scr"]) for row in rows], [1.5, 2.5, 5.0])
        self.assertEqual(
            [row["vendorOutcome"] for row in rows],
            ["Stable", "Stable", "Unstable"],
        )
        self.assertTrue(math.isnan(float(rows[2]["activePowerSettlingTimeS"])))
        for row, point in zip(rows, self.payload["points"], strict=True):
            self.assertAlmostEqual(
                float(row["frequencyMaximumDeviationHz"]),
                point["frequencyMaximumDeviationHz"],
                places=12,
            )


if __name__ == "__main__":
    unittest.main()
