"""Equation/implementation tests; no claim of independent physical validation."""

import unittest

import numpy as np

from run_power_feasibility import K, VG, build_case, run_case


class FeasibilityTests(unittest.TestCase):
    def test_pre_point_is_not_silently_interchanged(self):
        poi = build_case(60, "poi")
        grid = build_case(60, "grid")
        self.assertAlmostEqual(poi["ppre"], 1, places=12)
        self.assertGreater(grid["ppre"], 1)
        self.assertGreater(np.linalg.norm(poi["iss"] - grid["iss"]), 0.3)

    def test_limit_initial_condition_and_frozen_continuity(self):
        c = build_case(60, "poi")
        self.assertAlmostEqual(np.linalg.norm(c["i0"]), 1.2, places=11)
        self.assertGreater(c["p0"], c["ppre"])
        self.assertLess(c["tlim"], 0.002)

    def test_nominal_frequency_scaling(self):
        a, b = build_case(50, "poi"), build_case(60, "poi")
        np.testing.assert_allclose(a["i0"], b["i0"], rtol=1e-10, atol=1e-10)
        self.assertAlmostEqual(a["tlim"] * 50, b["tlim"] * 60, places=10)

    def test_poi_power_equals_energy_balance(self):
        c = build_case(60, "poi")
        for i, di in [
            (np.array([0.9, 0.5]), np.array([12.0, -30.0])),
            (np.array([1.1, -0.3]), np.array([-8.0, 17.0])),
        ]:
            u = VG + c["rt"] * i + c["lt"] * K @ i + c["lt"] / c["wb"] * di
            vpoi = c["alpha"] * u + c["beta"] * VG + c["correction"] * i
            direct = float(vpoi @ i)
            energy = float(i[0] + c["rg"] * (i @ i) + c["lg"] / c["wb"] * (i @ di))
            self.assertAlmostEqual(direct, energy, places=12)

    def test_main_witness_reintegrates_with_prescribed_voltage(self):
        c = build_case(60, "poi")
        row = run_case(c, float(np.linalg.norm(c["frozen"])), 5e-5, verify=True)
        self.assertTrue(row["sampled_constraints_pass"])
        self.assertLess(row["current_peak_pu"], 1.3)
        self.assertGreaterEqual(row["power_min_pu"], c["ppre"] - 1e-12)
        self.assertLess(row["terminal_current_error"], 1e-5)
        self.assertLess(row["power_target_error"], 1e-12)
        self.assertLess(
            max(row["prescribed_input_reintegration_errors"].values()), 1e-7
        )


if __name__ == "__main__":
    unittest.main()
