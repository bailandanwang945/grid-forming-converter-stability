"""Review and archive acceptance-results returned from another Windows PC."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.cross_machine_acceptance import (  # noqa: E402
    review_cross_machine_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-zip-sha256", required=True)
    parser.add_argument("--manual-browser-check-passed", action="store_true")
    parser.add_argument("--operator")
    parser.add_argument("--manual-evidence", type=Path, action="append", default=[])
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=PROJECT_ROOT / "results" / "verification" / "cross-machine",
    )
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    if args.manual_browser_check_passed and (
        not args.operator or not args.manual_evidence
    ):
        parser.error(
            "--manual-browser-check-passed requires --operator and at least one --manual-evidence file"
        )
    missing_manual_files = [path for path in args.manual_evidence if not path.is_file()]
    if missing_manual_files:
        parser.error(f"manual evidence file not found: {missing_manual_files[0]}")
    review = review_cross_machine_evidence(
        args.evidence_directory,
        expected_version=args.expected_version,
        expected_commit=args.expected_commit,
        expected_zip_sha256=args.expected_zip_sha256,
        manual_browser_check_passed=args.manual_browser_check_passed,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    machine = review.machine_name or "unknown-pc"
    safe_machine = "".join(character if character.isalnum() or character in "-_" else "_" for character in machine)
    destination = args.archive_root.resolve() / f"{timestamp}-{safe_machine}"
    destination.mkdir(parents=True, exist_ok=False)
    source = Path(review.evidence_directory)
    for name in (
        "cross-machine-acceptance.json",
        "runtime-evidence.json",
        "acceptance-summary.txt",
        "runtime-console.log",
    ):
        path = source / name
        if path.is_file():
            shutil.copy2(path, destination / name)
    review_payload = review.to_dict() | {"reviewed_at_utc": datetime.now(UTC).isoformat()}
    review_payload["manual_operator"] = args.operator
    review_payload["manual_evidence_files"] = [path.name for path in args.manual_evidence]
    if args.manual_evidence:
        manual_destination = destination / "manual-evidence"
        manual_destination.mkdir()
        for path in args.manual_evidence:
            shutil.copy2(path, manual_destination / path.name)
    (destination / "review.json").write_text(
        json.dumps(review_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Windows 异机验收复核记录",
        "",
        f"- 软件版本：`{review.version}`",
        f"- 构建提交：`{review.commit}`",
        f"- 验收电脑：`{review.machine_name}`",
        f"- 自动证据：{'通过' if review.automated_evidence_passed else '未通过'}",
        f"- 人工浏览器检查：{'通过' if review.manual_browser_check_passed else '未确认'}",
        f"- 人工检查人：`{args.operator or '未记录'}`",
        f"- 人工证据附件：{len(args.manual_evidence)} 个",
        f"- 发布验收结论：{'通过' if review.release_accepted else '未完成'}",
        "",
        "## 错误",
        "",
        *(f"- {item}" for item in review.errors),
        *( ["- 无"] if not review.errors else [] ),
        "",
        "## 提醒",
        "",
        *(f"- {item}" for item in review.warnings),
        *( ["- 无"] if not review.warnings else [] ),
        "",
    ]
    (destination / "review.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Evidence archived: {destination}")
    if review.release_accepted:
        print("GFM_CROSS_MACHINE_RELEASE_ACCEPTED")
        return 0
    if review.automated_evidence_passed:
        print("GFM_CROSS_MACHINE_MANUAL_CHECK_PENDING")
        return 2
    print("GFM_CROSS_MACHINE_EVIDENCE_REJECTED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
