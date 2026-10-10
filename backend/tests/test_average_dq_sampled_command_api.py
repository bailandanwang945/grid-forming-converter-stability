"""Request/result contract tests for the opt-in sampled-command endpoint."""

from copy import deepcopy
import json
import unittest

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.average_dq_presets import build_average_dq_ablation_anchor_case


ENDPOINT = "/api/experimental/average-dq/sampled-command"


class SampledCommandApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def base_request(self):
        return {
            "preset_id": "average-dq-smib-verification",
            "sampling_periods_s": [0.001],
            "holding_frames": ["local-control-dq"],
            "delay_steps": [0],
        }

    def test_explicit_case_required(self):
        self.assertEqual(self.client.post(ENDPOINT, json={}).status_code, 422)

    def test_invalid_assumptions_are_rejected_before_computation(self):
        cases = [
            {"sampling_periods_s": [True]},
            {"sampling_periods_s": ["0.001"]},
            {"sampling_periods_s": [0]},
            {"sampling_periods_s": [-0.001]},
            {"sampling_periods_s": [0.03]},
            {"sampling_periods_s": [0.001, 0.001]},
            {"sampling_periods_s": [0.002, 0.001]},
            {"sampling_periods_s": [i * 0.0001 for i in range(1, 18)]},
            {"holding_frames": ["abc"]},
            {"holding_frames": ["local-control-dq", "local-control-dq"]},
            {"delay_steps": [True]},
            {"delay_steps": ["1"]},
            {"delay_steps": [2]},
            {"delay_steps": [1, 1]},
            {"digital_pi": True},
        ]
        for change in cases:
            with self.subTest(change=change):
                request = self.base_request() | change
                self.assertEqual(
                    self.client.post(ENDPOINT, json=request).status_code, 422
                )

    def test_nonstandard_json_numbers_have_a_controlled_client_error(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                request = self.base_request()
                request["sampling_periods_s"] = [value]
                client = TestClient(app, raise_server_exceptions=False)
                response = client.post(
                    ENDPOINT,
                    content=json.dumps(request),
                    headers={"content-type": "application/json"},
                )
                self.assertEqual(response.status_code, 422, response.text)

    def test_invalid_json_and_oversized_request_are_rejected(self):
        for body in (
            b"{",
            b"\xff",
            b'{"preset_id":"average-dq-smib-verification","sampling_periods_s":[1e400]}',
            b"[" * 2000 + b"0" + b"]" * 2000,
        ):
            with self.subTest(body_size=len(body)):
                response = self.client.post(
                    ENDPOINT, content=body, headers={"content-type": "application/json"}
                )
                self.assertEqual(response.status_code, 422)
        response = self.client.post(
            ENDPOINT,
            content=b" " * (2 * 1024 * 1024 + 1),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)

    def test_complete_case_source_cannot_be_mixed(self):
        topology, parameters = build_average_dq_ablation_anchor_case()
        for change in [
            {"topology": topology.model_dump(mode="json")},
            {"parameters": parameters.model_dump(mode="json")},
            {
                "topology": topology.model_dump(mode="json"),
                "parameters": parameters.model_dump(mode="json"),
            },
        ]:
            with self.subTest(keys=list(change)):
                self.assertEqual(
                    self.client.post(
                        ENDPOINT, json=self.base_request() | change
                    ).status_code,
                    422,
                )

    def test_preset_recomputes_and_discloses_scope(self):
        response = self.client.post(ENDPOINT, json=self.base_request())
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["experimental"])
        self.assertFalse(payload["provenance"]["result_table_lookup"])
        self.assertFalse(payload["model_scope"]["full_digital_controller"])
        self.assertFalse(payload["model_scope"]["safe_sampling_period_recommendation"])
        self.assertEqual(
            payload["model_scope"]["theorem_status"], "not-evaluated-by-sampled-api"
        )
        self.assertEqual(payload["comparison_count"], 1)
        self.assertLess(payload["operating_point"]["closed_rhs_residual_inf"], 1e-8)
        self.assertEqual(
            len(payload["comparisons"][0]["references"]["sampled_command"]["spectrum"]),
            14,
        )

    def test_custom_parameter_disagreement_is_recomputed_not_interpolated(self):
        topology, parameters = build_average_dq_ablation_anchor_case()
        topology.lines[0].reactance_pu = 0.2
        parameters.current_proportional_gain_pu *= 2
        parameters.current_integral_gain_per_s *= 2
        request = self.base_request()
        del request["preset_id"]
        request["topology"] = topology.model_dump(mode="json")
        request["parameters"] = parameters.model_dump(mode="json")
        before = deepcopy(request)
        response = self.client.post(ENDPOINT, json=request)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(request, before)
        payload = response.json()
        self.assertEqual(
            payload["provenance"]["source_kind"], "user-supplied-average-dq-case"
        )
        self.assertEqual(payload["input_topology"], before["topology"])
        self.assertEqual(payload["input_parameters"], before["parameters"])
        refs = payload["comparisons"][0]["references"]
        self.assertEqual(refs["sampled_command"]["classification"], "unstable")
        self.assertEqual(
            refs["same_hold_low_frequency_lag"]["classification"], "stable"
        )
        self.assertAlmostEqual(
            refs["sampled_command"]["metric_per_s"], 0.889960142, places=5
        )

    def test_all_declared_conditions_are_returned_with_memory_roots(self):
        request = self.base_request()
        request["holding_frames"] = ["local-control-dq", "global-synchronous-dq"]
        request["delay_steps"] = [0, 1]
        response = self.client.post(ENDPOINT, json=request)
        self.assertEqual(response.status_code, 200, response.text)
        comparisons = response.json()["comparisons"]
        self.assertEqual(len(comparisons), 4)
        for result in comparisons:
            expected = 14 if result["delay_steps"] == 0 else 16
            self.assertEqual(
                len(result["references"]["sampled_command"]["spectrum"]), expected
            )
            self.assertEqual(
                len(result["references"]["original_continuous_modulation"]["spectrum"]),
                16,
            )
            self.assertAlmostEqual(
                result["phase_matched_tau_s"], (result["delay_steps"] + 0.5) * 0.001
            )

    def test_maximum_grid_contains_all_64_unique_comparisons(self):
        request = self.base_request()
        request["sampling_periods_s"] = [i * 1e-4 for i in range(1, 17)]
        request["holding_frames"] = ["local-control-dq", "global-synchronous-dq"]
        request["delay_steps"] = [0, 1]
        response = self.client.post(ENDPOINT, json=request)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["comparison_count"], 64)
        keys = {
            (row["sampling_period_s"], row["holding_frame"], row["delay_steps"])
            for row in payload["comparisons"]
        }
        self.assertEqual(len(keys), 64)
        for row in payload["comparisons"]:
            self.assertEqual(row["theorem_status"], "not-evaluated-by-sampled-api")
            self.assertEqual(row["step_check"]["status"], "step-comparison-evaluated")
            self.assertEqual(row["original_continuous_tau_s"], 0.001)

    def test_unsupported_topology_returns_a_model_error_not_a_partial_result(self):
        topology, parameters = build_average_dq_ablation_anchor_case()
        parallel = topology.lines[0].model_copy(deep=True)
        parallel.id = "line-grid-parallel"
        topology.lines.append(parallel)
        request = self.base_request()
        del request["preset_id"]
        request["topology"] = topology.model_dump(mode="json")
        request["parameters"] = parameters.model_dump(mode="json")
        response = self.client.post(ENDPOINT, json=request)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn("comparisons", response.json())


if __name__ == "__main__":
    unittest.main()
