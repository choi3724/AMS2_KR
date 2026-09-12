using System;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace Ams2KoreanBeta
{
    // Only the reviewed HUDDISPLAY pair is supported. Rebuild the delta after a game archive update.
    internal static class ErsArchivePatch
    {
        internal const string RelativePath = "Pakfiles\\HUDDISPLAY.bff";
        internal const string DeltaRelativePath = "payload\\HUDDISPLAY.xor.gz";
        internal const int ArchiveBytes = 24235863;
        internal const string StockSha = "401A819D78DC45E9555888AB96F7885B0737F2831C9B02EF0654746AB9F93E97";
        internal const string PatchedSha = "AE07B378819414314952BE993C146C83AF85F327BCCC5F7C55323941B2A2FDBC";

        internal static void ValidatePackage(string releaseRoot)
        {
            FileInfo delta = new FileInfo(Path.Combine(releaseRoot, DeltaRelativePath));
            if (!delta.Exists || delta.Length == 0 || delta.Length > 2 * 1024 * 1024)
                throw new InvalidDataException("ERS 계기판 패치 데이터가 없거나 손상되었습니다.");
        }

        internal static bool IsNewLooseLayout(string relative)
        {
            return relative.Equals("gui\\display_formula_hybrid_gen1.bgui", StringComparison.OrdinalIgnoreCase) ||
                relative.Equals("gui\\display_formula_ultimate_2019.bgui", StringComparison.OrdinalIgnoreCase) ||
                relative.Equals("gui\\display_formula_ultimate_2022.bgui", StringComparison.OrdinalIgnoreCase) ||
                relative.Equals("gui\\display_formula_ultimate_2024.bgui", StringComparison.OrdinalIgnoreCase);
        }

        internal static void RestoreLooseOriginal(string live, string output, string expectedSha)
        {
            // The exact tested file hash is checked by the caller; Latin-1 preserves every binary byte.
            Encoding binary = Encoding.GetEncoding(28591);
            byte[] source = File.ReadAllBytes(live);
            string value = binary.GetString(source);
            foreach (int size in new[] { 40, 52, 60 })
                value = value.Replace("GUI\\kr081_ers_value_" + size + ".bfont", "GUI\\font_arial_bold_" + size + ".bfont");
            File.WriteAllBytes(output, binary.GetBytes(value));
            PackageManifest.RequireFile(output, source.Length, expectedSha, "ERS 테스트 원본 복구 검증");
        }

        internal static void Prepare(string releaseRoot, string live, string candidate, string original)
        {
            ValidatePackage(releaseRoot);
            FileInfo info = new FileInfo(live);
            if (!info.Exists || info.Length != ArchiveBytes)
                throw new InvalidDataException("현재 게임의 계기판 파일은 이 패치의 지원 버전과 다릅니다. 최신 패치를 확인해주세요.");
            string sourceSha = FileOps.Sha256(live);
            if (sourceSha != StockSha && sourceSha != PatchedSha)
                throw new InvalidDataException("현재 게임의 계기판 파일은 이 패치의 지원 버전과 다릅니다. 최신 패치를 확인해주세요.");
            byte[] transformed = File.ReadAllBytes(live);
            using (FileStream file = File.OpenRead(Path.Combine(releaseRoot, DeltaRelativePath)))
            using (GZipStream delta = new GZipStream(file, CompressionMode.Decompress))
            {
                byte[] buffer = new byte[65536];
                int offset = 0;
                while (offset < transformed.Length)
                {
                    int count = delta.Read(buffer, 0, Math.Min(buffer.Length, transformed.Length - offset));
                    if (count == 0) throw new InvalidDataException("ERS 패치 데이터가 잘렸습니다.");
                    for (int i = 0; i < count; i++) transformed[offset + i] ^= buffer[i];
                    offset += count;
                }
                if (delta.ReadByte() != -1) throw new InvalidDataException("ERS 패치 데이터의 길이가 다릅니다.");
            }
            File.WriteAllBytes(sourceSha == StockSha ? candidate : original, transformed);
            File.Copy(live, sourceSha == StockSha ? original : candidate, false);
            // Both directions must be exact before the installer creates any transaction or writes game assets.
            PackageManifest.RequireFile(original, ArchiveBytes, StockSha, "ERS 원본 검증");
            PackageManifest.RequireFile(candidate, ArchiveBytes, PatchedSha, "ERS 수정본 검증");
        }
    }
}
