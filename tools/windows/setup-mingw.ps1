[CmdletBinding()]
param(
    [switch]$InstallIfMissing,
    [switch]$DetectOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Msys2InstallerApi = 'https://api.github.com/repos/msys2/msys2-installer/releases/latest'

function Test-MinGWToolchain {
    param([Parameter(Mandatory = $true)][string]$BinDirectory)

    $gcc = Join-Path $BinDirectory 'gcc.exe'
    $assembler = Join-Path $BinDirectory 'as.exe'
    if (-not (Test-Path -LiteralPath $gcc -PathType Leaf) -or
        -not (Test-Path -LiteralPath $assembler -PathType Leaf)) {
        return $false
    }

    $machine = (& $gcc -dumpmachine 2>$null | Select-Object -First 1)
    $gccExitCode = $LASTEXITCODE
    $asVersion = (& $assembler --version 2>&1 | Select-Object -First 1)
    $asExitCode = $LASTEXITCODE

    return ($gccExitCode -eq 0 -and
        [string]$machine -match '^x86_64-w64-mingw32$' -and
        $asExitCode -eq 0 -and
        [string]$asVersion -match 'GNU assembler')
}

function Find-MinGWToolchain {
    $directories = @()

    foreach ($entry in ($env:Path -split ';')) {
        $candidate = $entry.Trim().Trim('"')
        if ($candidate) { $directories += $candidate }
    }

    foreach ($commandName in @('gcc.exe', 'as.exe')) {
        foreach ($command in (Get-Command $commandName -All -ErrorAction SilentlyContinue)) {
            if ($command.Path) {
                $directories += (Split-Path -Parent $command.Path)
            }
        }
    }

    $roots = @()
    if ($env:MSYS2_ROOT) { $roots += $env:MSYS2_ROOT }
    if ($env:LOCALAPPDATA) {
        $roots += (Join-Path $env:LOCALAPPDATA 'MSYS2')
        $roots += (Join-Path $env:LOCALAPPDATA 'Programs\MSYS2')
    }
    $roots += 'C:\msys64'

    foreach ($root in ($roots | Select-Object -Unique)) {
        $directories += (Join-Path $root 'ucrt64\bin')
        $directories += (Join-Path $root 'mingw64\bin')
    }

    foreach ($directory in ($directories | Where-Object { $_ } | Select-Object -Unique)) {
        if (Test-MinGWToolchain -BinDirectory $directory) {
            return (Resolve-Path -LiteralPath $directory).Path
        }
    }
    return $null
}

function Find-MSYS2Root {
    $roots = @()
    if ($env:MSYS2_ROOT) { $roots += $env:MSYS2_ROOT }
    if ($env:LOCALAPPDATA) {
        $roots += (Join-Path $env:LOCALAPPDATA 'MSYS2')
        $roots += (Join-Path $env:LOCALAPPDATA 'Programs\MSYS2')
    }
    $roots += 'C:\msys64'

    foreach ($root in ($roots | Select-Object -Unique)) {
        if (Test-Path -LiteralPath (Join-Path $root 'usr\bin\pacman.exe') -PathType Leaf) {
            return $root
        }
    }
    return $null
}

function Install-MSYS2 {
    param([Parameter(Mandatory = $true)][string]$Root)

    if (-not (Test-Path -LiteralPath $Root)) {
        New-Item -ItemType Directory -Path $Root -Force | Out-Null
    }

    # MSYS2 recommends a short path without spaces or non-ASCII characters.
    if ($Root -match '[^\x20-\x7E]' -or $Root.Contains(' ')) {
        throw "The MSYS2 install path '$Root' contains spaces or non-ASCII characters. Install MSYS2 manually into a short ASCII-only path, then run Orb! Setup again."
    }

    $tempDirectory = Join-Path ([IO.Path]::GetTempPath()) ("orb-msys2-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tempDirectory -Force | Out-Null
    try {
        Write-Host 'Getting the latest stable MSYS2 installer metadata...'
        $release = Invoke-RestMethod -Uri $Msys2InstallerApi -Headers @{
            'Accept' = 'application/vnd.github+json'
            'User-Agent' = 'Orb-Setup/0.2.1.1'
        }
        $installerAsset = $release.assets |
            Where-Object { $_.name -match '^msys2-x86_64-\d{8}\.exe$' } |
            Select-Object -First 1
        if (-not $installerAsset) {
            throw 'The latest MSYS2 release does not contain the expected x86-64 installer.'
        }
        $checksumAsset = $release.assets |
            Where-Object { $_.name -eq ($installerAsset.name + '.sha256') } |
            Select-Object -First 1
        if (-not $checksumAsset) {
            throw 'The MSYS2 release does not provide a SHA-256 checksum; refusing to run an unverified installer.'
        }

        $installerPath = Join-Path $tempDirectory $installerAsset.name
        $checksumPath = Join-Path $tempDirectory ($installerAsset.name + '.sha256')
        Write-Host 'Downloading the official MSYS2 installer...'
        Invoke-WebRequest -Uri $installerAsset.browser_download_url -OutFile $installerPath -UseBasicParsing
        Invoke-WebRequest -Uri $checksumAsset.browser_download_url -OutFile $checksumPath -UseBasicParsing

        $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
        $actualHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            throw 'MSYS2 installer checksum mismatch. The installer will not be run.'
        }

        Write-Host "Installing MSYS2 into $Root..."
        $rootArgument = $Root.Replace('\', '/')
        $arguments = 'in --confirm-command --accept-messages --root "' + $rootArgument + '"'
        $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            throw "MSYS2 installer exited with code $($process.ExitCode)."
        }
    }
    finally {
        Remove-Item -LiteralPath $tempDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-MinGWPackage {
    param([Parameter(Mandatory = $true)][string]$Root)

    $shell = Join-Path $Root 'msys2_shell.cmd'
    if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) {
        throw "MSYS2 shell was not found at '$shell'."
    }

    Write-Host 'Installing the MSYS2 UCRT64 GCC and GNU Binutils packages...'
    & $shell -defterm -no-start -ucrt64 -c 'pacman -S --needed --noconfirm mingw-w64-ucrt-x86_64-gcc'
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "MSYS2 package installation failed with exit code $exitCode."
    }
}

function Add-UserPathEntry {
    param([Parameter(Mandatory = $true)][string]$Directory)

    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @()
    if ($current) { $entries = @($current -split ';' | Where-Object { $_ }) }

    $alreadyPresent = $false
    foreach ($entry in $entries) {
        if ([string]::Equals($entry.Trim().Trim('"').TrimEnd('\'),
                $Directory.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
            $alreadyPresent = $true
            break
        }
    }

    if (-not $alreadyPresent) {
        $entries += $Directory
        [Environment]::SetEnvironmentVariable('Path', ($entries -join ';'), 'User')
    }
    $env:Path = "$Directory;$env:Path"
}

try {
    $binDirectory = Find-MinGWToolchain

    if ($DetectOnly) {
        if (-not $binDirectory) {
            throw 'No working x86-64 MinGW-w64 GCC and GNU assembler were found on PATH or in the standard MSYS2 locations.'
        }
        Write-Host "Detected working MinGW-w64 toolchain: $binDirectory"
        exit 0
    }

    if (-not $binDirectory) {
        if (-not $InstallIfMissing) {
            Write-Warning 'No MinGW-w64 toolchain was found. Native Windows builds remain unavailable; WebAssembly builds do not need MinGW.'
            exit 0
        }

        $root = Find-MSYS2Root
        if (-not $root) {
            if (-not $env:LOCALAPPDATA) {
                throw 'LOCALAPPDATA is unavailable; cannot choose a per-user MSYS2 installation directory.'
            }
            $root = Join-Path $env:LOCALAPPDATA 'Programs\MSYS2'
            Install-MSYS2 -Root $root
        }

        Install-MinGWPackage -Root $root
        $binDirectory = Join-Path $root 'ucrt64\bin'
        if (-not (Test-MinGWToolchain -BinDirectory $binDirectory)) {
            throw 'MinGW-w64 installation finished, but gcc.exe and as.exe did not pass validation.'
        }
    }

    Add-UserPathEntry -Directory $binDirectory
    if (-not (Test-MinGWToolchain -BinDirectory $binDirectory)) {
        throw 'The selected MinGW-w64 toolchain failed its final validation.'
    }

    Write-Host "MinGW-w64 is ready: $binDirectory"
    Write-Host 'The toolchain was added to the current user PATH. Open a new terminal, then run: orb doctor'
    exit 0
}
catch {
    Write-Error ("Orb! MinGW setup failed: " + $_.Exception.Message)
    exit 1
}
