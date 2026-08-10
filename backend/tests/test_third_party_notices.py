import json
from pathlib import Path
import tempfile
import unittest

from scripts.generate_third_party_notices import _copy_license_files, _node_components


class ThirdPartyNoticeTests(unittest.TestCase):
    def test_copied_license_paths_are_package_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source" / "LICENSE"
            source.parent.mkdir()
            source.write_text("example license", encoding="utf-8")

            copied = _copy_license_files(
                [("LICENSE", source)], root / "package" / "licenses", root / "package"
            )

            self.assertEqual(copied[0]["packaged_path"], "licenses/01-LICENSE")
            self.assertFalse(Path(copied[0]["packaged_path"]).is_absolute())

    def test_node_inventory_excludes_development_only_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            frontend = root / "web"
            production = frontend / "node_modules" / "production-package"
            development = frontend / "node_modules" / "development-package"
            production.mkdir(parents=True)
            development.mkdir(parents=True)
            (frontend / "package-lock.json").write_text(
                json.dumps(
                    {
                        "packages": {
                            "": {},
                            "node_modules/production-package": {"version": "1.0.0"},
                            "node_modules/development-package": {
                                "version": "2.0.0",
                                "dev": True,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            (production / "package.json").write_text(
                json.dumps(
                    {"name": "production-package", "version": "1.0.0", "license": "MIT"}
                ),
                encoding="utf-8",
            )
            (production / "LICENSE").write_text("MIT", encoding="utf-8")
            (development / "package.json").write_text(
                json.dumps(
                    {"name": "development-package", "version": "2.0.0", "license": "MIT"}
                ),
                encoding="utf-8",
            )

            components = _node_components(frontend, root / "package")

            self.assertEqual([component["name"] for component in components], ["production-package"])
            self.assertEqual(
                components[0]["license_files"][0]["packaged_path"],
                "licenses/web/production-package-1.0.0/01-LICENSE",
            )


if __name__ == "__main__":
    unittest.main()
