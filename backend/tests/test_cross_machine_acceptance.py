import json
import tempfile
import unittest
from pathlib import Path

from backend.core.cross_machine_acceptance import review_cross_machine_evidence


VERSION = "0.4.0-rc2"
COMMIT = "a" * 40
ZIP_HASH = "b" * 64


def _write_valid_evidence(
    directory: Path,
    runtime_schema: str = "gfm-runtime-acceptance/1.2",
) -> None:
    acceptance = {
        "schema_version": "gfm-cross-machine-acceptance/1.1",
        "package": {
            "version": VERSION,
            "commit": COMMIT,
            "working_tree_dirty": False,
            "manifest_file_count": 889,
        },
        "machine": {
            "computer_name": "CLEAN-PC",
            "os_64_bit": True,
            "process_64_bit": True,
        },
        "qualification": {
            "offline_user_declared": True,
            "offline_evidence_kind": "user-declaration-only",
            "clean_environment_user_declared": True,
            "detected_runtime_commands": {
                "python.exe": None,
                "node.exe": None,
                "matlab.exe": None,
            },
            "runtime_commands_absent": True,
            "source_zip_present": True,
            "m5_offline_no_dev_environment_qualified": True,
        },
        "checks": {
            "manifest_verified": True,
            "manifest_errors": [],
            "runtime_exit_code": 0,
            "runtime_status": "passed",
            "port_released": True,
            "functional_passed": True,
        },
        "source_zip": {"sha256": ZIP_HASH, "size_bytes": 123},
    }
    runtime = {
        "schema_version": runtime_schema,
        "status": "passed",
        "checks": {
            "health": "passed",
            "frontend": {"index": "passed", "local_asset_count": 2},
            "fig8": {
                "scenario_id": "fig8_D_0p05",
                "closed_loop_reference": "unstable",
                "uncovered_points": 75,
                "frequency_points": 1000,
            },
            "same_domain": {
                "point_count": 176,
                "classification_counts": {
                    "criterionCoveredStable": 45,
                    "stableNotCovered": 96,
                    "unstableNotCovered": 35,
                    "numericalPending": 0,
                    "consistencyViolation": 0,
                },
            },
            "reduced_order": {
                "preset_id": "reduced-smib-stable",
                "stability": "stable",
                "pole_count": 3,
                "report": "passed",
            },
            "average_dq": {
                "preset_id": "average-dq-smib-verification",
                "stability": "stable",
                "pole_count": 16,
                "closed_rhs_residual_inf": 1.0e-12,
                "active_power_balance_residual_pu": 1.0e-15,
                "port_interconnection_max_abs_error": 1.0e-10,
                "reduction_frequency_relative_error": 0.01,
                "reduction_decay_relative_error": 0.02,
                "hierarchy_scan_point_count": 42,
                "hierarchy_scan_agreement_count": 39,
                "hierarchy_scan_disagreement_count": 3,
                "report": "passed",
            },
        },
    }
    if runtime_schema in (
        "gfm-runtime-acceptance/1.3",
        "gfm-runtime-acceptance/1.4",
        "gfm-runtime-acceptance/1.5",
        "gfm-runtime-acceptance/1.6",
    ):
        runtime["checks"]["fig8_sensitivity"] = {
            "baseline_reconstruction_exact": True,
            "common_scale_invariant_on_tested_range": True,
            "stable_case_remains_covered_in_all_tested_settings": True,
            "nine_point_detects_uncovered_region": False,
            "nine_point_unobserved_full_grid_uncovered_points": 75,
            "report": "passed",
        }
    if runtime_schema in (
        "gfm-runtime-acceptance/1.4",
        "gfm-runtime-acceptance/1.5",
        "gfm-runtime-acceptance/1.6",
    ):
        runtime["checks"]["average_dq_port_identification"] = {
            "preset_id": "average-dq-smib-verification",
            "frequencies_hz": [0.2, 2.0, 20.0],
            "source_amplitude_pu": 1.0e-4,
            "point_count": 3,
            "passed": True,
            "maximum_magnitude_relative_error": 0.0002,
            "maximum_phase_error_deg": 0.03,
            "maximum_harmonic_residual_ratio": 0.001,
            "maximum_voltage_matrix_condition_number": 3.1,
            "amplitude_halving_maximum_element_relative_difference": 0.0003,
            "physical_validation": False,
            "emt_validation": False,
            "report": "passed",
        }
    if runtime_schema in (
        "gfm-runtime-acceptance/1.5",
        "gfm-runtime-acceptance/1.6",
    ):
        runtime["checks"]["mathworks_team_comparison"] = {
            "run_id": "mathworks-team-aligned-eight-point-comparison-v1",
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
            "external_vendor_classification_bracket_pu_per_hz": [
                1.30675,
                1.3215,
            ],
            "team_local_eigenvalue_boundaries_pu_per_hz": [
                0.7586000105,
                0.7560116930,
            ],
            "quantitative_transition_reproduced": False,
            "same_full_physical_model": False,
            "same_classifier": False,
            "nonlinear_team_step_completed": (
                runtime_schema == "gfm-runtime-acceptance/1.6"
            ),
            "paper_sufficient_condition_evaluated": False,
            "physical_hardware_validation": False,
        }
        if runtime_schema == "gfm-runtime-acceptance/1.6":
            runtime["checks"]["mathworks_team_comparison"][
                "nonlinear_team_step_study_id"
            ] = "average-dq-aligned-three-point-nonlinear-step-v1"
            runtime["checks"]["average_dq_aligned_nonlinear_step"] = {
                "study_id": "average-dq-aligned-three-point-nonlinear-step-v1",
                "point_count": 3,
                "solver_agreement_count": 3,
                "outcomes_by_damping": {
                    "0.6": "departed_declared_diagnostic_range",
                    "1.056": "converged_within_horizon",
                    "2.0": "converged_within_horizon",
                },
                "disagreement_coordinate_outcome": "converged_within_horizon",
                "low_damping_exit_event": "grid_current_limit",
                "same_full_model_as_mathworks": False,
                "diagnostic_exit_is_physical_instability": False,
                "emt_validation": False,
                "hardware_validation": False,
            }
    (directory / "cross-machine-acceptance.json").write_text(json.dumps(acceptance))
    (directory / "runtime-evidence.json").write_text(json.dumps(runtime))
    (directory / "acceptance-summary.txt").write_text("passed")
    (directory / "runtime-console.log").write_text("passed")


class CrossMachineAcceptanceTest(unittest.TestCase):
    def test_valid_automated_evidence_still_requires_manual_browser_check(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_valid_evidence(directory)
            review = review_cross_machine_evidence(
                directory,
                expected_version=VERSION,
                expected_commit=COMMIT,
                expected_zip_sha256=ZIP_HASH,
            )
        self.assertTrue(review.automated_evidence_passed)
        self.assertFalse(review.release_accepted)
        self.assertIn("人工确认", " ".join(review.warnings))

    def test_manual_check_closes_release_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_valid_evidence(directory)
            review = review_cross_machine_evidence(
                directory,
                expected_version=VERSION,
                expected_commit=COMMIT,
                expected_zip_sha256=ZIP_HASH,
                manual_browser_check_passed=True,
            )
        self.assertTrue(review.release_accepted)

    def test_wrong_zip_hash_and_changed_research_count_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_valid_evidence(directory)
            runtime_path = directory / "runtime-evidence.json"
            runtime = json.loads(runtime_path.read_text())
            runtime["checks"]["same_domain"]["point_count"] = 175
            runtime_path.write_text(json.dumps(runtime))
            review = review_cross_machine_evidence(
                directory,
                expected_version=VERSION,
                expected_commit=COMMIT,
                expected_zip_sha256="c" * 64,
                manual_browser_check_passed=True,
            )
        self.assertFalse(review.automated_evidence_passed)
        self.assertFalse(review.release_accepted)
        self.assertGreaterEqual(len(review.errors), 2)

    def test_runtime_1p3_requires_sampled_sensitivity_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_valid_evidence(
                directory,
                runtime_schema="gfm-runtime-acceptance/1.3",
            )
            runtime_path = directory / "runtime-evidence.json"
            runtime = json.loads(runtime_path.read_text())
            runtime["checks"]["fig8_sensitivity"][
                "nine_point_detects_uncovered_region"
            ] = True
            runtime_path.write_text(json.dumps(runtime))
            review = review_cross_machine_evidence(
                directory,
                expected_version=VERSION,
                expected_commit=COMMIT,
                expected_zip_sha256=ZIP_HASH,
            )
        self.assertFalse(review.automated_evidence_passed)
        self.assertIn("采样敏感性", " ".join(review.errors))

    def test_runtime_1p4_requires_port_identification_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_valid_evidence(
                directory,
                runtime_schema="gfm-runtime-acceptance/1.4",
            )
            runtime_path = directory / "runtime-evidence.json"
            runtime = json.loads(runtime_path.read_text())
            runtime["checks"]["average_dq_port_identification"][
                "maximum_phase_error_deg"
            ] = 1.1
            runtime_path.write_text(json.dumps(runtime))
            review = review_cross_machine_evidence(
                directory,
                expected_version=VERSION,
                expected_commit=COMMIT,
                expected_zip_sha256=ZIP_HASH,
            )
        self.assertFalse(review.automated_evidence_passed)
        self.assertIn("三频点端口正弦辨识", " ".join(review.errors))

    def test_runtime_1p5_requires_mathworks_team_comparison(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_valid_evidence(
                directory,
                runtime_schema="gfm-runtime-acceptance/1.5",
            )
            runtime_path = directory / "runtime-evidence.json"
            runtime = json.loads(runtime_path.read_text())
            runtime["checks"]["mathworks_team_comparison"][
                "classification_agreement_count"
            ] = 8
            runtime_path.write_text(json.dumps(runtime))
            review = review_cross_machine_evidence(
                directory,
                expected_version=VERSION,
                expected_commit=COMMIT,
                expected_zip_sha256=ZIP_HASH,
            )
        self.assertFalse(review.automated_evidence_passed)
        self.assertIn("八点对照", " ".join(review.errors))

    def test_runtime_1p6_requires_aligned_nonlinear_step_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _write_valid_evidence(
                directory,
                runtime_schema="gfm-runtime-acceptance/1.6",
            )
            runtime_path = directory / "runtime-evidence.json"
            runtime = json.loads(runtime_path.read_text())
            runtime["checks"]["average_dq_aligned_nonlinear_step"][
                "disagreement_coordinate_outcome"
            ] = "numerical_pending"
            runtime_path.write_text(json.dumps(runtime))
            review = review_cross_machine_evidence(
                directory,
                expected_version=VERSION,
                expected_commit=COMMIT,
                expected_zip_sha256=ZIP_HASH,
            )
        self.assertFalse(review.automated_evidence_passed)
        self.assertIn("三点非线性阶跃", " ".join(review.errors))


if __name__ == "__main__":
    unittest.main()
