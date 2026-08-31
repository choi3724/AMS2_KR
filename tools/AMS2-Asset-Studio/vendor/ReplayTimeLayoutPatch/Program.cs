using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace ReplayTimeLayoutPatch
{
    internal static class Program
    {
        private const string SourceBguiSha256 = "4E47A66E200F1F3EF61603BDF44AC9DF9FA1CCD81A5D87875F539DF135E25990";
        private const string SourceBfontSha256 = "8CA0523F4D34341A03DD284583C6A73D5B594EE38D3223CBB54505CF4E386C64";
        private const string SourceEmbeddedName = "ams2_font_hud_main";
        private const string CandidateEmbeddedName = "kr13_time_hud_main";
        private const string OldFont = @"gui\ams2_font_hud_main.bfont";
        private const string NewFont = @"gui\kr13_time_hud_main.bfont";
        private static readonly int[] SplitObjects =
        {
            7530, 16522, 25514, 34506, 43498, 52490,
            61482, 70474, 79466, 88458, 97450,
        };
        private static readonly int[] CondensedCodepoints = { '.', ':' };
        private static readonly int[] DigitCodepoints = Enumerable.Range('0', 10).ToArray();
        private static readonly string[] ValidationStrings =
        {
            "0:00.000", "0:59.999", "1:23.456", "9:59.999",
            "12:34.567",
        };

        private static int Main(string[] args)
        {
            try
            {
                if (args.Length != 5)
                {
                    Console.Error.WriteLine("Usage: ReplayTimeLayoutPatch <source.bgui> <source.bfont> <output.bgui> <output.bfont> <report.json>");
                    return 2;
                }

                var sourceBgui = File.ReadAllBytes(args[0]);
                var sourceBfont = File.ReadAllBytes(args[1]);
                RequireSha(sourceBgui, SourceBguiSha256, "BGUI");
                RequireSha(sourceBfont, SourceBfontSha256, "BFONT");
                if (Encoding.UTF8.GetByteCount(OldFont) != Encoding.UTF8.GetByteCount(NewFont))
                    throw new InvalidOperationException("Dedicated BFONT route must be byte-length preserving.");

                var candidateBgui = (byte[])sourceBgui.Clone();
                var allowedBgui = new HashSet<int>();
                var bguiRecords = new List<object>();
                var oldFontBytes = Encoding.UTF8.GetBytes(OldFont);
                var newFontBytes = Encoding.UTF8.GetBytes(NewFont);
                foreach (var objectOffset in SplitObjects)
                {
                    var nameLength = candidateBgui[objectOffset + 4];
                    var name = Encoding.UTF8.GetString(candidateBgui, objectOffset + 5, nameLength);
                    if (name != "SplitApplink")
                        throw new InvalidOperationException($"Unexpected object {name} at 0x{objectOffset:X}.");

                    var xOffset = objectOffset + 13 + nameLength;
                    var widthOffset = xOffset + 8;
                    var oldX = BitConverter.ToSingle(candidateBgui, xOffset);
                    var oldWidth = BitConverter.ToSingle(candidateBgui, widthOffset);
                    if (Math.Abs(oldX - 76.0f) > 0.001f || Math.Abs(oldWidth - 70.0f) > 0.001f)
                        throw new InvalidOperationException($"Unexpected bounds x={oldX}, width={oldWidth} at 0x{objectOffset:X}.");

                    var alignmentOffset = objectOffset + 53 + nameLength;
                    var oldHorizontalAlignment = candidateBgui[alignmentOffset];
                    if (oldHorizontalAlignment != 4)
                        throw new InvalidOperationException($"Unexpected horizontal alignment {oldHorizontalAlignment} at 0x{objectOffset:X}.");

                    var fontOffset = FindUnique(candidateBgui, oldFontBytes, objectOffset, 256);
                    Buffer.BlockCopy(newFontBytes, 0, candidateBgui, fontOffset, newFontBytes.Length);
                    foreach (var offset in Enumerable.Range(fontOffset, newFontBytes.Length)) allowedBgui.Add(offset);

                    bguiRecords.Add(new
                    {
                        object_name = name,
                        object_offset = objectOffset,
                        x_offset = xOffset,
                        alignment_offset = alignmentOffset,
                        font_offset = fontOffset,
                        old_x = oldX,
                        new_x = oldX,
                        width = oldWidth,
                        old_horizontal_alignment = oldHorizontalAlignment,
                        new_horizontal_alignment = oldHorizontalAlignment,
                        old_font = OldFont,
                        new_font = NewFont,
                    });
                }

                var bguiChanged = ChangedOffsets(sourceBgui, candidateBgui);
                var bguiUnexpected = bguiChanged.Where(offset => !allowedBgui.Contains(offset)).ToArray();
                if (bguiUnexpected.Length != 0)
                    throw new InvalidOperationException("Unexpected BGUI byte changes at " + string.Join(",", bguiUnexpected.Select(x => $"0x{x:X}")));

                var candidateBfont = (byte[])sourceBfont.Clone();
                var font = ParseFont(sourceBfont);
                var allowedBfont = new HashSet<int>();
                var metricRecords = new List<object>();
                if (font.EmbeddedName != SourceEmbeddedName || SourceEmbeddedName.Length != CandidateEmbeddedName.Length)
                    throw new InvalidOperationException("Unexpected source BFONT embedded name contract.");
                var candidateNameBytes = Encoding.UTF8.GetBytes(CandidateEmbeddedName);
                Buffer.BlockCopy(candidateNameBytes, 0, candidateBfont, 20, candidateNameBytes.Length);
                foreach (var offset in Enumerable.Range(20, candidateNameBytes.Length)) allowedBfont.Add(offset);
                foreach (var character in CondensedCodepoints)
                {
                    var codepoint = (int)(char)character;
                    var index = Array.IndexOf(font.Codepoints, codepoint);
                    if (index < 0)
                        throw new InvalidOperationException($"Source BFONT is missing U+{codepoint:X4}.");
                    var metricOffset = font.MetricStart + index * 12;
                    var bearing = BitConverter.ToInt32(candidateBfont, metricOffset);
                    var rasterWidth = BitConverter.ToInt32(candidateBfont, metricOffset + 4);
                    var oldAdvance = BitConverter.ToInt32(candidateBfont, metricOffset + 8);
                    if (oldAdvance != 4)
                        throw new InvalidOperationException($"Unexpected U+{codepoint:X4} advance {oldAdvance}.");
                    const int newAdvance = 3;
                    Buffer.BlockCopy(BitConverter.GetBytes(newAdvance), 0, candidateBfont, metricOffset + 8, 4);
                    foreach (var offset in Enumerable.Range(metricOffset + 8, 4)) allowedBfont.Add(offset);
                    metricRecords.Add(new
                    {
                        character = ((char)codepoint).ToString(),
                        codepoint = $"U+{codepoint:X4}",
                        glyph_index = index,
                        metric_offset = metricOffset,
                        bearing,
                        raster_width = rasterWidth,
                        old_advance = oldAdvance,
                        new_advance = newAdvance,
                    });
                }

                foreach (var codepoint in DigitCodepoints)
                {
                    var index = Array.IndexOf(font.Codepoints, codepoint);
                    if (index < 0)
                        throw new InvalidOperationException($"Source BFONT is missing U+{codepoint:X4}.");
                    var metricOffset = font.MetricStart + index * 12;
                    var bearing = BitConverter.ToInt32(candidateBfont, metricOffset);
                    var rasterWidth = BitConverter.ToInt32(candidateBfont, metricOffset + 4);
                    var oldAdvance = BitConverter.ToInt32(candidateBfont, metricOffset + 8);
                    if (oldAdvance != 8)
                        throw new InvalidOperationException($"Unexpected U+{codepoint:X4} advance {oldAdvance}.");
                    const int newAdvance = 9;
                    Buffer.BlockCopy(BitConverter.GetBytes(newAdvance), 0, candidateBfont, metricOffset + 8, 4);
                    foreach (var offset in Enumerable.Range(metricOffset + 8, 4)) allowedBfont.Add(offset);
                    metricRecords.Add(new
                    {
                        character = ((char)codepoint).ToString(),
                        codepoint = $"U+{codepoint:X4}",
                        glyph_index = index,
                        metric_offset = metricOffset,
                        bearing,
                        raster_width = rasterWidth,
                        old_advance = oldAdvance,
                        new_advance = newAdvance,
                    });
                }

                var bfontChanged = ChangedOffsets(sourceBfont, candidateBfont);
                var bfontUnexpected = bfontChanged.Where(offset => !allowedBfont.Contains(offset)).ToArray();
                if (bfontUnexpected.Length != 0)
                    throw new InvalidOperationException("Unexpected BFONT byte changes at " + string.Join(",", bfontUnexpected.Select(x => $"0x{x:X}")));

                var patchedFont = ParseFont(candidateBfont);
                var widths = ValidationStrings.Select(value => new
                {
                    value,
                    source_visible_width = MeasureVisible(font, value),
                    candidate_visible_width = MeasureVisible(patchedFont, value),
                    candidate_pen_width = MeasureAdvance(patchedFont, value),
                    candidate_box_width = 70,
                    candidate_box_remaining = 70 - MeasureAdvance(patchedFont, value),
                    candidate_last_glyph_trailing_space = LastGlyphTrailingSpace(patchedFont, value),
                }).ToArray();
                if (widths.Any(row => row.candidate_box_remaining < 0 || row.candidate_last_glyph_trailing_space < 1))
                    throw new InvalidOperationException("A validation time exceeds the box or lacks trailing glyph space.");

                WriteBytes(args[2], candidateBgui);
                WriteBytes(args[3], candidateBfont);
                var report = new
                {
                    resource = @"gui\hud_leaderboard2_1_6.bgui",
                    bff_entry_index = 293,
                    runtime_route_evidence = "Runtime proved that x/alignment changes and a dedicated path with the original embedded BFONT name were ignored by the renderer cache. Keep all 11 objects at stock bounds/right alignment, route them to a dedicated BFONT, and change its equal-length embedded name to kr13_time_hud_main so the matching byte-exact DDS clone is loaded. Only period/colon advances change 4 to 3 and digit advances change 8 to 9; every other Latin and all Hangul metrics, glyph rasters, UVs and DDS pixels remain exact.",
                    bgui = new
                    {
                        source_sha256 = Sha256(sourceBgui),
                        candidate_sha256 = Sha256(candidateBgui),
                        source_size = sourceBgui.Length,
                        candidate_size = candidateBgui.Length,
                        changed_byte_offsets = bguiChanged,
                        records = bguiRecords,
                    },
                    bfont = new
                    {
                        source_sha256 = Sha256(sourceBfont),
                        candidate_sha256 = Sha256(candidateBfont),
                        source_size = sourceBfont.Length,
                        candidate_size = candidateBfont.Length,
                        source_embedded_name = font.EmbeddedName,
                        candidate_embedded_name = patchedFont.EmbeddedName,
                        atlas_reuse = "kr13_time_hud_main.dds is a byte-exact clone of ams2_font_hud_main.dds; only its filename follows the dedicated embedded name.",
                        changed_byte_offsets = bfontChanged,
                        records = metricRecords,
                    },
                    patch_contract = new
                    {
                        split_x_changes = 0,
                        split_alignment_changes = 0,
                        split_font_route_changes = bguiRecords.Count,
                        split_width_changes = 0,
                        digit_metric_changes = DigitCodepoints.Length,
                        punctuation_advance_changes = CondensedCodepoints.Length,
                        embedded_name_changes = 1,
                        other_latin_metric_changes = 0,
                        hangul_metric_changes = 0,
                        glyph_raster_changes = 0,
                        uv_changes = 0,
                        dds_changes = 0,
                        unexpected_byte_changes = bguiUnexpected.Length + bfontUnexpected.Length,
                    },
                    validation_strings = widths,
                };
                var json = JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true });
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[4])));
                File.WriteAllText(args[4], json + Environment.NewLine, new UTF8Encoding(false));
                Console.WriteLine(json);
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(ex.ToString());
                return 1;
            }
        }

        private static FontInfo ParseFont(byte[] data)
        {
            var nameLength = checked((int)BitConverter.ToUInt32(data, 16));
            var nameEnd = 20 + nameLength;
            var embeddedName = Encoding.UTF8.GetString(data, 20, nameLength);
            var count = checked((int)BitConverter.ToUInt32(data, nameEnd + 8));
            var codepointStart = nameEnd + 12;
            var metricStart = codepointStart + count * 2 + count * 16;
            var codepoints = new int[count];
            var metrics = new Metric[count];
            for (var index = 0; index < count; index++)
            {
                codepoints[index] = BitConverter.ToUInt16(data, codepointStart + index * 2);
                var offset = metricStart + index * 12;
                metrics[index] = new Metric(
                    BitConverter.ToInt32(data, offset),
                    BitConverter.ToInt32(data, offset + 4),
                    BitConverter.ToInt32(data, offset + 8));
            }
            return new FontInfo(embeddedName, codepoints, metrics, metricStart);
        }

        private static int MeasureVisible(FontInfo font, string value)
        {
            var pen = 0;
            var right = 0;
            foreach (var character in value)
            {
                var index = Array.IndexOf(font.Codepoints, (int)character);
                if (index < 0) throw new InvalidOperationException($"Missing U+{(int)character:X4} in validation text.");
                var metric = font.Metrics[index];
                right = Math.Max(right, pen + metric.Bearing + metric.RasterWidth);
                pen += metric.Advance;
            }
            return right;
        }

        private static int MeasureAdvance(FontInfo font, string value) =>
            value.Sum(character => font.Metrics[Array.IndexOf(font.Codepoints, (int)character)].Advance);

        private static int LastGlyphTrailingSpace(FontInfo font, string value)
        {
            var index = Array.IndexOf(font.Codepoints, (int)value[value.Length - 1]);
            var metric = font.Metrics[index];
            return metric.Advance - metric.Bearing - metric.RasterWidth;
        }

        private static int FindUnique(byte[] data, byte[] value, int start, int length)
        {
            var matches = new List<int>();
            var end = Math.Min(data.Length - value.Length, start + length);
            for (var offset = start; offset <= end; offset++)
                if (value.SequenceEqual(data.Skip(offset).Take(value.Length))) matches.Add(offset);
            if (matches.Count != 1)
                throw new InvalidOperationException($"Expected one font path near 0x{start:X}, found {matches.Count}.");
            return matches[0];
        }

        private static int[] ChangedOffsets(byte[] before, byte[] after) =>
            Enumerable.Range(0, before.Length).Where(index => before[index] != after[index]).ToArray();

        private static void RequireSha(byte[] data, string expected, string label)
        {
            var actual = Sha256(data);
            if (!string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException($"{label} SHA-256 is {actual}; expected {expected}.");
        }

        private static void WriteBytes(string path, byte[] data)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path)));
            File.WriteAllBytes(path, data);
        }

        private static string Sha256(byte[] data)
        {
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(data)).Replace("-", string.Empty);
        }

        private sealed class FontInfo
        {
            public FontInfo(string embeddedName, int[] codepoints, Metric[] metrics, int metricStart)
            {
                EmbeddedName = embeddedName;
                Codepoints = codepoints;
                Metrics = metrics;
                MetricStart = metricStart;
            }
            public string EmbeddedName { get; }
            public int[] Codepoints { get; }
            public Metric[] Metrics { get; }
            public int MetricStart { get; }
        }

        private readonly struct Metric
        {
            public Metric(int bearing, int rasterWidth, int advance)
            {
                Bearing = bearing;
                RasterWidth = rasterWidth;
                Advance = advance;
            }
            public int Bearing { get; }
            public int RasterWidth { get; }
            public int Advance { get; }
        }
    }
}
