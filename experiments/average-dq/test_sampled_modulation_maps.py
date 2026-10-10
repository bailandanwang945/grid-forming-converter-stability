"""Analytic regression tests for the isolated sampled-command model audit.

These verify numerical maps, not physical converter validity or novelty.
Run: python experiments/average-dq/test_sampled_modulation_maps.py
"""
from types import SimpleNamespace
import unittest

import numpy as np

from run_sampled_modulation_holdout import coordinates, transition
from run_sampled_modulation_pilot import lag_matrix


def scalar_embedding(a_scalar, feedback):
    a = -np.diag(np.arange(1.0, 15.0))
    a[0, 0] = a_scalar
    b = np.zeros((14, 2))
    b[0, 0] = 1.0
    f = np.zeros((2, 14))
    f[0, 0] = feedback
    return a, b, f


class SampledMapAnalyticTests(unittest.TestCase):
    def test_singular_plant_exact_hold_integral(self):
        a, b, f = scalar_embedding(0.0, -2.0)
        phi, e, gamma = transition(a, b, f, 0.3, 0)
        self.assertAlmostEqual(e[0, 0], 1.0)
        self.assertAlmostEqual(gamma[0, 0], 0.3)
        self.assertAlmostEqual(phi[0, 0], 0.4)

    def test_sampled_unstable_but_phase_matched_lag_stable(self):
        a, b, f = scalar_embedding(0.0, -3.0)
        ts = 1.0
        phi, _, _ = transition(a, b, f, ts, 0)
        self.assertAlmostEqual(phi[0, 0], -2.0)
        self.assertGreater(np.max(np.abs(np.linalg.eigvals(phi))), 1.0)
        self.assertLess(np.max(np.linalg.eigvals(lag_matrix(a, b, f, ts / 2)).real), 0)

    def test_reverse_stability_disagreement(self):
        a, b, f = scalar_embedding(1.0, -1.1)
        ts = 2.5
        phi, _, _ = transition(a, b, f, ts, 0)
        self.assertAlmostEqual(phi[0, 0], 1.1 - 0.1 * np.exp(ts))
        self.assertLess(np.max(np.abs(np.linalg.eigvals(phi))), 1.0)
        self.assertGreater(np.max(np.linalg.eigvals(lag_matrix(a, b, f, ts / 2)).real), 0)

    def test_one_step_uses_old_buffer_and_queues_start_state(self):
        a, b, f = scalar_embedding(-0.7, -2.0)
        phi, e, gamma = transition(a, b, f, 0.2, 1)
        x = np.linspace(-0.1, 0.2, 14)
        old = np.array([0.4, -0.3])
        actual = phi @ np.concatenate([x, old])
        expected = np.concatenate([e @ x + gamma @ old, f @ x])
        np.testing.assert_allclose(actual, expected, atol=1e-14)
        self.assertGreater(np.linalg.norm(actual[:14] - (e @ x + gamma @ (f @ x))), 0.01)

    def test_delay_scalar_polynomial_retains_memory_roots(self):
        a, b, f = scalar_embedding(0.0, -3.0)
        phi, _, _ = transition(a, b, f, 0.5, 1)
        roots = np.linalg.eigvals(phi[np.ix_([0, 14], [0, 14])])
        # mu^2 - mu + k*Ts = 0; removing the buffer would lose this instability.
        np.testing.assert_allclose(roots**2 - roots + 1.5, 0, atol=1e-14)
        self.assertGreater(np.max(np.abs(roots)), 1.0)
        self.assertEqual(phi.shape, (16, 16))

    def test_coordinate_sign_and_ideal_feedback_invariance(self):
        a, b, f = scalar_embedding(-0.7, -2.0)
        tau = 0.001
        state = np.zeros(16)
        state[14:] = [1.2, -0.4]
        model = SimpleNamespace(
            linearization=SimpleNamespace(closed_state_matrix=lag_matrix(a, b, f, tau)),
            parameters=SimpleNamespace(modulation_time_constant_s=tau),
            operating_point=SimpleNamespace(state=state),
        )
        cases, c = coordinates(model)
        ag, bg, fg = cases['global-synchronous-dq']
        np.testing.assert_allclose(c[:, 0], [0.4, 1.2])
        np.testing.assert_allclose(c[:, 1:], 0)
        np.testing.assert_allclose(ag, a - b @ c)
        np.testing.assert_allclose(fg, f + c)
        np.testing.assert_allclose(ag + bg @ fg, a + b @ f, atol=1e-14)

    def test_no_delay_low_frequency_first_order_coefficient(self):
        self._check_slow_first_order_coefficient(delay=0)

    def test_one_step_low_frequency_first_order_coefficient(self):
        self._check_slow_first_order_coefficient(delay=1)

    def _check_slow_first_order_coefficient(self, delay):
        a, b, f = scalar_embedding(-0.7, -2.0)
        ideal = -2.7
        expected_coefficient = -(delay + 0.5) * (-2.0) * ideal
        errors = []
        for ts in [1e-4, 5e-5]:
            phi, _, _ = transition(a, b, f, ts, delay)
            if delay:
                roots = np.linalg.eigvals(phi[np.ix_([0, 14], [0, 14])])
                slow = roots[np.argmin(np.abs(roots - 1))]
            else:
                slow = phi[0, 0]
            observed_coefficient = (np.log(slow).real / ts - ideal) / ts
            errors.append(abs(observed_coefficient - expected_coefficient))
        self.assertLess(errors[-1], 0.003 * abs(expected_coefficient))
        self.assertLess(errors[-1], errors[0])


if __name__ == '__main__':
    unittest.main()
