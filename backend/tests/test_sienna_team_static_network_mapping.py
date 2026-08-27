from __future__ import annotations

import unittest

from backend.core.sienna_team_static_network_mapping import (
    run_static_network_mapping_audit,
)
from backend.core.sienna_test08_reference import SiennaTest08Parameters


class SiennaTeamStaticNetworkMappingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = run_static_network_mapping_audit()

    def test_common_static_network_equations_match(self) -> None:
        self.assertEqual(self.payload["status"], "passed")
        self.assertLessEqual(
            self.payload["maximum_voltage_difference_abs_pu"], 1.0e-12
        )
        self.assertAlmostEqual(
            self.payload["model_contract"][
                "converted_reactance_pu_device_base"
            ],
            0.0020625,
            places=12,
        )
        source_voltage = SiennaTest08Parameters().infinite_bus_voltage_pu
        self.assertEqual(
            self.payload["model_contract"]["infinite_bus_voltage"],
            [float(source_voltage.real), float(source_voltage.imag)],
        )

    def test_base_and_sign_counterexamples_are_rejected(self) -> None:
        counterexamples = self.payload["counterexamples"]
        self.assertGreater(
            counterexamples["base_conversion_omitted_difference_abs_pu"],
            1.0e-3,
        )
        self.assertGreater(
            counterexamples[
                "current_direction_inversion_omitted_difference_abs_pu"
            ],
            1.0e-3,
        )

    def test_gate_does_not_claim_dynamic_network_isomorphism(self) -> None:
        scope = self.payload["scope"]
        self.assertTrue(scope["common_static_network_equations_isomorphic"])
        self.assertFalse(
            scope["original_team_dynamic_line_isomorphic_to_source_network"]
        )
        self.assertFalse(
            scope["full_model_eigenvalues_comparable_from_this_gate"]
        )


if __name__ == "__main__":
    unittest.main()
