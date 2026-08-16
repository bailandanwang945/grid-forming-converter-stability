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
    if runtime_schema == "gfm-runtime-acceptance/1.3":
        runtime["checks"]["fig8_sensitivity"] = {
            "baseline_reconstruction_exact": True,
            "common_scale_invariant_on_tested_range": True,
            "stable_case_remains_covered_in_all_tested_settings": True,
            "nine_point_detects_uncovered_region": False,
            "nine_point_unobserved_full_grid_uncovered_points": 75,
            "report": "passed",
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


if __name__ == "__main__":
    unittest.main()
