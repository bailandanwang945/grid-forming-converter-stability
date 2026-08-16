from __future__ import annotations

import json
import unittest

import numpy as np

from backend.core.fig8_sensitivity import (
    Fig8SensitivityError,
    _classify_indices,
    _sample_indices,
    evaluate_fig8_sensitivity,
)
from backend.core.fig8_kernel import evaluate_fig8_case


class Fig8SensitivityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.study = evaluate_fig8_sensitivity()
        cls.cases = {
            case["case_id"]: case for case in cls.study["cases"]
        }

    def test_default_decision_reconstructs_both_pinned_cases_exactly(self) -> None:
        self.assertTrue(
            self.study["summary"]["baseline_reconstruction_exact"]
        )
        self.assertEqual(
            self.cases["fig8_D_0p05"]["baseline"]["uncovered_count"],
            75,
        )
        self.assertEqual(
            self.cases["fig8_D_0p5"]["baseline"]["uncovered_count"],
            0,
        )
        json.dumps(self.study, allow_nan=False)

    def test_sparse_frequency_grid_preserves_a_real_missed_band_counterexample(self) -> None:
        rows = {
            row["requested_point_count"]: row
            for row in self.cases["fig8_D_0p05"]["frequency_density"]
        }
        self.assertFalse(rows[9]["detects_uncovered_region"])
        self.assertEqual(rows[9]["uncovered_count"], 0)
        self.assertEqual(rows[9]["unobserved_full_grid_uncovered_points"], 75)
        self.assertTrue(rows[15]["detects_uncovered_region"])
        self.assertEqual(rows[15]["uncovered_count"], 1)
        self.assertEqual(rows[1000]["uncovered_count"], 75)
        self.assertAlmostEqual(
            rows[1000]["first_uncovered_frequency_hz"],
            0.4985373463873894,
            places=14,
        )
        self.assertAlmostEqual(
            rows[1000]["last_uncovered_frequency_hz"],
            1.6451905877536626,
            places=14,
        )

    def test_stable_case_never_gains_an_uncovered_sample(self) -> None:
        self.assertTrue(
            self.study["summary"][
                "stable_case_remains_covered_in_all_tested_settings"
            ]
        )
        stable = self.cases["fig8_D_0p5"]
        for study_name in (
            "frequency_density",
            "decision_tolerance",
            "common_matrix_scale",
        ):
            self.assertTrue(
                all(
                    row["uncovered_count"] == 0
                    for row in stable[study_name]
                )
            )

    def test_tested_tolerances_and_common_scales_do_not_change_coverage(self) -> None:
        self.assertTrue(
            self.study["summary"]["common_scale_invariant_on_tested_range"]
        )
        for case in self.study["cases"]:
            self.assertTrue(
                all(
                    row["coverage_mismatch_from_default"] == 0
                    for row in case["decision_tolerance"]
                )
            )
            self.assertTrue(
                all(
                    row["coverage_mismatch_from_unit_scale"] == 0
                    for row in case["common_matrix_scale"]
                )
            )

    def test_subgrid_is_deterministic_unique_and_endpoint_inclusive(self) -> None:
        indices = _sample_indices(1000, 31)
        self.assertEqual(indices.size, 31)
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 999)
        self.assertTrue(np.all(np.diff(indices) > 0))
        np.testing.assert_array_equal(indices, _sample_indices(1000, 31))

    def test_invalid_contracts_are_rejected(self) -> None:
        with self.assertRaisesRegex(Fig8SensitivityError, "点数"):
            _sample_indices(1000, 1)
        scan = evaluate_fig8_case("fig8_D_0p05")["frequency_scan"]
        with self.assertRaisesRegex(Fig8SensitivityError, "容差"):
            _classify_indices(
                scan,
                [0],
                gain_relative_tolerance=0.0,
                phase_tolerance_rad=1.0e-10,
            )
        with self.assertRaisesRegex(Fig8SensitivityError, "尺度"):
            _classify_indices(
                scan,
                [0],
                gain_relative_tolerance=1.0e-10,
                phase_tolerance_rad=1.0e-10,
                common_matrix_scale=-1.0,
            )


if __name__ == "__main__":
    unittest.main()
