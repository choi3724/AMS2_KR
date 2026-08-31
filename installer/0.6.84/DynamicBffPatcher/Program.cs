using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ICSharpCode.SharpZipLib.Zip.Compression;
using ICSharpCode.SharpZipLib.Zip.Compression.Streams;
using PCarsTools.Config;
using PCarsTools.Encryption;
using PCarsTools.Pak;

namespace Ams2DynamicBffPatcher
{
    internal static class Program
    {
        private const string TargetPath = "gui\\hud_infoabovecar.bgui";
        private const string StockRoute = "GUI\\font_phoenix_body_regular.bfont";
        private const string LegacyKoreanRoute = "GUI\\kr13_font_hud_main.bfont";
        private const string DesiredRoute = "GUI\\kr13_driver_name_semibold.bfont";
        private const int TocOffset = 0x130;

        private static int Main(string[] args)
        {
            try
            {
                if (args.Length == 4 && args[0] == "inspect")
                    return Inspect(args[1], args[2], args[3]);
                if (args.Length == 5 && args[0] == "patch")
                    return Patch(args[1], args[2], args[3], args[4]);
                Console.Error.WriteLine("Usage: AMS2.DynamicBffPatcher inspect <game-dir> <pak> <report.json>");
                Console.Error.WriteLine("   or: AMS2.DynamicBffPatcher patch <game-dir> <source-pak> <output-pak> <report.json>");
                return 2;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error.GetType().Name + ": " + error.Message);
                return 1;
            }
        }

        private static int Inspect(string gameDir, string pakPath, string reportPath)
        {
            var pak = OpenPak(gameDir, pakPath);
            var target = FindTarget(pak);
            byte[] bgui = Extract(pak, target.Index, Path.GetDirectoryName(Path.GetFullPath(reportPath)));
            string route = DetectRoute(bgui, out _);
            WriteReport(reportPath, new
            {
                schema = "ams2-kr-v0684-bff-inspect-v1",
                status = "PASS",
                archive = Path.GetFullPath(pakPath),
                archive_bytes = new FileInfo(pakPath).Length,
                archive_sha256 = Sha256(File.ReadAllBytes(pakPath)),
                entry_index = target.Index,
                entry_path = target.Path,
                entry_route = route,
                supported_route = IsSupportedRoute(route)
            });
            Console.WriteLine("route=" + route);
            return IsSupportedRoute(route) ? 0 : 3;
        }

        private static int Patch(string gameDir, string sourcePakPath, string outputPakPath, string reportPath)
        {
            var sourcePak = OpenPak(gameDir, sourcePakPath);
            if (sourcePak.Header.mEncryption != eEncryptionType.RC4)
                throw new InvalidOperationException("IGPHASEHUD archive is not RC4.");

            var target = FindTarget(sourcePak);
            var sourceEntry = sourcePak.Entries[target.Index];
            if (sourceEntry.mFileType != PakFileCompressionType.ZLib)
                throw new InvalidOperationException("Target BGUI entry is not ZLib-compressed.");

            byte[] sourceArchive = File.ReadAllBytes(sourcePakPath);
            byte[] sourceBgui = Extract(sourcePak, target.Index, Path.GetDirectoryName(Path.GetFullPath(reportPath)));
            string sourceRoute;
            byte[] patchedBgui = PatchProfileNameRoute(sourceBgui, out sourceRoute);

            if (sourceBgui.SequenceEqual(patchedBgui))
            {
                WriteExact(outputPakPath, sourceArchive);
                ValidateCandidate(gameDir, sourcePakPath, outputPakPath, target.Index, target.Path, patchedBgui, sourceArchive, sourceArchive);
                WritePatchReport(reportPath, sourcePakPath, outputPakPath, target, sourceEntry, sourceRoute, patchedBgui, sourceArchive, sourceArchive, sourceEntry.mSizeInPak, sourceEntry.mCRC, true, 0);
                return 0;
            }

            byte[] compressed = CompressZlib(patchedBgui);
            long nextData = sourcePak.Entries.Select(entry => (long)entry.mDataPos)
                .Where(position => position > (long)sourceEntry.mDataPos).DefaultIfEmpty(sourceArchive.LongLength).Min();
            long allocation = nextData - (long)sourceEntry.mDataPos;
            if (allocation <= 0 || compressed.LongLength > allocation)
                throw new InvalidOperationException("Compressed target payload exceeds its existing allocation.");

            byte[] encryptedPayload = (byte[])compressed.Clone();
            BPakFileEncryption.DecryptData(sourcePak.Header.mEncryption, encryptedPayload, encryptedPayload.Length, sourcePak.KeyIndex);

            int entryBytes = checked((int)(sourcePak.Header.mTocSize / sourcePak.Header.mFileCount));
            if (entryBytes != 42 || sourcePak.Header.mTocSize != sourcePak.Header.mFileCount * entryBytes)
                throw new InvalidOperationException("Unexpected IGPHASEHUD TOC structure.");
            if (TocOffset + sourcePak.Header.mTocSize > sourcePak.Header.mDataOffset)
                throw new InvalidOperationException("Invalid IGPHASEHUD TOC bounds.");

            byte[] decryptedToc = new byte[sourcePak.Header.mTocSize];
            Buffer.BlockCopy(sourceArchive, TocOffset, decryptedToc, 0, decryptedToc.Length);
            BPakFileEncryption.DecryptData(sourcePak.Header.mEncryption, decryptedToc, decryptedToc.Length, sourcePak.KeyIndex);
            int entryOffset = checked(target.Index * entryBytes);
            Buffer.BlockCopy(BitConverter.GetBytes((uint)compressed.Length), 0, decryptedToc, entryOffset + 16, 4);
            Buffer.BlockCopy(BitConverter.GetBytes((uint)patchedBgui.Length), 0, decryptedToc, entryOffset + 20, 4);
            uint crc = ~Crc32(encryptedPayload);
            Buffer.BlockCopy(BitConverter.GetBytes(crc), 0, decryptedToc, entryOffset + 34, 4);
            byte[] encryptedToc = (byte[])decryptedToc.Clone();
            BPakFileEncryption.DecryptData(sourcePak.Header.mEncryption, encryptedToc, encryptedToc.Length, sourcePak.KeyIndex);

            byte[] candidate = (byte[])sourceArchive.Clone();
            Buffer.BlockCopy(encryptedToc, 0, candidate, TocOffset, encryptedToc.Length);
            Buffer.BlockCopy(encryptedPayload, 0, candidate, checked((int)sourceEntry.mDataPos), encryptedPayload.Length);
            WriteExact(outputPakPath, candidate);

            int changedBytes = ValidateCandidate(gameDir, sourcePakPath, outputPakPath, target.Index, target.Path, patchedBgui, sourceArchive, candidate);
            WritePatchReport(reportPath, sourcePakPath, outputPakPath, target, sourceEntry, sourceRoute, patchedBgui, sourceArchive, candidate, compressed.Length, crc, false, changedBytes);
            return 0;
        }

        private static BPakFile OpenPak(string gameDir, string pakPath)
        {
            string languages = Path.Combine(gameDir, "Languages", "Languages.bml");
            if (!File.Exists(languages) || !BConfig.Instance.LoadConfig(languages))
                throw new InvalidOperationException("Languages.bml could not be loaded.");
            BPakFileEncryption.SetKeyset(KeysetType.PC2AndAbove);
            var pak = new BPakFile();
            pak.FromFile(pakPath, withExtraInfo: true);
            if (pak.Entries.Count != pak.ExtEntries.Count || pak.Entries.Count != pak.Header.mFileCount)
                throw new InvalidOperationException("IGPHASEHUD entry tables are inconsistent.");
            return pak;
        }

        private static (int Index, string Path) FindTarget(BPakFile pak)
        {
            var matches = pak.ExtEntries.Select((extra, index) => new { index, path = Normalize(extra.Path) })
                .Where(item => item.path.Equals(TargetPath, StringComparison.OrdinalIgnoreCase)).ToArray();
            if (matches.Length != 1)
                throw new InvalidOperationException("Expected exactly one " + TargetPath + " entry; found " + matches.Length + ".");
            return (matches[0].index, matches[0].path);
        }

        private static byte[] Extract(BPakFile pak, int index, string tempParent)
        {
            string root = Path.Combine(String.IsNullOrWhiteSpace(tempParent) ? Path.GetTempPath() : tempParent, "bff-extract-" + Guid.NewGuid().ToString("N"));
            string path = Path.Combine(root, "target.bgui");
            Directory.CreateDirectory(root);
            try
            {
                if (!pak.UnpackFromStream(pak.Entries[index], pak.ExtEntries[index], path))
                    throw new InvalidOperationException("Target BGUI extraction failed.");
                return File.ReadAllBytes(path);
            }
            finally
            {
                try { if (Directory.Exists(root)) Directory.Delete(root, true); } catch { }
            }
        }

        private static byte[] PatchProfileNameRoute(byte[] source, out string sourceRoute)
        {
            int profileName = FindAscii(source, "ProfileName").SingleOrDefault(-1);
            if (profileName < 0 || FindAscii(source, "ProfileName").Count != 1)
                throw new InvalidOperationException("ProfileName object is missing or duplicated.");

            var routeMatches = new List<(string Route, int Offset)>();
            foreach (string route in new[] { StockRoute, LegacyKoreanRoute, DesiredRoute })
                routeMatches.AddRange(FindAscii(source, route).Select(offset => (route, offset)));
            if (routeMatches.Count != 1)
                throw new InvalidOperationException("ProfileName font route is missing, duplicated, or unsupported.");
            var match = routeMatches[0];
            if (match.Offset <= profileName || match.Offset - profileName > 512)
                throw new InvalidOperationException("Font route is not owned by the ProfileName object.");
            sourceRoute = match.Route;

            byte[] desired = Encoding.ASCII.GetBytes(DesiredRoute);
            byte[] current = Encoding.ASCII.GetBytes(match.Route);
            int lengthOffset = match.Offset - 1;
            if (lengthOffset < 0 || source[lengthOffset] != current.Length || desired.Length > Byte.MaxValue)
                throw new InvalidOperationException("Unsupported BGUI string-length encoding.");
            if (match.Route.Equals(DesiredRoute, StringComparison.OrdinalIgnoreCase))
                return (byte[])source.Clone();

            byte[] result = new byte[source.Length - current.Length + desired.Length];
            Buffer.BlockCopy(source, 0, result, 0, lengthOffset);
            result[lengthOffset] = (byte)desired.Length;
            Buffer.BlockCopy(desired, 0, result, match.Offset, desired.Length);
            int sourceTail = match.Offset + current.Length;
            int resultTail = match.Offset + desired.Length;
            Buffer.BlockCopy(source, sourceTail, result, resultTail, source.Length - sourceTail);

            string finalRoute = DetectRoute(result, out int finalOffset);
            if (!finalRoute.Equals(DesiredRoute, StringComparison.Ordinal) || finalOffset != match.Offset)
                throw new InvalidOperationException("BGUI route replacement validation failed.");
            return result;
        }

        private static string DetectRoute(byte[] bgui, out int offset)
        {
            var matches = new List<(string Route, int Offset)>();
            foreach (string route in new[] { StockRoute, LegacyKoreanRoute, DesiredRoute })
                matches.AddRange(FindAscii(bgui, route).Select(found => (route, found)));
            if (matches.Count != 1) { offset = -1; return "UNKNOWN"; }
            offset = matches[0].Offset;
            return matches[0].Route;
        }

        private static bool IsSupportedRoute(string route)
        {
            return route == StockRoute || route == LegacyKoreanRoute || route == DesiredRoute;
        }

        private static List<int> FindAscii(byte[] source, string value)
        {
            byte[] needle = Encoding.ASCII.GetBytes(value);
            var found = new List<int>();
            for (int i = 0; i <= source.Length - needle.Length; i++)
            {
                bool match = true;
                for (int j = 0; j < needle.Length; j++)
                {
                    byte left = source[i + j], right = needle[j];
                    if (left >= (byte)'A' && left <= (byte)'Z') left = (byte)(left + 32);
                    if (right >= (byte)'A' && right <= (byte)'Z') right = (byte)(right + 32);
                    if (left != right) { match = false; break; }
                }
                if (match) found.Add(i);
            }
            return found;
        }

        private static int ValidateCandidate(string gameDir, string sourcePath, string candidatePath, int targetIndex, string targetPath, byte[] expectedBgui, byte[] sourceBytes, byte[] candidateBytes)
        {
            if (sourceBytes.LongLength != candidateBytes.LongLength)
                throw new InvalidOperationException("Archive length changed.");
            var source = OpenPak(gameDir, sourcePath);
            var candidate = OpenPak(gameDir, candidatePath);
            var candidateTarget = FindTarget(candidate);
            if (candidateTarget.Index != targetIndex || !candidateTarget.Path.Equals(targetPath, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Target entry identity changed.");
            if (source.Entries.Count != candidate.Entries.Count)
                throw new InvalidOperationException("Archive entry count changed.");

            for (int i = 0; i < source.Entries.Count; i++)
            {
                var a = source.Entries[i]; var b = candidate.Entries[i];
                if (i == targetIndex)
                {
                    if (a.mDataPos != b.mDataPos || a.mFileType != b.mFileType)
                        throw new InvalidOperationException("Target entry placement/type changed.");
                    continue;
                }
                if (!Normalize(source.ExtEntries[i].Path).Equals(Normalize(candidate.ExtEntries[i].Path), StringComparison.Ordinal) ||
                    a.mDataPos != b.mDataPos || a.mSizeInPak != b.mSizeInPak || a.mOriginalSize != b.mOriginalSize ||
                    a.mCRC != b.mCRC || a.mFileType != b.mFileType || a.mUid != b.mUid || a.mModifiedTime != b.mModifiedTime)
                    throw new InvalidOperationException("Non-target entry metadata changed at index " + i + ".");
            }

            byte[] extracted = Extract(candidate, targetIndex, Path.GetDirectoryName(Path.GetFullPath(candidatePath)));
            if (!expectedBgui.SequenceEqual(extracted))
                throw new InvalidOperationException("Re-extracted target does not match the patched BGUI.");
            string route = DetectRoute(extracted, out _);
            if (route != DesiredRoute)
                throw new InvalidOperationException("Re-extracted target does not use the dedicated driver-name font.");

            int entryBytes = checked((int)(source.Header.mTocSize / source.Header.mFileCount));
            int entryOffset = targetIndex * entryBytes;
            long payloadStart = (long)source.Entries[targetIndex].mDataPos;
            long payloadEnd = payloadStart + Math.Max(source.Entries[targetIndex].mSizeInPak, candidate.Entries[targetIndex].mSizeInPak);
            int changed = 0;
            for (long i = 0; i < sourceBytes.LongLength; i++)
            {
                if (sourceBytes[i] == candidateBytes[i]) continue;
                changed++;
                bool targetToc = (i >= TocOffset + entryOffset + 16 && i < TocOffset + entryOffset + 24) ||
                                 (i >= TocOffset + entryOffset + 34 && i < TocOffset + entryOffset + 38);
                bool targetPayload = i >= payloadStart && i < payloadEnd;
                if (!targetToc && !targetPayload)
                    throw new InvalidOperationException("Byte changed outside the target TOC/payload contract at 0x" + i.ToString("X") + ".");
            }
            return changed;
        }

        private static void WritePatchReport(string reportPath, string sourcePath, string outputPath, (int Index, string Path) target,
            PakFileTocEntry sourceEntry, string sourceRoute, byte[] patchedBgui, byte[] sourceBytes, byte[] candidateBytes,
            long packedBytes, uint crc, bool noOp, int changedBytes)
        {
            WriteReport(reportPath, new
            {
                schema = "ams2-kr-v0684-dynamic-single-bff-entry-patch-v1",
                status = "PASS",
                source_archive = Path.GetFullPath(sourcePath),
                source_archive_bytes = sourceBytes.LongLength,
                source_archive_sha256 = Sha256(sourceBytes),
                output_archive = Path.GetFullPath(outputPath),
                output_archive_bytes = candidateBytes.LongLength,
                output_archive_sha256 = Sha256(candidateBytes),
                entry_index = target.Index,
                entry_path = target.Path,
                data_position = "0x" + sourceEntry.mDataPos.ToString("X"),
                source_route = sourceRoute,
                target_route = DesiredRoute,
                candidate_original_bytes = patchedBgui.Length,
                candidate_packed_bytes = packedBytes,
                candidate_crc32 = "0x" + crc.ToString("X8"),
                no_op = noOp,
                changed_archive_bytes = changedBytes,
                other_entry_payload_changes = 0,
                other_entry_metadata_changes = 0,
                whole_archive_size_gate = false,
                whole_archive_sha_gate = false
            });
        }

        private static byte[] CompressZlib(byte[] source)
        {
            using var output = new MemoryStream();
            using (var stream = new DeflaterOutputStream(output, new Deflater(9, noZlibHeaderOrFooter: true)))
            {
                stream.IsStreamOwner = false;
                stream.Write(source, 0, source.Length);
                stream.Finish();
            }
            return output.ToArray();
        }

        private static uint Crc32(byte[] data)
        {
            uint crc = 0xFFFFFFFF;
            foreach (byte value in data)
            {
                crc ^= value;
                for (int bit = 0; bit < 8; bit++) crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320 : crc >> 1;
            }
            return crc ^ 0xFFFFFFFF;
        }

        private static string Normalize(string value) { return value.Replace('/', '\\'); }

        private static string Sha256(byte[] bytes)
        {
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", String.Empty);
        }

        private static void WriteExact(string path, byte[] bytes)
        {
            string full = Path.GetFullPath(path);
            Directory.CreateDirectory(Path.GetDirectoryName(full));
            File.WriteAllBytes(full, bytes);
        }

        private static void WriteReport(string path, object value)
        {
            string full = Path.GetFullPath(path);
            Directory.CreateDirectory(Path.GetDirectoryName(full));
            File.WriteAllText(full, JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine, new UTF8Encoding(false));
        }
    }

    internal static class EnumerableCompatibility
    {
        public static T SingleOrDefault<T>(this IEnumerable<T> values, T defaultValue)
        {
            using var iterator = values.GetEnumerator();
            if (!iterator.MoveNext()) return defaultValue;
            T value = iterator.Current;
            if (iterator.MoveNext()) throw new InvalidOperationException("Sequence contains more than one element.");
            return value;
        }
    }
}
