import json
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
        self.assertIn("matched_full_pole", reduction)
        self.assertIn("matching_method", reduction)
        self.assertIn("稳定性分类分别取", reduction["interpretation"])
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

    def test_scan_compares_full_and_reduced_models_without_scr_overclaim(self) -> None:
        response = self.client.post(
            "/api/average-dq/scan",
            json={
                "preset_id": "average-dq-smib-verification",
                "damping_values_pu": [20.0, 40.0, 60.0],
                "reactance_values_pu": [0.1, 0.3, 0.8],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["result"]["point_count"], 9)
        self.assertEqual(payload["result"]["counts"]["agreement"], 8)
        self.assertEqual(payload["result"]["counts"]["disagreement"], 1)
        disagreement = payload["result"]["rows"][2][0]
        self.assertEqual(disagreement["full_stability"], "unstable")
        self.assertEqual(disagreement["reduced_stability"], "stable")
        self.assertFalse(disagreement["stability_agreement"])
        self.assertEqual(
            disagreement["full_dominant_participation"][0]["state"],
            "converter_current_q_pu",
        )
        self.assertIn("不等同于普遍 SCR", payload["model_scope"]["statement"])
        self.assertFalse(payload["model_scope"]["paper_theorem_evaluated"])
        self.assertFalse(payload["provenance"]["interpolation_used"])

    def test_scan_rejects_duplicate_axis_values(self) -> None:
        response = self.client.post(
            "/api/average-dq/scan",
            json={
                "preset_id": "average-dq-smib-verification",
                "damping_values_pu": [20.0, 20.0],
                "reactance_values_pu": [0.3],
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("严格递增", response.text)

    def test_fixed_ablation_returns_traceable_nineteen_point_evidence(self) -> None:
        response = self.client.post(
            "/api/average-dq/ablation",
            json={
                "preset_id": (
                    "average-dq-hierarchy-disagreement-ablation-v1"
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        result = payload["result"]
        self.assertEqual(result["point_count"], 19)
        self.assertEqual(len({p["scenario_id"] for p in result["points"]}), 19)
        self.assertEqual(
            result["summary"]["stability_counts"],
            {"stable": 5, "marginal": 0, "unstable": 14},
        )
        self.assertEqual(
            result["summary"]["extra_mode_tracking_counts"],
            {"matched": 19, "pending": 0},
        )
        self.assertTrue(
            all(point["damping_coefficient_pu"] == 60.0 for point in result["points"])
        )
        self.assertTrue(
            all(point["line_reactance_pu"] == 0.1 for point in result["points"])
        )
        baseline = next(
            point for point in result["points"] if point["scenario_id"] == "baseline"
        )
        self.assertAlmostEqual(
            baseline["extra_mode"]["pole"]["real_per_s"], 4.5864, places=3
        )
        two_path = next(
            point
            for point in result["points"]
            if point["scenario_id"]
            == "voltage_pi__2p0__current_pi__2p0"
        )
        self.assertIn("|", two_path["extra_mode"]["path_label"])
        self.assertIn(
            "局部候选间隔不是全局指派唯一性证明",
            payload["model_scope"]["tracking_boundary"],
        )
        self.assertFalse(payload["model_scope"]["paper_theorem_evaluated"])
        self.assertFalse(payload["model_scope"]["physical_validation"])
        self.assertFalse(
            payload["model_scope"]["accepts_arbitrary_state_definition"]
        )
        self.assertFalse(
            payload["provenance"]["interpolation_used_for_reported_points"]
        )
        json.dumps(payload, allow_nan=False)

    def test_fixed_ablation_rejects_custom_state_or_unknown_preset(self) -> None:
        custom_state = self.client.post(
            "/api/average-dq/ablation",
            json={
                "preset_id": (
                    "average-dq-hierarchy-disagreement-ablation-v1"
                ),
                "state_matrix": [[0.0]],
            },
        )
        unknown = self.client.post(
            "/api/average-dq/ablation",
            json={"preset_id": "some-other-experiment"},
        )

        self.assertEqual(custom_state.status_code, 422)
        self.assertEqual(unknown.status_code, 422)

    def test_fixed_boundary_returns_four_independently_recomputed_paths(self) -> None:
        response = self.client.post(
            "/api/average-dq/boundary",
            json={
                "preset_id": (
                    "average-dq-hierarchy-disagreement-ablation-v1"
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        result = payload["result"]
        self.assertEqual(result["path_count"], 4)
        self.assertEqual(result["converged_extra_mode_boundaries"], 4)
        self.assertEqual(result["converged_overall_boundaries"], 4)
        self.assertEqual(result["agreeing_boundary_count"], 4)
        expected = {
            "voltage_pi": 1.6297459207796248,
            "current_pi": 1.6016445244183835,
            "converter_side_reactance": 0.6931690497962353,
            "grid_side_reactance": 1.9945604684575917,
        }
        self.assertEqual(
            {path["factor_name"] for path in result["paths"]},
            set(expected),
        )
        for path in result["paths"]:
            self.assertAlmostEqual(
                path["extra_mode_boundary"]["factor_value"],
                expected[path["factor_name"]],
                places=10,
            )
            self.assertTrue(path["boundaries_agree"])
            self.assertGreater(path["trial_count"], 2)
            self.assertTrue(
                all(
                    trial["calculation_status"] == "valid"
                    and trial["extra_mode"]["status"] == "matched"
                    for trial in path["trials"]
                )
            )
        self.assertFalse(
            payload["model_scope"]["accepts_arbitrary_parameter_paths"]
        )
        self.assertFalse(payload["model_scope"]["causal_identification"])
        self.assertFalse(
            payload["provenance"][
                "interpolation_used_for_reported_boundaries"
            ]
        )
        json.dumps(payload, allow_nan=False)

    def test_fixed_boundary_rejects_custom_state_or_unknown_preset(self) -> None:
        custom_state = self.client.post(
            "/api/average-dq/boundary",
            json={
                "preset_id": (
                    "average-dq-hierarchy-disagreement-ablation-v1"
                ),
                "parameter_path": {"voltage_pi": [1.0, 2.0]},
            },
        )
        unknown = self.client.post(
            "/api/average-dq/boundary",
            json={"preset_id": "some-other-experiment"},
        )

        self.assertEqual(custom_state.status_code, 422)
        self.assertEqual(unknown.status_code, 422)

    def test_fixed_port_identification_returns_traceable_three_frequency_evidence(
        self,
    ) -> None:
        response = self.client.post(
            "/api/average-dq/port-identification",
            json={"preset_id": "average-dq-smib-verification"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        result = payload["result"]
        self.assertTrue(result["summary"]["passed"])
        self.assertEqual(result["contract"]["frequencies_hz"], [0.2, 2.0, 20.0])
        self.assertEqual(result["contract"]["source_amplitude_pu"], 1.0e-4)
        self.assertEqual(len(result["points"]), 3)
        self.assertTrue(all(point["passed"] for point in result["points"]))
        self.assertLess(
            result["summary"]["maximum_magnitude_relative_error"], 0.01
        )
        self.assertLess(result["summary"]["maximum_phase_error_deg"], 1.0)
        self.assertLess(
            result["amplitude_halving_check_at_2hz"][
                "maximum_element_relative_difference"
            ],
            1.0e-3,
        )
        self.assertGreater(
            payload["provenance"][
                "device_open_port_spectral_abscissa_per_s"
            ],
            0.0,
        )
        self.assertFalse(payload["model_scope"]["physical_validation"])
        self.assertFalse(payload["model_scope"]["emt_validation"])
        json.dumps(payload, allow_nan=False)

    def test_port_identification_report_and_fixed_contract_preserve_boundaries(
        self,
    ) -> None:
        report = self.client.post(
            "/api/reports/average-dq-port-identification",
            json={"preset_id": "average-dq-smib-verification"},
        )
        custom = self.client.post(
            "/api/average-dq/port-identification",
            json={
                "preset_id": "average-dq-smib-verification",
                "frequencies_hz": [1.0],
            },
        )

        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn("平均值 dq 三频点端口正弦辨识报告", report.text)
        self.assertIn("Y=I·V⁻¹", report.text)
        self.assertIn("设备开端口状态矩阵", report.text)
        self.assertIn("不评价论文稳定性充分条件", report.text)
        self.assertIn("未完成硬件、硬件在环或可信 EMT 确认", report.text)
        self.assertEqual(custom.status_code, 422)


if __name__ == "__main__":
    unittest.main()
