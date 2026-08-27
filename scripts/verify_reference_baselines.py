"""Verify the fixed paper and author-code baselines without network access."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


MANIFEST_LINE = re.compile(r"^([0-9a-fA-F]{64})  (.+)$")
ARXIV_BASELINES = ("arxiv-2510.20544v1", "arxiv-2510.20544v2")
CORE_PDF = Path("references/papers/Cifelli_2025_Decentralized_Small_Gain_Phase_GFM.pdf")
CORE_PDF_SHA256 = "78c0b5f926a80f71f5c3391b4d115d332d8cb1817452ebcad77d3a606b73ec49"
AUTHOR_REPOSITORY = Path("external/cifelli-small-gain-phase")
AUTHOR_COMMIT = "ef67c7a4ac84e4e1142e95b072d241db89eb64ba"
AUTHOR_TAG = "v1.0.0"
AUTHOR_LICENSE = Path(
    "packaging/research-licenses/Cifelli-Anta-author-code-v1.0.0-LICENSE.txt"
)
AUTHOR_LICENSE_SHA256 = (
    "0f8deba5d0be7dc0177ba107408b2d848fb3ca23ce4c625fe48b048b25bf2bf4"
)


class VerificationError(RuntimeError):
    """Raised when a fixed baseline differs from its trusted expectation."""


@dataclass(frozen=True)
class ManifestResult:
    baseline: str
    checked_files: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(manifest_path: Path) -> dict[Path, str]:
    entries: dict[Path, str] = {}
    for line_number, raw_line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        match = MANIFEST_LINE.fullmatch(raw_line)
        if match is None:
            raise VerificationError(
                f"invalid manifest line {line_number} in {manifest_path}"
            )
        # Re-create the path from normalized components so validation is
        # identical on Windows and POSIX test hosts.
        relative = Path(*Path(match.group(2).replace("\\", "/")).parts)
        if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
            raise VerificationError(
                f"unsafe manifest path at line {line_number}: {match.group(2)}"
            )
        if relative in entries:
            raise VerificationError(f"duplicate manifest path: {relative.as_posix()}")
        entries[relative] = match.group(1).lower()
    if not entries:
        raise VerificationError(f"empty manifest: {manifest_path}")
    return entries


def verify_manifest(baseline_root: Path) -> ManifestResult:
    baseline_root = baseline_root.resolve()
    manifest_path = baseline_root / "SHA256SUMS.txt"
    if not manifest_path.is_file():
        raise VerificationError(f"manifest is missing: {manifest_path}")
    entries = parse_manifest(manifest_path)
    for relative, expected in entries.items():
        target = (baseline_root / relative).resolve()
        if baseline_root not in target.parents:
            raise VerificationError(f"manifest path escapes baseline root: {relative}")
        if not target.is_file():
            raise VerificationError(f"manifest file is missing: {target}")
        actual = sha256_file(target)
        if actual != expected:
            raise VerificationError(
                f"SHA-256 mismatch: {target} expected={expected} actual={actual}"
            )

    allowed_unlisted = {Path("README.md"), Path("SHA256SUMS.txt")}
    actual_files = {
        path.relative_to(baseline_root)
        for path in baseline_root.rglob("*")
        if path.is_file()
    }
    unexpected = sorted(actual_files - set(entries) - allowed_unlisted)
    if unexpected:
        names = ", ".join(path.as_posix() for path in unexpected)
        raise VerificationError(f"unlisted files in {baseline_root}: {names}")
    return ManifestResult(baseline_root.name, len(entries))


def verify_expected_file(project_root: Path, relative: Path, expected: str) -> None:
    target = project_root / relative
    if not target.is_file():
        raise VerificationError(f"required baseline file is missing: {target}")
    actual = sha256_file(target)
    if actual != expected:
        raise VerificationError(
            f"SHA-256 mismatch: {target} expected={expected} actual={actual}"
        )


def git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VerificationError(f"git inspection failed for {repository}: {detail}")
    return result.stdout.strip()


def verify_author_repository(repository: Path) -> None:
    if git_output(repository, "rev-parse", "HEAD") != AUTHOR_COMMIT:
        raise VerificationError(f"author repository is not at fixed commit {AUTHOR_COMMIT}")
    tags = git_output(repository, "tag", "--points-at", "HEAD").splitlines()
    if AUTHOR_TAG not in tags:
        raise VerificationError(f"author repository HEAD is not tagged {AUTHOR_TAG}")


def verify_project(project_root: Path, strict_local_archive: bool = False) -> list[str]:
    messages: list[str] = []
    source_root = project_root / "references" / "source"
    for name in ARXIV_BASELINES:
        result = verify_manifest(source_root / name)
        messages.append(f"{result.baseline}: {result.checked_files} files verified")

    verify_expected_file(project_root, AUTHOR_LICENSE, AUTHOR_LICENSE_SHA256)
    messages.append("author license snapshot: verified")

    core_pdf = project_root / CORE_PDF
    if core_pdf.is_file():
        verify_expected_file(project_root, CORE_PDF, CORE_PDF_SHA256)
        messages.append("core paper PDF: verified")
    elif strict_local_archive:
        raise VerificationError(f"local core paper PDF is missing: {core_pdf}")
    else:
        messages.append("core paper PDF: absent (optional local archive)")

    author_repository = project_root / AUTHOR_REPOSITORY
    if (author_repository / ".git").exists():
        verify_author_repository(author_repository)
        messages.append(f"author repository: {AUTHOR_TAG} / {AUTHOR_COMMIT[:12]} verified")
    elif strict_local_archive:
        raise VerificationError(f"local author repository is missing: {author_repository}")
    else:
        messages.append("author repository: absent (optional local archive)")
    return messages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify tracked paper sources and optional local research archives."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--strict-local-archive",
        action="store_true",
        help="also require the ignored core PDF and full author repository",
    )
    arguments = parser.parse_args()
    try:
        messages = verify_project(
            arguments.project_root.resolve(), arguments.strict_local_archive
        )
    except VerificationError as error:
        print(f"GFM_REFERENCE_BASELINE_FAILED: {error}", file=sys.stderr)
        return 1
    for message in messages:
        print(f"[GFM Reference] {message}")
    print("GFM_REFERENCE_BASELINE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
