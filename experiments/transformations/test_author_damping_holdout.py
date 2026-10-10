"""Regression checks for saved-result audit, including deliberate corruption."""
import copy
import json
import unittest

from verify_author_damping_holdout import ROOT, RESULT, audit


class SavedHoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(RESULT.read_text(encoding="utf-8"))
        cls.models = json.loads((RESULT.parent / "models.json").read_text(encoding="utf-8"))
        cls.selection = json.loads((ROOT / "results/automatic-transform-search/run-2026-10-03-01/run.json").read_text(encoding="utf-8"))

    def test_saved_result(self):
        self.assertEqual(len(audit(self.result, self.models, self.selection)), 3)

    def test_frozen_candidate_drift(self):
        modified = copy.deepcopy(self.result)
        modified["frozen_candidates"]["evolution"]["cutoff_hz"] = 999
        with self.assertRaisesRegex(AssertionError, "Candidates were not frozen"):
            audit(modified, self.models, self.selection)

    def test_reference_mislabel(self):
        modified = copy.deepcopy(self.result)
        modified["cases"][0]["closed_loop_reference"] = "unstable"
        with self.assertRaisesRegex(AssertionError, "Wrong reference label"):
            audit(modified, self.models, self.selection)

    def test_counts_corruption(self):
        modified = copy.deepcopy(self.result)
        modified["cases"][0]["strategies"]["baseline"]["counts"]["uncovered"] = 0
        with self.assertRaisesRegex(AssertionError, "Uncovered count differs"):
            audit(modified, self.models, self.selection)

    def test_false_positive_benefit(self):
        modified = copy.deepcopy(self.result)
        modified["new_full_coverage_observed"] = True
        with self.assertRaisesRegex(AssertionError, "Aggregate flag differs"):
            audit(modified, self.models, self.selection)


if __name__ == "__main__":
    unittest.main()
