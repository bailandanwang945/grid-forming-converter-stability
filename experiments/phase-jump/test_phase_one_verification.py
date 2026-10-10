import unittest

from run_constrained_ocp import SplineProblem, T
from verify_phase_one_refinement import endpoint_audit, combined_constraint_check


class TestIndependentEndpoints(unittest.TestCase):
    def test_frozen_endpoint_conditions(self):
        p = SplineProblem()
        audit = endpoint_audit(p.knots*T, p.coefficients(p.x0), p.case)
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["units"]["start_ddi"], "p.u./s^2")
        self.assertEqual(audit["units"]["start_dv"], "p.u./s")

    def test_corrupted_fixed_endpoint_is_rejected(self):
        p = SplineProblem()
        coef = p.coefficients(p.x0)
        coef[-1, 0] += .001
        audit = endpoint_audit(p.knots*T, coef, p.case)
        self.assertFalse(audit["passed"])
        self.assertGreater(audit["residuals"]["end_i"], 1e-4)

    def test_dense_contradiction_rejects_candidate(self):
        case = dict(frozen=[1., 0.], ppre=1.)
        summary = dict(current_peak_pu=1.2, voltage_peak_pu=1., minimum_power_pu=1.)
        dense = dict(current_peak_pu=1.4, voltage_peak_pu=1., power_min_pu=1.,
                     current_pass=False, voltage_pass=True, power_pass=True)
        checked = combined_constraint_check(summary, dense, dict(passed=True), case, True)
        self.assertFalse(checked[3])
        self.assertFalse(checked[4])


if __name__ == "__main__":
    unittest.main()
