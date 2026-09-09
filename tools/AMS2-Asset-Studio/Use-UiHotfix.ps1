[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Apply','Restore','Status')][string]$Action,
    [Parameter(Mandatory=$true)][string]$CandidateDir,
    [string]$GameDir = 'E:\SteamLibrary\steamapps\common\Automobilista 2',
    [string]$BackupRoot
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$GameDir = [IO.Path]::GetFullPath($GameDir).TrimEnd('\')
$CandidateDir = [IO.Path]::GetFullPath($CandidateDir).TrimEnd('\')
if (-not $BackupRoot) { $BackupRoot = Join-Path $CandidateDir 'backup' }
$BackupRoot = [IO.Path]::GetFullPath($BackupRoot).TrimEnd('\')
if ($BackupRoot -eq $GameDir -or $BackupRoot.StartsWith($GameDir + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Test backups must be outside the game directory.'
}
foreach ($exe in @('AMS2.exe','AMS2AVX.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $GameDir $exe) -PathType Leaf)) { throw "Game executable missing: $exe" }
}
if ($Action -ne 'Status' -and @(Get-Process -Name 'AMS2','AMS2AVX','AMS2 Korean Launcher','AMS2 Korean VR Launcher' -ErrorAction SilentlyContinue | Where-Object {
    -not $_.Path -or [IO.Path]::GetDirectoryName($_.Path) -eq $GameDir
}).Count) {
    throw 'Close AMS2 and the Korean launcher before applying or restoring the test.'
}
$manifest = Get-Content -LiteralPath (Join-Path $CandidateDir 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$allowed = @('text/drivers.tdb','text/game.tdb')
$created = @()
if ($manifest.PSObject.Properties['scope'] -and $manifest.scope -in @('ERS_COCKPIT_TEST','ERS_COCKPIT_ARCHIVE_TEST')) {
    $allowed = @('gui/display_formula_hybrid_gen1.bgui','gui/display_formula_ultimate_2019.bgui',
                 'gui/display_formula_ultimate_2022.bgui','gui/display_formula_ultimate_2024.bgui',
                 'gui/display_lamborghini_sc63.bgui','gui/display_lamborghini_sc63_IMSA.bgui',
                 'gui/display_porsche_963.bgui','gui/display_porsche_963_IMSA.bgui')
    $created = @(foreach ($size in @(20,40,52,60)) {
        "gui/kr081_ers_value_$size.bfont"
        "gui/kr081_ers_value_$($size)_00.dds"
        "gui/kr081_ers_value_$($size)_01.dds"
    })
    $allowed += $created
    if ($manifest.scope -eq 'ERS_COCKPIT_ARCHIVE_TEST') { $allowed += 'Pakfiles/HUDDISPLAY.bff' }
}
if ($manifest.PSObject.Properties['scope'] -and $manifest.scope -eq 'REPLAY_TIME_DIAGNOSTIC') {
    $allowed = @('gui/hud_leaderboard2_1_6.bgui','hud_leaderboard2_1_6.bgui')
}
if ($manifest.PSObject.Properties['scope'] -and $manifest.scope -eq 'LAUNCHER_TEST') {
    $allowed = @('AMS2 Korean Launcher.exe','AMS2 Korean VR Launcher.exe')
}
if ($manifest.PSObject.Properties['scope'] -and $manifest.scope -eq 'MENU_FOOTER_TEST') {
    $allowed = @('gui/menu_mainmenu_1_6.bgui','gui/menu_mainmenuams2.bgui')
    if ($Action -eq 'Apply') { throw 'Menu footer prototypes are blocked after repeated startup crashes; only Status and Restore are allowed.' }
}
# Preserve restoration of the failed test1, but never apply its BGUI files again.
if ($Action -ne 'Apply' -and $manifest.files.Count -eq 4) {
    $allowed += @('gui/menu_mainmenu_1_6.bgui','gui/menu_mainmenuams2.bgui')
}
if ($manifest.files.Count -ne $allowed.Count -or @(Compare-Object $allowed @($manifest.files.path | Sort-Object -Unique)).Count) {
    throw 'Candidate must contain an exact supported test file set; legacy menu files are only restorable.'
}
if ($Action -eq 'Apply' -and $manifest.status -notin @('AWAITING_GAME_TEST','GAME_TEST_PASSED')) {
    throw 'This candidate is blocked: ' + $manifest.status
}

function Hash([string]$Path) {
    if (-not [IO.File]::Exists($Path)) { return 'MISSING' }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}
function Inside([string]$Root, [string]$Relative) {
    $full = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    if (-not $full.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escaped root.' }
    return $full
}
function Replace-Exact([string]$Source, [string]$Target, [string]$Expected) {
    $temp = $Target + '.ui-test-' + [Guid]::NewGuid().ToString('N')
    try {
        [IO.File]::Copy($Source, $temp, $false)
        if ((Hash $temp) -ne $Expected) { throw "Temporary copy mismatch: $Target" }
        if ([IO.File]::Exists($Target)) { [IO.File]::Replace($temp, $Target, [NullString]::Value) }
        else { [IO.File]::Move($temp, $Target) }
        if ((Hash $Target) -ne $Expected) { throw "Final copy mismatch: $Target" }
    } finally {
        if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) }
    }
}
function Restore-Item($Item) {
    if ($Item.row.before_sha256 -eq 'MISSING') {
        $current = Hash $Item.live
        if ($current -notin @('MISSING', $Item.row.after_sha256)) { throw "Refusing to delete changed test font: $($Item.live)" }
        if ($current -ne 'MISSING') { [IO.File]::Delete($Item.live) }
    } else { Replace-Exact $Item.backup $Item.live $Item.row.before_sha256 }
}

$items = foreach ($row in $manifest.files) {
    if ($row.path -in $created) {
        if ($row.before_sha256 -ne 'MISSING') { throw 'New ERS fonts must be absent before the test.' }
    } elseif ($row.before_sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid original hash.' }
    if ($row.after_sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid candidate hash.' }
    $live = Inside $GameDir $row.path
    $payload = Inside (Join-Path $CandidateDir 'payload') $row.path
    $backup = Inside $BackupRoot $row.path
    $current = Hash $live
    if ($Action -ne 'Status') {
        $accepted = @($row.before_sha256, $row.after_sha256)
        if ($Action -eq 'Restore') { $accepted += 'MISSING' }
        if ($current -notin $accepted) { throw "Unexpected current file; no files changed: $live" }
        if ($Action -eq 'Apply' -and (Hash $payload) -ne $row.after_sha256) { throw "Candidate mismatch: $payload" }
        if (($Action -eq 'Restore' -or $current -eq $row.after_sha256 -or [IO.File]::Exists($backup)) -and (Hash $backup) -ne $row.before_sha256) {
            throw "Original test backup missing or damaged: $backup"
        }
    }
    [pscustomobject]@{ row=$row; live=$live; payload=$payload; backup=$backup; current=$current }
}
if ($Action -eq 'Apply') {
    # Complete and verify every backup before changing any game file.
    foreach ($item in $items) {
        if ($item.row.before_sha256 -eq 'MISSING') {
            if ([IO.File]::Exists($item.backup)) { throw 'Unexpected backup for a newly created font.' }
            continue
        }
        if (-not [IO.File]::Exists($item.backup)) {
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($item.backup)) | Out-Null
            [IO.File]::Copy($item.live, $item.backup, $false)
        }
        if ((Hash $item.backup) -ne $item.row.before_sha256) { throw 'Backup verification failed.' }
    }
    try {
        foreach ($item in $items) { Replace-Exact $item.payload $item.live $item.row.after_sha256 }
    } catch {
        $failure = $_
        foreach ($item in $items) {
            try { Restore-Item $item }
            catch { Write-Warning "Rollback failed: $($item.live): $_" }
        }
        throw $failure
    }
} elseif ($Action -eq 'Restore') {
    foreach ($item in $items) { Restore-Item $item }
}
$observed = @($items | ForEach-Object {
    $value = Hash $_.live
    [pscustomobject]@{ path=$_.row.path; sha256=$value; original=($value -eq $_.row.before_sha256); candidate=($value -eq $_.row.after_sha256) }
})
$state = if (@($observed | Where-Object { -not $_.candidate }).Count -eq 0) { 'TEST_APPLIED' }
         elseif (@($observed | Where-Object { -not $_.original }).Count -eq 0) {
             if ($created.Count) { 'ORIGINAL_0.81' } else { 'ORIGINAL_0.7' }
         }
         else { 'MIXED_OR_CHANGED' }
$result = [ordered]@{ action=$Action; state=$state; version=$manifest.version; game=$GameDir; backup=$BackupRoot; files=$observed }
$json = $result | ConvertTo-Json -Depth 4
if ($Action -ne 'Status') { [IO.File]::WriteAllText((Join-Path $BackupRoot 'last-operation.json'), $json, [Text.UTF8Encoding]::new($false)) }
$json
