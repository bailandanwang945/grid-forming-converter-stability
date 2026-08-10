import unittest

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.average_dq_presets import build_average_dq_verification_case


class AverageDQApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_preset_is_explicitly_separated_from_paper_fixture(self) -> None:
        response = self.client.get("/api/average-dq/presets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["presets"]), 1)
        preset = payload["presets"][0]
        self.assertEqual(preset["id"], "average-dq-smib-verification")
        self.assertFalse(preset["provenance"]["paper_fixture"])
        self.assertFalse(preset["provenance"]["physical_hardware_fit"])
        self.assertIn("16状态", payload["separation_notice"])

    def test_analysis_returns_operating_modal_port_and_time_evidence(self) -> None:
        response = self.client.post(
            "/api/average-dq/analyze",
            json={
                "preset_id": "average-dq-smib-verification",
                "simulation_time_s": 0.2,
                "time_step_s": 0.002,
                "initial_angle_perturbation_rad": 1.0e-4,
                "frequency_values_hz": [0.1, 1.0, 10.0],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["result"]["stability"], "stable")
        self.assertEqual(len(payload["result"]["poles"]), 16)
        self.assertEqual(
            payload["result"]["port_admittance"]["frequencies_hz"],
            [0.1, 1.0, 10.0],
        )
        self.assertEqual(
            len(payload["result"]["time_response"]["nonlinear_states"]), 101
        )
        self.assertLess(
            payload["operating_point"]["closed_rhs_residual_inf"], 1.0e-9
        )
        self.assertLess(
            abs(payload["operating_point"]["active_power_balance_residual_pu"]),
            1.0e-8,
        )
        self.assertLess(
            payload["result"]["port_interconnection_max_abs_error"], 1.0e-6
        )
        reduction = payload["result"]["quasisteady_reduction_comparison"]
        self.assertLess(reduction["oscillation_frequency_relative_error"], 0.05)
        self.assertLess(reduction["decay_rate_relative_error"], 0.05)
        self.assertIn("不证明一般等价", reduction["interpretation"])
        self.assertIn("不是论文 Fig. 8", payload["model_scope"]["statement"])
        self.assertTrue(payload["provenance"]["separated_from_fig8_fixture"])

    def test_custom_case_preserves_inputs_and_uses_same_solver(self) -> None:
        topology, parameters = build_average_dq_verification_case()
        topology.grid_forming_converters[0].active_power_setpoint_pu = 0.4
        response = self.client.post(
            "/api/average-dq/analyze",
            json={
                "topology": topology.model_dump(mode="json"),
                "parameters": parameters.model_dump(mode="json"),
                "simulation_time_s": 0.02,
                "time_step_s": 0.002,
                "frequency_values_hz": [1.0],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(
            payload["input_topology"]["grid_forming_converters"][0][
                "active_power_setpoint_pu"
            ],
            0.4,
        )
        self.assertEqual(
            payload["input_parameters"]["id"], parameters.id
        )
        self.assertEqual(
            payload["provenance"]["source_kind"],
            "user-supplied-average-dq-case",
        )

    def test_printable_report_contains_diagnostics_and_scope_boundary(self) -> None:
        response = self.client.post(
            "/api/reports/average-dq",
            json={
                "preset_id": "average-dq-smib-verification",
                "simulation_time_s": 0.02,
                "time_step_s": 0.002,
                "frequency_values_hz": [1.0],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("平均值 dq 构网型变流器分析报告", response.text)
        self.assertIn("滤波器有功平衡残差", response.text)
        self.assertIn("端口互联误差", response.text)
        self.assertIn("三状态低频近似", response.text)
        self.assertIn("不是论文算例复现", response.text)
        self.assertIn("不宣称完成工程模型确认", response.text)

    def test_request_rejects_mixed_sources_and_nonmonotonic_frequency_grid(self) -> None:
        topology, parameters = build_average_dq_verification_case()
        mixed = self.client.post(
            "/api/average-dq/analyze",
            json={
                "preset_id": "average-dq-smib-verification",
                "topology": topology.model_dump(mode="json"),
                "parameters": parameters.model_dump(mode="json"),
            },
        )
        nonmonotonic = self.client.post(
            "/api/average-dq/analyze",
            json={
                "preset_id": "average-dq-smib-verification",
                "frequency_values_hz": [1.0, 0.5],
            },
        )

        self.assertEqual(mixed.status_code, 422)
        self.assertEqual(nonmonotonic.status_code, 422)


if __name__ == "__main__":
    unittest.main()
