$ErrorActionPreference = 'Stop'

$Repo = 'E:\AMS2_Korean_Work\AMS2'
$ReleaseRoot = 'E:\AMS2_Korean_Work\releases'
$V065Release = Get-ChildItem -LiteralPath $ReleaseRoot -Directory | Where-Object Name -Like '*CB 0.6.5' | Select-Object -First 1
$V066Release = Get-ChildItem -LiteralPath $ReleaseRoot -Directory | Where-Object Name -Like '*CB 0.6.6' | Select-Object -First 1
if ($null -eq $V065Release -or $null -eq $V066Release) { throw '0.6.5/0.6.6 release baseline missing' }
$V065 = Join-Path $V065Release.FullName 'payload\direct'
$V066 = Join-Path $V066Release.FullName 'payload\direct'
$Live = 'E:\SteamLibrary\steamapps\common\Automobilista 2'
$Output = Join-Path $Repo 'reports\0.6.7\v066-semantic-regression-audit.json'

function Read-LpUtf8 {
    param([System.IO.BinaryReader]$Reader)
    $length = $Reader.ReadUInt32()
    if ($length -gt 10485760) { throw "Implausible UTF-8 string length: $length" }
    return [Text.Encoding]::UTF8.GetString($Reader.ReadBytes([int]$length))
}

function Read-TdbKorean {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    try {
        $reader = [IO.BinaryReader]::new($stream)
        [void]$reader.ReadUInt32()
        [void](Read-LpUtf8 $reader)
        $languageCount = $reader.ReadUInt32()
        $groupCount = $reader.ReadUInt32()
        $keyCount = $reader.ReadUInt32()
        [void]$reader.ReadUInt32()
        [void]$reader.ReadUInt32()
        [void]$reader.ReadUInt32()
        for ($i = 0; $i -lt $groupCount; $i++) { [void](Read-LpUtf8 $reader) }
        $keys = [Collections.Generic.List[string]]::new()
        for ($i = 0; $i -lt $keyCount; $i++) { $keys.Add((Read-LpUtf8 $reader)) }
        $korean = $null
        for ($languageIndex = 0; $languageIndex -lt $languageCount; $languageIndex++) {
            $name = Read-LpUtf8 $reader
            $blockSize = $reader.ReadUInt32()
            $blockEnd = $stream.Position + $blockSize
            $values = [Collections.Generic.List[string]]::new()
            for ($record = 0; $record -lt $keyCount; $record++) {
                [void]$reader.ReadUInt64()
                $units = $reader.ReadUInt32()
                $values.Add([Text.Encoding]::Unicode.GetString($reader.ReadBytes([int]($units * 2))))
            }
            if ($stream.Position -ne $blockEnd) { throw "$Path/$name block boundary mismatch" }
            if ($name -ieq 'Korean') { $korean = $values.ToArray() }
        }
        if ($stream.Position -ne $stream.Length) { throw "$Path has trailing bytes" }
        if ($null -eq $korean) { throw "$Path has no Korean language" }
        return [pscustomobject]@{ Keys = $keys.ToArray(); Values = $korean }
    }
    finally {
        if ($null -ne $reader) { $reader.Dispose() }
        else { $stream.Dispose() }
    }
}

function Read-BFontSummary {
    param([string]$Path)
    $data = [IO.File]::ReadAllBytes($Path)
    if ($data.Length -lt 40) { throw "BFONT too short: $Path" }
    $nameLength = [BitConverter]::ToUInt32($data, 16)
    $nameEnd = 20 + [int]$nameLength
    $glyphCount = [BitConverter]::ToUInt32($data, $nameEnd + 8)
    $cpStart = $nameEnd + 12
    $metricStart = $cpStart + [int]$glyphCount * 2 + [int]$glyphCount * 16
    $codepoints = [Collections.Generic.HashSet[int]]::new()
    $metrics = [Collections.Generic.Dictionary[int,string]]::new()
    for ($index = 0; $index -lt $glyphCount; $index++) {
        $codepoint = [BitConverter]::ToUInt16($data, $cpStart + $index * 2)
        [void]$codepoints.Add($codepoint)
        $offset = $metricStart + $index * 12
        $metrics.Add($codepoint, ('{0},{1},{2}' -f [BitConverter]::ToInt32($data, $offset), [BitConverter]::ToInt32($data, $offset + 4), [BitConverter]::ToInt32($data, $offset + 8)))
    }
    if ($codepoints.Count -ne $glyphCount) { throw "Duplicate BFONT codepoint: $Path" }
    return [pscustomobject]@{ GlyphCount = [int]$glyphCount; Codepoints = $codepoints; Metrics = $metrics }
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-SafeJsonText {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return $null }
    $builder = [Text.StringBuilder]::new()
    foreach ($character in $Value.ToCharArray()) {
        if ([int]$character -lt 0x20) { [void]$builder.Append(('\u{0:X4}' -f [int]$character)) }
        else { [void]$builder.Append($character) }
    }
    return $builder.ToString()
}

function Get-DriverNameSemanticText {
    param([string]$Value)
    return $Value.Replace([string]' ', [string]'').Replace([string][char]0x00A0, [string]'')
}

function Audit-Tdb {
    param([string]$RelativePath)
    $oldPath = Join-Path $V065 $RelativePath
    $basePath = Join-Path $V066 $RelativePath
    $livePath = Join-Path $Live $RelativePath
    $old = if (Test-Path -LiteralPath $oldPath) { Read-TdbKorean $oldPath } else { $null }
    $base = Read-TdbKorean $basePath
    $actual = Read-TdbKorean $livePath
    if ($base.Keys.Count -ne $actual.Keys.Count) { throw "v0.6.6/live TDB key count mismatch: $RelativePath" }
    for ($index = 0; $index -lt $base.Keys.Count; $index++) {
        if ($base.Keys[$index] -cne $actual.Keys[$index]) { throw "v0.6.6/live TDB key layout mismatch: $RelativePath/$index" }
    }
    $oldMap = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::Ordinal)
    $oldOccurrences = [Collections.Generic.Dictionary[string,int]]::new([StringComparer]::Ordinal)
    if ($null -ne $old) {
        for ($index = 0; $index -lt $old.Keys.Count; $index++) {
            $oldKey = $old.Keys[$index]
            $ordinal = 0
            if ($oldOccurrences.ContainsKey($oldKey)) { $ordinal = $oldOccurrences[$oldKey] }
            $oldOccurrences[$oldKey] = $ordinal + 1
            $oldMap.Add("$oldKey`0$ordinal", $old.Values[$index])
        }
    }
    $baseOccurrences = [Collections.Generic.Dictionary[string,int]]::new([StringComparer]::Ordinal)
    $counts = [ordered]@{
        v066_changed_records = 0
        v066_added_records = 0
        preserved_exact = 0
        preserved_semantic_format_variant = 0
        reverted_to_v065 = 0
        changed_after_v066 = 0
    }
    $rows = [Collections.Generic.List[object]]::new()
    for ($index = 0; $index -lt $base.Keys.Count; $index++) {
        $key = $base.Keys[$index]
        $ordinal = 0
        if ($baseOccurrences.ContainsKey($key)) { $ordinal = $baseOccurrences[$key] }
        $baseOccurrences[$key] = $ordinal + 1
        $before = $null
        $hasBefore = $oldMap.TryGetValue("$key`0$ordinal", [ref]$before)
        $expected = $base.Values[$index]
        $liveValue = $actual.Values[$index]
        if ($hasBefore -and $before -ceq $expected) { continue }
        $counts.v066_changed_records++
        if (-not $hasBefore) { $counts.v066_added_records++ }
        if ($liveValue -ceq $expected) {
            $status = 'PRESERVED_EXACT'
            $counts.preserved_exact++
        }
        elseif ($RelativePath -ieq 'text\drivers.tdb' -and
                (Get-DriverNameSemanticText $liveValue) -ceq (Get-DriverNameSemanticText $expected)) {
            $status = 'PRESERVED_SEMANTIC_FORMAT_VARIANT'
            $counts.preserved_semantic_format_variant++
        }
        elseif ($hasBefore -and $liveValue -ceq $before) {
            $status = 'REVERTED_TO_V065'
            $counts.reverted_to_v065++
        }
        else {
            $status = 'CHANGED_AFTER_V066'
            $counts.changed_after_v066++
        }
        if ($status -in @('REVERTED_TO_V065', 'CHANGED_AFTER_V066') -or $rows.Count -lt 50) {
            $rows.Add([ordered]@{
                index = $index
                key = $key
                key_occurrence = $ordinal
                v065 = if ($hasBefore) { Get-SafeJsonText $before } else { $null }
                v066 = Get-SafeJsonText $expected
                live = Get-SafeJsonText $liveValue
                status = $status
            })
        }
    }
    return [ordered]@{
        file = $RelativePath
        v065_sha256 = if ($null -ne $old) { Get-Sha256 $oldPath } else { $null }
        v066_sha256 = Get-Sha256 $basePath
        live_sha256 = Get-Sha256 $livePath
        counts = $counts
        non_exact_or_sample_records = $rows.ToArray()
    }
}

function Audit-Fonts {
    $oldRoot = Join-Path $V065 'gui'
    $baseRoot = Join-Path $V066 'gui'
    $liveRoot = Join-Path $Live 'GUI'
    $rows = [Collections.Generic.List[object]]::new()
    $totals = [ordered]@{
        font_aliases = 0
        aliases_with_v066_additions = 0
        aliases_missing_v066_codepoints = 0
        missing_v066_codepoints_total = 0
        aliases_with_nbsp = 0
        v065_common_metric_mismatches = 0
    }
    foreach ($basePath in Get-ChildItem -LiteralPath $baseRoot -Filter 'kr*.bfont' | Sort-Object Name) {
        $oldPath = Join-Path $oldRoot $basePath.Name
        $livePath = Join-Path $liveRoot $basePath.Name
        if (-not (Test-Path -LiteralPath $oldPath) -or -not (Test-Path -LiteralPath $livePath)) { continue }
        $totals.font_aliases++
        $old = Read-BFontSummary $oldPath
        $base = Read-BFontSummary $basePath.FullName
        $actual = Read-BFontSummary $livePath
        $additions = @($base.Codepoints | Where-Object { -not $old.Codepoints.Contains($_) } | Sort-Object)
        $missing = @($base.Codepoints | Where-Object { -not $actual.Codepoints.Contains($_) } | Sort-Object)
        if ($additions.Count) { $totals.aliases_with_v066_additions++ }
        if ($missing.Count) {
            $totals.aliases_missing_v066_codepoints++
            $totals.missing_v066_codepoints_total += $missing.Count
        }
        $nbsp = $actual.Codepoints.Contains(0x00A0)
        if ($nbsp) { $totals.aliases_with_nbsp++ }
        $metricMismatches = 0
        foreach ($codepoint in $old.Codepoints) {
            if ($actual.Codepoints.Contains($codepoint) -and $old.Metrics[$codepoint] -cne $actual.Metrics[$codepoint]) { $metricMismatches++ }
        }
        $totals.v065_common_metric_mismatches += $metricMismatches
        $rows.Add([ordered]@{
            alias = $basePath.BaseName
            v065_glyph_count = $old.GlyphCount
            v066_glyph_count = $base.GlyphCount
            live_glyph_count = $actual.GlyphCount
            v066_additions = $additions.Count
            missing_from_live = $missing.Count
            missing = @($missing | ForEach-Object { [ordered]@{ codepoint = ('U+{0:X4}' -f $_); character = [char]$_ } })
            nbsp_present = $nbsp
            v065_common_metric_mismatches = $metricMismatches
        })
    }
    return [ordered]@{ totals = $totals; fonts = $rows.ToArray() }
}

$tdbRows = @()
$tdbRows += Audit-Tdb 'text\game.tdb'
$tdbRows += Audit-Tdb 'text\general.tdb'
$tdbRows += Audit-Tdb 'text\drivers.tdb'
$fonts = Audit-Fonts
$reverted = ($tdbRows | ForEach-Object { $_.counts.reverted_to_v065 } | Measure-Object -Sum).Sum
$missing = $fonts.totals.missing_v066_codepoints_total
$report = [ordered]@{
    schema = 'ams2-kr-067-v066-semantic-regression-audit-v1'
    status = if ($reverted -eq 0 -and $missing -eq 0) { 'PASS' } else { 'BLOCK' }
    baseline = 'Closed Beta 0.6.6 direct payload'
    tdb = $tdbRows
    fonts = $fonts
    summary = [ordered]@{
        tdb_records_reverted_to_v065 = $reverted
        v066_font_codepoints_missing_from_live = $missing
        note = 'CHANGED_AFTER_V066 is reviewed separately as an intentional 0.6.7 edit.'
    }
}
$json = $report | ConvertTo-Json -Depth 12
[IO.File]::WriteAllText($Output, $json + "`n", [Text.UTF8Encoding]::new($false))
[pscustomobject]@{ status = $report['status']; summary = $report['summary']; font_totals = $fonts.totals } | ConvertTo-Json -Depth 6
if ($report['status'] -ne 'PASS') { exit 1 }
