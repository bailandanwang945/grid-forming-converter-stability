import json
import unittest

import numpy as np

from run_constrained_ocp import SplineProblem, T
from verify_lc_voltage_results import dense_check, check_candidate, boundary_demands


class LCResultCheckTests(unittest.TestCase):
    def test_dense_flags_are_json_serializable(self):
        p = SplineProblem()
        checked = dense_check(p.knots*T, p.coefficients(p.x0), p.case)
        json.dumps(checked, allow_nan=False)
        self.assertIsInstance(checked["voltage_pass"], bool)

    def test_corrupted_endpoint_is_not_accepted(self):
        p = SplineProblem()
        coef = p.coefficients(p.x0)
        coef[-1, 0] += .001
        checked = check_candidate(dict(knots_s=(p.knots*T).tolist(), coefficients=coef.tolist()), p.case, True)
        self.assertFalse(checked["strategy_constraints_pass"])
        self.assertFalse(checked["independent_endpoints"]["passed"])

    def test_boundary_values_and_scope(self):
        p = SplineProblem()
        b = boundary_demands(p.case)
        self.assertAlmostEqual(b["frozen_segment_join_voltage_pu"], 1.1265104997076807, places=10)
        self.assertAlmostEqual(b["sustained_steady_voltage_pu"], 1.0619746885696872, places=10)
        self.assertGreater(b["necessary_point_lower_bound_for_including_adjacent_stages_pu"], b["sustained_steady_voltage_pu"])
        self.assertTrue(np.isfinite(b["inverter_current_at_frozen_join_pu"]))
        self.assertIn("not a lower bound", b["scope"])


if __name__ == "__main__":
    unittest.main()
