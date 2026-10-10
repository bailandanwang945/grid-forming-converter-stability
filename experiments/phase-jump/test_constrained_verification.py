"""Independent verifier tests without optimization or saved-result dependencies."""
import unittest

import numpy as np
from numpy.polynomial import Polynomial as Poly
from scipy.interpolate import make_interp_spline

from verify_constrained_ocp import extrema, polynomial_audit


class VerificationTests(unittest.TestCase):
    def test_extrema_between_grid_points(self):
        minimum, maximum, at, _ = extrema(Poly([.04, -.4, 1]))
        self.assertAlmostEqual(minimum, 0)
        self.assertAlmostEqual(at, .2)
        self.assertAlmostEqual(maximum, .64)

    def test_constant_extrema(self):
        self.assertEqual(extrema(Poly([3]))[:2], (3., 3.))

    def test_piecewise_conversion_on_steady_equilibrium(self):
        wb, lt, rt = 2 * np.pi * 60, .45, .075
        current = np.array([1., 0.])
        spline = make_interp_spline(np.linspace(0, .06, 8), np.tile(current, (8, 1)), k=5)
        case = dict(wb=wb, lt=lt, rt=rt, alpha=2/3, beta=1/3, correction=0.)
        summary, rows = polynomial_audit(spline.t, spline.c, case)
        self.assertTrue(rows)
        self.assertAlmostEqual(summary["current_peak_pu"], 1)
        self.assertAlmostEqual(summary["minimum_power_pu"], 1.05)
        self.assertAlmostEqual(summary["voltage_peak_pu"], np.hypot(1.075, .45))
        self.assertLess(summary["maximum_representation_difference"], 1e-9)


if __name__ == "__main__":
    unittest.main()
