"""A variable scaling must preserve physical fields and their derivatives."""
import unittest

import numpy as np

from run_constrained_ocp import SplineProblem
from run_scaled_ocp import ScaledProblem


class ScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = SplineProblem()
        cls.scaled = ScaledProblem(cls.base)

    def test_initial_physical_coefficients_identical(self):
        np.testing.assert_array_equal(self.scaled.coefficients(self.scaled.x0), self.base.coefficients(self.base.x0))

    def test_constraints_and_objective_are_same_problem(self):
        z = np.linspace(-.01, .01, self.base.nvar)
        x = self.scaled.physical(z)
        self.assertAlmostEqual(self.scaled.objective(z) * self.scaled.scale, self.base.objective(x), places=12)
        for hard in [False, True]:
            np.testing.assert_array_equal(self.scaled.constraints(z, hard), self.base.constraints(x, hard))

    def test_scaled_objective_gradient(self):
        z = np.linspace(-.01, .01, self.base.nvar)
        direction = np.linspace(.2, .8, self.base.nvar)
        h = 1e-5
        numerical = (self.scaled.objective(z + h * direction) - self.scaled.objective(z - h * direction)) / (2 * h)
        analytic = self.scaled.gradient(z) @ direction
        self.assertAlmostEqual(numerical, analytic, places=7)

    def test_scaled_constraint_gradient(self):
        z = np.linspace(-.01, .01, self.base.nvar)
        direction = np.linspace(.2, .8, self.base.nvar)
        h = 1e-5
        for hard in [False, True]:
            numerical = (self.scaled.constraints(z + h * direction, hard) - self.scaled.constraints(z - h * direction, hard)) / (2 * h)
            analytic = self.scaled.constraint_jacobian(z, hard) @ direction
            np.testing.assert_allclose(numerical, analytic, rtol=1e-6, atol=1e-7)


if __name__ == "__main__":
    unittest.main()
