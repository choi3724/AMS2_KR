param([Parameter(Mandatory=$true)][string]$CandidateDir, [Parameter(Mandatory=$true)][string]$ReleaseRoot,
      [Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference = 'Stop'
$fixture = Join-Path ([IO.Path]::GetFullPath($OutputRoot)) ('fixture-' + [Guid]::NewGuid().ToString('N'))
$game = Join-Path $fixture 'game'
$backup = Join-Path $fixture 'backup'
$helper = Join-Path $PSScriptRoot 'Use-UiHotfix.ps1'
$manifest = Get-Content -LiteralPath (Join-Path $CandidateDir 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
[IO.Directory]::CreateDirectory($game) | Out-Null
foreach ($name in @('AMS2.exe','AMS2AVX.exe')) { [IO.File]::WriteAllText((Join-Path $game $name), 'NOT EXECUTED') }
foreach ($row in $manifest.files) {
    $destination = Join-Path $game $row.path
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
    [IO.File]::Copy((Join-Path (Join-Path $ReleaseRoot 'payload/direct') $row.path), $destination)
}
$options = @{ CandidateDir=$CandidateDir; GameDir=$game; BackupRoot=$backup }
for ($pass = 1; $pass -le 2; $pass++) {
    $result = & $helper -Action Apply @options | ConvertFrom-Json
    if ($result.state -ne 'TEST_APPLIED') { throw 'Apply failed' }
    $result = & $helper -Action Apply @options | ConvertFrom-Json
    if ($result.state -ne 'TEST_APPLIED') { throw 'Repeated apply failed' }
    if ($pass -eq 2) { [IO.File]::Delete((Join-Path $game $manifest.files[0].path)) }
    $result = & $helper -Action Restore @options | ConvertFrom-Json
    if ($result.state -ne 'ORIGINAL_0.7') { throw 'Exact restore failed' }
}
$blocked = Join-Path $fixture 'blocked-candidate'
[IO.Directory]::CreateDirectory($blocked) | Out-Null
$manifest.status = 'RUNTIME_FAILED'
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $blocked 'manifest.json') -Encoding UTF8
$refused = $false
try { & $helper -Action Apply -CandidateDir $blocked -GameDir $game -BackupRoot $backup | Out-Null }
catch { $refused = $_.ToString().Contains('candidate is blocked') }
if (-not $refused) { throw 'Failed-candidate guard failed' }
[IO.File]::WriteAllText((Join-Path $game $manifest.files[0].path), 'MANUAL CHANGE MUST BE PRESERVED')
$before = @($manifest.files | ForEach-Object { (Get-FileHash -LiteralPath (Join-Path $game $_.path)).Hash })
$refused = $false
try { & $helper -Action Apply @options | Out-Null } catch { $refused = $true }
$after = @($manifest.files | ForEach-Object { (Get-FileHash -LiteralPath (Join-Path $game $_.path)).Hash })
if (-not $refused -or @(Compare-Object $before $after).Count) { throw 'Unexpected-file guard failed' }
Write-Output 'PASS: two apply/restore cycles, repeated apply, missing-file recovery, failed-candidate and manual-change refusal'
Write-Output "Fixture: $fixture"
