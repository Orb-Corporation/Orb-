# Installing Orb!

Orb! is distributed as a compiler with its standard library and browser runtime built in.

## Quick install

### Linux

```sh
curl -fsSL https://raw.githubusercontent.com/Orb-Corporation/Orb-/main/install.sh | sh
```

### macOS

```sh
curl -fsSL https://raw.githubusercontent.com/Orb-Corporation/Orb-/main/install.sh | sh
```

The current macOS compiler targets x86-64. Apple Silicon requires Rosetta 2.

### Windows

In PowerShell:

```powershell
irm https://raw.githubusercontent.com/Orb-Corporation/Orb-/main/install.ps1 | iex
```

This downloads and opens the graphical Orb! Setup wizard. You can also download
`Orb-Setup-0.2.1.1.exe` from the latest GitHub Release.

## Component selection

The compiler is required. Its standard modules and browser runtime are embedded; they are not
separate components and do not need separate installation.

Optional components:

- Visual Studio Code language extension
- Example projects
- Offline documentation
- Standard-library source files (for contributors)
- Browser host source (for contributors)
- Add the compiler to the current user's PATH
- Install or reuse MSYS2 MinGW-w64 tools for native Windows builds (optional; selected by default)

The Linux/macOS bootstrapper downloads the matching release archive, verifies its SHA-256 checksum,
and installs only the selected components. The Windows installer provides component selection in a
graphical wizard. Its MinGW-w64 task reuses a working toolchain when one is already available; otherwise
it can install the latest stable MSYS2 distribution for the current user, verify the installer SHA-256,
install the UCRT64 GCC toolchain, and add its `bin` directory to the user's PATH. Deselect that task to
skip automatic toolchain setup. MSYS2 is a separate dependency and is not removed when Orb! is uninstalled.

## First run

Open a new terminal and check the toolchain:

```sh
orb version
orb doctor
orb new hello
orb run hello/main.orb
```

The compiler and standard library are self-contained. Git is only required when installing or updating third-party project dependencies with `orb install` / `orb update`; see [PACKAGES.md](PACKAGES.md). Native Windows compilation uses MinGW-w64; Linux
and macOS use their host assembler/linker as described in [PLATFORMS.md](PLATFORMS.md). WebAssembly
compilation does not require a native assembler or linker.

## Build from source instead

If you want to build Orb! from a checkout, see the repository README and run
`python3 tools/install.py` for the source-based installer wizard.
