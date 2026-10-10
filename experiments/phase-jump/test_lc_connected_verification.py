"""Reject altered candidate provenance and broken endpoint input."""
import unittest

from lc_connected_coordinates import ConnectedScaledProblem, endpoint_input_audit
from run_constrained_ocp import SplineProblem, T
from run_scaled_ocp import ScaledProblem
from verify_lc_connected_conic import verify_step_coordinates


class ConnectedVerificationTests(unittest.TestCase):
    def test_coordinate_provenance_and_altered_coefficients(self):
        data = dict(anchor_original_scaled=[.1, .2], nullspace=[[1., 0.], [0., 1.]],
                    original_physical_origin=[.5, .3], original_transform=[[2., 0.], [0., 3.]],
                    free_coefficient_indices=[0])
        step = dict(reference_connected=[.01, .02], increment_connected=[.02, .01], coefficients=[[.76, .99]])
        self.assertLess(verify_step_coordinates(step, data), 1e-14)
        step["coefficients"][0][0] += .001
        with self.assertRaises(AssertionError):
            verify_step_coordinates(step, data)

    def test_broken_third_derivative_endpoint_is_rejected(self):
        old = ScaledProblem(SplineProblem())
        p = ConnectedScaledProblem(old, old.x0)
        coef = p.coefficients(p.x0)
        self.assertTrue(endpoint_input_audit(p.knots*T, coef, p.case)["input_endpoint_pass"])
        coef[3, 0] += 1e-6
        audit = endpoint_input_audit(p.knots*T, coef, p.case)
        self.assertFalse(audit["input_endpoint_pass"])
        self.assertGreater(audit["inverter_input_errors_pu"]["start"], 1e-7)


if __name__ == "__main__":
    unittest.main()
