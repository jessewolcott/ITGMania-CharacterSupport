<#
.SYNOPSIS
    Run fontpatch without installing Python yourself.

.DESCRIPTION
    On first run, downloads a private copy of Python (the official embeddable
    build from python.org) plus Pillow and fonttools (from PyPI) into
    .runtime\ next to this script, checks every download against a pinned
    SHA-256, then runs src\fontpatch.py with it. Nothing is installed
    system-wide: delete .runtime\ (or run with -Clean) to remove it.

    Later runs reuse .runtime\ and need no network.

    Any other argument is passed to fontpatch.py unchanged, e.g. -v,
    --text "...", -o out.png, --thai-font C:\path\font.ttf.

.PARAMETER Command
    The fontpatch command: install (default), scan, verify, preview,
    uninstall.

.PARAMETER Root
    ITGmania folder(s), the one containing Themes. Defaults to the usual
    locations.

.PARAMETER Theme
    Only these themes.

.PARAMETER Scripts
    install only: some of vietnamese, thai, korean, chinese.

.PARAMETER Clean
    Delete the private runtime and exit.

.EXAMPLE
    .\Install-FontPatch.ps1
.EXAMPLE
    .\Install-FontPatch.ps1 scan -v
.EXAMPLE
    .\Install-FontPatch.ps1 install -Root D:\Games\ITGmania -Scripts thai,korean
#>
# Deliberately not [CmdletBinding()]: that adds PowerShell's common parameters,
# which would swallow fontpatch's own flags (-v becomes -Verbose, -o is
# ambiguous). Unknown arguments land in $args and are passed through.
param(
    [ValidateSet('install', 'scan', 'verify', 'preview', 'uninstall')]
    [string]$Command = 'install',
    [string[]]$Root,
    [string[]]$Theme,
    [string[]]$Scripts,
    [switch]$Clean
)
$ExtraArgs = $args

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'    # 5.1's progress bar slows downloads badly

# Pinned versions and hashes. To update: change a version, then replace its
# hashes with the ones python.org / PyPI publish for the new files.
$PythonVersion = '3.13.16'
$PythonSha = @{
    amd64 = '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297'
    arm64 = '790d097697a2020477549a6764d89d22194c88d6e42caebcb2db63791e004c94'
    win32 = '0a3b162281b0a8e4d95d748e40ec2db9927086c7ec4231a5c8d29f91a1c2ba89'
}
$Packages = @(
    @{ Name = 'pillow'; Version = '12.3.0'; Files = @{
        amd64 = @('pillow-12.3.0-cp313-cp313-win_amd64.whl', '1cca606cd25738df4ed873d5ad46bbdb3d83b5cbca291f6b4ff13a4df6b0bbe8')
        arm64 = @('pillow-12.3.0-cp313-cp313-win_arm64.whl', 'b629de27fda84b42cde7edef0d85f13b958b47f6e9bbcbba9b673c562a89bd8b')
        win32 = @('pillow-12.3.0-cp313-cp313-win32.whl', 'a876864214e136f0eb367788dbd7df045f4806801518e2cfe9e13229cfe06d8f') } },
    # pure-Python build: one file for every architecture
    @{ Name = 'fonttools'; Version = '4.66.1'; Files = @{
        any = @('fonttools-4.66.1-py3-none-any.whl', '7234ae9e28db64273fbbfa72caebd0a97e3bdba6b05064114741b9539ef339d0') } }
)

$Here = $PSScriptRoot
$RuntimeDir = Join-Path $Here '.runtime'
$PyDir = Join-Path $RuntimeDir "python-$PythonVersion"
$PyExe = Join-Path $PyDir 'python.exe'
$Marker = Join-Path $PyDir '.complete'
$Entry = Join-Path $Here 'src\fontpatch.py'

function Write-Step($msg) { Write-Host "  $msg" -ForegroundColor Cyan }

function Get-Arch {
    # 32-bit PowerShell on 64-bit Windows reports x86 here, the real arch in W6432
    $a = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    switch ($a) {
        'AMD64' { 'amd64' }
        'ARM64' { 'arm64' }
        'x86' { 'win32' }
        default { throw "Unsupported processor architecture: $a" }
    }
}

function Get-Verified([string]$url, [string]$dest, [string]$sha) {
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    $got = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($got -ne $sha) {
        Remove-Item -LiteralPath $dest -Force
        throw "Checksum mismatch for $(Split-Path $url -Leaf) - expected $sha, got $got. Download refused."
    }
}

function Expand-Zip([string]$zip, [string]$dest) {
    # ZipFile, not Expand-Archive: 5.1's Expand-Archive refuses .whl files
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $dest)
}

function Install-Runtime {
    $arch = Get-Arch
    Write-Host "Setting up a private Python $PythonVersion ($arch) in .runtime\ - first run only." -ForegroundColor Yellow
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    if (Test-Path -LiteralPath $PyDir) { Remove-Item -LiteralPath $PyDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $PyDir | Out-Null
    $tmp = Join-Path $RuntimeDir 'download'
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null

    try {
        Write-Step "downloading Python $PythonVersion from python.org"
        $zip = Join-Path $tmp 'python.zip'
        Get-Verified "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-$arch.zip" $zip $PythonSha[$arch]
        Expand-Zip $zip $PyDir

        $site = Join-Path $PyDir 'site-packages'
        New-Item -ItemType Directory -Force -Path $site | Out-Null
        foreach ($p in $Packages) {
            $file, $sha = if ($p.Files.ContainsKey($arch)) { $p.Files[$arch] } else { $p.Files['any'] }
            Write-Step "downloading $($p.Name) $($p.Version) from PyPI"
            $meta = Invoke-RestMethod -Uri "https://pypi.org/pypi/$($p.Name)/$($p.Version)/json" -UseBasicParsing
            $url = ($meta.urls | Where-Object { $_.filename -eq $file } | Select-Object -First 1).url
            if (-not $url) { throw "PyPI has no $file" }
            $whl = Join-Path $tmp $file
            Get-Verified $url $whl $sha
            Expand-Zip $whl $site
        }

        # The embeddable build takes sys.path only from its ._pth file and
        # ignores the script's own folder, so list src\ there. Relative paths
        # keep working if the whole tool folder is moved.
        $pth = Get-ChildItem -LiteralPath $PyDir -Filter 'python*._pth' | Select-Object -First 1
        $zipName = (Get-ChildItem -LiteralPath $PyDir -Filter 'python*.zip' | Select-Object -First 1).Name
        $lines = @($zipName, '.', 'site-packages', '..\..\src')
        [IO.File]::WriteAllLines($pth.FullName, $lines)

        Write-Step 'checking the runtime'
        # no quotes inside: 5.1 strips embedded quotes from native arguments
        & $PyExe -c 'import PIL.ImageFont, fontTools.ttLib, smfont'
        if ($LASTEXITCODE -ne 0) { throw 'The downloaded runtime failed its self-test.' }
        Set-Content -LiteralPath $Marker -Value $PythonVersion
        Write-Step 'ready'
    } catch {
        # never leave a half-built runtime that a later run would trust
        Remove-Item -LiteralPath $PyDir -Recurse -Force -ErrorAction SilentlyContinue
        throw
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------------ main
if ($Clean) {
    if (Test-Path -LiteralPath $RuntimeDir) {
        Remove-Item -LiteralPath $RuntimeDir -Recurse -Force
        Write-Host 'Removed the private runtime (.runtime\).'
    } else {
        Write-Host 'Nothing to remove.'
    }
    exit 0
}

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    Write-Host 'This script downloads the Windows build of Python. On macOS/Linux, install Python 3 and run:' -ForegroundColor Yellow
    Write-Host '  python3 -m pip install -r requirements.txt'
    Write-Host "  python3 src/fontpatch.py $Command"
    exit 1
}
if (-not (Test-Path -LiteralPath $Entry)) {
    Write-Host "Can't find src\fontpatch.py next to this script. Keep Install-FontPatch.ps1 in the tool's folder." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $Marker)) {
    try { Install-Runtime }
    catch {
        Write-Host "`nSetup failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Check your internet connection and try again, or install Python yourself (see README).' -ForegroundColor Red
        exit 1
    }
}

$argv = @($Entry, $Command)
foreach ($r in @($Root)) {
    if (-not $r) { continue }
    # resolve relative paths against the PowerShell location; fontpatch.py
    # validates the result and reports a bad root itself
    try { $r = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($r) } catch { }
    $argv += @('--root', $r)
}
foreach ($t in @($Theme)) { if ($t) { $argv += @('--theme', $t) } }
if ($Scripts) { $argv += @('--scripts', ($Scripts -join ',')) }
if ($ExtraArgs) { $argv += $ExtraArgs }

& $PyExe @argv
exit $LASTEXITCODE
