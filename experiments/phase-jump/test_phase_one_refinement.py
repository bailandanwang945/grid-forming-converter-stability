"""Tests for normalization and constraint-only grid refinement."""
import unittest

import numpy as np

from run_constrained_ocp import SplineProblem
from run_scaled_ocp import ScaledProblem
from run_phase_one_refinement import ConstraintGrid, refinement_points


class TestPhaseOneRefinement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scaled = ScaledProblem(SplineProblem())

    def test_zero_slack_preserves_constraint_signs(self):
        p = self.scaled
        for hard in [False, True]:
            g = ConstraintGrid(p, p.times, hard)
            np.testing.assert_allclose(g.raw(p.x0), p.base.constraints(p.base.x0, hard), atol=1e-14)
            np.testing.assert_array_equal(g.values(p.x0) >= 0, g.raw(p.x0)[g.keep] >= 0)
            y = np.r_[p.x0, 0.]
            np.testing.assert_allclose(g.slack_values(y), g.values(p.x0))

    def test_constraint_jacobian(self):
        p = self.scaled
        g = ConstraintGrid(p, np.array([0., .000073, .0049, .012, .06]), True)
        z = np.linspace(-.0001, .0001, len(p.x0))
        direction = np.linspace(-.05, .05, len(z))
        eps = 1e-6
        finite = (g.values(z+eps*direction)-g.values(z-eps*direction))/(2*eps)
        np.testing.assert_allclose(g.jacobian(z) @ direction, finite, atol=2e-8, rtol=2e-6)
        np.testing.assert_array_equal(g.slack_jacobian(np.r_[z, .3])[:, -1], 1.)

    def test_refinement_does_not_change_objective(self):
        p = self.scaled
        before = p.objective(p.x0)
        old_times = p.base.times.copy()
        fine = np.unique(np.r_[p.times, .000073, .001231, .003987])
        g = ConstraintGrid(p, fine, True)
        self.assertEqual(g.values(p.x0).size, 3*len(fine)-6)
        self.assertEqual(p.objective(p.x0), before)
        np.testing.assert_array_equal(p.base.times, old_times)

    def test_fixed_violated_constraint_rejected(self):
        p = ScaledProblem(SplineProblem())
        p.base.case["ppre"] = 100.
        with self.assertRaisesRegex(ValueError, "fixed physical"):
            ConstraintGrid(p, p.times, True)

    def test_segment_times_include_all_required_fields(self):
        rows = [dict(current_peak_at_s=.001, voltage_peak_at_s=.002, minimum_power_at_s=.003),
                dict(current_peak_at_s=.004, voltage_peak_at_s=.004, minimum_power_at_s=.005)]
        np.testing.assert_array_equal(refinement_points(rows, False), [.001, .002, .004])
        np.testing.assert_array_equal(refinement_points(rows, True), [.001, .002, .003, .004, .005])


if __name__ == "__main__":
    unittest.main()
