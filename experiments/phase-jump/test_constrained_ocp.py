"""Implementation checks only; do not run or tune the two-strategy experiment."""
import unittest

import numpy as np

from run_constrained_ocp import K, SplineProblem, T, VG, grid


class ConstrainedOcpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = SplineProblem()

    def test_endpoint_matching(self):
        row = self.p.check(self.p.x0, self.p.times)
        self.assertTrue(row["endpoint_pass"], row["endpoint_errors"])

    def test_objective_gradient(self):
        x = self.p.x0.copy()
        h = 1e-6
        numeric = np.array([(self.p.objective(x+h*np.eye(len(x))[j])-self.p.objective(x-h*np.eye(len(x))[j]))/(2*h) for j in range(len(x))])
        np.testing.assert_allclose(self.p.gradient(x), numeric, rtol=2e-7, atol=1e-7)

    def test_constraint_jacobian_both_strategies(self):
        x = self.p.x0.copy()
        h = 1e-6
        for hard in [False, True]:
            numeric = np.column_stack([(self.p.constraints(x+h*np.eye(len(x))[j], hard)-self.p.constraints(x-h*np.eye(len(x))[j], hard))/(2*h) for j in range(len(x))])
            np.testing.assert_allclose(self.p.constraint_jacobian(x, hard), numeric, rtol=1e-6, atol=1e-7)

    def test_line_and_power_balance(self):
        p, c = self.p, self.p.case
        i, v, _ = p.fields(p.x0)
        spline = p.basis(p.times/T, nu=1)/T @ p.coefficients(p.x0)
        rhs = c["wb"]/c["lt"]*(v-VG-c["rt"]*i)-c["wb"]*(i@K.T)
        np.testing.assert_allclose(rhs, spline, atol=2e-11, rtol=2e-11)
        poi = c["alpha"]*v+c["beta"]*VG+c["correction"]*i
        power = np.sum(poi*i, axis=1)
        identity = i[:, 0]+c["rg"]*np.sum(i*i, axis=1)+c["lg"]/c["wb"]*np.sum(i*spline, axis=1)
        np.testing.assert_allclose(power, identity, atol=2e-12, rtol=2e-12)

    def test_grids_and_known_failure(self):
        self.assertGreater(len(grid(True)), len(grid()))
        for t in [0., T]:
            self.assertIn(t, grid())
        x = self.p.x0+100.
        self.assertLess(self.p.constraints(x, True).min(), -1.)


if __name__ == "__main__":
    unittest.main()
