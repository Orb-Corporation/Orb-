# Orb! packages

Orb! can resolve project-local modules from `.orb/packages` and additional module
directories listed in `ORB_PATH`. The companion `orb-pkg` tool manages Git-backed
dependencies and records exact commits in `.orb/lock.json`.

## Requirements

- Python 3.11 or newer (uses the standard-library `tomllib` parser).
- Git available on `PATH`.
- The Orb! compiler.

## Create a project

```sh
orb-pkg init --name my_app
```

This creates `orb.toml`, `src/main.orb` and `.orb/lock.json`.

## Add and use a dependency

```sh
orb-pkg add strings_extra https://github.com/example/strings_extra.git
orb-pkg install
orb-pkg list
```

A package repository must expose an Orb! module whose name matches the dependency name.
Supported source locations inside the repository are:

- `strings_extra.orb`
- `strings_extra/strings_extra.orb`
- `src/strings_extra.orb`

The package is checked out into `.orb/packages/strings_extra`, so source code can
import it with `use strings_extra;`. The compiler searches the current project’s
`.orb/packages` directory automatically.

## Update or remove

```sh
orb-pkg update                 # update every dependency to its current Git HEAD
orb-pkg update strings_extra   # update one dependency
orb-pkg remove strings_extra
```

`orb-pkg install` uses the exact commit recorded in `.orb/lock.json`; commit the
lock file to version control for reproducible builds. `orb-pkg add` resolves the
remote HEAD and installs that commit immediately.

## Manifest format

```toml
[package]
name = "my_app"
version = "0.1.0"

[dependencies]
strings_extra = "https://github.com/example/strings_extra.git"
```

## Scope and limitations

This is an intentionally small first package manager, not a central package registry.
Dependencies are Git repositories pinned to commit hashes. There is no semantic-version
solver, registry search, transitive dependency resolution, package signing or automatic
build-script execution. Each dependency must currently be a single Orb! module with the
same name as its package. Git URL dependencies should be reviewed before installing them.
The compiler itself has no Python runtime dependency; Python and Git are required only
for `orb-pkg`.
