"""Generate third-party notices from the actual packaged executable and web lock."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


LICENSE_PREFIXES = ("license", "licence", "copying", "notice", "copyright")
ARCHIVE_MODULE_PATTERN = re.compile(
    r"'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)'\s*$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_component(value: str) -> str:
    result = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-.")
    return result or "unknown"


def _license_label(distribution: metadata.Distribution) -> str:
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return expression.strip()
    classifiers = [
        value.split(" :: ")[-1]
        for value in distribution.metadata.get_all("Classifier", [])
        if value.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    return "SEE INCLUDED LICENSE FILES"


def _archive_roots(executable: Path) -> set[str]:
    viewer = shutil.which("pyi-archive_viewer")
    if viewer is None:
        candidate = Path(sys.executable).parent / "Scripts" / "pyi-archive_viewer.exe"
        if candidate.is_file():
            viewer = str(candidate)
    if viewer is None:
        raise RuntimeError("pyi-archive_viewer is required on the build machine")
    result = subprocess.run(
        [viewer, "-l", "-r", str(executable)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"unable to inspect PyInstaller archive: {result.stderr.strip()}")
    roots: set[str] = set()
    for line in result.stdout.splitlines():
        match = ARCHIVE_MODULE_PATTERN.search(line)
        if match:
            roots.add(match.group(1).split(".")[0])
    internal = executable.parent / "_internal"
    for path in internal.iterdir():
        if (
            path.is_dir()
            and not path.name.endswith(".dist-info")
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", path.name)
        ):
            roots.add(path.name)
    return roots


def _copy_license_files(
    files: list[tuple[str, Path]], destination: Path, output_root: Path
) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    destination.mkdir(parents=True, exist_ok=True)
    seen_hashes: set[str] = set()
    for index, (source_label, source) in enumerate(files, start=1):
        digest = _sha256(source)
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        target = destination / f"{index:02d}-{_safe_component(source.name)}"
        shutil.copy2(source, target)
        copied.append(
            {
                "source_path": source_label.replace("\\", "/"),
                "packaged_path": target.relative_to(output_root).as_posix(),
                "sha256": digest,
            }
        )
    return copied


def _python_components(executable: Path, output_root: Path) -> list[dict[str, Any]]:
    package_map = metadata.packages_distributions()
    names = {
        distribution_name
        for root in _archive_roots(executable)
        for distribution_name in package_map.get(root, [])
    }
    names.add("PyInstaller")
    components: list[dict[str, Any]] = []
    for name in sorted(names, key=str.casefold):
        distribution = metadata.distribution(name)
        canonical_name = distribution.metadata["Name"]
        license_sources: list[tuple[str, Path]] = []
        for item in distribution.files or ():
            if item.name.lower().startswith(LICENSE_PREFIXES):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    license_sources.append((str(item), source))
        if not license_sources:
            raise RuntimeError(
                f"no license file found for packaged Python distribution {canonical_name}"
            )
        component_dir = (
            output_root
            / "licenses"
            / "python"
            / _safe_component(f"{canonical_name}-{distribution.version}")
        )
        copied = _copy_license_files(license_sources, component_dir, output_root)
        components.append(
            {
                "ecosystem": "python",
                "name": canonical_name,
                "version": distribution.version,
                "declared_license": _license_label(distribution),
                "license_files": copied,
            }
        )
    return components


def _node_components(frontend_root: Path, output_root: Path) -> list[dict[str, Any]]:
    lock = json.loads((frontend_root / "package-lock.json").read_text(encoding="utf-8"))
    components: list[dict[str, Any]] = []
    for relative_path, lock_entry in sorted(lock["packages"].items()):
        if not relative_path.startswith("node_modules/") or lock_entry.get("dev") is True:
            continue
        package_root = frontend_root / relative_path
        package_json = package_root / "package.json"
        if not package_json.is_file():
            raise RuntimeError(f"production Node package is not installed: {relative_path}")
        package = json.loads(package_json.read_text(encoding="utf-8"))
        license_value = package.get("license") or package.get("licenses")
        if isinstance(license_value, list):
            license_value = " OR ".join(
                value.get("type", str(value)) if isinstance(value, dict) else str(value)
                for value in license_value
            )
        license_sources = [
            (path.name, path)
            for path in sorted(package_root.iterdir())
            if path.is_file() and path.name.lower().startswith(LICENSE_PREFIXES)
        ]
        if not license_sources:
            raise RuntimeError(f"no license file found for production Node package {package['name']}")
        component_dir = (
            output_root
            / "licenses"
            / "web"
            / _safe_component(f"{package['name']}-{package['version']}")
        )
        copied = _copy_license_files(license_sources, component_dir, output_root)
        components.append(
            {
                "ecosystem": "web",
                "name": package["name"],
                "version": package["version"],
                "declared_license": str(license_value or "SEE INCLUDED LICENSE FILES"),
                "license_files": copied,
            }
        )
    return components


def _runtime_components(output_root: Path) -> list[dict[str, Any]]:
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError(f"Python runtime license is missing: {python_license}")
    destination = output_root / "licenses" / "runtime" / _safe_component(
        f"Python-{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    copied = _copy_license_files(
        [("LICENSE.txt", python_license)], destination, output_root
    )
    return [
        {
            "ecosystem": "runtime",
            "name": "CPython",
            "version": ".".join(str(value) for value in sys.version_info[:3]),
            "declared_license": "PSF-2.0",
            "license_files": copied,
        },
        {
            "ecosystem": "runtime",
            "name": "Microsoft Visual C++ and Universal C Runtime files",
            "version": "build-machine redistributable",
            "declared_license": "Microsoft redistributable runtime terms",
            "license_files": [],
            "note": "Runtime DLLs are included by the Windows Python/PyInstaller toolchain.",
        },
    ]


def _research_source_component(author_license: Path, output_root: Path) -> dict[str, Any]:
    if not author_license.is_file():
        raise RuntimeError(f"author repository license is missing: {author_license}")
    destination = output_root / "licenses" / "research-source" / "cifelli-anta-author-code"
    copied = _copy_license_files([("LICENSE", author_license)], destination, output_root)
    return {
        "ecosystem": "research-source",
        "name": "Cifelli-Anta Fig. 8 author code and derived regression fixtures",
        "version": "v1.0.0 / ef67c7a4ac84e4e1142e95b072d241db89eb64ba",
        "declared_license": "MIT",
        "license_files": copied,
        "note": "The package contains derived numerical fixtures, not the author MATLAB repository.",
    }


def _write_notices(components: list[dict[str, Any]], output_root: Path) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for component in components:
        grouped.setdefault(component["ecosystem"], []).append(component)
    lines = [
        "# Third-Party Notices",
        "",
        "This file describes third-party components actually included in the Windows package.",
        "It does not grant a license for the team's own source code; that project-level decision remains pending.",
        "Full license texts are stored under `licenses/` and are covered by `release-manifest.json`.",
        "",
        "The arXiv paper PDF/TeX, MATLAB, Simulink, Simplus repositories, and the complete author MATLAB repository are not included in this package.",
        "",
    ]
    titles = {
        "python": "Python distributions embedded by PyInstaller",
        "web": "Web production dependencies embedded in the JavaScript bundle",
        "runtime": "Runtime components",
        "research-source": "Research-source attribution",
    }
    for ecosystem in ("python", "web", "runtime", "research-source"):
        lines.extend([f"## {titles[ecosystem]}", "", "| Component | Version | Declared license |", "|---|---|---|"])
        for component in sorted(grouped.get(ecosystem, []), key=lambda item: item["name"].casefold()):
            lines.append(
                f"| {component['name']} | {component['version']} | {component['declared_license']} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Boundary",
            "",
            "- Component names and versions are generated from the built PyInstaller archive and the locked production web dependency tree.",
            "- A declared license label is only an index; the included original license text is authoritative.",
            "- Third-party trademarks and authorship remain with their respective owners.",
            "- This inventory is a build artifact and must be regenerated whenever dependencies or the packaging toolchain change.",
            "",
        ]
    )
    (output_root / "THIRD_PARTY_NOTICES.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--frontend-root", type=Path, required=True)
    parser.add_argument("--author-license", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    components = [
        *_python_components(args.executable.resolve(), output_root),
        *_node_components(args.frontend_root.resolve(), output_root),
        *_runtime_components(output_root),
        _research_source_component(args.author_license.resolve(), output_root),
    ]
    _write_notices(components, output_root)
    payload = {
        "schema_version": "gfm-third-party-sbom/1.0",
        "inventory_basis": {
            "python": "modules present in the recursive PyInstaller archive listing",
            "web": "non-development package-lock entries installed for the production bundle",
            "research_source": "fixed author repository license recorded in docs/EXTERNAL_RESOURCES.md",
        },
        "component_count": len(components),
        "components": sorted(
            components, key=lambda item: (item["ecosystem"], item["name"].casefold())
        ),
    }
    (output_root / "third-party-sbom.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "GFM_THIRD_PARTY_INVENTORY_OK "
        f"components={len(components)} "
        f"python={sum(item['ecosystem'] == 'python' for item in components)} "
        f"web={sum(item['ecosystem'] == 'web' for item in components)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
