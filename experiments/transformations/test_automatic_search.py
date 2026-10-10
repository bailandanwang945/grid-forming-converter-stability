"""Checks for candidate generation, rational algebra and honest rejection."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from automatic_search import (BASELINE, BOUNDS, Candidate, Evaluator, fit_rl_shunt,
                              mutate, n_coefficients, network_n_coefficients, random_candidate, run)


class AutomaticSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluator = Evaluator()

    def test_invalid_candidates(self):
        for values in [(0, .1, .5), (.01, -1, .5), (.01, .1, np.nan),
                       (np.inf, .1, .5)]:
            with self.assertRaises(ValueError):
                Candidate(*values).validate()

    def test_generation_is_reproducible_and_bounded(self):
        a, b = np.random.default_rng(7), np.random.default_rng(7)
        for _ in range(20):
            candidate = random_candidate(a)
            self.assertEqual(candidate, random_candidate(b))
            child = mutate(candidate, a)
            self.assertEqual(child, mutate(candidate, b))
            values = np.array(list(child.__dict__.values()))
            self.assertTrue(np.all(values >= BOUNDS[:, 0]))
            self.assertTrue(np.all(values <= BOUNDS[:, 1]))

    def test_n_polynomial_matches_direct_matrix(self):
        for wc in [0.3, 3, 30]:
            z0, ln, _, _ = self.evaluator.rl["fig8_D_0p5"]
            coef, a, b = n_coefficients(self.evaluator.e, self.evaluator.c, z0, ln, wc)
            for s in [0j, 1 + 5j, 100j, -11 + 7j]:
                direct = (s + wc) * self.evaluator.e - wc * self.evaluator.c @ (z0 + s * ln * np.eye(2))
                np.testing.assert_allclose(direct, a * s + b, rtol=1e-13, atol=1e-13)
                np.testing.assert_allclose(np.linalg.det(direct), np.polyval(coef, s), rtol=1e-12)

    def test_shunt_n_polynomial_matches_direct_matrix(self):
        e, c = self.evaluator.e, self.evaluator.c
        z0, ln, g, _ = self.evaluator.rl["fig8_D_0p5"]
        for wc in [.3, 3, 30]:
            coef, parts, _ = network_n_coefficients(e, c, z0, ln, g, wc)
            for s in [0j, 1 + 5j, 100j, -11 + 7j]:
                z = z0 + s * ln * np.eye(2)
                direct = (s + wc) * e @ (g * z + np.eye(2)) - wc * c @ z
                np.testing.assert_allclose(direct, parts[0] + s * parts[1] + s**2 * parts[2], rtol=1e-13, atol=1e-13)
                np.testing.assert_allclose(np.linalg.det(direct), np.polyval(coef, s), rtol=1e-12)

    def test_supported_rl_only(self):
        case = self.evaluator.cases["fig8_D_0p5"]
        broken = case["network"].copy()
        broken[10, 0, 0] *= 1.01
        with self.assertRaises(ValueError):
            fit_rl_shunt(case["frequencies_hz"], broken, self.evaluator.wbase)

    def test_invalid_f_is_rejected_before_phase_evaluation(self):
        metrics = self.evaluator.evaluate(Candidate(.01, .1, 5.), "fig8_D_0p5", np.arange(10))
        self.assertEqual(metrics["status"], "rejected")
        self.assertIn("f_zeros", metrics["checks"]["rejected_by"])
        self.assertNotIn("coverage", metrics)

    def test_baseline_shape_matches_production(self):
        from backend.core import fig8_kernel as kernel
        for name, case in self.evaluator.cases.items():
            indices = np.array([0, 10, 80, 200, 999])
            _, jc, jn, residual, _ = self.evaluator.shape(Candidate(*BASELINE), name, indices)
            prod = kernel._build_shaped_responses(case["frequencies_hz"][indices],
                case["converter"][indices], case["network"][indices], self.evaluator.manifest)
            np.testing.assert_allclose(jc, prod[0], rtol=1e-13, atol=1e-13)
            np.testing.assert_allclose(jn, prod[1], rtol=1e-13, atol=1e-13)
            self.assertLess(residual, 1e-12)

    def test_single_g_check_can_reject_even_when_f_is_valid(self):
        # Higher operating current, not a modification of the author's fixture.
        old = self.evaluator.c.copy()
        try:
            self.evaluator.c = np.eye(2) * 20
            metrics = self.evaluator.prerequisites(Candidate(.01, .1, .5), "fig8_D_0p5")
            self.assertEqual(metrics["f_zeros"], "strict-lhp-zeros")
            self.assertIn("g_zeros", metrics["rejected_by"])
        finally:
            self.evaluator.c = old

    def test_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileExistsError):
                run(Path(folder))


if __name__ == "__main__":
    unittest.main()
