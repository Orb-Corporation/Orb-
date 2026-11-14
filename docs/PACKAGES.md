# Orb! package manager

Orb! 0.3.0 adds a small source-only package manager to the compiler CLI. It installs public
GitHub repositories containing Orb! modules. It does not install native binaries, run package
scripts, or execute code while installing.

Python 3.10 or newer is required for the "orb pkg" commands. The native compiler itself remains a standalone
C program.

## Start a project

~~~sh
orb new hello
cd hello
orb pkg init
~~~

This creates:

- **orb.json** — project metadata and declared dependencies.
- **orb.lock.json** — resolved source revision and SHA-256 hashes for installed module files.

## Add a module

~~~sh
orb pkg add http yourname/orb-http v1.0.0
~~~

The repository must contain **http.orb** either at its root or in **src/**. Orb! source files
next to that entry point are installed too, so local **use helper;** imports keep working.
The package manager places those files beside your project's main.orb; the existing compiler
module resolver can then load them with:

~~~orb
use http;

fn main() {
    // Call the public API exposed by http.orb.
}
~~~

## Maintain dependencies

~~~sh
orb pkg install          # restore dependencies declared in orb.json
orb pkg update           # fetch the latest contents for the declared refs
orb pkg update http      # update one module
orb pkg list             # show installed modules
orb pkg verify           # verify installed source hashes
orb pkg remove http      # remove files managed by that package
~~~

When a branch or HEAD is used, orb.lock.json records the resolved commit and archive hash.
Pin a release tag or commit in "orb pkg add" for reproducible builds. "orb pkg remove"
only deletes files whose contents still match the lockfile; locally edited files are kept.

## Security and current limits

- Only public GitHub repositories are supported.
- The archive is checked for path traversal and size limits before source files are written.
- Only sibling .orb files beside the selected module entry point are copied. No shell scripts,
  binaries, post-install hooks, or arbitrary files are executed.
- Existing user files are never silently overwritten. Updating a locally modified managed file
  is refused until the conflict is resolved.
- Dependencies are explicit. A package's own dependencies are not resolved automatically; add
  each required module to the project separately.
- The package manager does not yet support private repositories, version constraints, registries,
  native libraries, or dependency graphs.

The package format is intentionally simple: a module is a .orb file whose filename matches
the module name used by use.
