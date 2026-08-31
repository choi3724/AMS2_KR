param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$RepositoryRoot
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = (& git rev-parse --show-toplevel 2>$null)
}
if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    throw 'Unable to resolve the Git repository root.'
}

$repo = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
$output = [IO.Path]::GetFullPath($OutputPath).TrimEnd('\')
if ($output.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or
    $output.StartsWith($repo + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Output path is inside the Git repository: $output"
}

$output
