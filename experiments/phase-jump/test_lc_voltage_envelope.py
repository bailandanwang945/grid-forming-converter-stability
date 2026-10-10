"""No optimization: tests for independent hypothetical LC reconstruction."""
import json
import unittest
from pathlib import Path

import numpy as np

from verify_lc_voltage_envelope import CF, K, R1, VG, X1, hardware_audit

ROOT = Path(__file__).resolve().parents[2]


class LcEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.knots = np.r_[np.zeros(6), np.ones(6)*.06]
        self.i = np.array([.9, .2])
        wb, lt, rt = 2*np.pi*60, .48, .08
        self.vc = VG+rt*self.i+lt*K@self.i
        self.case = dict(wb=wb, lt=lt, rt=rt, i0=self.i, iss=self.i, frozen=self.vc)
        self.coefficients = np.tile(self.i, (6, 1))

    def test_constant_steady_state(self):
        summary, segments = hardware_audit(self.knots, self.coefficients, self.case)
        i1 = self.i+CF*K@self.vc
        vi = self.vc+R1*i1+X1*K@i1
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(summary["i1_peak_pu"], np.linalg.norm(i1), places=12)
        self.assertAlmostEqual(summary["vi_peak_pu"], np.linalg.norm(vi), places=12)
        self.assertLess(summary["endpoint_check"]["start_i1_error_pu"], 1e-12)
        self.assertLess(summary["endpoint_check"]["end_i1_error_pu"], 1e-12)
        self.assertFalse(summary["hardware_ratings_evaluated"])

    def test_saved_hard_power_candidate(self):
        path = ROOT/"results/phase-jump-power-feasibility/phase-one-refinement-2026-10-05/result.json"
        if not path.exists():
            self.skipTest("Fixed previous-result fixture not available")
        result = json.loads(path.read_text(encoding="utf-8"))
        row = next(r for r in result["strategies"] if r["hard_power_constraint"])
        summary, segments = hardware_audit(row["knots_s"], row["coefficients"], result["case"])
        self.assertGreater(summary["vi_peak_pu"], 1.)
        self.assertAlmostEqual(summary["vi_peak_pu"], 19.43484, places=4)
        self.assertGreater(len(segments), 1)
        self.assertLess(max(summary["equation_residuals_pu_per_s"].values()), 1e-7)
        self.assertLess(summary["endpoint_check"]["start_i1_error_pu"], 1e-7)
        self.assertGreaterEqual(summary["vi_peak_pu"]+1e-7, summary["dense_check"]["peaks_pu"]["vi"])

    def test_invalid_inputs(self):
        for knots, coef in [(self.knots[::-1], self.coefficients),
                            (self.knots, np.zeros((3, 2))),
                            (self.knots, np.ones((6, 2))*np.nan)]:
            with self.assertRaises(ValueError):
                hardware_audit(knots, coef, self.case)
        bad = dict(self.case, wb=0.)
        with self.assertRaises(ValueError):
            hardware_audit(self.knots, self.coefficients, bad)


if __name__ == "__main__":
    unittest.main()
