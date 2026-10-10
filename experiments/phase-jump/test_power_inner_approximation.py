"""Verify algebra against direct dq power, not against another optimizer."""
import unittest

import numpy as np

from power_inner_approximation import PowerQuadratic, expand_power, make_inner_approximation
from run_constrained_ocp import SplineProblem
from run_power_feasibility import VG


class PowerInnerTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(20261005)
        self.a, self.b = self.rng.normal(size=(2, 7, 2))
        self.A, self.B = self.rng.normal(size=(2, 7, 2, 5))
        self.z = self.rng.normal(size=5)
        self.ref = self.rng.normal(size=5)
        self.power = expand_power(self.a, self.A, self.b, self.B, VG, .7, .3, .09)
        self.inner = make_inner_approximation(self.power, self.ref)

    def test_direct_power_including_all_correction_terms(self):
        i = self.a + self.A @ self.z
        v = self.b + self.B @ self.z
        expected = np.sum((.7*v+.3*VG+.09*i)*i, axis=1)
        np.testing.assert_allclose(self.power.value(self.z), expected, atol=2e-14)

    def test_exact_gap_and_lower_bound(self):
        for z in self.rng.normal(size=(20, 5)):
            gap = self.power.value(z)-self.inner.value(z)
            np.testing.assert_allclose(gap, self.inner.gap(z), atol=4e-14)
            self.assertGreaterEqual(float(np.min(gap)), -4e-14)

    def test_reference_value_and_gradient_agree(self):
        np.testing.assert_allclose(self.inner.value(self.ref), self.power.value(self.ref), atol=2e-14)
        np.testing.assert_allclose(self.inner.gradient(self.ref), self.power.gradient(self.ref), atol=2e-14)

    def test_concavity_and_gradient(self):
        y = self.rng.normal(size=5)
        mix = .37*self.z + .63*y
        residual = self.inner.value(mix) - (.37*self.inner.value(self.z)+.63*self.inner.value(y))
        self.assertGreaterEqual(float(np.min(residual)), -3e-14)
        direction = self.rng.normal(size=5)
        eps = 1e-6
        finite = (self.inner.value(self.z+eps*direction)-self.inner.value(self.z-eps*direction))/(2*eps)
        np.testing.assert_allclose(finite, self.inner.gradient(self.z) @ direction, atol=2e-8)

    def test_small_signed_eigenvalues_not_discarded(self):
        Q = np.diag([1., -1e-12, 2e-12])[None]
        power = PowerQuadratic(Q, np.zeros((1, 3)), np.zeros(1))
        inner = make_inner_approximation(power, np.zeros(3))
        np.testing.assert_allclose(inner.positive-inner.negative, Q, atol=1e-25)
        self.assertEqual(inner.negative[0, 1, 1], 1e-12)
        self.assertFalse(inner.diagnostics["small_eigenvalues_discarded"])

    def test_actual_spline_power_and_jacobian(self):
        p = SplineProblem()
        m, c = p.train, p.case
        power = expand_power(m["i0"], m["ij"], m["v0"], m["vj"], VG, c["alpha"], c["beta"], c["correction"])
        x = p.x0 + self.rng.normal(scale=.001, size=p.nvar)
        n = len(p.times)
        np.testing.assert_allclose(power.value(x)-c["ppre"], p.constraints(x, True)[2*n:], atol=2e-13)
        np.testing.assert_allclose(power.gradient(x), p.constraint_jacobian(x, True)[2*n:], atol=3e-13)
        inner = make_inner_approximation(power, p.x0)
        np.testing.assert_allclose(power.value(x)-inner.value(x), inner.gap(x), atol=3e-13)

    def test_bad_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            expand_power(self.a, self.A, self.b, self.B, VG, float("nan"), .3, 0.)
        with self.assertRaises(ValueError):
            make_inner_approximation(self.power, np.zeros(4))
        Q = self.power.Q.copy()
        Q[0, 0, 1] += .01
        with self.assertRaises(ValueError):
            make_inner_approximation(PowerQuadratic(Q, self.power.q, self.power.r), self.ref)


if __name__ == "__main__":
    unittest.main()
