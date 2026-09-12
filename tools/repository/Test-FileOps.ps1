param(
    [string]$Tool = 'E:\AMS2_Korean_Work\build\audit-next\build\0.82\installer\AMS2 Korean Patch TestCli.exe',
    [string]$Published = 'E:\AMS2_Korean_Work\build\0.82\installer\AMS2 Korean Patch TestCli.exe',
    [string]$WorkRoot = 'E:\AMS2_Korean_Work\build'
)
$ErrorActionPreference = 'Stop'
[AppContext]::SetSwitch('Switch.System.IO.UseLegacyPathHandling', $true)
[AppContext]::SetSwitch('Switch.System.IO.BlockLongPaths', $true)
$output = Join-Path $WorkRoot ('fileops-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $output | Out-Null
$folder = Join-Path $output ('d' * (180 - $output.Length - 1))
New-Item -ItemType Directory -Path $folder | Out-Null
$source = Join-Path $output 'source.bin'
[IO.File]::WriteAllText($source, 'verified source')
$hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
$target = Join-Path $folder (('long-file-' * 6) + '.bin')
$current = [Reflection.Assembly]::LoadFile($Tool).GetType('Ams2KoreanBeta.FileOps')
$old = [Reflection.Assembly]::LoadFile($Published).GetType('Ams2KoreanBeta.FileOps')
function Invoke-FileOp($type, $name, [string[]]$arguments) {
    $type.GetMethod($name).Invoke($null, $arguments)
}
$refused = $false
try { Invoke-FileOp $old 'CopyNewExact' @($source, $target, $hash) }
catch {
    $detail = $_.Exception.ToString()
    $detail | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $output 'published-error.txt')
    $refused = $detail.Contains('PathTooLongException') -or $detail.Contains('DirectoryNotFoundException')
}
if (-not $refused -or (Test-Path -LiteralPath $target)) { throw 'Published long-path failure was not reproduced.' }
Invoke-FileOp $current 'CopyNewExact' @($source, $target, $hash)
Invoke-FileOp $current 'ReplaceExact' @($source, $target, $hash)
if ((Get-FileHash -LiteralPath $target).Hash -ne $hash) { throw 'Long-path copy/replace differs.' }
Invoke-FileOp $current 'WriteTextAtomic' @($target, 'new state')
Invoke-FileOp $current 'WriteTextAtomic' @($target, 'updated state')
if ([IO.File]::ReadAllText($target) -ne 'updated state') { throw 'Atomic state write differs.' }
[IO.File]::SetAttributes($source, [IO.FileAttributes]::ReadOnly)
foreach ($method in @('CopyNewExact','ReplaceExact')) {
    $failedTarget = Join-Path $folder ($method + '.bin')
    $refused = $false
    try { Invoke-FileOp $current $method @($source, $failedTarget, ('0' * 64)) }
    catch { $refused = $true }
    if (-not $refused -or (Test-Path -LiteralPath $failedTarget)) { throw 'Invalid hash was accepted.' }
}
if (@(Get-ChildItem -LiteralPath $folder -Filter '*.tmp').Count -ne 0) { throw 'Temporary files remain after refusal.' }
@{ status='PASS'; published_long_path_failure_reproduced=$true; copy_replace_atomic_write='PASS'; invalid_hash_readonly_cleanup='PASS'; live_game_modified=$false } |
    ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $output 'result.json')
Write-Output "PASS: $output"
