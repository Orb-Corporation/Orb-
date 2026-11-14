#!/usr/bin/env python3
"""Orb! package manager. Installs source-only Orb! modules from public GitHub repositories."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.request
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath

MANIFEST = "orb.json"
LOCKFILE = "orb.lock.json"
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_TOTAL_SOURCE = 16 * 1024 * 1024
MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SOURCE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\.orb$")


class PackageError(Exception):
    """A user-facing package-manager error."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def valid_module_name(name: str) -> bool:
    return bool(MODULE_RE.fullmatch(name))


def safe_archive_path(name: str) -> PurePosixPath:
    if "\\" in name or "\x00" in name:
        raise PackageError(f"unsafe path separator in source archive: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in ("..", "") for part in path.parts):
        raise PackageError(f"unsafe path in source archive: {name!r}")
    if any(":" in part for part in path.parts):
        raise PackageError(f"unsafe drive path in source archive: {name!r}")
    return path


def project_root() -> Path:
    for directory in (Path.cwd(), *Path.cwd().parents):
        if (directory / MANIFEST).is_file():
            return directory
    raise PackageError(f"{MANIFEST} not found; run 'orb pkg init' first")


def read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise PackageError(f"{path.name} must contain a JSON object")
    return value


def write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def init_project(name: str | None = None) -> Path:
    root = Path.cwd()
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        raise PackageError(f"{MANIFEST} already exists in {root}")
    project_name = name or root.name
    if not valid_module_name(project_name.replace("-", "_")):
        raise PackageError("project name must contain only letters, digits, '_' or '-'")
    write_json_atomic(manifest_path, {
        "name": project_name,
        "version": "0.1.0",
        "description": "",
        "dependencies": {},
    })
    write_json_atomic(root / LOCKFILE, {"lockfile_version": 1, "packages": {}})
    print(f"created {manifest_path}")
    return root


def download_source_archive(repository: str, ref: str) -> tuple[bytes, str]:
    if not REPO_RE.fullmatch(repository) or any(part in (".", "..") for part in repository.split("/")):
        raise PackageError("repository must use the owner/repository form")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Orb-Package-Manager/0.3",
    }
    try:
        if ref == "HEAD":
            request = urllib.request.Request(f"https://api.github.com/repos/{repository}", headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                repository_info = json.load(response)
            ref = repository_info.get("default_branch") or ""
            if not ref:
                raise PackageError("GitHub did not report a default branch for this repository")
        commit_url = f"https://api.github.com/repos/{repository}/commits/{urllib.parse.quote(ref, safe='')}"
        request = urllib.request.Request(commit_url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            commit_info = json.load(response)
        resolved = commit_info.get("sha")
        if not isinstance(resolved, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", resolved):
            raise PackageError("GitHub returned an invalid commit SHA")
        url = f"https://api.github.com/repos/{repository}/zipball/{resolved}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(MAX_ARCHIVE + 1)
    except PackageError:
        raise
    except Exception as exc:
        raise PackageError(f"could not resolve or download {repository}@{ref}: {exc}") from exc
    if len(data) > MAX_ARCHIVE:
        raise PackageError("source archive exceeds the 32 MiB download limit")
    return data, resolved.lower()


def source_files(archive: bytes, module: str) -> dict[str, bytes]:
    try:
        bundle = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise PackageError("GitHub returned an invalid ZIP archive") from exc

    entries: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    for info in bundle.infolist():
        if info.is_dir():
            continue
        path = safe_archive_path(info.filename)
        if info.file_size > MAX_TOTAL_SOURCE:
            raise PackageError(f"archive entry is too large: {info.filename}")
        entries.append((info, path))

    candidates = [
        (info, path) for info, path in entries
        if path.name == f"{module}.orb" and len(path.parts) <= 2
    ]
    if not candidates:
        raise PackageError(
            f"repository has no {module}.orb module file; expected it at the repository root or in src/"
        )
    candidates.sort(key=lambda pair: (len(pair[1].parts), "src" not in pair[1].parts))
    entry_info, entry_path = candidates[0]
    parent = entry_path.parent
    output: dict[str, bytes] = {}
    total = 0
    for info, path in entries:
        if path.parent != parent or not SOURCE_RE.fullmatch(path.name):
            continue
        filename = path.name
        data = bundle.read(info)
        total += len(data)
        if total > MAX_TOTAL_SOURCE:
            raise PackageError("Orb! source files exceed the 16 MiB extraction limit")
        if filename in output:
            raise PackageError(f"duplicate source filename in archive: {filename}")
        output[filename] = data
    if f"{module}.orb" not in output:
        raise PackageError("module entry point was not included in the extracted source set")
    return output


def install_one(root: Path, module: str, repository: str, ref: str, lock: dict) -> dict:
    if not valid_module_name(module):
        raise PackageError(f"invalid module name: {module!r}")
    archive, resolved_ref = download_source_archive(repository, ref)
    files = source_files(archive, module)
    previous = lock.get("packages", {}).get(module, {})
    previous_files = previous.get("files", {})

    # Do not overwrite user files or files modified since the last managed install.
    for filename in files:
        destination = root / filename
        if destination.exists():
            old_hash = previous_files.get(filename)
            if not old_hash:
                raise PackageError(f"refusing to overwrite existing file: {filename}")
            if sha256(destination.read_bytes()) != old_hash:
                raise PackageError(f"{filename} was modified locally; back it up or remove it before updating")

    for filename, old_hash in previous_files.items():
        if filename not in files:
            stale = root / safe_archive_path(filename)
            if stale.is_file() and sha256(stale.read_bytes()) == old_hash:
                stale.unlink()
            elif stale.exists():
                print(f"warning: kept locally modified stale file {filename}", file=sys.stderr)

    for filename, data in files.items():
        temporary = root / (filename + ".orb-pkg.tmp")
        temporary.write_bytes(data)
        temporary.replace(root / filename)

    return {
        "module": module,
        "repository": repository,
        "ref": ref,
        "resolved_ref": resolved_ref,
        "archive_sha256": sha256(archive),
        "files": {filename: sha256(data) for filename, data in sorted(files.items())},
    }


def cmd_add(args: argparse.Namespace) -> int:
    root = project_root()
    manifest = read_json(root / MANIFEST, {})
    lock = read_json(root / LOCKFILE, {"lockfile_version": 1, "packages": {}})
    package = install_one(root, args.module, args.repository, args.ref, lock)
    manifest.setdefault("dependencies", {})[args.module] = {
        "repository": args.repository,
        "ref": args.ref,
    }
    lock.setdefault("packages", {})[args.module] = package
    write_json_atomic(root / MANIFEST, manifest)
    write_json_atomic(root / LOCKFILE, lock)
    print(f"installed {args.module} from {args.repository}@{package['resolved_ref']}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    root = project_root()
    manifest = read_json(root / MANIFEST, {})
    lock = read_json(root / LOCKFILE, {"lockfile_version": 1, "packages": {}})
    dependencies = manifest.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise PackageError("dependencies in orb.json must be an object")
    selected = [args.module] if args.module else sorted(dependencies)
    if not selected:
        print("no dependencies to install")
        return 0
    for module in selected:
        dependency = dependencies.get(module)
        if not isinstance(dependency, dict):
            raise PackageError(f"missing dependency declaration for {module}")
        repository = dependency.get("repository")
        declared_ref = dependency.get("ref", "HEAD")
        if not isinstance(repository, str) or not isinstance(declared_ref, str):
            raise PackageError(f"invalid dependency entry for {module}")
        previous = lock.get("packages", {}).get(module, {})
        use_lock = (
            args.command == "install"
            and previous.get("repository") == repository
            and previous.get("ref") == declared_ref
            and isinstance(previous.get("resolved_ref"), str)
        )
        selected_ref = previous["resolved_ref"] if use_lock else declared_ref
        package = install_one(root, module, repository, selected_ref, lock)
        package["ref"] = declared_ref
        lock.setdefault("packages", {})[module] = package
        action = "restored" if use_lock else "installed"
        print(f"{action} {module} from {repository}@{package['resolved_ref']}")
    write_json_atomic(root / LOCKFILE, lock)
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    root = project_root()
    manifest = read_json(root / MANIFEST, {})
    lock = read_json(root / LOCKFILE, {"lockfile_version": 1, "packages": {}})
    package = lock.get("packages", {}).get(args.module)
    if not package:
        raise PackageError(f"module {args.module!r} is not installed")
    for filename, expected in package.get("files", {}).items():
        target = root / safe_archive_path(filename)
        if target.is_file() and sha256(target.read_bytes()) == expected:
            target.unlink()
        elif target.exists():
            print(f"warning: kept locally modified file {filename}", file=sys.stderr)
    lock["packages"].pop(args.module, None)
    manifest.get("dependencies", {}).pop(args.module, None)
    write_json_atomic(root / MANIFEST, manifest)
    write_json_atomic(root / LOCKFILE, lock)
    print(f"removed {args.module}")
    return 0


def cmd_list() -> int:
    root = project_root()
    lock = read_json(root / LOCKFILE, {"packages": {}})
    packages = lock.get("packages", {})
    if not packages:
        print("no installed Orb! modules")
        return 0
    for name, package in sorted(packages.items()):
        print(f"{name:<18} {package.get('repository', '?')}@{package.get('resolved_ref', '?')}")
    return 0


def cmd_verify() -> int:
    root = project_root()
    lock = read_json(root / LOCKFILE, {"packages": {}})
    failed = False
    for module, package in sorted(lock.get("packages", {}).items()):
        for filename, expected in package.get("files", {}).items():
            target = root / safe_archive_path(filename)
            actual = sha256(target.read_bytes()) if target.is_file() else None
            if actual != expected:
                print(f"FAIL {module}: {filename}")
                failed = True
    if failed:
        return 1
    print("all installed package files match orb.lock.json")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orb pkg", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create orb.json and orb.lock.json")
    init.add_argument("name", nargs="?")
    add = commands.add_parser("add", help="install a module from a public GitHub repository")
    add.add_argument("module", help="Orb! module name used by 'use module;'")
    add.add_argument("repository", help="GitHub repository in owner/name form")
    add.add_argument("ref", nargs="?", default="HEAD", help="branch, tag or commit (default: HEAD)")
    install = commands.add_parser("install", help="install or restore all manifest dependencies")
    install.set_defaults(module=None)
    update = commands.add_parser("update", help="update all dependencies, or one named dependency")
    update.add_argument("module", nargs="?")
    remove = commands.add_parser("remove", help="remove a managed module")
    remove.add_argument("module")
    commands.add_parser("list", help="list installed modules")
    commands.add_parser("verify", help="verify installed files against the lockfile")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init_project(args.name)
            return 0
        if args.command == "add":
            return cmd_add(args)
        if args.command in ("install", "update"):
            return cmd_sync(args)
        if args.command == "remove":
            return cmd_remove(args)
        if args.command == "list":
            return cmd_list()
        if args.command == "verify":
            return cmd_verify()
        parser.error("unknown command")
    except (PackageError, OSError, ValueError, KeyError) as exc:
        print(f"orb pkg: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
