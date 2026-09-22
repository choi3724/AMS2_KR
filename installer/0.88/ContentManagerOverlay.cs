using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Web.Script.Serialization;

namespace Ams2KoreanBeta
{
    // Only reviewed native CM bootfiles are eligible. Unknown mod edits are never replaced.
    internal static class ContentManagerOverlay
    {
        public sealed class Edit { public string before, after, remove, insert; public int offset; }
        public sealed class Profile { public string build; public Dictionary<string, Edit> files; }
        public sealed class Saved
        {
            public string path, before, after, backup;
            public int attributes;
            public long creation, modified;
        }
        private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 32 * 1024 * 1024 };
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        private static Profile Load()
        {
            using (var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Ams2KoreanBeta.Compatibility.cm-overlays.json.gz"))
            {
                if (resource == null) throw new InvalidDataException("CM 호환성 데이터가 없습니다.");
                using (var unzip = new GZipStream(resource, CompressionMode.Decompress))
                using (var reader = new StreamReader(unzip, Utf8)) return Json.Deserialize<Profile>(reader.ReadToEnd());
            }
        }
        internal static bool TryPatchCurrent(string relative, byte[] source, out byte[] candidate)
        {
            Profile profile = Load(); Edit edit;
            string key = relative.Replace('\\', '/').ToLowerInvariant();
            if (!profile.files.TryGetValue(key, out edit)) { candidate = null; return false; }
            candidate = Patch(source, edit, false); return true;
        }
        private static string PathIn(string root, string relative) { return GameUpdateCompatibility.SafePath(root, relative); }
        internal static HashSet<string> Owned(string game)
        {
            string state = PathIn(game, "Mods/state.json");
            var result = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (!File.Exists(state)) return result;
            var document = (Dictionary<string, object>)Json.DeserializeObject(File.ReadAllText(state, Utf8));
            var install = (Dictionary<string, object>)document["Install"];
            var mods = (Dictionary<string, object>)install["Mods"];
            var other = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var mod in mods)
            {
                var value = (Dictionary<string, object>)mod.Value;
                foreach (string name in (IEnumerable)value["Files"])
                {
                    string relative = name.Replace('\\', '/').ToLowerInvariant();
                    PathIn(game, relative);
                    (mod.Key == "__bootfiles_generated" ? result : other).Add(relative);
                }
            }
            result.ExceptWith(other);
            return result;
        }
        private static bool MatchesAt(byte[] source, byte[] pattern, int offset)
        {
            if (offset < 0 || offset > source.Length - pattern.Length) return false;
            for (int i = 0; i < pattern.Length; i++) if (source[offset + i] != pattern[i]) return false;
            return true;
        }

        // KMP bounds the scan to O(source + pattern), including repeated prefixes.
        // -1: absent; -2: ambiguous. Count overlapping matches as before.
        private static int UniqueOffset(byte[] source, byte[] pattern)
        {
            if (pattern.Length == 0) throw new InvalidDataException("CM 변경 영역 데이터가 비어 있습니다.");
            int[] prefix = new int[pattern.Length];
            for (int i = 1, j = 0; i < pattern.Length; i++)
            {
                while (j > 0 && pattern[i] != pattern[j]) j = prefix[j - 1];
                if (pattern[i] == pattern[j]) j++;
                prefix[i] = j;
            }
            int found = -1;
            for (int i = 0, j = 0; i < source.Length; i++)
            {
                while (j > 0 && source[i] != pattern[j]) j = prefix[j - 1];
                if (source[i] == pattern[j]) j++;
                if (j != pattern.Length) continue;
                if (found >= 0) return -2;
                found = i - pattern.Length + 1;
                j = prefix[j - 1];
            }
            return found;
        }

        internal static byte[] Patch(byte[] source, Edit edit, bool reverse)
        {
            byte[] from = Convert.FromBase64String(reverse ? edit.insert : edit.remove);
            byte[] to = Convert.FromBase64String(reverse ? edit.remove : edit.insert);
            if (from.Length == 0 || to.Length == 0) throw new InvalidDataException("CM 변경 영역 데이터가 비어 있습니다.");
            // Other TDB languages can still contain the original block. Recognize
            // the applied block at its reviewed location before searching them.
            if (MatchesAt(source, to, edit.offset)) return (byte[])source.Clone();
            int offset = MatchesAt(source, from, edit.offset) ? edit.offset : UniqueOffset(source, from);
            if (offset == -2) throw new InvalidDataException("CM 한글 변경 영역이 여러 곳이라 안전하게 적용할 수 없습니다.");
            if (offset < 0)
            {
                if (UniqueOffset(source, to) >= 0) return (byte[])source.Clone();
                throw new InvalidDataException("CM 한글 변경 영역을 찾지 못했습니다.");
            }
            using (var output = new MemoryStream())
            {
                output.Write(source, 0, offset); output.Write(to, 0, to.Length);
                output.Write(source, offset + from.Length, source.Length - offset - from.Length);
                byte[] candidate = output.ToArray();
                using (var restore = new MemoryStream())
                {
                    restore.Write(candidate, 0, offset); restore.Write(from, 0, from.Length);
                    restore.Write(candidate, offset + to.Length, candidate.Length - offset - to.Length);
                    if (!restore.ToArray().SequenceEqual(source)) throw new InvalidDataException("CM 한글 변경 외의 내용이 달라졌습니다.");
                }
                return candidate;
            }
        }
        private static string Hash(byte[] bytes)
        {
            using (var sha = System.Security.Cryptography.SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "");
        }
        private static string StateHash(string game)
        {
            string path = PathIn(game, "Mods/state.json");
            return File.Exists(path) ? FileOps.Sha256(path) : "ABSENT";
        }
        internal static string StateToken(string game) { return StateHash(game); }
        internal static void RecoverPendingOnly(string game, string root, Action<string> log)
        {
            Profile profile = Load();
            string folder = Path.Combine(root, "cm-overlay");
            if (!File.Exists(Path.Combine(folder, "pending.json"))) return;
            GuardGame();
            Restore(game, folder, profile);
            if (log != null) log("중단된 CM 한글 재적용을 작업 전 상태로 복구했습니다.");
        }
        private static void Restore(string game, string folder, Profile profile)
        {
            string pending = Path.Combine(folder, "pending.json");
            if (!File.Exists(pending)) return;
            var rows = Json.Deserialize<List<Saved>>(File.ReadAllText(pending, Utf8));
            foreach (Saved row in rows)
            {
                if (!profile.files.ContainsKey(row.path)) throw new InvalidDataException("CM 복구 경로가 잘못되었습니다.");
                string live = PathIn(game, row.path), backup = PathIn(folder, row.backup);
                if (!File.Exists(live) || (FileOps.Sha256(live) != row.before && FileOps.Sha256(live) != row.after) || FileOps.Sha256(backup) != row.before)
                    throw new IOException("CM 작업 후 파일이 다시 변경되어 자동 복구를 중단했습니다: " + row.path);
            }
            foreach (Saved row in rows.AsEnumerable().Reverse())
            {
                string live = PathIn(game, row.path);
                if (FileOps.Sha256(live) != row.before)
                {
                    File.SetAttributes(live, FileAttributes.Normal);
                    FileOps.ReplaceExact(PathIn(folder, row.backup), live, row.before);
                }
                File.SetCreationTimeUtc(live, new DateTime(row.creation, DateTimeKind.Utc));
                File.SetLastWriteTimeUtc(live, new DateTime(row.modified, DateTimeKind.Utc));
                File.SetAttributes(live, (FileAttributes)row.attributes);
            }
            File.Delete(pending);
        }
        internal static void Ensure(string game, string root, Action<string> log)
        {
            Profile profile = Load();
            string build = SteamLocator.FromGameDirectory(game).BuildId;
            if (build != profile.build && log != null) log("참고: CM 프로필 빌드 " + profile.build + "와 현재 빌드 " + build + "가 다릅니다. 빌드 차단 대신 실제 변경 영역을 검사합니다.");
            string folder = Path.Combine(root, "cm-overlay");
            if (File.Exists(Path.Combine(folder, "pending.json")))
            {
                GuardGame(); Restore(game, folder, profile);
            }
            string cmState = StateHash(game);
            HashSet<string> owned = Owned(game);
            if (owned.Count == 0) return;
            var rows = File.ReadAllLines(Path.Combine(root, "files.tsv"), Utf8).Skip(1).Where(x => x.Length > 0).Select(x => x.Split('\t'))
                .ToDictionary(x => x[0].Replace('\\', '/').ToLowerInvariant());
            var candidates = new Dictionary<string, byte[]>();
            foreach (var pair in profile.files)
            {
                if (!owned.Contains(pair.Key)) continue;
                string[] record;
                if (!rows.TryGetValue(pair.Key, out record) || record.Length != 9)
                    throw new InvalidDataException("CM 재적용 전에 한글패치 버전을 확인해주세요: " + pair.Key);
                string path = PathIn(game, pair.Key);
                if (!File.Exists(path)) throw new FileNotFoundException("CM 공유 파일이 없습니다.", path);
                string hash = FileOps.Sha256(path);
                // An intact older installation needs no CM repair before upgrading.
                if (hash == record[5]) continue;
                if (hash == pair.Value.after) continue;
                candidates.Add(pair.Key, Patch(File.ReadAllBytes(path), pair.Value, false));
            }
            if (candidates.Count == 0) return;
            GuardGame(); Directory.CreateDirectory(folder);
            var saved = new List<Saved>();
            string id = Guid.NewGuid().ToString("N");
            foreach (var pair in candidates)
            {
                string live = PathIn(game, pair.Key);
                using (var locked = new FileStream(live, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
                string backup = id + "-" + saved.Count.ToString(CultureInfo.InvariantCulture);
                string before = FileOps.Sha256(live), after = Hash(candidates[pair.Key]);
                FileOps.CopyNewExact(live, PathIn(folder, backup), before);
                saved.Add(new Saved { path = pair.Key, before = before, after = after,
                    backup = backup, attributes = (int)File.GetAttributes(live), creation = File.GetCreationTimeUtc(live).Ticks, modified = File.GetLastWriteTimeUtc(live).Ticks });
            }
            FileOps.WriteTextAtomic(Path.Combine(folder, "pending.json"), Json.Serialize(saved));
            try
            {
                foreach (Saved row in saved)
                {
                    string live = PathIn(game, row.path);
                    if (StateHash(game) != cmState || FileOps.Sha256(live) != row.before) throw new IOException("CM 작업이 진행 중입니다. 완료 후 다시 실행해주세요.");
                    string candidate = Path.Combine(folder, "candidate"); File.WriteAllBytes(candidate, candidates[row.path]);
                    File.SetAttributes(live, FileAttributes.Normal);
                    FileOps.ReplaceExact(candidate, live, row.after);
                    // CM uses creation time to decide whether its own backup is still restorable.
                    File.SetCreationTimeUtc(live, new DateTime(row.creation, DateTimeKind.Utc));
                    File.SetLastWriteTimeUtc(live, new DateTime(row.modified, DateTimeKind.Utc));
                    File.SetAttributes(live, (FileAttributes)row.attributes);
#if COMPATIBILITY_TEST
                    if (File.Exists(Path.Combine(game, ".cm_fail_after_write"))) throw new IOException("Injected CM failure");
                    if (File.Exists(Path.Combine(game, ".cm_interrupt_after_write"))) Environment.Exit(74);
#endif
                }
                if (StateHash(game) != cmState || saved.Any(r => FileOps.Sha256(PathIn(game, r.path)) != r.after)) throw new IOException("CM 한글 재적용 중 파일이 변경되었습니다.");
                File.Delete(Path.Combine(folder, "pending.json"));
                if (log != null) log("CM 파일의 한글 번역·글꼴 연결 " + saved.Count + "개를 재적용했습니다.");
            }
            catch { Restore(game, folder, profile); throw; }
        }
        private static void GuardGame()
        {
            foreach (string name in new[] { "AMS2", "AMS2AVX" })
                foreach (Process process in Process.GetProcessesByName(name))
                    using (process) throw new InvalidOperationException("게임 종료 후 한글을 재적용해주세요.");
        }
    }
}
