from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

from backend.launcher import _find_available_port, run


def acceptance_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(
            '<!doctype html><div id="root"></div>'
            '<script src="/assets/app.js"></script>'
        )

    @app.get("/assets/app.js")
    def asset() -> Response:
        return Response("console.log('ok')", media_type="text/javascript")

    @app.post("/api/analysis/run")
    def fig8() -> dict:
        return {
            "scenario_id": "fig8_D_0p05",
            "summary": {
                "closed_loop_reference": "unstable",
                "uncovered_points": 75,
                "frequency_points": 1000,
            },
        }

    @app.get("/api/analysis/fig8-sensitivity")
    def fig8_sensitivity() -> dict:
        return {
            "status": "completed",
            "summary": {
                "baseline_reconstruction_exact": True,
                "common_scale_invariant_on_tested_range": True,
                "stable_case_remains_covered_in_all_tested_settings": True,
            },
            "cases": [
                {
                    "case_id": "fig8_D_0p05",
                    "frequency_density": [
                        {
                            "requested_point_count": 9,
                            "detects_uncovered_region": False,
                            "unobserved_full_grid_uncovered_points": 75,
                        }
                    ],
                }
            ],
        }

    @app.get("/api/reports/fig8-sensitivity")
    def fig8_sensitivity_report() -> HTMLResponse:
        return HTMLResponse(
            "漏检75个完整网格未覆盖样点；不评价论文连续全频定理"
        )

    @app.get("/api/comparison/fig8-domain")
    def comparison() -> dict:
        return {
            "status": "completed",
            "rows": [{}] * 176,
            "summary": {
                "classificationCounts": {
                    "criterionCoveredStable": 45,
                    "stableNotCovered": 96,
                    "unstableNotCovered": 35,
                    "numericalPending": 0,
                    "consistencyViolation": 0,
                }
            },
        }

    @app.post("/api/reduced-order/analyze")
    def reduced_order() -> dict:
        return {
            "status": "completed",
            "input_validation": {"status": "passed"},
            "result": {
                "stability": "stable",
                "poles": [{}, {}, {}],
            },
        }

    @app.post("/api/reports/reduced-order")
    def reduced_order_report() -> HTMLResponse:
        return HTMLResponse("输入拓扑与参数；不是完整 dq 模型结论")

    @app.post("/api/average-dq/analyze")
    def average_dq() -> dict:
        return {
            "status": "completed",
            "operating_point": {
                "closed_rhs_residual_inf": 1.0e-12,
                "active_power_balance_residual_pu": 1.0e-15,
            },
            "result": {
                "stability": "stable",
                "poles": [{}] * 16,
                "port_interconnection_max_abs_error": 1.0e-10,
                "quasisteady_reduction_comparison": {
                    "oscillation_frequency_relative_error": 0.01,
                    "decay_rate_relative_error": 0.02,
                },
            },
        }

    @app.post("/api/reports/average-dq")
    def average_dq_report() -> HTMLResponse:
        return HTMLResponse(
            "端口互联误差；不是论文算例复现；不宣称完成工程模型确认"
        )

    @app.post("/api/average-dq/scan")
    def average_dq_scan() -> dict:
        return {
            "status": "completed",
            "result": {
                "point_count": 42,
                "counts": {
                    "valid": 42,
                    "invalid": 0,
                    "agreement": 39,
                    "disagreement": 3,
                },
            },
        }

    @app.post("/api/average-dq/port-identification")
    def average_dq_port_identification() -> dict:
        return {
            "status": "completed",
            "result": {
                "summary": {
                    "passed": True,
                    "maximum_magnitude_relative_error": 0.0002,
                    "maximum_phase_error_deg": 0.03,
                    "maximum_harmonic_residual_ratio": 0.001,
                    "maximum_voltage_matrix_condition_number": 3.1,
                },
                "contract": {
                    "frequencies_hz": [0.2, 2.0, 20.0],
                    "source_amplitude_pu": 1.0e-4,
                },
                "points": [{"passed": True}] * 3,
                "amplitude_halving_check_at_2hz": {
                    "maximum_element_relative_difference": 0.0003,
                },
            },
            "model_scope": {
                "physical_validation": False,
                "emt_validation": False,
            },
        }

    @app.post("/api/reports/average-dq-port-identification")
    def average_dq_port_identification_report() -> HTMLResponse:
        return HTMLResponse(
            "Y=I·V⁻¹；不评价论文稳定性充分条件；"
            "未完成硬件、硬件在环或可信 EMT 确认"
        )

    @app.get("/api/evidence/mathworks-team-comparison")
    def mathworks_team_comparison() -> dict:
        return {
            "run_id": "mathworks-team-aligned-eight-point-comparison-v1",
            "status": "completed",
            "summary": {
                "point_count": 8,
                "classification_agreement_count": 7,
                "classification_disagreement_count": 1,
                "disagreement_points": [
                    {
                        "scr": 5.0,
                        "damping_mathworks_pu_per_hz": 1.056,
                        "external_vendor_outcome": "Unstable",
                        "team_pre_step_stability": "stable",
                        "team_post_step_stability": "stable",
                    }
                ],
            },
            "boundary_comparison": {
                "external_vendor_classification_bracket_pu_per_hz": [
                    1.30675,
                    1.3215,
                ],
                "team_local_eigenvalue_boundaries": [
                    {"damping_mw_equivalent_pu_per_hz": 0.7586000105},
                    {"damping_mw_equivalent_pu_per_hz": 0.7560116930},
                ],
                "external_and_team_boundaries_are_same_evidence_type": False,
                "quantitative_transition_reproduced": False,
            },
            "scope": {
                "same_full_physical_model": False,
                "same_classifier": False,
                "nonlinear_team_step_completed": True,
                "nonlinear_team_step_study_id": (
                    "average-dq-aligned-three-point-nonlinear-step-v1"
                ),
                "paper_sufficient_condition_evaluated": False,
                "physical_hardware_validation": False,
            },
        }

    @app.get("/api/evidence/average-dq-aligned-nonlinear-step")
    def average_dq_aligned_nonlinear_step() -> dict:
        points = []
        for damping, outcome, event_name, power_settling, frequency_settling in (
            (0.6, "departed_declared_diagnostic_range", "grid_current_limit", None, None),
            (1.056, "converged_within_horizon", None, 1.82, 2.11),
            (2.0, "converged_within_horizon", None, 0.75, 0.77),
        ):
            points.append(
                {
                    "damping_mathworks_pu_per_hz": damping,
                    "study_outcome": outcome,
                    "solver_agreement": True,
                    "solver_results": [
                        {
                            "method": method,
                            "outcome": outcome,
                            "event_name": event_name,
                            "completed_time_s": 1.47 if event_name else 8.0,
                            "active_power_settling_time_s": power_settling,
                            "frequency_settling_time_s": frequency_settling,
                        }
                        for method in ("Radau", "LSODA")
                    ],
                }
            )
        return {
            "schema_version": "gfm-average-dq-nonlinear-step-study/1.0",
            "study_id": "average-dq-aligned-three-point-nonlinear-step-v1",
            "status": "completed",
            "summary": {
                "point_count": 3,
                "solver_agreement_count": 3,
                "disagreement_coordinate_outcome": "converged_within_horizon",
            },
            "points": points,
            "scope": {
                "same_full_model_as_mathworks": False,
                "diagnostic_exit_is_physical_instability": False,
                "emt_validation": False,
                "hardware_validation": False,
            },
        }

    return app


class ReleaseLauncherTest(unittest.TestCase):
    def test_default_port_search_skips_an_existing_listener(self) -> None:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            occupied_port = int(listener.getsockname()[1])
            selected_port = _find_available_port(occupied_port, 20)

        self.assertGreater(selected_port, occupied_port)
        self.assertLess(selected_port, occupied_port + 20)

    def test_default_port_search_reports_a_bounded_failure(self) -> None:
        with patch("backend.launcher._port_is_available", return_value=False):
            with self.assertRaisesRegex(
                RuntimeError,
                "No available local port was found",
            ):
                _find_available_port(8000, 3)

    def test_smoke_writes_cross_machine_runtime_evidence(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])

        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "runtime-evidence.json"
            with patch(
                "backend.launcher.create_production_app",
                return_value=acceptance_app(),
            ):
                exit_code = run(
                    port,
                    open_browser=False,
                    smoke_test=True,
                    evidence_file=str(evidence_path),
                )

            self.assertEqual(exit_code, 0)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "passed")
            self.assertEqual(
                evidence["schema_version"],
                "gfm-runtime-acceptance/1.6",
            )
            self.assertEqual(
                evidence["checks"]["fig8"]["uncovered_points"],
                75,
            )
            self.assertFalse(
                evidence["checks"]["fig8_sensitivity"][
                    "nine_point_detects_uncovered_region"
                ]
            )
            self.assertEqual(
                evidence["checks"]["average_dq_aligned_nonlinear_step"][
                    "disagreement_coordinate_outcome"
                ],
                "converged_within_horizon",
            )
            self.assertEqual(
                evidence["checks"]["average_dq_aligned_nonlinear_step"][
                    "low_damping_exit_event"
                ],
                "grid_current_limit",
            )
            self.assertEqual(
                evidence["checks"]["fig8_sensitivity"]["report"],
                "passed",
            )
            self.assertEqual(
                evidence["checks"]["mathworks_team_comparison"][
                    "classification_agreement_count"
                ],
                7,
            )
            self.assertFalse(
                evidence["checks"]["mathworks_team_comparison"][
                    "quantitative_transition_reproduced"
                ]
            )
            self.assertEqual(
                evidence["checks"]["same_domain"]["point_count"],
                176,
            )
            self.assertEqual(
                evidence["checks"]["reduced_order"]["stability"],
                "stable",
            )
            self.assertEqual(
                evidence["checks"]["reduced_order"]["report"],
                "passed",
            )
            self.assertEqual(
                evidence["checks"]["average_dq"]["pole_count"],
                16,
            )
            self.assertEqual(
                evidence["checks"]["average_dq"]["report"],
                "passed",
            )
            self.assertEqual(
                evidence["checks"]["average_dq"][
                    "hierarchy_scan_disagreement_count"
                ],
                3,
            )
            self.assertEqual(
                evidence["checks"]["average_dq_port_identification"][
                    "frequencies_hz"
                ],
                [0.2, 2.0, 20.0],
            )
            self.assertTrue(
                evidence["checks"]["average_dq_port_identification"][
                    "passed"
                ]
            )
            self.assertEqual(
                evidence["checks"]["average_dq_port_identification"][
                    "report"
                ],
                "passed",
            )


if __name__ == "__main__":
    unittest.main()
