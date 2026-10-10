"""Independent tests of conic signs, shifts and quadratic power cone."""
import unittest

import numpy as np

from lc_conic_subproblem import build_subproblem
from power_inner_approximation import make_inner_approximation
from run_constrained_ocp import SplineProblem
from run_lc_voltage_envelope import LCConstraintGrid
from run_scaled_ocp import ScaledProblem


class ConicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scaled = ScaledProblem(SplineProblem())
        cls.times = np.array([0., .000073, .0011, .012, .06])
        cls.ref = np.linspace(-1e-4, 1e-4, len(cls.scaled.x0))
        cls.problem = build_subproblem(cls.scaled, cls.times, cls.ref)

    def test_norm_cones_match_physical_fields_and_slack(self):
        p = self.problem
        d = np.linspace(1e-5, -1e-5, len(self.ref))
        slack = .001
        vector = p.b-p.A @ np.r_[d, slack]
        g = LCConstraintGrid(self.scaled, self.times, True, 1.2)
        i1, vi = g.fields(self.ref+d)
        physical_x = self.scaled.physical(self.ref+d)
        i, v, _ = self.scaled.base.fields(physical_x, self.scaled.base.matrices(self.times))
        actual = dict(i=i, v=v, i1=i1, vi=vi)
        for group in p.groups:
            if group["tag"].startswith(("power:", "slack")):
                continue
            key, index = group["tag"].split(":")
            block = vector[group["start"]:group["end"]]
            np.testing.assert_allclose(block[1:], actual[key][int(index)], atol=3e-12)
            self.assertAlmostEqual(block[0], p.diagnostics["physical_limits"][key]*(1+slack), places=14)

    def test_power_soc_equivalence_and_coordinate_shift(self):
        p = self.problem
        inner = make_inner_approximation(p.power, self.ref)
        for scale in [0., 1e-4, .01]:
            d = np.linspace(-scale, scale, len(self.ref))
            slack = .003
            vec = p.b-p.A @ np.r_[d, slack]
            lower = inner.value(self.ref+d)-self.scaled.case["ppre"]+slack
            for group in p.groups:
                if not group["tag"].startswith("power:"):
                    continue
                j = int(group["tag"].split(":")[1])
                block = vec[group["start"]:group["end"]]
                np.testing.assert_allclose((block[0]**2-np.dot(block[1:], block[1:]))/4, lower[j], atol=4e-13)
                self.assertEqual(block[0] >= np.linalg.norm(block[1:]), lower[j] >= 0)

    def test_objective_and_nonnegative_slack(self):
        p = self.problem
        y = np.r_[np.ones(len(self.ref))*.03, -.001]
        objective = .5*y @ p.P @ y+p.q @ y
        self.assertAlmostEqual(objective, y[-1]+1e-8*np.dot(y[:-1], y[:-1]))
        self.assertEqual(p.residuals(y[:-1], y[-1])[-1]["margin"], -.001)

    def test_invalid_inputs(self):
        for times in [[], [-.001], [.061], [float("nan")]]:
            with self.assertRaises(ValueError):
                build_subproblem(self.scaled, times, self.ref)
        with self.assertRaises(ValueError):
            build_subproblem(self.scaled, self.times, self.ref, voltage_limit=0.)

    def test_solver_returns_primal_candidate_for_relaxed_problem(self):
        try:
            import clarabel  # noqa: F401
        except ImportError:
            self.skipTest("Run solver smoke test in the isolated research environment")
        from lc_conic_subproblem import solve
        x, state = solve(self.problem, 5.)
        self.assertIsNotNone(x, state)
        self.assertIn(state["status"], ["Solved", "AlmostSolved"])
        self.assertGreaterEqual(min(r["margin"] for r in self.problem.residuals(x[:-1], x[-1])), -1e-7)


if __name__ == "__main__":
    unittest.main()
