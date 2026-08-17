from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULT_ROOT = PROJECT_ROOT / "results" / "mathworks-gfm-external-validation"

FROZEN_ARTIFACTS = {
    "scr_step": (
        "mathworks_gfm_scr_step_study.json",
        "169730ed706fa7bdaf147c071dd62c4cb6522fcd5714912184d51e5ef58860f7",
    ),
    "damping_factorial": (
        "mathworks_gfm_scr_damping_factorial.json",
        "90173e9ba8f9e554ff7058af2e004a741c37f4ed7340feb78064d045f0033fea",
    ),
    "damping_transition": (
        "mathworks_gfm_scr5_damping_transition.json",
        "9e7f58c79e8e58658538f42eb9982526dd61862a3d6d68ed0964b7ad4c38c518",
    ),
}


class MathWorksExternalEvidenceError(RuntimeError):
    """Raised when a frozen external-validation artifact cannot be trusted."""


def _load_frozen_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise MathWorksExternalEvidenceError(
            f"缺少冻结的 MathWorks 外部验证产物：{path.name}。"
        ) from error
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise MathWorksExternalEvidenceError(
            f"MathWorks 外部验证产物 {path.name} 的 SHA-256 不匹配。"
        )
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MathWorksExternalEvidenceError(
            f"MathWorks 外部验证产物 {path.name} 不是有效 JSON。"
        ) from error


def load_mathworks_external_evidence(
    result_root: Path = DEFAULT_RESULT_ROOT,
) -> dict[str, Any]:
    """Load the three frozen studies without rerunning MATLAB or Simulink."""

    studies = {
        name: _load_frozen_json(result_root / filename, digest)
        for name, (filename, digest) in FROZEN_ARTIFACTS.items()
    }
    transition = studies["damping_transition"]
    factorial = studies["damping_factorial"]
    step = studies["scr_step"]

    source_commits = {study["source"]["commit"] for study in studies.values()}
    if source_commits != {"a65692b004637acb38b2f8c64db7dcf47efe24c7"}:
        raise MathWorksExternalEvidenceError("三个外部验证产物的上游提交不一致。")

    return {
        "run_id": "mathworks-gfm-external-evidence-v1",
        "status": "completed",
        "mode": "frozen-read-only-external-validation-evidence",
        "source": {
            "provider": "MathWorks",
            "release_tag": step["source"]["releaseTag"],
            "commit": next(iter(source_commits)),
            "matlab_release": step["source"]["matlabRelease"],
        },
        "summary": {
            "three_point_vendor_outcomes": [
                point["vendorOutcome"] for point in step["points"]
            ],
            "factorial_stable_point_count": sum(
                point["vendorOutcome"] == "Stable" for point in factorial["points"]
            ),
            "factorial_point_count": len(factorial["points"]),
            "vendor_classification_bracket_pu": [
                transition["result"]["unstableLowerDampingPu"],
                transition["result"]["stableUpperDampingPu"],
            ],
            "vendor_classification_bracket_width_pu": transition["result"][
                "bracketWidthPu"
            ],
            "project_tracking_observed_bracket_pu": [
                transition["result"]["trackingFailureLowerDampingPu"],
                transition["result"]["trackingPassUpperDampingPu"],
            ],
            "project_tracking_target_achieved": transition["result"][
                "trackingTargetWidthAchieved"
            ],
        },
        "studies": studies,
        "artifact_sha256": {
            name: digest for name, (_, digest) in FROZEN_ARTIFACTS.items()
        },
        "scope": {
            "claim_level": "frozen-external-time-domain-evidence-summary",
            "reruns_matlab_or_simulink": False,
            "closed_loop_eigenvalue_boundary": False,
            "continuous_stability_proof": False,
            "physical_hardware_validation": False,
            "paper_sufficient_condition_evaluated": False,
            "statement": (
                "本页只读汇总固定版本 MathWorks GFM 模型的离散时域证据；"
                "供应商分类与项目跟踪门分列，不把区间称为临界阻尼或特征根边界。"
            ),
        },
    }
