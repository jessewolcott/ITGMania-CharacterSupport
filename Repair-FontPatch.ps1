<#
.SYNOPSIS
    Repair and check a fontpatch install without Python.

.DESCRIPTION
    1. Moves backups left by older fontpatch versions out of the theme's Fonts
       folder. Font::GetFontPaths globs "<name>*" and loads every non-.ini hit
       as a texture page, so "Common default.ini.fontpatch-bak" beside the
       original fails on launch with
       "RageBitmapTexture: Couldn't load ... unknown file format".
       The backup goes to <root>\fontpatch-backup\<same relative path>, which
       is where fontpatch.py now keeps it, and the manifest is updated.

    2. Checks the fonts, per theme:
         - which Common default the theme resolves to
         - every generated _fontpatch page/ini still exists and is unmodified
         - every page is a real PNG
         - every import line is still present (a theme update reverts it)
         - no stray file next to any font that the engine would try to load
           as a texture

    Generating pages still needs `python fontpatch.py install`; this script
    only repairs the backup location and reports.

.PARAMETER Root
    ITGmania install(s) to act on. Defaults to the usual locations.

.PARAMETER Theme
    Limit the font check to these themes.

.EXAMPLE
    .\Repair-FontPatch.ps1
.EXAMPLE
    .\Repair-FontPatch.ps1 -Root C:\Games\ITGmania -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string[]]$Root,
    [string[]]$Theme
)

$ErrorActionPreference = 'Stop'

$BackupDir = 'fontpatch-backup'
$LegacySuffix = '.fontpatch-bak'
$ManifestFile = 'fontpatch-manifest.json'
$Prefix = '_fontpatch'
# what RageSurfaceUtils can open; anything else matched by a font's glob fails
$TextureExt = @('.png', '.jpg', '.jpeg', '.gif', '.bmp')

$DefaultRoots = @(
    'C:\Games\ITGmania',
    (Join-Path $env:ProgramFiles 'ITGmania'),
    (Join-Path $env:APPDATA 'ITGmania')
)

$script:Problems = 0

function Write-Ok($msg) { Write-Host "    [OK ] $msg" -ForegroundColor Green }
function Write-Fixed($msg) { Write-Host "    [FIX] $msg" -ForegroundColor Cyan }
function Write-Info($msg) { Write-Host "          $msg" -ForegroundColor DarkGray }
function Write-Bad($msg) {
    Write-Host "    [BAD] $msg" -ForegroundColor Red
    $script:Problems++
}

function Get-Rel([string]$base, [string]$path) {
    $b = [IO.Path]::GetFullPath($base).TrimEnd('\') + '\'
    $p = [IO.Path]::GetFullPath($path)
    if ($p.StartsWith($b, [StringComparison]::OrdinalIgnoreCase)) { return $p.Substring($b.Length) }
    return $p
}

function Read-Manifest([string]$root) {
    $p = Join-Path $root $ManifestFile
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    try { return Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { Write-Bad "manifest unreadable: $p"; return $null }
}

function Save-Manifest([string]$root, $m) {
    $p = Join-Path $root $ManifestFile
    $json = $m | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($p, $json, (New-Object Text.UTF8Encoding($false)))
}

function Get-ManifestEntries($m) {
    if (-not $m -or -not $m.entries) { return @() }
    return @($m.entries.PSObject.Properties | ForEach-Object { $_.Value })
}

function Get-Themes([string]$root) {
    $dir = Join-Path $root 'Themes'
    if (-not (Test-Path -LiteralPath $dir)) { return @() }
    return @(Get-ChildItem -LiteralPath $dir -Directory | Sort-Object Name | ForEach-Object { $_.Name })
}

# The Common default a theme actually loads: its own, else _fallback's.
function Resolve-CommonDefault([string]$root, [string]$themeName) {
    foreach ($t in @($themeName, '_fallback') | Select-Object -Unique) {
        $p = Join-Path $root "Themes\$t\Fonts\Common default.ini"
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

# Entries on the [main] import= line, as Font::Load reads them.
function Get-Imports([string]$ini) {
    $inMain = $false
    foreach ($line in [IO.File]::ReadAllLines($ini)) {
        $s = $line.Trim()
        if ($s.StartsWith('[') -and $s.EndsWith(']')) { $inMain = ($s -ieq '[main]'); continue }
        if ($inMain -and $s -match '^(?i)import=(.*)$') {
            return @($Matches[1].Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        }
    }
    return @()
}

function Test-Png([string]$path) {
    $fs = [IO.File]::OpenRead($path)
    try {
        $buf = New-Object byte[] 8
        $n = $fs.Read($buf, 0, 8)
    } finally { $fs.Dispose() }
    return $n -eq 8 -and $buf[0] -eq 0x89 -and $buf[1] -eq 0x50 -and $buf[2] -eq 0x4E -and $buf[3] -eq 0x47
}

# fontpatch.py records sha256 truncated to 16 hex chars
function Get-ShortSha([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.Substring(0, 16).ToLowerInvariant()
}

# ------------------------------------------------------------- 1. backups
function Repair-Backups {
    [CmdletBinding(SupportsShouldProcess)]
    param([string]$root, $manifest)
    $changed = $false
    $themesDir = Join-Path $root 'Themes'
    $legacy = @(Get-ChildItem -LiteralPath $themesDir -Recurse -File -Filter "*$LegacySuffix" -ErrorAction SilentlyContinue)
    if (-not $legacy) {
        Write-Ok 'no backups inside theme Fonts folders'
        return $false
    }
    foreach ($f in $legacy) {
        $original = $f.FullName.Substring(0, $f.FullName.Length - $LegacySuffix.Length)
        $relOrig = Get-Rel $root $original
        $dest = Join-Path (Join-Path $root $BackupDir) $relOrig
        if (-not $PSCmdlet.ShouldProcess($f.FullName, "move backup to $dest")) { continue }
        if (Test-Path -LiteralPath $dest) {
            Remove-Item -LiteralPath $f.FullName -Force
            Write-Fixed "removed $(Get-Rel $root $f.FullName) (backup already at $(Get-Rel $root $dest))"
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
            Move-Item -LiteralPath $f.FullName -Destination $dest
            Write-Fixed "moved $(Get-Rel $root $f.FullName) -> $(Get-Rel $root $dest)"
        }
        foreach ($e in Get-ManifestEntries $manifest) {
            if (($e.common_default -replace '/', '\') -ieq $relOrig) {
                $e.backup = Get-Rel $root $dest
                $changed = $true
            }
        }
    }
    return $changed
}

# ------------------------------------------------------------- 2. stray files
# For every font .ini, anything else matching "<stem>*" in the same folder is
# handed to RageBitmapTexture. Report the ones it cannot open.
function Test-StrayFiles([string]$root, [string]$fontsDir) {
    $bad = 0
    $dirs = @(Get-Item -LiteralPath $fontsDir) + @(Get-ChildItem -LiteralPath $fontsDir -Recurse -Directory)
    foreach ($d in $dirs) {
        $files = @(Get-ChildItem -LiteralPath $d.FullName -File)
        $stems = $files | Where-Object { $_.Extension -ieq '.ini' } | ForEach-Object { $_.BaseName }
        foreach ($stem in $stems) {
            foreach ($f in $files) {
                if (-not $f.Name.StartsWith($stem, [StringComparison]::OrdinalIgnoreCase)) { continue }
                if ($f.Extension -ieq '.ini' -or $TextureExt -contains $f.Extension.ToLowerInvariant()) { continue }
                Write-Bad "'$(Get-Rel $root $f.FullName)' would be loaded as a texture of font '$stem' - move it out of Fonts"
                $bad++
            }
        }
    }
    return $bad
}

# ------------------------------------------------------------- 3. fonts
function Test-Theme([string]$root, [string]$themeName, $manifest, [hashtable]$seen) {
    Write-Host "  $themeName" -ForegroundColor White
    $cd = Resolve-CommonDefault $root $themeName
    if (-not $cd) { Write-Info 'no Common default font - skipped'; return }
    $relCd = Get-Rel $root $cd
    Write-Info "uses $relCd"

    $fontsDir = Join-Path $root "Themes\$themeName\Fonts"
    if ((Test-Path -LiteralPath $fontsDir) -and (Test-StrayFiles $root $fontsDir) -eq 0) {
        Write-Ok 'no stray files next to fonts'
    }

    if ($seen.ContainsKey($relCd.ToLowerInvariant())) {
        Write-Info "font wiring checked above (shared $relCd)"
        return
    }
    $seen[$relCd.ToLowerInvariant()] = $true

    $entry = Get-ManifestEntries $manifest | Where-Object { ($_.common_default -replace '/', '\') -ieq $relCd } | Select-Object -First 1
    $imports = Get-Imports $cd

    if (-not $entry) {
        $ours = @($imports | Where-Object { $_ -like "$Prefix *" })
        if ($ours) { Write-Bad "imports $($ours -join ', ') but has no manifest entry" }
        else { Write-Info 'not patched (run: python fontpatch.py install)' }
        return
    }

    $bak = Join-Path $root $entry.backup
    if ((Test-Path -LiteralPath $bak) -and -not $bak.StartsWith((Join-Path $root 'Themes'), [StringComparison]::OrdinalIgnoreCase)) {
        Write-Ok "backup at $($entry.backup)"
    } elseif (Test-Path -LiteralPath $bak) {
        Write-Bad "backup is still inside Themes: $($entry.backup)"
    } else {
        Write-Bad "backup missing: $($entry.backup) (uninstall cannot restore exactly)"
    }

    if ($entry.scripts) {
        foreach ($p in $entry.scripts.PSObject.Properties) {
            $g = $p.Value
            $missing = @(); $modified = @(); $notPng = @()
            foreach ($rel in $g.files) {
                $f = Join-Path $root $rel
                $name = Split-Path $rel -Leaf
                if (-not (Test-Path -LiteralPath $f)) { $missing += $name; continue }
                if ($f -like '*.png' -and -not (Test-Png $f)) { $notPng += $name }
                $want = $null
                if ($g.sha) { $want = $g.sha.$name }
                if ($want -and (Get-ShortSha $f) -ne $want) { $modified += $name }
            }
            $label = '{0,-11} {1,6} glyphs' -f $p.Name, $g.glyphs
            if ($missing) { Write-Bad "$label  missing: $($missing -join ', ')" }
            if ($notPng) { Write-Bad "$label  not a PNG: $($notPng -join ', ')" }
            if ($modified) { Write-Bad "$label  changed since install: $($modified -join ', ')" }
            if ($imports -notcontains $g.font) { Write-Bad "$label  import '$($g.font)' lost (theme updated?)" }
            if (-not ($missing -or $notPng -or $modified) -and $imports -contains $g.font) {
                Write-Ok "$label  from $($g.source)"
            }
        }
    }
    foreach ($name in @($entry.extra_imports)) {
        if (-not $name) { continue }
        if ($imports -contains $name) { Write-Ok ('{0,-18} wired up' -f $name) }
        else { Write-Bad "import '$name' lost (theme updated?)" }
    }
    foreach ($p in @($entry.failed.PSObject.Properties)) {
        if ($p) { Write-Info "$($p.Name) was skipped at install: $($p.Value)" }
    }
}

# ------------------------------------------------------------- main
# Validate -Root up front; a typo should not fall through to "nothing to do".
# Relative paths resolve against the PowerShell location, not the process cwd.
$rootErrors = 0
foreach ($p in @($Root)) {
    if (-not $p) { continue }
    try {
        $full = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($p)
        $why = if (-not (Test-Path -LiteralPath $full)) { 'does not exist' }
               elseif (-not (Test-Path -LiteralPath $full -PathType Container)) { 'is not a directory' }
               elseif (-not (Test-Path -LiteralPath (Join-Path $full 'Themes') -PathType Container)) { 'has no Themes folder - not an ITGmania install' }
    } catch { $why = 'is not a valid path' }
    if ($why) {
        Write-Host "-Root ${p}: $why" -ForegroundColor Red
        $rootErrors++
    }
}
if ($rootErrors) { exit 2 }

$roots = if ($Root) { $Root | ForEach-Object { $PSCmdlet.GetUnresolvedProviderPathFromPSPath($_) } }
         else { $DefaultRoots | Where-Object { $_ -and (Test-Path -LiteralPath (Join-Path $_ 'Themes')) } }
$roots = @($roots | Select-Object -Unique)
if (-not $roots) {
    Write-Host 'No ITGmania install found. Pass -Root <path>.' -ForegroundColor Yellow
    exit 1
}

foreach ($r in $roots) {
    Write-Host "`n=== $r" -ForegroundColor Yellow
    $manifest = Read-Manifest $r

    Write-Host '  backups' -ForegroundColor White
    if ((Repair-Backups $r $manifest) -and $manifest) {
        Save-Manifest $r $manifest
        Write-Fixed "updated $ManifestFile"
    }

    $names = if ($Theme) { $Theme } else { Get-Themes $r }
    # _fallback first so themes that share its Common default report "shared"
    $names = @($names | Sort-Object { $_ -ne '_fallback' }, { $_ })
    $seen = @{}
    foreach ($t in $names) {
        if (-not (Test-Path -LiteralPath (Join-Path $r "Themes\$t"))) {
            Write-Bad "theme '$t' not found"
            continue
        }
        Test-Theme $r $t $manifest $seen
    }
}

Write-Host ''
if ($script:Problems) {
    Write-Host "$script:Problems problem(s). Lost imports or missing pages: python fontpatch.py install" -ForegroundColor Red
    exit 1
}
Write-Host 'All good.' -ForegroundColor Green
exit 0
