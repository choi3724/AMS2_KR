param([switch]$StagedOnly)

$ErrorActionPreference = 'Stop'
$repo = (& git rev-parse --show-toplevel 2>$null)
if (-not $repo) { throw 'Not a Git repository.' }

$paths = if ($StagedOnly) {
    & git diff --cached --name-only --diff-filter=ACMR
} else {
    @(& git diff --name-only --diff-filter=ACMR; & git ls-files --others --exclude-standard)
}

$blocked = $paths | Where-Object {
    $_ -match '(^|/)(build|bin|obj|dist|out|publish|local-debug|diagnostics|logs|handoff)/' -or
    $_ -match '\.(zip|exe|pdb|dmp|pml|deps\.json|runtimeconfig\.json)$'
}

if ($blocked) {
    $blocked | Sort-Object -Unique | ForEach-Object { Write-Error "Generated artifact candidate: $_" }
    exit 2
}

Write-Host "PASS: no generated artifact commit candidates. ($(@($paths).Count) paths checked)"
