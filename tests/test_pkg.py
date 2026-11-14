import argparse
import importlib.util
import json
import io
import os
import tempfile
import unittest
from unittest.mock import patch
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
        with self.assertRaises(orb_pkg.PackageError):
            orb_pkg.safe_archive_path("repo/src/.." + chr(92) + "escape.orb")
        with self.assertRaises(orb_pkg.PackageError):
            orb_pkg.safe_archive_path("repo/src/module.orb:alternate-stream")

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

    def test_source_files_only_accepts_safe_module_filenames(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("repo/src/network.orb", "pub fn connect() {}")
            bundle.writestr("repo/src/bad-name.orb", "not a valid module filename")
            bundle.writestr("repo/src/nested/helper.orb", "not a sibling module")
        files = orb_pkg.source_files(archive.getvalue(), "network")
        self.assertEqual(sorted(files), ["network.orb"])

    def test_install_reuses_lock_commit_but_update_resolves_again(self):
        old = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = {
                "name": "test",
                "version": "0.1.0",
                "dependencies": {"network": {"repository": "owner/network", "ref": "main"}},
            }
            locked_sha = "a" * 40
            lock = {
                "lockfile_version": 1,
                "packages": {
                    "network": {
                        "repository": "owner/network",
                        "ref": "main",
                        "resolved_ref": locked_sha,
                        "files": {},
                    }
                },
            }
            (root / "orb.json").write_text(json.dumps(manifest), encoding="utf-8")
            (root / "orb.lock.json").write_text(json.dumps(lock), encoding="utf-8")
            seen = []

            def fake_install(project, module, repository, ref, current_lock):
                seen.append(ref)
                return {
                    "module": module,
                    "repository": repository,
                    "ref": ref,
                    "resolved_ref": ref,
                    "files": {},
                }

            try:
                os.chdir(root)
                with patch.object(orb_pkg, "project_root", return_value=root), patch.object(
                    orb_pkg, "install_one", side_effect=fake_install
                ):
                    self.assertEqual(orb_pkg.cmd_sync(argparse.Namespace(command="install", module=None)), 0)
                    self.assertEqual(seen[-1], locked_sha)
                    self.assertEqual(orb_pkg.cmd_sync(argparse.Namespace(command="update", module=None)), 0)
                    self.assertEqual(seen[-1], "main")
            finally:
                os.chdir(old)

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
