param(
    [string]$TextRoot = 'E:\SteamLibrary\steamapps\common\Automobilista 2\text',
    [string]$Output = 'E:\AMS2_Korean_Work\AMS2\reports\0.6.7\tdb-runtime-source-candidates.json'
)

$ErrorActionPreference = 'Stop'

function Read-LpUtf8 {
    param([System.IO.BinaryReader]$Reader)
    $length = $Reader.ReadUInt32()
    if ($length -gt 10485760) { throw "Implausible UTF-8 string length: $length" }
    return [Text.Encoding]::UTF8.GetString($Reader.ReadBytes([int]$length))
}

function Read-Tdb {
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
        $languages = [Collections.Generic.Dictionary[string,string[]]]::new([StringComparer]::OrdinalIgnoreCase)
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
            $languages.Add($name, $values.ToArray())
        }
        return [pscustomobject]@{ Keys = $keys.ToArray(); Languages = $languages }
    }
    finally {
        if ($null -ne $reader) { $reader.Dispose() } else { $stream.Dispose() }
    }
}

$patterns = @(
    'Distance', 'Length', 'Meter', 'Metre', 'KMFormat', 'LimitedSetup', 'Limited Setup',
    'ParcFerme', 'Parc Ferme', 'TrackDetails', 'PlayTimeFormat', 'MainMenu_Time2'
)
$rows = [Collections.Generic.List[object]]::new()
foreach ($file in Get-ChildItem -LiteralPath $TextRoot -Filter '*.tdb' -File | Sort-Object Name) {
    $doc = Read-Tdb $file.FullName
    if (-not $doc.Languages.ContainsKey('English') -or -not $doc.Languages.ContainsKey('Korean')) { continue }
    $english = $doc.Languages['English']
    $korean = $doc.Languages['Korean']
    for ($index = 0; $index -lt $doc.Keys.Count; $index++) {
        $haystack = "$($doc.Keys[$index])`n$($english[$index])`n$($korean[$index])"
        $matched = @($patterns | Where-Object { $haystack.IndexOf($_, [StringComparison]::OrdinalIgnoreCase) -ge 0 })
        if ($matched.Count -eq 0) { continue }
        $rows.Add([ordered]@{
            file = $file.Name
            index = $index
            key = $doc.Keys[$index]
            english = $english[$index]
            korean = $korean[$index]
            matched = $matched
        })
    }
}
$report = [ordered]@{
    schema = 'ams2-kr-067-tdb-runtime-source-candidates-v1'
    text_root = $TextRoot
    record_count = $rows.Count
    records = $rows.ToArray()
}
[IO.File]::WriteAllText($Output, (($report | ConvertTo-Json -Depth 8) + "`n"), [Text.UTF8Encoding]::new($false))
[pscustomobject]@{ output = $Output; record_count = $rows.Count } | ConvertTo-Json
