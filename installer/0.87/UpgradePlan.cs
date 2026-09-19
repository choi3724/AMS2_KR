using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Ams2KoreanBeta
{
    internal sealed partial class BetaEngine
    {
        private List<PreviousInstallInfo> upgradeHistory = new List<PreviousInstallInfo>();
        private bool preservePreUpgradeBaseline;
        private bool HasVerifiedOriginal(string path, string hash)
        {
            foreach (var h in upgradeHistory)
            foreach (var old in h.State.Files.Where(x => x.RelativePath.Equals(path, StringComparison.OrdinalIgnoreCase) && x.AfterSha == hash))
            {
                if (old.Action == "created") return true;
                string backup = GameUpdateCompatibility.SafePath(h.StateRoot, "original/" + (h.State.BackupId.Length > 0 ? h.State.BackupId + "/" : "") + path);
                if (File.Exists(backup) && new FileInfo(backup).Length == old.BeforeBytes && FileOps.Sha256(backup) == old.BeforeSha) return true;
            }
            return false;
        }
        private sealed class RetiredFile { internal string Path, Before, After, Source; }
        private readonly List<RetiredFile> retiredFiles = new List<RetiredFile>();
        private byte[] PatchUpgradeMenu(DirectFile file, byte[] current, GameUpdateCompatibility.MenuRule rule)
        {
            try { return GameUpdateCompatibility.PatchMenu(current, rule); }
            catch (Exception directFailure)
            {
                // Older patches sometimes changed the menu layout itself. Only an
                // exact predecessor result permits undoing those owned edits from
                // its verified original; a third-party or Steam change never does.
                string currentHash = FileOps.Sha256TextBytes(current);
                foreach (var history in upgradeHistory.OrderByDescending(x => x.InstalledUtc))
                foreach (var old in history.State.Files.Where(x => x.Action == "modified" && x.RelativePath.Equals(file.RelativePath, StringComparison.OrdinalIgnoreCase) && x.AfterSha == currentHash && x.AfterBytes == current.LongLength))
                {
                    string backup = GameUpdateCompatibility.SafePath(history.StateRoot, "original/" + (history.State.BackupId.Length > 0 ? history.State.BackupId + "/" : "") + file.RelativePath);
                    if (!File.Exists(backup) || new FileInfo(backup).Length != old.BeforeBytes || FileOps.Sha256(backup) != old.BeforeSha) continue;
                    byte[] original = File.ReadAllBytes(backup);
                    if (FileOps.Sha256TextBytes(original) != old.BeforeSha) throw new IOException("이전 원본 백업 동시 변경: " + file.RelativePath);
                    var candidates = new List<GameUpdateCompatibility.MenuRule> { rule };
                    var legacy = GameUpdateCompatibility.ForBuild("").legacy;
                    GameUpdateCompatibility.MenuRule legacyRule;
                    if (legacy != null && legacy.menus.TryGetValue(file.RelativePath.Replace('\\','/').ToLowerInvariant(), out legacyRule) && legacyRule.stock == old.BeforeSha)
                        candidates.Add(legacyRule);
                    foreach (var candidateRule in candidates)
                    {
                        try
                        {
                            byte[] result = GameUpdateCompatibility.PatchMenu(original, candidateRule);
                            Log("이전 패치 소유 변경을 검증된 원본에서 재구성: " + file.RelativePath);
                            return result;
                        }
                        catch (InvalidDataException) { }
                    }
                }
                throw new InvalidDataException(directFailure.Message + " (이전 원본 기반 재구성도 확인하지 못했습니다.)", directFailure);
            }
        }
        private bool CanAdoptCreated(DirectFile f, string target)
        {
            string current = FileOps.Sha256(target); long bytes = new FileInfo(target).Length;
            if (current == f.Sha256 || f.AllowedBefore.Contains(current) || UpgradeOwnership.Owns(f.RelativePath,current,bytes,upgradeHistory))
            {
                // Reuse the same verified ownership decision for canonical uninstall
                // and rollback backup selection. This is per operation, not a hash list patch.
                if (!f.AllowedBefore.Contains(current)) f.AllowedBefore.Add(current);
                f.PreparedBeforeSha = current;
                Log("패치 소유 파일 인계: " + f.RelativePath + " | " + current);
                return true;
            }
            return false;
        }
        private void PlanRetiredFiles()
        {
            retiredFiles.Clear();
            preservePreUpgradeBaseline = manifest.DirectFiles.Any(f => f.Role == "modified" && f.PreparedBeforeSha == f.PreparedSha &&
                !HasVerifiedOriginal(f.RelativePath, f.PreparedBeforeSha));
            preservePreUpgradeBaseline |= manifest.DirectFiles.Any(f => upgradeHistory.Any(h => h.State.Files.Any(old =>
                old.Action == "modified" && old.RelativePath.Equals(f.RelativePath, StringComparison.OrdinalIgnoreCase) && old.AfterSha == f.PreparedBeforeSha)) &&
                !HasVerifiedOriginal(f.RelativePath, f.PreparedBeforeSha));
            preservePreUpgradeBaseline |= !String.IsNullOrEmpty(igphaseHudCandidatePath) && FileOps.Sha256(igphaseHudCandidatePath) == igphaseBefore && !HasVerifiedOriginal(PackageManifest.IgphaseHudRelativePath, igphaseBefore);
            preservePreUpgradeBaseline |= !String.IsNullOrEmpty(ersCandidatePath) && FileOps.Sha256(ersCandidatePath) == ersBefore && !HasVerifiedOriginal(ErsArchivePatch.RelativePath, ersBefore);
            if (preservePreUpgradeBaseline) preflightWarnings.Add("이전 원본 기록을 완전히 확인할 수 없어 제거 시 순정 대신 업그레이드 직전 전체 상태로 복원합니다. 기존 파일은 백업합니다.");
            var managed = new HashSet<string>(manifest.DirectFiles.Select(x=>x.RelativePath),StringComparer.OrdinalIgnoreCase);
            managed.Add(PackageManifest.IgphaseHudRelativePath); managed.Add(ErsArchivePatch.RelativePath);
            var candidates = UpgradeOwnership.Catalog.Select(x=>x.Path).Concat(upgradeHistory.SelectMany(x=>x.State.Files.Select(f=>f.RelativePath))).Distinct(StringComparer.OrdinalIgnoreCase);
            var cm = ContentManagerOverlay.Owned(gameDir);
            // Without a complete original baseline, retain all predecessor assets
            // so uninstall can restore the complete working pre-upgrade state.
            if (preservePreUpgradeBaseline) return;
            foreach(string path in candidates.Where(x=>!managed.Contains(x)))
            {
                string live = GameUpdateCompatibility.SafePath(gameDir,path);
                if(!File.Exists(live)) continue;
                string sha=FileOps.Sha256(live); long bytes=new FileInfo(live).Length;
                if(cm.Contains(path.Replace('\\','/').ToLowerInvariant())) { Log("폐기 후보 유지: CM 공유 파일 " + path); continue; }
                var matches=upgradeHistory.SelectMany(h=>h.State.Files.Where(f=>f.RelativePath.Equals(path,StringComparison.OrdinalIgnoreCase) && f.AfterSha==sha && f.AfterBytes==bytes).Select(f=>new {History=h,File=f})).ToList();
                if(matches.Any(x=>x.File.Action=="modified"))
                {
                    var valid=matches.FirstOrDefault(x=>x.File.Action=="modified" &&
                        File.Exists(GameUpdateCompatibility.SafePath(x.History.StateRoot,"original/"+(x.History.State.BackupId.Length>0?x.History.State.BackupId+"/":"")+path)));
                    if(valid==null) { preflightWarnings.Add("폐기 파일 유지: 현재 빌드의 원본 백업 확인 불가 | "+path); continue; }
                    string original=GameUpdateCompatibility.SafePath(valid.History.StateRoot,"original/"+(valid.History.State.BackupId.Length>0?valid.History.State.BackupId+"/":"")+path);
                    PackageManifest.RequireFile(original,valid.File.BeforeBytes,valid.File.BeforeSha,"폐기 파일 원본 백업");
                    retiredFiles.Add(new RetiredFile {Path=path,Before=sha,After=valid.File.BeforeSha,Source=original});
                }
                else if(matches.Any(x=>x.File.Action=="created") || UpgradeOwnership.Official(path,sha,bytes,"created"))
                    retiredFiles.Add(new RetiredFile {Path=path,Before=sha,After="ABSENT"});
                else Log("폐기 후보 유지: 현재 파일 소유권 불명 또는 외부 변경 | "+path);
            }
            Log("업그레이드 계획: 최신 관리 파일 "+manifest.DirectFiles.Count+", 폐기/원복 "+retiredFiles.Count+". 전체 후보 검증 후 반영합니다.");
        }
        private void ApplyRetiredFiles()
        {
            foreach(var item in retiredFiles)
            {
                string live=GameUpdateCompatibility.SafePath(gameDir,item.Path);
                if(!File.Exists(live) || FileOps.Sha256(live)!=item.Before) throw new IOException("폐기 파일 동시 변경: "+item.Path);
                if(item.After=="ABSENT") File.Delete(live); else FileOps.ReplaceExact(item.Source,live,item.After);
                Log("폐기 파일 처리: "+item.Path+" | "+item.After);
            }
        }
    }
}
