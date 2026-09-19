using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;

namespace Ams2KoreanBeta
{
    // Independent of release names, package IDs, file counts and version distances.
    internal static class UpgradeOwnership
    {
        internal sealed class Evidence { internal string Path, Hash, Role, Release; internal long Bytes; }
        private static List<Evidence> catalog;
        internal static List<Evidence> Catalog
        {
            get
            {
                if (catalog != null) return catalog;
                var result = new List<Evidence>();
                using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Ams2KoreanBeta.Ownership"))
                {
                    if (stream == null) throw new InvalidDataException("정식 배포 소유권 목록이 없습니다.");
                    using (var reader = new StreamReader(stream, Encoding.UTF8))
                    {
                        reader.ReadLine(); string line;
                        while ((line = reader.ReadLine()) != null)
                        {
                            string[] p = line.Split('\t');
                            if (p.Length != 6) throw new InvalidDataException("소유권 목록 형식 오류");
                            result.Add(new Evidence { Path = PackageManifest.NormalizeRelative(p[0]), Bytes = Int64.Parse(p[1]), Hash = PackageManifest.NormalizeHash(p[2]), Role = p[3], Release = p[4] });
                        }
                    }
                }
                catalog = result; return result;
            }
        }

        internal static bool Official(string path, string hash, long bytes, string role = null)
        { return Catalog.Any(x => x.Path.Equals(path, StringComparison.OrdinalIgnoreCase) && x.Hash == hash && x.Bytes == bytes && (role == null || x.Role == role)); }

        private static HashSet<string> managedPaths;
        internal static bool IsManagedPath(string path)
        {
            if (managedPaths == null)
            {
                var current = GameUpdateCompatibility.ForBuild("");
                managedPaths = new HashSet<string>(Catalog.Select(x => x.Path.Replace('\\','/')).Concat(current.files.Keys).Concat(current.archives.Keys), StringComparer.OrdinalIgnoreCase);
            }
            return managedPaths.Contains(path.Replace('\\','/'));
        }

        internal static IEnumerable<string> Roots(string game)
        {
            string parent = GameUpdateCompatibility.SafePath(game, "Backup/AMS2-Korean");
            if (!Directory.Exists(parent)) return new string[0];
            // Historical records live directly in this owned container, or its root.
            return new[] { parent }.Concat(Directory.GetDirectories(parent)).Where(x => File.Exists(Path.Combine(x, "files.tsv")) || File.Exists(Path.Combine(x, "install-state.tsv"))).ToArray();
        }
        internal static Dictionary<string,string> Head(string root)
        {
            var head = new Dictionary<string,string>(StringComparer.OrdinalIgnoreCase);
            string path = GameUpdateCompatibility.SafePath(root, "install-state.tsv");
            if (File.Exists(path)) foreach (string line in File.ReadAllLines(path, Encoding.UTF8))
            { string[] p = line.Split(new[] { '\t' }, 2); if (p.Length == 2) head[p[0]] = p[1]; }
            return head;
        }
        private static string Value(Dictionary<string,string> h, string key, string fallback)
        { string value; return h.TryGetValue(key, out value) ? value : fallback; }
        internal static List<PreviousInstallInfo> Read(string game, Action<string> log)
        {
            var result = new List<PreviousInstallInfo>();
            foreach (string root in Roots(game))
            {
                try
                {
                    var h = Head(root);
                    string recordedGame = Value(h, "game_dir", game);
                    if (!Path.GetFullPath(recordedGame).TrimEnd('\\').Equals(Path.GetFullPath(game).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("설치 기록의 게임 경로가 다릅니다.");
                    string status = Value(h, "status", "INCOMPLETE");
                    if (status == "RESTORED" || status == "ROLLED_BACK") continue;
                    string backup = Value(h, "backup_id", "");
                    if (backup.Length > 0 && (backup.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || backup == "." || backup == "..")) throw new InvalidDataException("백업 경로 오류");
                    var state = new InstallState { Status = status, GameDir = game, BuildId = Value(h,"buildid",""), BackupId = backup, InstalledUtc = Value(h,"installed_utc","") };
                    string file = GameUpdateCompatibility.SafePath(root, "files.tsv");
                    if (!File.Exists(file)) throw new InvalidDataException("파일 기록 누락; 정식 배포 목록으로 검사합니다.");
                    string[] lines = File.ReadAllLines(file, Encoding.UTF8);
                    if (lines.Length == 0) throw new InvalidDataException("파일 기록이 비어 있습니다.");
                    string[] columns = lines[0].Split('\t');
                    var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach (string line in lines.Skip(1).Where(x => !String.IsNullOrWhiteSpace(x)))
                    {
                        try
                        {
                            string[] p = line.Split('\t');
                            if (p.Length != columns.Length) throw new InvalidDataException("열 수 불일치");
                            var row = columns.Select((c,i) => new {c,i}).ToDictionary(x => x.c, x => p[x.i]);
                            string relative = PackageManifest.NormalizeRelative(row["relative_path"]);
                            GameUpdateCompatibility.SafePath(game, relative);
                            if (!seen.Add(relative)) throw new InvalidDataException("중복 파일 기록: " + relative);
                            // Records may identify only independently known localization paths.
                            if (!IsManagedPath(relative))
                                throw new InvalidDataException("정식 패치 관리 범위 밖: " + relative);
                            string action = row["action"];
                            if (action != "created" && action != "modified") throw new InvalidDataException("알 수 없는 소유권 action");
                            string before = row["before_sha256"];
                            if (action == "created" && before != "ABSENT") throw new InvalidDataException("생성 파일 원본 기록 오류");
                            if (action == "modified") before = PackageManifest.NormalizeHash(before);
                            var d = new DirectState { RelativePath = relative, Action = action, BeforeSha = before, BeforeBytes = Int64.Parse(row["before_bytes"]), AfterSha = PackageManifest.NormalizeHash(row["after_sha256"]), AfterBytes = Int64.Parse(row["after_bytes"]) };
                            if (d.BeforeBytes < 0 || d.AfterBytes < 0) throw new InvalidDataException("파일 크기 오류");
                            bool completeHeader = h.ContainsKey("game_dir") && h.ContainsKey("buildid") && h.ContainsKey("installed_utc") &&
                                new[] { "INSTALLED", "SUPERSEDED", "PREPARED", "GAME_UPDATE_PENDING" }.Contains(status);
                            if (!completeHeader && !Official(relative, d.AfterSha, d.AfterBytes)) throw new InvalidDataException("불완전한 기록이며 정식 배포본으로도 확인되지 않습니다: " + relative);
                            state.Files.Add(d);
                        }
                        catch (Exception e) { if(log != null) log("이전 기록 일부 복구 필요: " + root + " | " + e.Message); }
                    }
                    DateTime time; DateTime.TryParse(state.InstalledUtc, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out time);
                    result.Add(new PreviousInstallInfo { StateRoot = root, State = state, InstalledUtc = time, PackageId = Path.GetFileName(root), Version = Value(h,"package_version",Path.GetFileName(root)) });
                }
                catch (Exception e) { if(log != null) log("이전 기록 복구 검사: " + root + " | " + e.Message); }
            }
            return result;
        }
        internal static bool Match(string game, DirectState row)
        {
            string path = GameUpdateCompatibility.SafePath(game, row.RelativePath);
            return File.Exists(path) && new FileInfo(path).Length == row.AfterBytes && FileOps.Sha256(path) == row.AfterSha;
        }
        internal static bool Owns(string path, string hash, long bytes, IEnumerable<PreviousInstallInfo> history)
        {
            return Official(path, hash, bytes) || history.Any(x => x.State.Files.Any(f => f.RelativePath.Equals(path, StringComparison.OrdinalIgnoreCase) && f.AfterSha == hash && f.AfterBytes == bytes));
        }
    }

    // A durable outer transaction includes upgrade files AND predecessor metadata.
    // Candidates and all backups exist before PREPARED is published. Recovery is
    // idempotent and checks every current hash before overwriting any file.
    internal sealed class UpgradeTransaction
    {
        internal sealed class Item { public string Path, Before, After; public long Attributes, Created, Modified; }
        private readonly string game, root;
        private readonly List<Item> items;
        private UpgradeTransaction(string game, string root, List<Item> items) { this.game=game; this.root=root; this.items=items; }
        internal static UpgradeTransaction Begin(string game, Dictionary<string,string> targets)
        {
            string root=GameUpdateCompatibility.SafePath(game,"Backup/AMS2-Korean-Upgrade/current");
            Directory.CreateDirectory(root);
            if(File.Exists(Path.Combine(root,"pending.tsv"))) throw new InvalidOperationException("이전 업그레이드 복구가 필요합니다.");
            string id=Guid.NewGuid().ToString("N"); var items=new List<Item>();
            foreach(var target in targets.OrderBy(x=>x.Key,StringComparer.OrdinalIgnoreCase))
            {
                string live=GameUpdateCompatibility.SafePath(game,target.Key);
                var item=new Item {Path=target.Key,Before=File.Exists(live)?FileOps.Sha256(live):"ABSENT",After=target.Value};
                if(item.Before!="ABSENT")
                {
                    item.Attributes=(long)File.GetAttributes(live); item.Created=File.GetCreationTimeUtc(live).Ticks; item.Modified=File.GetLastWriteTimeUtc(live).Ticks;
                    FileOps.CopyNewExact(live,GameUpdateCompatibility.SafePath(root,"snapshots/"+id+"/"+items.Count.ToString("D4")),item.Before);
                }
                items.Add(item);
            }
            FileOps.WriteTextAtomic(Path.Combine(root,"pending.tsv"),id+"\n"+String.Join("\n",items.Select(x=>x.Path+"\t"+x.Before+"\t"+x.After+"\t"+x.Attributes+"\t"+x.Created+"\t"+x.Modified))+"\n");
            return new UpgradeTransaction(game,root,items);
        }
        internal void Commit() { File.Delete(Path.Combine(root,"pending.tsv")); }
        internal static bool Recover(string game, Action<string> log)
        {
            string root=GameUpdateCompatibility.SafePath(game,"Backup/AMS2-Korean-Upgrade/current");
            string pending=Path.Combine(root,"pending.tsv"); if(!File.Exists(pending)) return false;
            string[] lines=File.ReadAllLines(pending,Encoding.UTF8); string id=lines[0];
            if(id.Length!=32 || !id.All(Uri.IsHexDigit)) throw new InvalidDataException("업그레이드 복구 ID 오류");
            var entries=new List<Item>();
            foreach(string line in lines.Skip(1).Where(x=>x.Length>0))
            {
                string[] p=line.Split('\t'); if(p.Length!=6) throw new InvalidDataException("업그레이드 복구 기록 오류");
                string live=GameUpdateCompatibility.SafePath(game,p[0]);
                string normalized=p[0].Replace('\\','/');
                bool metadata=normalized.StartsWith("Backup/AMS2-Korean/",StringComparison.OrdinalIgnoreCase) &&
                    (normalized.Split('/').Length==3 || normalized.Split('/').Length==4) &&
                    new[] { "install-state.tsv", "files.tsv", "invariants.tsv", "shortcuts.tsv" }.Contains(Path.GetFileName(p[0]));
                if(!metadata && !UpgradeOwnership.IsManagedPath(p[0]))
                    throw new InvalidDataException("업그레이드 복구 관리 범위 밖: "+p[0]);
                string current=File.Exists(live)?FileOps.Sha256(live):"ABSENT";
                if(!metadata && current!=p[1] && current!=p[2]) throw new IOException("업그레이드 중 외부 변경으로 복구 중단: "+p[0]);
                if(p[1]!="ABSENT")
                {
                    PackageManifest.NormalizeHash(p[1]);
                    if(FileOps.Sha256(GameUpdateCompatibility.SafePath(root,"snapshots/"+id+"/"+entries.Count.ToString("D4")))!=p[1]) throw new InvalidDataException("업그레이드 백업 손상: "+p[0]);
                }
                entries.Add(new Item {Path=p[0],Before=p[1],After=p[2],Attributes=Int64.Parse(p[3]),Created=Int64.Parse(p[4]),Modified=Int64.Parse(p[5])});
            }
            foreach(Item item in entries.AsEnumerable().Reverse())
            {
                string live=GameUpdateCompatibility.SafePath(game,item.Path);
                if(item.Before=="ABSENT") {if(File.Exists(live)) File.Delete(live);}
                else
                {
                    FileOps.ReplaceExact(GameUpdateCompatibility.SafePath(root,"snapshots/"+id+"/"+entries.IndexOf(item).ToString("D4")),live,item.Before);
                    File.SetCreationTimeUtc(live,new DateTime(item.Created,DateTimeKind.Utc)); File.SetLastWriteTimeUtc(live,new DateTime(item.Modified,DateTimeKind.Utc)); File.SetAttributes(live,(FileAttributes)item.Attributes);
                }
            }
            File.Delete(pending); if(log!=null) log("업그레이드 전체 복구 완료: 작업 직전 파일과 이전 설치 기록을 복원했습니다."); return true;
        }
    }
}
