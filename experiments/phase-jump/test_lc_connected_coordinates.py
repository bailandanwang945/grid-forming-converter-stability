"""Coordinate algebra and direct spline checks, without conic optimization."""
import unittest

import numpy as np

from lc_connected_coordinates import ConnectedScaledProblem, endpoint_input_audit
from lc_conic_subproblem import build_subproblem
from run_constrained_ocp import SplineProblem, T
from run_lc_voltage_envelope import lc_matrices
from run_scaled_ocp import ScaledProblem


class ConnectedCoordinatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = ScaledProblem(SplineProblem())
        cls.seed = np.linspace(-.02, .02, len(cls.old.x0))
        cls.p = ConnectedScaledProblem(cls.old, cls.seed)

    def test_rank_projection_and_orthogonality(self):
        p = self.p
        self.assertEqual(p.diagnostics["endpoint_rank"], 4)
        self.assertEqual(len(p.x0), 20)
        np.testing.assert_allclose(p.E@p.anchor, p.target, atol=1e-8)
        np.testing.assert_allclose(p.null_basis.T@p.null_basis, np.eye(20), atol=1e-12)
        np.testing.assert_allclose(p.null_basis.T@(p.anchor-self.seed), 0., atol=1e-12)
        self.assertIsNot(p.base, self.old.base)
        np.testing.assert_array_equal(self.old.base.x0, SplineProblem().x0)

    def test_random_coordinates_keep_endpoint_inputs(self):
        rng = np.random.default_rng(491)
        for _ in range(3):
            y = rng.normal(size=20)*.1
            audit = endpoint_input_audit(self.p.knots*T, self.p.coefficients(y), self.p.case)
            self.assertTrue(audit["input_endpoint_pass"], audit)

    def test_affine_fields_match_physical_spline(self):
        p = self.p
        y = np.linspace(-.03, .03, 20)
        old_z = p.original_coordinates(y)
        np.testing.assert_allclose(p.physical(y), self.old.physical(old_z), atol=1e-12)
        np.testing.assert_allclose(p.coefficients(y), self.old.coefficients(old_z), atol=1e-12)
        times = np.array([0., .003, .021, T])
        m = lc_matrices(p.base, times)
        for key in ["i1", "vi"]:
            affine = m[key+"0"]+m[key+"j"]@p.base.x0+(m[key+"j"]@p.transform)@y
            physical = m[key+"0"]+m[key+"j"]@p.physical(y)
            np.testing.assert_allclose(affine, physical, atol=1e-10)

    def test_power_map_and_conic_dimensions(self):
        times = np.array([0., .002, .017, T])
        y = np.linspace(-.01, .01, 20)
        newer = build_subproblem(self.p, times, y)
        older = build_subproblem(self.old, times, self.p.original_coordinates(y))
        np.testing.assert_allclose(newer.power.value(y), older.power.value(self.p.original_coordinates(y)), atol=1e-11)
        self.assertEqual(newer.q.shape, (21,))
        self.assertEqual(newer.A.shape[1], 21)

    def test_invalid_inputs(self):
        for seed in [np.zeros(3), np.ones(24)*np.nan]:
            with self.assertRaises(ValueError):
                ConnectedScaledProblem(self.old, seed)
        with self.assertRaises(ValueError):
            self.p.physical(np.zeros(24))
        with self.assertRaises(ValueError):
            endpoint_input_audit(self.p.knots*T, np.zeros((2, 2)), self.p.case)


if __name__ == "__main__":
    unittest.main()
