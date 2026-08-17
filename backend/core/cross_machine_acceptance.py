"""Validate and normalize returned cross-machine release evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXPECTED_CLASSIFICATION_COUNTS = {
    "criterionCoveredStable": 45,
    "stableNotCovered": 96,
    "unstableNotCovered": 35,
    "numericalPending": 0,
    "consistencyViolation": 0,
}


@dataclass(frozen=True)
class CrossMachineReview:
    evidence_directory: str
    version: str | None
    commit: str | None
    machine_name: str | None
    automated_evidence_passed: bool
    manual_browser_check_passed: bool
    release_accepted: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "gfm-cross-machine-review/1.0",
            "evidence_directory": self.evidence_directory,
            "version": self.version,
            "commit": self.commit,
            "machine_name": self.machine_name,
            "automated_evidence_passed": self.automated_evidence_passed,
            "manual_browser_check_passed": self.manual_browser_check_passed,
            "release_accepted": self.release_accepted,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"缺少证据文件：{path.name}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"无法读取 {path.name}：{exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path.name} 顶层必须是 JSON 对象")
        return {}
    return value


def review_cross_machine_evidence(
    evidence_directory: str | Path,
    *,
    expected_version: str,
    expected_commit: str,
    expected_zip_sha256: str,
    manual_browser_check_passed: bool = False,
) -> CrossMachineReview:
    """Review one returned acceptance-results leaf directory.

    This deliberately recomputes the qualification decision instead of trusting
    the booleans emitted on the other computer.
    """

    directory = Path(evidence_directory).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    acceptance = _read_json(directory / "cross-machine-acceptance.json", errors)
    runtime = _read_json(directory / "runtime-evidence.json", errors)

    package = acceptance.get("package") if isinstance(acceptance.get("package"), dict) else {}
    machine = acceptance.get("machine") if isinstance(acceptance.get("machine"), dict) else {}
    qualification = (
        acceptance.get("qualification")
        if isinstance(acceptance.get("qualification"), dict)
        else {}
    )
    checks = acceptance.get("checks") if isinstance(acceptance.get("checks"), dict) else {}
    source_zip = (
        acceptance.get("source_zip") if isinstance(acceptance.get("source_zip"), dict) else {}
    )

    if acceptance.get("schema_version") != "gfm-cross-machine-acceptance/1.1":
        errors.append("异机证据版本不是 gfm-cross-machine-acceptance/1.1")
    runtime_schema = runtime.get("schema_version")
    if runtime_schema not in (
        "gfm-runtime-acceptance/1.2",
        "gfm-runtime-acceptance/1.3",
        "gfm-runtime-acceptance/1.4",
        "gfm-runtime-acceptance/1.5",
    ):
        errors.append("运行时证据版本不是受支持的 1.2、1.3、1.4 或 1.5")
    if package.get("version") != expected_version:
        errors.append("软件版本与指定候选包不一致")
    if package.get("commit") != expected_commit:
        errors.append("构建提交与指定候选包不一致")
    if package.get("working_tree_dirty") is not False:
        errors.append("候选包不是从干净工作树构建")
    if not isinstance(package.get("manifest_file_count"), int) or package.get(
        "manifest_file_count", 0
    ) <= 0:
        errors.append("发布清单文件数无效")

    actual_zip_hash = str(source_zip.get("sha256", "")).lower()
    if actual_zip_hash != expected_zip_sha256.lower():
        errors.append("回传证据中的原始 ZIP SHA-256 与指定候选包不一致")
    if not isinstance(source_zip.get("size_bytes"), int) or source_zip.get("size_bytes", 0) <= 0:
        errors.append("回传证据没有有效的原始 ZIP 大小")

    required_cross_checks = {
        "manifest_verified": True,
        "runtime_exit_code": 0,
        "runtime_status": "passed",
        "port_released": True,
        "functional_passed": True,
    }
    for field, expected in required_cross_checks.items():
        if checks.get(field) != expected:
            errors.append(f"异机检查字段 {field} 未达到要求")
    if checks.get("manifest_errors") not in ([], None):
        errors.append("发布清单报告了文件错误")

    detected = qualification.get("detected_runtime_commands")
    detected_values = detected.values() if isinstance(detected, dict) else ()
    recomputed_environment_qualified = all(
        (
            qualification.get("offline_user_declared") is True,
            qualification.get("clean_environment_user_declared") is True,
            qualification.get("runtime_commands_absent") is True,
            qualification.get("source_zip_present") is True,
            qualification.get("m5_offline_no_dev_environment_qualified") is True,
            machine.get("os_64_bit") is True,
            machine.get("process_64_bit") is True,
            not any(value for value in detected_values),
        )
    )
    if not recomputed_environment_qualified:
        errors.append("断网、无开发环境和 64 位运行资格未形成一致证据")
    if qualification.get("offline_evidence_kind") == "user-declaration-only":
        warnings.append("物理断网仍属于操作者声明，不能由脚本独立证明")

    runtime_checks = runtime.get("checks") if isinstance(runtime.get("checks"), dict) else {}
    frontend = (
        runtime_checks.get("frontend") if isinstance(runtime_checks.get("frontend"), dict) else {}
    )
    fig8 = runtime_checks.get("fig8") if isinstance(runtime_checks.get("fig8"), dict) else {}
    fig8_sensitivity = (
        runtime_checks.get("fig8_sensitivity")
        if isinstance(runtime_checks.get("fig8_sensitivity"), dict)
        else {}
    )
    same_domain = (
        runtime_checks.get("same_domain")
        if isinstance(runtime_checks.get("same_domain"), dict)
        else {}
    )
    reduced = (
        runtime_checks.get("reduced_order")
        if isinstance(runtime_checks.get("reduced_order"), dict)
        else {}
    )
    average_dq = (
        runtime_checks.get("average_dq")
        if isinstance(runtime_checks.get("average_dq"), dict)
        else {}
    )
    port_identification = (
        runtime_checks.get("average_dq_port_identification")
        if isinstance(
            runtime_checks.get("average_dq_port_identification"), dict
        )
        else {}
    )
    mathworks_team_comparison = (
        runtime_checks.get("mathworks_team_comparison")
        if isinstance(runtime_checks.get("mathworks_team_comparison"), dict)
        else {}
    )
    if runtime.get("status") != "passed" or runtime_checks.get("health") != "passed":
        errors.append("运行时健康检查未通过")
    if frontend.get("index") != "passed" or frontend.get("local_asset_count", 0) < 2:
        errors.append("打包网页资源检查未通过")
    if (
        fig8.get("scenario_id") != "fig8_D_0p05"
        or fig8.get("closed_loop_reference") != "unstable"
        or fig8.get("uncovered_points") != 75
        or fig8.get("frequency_points") != 1000
    ):
        errors.append("Fig. 8 固定失稳工况证据与冻结基线不一致")
    if runtime_schema in (
        "gfm-runtime-acceptance/1.3",
        "gfm-runtime-acceptance/1.4",
        "gfm-runtime-acceptance/1.5",
    ):
        if (
            fig8_sensitivity.get("baseline_reconstruction_exact") is not True
            or fig8_sensitivity.get(
                "common_scale_invariant_on_tested_range"
            )
            is not True
            or fig8_sensitivity.get(
                "stable_case_remains_covered_in_all_tested_settings"
            )
            is not True
            or fig8_sensitivity.get(
                "nine_point_detects_uncovered_region"
            )
            is not False
            or fig8_sensitivity.get(
                "nine_point_unobserved_full_grid_uncovered_points"
            )
            != 75
            or fig8_sensitivity.get("report") != "passed"
        ):
            errors.append("Fig. 8 采样敏感性证据与冻结基线不一致")
    elif runtime_schema == "gfm-runtime-acceptance/1.2":
        warnings.append("旧版运行时证据未包含 Fig. 8 采样敏感性检查")
    if same_domain.get("point_count") != 176 or same_domain.get(
        "classification_counts"
    ) != EXPECTED_CLASSIFICATION_COUNTS:
        errors.append("同域 176 点分类证据与冻结基线不一致")
    if (
        reduced.get("preset_id") != "reduced-smib-stable"
        or reduced.get("stability") != "stable"
        or reduced.get("pole_count") != 3
        or reduced.get("report") != "passed"
    ):
        errors.append("独立低频模型或打印报告证据未通过")
    if (
        average_dq.get("preset_id") != "average-dq-smib-verification"
        or average_dq.get("stability") != "stable"
        or average_dq.get("pole_count") != 16
        or average_dq.get("closed_rhs_residual_inf", 1.0) >= 1.0e-9
        or abs(average_dq.get("active_power_balance_residual_pu", 1.0))
        >= 1.0e-8
        or average_dq.get("port_interconnection_max_abs_error", 1.0) >= 1.0e-6
        or average_dq.get("reduction_frequency_relative_error", 1.0) >= 0.05
        or average_dq.get("reduction_decay_relative_error", 1.0) >= 0.05
        or average_dq.get("hierarchy_scan_point_count") != 42
        or average_dq.get("hierarchy_scan_agreement_count") != 39
        or average_dq.get("hierarchy_scan_disagreement_count") != 3
        or average_dq.get("report") != "passed"
    ):
        errors.append("16状态平均值 dq 模型或打印报告证据未通过")
    if runtime_schema in (
        "gfm-runtime-acceptance/1.4",
        "gfm-runtime-acceptance/1.5",
    ):
        if (
            port_identification.get("preset_id")
            != "average-dq-smib-verification"
            or port_identification.get("frequencies_hz") != [0.2, 2.0, 20.0]
            or port_identification.get("source_amplitude_pu") != 1.0e-4
            or port_identification.get("point_count") != 3
            or port_identification.get("passed") is not True
            or port_identification.get(
                "maximum_magnitude_relative_error", 1.0
            )
            >= 0.01
            or port_identification.get("maximum_phase_error_deg", 1.0)
            >= 1.0
            or port_identification.get(
                "maximum_harmonic_residual_ratio", 1.0
            )
            >= 0.02
            or port_identification.get(
                "maximum_voltage_matrix_condition_number", 1.0e9
            )
            >= 100.0
            or port_identification.get(
                "amplitude_halving_maximum_element_relative_difference", 1.0
            )
            >= 1.0e-3
            or port_identification.get("physical_validation") is not False
            or port_identification.get("emt_validation") is not False
            or port_identification.get("report") != "passed"
        ):
            errors.append("三频点端口正弦辨识或打印报告证据未通过")
    elif runtime_schema in (
        "gfm-runtime-acceptance/1.2",
        "gfm-runtime-acceptance/1.3",
    ):
        warnings.append("旧版运行时证据未包含三频点端口正弦辨识检查")

    if runtime_schema == "gfm-runtime-acceptance/1.5":
        roots = mathworks_team_comparison.get(
            "team_local_eigenvalue_boundaries_pu_per_hz", []
        )
        disagreement_points = mathworks_team_comparison.get(
            "disagreement_points", []
        )
        expected_disagreement = {
            "scr": 5.0,
            "damping_mathworks_pu_per_hz": 1.056,
            "external_vendor_outcome": "Unstable",
            "team_pre_step_stability": "stable",
            "team_post_step_stability": "stable",
        }
        if (
            mathworks_team_comparison.get("point_count") != 8
            or mathworks_team_comparison.get("classification_agreement_count") != 7
            or mathworks_team_comparison.get("classification_disagreement_count")
            != 1
            or disagreement_points != [expected_disagreement]
            or mathworks_team_comparison.get(
                "external_vendor_classification_bracket_pu_per_hz"
            )
            != [1.30675, 1.3215]
            or not isinstance(roots, list)
            or len(roots) != 2
            or not all(isinstance(value, (int, float)) for value in roots)
            or abs(roots[0] - 0.7586000105) >= 1.0e-8
            or abs(roots[1] - 0.7560116930) >= 1.0e-8
            or mathworks_team_comparison.get(
                "quantitative_transition_reproduced"
            )
            is not False
            or mathworks_team_comparison.get("same_full_physical_model")
            is not False
            or mathworks_team_comparison.get("same_classifier") is not False
            or mathworks_team_comparison.get("nonlinear_team_step_completed")
            is not False
            or mathworks_team_comparison.get(
                "paper_sufficient_condition_evaluated"
            )
            is not False
            or mathworks_team_comparison.get("physical_hardware_validation")
            is not False
        ):
            errors.append("MathWorks 外部证据与团队模型八点对照证据不一致")
    elif runtime_schema in (
        "gfm-runtime-acceptance/1.2",
        "gfm-runtime-acceptance/1.3",
        "gfm-runtime-acceptance/1.4",
    ):
        warnings.append("旧版运行时证据未包含 MathWorks—团队模型八点对照")

    for required_file in ("acceptance-summary.txt", "runtime-console.log"):
        if not (directory / required_file).is_file():
            errors.append(f"缺少可读审计附件：{required_file}")

    automated_passed = not errors
    if automated_passed and not manual_browser_check_passed:
        warnings.append("自动证据已通过，但浏览器交互、CSV/HTML 导出和安全软件行为尚待人工确认")
    return CrossMachineReview(
        evidence_directory=str(directory),
        version=package.get("version"),
        commit=package.get("commit"),
        machine_name=machine.get("computer_name"),
        automated_evidence_passed=automated_passed,
        manual_browser_check_passed=manual_browser_check_passed,
        release_accepted=automated_passed and manual_browser_check_passed,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
