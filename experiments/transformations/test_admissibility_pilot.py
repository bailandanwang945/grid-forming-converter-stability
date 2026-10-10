"""Small independent checks; not an independent experimental reproduction."""

import unittest
import numpy as np
from run_admissibility_pilot import (
    coefficients,
    cutoff_limit,
    direct_determinant,
    f_matrix,
    root_status,
    routh_status,
    diagnostic,
)


class AdmissibilityTests(unittest.TestCase):
    def test_known_quartics(self):
        self.assertEqual(routh_status([1, 4, 6, 4, 1])[0], "strict-lhp-zeros")
        self.assertEqual(routh_status([1, -4, 6, -4, 1])[0], "rhp-zero")
        self.assertEqual(routh_status([1, 2, 2, 2, 1])[0], "critical")

    def test_v_one_analytic_limit(self):
        r, x = 0.01, 0.1
        expected = r * 2 * np.pi * 50 / np.hypot(r, x)
        self.assertAlmostEqual(cutoff_limit(1, r, x), expected, places=12)

    def test_degenerate_inputs_rejected(self):
        for args in [
            (0, 0.01, 0.1, 50),
            (1, 0, 0.1, 50),
            (1, 0.01, 0, 50),
            (1, 0.01, 0.1, 0),
            (1, -1, 0.1, 50),
            (np.nan, 0.01, 0.1, 50),
            (1, 0.01, np.inf, 50),
        ]:
            with self.assertRaises(ValueError):
                cutoff_limit(*args)
        for wc in [0, -1, np.inf, np.nan]:
            with self.assertRaises(ValueError):
                coefficients(1, 0.01, 0.1, wc)

    def test_direct_matrix_determinant(self):
        for v in [0.8, 1, 1.2]:
            wc = cutoff_limit(v, 0.01, 0.1) * 0.8
            coef = direct_determinant(v, 0.01, 0.1, wc)
            for s in [1 + 2j, -3 + 7j, 100j]:
                factor = 0.0101 * v**2 * (s + wc) ** 2
                actual = -np.linalg.det(f_matrix(s, v, 0.01, 0.1, wc)) * factor
                self.assertLess(abs(actual - np.polyval(coef, s)) / abs(actual), 1e-12)

    def test_v_nonunit_boundary(self):
        for v in [0.8, 1, 1.2]:
            limit = cutoff_limit(v, 0.01, 0.1)
            for ratio, label in [
                (0.9, "strict-lhp-zeros"),
                (1, "critical"),
                (1.1, "rhp-zero"),
            ]:
                coef = coefficients(v, 0.01, 0.1, limit * ratio)
                self.assertEqual(root_status(np.roots(coef)), label)
                self.assertEqual(routh_status(coef)[0], label)

    def test_no_generic_jnet_cancellation_in_diagnostic(self):
        data = diagnostic()
        self.assertEqual(
            [r["fZeroStatus"] for r in data], ["strict-lhp-zeros", "rhp-zero"]
        )
        self.assertGreater(data[1]["sampledMinimumSingularValue"], 0)
        self.assertEqual(len(data[1]["rhpZeroProbes"]), 2)
        for probe in data[1]["rhpZeroProbes"]:
            self.assertLess(probe["bracketConditionNumber"], 1e8)
            self.assertLess(probe["jnetRelativeMinimumSingularValue"], 1e-10)
            np.testing.assert_allclose(
                probe["successiveInverseNormRatios"], [10, 10], rtol=0.02
            )


if __name__ == "__main__":
    unittest.main()
