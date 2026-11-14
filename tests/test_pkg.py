import importlib.util
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "orb-pkg.py"
SPEC = importlib.util.spec_from_file_location("orb_pkg", MODULE_PATH)
orb_pkg = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(orb_pkg)


class PackageManagerTests(unittest.TestCase):
    def test_module_name_validation(self):
        self.assertTrue(orb_pkg.valid_module_name("math_extra"))
        self.assertFalse(orb_pkg.valid_module_name("../outside"))
        self.assertFalse(orb_pkg.valid_module_name("two words"))

    def test_archive_path_rejects_traversal(self):
        with self.assertRaises(orb_pkg.PackageError):
            orb_pkg.safe_archive_path("../escape.orb")
        with self.assertRaises(orb_pkg.PackageError):
            orb_pkg.safe_archive_path("/absolute/file.orb")
        with self.assertRaises(orb_pkg.PackageError):
            orb_pkg.safe_archive_path("C:/outside/file.orb")

    def test_source_files_extracts_only_sibling_orb_sources(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("owner-repo-123/src/network.orb", "pub fn connect() {}")
            bundle.writestr("owner-repo-123/src/codec.orb", "pub fn encode() {}")
            bundle.writestr("owner-repo-123/README.md", "not installed")
            bundle.writestr("owner-repo-123/tests/test.orb", "not a sibling")
        files = orb_pkg.source_files(archive.getvalue(), "network")
        self.assertEqual(sorted(files), ["codec.orb", "network.orb"])
        self.assertIn(b"connect", files["network.orb"])

    def test_source_files_rejects_traversal_entries(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("repo/src/network.orb", "pub fn connect() {}")
            bundle.writestr("repo/src/../../escape.orb", "unsafe")
        with self.assertRaises(orb_pkg.PackageError):
            orb_pkg.source_files(archive.getvalue(), "network")

    def test_init_creates_manifest_and_lockfile(self):
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                root = orb_pkg.init_project("demo-app")
                self.assertTrue((root / "orb.json").is_file())
                self.assertTrue((root / "orb.lock.json").is_file())
                manifest = orb_pkg.read_json(root / "orb.json", {})
                self.assertEqual(manifest["name"], "demo-app")
                self.assertEqual(manifest["dependencies"], {})
                with self.assertRaises(orb_pkg.PackageError):
                    orb_pkg.init_project("demo-app")
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
