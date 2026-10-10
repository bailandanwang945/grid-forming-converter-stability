"""Equation and extrema regressions for the fixed quintic trajectory family."""
import unittest

import numpy as np
from numpy.polynomial import Polynomial as Poly

from check_c1_repair import extrema, rotate, trajectory, vector_value
from run_power_feasibility import K, VG, build_case


class C1RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = build_case(60., "poi")

    def test_polynomial_stationary_extrema(self):
        lower, upper = extrema(Poly([0, 1, -1]))
        self.assertAlmostEqual(lower, 0)
        self.assertAlmostEqual(upper, .25)
        self.assertEqual(extrema(Poly([2])), (2., 2.))

    def test_endpoint_voltage_and_derivatives(self):
        c = self.case
        for duration in [.001, .002, .005, .01, .02, .04]:
            i, u = trajectory(c, duration)
            du = [p.deriv() / duration for p in u]
            np.testing.assert_allclose(vector_value(i, 0), c["i0"], atol=1e-12)
            np.testing.assert_allclose(vector_value(i, 1), c["iss"], atol=1e-12)
            np.testing.assert_allclose(vector_value(u, 0), c["frozen"], atol=1e-12)
            np.testing.assert_allclose(vector_value(du, 0), np.zeros(2), atol=1e-8)
            np.testing.assert_allclose(vector_value(du, 1), np.zeros(2), atol=1e-8)

    def test_rl_equation_and_poi_energy_identity(self):
        c, duration = self.case, .005
        i, u = trajectory(c, duration)
        di = [p.deriv() / duration for p in i]
        for t in np.linspace(0, 1, 17):
            current, voltage, derivative = vector_value(i, t), vector_value(u, t), vector_value(di, t)
            direct = c["wb"] / c["lt"] * (voltage - VG - c["rt"] * current) - c["wb"] * K @ current
            np.testing.assert_allclose(derivative, direct, atol=1e-10)
            poi = c["alpha"] * voltage + c["beta"] * VG + c["correction"] * current
            balance = current[0] + c["rg"] * np.dot(current, current) + c["lg"] / c["wb"] * np.dot(current, derivative)
            self.assertAlmostEqual(np.dot(poi, current), balance, places=11)

    def test_complete_lc_equations_and_initial_current_continuity(self):
        c, duration, cf, x1, r1 = self.case, .002, .02, .1, .01
        i, u = trajectory(c, duration)
        du = [p.deriv() / duration for p in u]
        ku = rotate(u)
        i1 = [i[j] + cf / c["wb"] * du[j] + cf * ku[j] for j in range(2)]
        di1, ki1 = [p.deriv() / duration for p in i1], rotate(i1)
        u1 = [u[j] + r1 * i1[j] + x1 * ki1[j] + x1 / c["wb"] * di1[j] for j in range(2)]
        expected_initial = c["i0"] + cf * K @ c["frozen"]
        np.testing.assert_allclose(vector_value(i1, 0), expected_initial, atol=1e-12)
        for t in np.linspace(0, 1, 17):
            grid_i, capacitor_u, inv_i, inv_u = [vector_value(p, t) for p in (i, u, i1, u1)]
            rhs_u = c["wb"] / cf * (inv_i - grid_i) - c["wb"] * K @ capacitor_u
            rhs_i1 = c["wb"] / x1 * (inv_u - capacitor_u - r1 * inv_i) - c["wb"] * K @ inv_i
            np.testing.assert_allclose(vector_value(du, t), rhs_u, atol=1e-9)
            np.testing.assert_allclose(vector_value(di1, t), rhs_i1, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
