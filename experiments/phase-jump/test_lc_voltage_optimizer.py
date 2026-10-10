"""Affine hardware maps and minimax derivatives, without running a search."""
import unittest

import numpy as np
from scipy.interpolate import BSpline

from run_constrained_ocp import SplineProblem, T
from run_scaled_ocp import ScaledProblem
from run_lc_voltage_envelope import CF, X1, R1, LCConstraintGrid
from run_power_feasibility import K, VG


class LCOptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scaled = ScaledProblem(SplineProblem())
        cls.times = np.array([0., .000073, .0011, .012, .06])

    def test_affine_maps_match_direct_physical_derivatives(self):
        p, times = self.scaled, self.times
        g = LCConstraintGrid(p, times, True, 19.43484)
        z = np.linspace(-1e-4, 1e-4, len(p.x0))
        spline = BSpline(p.knots*T, p.coefficients(z), 5)
        i, di, ddi, dddi = [spline(times, nu=n) for n in range(4)]
        c = p.case
        vc = VG+c["rt"]*i+c["lt"]*i@K.T+c["lt"]/c["wb"]*di
        dvc = c["rt"]*di+c["lt"]*di@K.T+c["lt"]/c["wb"]*ddi
        ddvc = c["rt"]*ddi+c["lt"]*ddi@K.T+c["lt"]/c["wb"]*dddi
        i1 = i+CF/c["wb"]*dvc+CF*vc@K.T
        di1 = di+CF/c["wb"]*ddvc+CF*dvc@K.T
        vi = vc+R1*i1+X1*i1@K.T+X1/c["wb"]*di1
        actual_i1, actual_vi = g.fields(z)
        np.testing.assert_allclose(actual_i1, i1, atol=2e-12)
        np.testing.assert_allclose(actual_vi, vi, atol=2e-10)

    def test_epigraph_analytic_jacobian(self):
        p = self.scaled
        g = LCConstraintGrid(p, self.times, True, 19.43484)
        y = np.r_[np.linspace(-1e-4, 1e-4, len(p.x0)), 1.]
        direction = np.linspace(-.03, .03, len(y))
        eps = 1e-6
        finite = (g.epigraph_values(y+eps*direction)-g.epigraph_values(y-eps*direction))/(2*eps)
        np.testing.assert_allclose(g.epigraph_jac(y)@direction, finite, atol=2e-8, rtol=2e-6)

    def test_constant_i1_but_not_voltage_endpoints(self):
        g = LCConstraintGrid(self.scaled, self.times, True, 19.43484)
        self.assertFalse(g.i1keep[0])
        self.assertFalse(g.i1keep[-1])
        self.assertGreater(np.max(np.abs(g.mat["vij"][0])), 1.)
        self.assertGreater(np.max(np.abs(g.mat["vij"][-1])), 0.)
        self.assertGreater(float(g.i1values(self.scaled.x0, False)[0]), 0.)

    def test_added_current_constraint_does_not_alter_original(self):
        p = self.scaled
        a = LCConstraintGrid(p, self.times, False, 19.43484)
        b = LCConstraintGrid(p, self.times, True, 19.43484)
        n = len(a.physical_values(p.x0))
        np.testing.assert_allclose(a.physical_values(p.x0), b.physical_values(p.x0)[:n])
        self.assertGreater(len(b.physical_values(p.x0)), n)


if __name__ == "__main__":
    unittest.main()
