param(
    [string]$Version = '0.82',
    [string]$WorkRoot = 'E:\AMS2_Korean_Work',
    [string]$CompatibilityDataRoot = ''
)

$ErrorActionPreference = 'Stop'
$repo = (& git rev-parse --show-toplevel 2>$null)
if (-not $repo) { throw 'Not a Git repository.' }
$repo = [IO.Path]::GetFullPath($repo)
$source = Join-Path $repo "installer\$Version"
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw "Installer source is missing: $source" }
$assetSource = if (Test-Path -LiteralPath (Join-Path $source 'assets')) { $source } else { Join-Path $repo 'installer\0.83.1' }

$output = Join-Path $WorkRoot "build\$Version\installer"
$output = & (Join-Path $PSScriptRoot 'Assert-ExternalOutputPath.ps1') -OutputPath $output -RepositoryRoot $repo
$intermediate = Join-Path $WorkRoot "build\$Version\intermediate"
$intermediate = & (Join-Path $PSScriptRoot 'Assert-ExternalOutputPath.ps1') -OutputPath $intermediate -RepositoryRoot $repo
New-Item -ItemType Directory -Path $output,$intermediate -Force | Out-Null

$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $csc)) { throw ".NET Framework compiler is missing: $csc" }
$commonReferences = @(
    '/reference:System.dll',
    '/reference:System.Core.dll',
    '/reference:System.Drawing.dll',
    '/reference:System.Windows.Forms.dll',
    '/reference:System.IO.Compression.dll',
    '/reference:System.IO.Compression.FileSystem.dll',
    '/reference:System.Web.Extensions.dll'
)

function Invoke-Csc([string]$Target, [string]$Main, [string]$OutputFile, [string[]]$Sources, [string[]]$Extra = @()) {
    $arguments = @('/nologo', "/target:$Target", '/platform:anycpu', "/main:$Main", "/out:$OutputFile") + $commonReferences + $Extra + $Sources
    & $csc @arguments
    if ($LASTEXITCODE -ne 0) { throw "C# compile failed: $OutputFile" }
}

$assembly = Join-Path $source 'AssemblyInfo.cs'
$core = @('BetaCore.cs','ErsArchivePatch.cs' | ForEach-Object { Join-Path $source $_ } | Where-Object { Test-Path -LiteralPath $_ })
$icon = Join-Path $assetSource 'ams2-korean.ico'
$manifest = Join-Path $source 'app.manifest'
$win32 = @("/win32icon:$icon", "/win32manifest:$manifest")

$shared = @('GameLauncher.cs','GithubUpdater.cs' | ForEach-Object { Join-Path $source $_ } | Where-Object { Test-Path -LiteralPath $_ })
$compatibility = Join-Path $source 'GameUpdateCompatibility.cs'
$compatibilityResources = @()
$launcherCore = @()
if (Test-Path -LiteralPath $compatibility) {
    if (-not $CompatibilityDataRoot) { throw 'CompatibilityDataRoot is required for an update-aware installer/launcher.' }
    $shared += $compatibility
    $cmOverlay = Join-Path $source 'ContentManagerOverlay.cs'
    if (Test-Path -LiteralPath $cmOverlay) {
        $shared += $cmOverlay
        $cmData = Join-Path $CompatibilityDataRoot 'cm-overlays.json.gz'
        if (-not (Test-Path -LiteralPath $cmData)) { throw "Missing CM compatibility data: $cmData" }
        $compatibilityResources += '/resource:' + $cmData + ',Ams2KoreanBeta.Compatibility.cm-overlays.json.gz'
    }
    $launcherCore = $core
    foreach ($name in @('rules.json','IGPHASEHUD.xor.gz','HUDDISPLAY.xor.gz')) {
        $path = Join-Path $CompatibilityDataRoot $name
        if (-not (Test-Path -LiteralPath $path)) { throw "Missing compatibility data: $path" }
        $compatibilityResources += '/resource:' + $path + ',Ams2KoreanBeta.Compatibility.' + $name
    }
    foreach ($path in Get-ChildItem -LiteralPath $CompatibilityDataRoot -Filter '*.24132163.*.gz' -File) {
        $compatibilityResources += '/resource:' + $path.FullName + ',Ams2KoreanBeta.Compatibility.' + $path.Name
    }
}
$update = @(Join-Path $source 'InstallerUpdate.cs' | Where-Object { Test-Path -LiteralPath $_ })
$launcherResources = @()
if (Test-Path -LiteralPath (Join-Path $source 'GithubUpdater.cs')) {
    $launcherResources = @('/resource:' + (Join-Path $assetSource 'assets\installer-hero.png') + ',Ams2KoreanBeta.LauncherHero')
    $launcherResources += '/resource:' + (Join-Path $assetSource 'assets\Pretendard-Medium.otf') + ',Ams2KoreanBeta.Pretendard'
}
Invoke-Csc 'winexe' 'Ams2KoreanBeta.InstallerProgram' (Join-Path $output "AMS2-Korean-Patch-OB-$Version.exe") ((@((Join-Path $source 'InstallerProgram.cs'),$assembly) + $core) + $shared + $update) ($win32 + $compatibilityResources)
Invoke-Csc 'winexe' 'Ams2KoreanBeta.LauncherProgram' (Join-Path $output 'AMS2 Korean Launcher.exe') (@((Join-Path $source 'LauncherProgram.cs'),$assembly) + $shared + $launcherCore) ($win32 + $launcherResources + $compatibilityResources)
Invoke-Csc 'winexe' 'Ams2KoreanBeta.LauncherProgram' (Join-Path $output 'AMS2 Korean VR Launcher.exe') (@((Join-Path $source 'LauncherProgram.cs'),$assembly) + $shared + $launcherCore) ($win32 + $launcherResources + $compatibilityResources + '/define:VR_LAUNCHER')
Invoke-Csc 'exe' 'Ams2KoreanBeta.TestCliProgram' (Join-Path $output 'AMS2 Korean Patch TestCli.exe') ((@((Join-Path $source 'TestCliProgram.cs'),$assembly) + $core) + $shared) $compatibilityResources
if (Test-Path -LiteralPath (Join-Path $source 'LauncherUpdateTest.cs')) {
    Invoke-Csc 'exe' 'Ams2KoreanBeta.LauncherUpdateTest' (Join-Path $output 'AMS2 Launcher Update Test.exe') (@((Join-Path $source 'LauncherUpdateTest.cs'),(Join-Path $source 'LauncherProgram.cs'),$assembly) + $shared + $launcherCore) ($launcherResources + $compatibilityResources)
}

Copy-Item -LiteralPath (Join-Path $source 'Installer.exe.config') -Destination (Join-Path $output "AMS2-Korean-Patch-OB-$Version.exe.config") -Force
Copy-Item -LiteralPath (Join-Path $assetSource 'assets') -Destination (Join-Path $output 'assets') -Recurse -Force

$patcherOutput = Join-Path $output 'runtime'
$patcherIntermediate = Join-Path $intermediate 'DynamicBffPatcher'
$patcherBuildRoot = Join-Path $intermediate 'DynamicBffPatcher-bin'
New-Item -ItemType Directory -Path $patcherOutput,$patcherIntermediate,$patcherBuildRoot -Force | Out-Null
$baseIntermediateArg = '-p:BaseIntermediateOutputPath=' + $patcherIntermediate + '\'
$projectExtensionsArg = '-p:MSBuildProjectExtensionsPath=' + $patcherIntermediate + '\'
$baseOutputArg = '-p:BaseOutputPath=' + $patcherBuildRoot + '\'
dotnet publish (Join-Path $source 'DynamicBffPatcher\BffEntryInspect.csproj') -c Release -o $patcherOutput --nologo $baseIntermediateArg $projectExtensionsArg $baseOutputArg
if ($LASTEXITCODE -ne 0) { throw 'DynamicBffPatcher publish failed.' }

$head = (& git -C $repo rev-parse HEAD).Trim()
$files = Get-ChildItem -LiteralPath $output -File -Recurse | Sort-Object FullName | ForEach-Object {
    [pscustomobject]@{
        path = $_.FullName.Substring($output.Length).TrimStart('\')
        bytes = $_.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    }
}
$metadata = [ordered]@{
    version = $Version
    source_commit = $head
    build_time_utc = [DateTime]::UtcNow.ToString('o')
    framework_compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    dotnet_sdk = (& dotnet --version).Trim()
    output_root = $output
    files = @($files)
}
$metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'build-metadata.json') -Encoding utf8
Write-Host "PASS: $output"
