"""Archive verified run inputs, refusing drift rather than updating old hashes."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(run_file):
    run_file = run_file.resolve()
    if not run_file.is_relative_to(ROOT):
        raise ValueError("Run file must be within this project")
    run = json.loads(run_file.read_text(encoding="utf-8"))
    if run["status"] != "complete":
        raise ValueError("Cannot finalize an incomplete research run")
    target = run_file.parent / "source-snapshot"
    if target.exists():
        raise FileExistsError(target)
    sources = []
    for name, expected in run["source_hashes"].items():
        relative = Path(name.replace("\\", "/"))
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Input manifest escapes project root")
        provenance = "current-source-matches-run-hash"
        if digest(path) != expected:
            restored = run_file.parent / "plan-at-run-reconstructed.md"
            if relative.as_posix() != "results/automatic-transform-search/plan.md" or not restored.exists() or digest(restored) != expected:
                raise AssertionError(f"Input drift: {name}")
            path = restored
            provenance = "post-run-reconstructed-plan-matches-original-hash-not-contemporaneous-snapshot"
        sources.append((relative, path, expected, provenance))
    target.mkdir()
    rows = []
    for relative, path, expected, provenance in sources:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        if digest(destination) != expected:
            raise AssertionError(f"Archived input mismatch: {relative}")
        rows.append({"path": relative.as_posix(), "sha256": expected, "provenance": provenance})
    manifest = {"status": "verified", "run_file_sha256": digest(run_file), "inputs": rows}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    reread = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    for row in reread["inputs"]:
        if digest(target / row["path"]) != row["sha256"]:
            raise AssertionError("Snapshot readback mismatch")
    print(f"VERIFIED_SOURCE_SNAPSHOT {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_file", type=Path)
    freeze(parser.parse_args().run_file)
