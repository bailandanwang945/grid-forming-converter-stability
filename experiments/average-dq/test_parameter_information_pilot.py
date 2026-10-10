"""Analytical regression tests; no physical-model or production-API claims."""
import itertools
import unittest

import numpy as np

from run_parameter_information_pilot import Evaluator, inertia_check, spectral_label


class ToyFamily:
    @staticmethod
    def raw(v, i):
        return np.array([[v - 1.1]])


class PilotTests(unittest.TestCase):
    def test_stable_family(self):
        self.assertEqual(inertia_check([-np.eye(2)], -np.eye(2))['label'], 'stable')

    def test_unstable_inertia(self):
        a = np.diag([-1., 2.])
        result = inertia_check([a], a)
        self.assertEqual(result['label'], 'unstable')
        self.assertEqual(result['negative_inertia'], 1)

    def test_corner_and_center_shortcut_rejected(self):
        def a(t):
            return np.array([[-1., 8*t], [2-4*t, -1.]])
        self.assertTrue(all(spectral_label(a(t))[0] == 'stable' for t in (0, .5, 1)))
        self.assertEqual(spectral_label(a(.25))[0], 'unstable')
        self.assertEqual(inertia_check([a(0), a(1)], a(.5))['label'], 'pending')

    def test_point_boundary_is_pending(self):
        self.assertEqual(spectral_label(np.zeros((1, 1)))[0], 'pending')

    def test_point_tolerance_and_inertia_have_different_semantics(self):
        # The pilot's point reference reserves a 1e-5 boundary band; common-P
        # checks ordinary strict stability. Do not treat this band as a refutation.
        for sign, label in ((-1, 'stable'), (1, 'unstable')):
            a = sign*1e-6*np.eye(2)
            self.assertEqual(spectral_label(a)[0], 'pending')
            self.assertEqual(inertia_check([a], a)['label'], label)

    def test_exhausted_information_may_remain_pending(self):
        ev = Evaluator(ToyFamily(), (1.1,))
        bounds = (1.1, 1.1, 1.1, 1.1)
        self.assertEqual(ev.optimal(bounds), (0., None))
        self.assertEqual(ev.run('exact-dp', bounds, (1.1, 1.1))['label'], 'pending')

    def test_optimal_can_stop_after_one_query(self):
        values = tuple(np.linspace(.5, 2, 5))
        ev = Evaluator(ToyFamily(), values)
        bounds = (.5, 2., .5, 2.)
        self.assertEqual(ev.optimal(bounds), (1., 0))
        for v, i in itertools.product(values, repeat=2):
            for method in ('exact-dp', 'slice-lookahead', 'fixed-v'):
                self.assertEqual(ev.run(method, bounds, (v, i))['requests'], 1)
            self.assertEqual(ev.run('fixed-i', bounds, (v, i))['requests'], 2)

    def test_optimal_zero_queries(self):
        ev = Evaluator(ToyFamily(), (.5, .75, 1.))
        self.assertEqual(ev.optimal((.5, 1., .5, 1.)), (0., None))

    def test_ec2_matches_explicit_weighted_edge_removal(self):
        values = (0., 1., 2.)
        ev = Evaluator(ToyFamily(), values)
        grid = [((v, i), 'stable' if v+i < 2 else 'unstable')
                for v, i in itertools.product(values, repeat=2)]
        for axis in (0, 1):
            edges = [(a, b) for a, b in itertools.combinations(grid, 2) if a[1] != b[1]]
            weight = 1 / len(grid)**2
            removed = sum((sum(a[0][axis] != z or b[0][axis] != z for a, b in edges)
                           * weight / len(values)) for z in values)
            self.assertAlmostEqual(ev.score('ec2', (0., 2., 0., 2.), axis, grid), removed)


if __name__ == '__main__':
    unittest.main()
