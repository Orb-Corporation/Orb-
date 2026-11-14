#!/usr/bin/env python3
"""Small Git-URL package manager for Orb! projects (Python 3.11+ and Git required)."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path.cwd()
MANIFEST = ROOT / "orb.toml"
ORB_DIR = ROOT / ".orb"
PACKAGES = ORB_DIR / "packages"
LOCK = ORB_DIR / "lock.json"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class PackageError(Exception):
    pass


def run(args: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    try:
        result = subprocess.run(
            args, cwd=cwd, check=True, text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except FileNotFoundError as exc:
        raise PackageError(f"Required program not found: {args[0]} (install Git and ensure it is on PATH)") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise PackageError(f"Command failed: {' '.join(args)}" + (f"\n{detail}" if detail else "")) from exc
    return result.stdout.strip() if capture else ""


def valid_name(name: str) -> None:
    if not NAME_RE.fullmatch(name):
        raise PackageError(f"Invalid package name: {name!r}")


def read_manifest() -> dict:
    if not MANIFEST.is_file():
        raise PackageError("orb.toml not found. Run 'orb-pkg init' first.")
    try:
        data = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PackageError(f"Cannot read orb.toml: {exc}") from exc
    package = data.get("package")
    if not isinstance(package, dict) or not isinstance(package.get("name"), str):
        raise PackageError("orb.toml needs [package] with a name.")
    deps = data.get("dependencies", {})
    if not isinstance(deps, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in deps.items()):
        raise PackageError("[dependencies] must map package names to Git URLs.")
    for name in deps:
        valid_name(name)
    return data


def write_manifest(data: dict) -> None:
    package = data["package"]
    lines = ["[package]", f"name = {json.dumps(package['name'])}", f'version = {json.dumps(package.get("version", "0.1.0"))}']
    if package.get("description"):
        lines.append(f"description = {json.dumps(package['description'])}")
    lines += ["", "[dependencies]"]
    for name, url in sorted(data.get("dependencies", {}).items()):
        lines.append(f"{name} = {json.dumps(url)}")
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_lock() -> dict:
    if not LOCK.is_file():
        return {"lock_version": 1, "dependencies": {}}
    try:
        data = json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageError(f"Cannot read lock file: {exc}") from exc
    if data.get("lock_version") != 1 or not isinstance(data.get("dependencies"), dict):
        raise PackageError("Unsupported or invalid .orb/lock.json.")
    return data


def write_lock(data: dict) -> None:
    ORB_DIR.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def valid_git_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme in ("https", "http", "ssh", "git") and parsed.netloc:
        return
    if url.startswith("git@") and ":" in url:
        return
    if Path(url).exists():
        return
    raise PackageError("Dependency URL must be an HTTPS/SSH Git URL or an existing local Git repository path.")


def remote_head(url: str) -> str:
    output = run(["git", "ls-remote", url, "HEAD"], capture=True)
    if not output:
        raise PackageError(f"Could not resolve HEAD for {url}")
    return output.split()[0]


def package_source_exists(path: Path, name: str) -> bool:
    candidates = [path / f"{name}.orb", path / name / f"{name}.orb", path / "src" / f"{name}.orb"]
    return any(candidate.is_file() for candidate in candidates)


def checkout(url: str, commit: str, destination: Path, name: str) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    run(["git", "init", "-q"], cwd=destination)
    run(["git", "remote", "add", "origin", url], cwd=destination)
    run(["git", "fetch", "--depth=1", "origin", commit], cwd=destination)
    run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=destination)
    if not package_source_exists(destination, name):
        shutil.rmtree(destination, ignore_errors=True)
        raise PackageError(
            f"Repository for '{name}' has no {name}.orb, {name}/{name}.orb or src/{name}.orb module."
        )


def install_locked(data: dict, lock: dict) -> None:
    deps = data.get("dependencies", {})
    locked = lock.get("dependencies", {})
    for name, url in sorted(deps.items()):
        valid_git_url(url)
        item = locked.get(name)
        if item and item.get("url") == url and item.get("commit"):
            commit = item["commit"]
        else:
            commit = remote_head(url)
            locked[name] = {"url": url, "commit": commit}
        target = PACKAGES / name
        if target.exists():
            current_url = ""
            try:
                current_url = run(["git", "remote", "get-url", "origin"], cwd=target, capture=True)
                current_commit = run(["git", "rev-parse", "HEAD"], cwd=target, capture=True)
            except PackageError:
                current_commit = ""
            if current_url == url and current_commit == commit and package_source_exists(target, name):
                print(f"  already installed {name} ({commit[:12]})")
                continue
        print(f"  installing {name} ({commit[:12]})")
        checkout(url, commit, target, name)
    for name in list(locked):
        if name not in deps:
            del locked[name]
    lock["dependencies"] = locked
    write_lock(lock)


def cmd_init(name: str) -> None:
    valid_name(name)
    if MANIFEST.exists():
        raise PackageError("orb.toml already exists.")
    MANIFEST.write_text(
        "[package]\n"
        f"name = {json.dumps(name)}\n"
        'version = "0.1.0"\n'
        "\n[dependencies]\n",
        encoding="utf-8",
    )
    (ROOT / "src").mkdir(exist_ok=True)
    main = ROOT / "src" / "main.orb"
    if not main.exists():
        main.write_text(
            f"// {name} - an Orb! application\n\n"
            "fn main() {\n"
            f'    println("Hello from {name}!");\n'
            "}\n",
            encoding="utf-8",
        )
    ORB_DIR.mkdir(exist_ok=True)
    write_lock({"lock_version": 1, "dependencies": {}})
    print(f"Created Orb! project '{name}'.")
    print("Build with: orb build src/main.orb")


def cmd_add(name: str, url: str) -> None:
    valid_name(name)
    valid_git_url(url)
    data = read_manifest()
    data.setdefault("dependencies", {})[name] = url
    write_manifest(data)
    lock = read_lock()
    # Resolve now and install a reproducible commit immediately.
    commit = remote_head(url)
    lock.setdefault("dependencies", {})[name] = {"url": url, "commit": commit}
    write_lock(lock)
    install_locked(data, lock)


def cmd_install() -> None:
    data = read_manifest()
    lock = read_lock()
    print("Installing Orb! dependencies:")
    install_locked(data, lock)
    if not data.get("dependencies"):
        print("  no dependencies declared")


def cmd_update(names: list[str]) -> None:
    data = read_manifest()
    lock = read_lock()
    deps = data.get("dependencies", {})
    selected = names or list(deps)
    for name in selected:
        if name not in deps:
            raise PackageError(f"'{name}' is not declared in [dependencies].")
        valid_git_url(deps[name])
        commit = remote_head(deps[name])
        lock.setdefault("dependencies", {})[name] = {"url": deps[name], "commit": commit}
    install_locked(data, lock)


def cmd_remove(name: str) -> None:
    data = read_manifest()
    if name not in data.get("dependencies", {}):
        raise PackageError(f"'{name}' is not declared in [dependencies].")
    del data["dependencies"][name]
    write_manifest(data)
    lock = read_lock()
    lock.get("dependencies", {}).pop(name, None)
    write_lock(lock)
    shutil.rmtree(PACKAGES / name, ignore_errors=True)
    print(f"Removed dependency '{name}'.")


def cmd_list() -> None:
    data = read_manifest()
    lock = read_lock()
    deps = data.get("dependencies", {})
    if not deps:
        print("No dependencies.")
        return
    for name, url in sorted(deps.items()):
        item = lock.get("dependencies", {}).get(name, {})
        commit = item.get("commit", "not locked")
        installed = package_source_exists(PACKAGES / name, name)
        state = "installed" if installed else "not installed"
        print(f"{name}: {state}, {commit[:12]} — {url}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="orb-pkg", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create orb.toml and src/main.orb")
    init.add_argument("--name", default=re.sub(r"[^A-Za-z0-9_]", "_", ROOT.name))
    add = sub.add_parser("add", help="add and install a Git dependency")
    add.add_argument("name")
    add.add_argument("url")
    sub.add_parser("install", help="install exact commits from .orb/lock.json")
    update = sub.add_parser("update", help="update all dependencies or selected ones")
    update.add_argument("names", nargs="*")
    remove = sub.add_parser("remove", help="remove a dependency")
    remove.add_argument("name")
    sub.add_parser("list", help="list dependencies and install state")
    args = parser.parse_args()

    try:
        if args.command == "init":
            cmd_init(args.name)
        elif args.command == "add":
            cmd_add(args.name, args.url)
        elif args.command == "install":
            cmd_install()
        elif args.command == "update":
            cmd_update(args.names)
        elif args.command == "remove":
            cmd_remove(args.name)
        elif args.command == "list":
            cmd_list()
        return 0
    except PackageError as exc:
        print(f"orb-pkg: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
