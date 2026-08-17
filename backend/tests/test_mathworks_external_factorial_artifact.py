from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULT_ROOT = PROJECT_ROOT / "results" / "mathworks-gfm-external-validation"
JSON_PATH = RESULT_ROOT / "mathworks_gfm_scr_damping_factorial.json"
CSV_PATH = RESULT_ROOT / "mathworks_gfm_scr_damping_factorial_points.csv"


class MathWorksExternalFactorialArtifactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(JSON_PATH.read_text(encoding="utf-8-sig"))

    def test_source_contract_and_scope_are_frozen(self) -> None:
        source = self.payload["source"]
        contract = self.payload["contract"]
        scope = self.payload["scope"]

        self.assertEqual(
            self.payload["schemaVersion"],
            "gfm-mathworks-scr-damping-factorial/1.0",
        )
        self.assertEqual(source["releaseTag"], "23.2.1.4")
        self.assertEqual(
            source["commit"],
            "a65692b004637acb38b2f8c64db7dcf47efe24c7",
        )
        self.assertEqual(source["matlabRelease"], "2024b")
        self.assertEqual(contract["scrValues"], [2.5, 5])
        self.assertEqual(
            contract["dampingCoefficientValuesPu"],
            [0.6, 1.056, 2, 4],
        )
        self.assertEqual(contract["vendorDefaultDampingCoefficientPu"], 1.056)
        self.assertEqual(contract["xByR"], 5)
        self.assertFalse(scope["physicalHardwareValidation"])
        self.assertFalse(scope["paperSufficientConditionEvaluated"])
        self.assertFalse(scope["uniqueCausalMechanismIdentified"])
        self.assertFalse(scope["continuousBoundaryEstablished"])
        self.assertFalse(scope["interactionIsStatisticalEstimate"])

    def test_factorial_result_supports_only_the_preregistered_main_hypothesis(self) -> None:
        points = self.payload["points"]
        results = self.payload["results"]

        self.assertEqual(len(points), 8)
        self.assertEqual(
            [(point["scr"], point["dampingCoefficientPu"]) for point in points],
            [
                (2.5, 0.6),
                (2.5, 1.056),
                (2.5, 2),
                (2.5, 4),
                (5, 0.6),
                (5, 1.056),
                (5, 2),
                (5, 4),
            ],
        )
        self.assertTrue(all(point["allReportedSignalsFinite"] for point in points))
        self.assertEqual(
            [point["vendorOutcome"] for point in points],
            [
                "Stable",
                "Stable",
                "Stable",
                "Stable",
                "Unstable",
                "Unstable",
                "Stable",
                "Stable",
            ],
        )
        self.assertEqual(
            results["stableMatrixRowsScrColumnsDamping"],
            [[True, True, True, True], [False, False, True, True]],
        )
        self.assertTrue(results["scr5StableAtHighDamping"])
        self.assertTrue(results["scr2p5StableAcrossTestedDamping"])
        self.assertTrue(results["hypothesisSupported"])
        self.assertTrue(results["classificationDependsOnBothTestedFactors"])
        self.assertEqual(
            results["frequencyDeviationNonincreasingByScr"],
            [True, False],
        )
        self.assertAlmostEqual(
            points[5]["frequencyMaximumDeviationHz"],
            184.8214725006767,
            places=6,
        )
        self.assertAlmostEqual(
            points[6]["activePowerSettlingTimeS"],
            0.4099,
            places=4,
        )
        self.assertAlmostEqual(
            points[7]["activePowerSettlingTimeS"],
            0.882,
            places=4,
        )

    def test_csv_matches_json_and_no_checkpoint_is_mistaken_for_final_output(self) -> None:
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))

        self.assertEqual(len(rows), 8)
        self.assertFalse(
            (RESULT_ROOT / "mathworks_gfm_scr_damping_factorial_checkpoint.json").exists()
        )
        self.assertFalse(
            (RESULT_ROOT / "mathworks_gfm_scr_damping_factorial_checkpoint.csv").exists()
        )
        for row, point in zip(rows, self.payload["points"], strict=True):
            self.assertEqual(row["vendorOutcome"], point["vendorOutcome"])
            self.assertAlmostEqual(float(row["scr"]), point["scr"], places=12)
            self.assertAlmostEqual(
                float(row["dampingCoefficientPu"]),
                point["dampingCoefficientPu"],
                places=12,
            )
            self.assertAlmostEqual(
                float(row["frequencyMaximumDeviationHz"]),
                point["frequencyMaximumDeviationHz"],
                places=12,
            )


if __name__ == "__main__":
    unittest.main()
