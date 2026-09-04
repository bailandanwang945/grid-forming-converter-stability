from __future__ import annotations

import unittest

import numpy as np

from backend.core.fig8_kernel import (
    DEFAULT_FIXTURE_ROOT,
    _build_shaped_responses,
    _load_fixture,
    evaluate_fig8_case,
)
from backend.core.sampled_decentralized_screening import (
    evaluate_sampled_decentralized_condition,
)


class SampledDecentralizedScreeningTest(unittest.TestCase):
    def test_single_converter_results_match_both_fig8_regressions(self) -> None:
        manifest, cases = _load_fixture(DEFAULT_FIXTURE_ROOT)
        for case_id in ("fig8_D_0p05", "fig8_D_0p5"):
            with self.subTest(case_id=case_id):
                case = cases[case_id]
                converter, network, *_ = _build_shaped_responses(
                    case["frequencies_hz"],
                    case["converter"],
                    case["network"],
                    manifest,
                )
                actual = evaluate_sampled_decentralized_condition(
                    case["frequencies_hz"],
                    converter[np.newaxis, ...],
                    network,
                    ["gfm-1"],
                )
                expected = evaluate_fig8_case(case_id)

                self.assertEqual(actual["counts"], expected["counts"])
                self.assertEqual(
                    actual["sampled_band_status"], expected["sampled_band_status"]
                )
                for key in ("gain_status", "phase_status", "coverage"):
                    self.assertEqual(
                        actual["frequency_scan"][key],
                        expected["frequency_scan"][key],
                    )
                for key in (
                    "gain_margin",
                    "upper_phase_margin",
                    "lower_phase_margin",
                    "converter_phase_spread_margin",
                ):
                    np.testing.assert_allclose(
                        np.asarray(actual["frequency_scan"][key], dtype=float),
                        np.asarray(expected["frequency_scan"][key], dtype=float),
                        rtol=1e-12,
                        atol=1e-12,
                        equal_nan=True,
                    )
                self.assertEqual(
                    actual["theorem_status"], "not-evaluated-by-sampled-api"
                )

    def test_cross_converter_phase_spread_is_an_independent_constraint(self) -> None:
        angle = 0.75 * np.pi
        converters = np.asarray(
            [
                [2 * np.exp(1j * angle) * np.eye(2)],
                [2 * np.exp(-1j * angle) * np.eye(2)],
            ]
        )
        network = np.asarray([np.eye(4, dtype=complex)])

        result = evaluate_sampled_decentralized_condition(
            [1.0], converters, network, ["leading", "lagging"]
        )

        scan = result["frequency_scan"]
        self.assertTrue(all(value > 0 for value in scan["per_converter_upper_phase_margin"][0]))
        self.assertTrue(all(value > 0 for value in scan["per_converter_lower_phase_margin"][0]))
        self.assertLess(scan["converter_phase_spread_margin"][0], 0)
        self.assertEqual(scan["phase_status"], ["fail"])
        self.assertEqual(scan["gain_status"], ["fail"])
        self.assertEqual(scan["coverage"], ["uncovered"])

    def test_device_permutation_does_not_change_aggregate_result(self) -> None:
        frequencies = [0.5, 5.0]
        converters = np.asarray(
            [
                [0.2 * np.eye(2), 0.3 * np.eye(2)],
                [0.4 * np.eye(2), 0.5 * np.eye(2)],
            ],
            dtype=complex,
        )
        network = np.asarray([np.eye(4), 1.5 * np.eye(4)], dtype=complex)

        first = evaluate_sampled_decentralized_condition(
            frequencies, converters, network, ["a", "b"]
        )
        second = evaluate_sampled_decentralized_condition(
            frequencies, converters[::-1], network, ["b", "a"]
        )

        for key in (
            "gain_margin",
            "upper_phase_margin",
            "lower_phase_margin",
            "converter_phase_spread_margin",
            "gain_status",
            "phase_status",
            "coverage",
        ):
            self.assertEqual(first["frequency_scan"][key], second["frequency_scan"][key])
        self.assertEqual(first["counts"], second["counts"])

    def test_nonsectorial_response_is_a_phase_failure_not_a_stability_claim(self) -> None:
        converters = np.asarray([[[[1.0, 2.0], [0.0, -1.0]]]], dtype=complex)
        network = np.asarray([np.eye(2)], dtype=complex)

        result = evaluate_sampled_decentralized_condition([1.0], converters, network)

        self.assertEqual(result["frequency_scan"]["phase_status"], ["fail"])
        self.assertEqual(result["frequency_scan"]["coverage"], ["uncovered"])
        self.assertIn("不能据此断言闭环失稳", result["interpretation_boundary"])

    def test_ill_conditioned_network_keeps_gain_evidence_and_marks_phase_pending(self) -> None:
        converters = np.asarray([[1e-16 * np.eye(2)]], dtype=complex)
        network = np.asarray([np.diag([1.0, 1e-14])], dtype=complex)

        result = evaluate_sampled_decentralized_condition([1.0], converters, network)

        scan = result["frequency_scan"]
        self.assertEqual(scan["gain_status"], ["pass"])
        self.assertEqual(scan["phase_status"], ["indeterminate"])
        self.assertEqual(scan["coverage"], ["gain-pass"])
        self.assertIsNone(result["phase_seed"]["network_inverse"])

    def test_invalid_dimensions_identifiers_and_values_are_rejected(self) -> None:
        converters = np.asarray([[np.eye(2)]], dtype=complex)
        network = np.asarray([np.eye(2)], dtype=complex)
        invalid_calls = (
            lambda: evaluate_sampled_decentralized_condition(
                [1.0, 0.5], np.repeat(converters, 2, axis=1), np.repeat(network, 2, axis=0)
            ),
            lambda: evaluate_sampled_decentralized_condition(
                [1.0], converters[0], network
            ),
            lambda: evaluate_sampled_decentralized_condition(
                [1.0], converters, np.asarray([np.eye(4)])
            ),
            lambda: evaluate_sampled_decentralized_condition(
                [1.0],
                np.repeat(converters, 2, axis=0),
                np.asarray([np.eye(4)]),
                ["same", "same"],
            ),
            lambda: evaluate_sampled_decentralized_condition(
                [1.0], np.asarray([[[[np.nan, 0], [0, 1]]]]), network
            ),
            lambda: evaluate_sampled_decentralized_condition(
                [1.0], converters, network, condition_limit=0
            ),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
