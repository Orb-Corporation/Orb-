# Orb! projects and dependencies

Orb! includes a small Git-based package manager. It deliberately has no central registry: dependencies are HTTPS Git repositories, stored inside the project so module resolution stays local.

## Start a project

```sh
mkdir hello
cd hello
orb init hello
orb run main.orb
```

This creates `orb.toml` and a starter `main.orb`. Existing files are not overwritten.

## Add a dependency

```sh
orb install greetings https://github.com/example/orb-greetings.git
```

The repository is cloned into `.orb/packages/greetings/` and registered in the `[dependencies]` section of `orb.toml`. Then import its module:

```orb
use greetings;

fn main() {
    println(greetings.hello());
}
```

A package must provide an Orb! module using one of these entry paths:

- `.orb/packages/<name>/<name>.orb`
- `.orb/packages/<name>/src/<name>.orb`
- `.orb/packages/<name>/lib/<name>.orb`
- `.orb/packages/<name>/src/lib.orb`

The package entry module is imported using the dependency name, and its exported members must be marked `pub`.

## Install, update and inspect

```sh
orb install   # clone all dependencies listed in orb.toml
orb update    # git pull --ff-only for each installed dependency
orb list      # show dependencies and whether they are installed
```

Git must be installed and available on PATH to install or update dependencies. The compiler and standard library remain self-contained; Git is only needed for third-party packages.

## Scope and security

This is the initial package-manager implementation. It clones the default branch with a shallow clone and updates it with fast-forward-only pulls. It does not yet provide semantic version constraints, a registry, dependency checksums, or a lockfile, so builds using moving branches are not yet guaranteed to be reproducible. Review third-party source code before installing it: dependencies are compiled as part of your program and are not sandboxed.
