param(
    [Parameter(Mandatory = $true)] [string] $BaseGuiDir,
    [Parameter(Mandatory = $true)] [string] $MetricSourceGuiDir,
    [Parameter(Mandatory = $true)] [string] $OutputGuiDir,
    [Parameter(Mandatory = $true)] [string] $ManifestPath
)

$ErrorActionPreference = "Stop"

function Get-Sha256([string] $Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash
}

function Read-BfontLayout([string] $Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $stream = [IO.MemoryStream]::new($bytes, $false)
    $reader = [IO.BinaryReader]::new($stream)
    try {
        $version = $reader.ReadUInt32()
        if ($version -ne 10) { throw "$Path is not a BFONT v10 file" }
        $null = $reader.ReadUInt32()
        $null = $reader.ReadUInt32()
        $null = $reader.ReadUInt32()
        $nameLength = $reader.ReadUInt32()
        $name = [Text.Encoding]::UTF8.GetString($reader.ReadBytes([int] $nameLength))
        $null = $reader.ReadUInt32()
        $null = $reader.ReadUInt32()
        $glyphCountOffset = [int] $stream.Position
        $glyphCount = $reader.ReadUInt32()
        $codepointStart = [int] $stream.Position
        $codepoints = New-Object 'System.UInt16[]' $glyphCount
        for ($index = 0; $index -lt $glyphCount; $index++) {
            $codepoints[$index] = $reader.ReadUInt16()
        }
        $uvStart = [int] $stream.Position
        $stream.Position += [int64] $glyphCount * 16
        $metricStart = [int] $stream.Position
        $stream.Position += [int64] $glyphCount * 12
        $footerStart = [int] $stream.Position
        $lineHeight = $reader.ReadUInt32()
        $baseline = $reader.ReadUInt32()
        $atlasCount = $reader.ReadUInt32()
        $glyphsPerAtlas = $reader.ReadUInt32()
        if ($atlasCount -lt 1 -or $glyphsPerAtlas -lt 1) {
            throw "$Path has an invalid multi-atlas footer"
        }
        return [pscustomobject]@{
            Path = $Path
            Bytes = $bytes
            Version = $version
            Name = $name
            GlyphCount = [int] $glyphCount
            GlyphCountOffset = $glyphCountOffset
            CodepointStart = $codepointStart
            UvStart = $uvStart
            MetricStart = $metricStart
            FooterStart = $footerStart
            Codepoints = $codepoints
            LineHeight = $lineHeight
            Baseline = $baseline
            AtlasCount = $atlasCount
            GlyphsPerAtlas = $glyphsPerAtlas
        }
    }
    finally {
        $reader.Dispose()
        $stream.Dispose()
    }
}

function Slice([byte[]] $Bytes, [int] $Start, [int] $Length) {
    $result = New-Object byte[] $Length
    [Array]::Copy($Bytes, $Start, $result, 0, $Length)
    return $result
}

function Test-BytesEqual([byte[]] $Left, [byte[]] $Right) {
    if ($Left.Length -ne $Right.Length) { return $false }
    for ($index = 0; $index -lt $Left.Length; $index++) {
        if ($Left[$index] -ne $Right[$index]) { return $false }
    }
    return $true
}

function Write-Bytes([IO.Stream] $Stream, [byte[]] $Bytes) {
    $Stream.Write($Bytes, 0, $Bytes.Length)
}

$baseRoot = [IO.Path]::GetFullPath($BaseGuiDir)
$metricRoot = [IO.Path]::GetFullPath($MetricSourceGuiDir)
$outputRoot = [IO.Path]::GetFullPath($OutputGuiDir)
[IO.Directory]::CreateDirectory($outputRoot) | Out-Null

$rows = New-Object System.Collections.Generic.List[object]
foreach ($basePath in Get-ChildItem -LiteralPath $baseRoot -Filter '*.bfont' | Sort-Object Name) {
    $metricPath = Join-Path $metricRoot $basePath.Name
    if (-not (Test-Path -LiteralPath $metricPath)) { continue }

    $base = Read-BfontLayout $basePath.FullName
    $metricSource = Read-BfontLayout $metricPath
    $baseNbspIndex = [Array]::IndexOf($base.Codepoints, [uint16] 0x00A0)
    $sourceNbspIndex = [Array]::IndexOf($metricSource.Codepoints, [uint16] 0x00A0)
    if ($baseNbspIndex -ge 0 -or $sourceNbspIndex -lt 0) { continue }
    if (($base.GlyphCount + 1) -gt ($base.AtlasCount * $base.GlyphsPerAtlas)) {
        throw "$($basePath.Name) has no atlas slot for an appended NBSP record"
    }

    $sourceMetricOffset = $metricSource.MetricStart + ($sourceNbspIndex * 12)
    $advance = [BitConverter]::ToInt32($metricSource.Bytes, $sourceMetricOffset + 8)
    if ($advance -le 0 -or $advance -gt 256) {
        throw "$($basePath.Name) has an invalid NBSP advance: $advance"
    }

    $memory = [IO.MemoryStream]::new()
    try {
        Write-Bytes $memory (Slice $base.Bytes 0 $base.GlyphCountOffset)
        Write-Bytes $memory ([BitConverter]::GetBytes([uint32] ($base.GlyphCount + 1)))
        Write-Bytes $memory (Slice $base.Bytes $base.CodepointStart ($base.GlyphCount * 2))
        Write-Bytes $memory ([BitConverter]::GetBytes([uint16] 0x00A0))
        Write-Bytes $memory (Slice $base.Bytes $base.UvStart ($base.GlyphCount * 16))
        Write-Bytes $memory (New-Object byte[] 16)
        Write-Bytes $memory (Slice $base.Bytes $base.MetricStart ($base.GlyphCount * 12))
        Write-Bytes $memory ([BitConverter]::GetBytes([int32] 0))
        Write-Bytes $memory ([BitConverter]::GetBytes([int32] 0))
        Write-Bytes $memory ([BitConverter]::GetBytes([int32] $advance))
        Write-Bytes $memory (Slice $base.Bytes $base.FooterStart ($base.Bytes.Length - $base.FooterStart))
        $outputBytes = $memory.ToArray()
    }
    finally {
        $memory.Dispose()
    }

    $outputPath = Join-Path $outputRoot $basePath.Name
    [IO.File]::WriteAllBytes($outputPath, $outputBytes)
    $check = Read-BfontLayout $outputPath
    if ($check.GlyphCount -ne ($base.GlyphCount + 1)) { throw "glyph count validation failed: $($basePath.Name)" }
    if ($check.Codepoints[$check.GlyphCount - 1] -ne 0x00A0) { throw "NBSP was not appended: $($basePath.Name)" }
    if (@(Compare-Object $base.Codepoints $check.Codepoints[0..($base.GlyphCount - 1)] -SyncWindow 0).Count -ne 0) {
        throw "existing codepoint order changed: $($basePath.Name)"
    }
    if (-not (Test-BytesEqual (Slice $base.Bytes $base.UvStart ($base.GlyphCount * 16)) (Slice $check.Bytes $check.UvStart ($base.GlyphCount * 16)))) {
        throw "existing UV bytes changed: $($basePath.Name)"
    }
    if (-not (Test-BytesEqual (Slice $base.Bytes $base.MetricStart ($base.GlyphCount * 12)) (Slice $check.Bytes $check.MetricStart ($base.GlyphCount * 12)))) {
        throw "existing metric bytes changed: $($basePath.Name)"
    }
    if (-not (Test-BytesEqual (Slice $base.Bytes $base.FooterStart ($base.Bytes.Length - $base.FooterStart)) (Slice $check.Bytes $check.FooterStart ($check.Bytes.Length - $check.FooterStart)))) {
        throw "footer changed: $($basePath.Name)"
    }

    $rows.Add([pscustomobject]@{
        file = $basePath.Name
        embedded_name = $base.Name
        base_sha256 = Get-Sha256 $basePath.FullName
        metric_source_sha256 = Get-Sha256 $metricPath
        output_sha256 = Get-Sha256 $outputPath
        old_glyph_count = $base.GlyphCount
        new_glyph_count = $check.GlyphCount
        appended_codepoint = 'U+00A0'
        appended_index = $base.GlyphCount
        appended_atlas_page = [Math]::Floor($base.GlyphCount / $base.GlyphsPerAtlas)
        left = 0
        width = 0
        advance = $advance
        existing_codepoints_exact = $true
        existing_uv_bytes_exact = $true
        existing_metric_bytes_exact = $true
        footer_exact = $true
        dds_changes_required = 0
    })
}

if ($rows.Count -ne 46) {
    throw "expected 46 BFONT outputs, produced $($rows.Count)"
}

$manifest = [ordered]@{
    schema = 'ams2-kr-067-safe-nbsp-bfont-v1'
    status = 'PASS'
    strategy = 'append-zero-area-nbsp-without-moving-existing-glyphs'
    font_count = $rows.Count
    existing_codepoint_changes = 0
    existing_uv_changes = 0
    existing_metric_changes = 0
    dds_changes = 0
    fonts = $rows
}
$manifestDirectory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($ManifestPath))
[IO.Directory]::CreateDirectory($manifestDirectory) | Out-Null
[IO.File]::WriteAllText(
    [IO.Path]::GetFullPath($ManifestPath),
    (($manifest | ConvertTo-Json -Depth 8) + "`n"),
    [Text.UTF8Encoding]::new($false)
)

Write-Output "PASS: generated $($rows.Count) safe BFONT files; DDS changes=0"
