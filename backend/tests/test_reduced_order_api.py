from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.domain.network_models import NetworkTopology


class ReducedOrderApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def preset_topology(self, preset_id: str = "reduced-smib-stable") -> dict:
        response = self.client.get("/api/reduced-order/presets")
        self.assertEqual(response.status_code, 200)
        presets = {
            preset["id"]: preset for preset in response.json()["presets"]
        }
        return presets[preset_id]["topology"]

    def test_presets_are_separate_traceable_network_contracts(self) -> None:
        response = self.client.get("/api/reduced-order/presets")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("不属于论文 Fig. 8", body["separation_notice"])
        self.assertEqual(
            [preset["id"] for preset in body["presets"]],
            [
                "reduced-smib-stable",
                "reduced-smib-critical",
                "reduced-smib-unstable",
            ],
        )
        for preset in body["presets"]:
            NetworkTopology.model_validate(preset["topology"])
            self.assertEqual(
                preset["provenance"]["source_kind"],
                "team-defined-analytic-verification-preset",
            )
            self.assertFalse(preset["provenance"]["paper_fixture"])
            self.assertIn(
                "M*T_p*s^3",
                preset["provenance"]["characteristic_polynomial"],
            )

    def test_three_presets_return_expected_stability_classes(self) -> None:
        expected = {
            "reduced-smib-stable": "stable",
            "reduced-smib-critical": "marginal",
            "reduced-smib-unstable": "unstable",
        }

        for preset_id, expected_stability in expected.items():
            with self.subTest(preset_id=preset_id):
                response = self.client.post(
                    "/api/reduced-order/analyze",
                    json={
                        "preset_id": preset_id,
                        "simulation_time_s": 1.0,
                        "time_step_s": 0.1,
                    },
                )

                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["result"]["stability"], expected_stability)
                self.assertTrue(
                    body["provenance"]["expected_stability_match"]
                )

    def test_analysis_returns_validation_modal_and_time_domain_outputs(self) -> None:
        response = self.client.post(
            "/api/reduced-order/analyze",
            json={
                "preset_id": "reduced-smib-stable",
                "simulation_time_s": 1.0,
                "time_step_s": 0.1,
                "initial_angle_perturbation_rad": 0.002,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        validation = body["input_validation"]
        result = body["result"]
        NetworkTopology.model_validate(body["input_topology"])
        self.assertEqual(body["input_topology"]["id"], "reduced-smib-stable")
        self.assertEqual(validation["status"], "passed")
        self.assertEqual(validation["network_contract"], "NetworkTopology/1.0")
        self.assertTrue(validation["connected_network"])
        self.assertEqual(result["synchronous_stiffness_matrix"], [[5.0]])
        self.assertEqual(len(result["state_matrix"]), 3)
        self.assertEqual(len(result["poles"]), 3)
        self.assertEqual(
            result["dominant_mode"]["imag_hz"],
            result["dominant_mode"]["oscillation_frequency_hz"],
        )
        time_response = result["time_response"]
        self.assertEqual(len(time_response["time_s"]), 11)
        self.assertEqual(len(time_response["states"]), 11)
        self.assertEqual(len(time_response["states"][0]), 3)
        self.assertEqual(time_response["initial_state"], [0.002, 0.0, 0.0])

    def test_custom_network_topology_is_accepted_without_preset_provenance(self) -> None:
        topology = self.preset_topology()
        topology["id"] = "user-smib-case"
        topology["name"] = "用户自定义单机低频降阶算例"
        topology["grid_forming_converters"][0]["damping_coefficient_pu"] = 0.6

        response = self.client.post(
            "/api/reduced-order/analyze",
            json={
                "topology": topology,
                "simulation_time_s": 1.0,
                "time_step_s": 0.1,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            body["provenance"]["source_kind"],
            "user-supplied-network-topology",
        )
        self.assertIsNone(body["provenance"]["preset_id"])
        self.assertEqual(body["input_validation"]["topology_id"], "user-smib-case")

    def test_request_requires_exactly_one_topology_source(self) -> None:
        topology = self.preset_topology()
        neither = self.client.post(
            "/api/reduced-order/analyze",
            json={},
        )
        both = self.client.post(
            "/api/reduced-order/analyze",
            json={
                "preset_id": "reduced-smib-stable",
                "topology": topology,
            },
        )

        self.assertEqual(neither.status_code, 422)
        self.assertEqual(both.status_code, 422)
        self.assertIn("必须且只能选择一个", neither.text)
        self.assertIn("必须且只能选择一个", both.text)

    def test_illegal_island_is_rejected_by_reduced_model_scope(self) -> None:
        topology = self.preset_topology()
        topology["id"] = "unsupported-island"
        topology["reference_bus_id"] = "bus-gfm"
        topology["infinite_buses"] = []

        response = self.client.post(
            "/api/reduced-order/analyze",
            json={"topology": topology},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("纯孤岛系统含公共旋转模态", response.text)

    def test_excessive_time_grid_is_rejected_before_analysis(self) -> None:
        response = self.client.post(
            "/api/reduced-order/analyze",
            json={
                "preset_id": "reduced-smib-stable",
                "simulation_time_s": 300.0,
                "time_step_s": 0.001,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("超过上限 5001", response.text)

    def test_response_does_not_claim_paper_theorem_or_general_gfm_stability(self) -> None:
        response = self.client.post(
            "/api/reduced-order/analyze",
            json={
                "preset_id": "reduced-smib-critical",
                "simulation_time_s": 1.0,
                "time_step_s": 0.1,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        scope = body["model_scope"]
        self.assertEqual(
            scope["claim_level"],
            "low-frequency-reduced-order-model-only",
        )
        self.assertIn("不等同于论文完整定理复现", scope["statement"])
        self.assertIn("任意构网型变流器", scope["statement"])
        self.assertTrue(body["provenance"]["separated_from_fig8_fixture"])

    def test_printable_report_contains_inputs_results_and_scope_boundary(self) -> None:
        response = self.client.post(
            "/api/reports/reduced-order",
            json={
                "preset_id": "reduced-smib-unstable",
                "simulation_time_s": 1.0,
                "time_step_s": 0.1,
                "initial_angle_perturbation_rad": 0.002,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/html", response.headers["content-type"])
        report = response.text
        for expected_text in (
            "输入拓扑与参数",
            "同步刚度",
            "极点与主导模态",
            "线性时域响应",
            "稳定性类别",
            "失稳",
            "模型假设",
            "reduced-smib-unstable",
            "不是完整 dq 模型结论",
            "没有评价论文的小增益—小相位定理",
        ):
            self.assertIn(expected_text, report)

    def test_custom_topology_report_preserves_user_parameters(self) -> None:
        topology = self.preset_topology()
        topology["id"] = "report-custom-case"
        topology["name"] = "报告自定义参数算例"
        topology["grid_forming_converters"][0]["virtual_inertia_s"] = 3.25
        topology["grid_forming_converters"][0]["damping_coefficient_pu"] = 0.65

        response = self.client.post(
            "/api/reports/reduced-order",
            json={
                "topology": topology,
                "simulation_time_s": 1.0,
                "time_step_s": 0.1,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("报告自定义参数算例", response.text)
        self.assertIn(">3.25</td>", response.text)
        self.assertIn(">0.65</td>", response.text)
        self.assertIn("user-supplied-network-topology", response.text)


if __name__ == "__main__":
    unittest.main()
