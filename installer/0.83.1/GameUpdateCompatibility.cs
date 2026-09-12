using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace Ams2KoreanBeta
{
    // Shared by both launchers and the installer. Unknown updates stop before any asset write.
    internal static class GameUpdateCompatibility
    {
        public sealed class MenuRule
        {
            public string stock, patched, resource;
            public int count, texts;
            public Dictionary<string, string> map;
            public Dictionary<string, string[]> overrides;
        }
        public sealed class ArchiveRule { public string stock, patched, resource; public int bytes; }
        public sealed class FileRule { public string sha256, role; }
        public sealed class Rules
        {
            public string build, textIndex, textIndexSha1;
            public long textIndexBytes;
            public Rules legacy;
            public Dictionary<string, MenuRule> menus;
            public Dictionary<string, ArchiveRule> archives;
            public Dictionary<string, FileRule> files;
        }
        private sealed class Change { public string Relative, Target, Before, After; public byte[] Content; }
        private sealed class Snapshot { public string Target, Copy, Hash; public FileAttributes Attributes; }
        private sealed class TextField { public int Start, End, Record; public uint Id; public string Font; }
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);

        internal static bool SupportedBuild(string build) { return build == "24132163" || build == PackageManifest.BuildId; }

        internal static Rules ForBuild(string build)
        {
            var rules = new JavaScriptSerializer { MaxJsonLength = 4 * 1024 * 1024 }.Deserialize<Rules>(Utf8.GetString(Resource("rules.json")));
            if (build != "24132163") return rules;
            if (rules.legacy == null || rules.legacy.build != build)
                throw new InvalidDataException("이전 게임 빌드용 패치 데이터가 없습니다. 설치 패키지를 새 폴더에 다시 풀어주세요.");
            return rules.legacy;
        }

        private static bool TextIndexMatches(string path, Rules rules)
        {
            if (!File.Exists(path)) return false;
            if (String.IsNullOrEmpty(rules.textIndexSha1)) return FileOps.Sha256(path) == rules.textIndex;
            // The old original is identified by the pinned official Steam depot file record.
            if (new FileInfo(path).Length != rules.textIndexBytes) return false;
            using (var algorithm = SHA1.Create())
            using (var stream = File.OpenRead(path))
                return BitConverter.ToString(algorithm.ComputeHash(stream)).Replace("-", "") == rules.textIndexSha1;
        }

        private static byte[] Resource(string name)
        {
            using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Ams2KoreanBeta.Compatibility." + name))
            {
                if (stream == null) throw new InvalidDataException("게임 업데이트 대응 데이터가 없습니다. 최신 설치 프로그램으로 다시 설치해주세요.");
                using (var output = new MemoryStream()) { stream.CopyTo(output); return output.ToArray(); }
            }
        }

        private static string Hash(byte[] bytes)
        {
            using (var algorithm = SHA256.Create()) return BitConverter.ToString(algorithm.ComputeHash(bytes)).Replace("-", "");
        }

        internal static string SafePath(string root, string relative)
        {
            string[] parts = relative.Replace('/', '\\').Split('\\');
            if (parts.Any(p => p.Length == 0 || p == "." || p == ".." || p.EndsWith(".") || p.EndsWith(" ") || p.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0))
                throw new InvalidDataException("잘못된 패치 경로입니다.");
            string full = Path.GetFullPath(Path.Combine(root, String.Join("\\", parts)));
            string boundary = Path.GetFullPath(root).TrimEnd('\\') + "\\";
            if (!full.StartsWith(boundary, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("패치 경로 범위를 벗어났습니다.");
            for (string path = full; path != null; path = Path.GetDirectoryName(path))
                if ((File.Exists(path) || Directory.Exists(path)) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("연결된 폴더/파일에는 자동 재적용하지 않습니다: " + path);
            return full;
        }

        private static Dictionary<string, string> ReadHead(string path)
        {
            return File.ReadAllLines(path, Utf8).Where(x => x.Length > 0).Select(x => x.Split('\t')).ToDictionary(x => x[0], x => x[1]);
        }

        internal static string ActiveState(string game)
        {
            string root = SafePath(game, "Backup/AMS2-Korean");
            if (!Directory.Exists(root)) return null;
            var active = new List<string>();
            foreach (string folder in Directory.GetDirectories(root, "AMS2-KR-BETA-*"))
            {
                string file = SafePath(game, "Backup/AMS2-Korean/" + Path.GetFileName(folder) + "/install-state.tsv");
                if (!File.Exists(file)) continue;
                string status = ReadHead(file)["status"];
                if (status == "INSTALLED" || status == "GAME_UPDATE_PENDING") active.Add(folder);
            }
            if (active.Count > 1) throw new InvalidDataException("활성 설치 기록이 여러 개입니다. 최신 설치 프로그램에서 상태를 확인해주세요.");
            return active.SingleOrDefault();
        }

        internal static bool NeedsRepair(string game)
        {
            string root = ActiveState(game);
            if (root == null) return false;
            if (ReadHead(Path.Combine(root, "install-state.tsv"))["status"] == "GAME_UPDATE_PENDING") return true;
            foreach (string line in File.ReadLines(Path.Combine(root, "files.tsv")).Skip(1))
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                string[] row = line.Split('\t');
                if (row.Length != 9) throw new InvalidDataException("설치 기록 형식이 잘못되었습니다.");
                string file = SafePath(game, row[0]);
                if (!File.Exists(file) || FileOps.Sha256(file) != row[5]) return true;
            }
            return ReadHead(Path.Combine(root, "install-state.tsv"))["buildid"] != SteamLocator.FromGameDirectory(game).BuildId;
        }

        internal static void Ensure(string game, bool requireInstalled, Action<string> log = null)
        {
            bool owner;
            using (var mutex = new Mutex(true, @"Local\AMS2-Korean-GameUpdate-" + FileOps.Sha256Text(Path.GetFullPath(game).ToUpperInvariant()).Substring(0, 24), out owner))
            {
                if (!owner) throw new InvalidOperationException("다른 창에서 한글패치 파일을 확인하고 있습니다. 완료 후 다시 실행해주세요.");
                GameInfo info = SteamLocator.FromGameDirectory(game);
                Rules rules = ForBuild(info.BuildId);
                if (!TextIndexMatches(SafePath(game, "Pakfiles/Dir/TEXT.bff"), rules))
                    throw Unsupported(info, "번역 데이터 구조");
                string root = ActiveState(game);
                if (root == null)
                {
                    if (requireInstalled) throw new InvalidOperationException("한글패치 설치 기록이 없습니다. 최신 설치 프로그램으로 설치해주세요.");
                    return;
                }
                string headPath = SafePath(root, "install-state.tsv"), filesPath = SafePath(root, "files.tsv");
                var head = ReadHead(headPath);
                if (!Path.GetFullPath(head["game_dir"]).TrimEnd('\\').Equals(Path.GetFullPath(game).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("설치 기록의 게임 경로가 다릅니다.");
                if (head["status"] == "GAME_UPDATE_PENDING")
                {
                    GuardGame();
                    RecoverPending(game, root, head, rules);
                    head = ReadHead(headPath);
                }
                string[] lines = File.ReadAllLines(filesPath, Utf8);
                var rows = lines.Skip(1).Where(x => !String.IsNullOrWhiteSpace(x)).Select(x => x.Split('\t')).ToList();
                if ((rows.Count != rules.files.Count && (requireInstalled || rows.Count != 450)) || rows.Any(x => x.Length != 9) || rows.Select(x => x[0].Replace('\\', '/').ToLowerInvariant()).Distinct().Count() != rows.Count)
                    throw new InvalidDataException("설치 파일 목록이 불완전합니다. 최신 설치 프로그램에서 복구해주세요.");
                var changes = new List<Change>();
                foreach (string[] row in rows)
                {
                    string relative = row[0].Replace('\\', '/').ToLowerInvariant();
                    if (!rules.files.ContainsKey(relative)) throw new InvalidDataException("관리 범위 밖 설치 기록입니다.");
                    string live = SafePath(game, relative);
                    if (!File.Exists(live)) throw new FileNotFoundException("한글패치 파일이 없습니다. 최신 설치 프로그램으로 다시 설치해주세요: " + relative);
                    string current = FileOps.Sha256(live);
                    if (current == row[5]) continue;
                    byte[] source = File.ReadAllBytes(live), candidate;
                    if (Hash(source) != current) throw new IOException("확인 중 게임 파일이 바뀌었습니다. Steam 업데이트 완료 후 다시 실행해주세요.");
                    if (rules.menus.ContainsKey(relative))
                    {
                        MenuRule rule = rules.menus[relative];
                        if (current != rule.stock && !SteamOriginal(info, relative, source)) throw Unsupported(info, relative);
                        candidate = PatchMenu(source, rule);
                    }
                    else if (rules.archives.ContainsKey(relative))
                    {
                        ArchiveRule rule = rules.archives[relative];
                        // Unreviewed archive layouts require a new compatibility release.
                        if (current != rule.stock || source.Length != rule.bytes) throw Unsupported(info, relative);
                        candidate = (byte[])source.Clone();
                        using (var compressed = new MemoryStream(Resource(rule.resource + ".xor.gz")))
                        using (var delta = new GZipStream(compressed, CompressionMode.Decompress))
                        {
                            byte[] buffer = new byte[65536];
                            int position = 0, count;
                            while (position < candidate.Length && (count = delta.Read(buffer, 0, Math.Min(buffer.Length, candidate.Length - position))) > 0)
                            { for (int i = 0; i < count; i++) candidate[position + i] ^= buffer[i]; position += count; }
                            if (position != candidate.Length || delta.ReadByte() != -1 || Hash(candidate) != rule.patched) throw new InvalidDataException("계기판 대응 데이터 검증에 실패했습니다.");
                        }
                    }
                    else throw Unsupported(info, relative);
                    changes.Add(new Change { Relative = relative, Target = live, Before = current, After = Hash(candidate), Content = candidate });
                }
                if (changes.Count == 0 && head["buildid"] == info.BuildId) return;
                GuardGame();
                if (log != null) log("게임 업데이트 감지: 원본을 백업하고 한글 폰트 연결을 다시 적용합니다.");
                Apply(game, root, headPath, filesPath, head, lines[0], rows, info, changes);
                if (log != null) log("게임 업데이트 대응 및 파일 검증 완료");
            }
        }

        internal static Exception Unsupported(GameInfo info, string file)
        {
            string reason = SupportedBuild(info.BuildId)
                ? "지원되는 게임 빌드이지만 일부 파일이 검증된 원본 또는 설치 기록과 다릅니다.\r\nSteam 게임 업데이트가 완료되었는지 확인해주세요. 계속 발생하면 진단 ZIP을 전달해주세요."
                : "아직 지원 여부가 확인되지 않은 게임 빌드입니다.\r\n지원 빌드: 24132163 / 25271800. Steam 게임 버전과 패치의 지원 버전을 확인해주세요.";
            return new InvalidDataException("현재 게임 빌드: " + info.BuildId + "\r\n확인할 항목: " + file + "\r\n" + reason + "\r\n검증되지 않은 파일을 강제로 덮어쓰거나 게임을 실행하지 않았습니다.");
        }

        private static void GuardGame()
        {
            foreach (string name in new[] { "AMS2", "AMS2AVX" })
                foreach (Process process in Process.GetProcessesByName(name))
                    using (process) throw new InvalidOperationException("게임을 완전히 종료한 뒤 다시 실행해주세요.");
        }

        private static void Apply(string game, string root, string headPath, string filesPath, Dictionary<string, string> head, string header, List<string[]> rows, GameInfo info, List<Change> changes)
        {
            string transaction = SafePath(root, "game-updates/" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(transaction);
            var snapshots = new List<Snapshot>();
            var writes = new List<Change>();
            foreach (Change change in changes)
            {
                string[] row = rows.Single(r => r[0].Replace('\\', '/').Equals(change.Relative, StringComparison.OrdinalIgnoreCase));
                if (row[1] != "modified") throw new InvalidDataException("게임 원본이 아닌 파일에는 자동 재적용하지 않습니다.");
                string original = SafePath(root, "original/" + head["backup_id"] + "/" + row[0]);
                PackageManifest.RequireFile(original, Int64.Parse(row[2]), row[3], "업데이트 이전 원본 백업");
                writes.Add(new Change { Target = original, Before = row[3], After = change.Before, Content = File.ReadAllBytes(change.Target) });
                writes.Add(change);
                row[2] = new FileInfo(change.Target).Length.ToString(CultureInfo.InvariantCulture); row[3] = change.Before;
                row[4] = change.Content.Length.ToString(CultureInfo.InvariantCulture); row[5] = change.After;
            }
            head["buildid"] = info.BuildId;
            string pending = String.Join("\n", head.Select(x => x.Key + "\t" + (x.Key == "status" ? "GAME_UPDATE_PENDING" : x.Value))) + "\ngame_update_transaction\t" + Path.GetFileName(transaction) + "\n";
            string complete = String.Join("\n", head.Select(x => x.Key + "\t" + x.Value)) + "\n";
            writes.Add(new Change { Target = filesPath, Before = FileOps.Sha256(filesPath), Content = Utf8.GetBytes(header + "\n" + String.Join("\n", rows.Select(x => String.Join("\t", x))) + "\n") });
            foreach (string target in writes.Select(x => x.Target).Concat(new[] { headPath }).Distinct(StringComparer.OrdinalIgnoreCase))
            {
                // Check every target for locks before changing any game asset or backup.
                using (var handle = new FileStream(target, FileMode.Open, FileAccess.Read, FileShare.None)) { }
                string backup = Path.Combine(transaction, snapshots.Count.ToString("D4"));
                string hash = FileOps.Sha256(target);
                FileOps.CopyNewExact(target, backup, hash);
                snapshots.Add(new Snapshot { Target = target, Copy = backup, Hash = hash, Attributes = File.GetAttributes(target) });
            }
            File.WriteAllLines(Path.Combine(transaction, "before.tsv"), snapshots.Select(x => x.Target + "\t" + Path.GetFileName(x.Copy) + "\t" + x.Hash + "\t" + (int)x.Attributes + "\t" +
                (x.Target == headPath ? Hash(Utf8.GetBytes(pending)) : Hash(writes.Single(w => w.Target == x.Target).Content))), Utf8);
            var touched = new List<Snapshot>();
            try
            {
                touched.Add(snapshots.Single(x => x.Target == headPath));
                FileOps.WriteTextAtomic(headPath, pending);
                foreach (Change write in writes)
                {
                    if (FileOps.Sha256(write.Target) != write.Before) throw new IOException("작업 중 다른 프로그램이 파일을 변경했습니다: " + write.Target);
                    Snapshot snapshot = snapshots.Single(x => x.Target == write.Target);
                    touched.Add(snapshot);
                    string temp = Path.Combine(transaction, "candidate");
                    File.WriteAllBytes(temp, write.Content);
                    File.SetAttributes(write.Target, snapshot.Attributes & ~FileAttributes.ReadOnly);
                    FileOps.ReplaceExact(temp, write.Target, Hash(write.Content));
                    File.SetAttributes(write.Target, snapshot.Attributes);
#if COMPATIBILITY_TEST
                    if (File.Exists(Path.Combine(game, ".compat_fail_after_write"))) throw new IOException("Injected compatibility rollback failure");
                    if (File.Exists(Path.Combine(game, ".compat_interrupt_after_write"))) Environment.Exit(73);
#endif
                }
                foreach (string[] row in rows) PackageManifest.RequireFile(SafePath(game, row[0]), Int64.Parse(row[4]), row[5], "재적용 완료 검증");
                FileOps.WriteTextAtomic(headPath, complete);
                File.WriteAllText(Path.Combine(transaction, "result.txt"), "PASS build=" + info.BuildId + " files=" + changes.Count, Utf8);
            }
            catch (Exception error)
            {
                var failures = new List<string>();
                foreach (Snapshot snapshot in touched.AsEnumerable().Reverse())
                    try
                    {
                        File.SetAttributes(snapshot.Target, File.GetAttributes(snapshot.Target) & ~FileAttributes.ReadOnly);
                        FileOps.ReplaceExact(snapshot.Copy, snapshot.Target, snapshot.Hash);
                        File.SetAttributes(snapshot.Target, snapshot.Attributes);
                    }
                    catch (Exception failure) { failures.Add(failure.Message); }
                File.WriteAllText(Path.Combine(transaction, "result.txt"), error.ToString() + "\n" + String.Join("\n", failures), Utf8);
                if (failures.Count > 0) throw new IOException("자동 롤백을 완료하지 못했습니다. 백업: " + transaction, error);
                throw;
            }
        }

        private static void RecoverPending(string game, string root, Dictionary<string, string> head, Rules rules)
        {
            string id;
            if (!head.TryGetValue("game_update_transaction", out id) || !Regex.IsMatch(id, "^[0-9]{8}-[0-9]{6}-[a-f0-9]{32}$"))
                throw new InvalidDataException("중단된 복구 기록의 위치를 확인하지 못했습니다. 백업을 보존하고 진단 ZIP을 생성해주세요.");
            string transaction = SafePath(root, "game-updates/" + id);
            string headPath = SafePath(root, "install-state.tsv");
            var allowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { headPath, SafePath(root, "files.tsv") };
            foreach (string relative in rules.menus.Keys.Concat(rules.archives.Keys))
            {
                allowed.Add(SafePath(game, relative));
                allowed.Add(SafePath(root, "original/" + head["backup_id"] + "/" + relative));
            }
            var snapshots = new List<Snapshot>();
            foreach (string line in File.ReadAllLines(SafePath(transaction, "before.tsv"), Utf8))
            {
                string[] row = line.Split('\t');
                if (row.Length != 5 || !allowed.Contains(row[0]) || !Regex.IsMatch(row[1], "^[0-9]{4}$") || snapshots.Any(x => x.Target.Equals(row[0], StringComparison.OrdinalIgnoreCase)))
                    throw new InvalidDataException("중단된 복구 기록의 경로 또는 형식이 잘못되었습니다.");
                string copy = SafePath(transaction, row[1]);
                string before = PackageManifest.NormalizeHash(row[2]), after = PackageManifest.NormalizeHash(row[4]);
                if (FileOps.Sha256(copy) != before) throw new InvalidDataException("중단된 복구의 백업 파일이 손상되었습니다.");
                string actual = FileOps.Sha256(row[0]);
                if (actual != before && actual != after) throw new InvalidDataException("복구가 중단된 뒤 파일이 추가로 변경되었습니다. 현재 파일을 보존했습니다: " + row[0]);
                using (var handle = new FileStream(row[0], FileMode.Open, FileAccess.Read, FileShare.None)) { }
                snapshots.Add(new Snapshot { Target = row[0], Copy = copy, Hash = before, Attributes = (FileAttributes)Int32.Parse(row[3]) });
            }
            if (snapshots.Count < 2 || snapshots.Count > allowed.Count || !snapshots.Any(x => x.Target == headPath))
                throw new InvalidDataException("중단된 복구의 백업 목록이 불완전합니다.");
            foreach (Snapshot snapshot in snapshots.Where(x => x.Target != headPath).Reverse().Concat(snapshots.Where(x => x.Target == headPath)))
            {
                File.SetAttributes(snapshot.Target, File.GetAttributes(snapshot.Target) & ~FileAttributes.ReadOnly);
                FileOps.ReplaceExact(snapshot.Copy, snapshot.Target, snapshot.Hash);
                File.SetAttributes(snapshot.Target, snapshot.Attributes);
            }
            File.WriteAllText(Path.Combine(transaction, "result.txt"), "RECOVERED: interrupted transaction restored before retry", Utf8);
        }

        private static List<TextField> Parse(byte[] data)
        {
            if (data.Length < 8 || data.Length > 64 * 1024 * 1024) throw new InvalidDataException("메뉴 크기 오류");
            float scale = BitConverter.ToSingle(data, 0);
            uint count = BitConverter.ToUInt32(data, 4);
            if (Single.IsNaN(scale) || Single.IsInfinity(scale) || count == 0 || count > 4096) throw new InvalidDataException("메뉴 헤더 변경");
            int cursor = 8;
            for (int n = 0; n < count; n++)
            {
                if (cursor >= data.Length) throw new InvalidDataException("메뉴 헤더 잘림");
                int length = data[cursor++];
                if (cursor + length > data.Length || !Utf8.GetString(data, cursor, length).EndsWith(".bspr", StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("메뉴 리소스 변경");
                cursor += length;
            }
            byte[] marker = { 4, 84, 101, 120, 116, 82, 43, 93, 95 };
            var result = new List<TextField>();
            var ids = new HashSet<uint>();
            for (int at = cursor; at <= data.Length - marker.Length; at++)
            {
                if (data[at] != 4) continue;
                bool match = true;
                for (int j = 1; j < marker.Length; j++) if (data[at + j] != marker[j]) { match = false; break; }
                if (!match) continue;
                int start = at - 4;
                if (start < 0 || start + 83 > data.Length || BitConverter.ToUInt32(data, start) > 65535) continue;
                int textLength = data[start + 73], fontAt = start + 82 + textLength;
                if (fontAt >= data.Length) continue;
                int length = data[fontAt], end = fontAt + 1 + length;
                if (end + 4 > data.Length) continue;
                string font;
                try { Utf8.GetString(data, start + 74, textLength); font = Utf8.GetString(data, fontAt + 1, length); }
                catch (DecoderFallbackException) { continue; }
                if (!font.StartsWith("gui\\", StringComparison.OrdinalIgnoreCase) || !font.EndsWith(".bfont", StringComparison.OrdinalIgnoreCase)) continue;
                bool geometry = true;
                for (int j = 0; j < 10; j++) { float f = BitConverter.ToSingle(data, start + 17 + 4 * j); if (Single.IsNaN(f) || Single.IsInfinity(f) || Math.Abs(f) > 1e8) geometry = false; }
                if (!geometry) continue;
                uint id = BitConverter.ToUInt32(data, start + 13);
                // Gamewide dialogs contain three anonymous (id=0) Text records in the official file.
                if ((id != 0 && !ids.Add(id)) || (result.Count > 0 && fontAt <= result[result.Count - 1].End)) throw new InvalidDataException("메뉴 항목 중복 또는 겹침");
                result.Add(new TextField { Record = start, Start = fontAt, End = end, Id = id, Font = font });
            }
            // Named widgets use the same length-prefixed font string without being named Text.
            // They were also remapped in the shipped patch; include them instead of losing those routes.
            var named = result.ToDictionary(x => x.Start);
            var fields = new List<TextField>();
            foreach (Match match in Regex.Matches(Encoding.GetEncoding(28591).GetString(data), @"(?i)gui\\[a-z0-9_]+\.bfont"))
            {
                if (match.Index == 0 || data[match.Index - 1] != match.Length || match.Index + match.Length > data.Length)
                    throw new InvalidDataException("폰트 문자열 구조가 변경되었습니다. 최신 패치가 필요합니다.");
                TextField field;
                if (!named.TryGetValue(match.Index - 1, out field))
                    field = new TextField { Start = match.Index - 1, End = match.Index + match.Length, Id = 0, Record = -1, Font = match.Value };
                fields.Add(field);
            }
            return fields;
        }

        internal static byte[] PatchMenu(byte[] source, MenuRule rule)
        {
            if (!String.IsNullOrEmpty(rule.resource))
            {
                // Legacy menus also contain previously reviewed non-font fixes. Only their exact stock is accepted.
                if (Hash(source) != rule.stock) throw new InvalidDataException("이전 빌드의 메뉴 파일이 검증된 원본과 다릅니다. 진단 ZIP을 생성해주세요.");
                using (var compressed = new MemoryStream(Resource(rule.resource)))
                using (var input = new GZipStream(compressed, CompressionMode.Decompress))
                using (var output = new MemoryStream())
                {
                    byte[] buffer = new byte[65536]; int count;
                    while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                    {
                        if (output.Length + count > 64 * 1024 * 1024) throw new InvalidDataException("이전 메뉴 데이터의 크기가 잘못되었습니다.");
                        output.Write(buffer, 0, count);
                    }
                    byte[] candidate = output.ToArray();
                    if (Hash(candidate) != rule.patched) throw new InvalidDataException("이전 메뉴 데이터 검증에 실패했습니다.");
                    return candidate;
                }
            }
            var records = Parse(source);
            if (records.Count < rule.count || records.Count > rule.count * 2) throw new InvalidDataException("메뉴 구조 변경으로 자동 재적용을 중단했습니다.");
            if (records.Count(record => record.Record >= 0) < rule.texts) throw new InvalidDataException("메뉴 Text 구조가 변경되었습니다.");
            if (rule.overrides.Keys.Any(key => !records.Any(record => record.Id.ToString() == key)))
                throw new InvalidDataException("개별 조정한 메뉴 항목이 변경되었습니다. 호환 패치가 필요합니다.");
            using (var output = new MemoryStream())
            {
                int cursor = 0;
                foreach (TextField record in records)
                {
                    string target;
                    if (!rule.map.TryGetValue(record.Font.ToLowerInvariant(), out target)) throw new InvalidDataException("새 폰트에 대한 호환 패치가 필요합니다: " + record.Font);
                    string[] special;
                    if (rule.overrides.TryGetValue(record.Id.ToString(), out special))
                    {
                        if (!record.Font.Equals(special[0], StringComparison.OrdinalIgnoreCase) || special.Length != 3 ||
                            Hash(source.Skip(record.Record).Take(record.Start - record.Record).ToArray()) != special[2])
                            throw new InvalidDataException("개별 메뉴 글씨 구조가 바뀌었습니다.");
                        target = special[1];
                    }
                    byte[] font = Utf8.GetBytes(target);
                    if (font.Length > 255) throw new InvalidDataException("폰트 이름 길이 오류");
                    output.Write(source, cursor, record.Start - cursor);
                    output.WriteByte((byte)font.Length); output.Write(font, 0, font.Length); cursor = record.End;
                }
                output.Write(source, cursor, source.Length - cursor);
                byte[] candidate = output.ToArray();
                var after = Parse(candidate);
                if (after.Count != records.Count) throw new InvalidDataException("메뉴 재검증 실패");
                // Reinsert every original font and require byte-for-byte identity, including all unknown fields.
                using (var reverse = new MemoryStream())
                {
                    cursor = 0;
                    for (int n = 0; n < records.Count; n++)
                    {
                        reverse.Write(candidate, cursor, after[n].Start - cursor);
                        reverse.Write(source, records[n].Start, records[n].End - records[n].Start);
                        cursor = after[n].End;
                    }
                    reverse.Write(candidate, cursor, candidate.Length - cursor);
                    if (!source.SequenceEqual(reverse.ToArray())) throw new InvalidDataException("폰트 이외의 메뉴 내용이 변경되었습니다.");
                }
                if (Hash(source) == rule.stock && Hash(candidate) != rule.patched) throw new InvalidDataException("검증된 메뉴 결과와 다릅니다.");
                return candidate;
            }
        }

        private sealed class Proto { public int Field, Wire; public ulong Number; public byte[] Bytes; }
        private static ulong Varint(byte[] data, ref int at)
        {
            ulong value = 0;
            for (int shift = 0; shift < 64 && at < data.Length; shift += 7)
            { byte b = data[at++]; if (shift == 63 && b > 1) break; value |= (ulong)(b & 127) << shift; if ((b & 128) == 0) return value; }
            throw new InvalidDataException("Steam manifest 정수 오류");
        }
        private static IEnumerable<Proto> Fields(byte[] data)
        {
            int at = 0;
            while (at < data.Length)
            {
                ulong tag = Varint(data, ref at);
                var field = new Proto { Field = checked((int)(tag >> 3)), Wire = (int)(tag & 7) };
                if (field.Field <= 0) throw new InvalidDataException("Steam manifest 필드 오류");
                if (field.Wire == 0) field.Number = Varint(data, ref at);
                else
                {
                    int length = field.Wire == 2 ? checked((int)Varint(data, ref at)) : field.Wire == 1 ? 8 : field.Wire == 5 ? 4 : -1;
                    if (length < 0 || length > data.Length - at) throw new InvalidDataException("Steam manifest 길이 오류");
                    field.Bytes = new byte[length]; Buffer.BlockCopy(data, at, field.Bytes, 0, length); at += length;
                }
                yield return field;
            }
        }
        private static bool SteamOriginal(GameInfo game, string relative, byte[] source)
        {
            string acf = File.ReadAllText(game.AppManifest);
            Match match = Regex.Match(acf, "\"1066891\"\\s*\\{\\s*\"manifest\"\\s*\"([0-9]+)\"");
            if (!match.Success) return false;
            var roots = new List<string> { Path.Combine(Path.GetDirectoryName(GameLauncher.FindSteam()), "depotcache"), Path.Combine(Path.GetDirectoryName(game.AppManifest), "depotcache") };
            foreach (string root in roots)
            {
                string file = Path.Combine(root, "1066891_" + match.Groups[1].Value + ".manifest");
                if (!File.Exists(file)) continue;
                byte[] data = File.ReadAllBytes(file);
                if (data.Length < 8 || data.Length > 64 * 1024 * 1024 || BitConverter.ToUInt32(data, 0) != 0x71F617D0) return false;
                int length = checked((int)BitConverter.ToUInt32(data, 4));
                if (length < 0 || length > data.Length - 8) return false;
                byte[] payload = new byte[length]; Buffer.BlockCopy(data, 8, payload, 0, length);
                foreach (Proto entry in Fields(payload).Where(x => x.Field == 1 && x.Wire == 2))
                {
                    var values = Fields(entry.Bytes).ToList();
                    Proto name = values.SingleOrDefault(x => x.Field == 1 && x.Wire == 2);
                    if (name == null || !Utf8.GetString(name.Bytes).Replace('\\', '/').Equals(relative, StringComparison.OrdinalIgnoreCase)) continue;
                    Proto size = values.Single(x => x.Field == 2 && x.Wire == 0), hash = values.Single(x => x.Field == 5 && x.Wire == 2);
                    using (var algorithm = SHA1.Create()) return size.Number == (ulong)source.Length && hash.Bytes.SequenceEqual(algorithm.ComputeHash(source));
                }
            }
            return false;
        }
    }
}
