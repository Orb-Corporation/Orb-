#!/usr/bin/env python3
"""Integration tests for the Git-based Orb! package manager."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "orb-pkg.py"


def run(args: list[str], cwd: Path, *, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != expect:
        raise AssertionError(
            f"orb-pkg {' '.join(args)} returned {result.returncode}, expected {expect}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.strip()


def commit_package(repo: Path, text: str) -> str:
    source = repo / "src" / "demo.orb"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(text, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "update demo module")
    return git(repo, "rev-parse", "HEAD")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="orb-pkg-test-") as temporary:
        root = Path(temporary)
        project = root / "project"
        package = root / "demo-repository"
        project.mkdir()
        package.mkdir()

        git(package, "init", "-q")
        git(package, "config", "user.name", "Orb Test")
        git(package, "config", "user.email", "orb-test@example.invalid")
        first = commit_package(package, "pub fn answer() -> i64 { return 42; }\n")

        run(["init", "--name", "sample"], project)
        run(["add", "demo", str(package)], project)
        lock = json.loads((project / ".orb" / "lock.json").read_text(encoding="utf-8"))
        assert lock["dependencies"]["demo"]["commit"] == first
        assert (project / ".orb" / "packages" / "demo" / "src" / "demo.orb").is_file()

        run(["install"], project)
        listed = run(["list"], project)
        assert "demo: installed" in listed.stdout

        second = commit_package(package, "pub fn answer() -> i64 { return 43; }\n")
        run(["update", "demo"], project)
        lock = json.loads((project / ".orb" / "lock.json").read_text(encoding="utf-8"))
        assert lock["dependencies"]["demo"]["commit"] == second
        installed = (project / ".orb" / "packages" / "demo" / "src" / "demo.orb").read_text(encoding="utf-8")
        assert "return 43" in installed

        run(["remove", "demo"], project)
        lock = json.loads((project / ".orb" / "lock.json").read_text(encoding="utf-8"))
        assert "demo" not in lock["dependencies"]
        assert not (project / ".orb" / "packages" / "demo").exists()

    print("orb-pkg tests: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
