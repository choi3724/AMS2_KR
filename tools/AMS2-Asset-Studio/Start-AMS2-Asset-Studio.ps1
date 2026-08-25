$ErrorActionPreference = 'Stop'

$toolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appPath = Join-Path $toolRoot 'ams2_asset_studio.py'
$pythonCandidates = @(
    (Join-Path $toolRoot 'runtime\python\pythonw.exe'),
    'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe',
    'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
)

$pythonPath = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonPath) {
    $pythonCommand = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    }
    if ($pythonCommand) {
        $pythonPath = $pythonCommand.Source
    }
}

if (-not $pythonPath) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        'Python 3을 찾지 못했습니다. README.md의 실행 환경 항목을 확인하십시오.',
        'AMS2 Asset Studio',
        'OK',
        'Error'
    ) | Out-Null
    exit 2
}

& $pythonPath $appPath
exit $LASTEXITCODE
