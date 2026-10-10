import unittest

import numpy as np

from lc_connected_coordinates import ConnectedScaledProblem
from lc_conic_voltage_objective import build_objective_subproblem, objective_quadratic
from run_constrained_ocp import SplineProblem
from run_scaled_ocp import ScaledProblem


class VoltageObjectiveTests(unittest.TestCase):
    def setUp(self):
        old = ScaledProblem(SplineProblem())
        self.p = ConnectedScaledProblem(old, old.x0)
        self.ref = np.linspace(-.01, .01, 20)

    def test_quadratic_matches_original_objective_and_gradient(self):
        H, q, constant = objective_quadratic(self.p, self.ref)
        d = np.linspace(.003, -.003, 20)
        expected = self.p.objective(self.ref+d)
        self.assertAlmostEqual(.5*d @ H @ d+q @ d+constant, expected, places=12)
        np.testing.assert_allclose(q, self.p.gradient(self.ref), atol=2e-12)

    def test_hard_power_adds_only_power_cones_no_slack(self):
        times = np.array([0., .003, .017, .06])
        a = build_objective_subproblem(self.p, times, self.ref, False)
        b = build_objective_subproblem(self.p, times, self.ref, True)
        self.assertEqual(a.q.shape, (20,))
        self.assertEqual(a.A.shape[1], 20)
        np.testing.assert_allclose(a.P.toarray(), b.P.toarray())
        np.testing.assert_allclose(a.q, b.q)
        np.testing.assert_allclose(a.A.toarray(), b.A[:a.A.shape[0]].toarray())
        self.assertEqual(len(b.cone_specs)-len(a.cone_specs), len(times))


if __name__ == "__main__":
    unittest.main()
