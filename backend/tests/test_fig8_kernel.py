from __future__ import annotations

import unittest

import numpy as np

from backend.core.fig8_kernel import (
    DEFAULT_FIXTURE_ROOT,
    _build_shaped_responses,
    _load_fixture,
    evaluate_fig8_case,
)


class Fig8PortableKernelTest(unittest.TestCase):
    def test_unstable_case_matches_pinned_matlab_regression(self) -> None:
        result = evaluate_fig8_case("fig8_D_0p05")
        self.assertEqual(result["closed_loop_reference"], "unstable")
        self.assertAlmostEqual(result["dominant_pole_hz"]["real"], 0.021154437103478328, places=10)
        self.assertAlmostEqual(result["dominant_pole_hz"]["imag"], 0.578113296840319, places=10)
        self.assertEqual(result["counts"]["gain"], {"pass": 385, "fail": 615, "indeterminate": 0})
        self.assertEqual(result["counts"]["phase"], {"pass": 540, "fail": 422, "indeterminate": 38})
        self.assertEqual(result["counts"]["uncovered"], 75)
        self.assertAlmostEqual(
            result["phase_seed"]["converter_frequency_hz"],
            0.0018461469463245475,
            places=15,
        )
        self.assertEqual(result["phase_seed"]["converter_index_zero_based"], 38)
        self.assertEqual(result["theorem_status"], "not-evaluated-by-sampled-api")

        scan = result["frequency_scan"]
        frequencies = np.asarray(scan["frequencies_hz"])
        gain_margin = np.asarray(scan["gain_margin"])
        upper_phase_margin = np.asarray(
            [np.nan if value is None else value for value in scan["upper_phase_margin"]]
        )
        gain_minimum_index = int(np.argmin(gain_margin))
        phase_minimum_index = int(np.nanargmin(upper_phase_margin))
        uncovered = np.flatnonzero(np.asarray(scan["coverage"]) == "uncovered")
        self.assertAlmostEqual(
            gain_margin[gain_minimum_index], -231.74749517423299, places=10
        )
        self.assertAlmostEqual(
            frequencies[gain_minimum_index], 2887.0909173592345, places=10
        )
        self.assertAlmostEqual(
            upper_phase_margin[phase_minimum_index], -2.5206717585577185, places=11
        )
        self.assertAlmostEqual(
            frequencies[phase_minimum_index], 0.0018461469463245475, places=15
        )
        self.assertEqual(uncovered.size, 75)
        self.assertAlmostEqual(frequencies[uncovered[0]], 0.49853734638738939, places=14)
        self.assertAlmostEqual(frequencies[uncovered[-1]], 1.6451905877536626, places=14)

    def test_stable_case_matches_pinned_matlab_regression(self) -> None:
        result = evaluate_fig8_case("fig8_D_0p5")
        self.assertEqual(result["closed_loop_reference"], "stable")
        self.assertAlmostEqual(result["dominant_pole_hz"]["real"], -0.289891360618, places=9)
        self.assertAlmostEqual(result["dominant_pole_hz"]["imag"], 0.399601027552, places=9)
        self.assertEqual(result["counts"]["gain"], {"pass": 337, "fail": 663, "indeterminate": 0})
        self.assertEqual(result["counts"]["phase"], {"pass": 1000, "fail": 0, "indeterminate": 0})
        self.assertEqual(result["counts"]["uncovered"], 0)

        scan = result["frequency_scan"]
        frequencies = np.asarray(scan["frequencies_hz"])
        upper_phase_margin = np.asarray(scan["upper_phase_margin"], dtype=float)
        phase_minimum_index = int(np.argmin(upper_phase_margin))
        self.assertAlmostEqual(
            upper_phase_margin[phase_minimum_index], 0.26699936598433283, places=12
        )
        self.assertAlmostEqual(
            frequencies[phase_minimum_index], 0.38511070023255689, places=14
        )

    def test_loop_shaping_matrix_order_matches_matlab_reference(self) -> None:
        manifest, cases = _load_fixture(DEFAULT_FIXTURE_ROOT)
        case = cases["fig8_D_0p05"]
        frequencies = case["frequencies_hz"]
        converter, network, condition, residual, status = _build_shaped_responses(
            frequencies,
            case["converter"],
            case["network"],
            manifest,
        )
        index = int(np.argmin(np.abs(frequencies - 0.57644882829258792)))
        expected_converter = np.array(
            [
                [
                    -1.1650331531114735 + 0.25868919701107729j,
                    0.41065641087092647 + 0.25062040835853822j,
                ],
                [
                    0.26895446862731209 + 0.29670317836642285j,
                    0.058662744406292919 + 0.67637913923602788j,
                ],
            ]
        )
        expected_network = np.array(
            [
                [
                    0.86820380449275059 + 0.040513627397145632j,
                    1.0697141050455119 - 0.28827333996708893j,
                ],
                [
                    -0.64280901353478781 - 0.20636103888417912j,
                    0.8186431490641024 + 0.041852976210707715j,
                ],
            ]
        )
        np.testing.assert_allclose(converter[index], expected_converter, rtol=1e-13, atol=1e-13)
        np.testing.assert_allclose(network[index], expected_network, rtol=1e-13, atol=1e-13)
        self.assertAlmostEqual(condition[index], 1.118502267616331, places=13)
        self.assertAlmostEqual(
            residual[index], 1.4235274868092878e-16, delta=1e-16
        )
        self.assertLess(residual[index], 2e-15)
        self.assertEqual(status[index], "sampled-algebra-resolved")

    def test_runtime_diagnostics_and_theorem_boundaries_are_explicit(self) -> None:
        expected_preconditions = {
            "openLoopStable",
            "realRationalProper",
            "transformationWellDefined",
            "networkInverseStable",
            "noRhpCancellation",
            "endpointsCovered",
            "fullFrequencyCoverage",
        }
        expected_spread_at_reference = {
            "fig8_D_0p05": 1.4815594970414432,
            "fig8_D_0p5": 2.4273954467899594,
        }
        for case_id, expected_spread in expected_spread_at_reference.items():
            with self.subTest(case_id=case_id):
                result = evaluate_fig8_case(case_id)
                scan = result["frequency_scan"]
                frequencies = np.asarray(scan["frequencies_hz"])
                residual = np.asarray(scan["interconnection_residual"])
                spread = np.asarray(
                    [
                        np.nan if value is None else value
                        for value in scan["converter_phase_spread_margin"]
                    ]
                )
                reference_index = int(
                    np.argmin(np.abs(frequencies - 0.57644882829258792))
                )

                self.assertEqual(spread.size, frequencies.size)
                self.assertAlmostEqual(
                    spread[reference_index], expected_spread, places=12
                )
                self.assertEqual(residual.size, frequencies.size)
                self.assertGreater(float(np.max(residual)), 0.0)
                self.assertLess(float(np.max(residual)), 2e-15)
                self.assertAlmostEqual(
                    result["maximum_interconnection_residual"],
                    float(np.max(residual)),
                    places=28,
                )
                self.assertTrue(
                    all(
                        value == "sampled-algebra-resolved"
                        for value in scan["transformation_status"]
                    )
                )

                preconditions = result["theorem_preconditions"]
                self.assertEqual(preconditions["status"], "not-verified")
                self.assertFalse(preconditions["all_satisfied"])
                self.assertEqual(
                    set(preconditions["values"]), expected_preconditions
                )
                self.assertFalse(any(preconditions["values"].values()))
                self.assertIn("七项论文定理前提均未核验", result["interpretation_boundary"])

    def test_unknown_case_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown pinned Fig. 8 case"):
            evaluate_fig8_case("not-a-case")


if __name__ == "__main__":
    unittest.main()
