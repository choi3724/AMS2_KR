using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using ICSharpCode.SharpZipLib.Zip.Compression;
using ICSharpCode.SharpZipLib.Zip.Compression.Streams;
using PCarsTools.Config;
using PCarsTools.Encryption;
using PCarsTools.Pak;

namespace BffEntryInspect
{
    internal static class Program
    {
        private static int Main(string[] args)
        {
            if (args.Length == 2 && args[0] == "--crc")
            {
                var crcBytes = File.ReadAllBytes(args[1]);
                Console.WriteLine($"CRC32=0x{Crc32(crcBytes):X8} SHA256={Sha256(crcBytes)} Bytes={crcBytes.Length}");
                return 0;
            }

            if (args.Length == 4 && args[0] == "--entry-crc")
            {
                var crcGame = args[1];
                var crcPakPath = args[2];
                var crcIndex = int.Parse(args[3]);
                if (!BConfig.Instance.LoadConfig(Path.Combine(crcGame, "Languages", "Languages.bml")))
                    throw new InvalidOperationException("Failed to load Languages.bml.");
                BPakFileEncryption.SetKeyset(KeysetType.PC2AndAbove);
                var crcPak = new BPakFile();
                crcPak.FromFile(crcPakPath, withExtraInfo: true);
                var crcEntry = crcPak.Entries[crcIndex];
                var crcFile = File.ReadAllBytes(crcPakPath);
                var raw = new byte[crcEntry.mSizeInPak];
                Buffer.BlockCopy(crcFile, checked((int)crcEntry.mDataPos), raw, 0, raw.Length);
                var decrypted = (byte[])raw.Clone();
                BPakFileEncryption.DecryptData(crcPak.Header.mEncryption, decrypted, decrypted.Length, crcPak.KeyIndex);
                Console.WriteLine($"EntryCRC=0x{crcEntry.mCRC:X8} RawCRC32=0x{Crc32(raw):X8} DecryptedCRC32=0x{Crc32(decrypted):X8} RawSHA={Sha256(raw)} DecryptedSHA={Sha256(decrypted)}");
                return 0;
            }

            if (args.Length == 7 && args[0] == "--pack-entry")
                return PackEntry(args[1], args[2], int.Parse(args[3]), args[4], args[5], args[6]);

            if (args.Length == 4 && args[0] == "--toc-entry")
            {
                var game = args[1];
                var pakPath = args[2];
                var index = int.Parse(args[3]);
                if (!BConfig.Instance.LoadConfig(Path.Combine(game, "Languages", "Languages.bml")))
                    throw new InvalidOperationException("Failed to load Languages.bml.");
                BPakFileEncryption.SetKeyset(KeysetType.PC2AndAbove);
                var tocPak = new BPakFile();
                tocPak.FromFile(pakPath, withExtraInfo: true);
                const int tocOffset = 0x130;
                const int entryBytes = 42;
                var file = File.ReadAllBytes(pakPath);
                var toc = new byte[tocPak.Header.mTocSize];
                Buffer.BlockCopy(file, tocOffset, toc, 0, toc.Length);
                BPakFileEncryption.DecryptData(tocPak.Header.mEncryption, toc, toc.Length, tocPak.KeyIndex);
                var offset = index * entryBytes;
                Console.WriteLine($"Index={index} TocFileOffset=0x{tocOffset + offset:X}");
                Console.WriteLine(BitConverter.ToString(toc, offset, entryBytes));
                Console.WriteLine($"Packed={BitConverter.ToUInt32(toc, offset + 16)} Original={BitConverter.ToUInt32(toc, offset + 20)} CRC=0x{BitConverter.ToUInt32(toc, offset + 34):X8}");
                return 0;
            }

            if (args.Length == 1 && args[0] == "--api")
            {
                foreach (var type in typeof(BPakFile).Assembly.GetTypes()
                    .Where(type => type.FullName.IndexOf("Pak", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                   type.FullName.IndexOf("Compress", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                   type.FullName.IndexOf("Encrypt", StringComparison.OrdinalIgnoreCase) >= 0)
                    .OrderBy(type => type.FullName))
                {
                    Console.WriteLine($"TYPE {type.FullName}");
                    foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                        .OrderBy(method => method.Name))
                    {
                        Console.WriteLine($"  {method.Name}({string.Join(", ", method.GetParameters().Select(parameter => $"{parameter.ParameterType.Name} {parameter.Name}"))}) -> {method.ReturnType.Name}");
                    }
                }
                return 0;
            }

            if (args.Length < 3 || args.Length > 4)
            {
                Console.Error.WriteLine("Usage: BffEntryInspect <game-directory> <pak-file> <path-substring> [output-directory]");
                return 2;
            }

            var configPath = Path.Combine(args[0], "Languages", "Languages.bml");
            if (!BConfig.Instance.LoadConfig(configPath))
                throw new InvalidOperationException("Failed to load Languages.bml.");

            BPakFileEncryption.SetKeyset(KeysetType.PC2AndAbove);
            var pak = new BPakFile();
            pak.FromFile(args[1], withExtraInfo: true);
            Console.WriteLine($"Header Encryption={pak.Header.mEncryption} KeyIndex={pak.KeyIndex} SectorSize=0x{pak.Header.mSectorSize:X} DataOffset=0x{pak.Header.mDataOffset:X} TocSize={pak.Header.mTocSize} CRCSize={pak.Header.mCRCSize} ExtInfoSize={pak.Header.mExtInfoSize} FileCount={pak.Header.mFileCount}");

            var matches = pak.ExtEntries
                .Select((extra, index) => new { extra, entry = pak.Entries[index], index })
                .Where(item => item.extra.Path.IndexOf(args[2], StringComparison.OrdinalIgnoreCase) >= 0)
                .ToArray();

            foreach (var item in matches)
            {
                Console.WriteLine(
                    $"[{item.index}] Path={item.extra.Path} DataPos=0x{item.entry.mDataPos:X} " +
                    $"Packed={item.entry.mSizeInPak} Original={item.entry.mOriginalSize} " +
                    $"Compression={item.entry.mFileType} CRC=0x{item.entry.mCRC:X8}");
                if (args.Length == 4)
                {
                    var output = Path.Combine(args[3], item.extra.Path.Replace('/', Path.DirectorySeparatorChar));
                    Directory.CreateDirectory(Path.GetDirectoryName(output));
                    if (!pak.UnpackFromStream(item.entry, item.extra, output))
                        throw new InvalidOperationException($"Failed to extract {item.extra.Path}.");
                    Console.WriteLine($"  Extracted={output}");
                }
            }

            Console.WriteLine($"Matches={matches.Length}");
            return matches.Length == 0 ? 1 : 0;
        }

        private static int PackEntry(string game, string sourcePakPath, int entryIndex, string replacementPath, string outputPakPath, string reportPath)
        {
            if (!BConfig.Instance.LoadConfig(Path.Combine(game, "Languages", "Languages.bml")))
                throw new InvalidOperationException("Failed to load Languages.bml.");
            BPakFileEncryption.SetKeyset(KeysetType.PC2AndAbove);

            var sourcePak = new BPakFile();
            sourcePak.FromFile(sourcePakPath, withExtraInfo: true);
            if (sourcePak.Header.mEncryption != eEncryptionType.RC4)
                throw new InvalidOperationException($"Expected RC4 archive, got {sourcePak.Header.mEncryption}.");
            if (entryIndex < 0 || entryIndex >= sourcePak.Entries.Count)
                throw new ArgumentOutOfRangeException(nameof(entryIndex));

            var sourceEntry = sourcePak.Entries[entryIndex];
            var sourceExtra = sourcePak.ExtEntries[entryIndex];
            if (sourceEntry.mFileType != PakFileCompressionType.ZLib)
                throw new InvalidOperationException($"Expected ZLib entry, got {sourceEntry.mFileType}.");

            var sourceBytes = File.ReadAllBytes(sourcePakPath);
            var replacement = File.ReadAllBytes(replacementPath);
            var compressed = CompressZlib(replacement);
            var sectorSize = checked((int)sourcePak.Header.mSectorSize);
            var allocation = entryIndex + 1 < sourcePak.Entries.Count
                ? checked((int)(sourcePak.Entries[entryIndex + 1].mDataPos - sourceEntry.mDataPos))
                : checked(sourceBytes.Length - (int)sourceEntry.mDataPos);
            if (compressed.Length > allocation)
                throw new InvalidOperationException($"Compressed replacement is {compressed.Length} bytes; allocation is {allocation} bytes.");

            var encryptedPayload = (byte[])compressed.Clone();
            BPakFileEncryption.DecryptData(sourcePak.Header.mEncryption, encryptedPayload, encryptedPayload.Length, sourcePak.KeyIndex);

            const int tocOffset = 0x130;
            const int entryBytes = 42;
            var decryptedToc = new byte[sourcePak.Header.mTocSize];
            Buffer.BlockCopy(sourceBytes, tocOffset, decryptedToc, 0, decryptedToc.Length);
            BPakFileEncryption.DecryptData(sourcePak.Header.mEncryption, decryptedToc, decryptedToc.Length, sourcePak.KeyIndex);
            var entryOffset = checked(entryIndex * entryBytes);
            Buffer.BlockCopy(BitConverter.GetBytes((uint)compressed.Length), 0, decryptedToc, entryOffset + 16, 4);
            Buffer.BlockCopy(BitConverter.GetBytes((uint)replacement.Length), 0, decryptedToc, entryOffset + 20, 4);
            var crc = ~Crc32(encryptedPayload);
            Buffer.BlockCopy(BitConverter.GetBytes(crc), 0, decryptedToc, entryOffset + 34, 4);
            var encryptedToc = (byte[])decryptedToc.Clone();
            BPakFileEncryption.DecryptData(sourcePak.Header.mEncryption, encryptedToc, encryptedToc.Length, sourcePak.KeyIndex);

            var candidate = (byte[])sourceBytes.Clone();
            Buffer.BlockCopy(encryptedToc, 0, candidate, tocOffset, encryptedToc.Length);
            Buffer.BlockCopy(encryptedPayload, 0, candidate, checked((int)sourceEntry.mDataPos), encryptedPayload.Length);

            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outputPakPath)));
            File.WriteAllBytes(outputPakPath, candidate);

            var validationDir = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(outputPakPath)), "validation-extract");
            Directory.CreateDirectory(validationDir);
            var validationPak = new BPakFile();
            validationPak.FromFile(outputPakPath, withExtraInfo: true);
            var validationOutput = Path.Combine(validationDir, sourceExtra.Path.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(validationOutput));
            if (!validationPak.UnpackFromStream(validationPak.Entries[entryIndex], validationPak.ExtEntries[entryIndex], validationOutput))
                throw new InvalidOperationException("Validation extraction failed.");
            var validationBytes = File.ReadAllBytes(validationOutput);
            if (!replacement.SequenceEqual(validationBytes))
                throw new InvalidOperationException("Validation extraction does not match the replacement bytes.");

            var report = new
            {
                schema = "ams2-kr-068.1-single-bff-entry-pack-v1",
                status = "PASS",
                source_archive = sourcePakPath,
                source_archive_sha256 = Sha256(sourceBytes),
                output_archive = outputPakPath,
                output_archive_sha256 = Sha256(candidate),
                entry_index = entryIndex,
                entry_path = sourceExtra.Path,
                data_position = $"0x{sourceEntry.mDataPos:X}",
                allocation_bytes = allocation,
                source_packed_bytes = sourceEntry.mSizeInPak,
                candidate_packed_bytes = compressed.Length,
                source_original_bytes = sourceEntry.mOriginalSize,
                candidate_original_bytes = replacement.Length,
                source_crc32 = $"0x{sourceEntry.mCRC:X8}",
                candidate_crc32 = $"0x{crc:X8}",
                replacement_sha256 = Sha256(replacement),
                validation_extract_sha256 = Sha256(validationBytes),
                other_entry_payload_changes = 0,
                other_entry_metadata_changes = 0,
                font_asset_changes = 0,
            };
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(reportPath)));
            File.WriteAllText(reportPath, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine);
            Console.WriteLine(JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
            return 0;
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
            foreach (var value in data)
            {
                crc ^= value;
                for (var bit = 0; bit < 8; bit++)
                    crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320 : crc >> 1;
            }
            return crc ^ 0xFFFFFFFF;
        }

        private static string Sha256(byte[] data)
        {
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(data)).Replace("-", string.Empty);
        }
    }
}
