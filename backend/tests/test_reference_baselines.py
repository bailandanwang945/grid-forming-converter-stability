from __future__ import annotations

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_reference_baselines.py"
SPEC = importlib.util.spec_from_file_location("verify_reference_baselines", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ReferenceBaselineVerifierTest(unittest.TestCase):
    def _baseline(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        source = root / "source" / "main.tex"
        source.parent.mkdir(parents=True)
        source.write_text("fixed source\n", encoding="utf-8")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        (root / "SHA256SUMS.txt").write_text(
            f"{digest}  source/main.tex\n", encoding="utf-8"
        )
        return temporary, root

    def test_valid_manifest_is_verified(self) -> None:
        temporary, root = self._baseline()
        self.addCleanup(temporary.cleanup)
        result = MODULE.verify_manifest(root)
        self.assertEqual(result.checked_files, 1)

    def test_changed_file_is_rejected(self) -> None:
        temporary, root = self._baseline()
        self.addCleanup(temporary.cleanup)
        (root / "source" / "main.tex").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.VerificationError, "SHA-256 mismatch"):
            MODULE.verify_manifest(root)

    def test_missing_file_is_rejected(self) -> None:
        temporary, root = self._baseline()
        self.addCleanup(temporary.cleanup)
        (root / "source" / "main.tex").unlink()
        with self.assertRaisesRegex(MODULE.VerificationError, "is missing"):
            MODULE.verify_manifest(root)

    def test_unlisted_file_is_rejected(self) -> None:
        temporary, root = self._baseline()
        self.addCleanup(temporary.cleanup)
        (root / "source" / "unexpected.bin").write_bytes(b"unexpected")
        with self.assertRaisesRegex(MODULE.VerificationError, "unlisted files"):
            MODULE.verify_manifest(root)

    def test_parent_traversal_is_rejected(self) -> None:
        temporary, root = self._baseline()
        self.addCleanup(temporary.cleanup)
        digest = "0" * 64
        (root / "SHA256SUMS.txt").write_text(
            f"{digest}  ../outside.bin\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(MODULE.VerificationError, "unsafe manifest path"):
            MODULE.parse_manifest(root / "SHA256SUMS.txt")

    def test_absolute_path_is_rejected(self) -> None:
        temporary, root = self._baseline()
        self.addCleanup(temporary.cleanup)
        absolute = (root / "source" / "main.tex").resolve().as_posix()
        (root / "SHA256SUMS.txt").write_text(
            f"{'0' * 64}  {absolute}\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(MODULE.VerificationError, "unsafe manifest path"):
            MODULE.parse_manifest(root / "SHA256SUMS.txt")


if __name__ == "__main__":
    unittest.main()
