"""Constant-row elimination must not relax any adjustable constraint."""
import unittest

import numpy as np

from run_constrained_ocp import SplineProblem
from run_repaired_ocp import RepairedProblem


class RepairTests(unittest.TestCase):
    def test_removed_rows_are_fixed_for_different_free_variables(self):
        base = SplineProblem()
        repaired = RepairedProblem(base)
        for hard in [False, True]:
            for z in [np.zeros(base.nvar), np.linspace(-.001, .001, base.nvar)]:
                x = repaired.physical(z)
                full = base.constraints(x, hard)
                np.testing.assert_array_equal(repaired.constraints(z, hard), full[repaired.keep[hard]])
                np.testing.assert_allclose(full[~repaired.keep[hard]], repaired.removed[str(hard)]["original_residuals"], atol=1e-13)
                np.testing.assert_array_equal(base.constraint_jacobian(x, hard)[~repaired.keep[hard]], 0.)

    def test_violated_fixed_boundary_is_not_ignored(self):
        base = SplineProblem()
        base.fixed[0] *= 2
        base.train = base.matrices(base.times)
        with self.assertRaisesRegex(ValueError, "actually violated fixed"):
            RepairedProblem(base)


if __name__ == "__main__":
    unittest.main()
