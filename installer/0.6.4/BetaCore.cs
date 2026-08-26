using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32;

namespace Ams2KoreanBeta
{
    internal sealed class DirectFile
    {
        public string RelativePath;
        public long Bytes;
        public string Sha256;
        public string Role;
        public List<string> AllowedBefore = new List<string>();
    }

    internal sealed class PackageManifest
    {
        public const string PackageId = "AMS2-KR-BETA-0.6.4-PRETENDARD";
        public const string Version = "Closed Beta 0.6.4";
        public const string AppId = "1066890";
        public const string BuildId = "24132163";
        public const string Branch = "public";
        public const string StockBootflowSha256 = "2FE28D744F8DF0443FB290A10DAC52AA1308DE9389E776F0BD5F2BB8F03355B7";
        public const string StockPhysicsSha256 = "39B720D1DC4CE529AC06AE10D0CF756E602ABD97772C5A24D7F31065C289C434";

        public string ReleaseRoot;
        public List<DirectFile> DirectFiles = new List<DirectFile>();

        public static PackageManifest Load(string releaseRoot)
        {
            PackageManifest m = new PackageManifest();
            m.ReleaseRoot = Path.GetFullPath(releaseRoot);
            string table = Path.Combine(m.ReleaseRoot, "manifest", "direct-files.tsv");
            if (!File.Exists(table)) throw new InvalidOperationException("설치 패키지 manifest가 없습니다.");
            foreach (string line in File.ReadAllLines(table, Encoding.UTF8).Skip(1))
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                string[] p = line.Split('\t');
                if (p.Length != 5) throw new InvalidOperationException("direct-files.tsv 형식 오류");
                DirectFile f = new DirectFile();
                f.RelativePath = NormalizeRelative(p[0]);
                f.Bytes = Int64.Parse(p[1], CultureInfo.InvariantCulture);
                f.Sha256 = NormalizeHash(p[2]);
                f.Role = p[3];
                if (!String.IsNullOrWhiteSpace(p[4])) f.AllowedBefore.AddRange(p[4].Split(';').Select(NormalizeHash));
                if (f.Role != "modified" && f.Role != "created") throw new InvalidOperationException("알 수 없는 role: " + f.Role);
                if (f.Role == "modified" && f.AllowedBefore.Count == 0) throw new InvalidOperationException("수정 원본 hash 누락: " + f.RelativePath);
                string lower = f.RelativePath.ToLowerInvariant();
                if (!(lower.StartsWith("gui\\") || lower.StartsWith("text\\") ||
                      (lower.StartsWith("hud_") && lower.EndsWith(".bgui")) ||
                      lower == "ams2 korean launcher.exe" || lower == "ams2 korean vr launcher.exe"))
                    throw new InvalidOperationException("localization-only 범위 밖 payload: " + f.RelativePath);
                m.DirectFiles.Add(f);
            }
            if (m.DirectFiles.Count == 0 || m.DirectFiles.Select(x => x.RelativePath).Distinct(StringComparer.OrdinalIgnoreCase).Count() != m.DirectFiles.Count)
                throw new InvalidOperationException("direct payload empty/duplicate");
            return m;
        }

        public string DirectSource(DirectFile f) { return SafeJoin(Path.Combine(ReleaseRoot, "payload", "direct"), f.RelativePath); }

        public void ValidateAll()
        {
            foreach (DirectFile f in DirectFiles) RequireFile(DirectSource(f), f.Bytes, f.Sha256, "payload");
        }

        internal static void RequireFile(string path, long bytes, string hash, string label)
        {
            FileInfo i = new FileInfo(path);
            if (!i.Exists || i.Length != bytes || FileOps.Sha256(path) != hash)
                throw new InvalidOperationException(label + " hash/size mismatch: " + path);
        }

        internal static string NormalizeRelative(string value)
        {
            string v = value.Replace('/', '\\').TrimStart('\\');
            if (Path.IsPathRooted(v) || v.Split('\\').Any(x => x == ".." || x == "")) throw new InvalidOperationException("unsafe path: " + value);
            return v;
        }

        internal static string NormalizeHash(string value)
        {
            string v = value.Trim().ToUpperInvariant();
            if (!Regex.IsMatch(v, "^[0-9A-F]{64}$")) throw new InvalidOperationException("invalid SHA-256");
            return v;
        }

        internal static string SafeJoin(string root, string relative)
        {
            string r = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            string p = Path.GetFullPath(Path.Combine(r, NormalizeRelative(relative)));
            if (!p.StartsWith(r, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("path boundary failure");
            return p;
        }
    }

    internal static class FileOps
    {
        public static string Sha256(string path)
        {
            using (SHA256 h = SHA256.Create())
            using (FileStream f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                return BitConverter.ToString(h.ComputeHash(f)).Replace("-", "");
        }

        public static string Sha256Text(string text)
        {
            using (SHA256 h = SHA256.Create()) return BitConverter.ToString(h.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-", "");
        }

        public static void EnsureDirectoryFor(string file)
        {
            string d = Path.GetDirectoryName(file);
            if (!Directory.Exists(d)) Directory.CreateDirectory(d);
        }

        public static void CopyNewExact(string source, string target, string expected)
        {
            if (File.Exists(target)) throw new InvalidOperationException("대상이 이미 존재합니다: " + target);
            EnsureDirectoryFor(target);
            string tmp = target + ".krbeta.tmp." + Guid.NewGuid().ToString("N");
            File.Copy(source, tmp, false);
            if (Sha256(tmp) != expected) throw new InvalidOperationException("임시 복사 hash 불일치");
            File.Move(tmp, target);
        }

        public static void ReplaceExact(string source, string target, string expected)
        {
            EnsureDirectoryFor(target);
            string tmp = target + ".krbeta.tmp." + Guid.NewGuid().ToString("N");
            File.Copy(source, tmp, false);
            if (Sha256(tmp) != expected) throw new InvalidOperationException("임시 교체 hash 불일치");
            if (File.Exists(target)) File.Replace(tmp, target, null); else File.Move(tmp, target);
            if (Sha256(target) != expected) throw new InvalidOperationException("교체 후 hash 불일치");
        }

        public static void WriteTextAtomic(string target, string text)
        {
            EnsureDirectoryFor(target);
            string tmp = target + ".tmp." + Guid.NewGuid().ToString("N");
            File.WriteAllText(tmp, text, new UTF8Encoding(false));
            if (File.Exists(target)) File.Replace(tmp, target, null); else File.Move(tmp, target);
        }
    }

    internal sealed class GameInfo
    {
        public string GameDir;
        public string AppManifest;
        public string BuildId;
        public string Branch;
    }

    internal static class SteamLocator
    {
        public static List<GameInfo> Detect()
        {
            HashSet<string> steamRoots = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            AddRegistry(steamRoots, Registry.CurrentUser, @"Software\Valve\Steam", "SteamPath");
            AddRegistry(steamRoots, Registry.LocalMachine, @"Software\WOW6432Node\Valve\Steam", "InstallPath");
            List<string> libraries = new List<string>();
            foreach (string root in steamRoots)
            {
                libraries.Add(root);
                string vdf = Path.Combine(root, "steamapps", "libraryfolders.vdf");
                if (!File.Exists(vdf)) continue;
                foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\\\"path\\\"\\s+\\\"([^\\\"]+)\\\"", RegexOptions.IgnoreCase))
                    libraries.Add(m.Groups[1].Value.Replace("\\\\", "\\"));
            }
            List<GameInfo> found = new List<GameInfo>();
            foreach (string lib in libraries.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                string acf = Path.Combine(lib, "steamapps", "appmanifest_" + PackageManifest.AppId + ".acf");
                if (!File.Exists(acf)) continue;
                try { found.Add(FromAppManifest(acf, null)); } catch { }
            }
            return found.GroupBy(x => x.GameDir, StringComparer.OrdinalIgnoreCase).Select(x => x.First()).ToList();
        }

        public static GameInfo FromGameDirectory(string gameDir)
        {
            string game = Path.GetFullPath(gameDir).TrimEnd(Path.DirectorySeparatorChar);
            DirectoryInfo common = Directory.GetParent(game);
            if (common == null || !common.Name.Equals("common", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("Steam common 경로가 아닙니다.");
            DirectoryInfo steamapps = common.Parent;
            if (steamapps == null) throw new InvalidOperationException("steamapps 경로를 찾지 못했습니다.");
            string acf = Path.Combine(steamapps.FullName, "appmanifest_" + PackageManifest.AppId + ".acf");
            return FromAppManifest(acf, game);
        }

        private static GameInfo FromAppManifest(string acf, string expected)
        {
            if (!File.Exists(acf)) throw new InvalidOperationException("Steam appmanifest가 없습니다.");
            string text = File.ReadAllText(acf);
            string app = Value(text, "appid");
            string build = Value(text, "buildid");
            string install = Value(text, "installdir");
            if (app != PackageManifest.AppId) throw new InvalidOperationException("AppID 불일치");
            string steamapps = Directory.GetParent(acf).FullName;
            string game = Path.Combine(steamapps, "common", install);
            if (expected != null && !Path.GetFullPath(game).Equals(Path.GetFullPath(expected), StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("선택 경로와 appmanifest가 다릅니다.");
            if (!File.Exists(Path.Combine(game, "AMS2.exe")) || !File.Exists(Path.Combine(game, "AMS2AVX.exe"))) throw new InvalidOperationException("AMS2 실행 파일이 없습니다.");
            return new GameInfo { GameDir = Path.GetFullPath(game), AppManifest = Path.GetFullPath(acf), BuildId = build, Branch = "public" };
        }

        private static string Value(string text, string key)
        {
            Match m = Regex.Match(text, "\\\"" + Regex.Escape(key) + "\\\"\\s+\\\"([^\\\"]*)\\\"", RegexOptions.IgnoreCase);
            if (!m.Success) throw new InvalidOperationException("appmanifest field missing: " + key);
            return m.Groups[1].Value;
        }

        private static void AddRegistry(HashSet<string> roots, RegistryKey hive, string subkey, string name)
        {
            try { using (RegistryKey k = hive.OpenSubKey(subkey)) { object v = k == null ? null : k.GetValue(name); if (v != null && Directory.Exists(v.ToString())) roots.Add(Path.GetFullPath(v.ToString())); } } catch { }
        }
    }

    internal sealed class DirectState
    {
        public string RelativePath;
        public string Action;
        public string BeforeSha;
        public long BeforeBytes;
        public string AfterSha;
        public long AfterBytes;
    }

    internal sealed class InvariantState
    {
        public string BootflowSha;
        public string PhysicsSha;
        public bool PhysicsMarker;
        public int VehicleFiles;
        public string VehicleTreeSha;
        public int TrackFiles;
        public string TrackTreeSha;
    }

    internal sealed class InstallState
    {
        public string Status;
        public string InstalledUtc;
        public string GameDir;
        public string BuildId;
        public string BackupId;
        public InvariantState Invariants;
        public List<DirectState> Files = new List<DirectState>();
    }

    internal sealed class OperationResult
    {
        public bool Success;
        public string Status;
        public string Message;
        public string LogPath;
    }

    internal sealed class PreviousInstallInfo
    {
        public string PackageId;
        public string Version;
        public DateTime InstalledUtc;
    }

    internal sealed class ShortcutOptions
    {
        public bool Desktop;
        public bool StartMenu;
        public bool Taskbar;
    }

    internal static class ShortcutManager
    {
        private const string NormalShortcutName = "오모빌2 한글판.lnk";
        private const string VrShortcutName = "오모빌2 한글판 VR모드.lnk";

        [DllImport("shell32.dll")]
        private static extern void SHChangeNotify(uint eventId, uint flags, IntPtr item1, IntPtr item2);

        public static void Apply(string gameDir, string stateRoot, ShortcutOptions options, Action<string> log)
        {
            RemoveOwned(stateRoot, log);
            if (options == null) return;
            string launcher = Path.Combine(gameDir, "AMS2 Korean Launcher.exe");
            string vrLauncher = Path.Combine(gameDir, "AMS2 Korean VR Launcher.exe");
            PackageManifest.RequireFile(launcher, new FileInfo(launcher).Length, FileOps.Sha256(launcher), "한국어 런처");
            PackageManifest.RequireFile(vrLauncher, new FileInfo(vrLauncher).Length, FileOps.Sha256(vrLauncher), "한국어 VR 런처");
            List<string[]> created = new List<string[]>();
            if (options.Desktop) CreatePair("DESKTOP", Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), launcher, vrLauncher, created, log);
            if (options.StartMenu) CreatePair("START_MENU", Environment.GetFolderPath(Environment.SpecialFolder.Programs), launcher, vrLauncher, created, log);
            if (options.Taskbar)
            {
                string pinned = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar");
                CreatePair("TASKBAR", pinned, launcher, vrLauncher, created, log);
                SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
            }
            StringBuilder state = new StringBuilder("kind\tpath\tsha256\r\n");
            foreach (string[] row in created) state.AppendLine(String.Join("\t", row));
            FileOps.WriteTextAtomic(Path.Combine(stateRoot, "shortcuts.tsv"), state.ToString());
        }

        private static void CreatePair(string kind, string directory, string launcher, string vrLauncher, List<string[]> created, Action<string> log)
        {
            CreateOwned(kind + "_NORMAL", Path.Combine(directory, NormalShortcutName), launcher, created, log);
            CreateOwned(kind + "_VR", Path.Combine(directory, VrShortcutName), vrLauncher, created, log);
        }

        public static void RemoveOwned(string stateRoot, Action<string> log)
        {
            string statePath = Path.Combine(stateRoot, "shortcuts.tsv");
            if (!File.Exists(statePath)) return;
            bool preserved = false;
            foreach (string line in File.ReadAllLines(statePath, Encoding.UTF8).Skip(1))
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                string[] row = line.Split('\t');
                if (row.Length != 3) { preserved = true; continue; }
                string path = row[1];
                if (!File.Exists(path)) continue;
                if (FileOps.Sha256(path) != row[2])
                {
                    preserved = true;
                    if (log != null) log("사용자가 변경한 바로가기를 보존했습니다: " + path);
                    continue;
                }
                File.Delete(path);
                if (log != null) log("바로가기 제거: " + path);
            }
            if (!preserved) File.Delete(statePath);
            SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
        }

        private static void CreateOwned(string kind, string path, string launcher, List<string[]> created, Action<string> log)
        {
            if (File.Exists(path))
            {
                if (log != null) log("기존 바로가기를 덮어쓰지 않았습니다: " + path);
                return;
            }
            FileOps.EnsureDirectoryFor(path);
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) throw new InvalidOperationException("Windows 바로가기 기능을 사용할 수 없습니다.");
            object shell = null;
            object shortcut = null;
            try
            {
                shell = Activator.CreateInstance(shellType);
                shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
                Type shortcutType = shortcut.GetType();
                shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { launcher });
                shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { Path.GetDirectoryName(launcher) });
                shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut, new object[] { launcher + ",0" });
                shortcutType.InvokeMember("Description", BindingFlags.SetProperty, null, shortcut, new object[] { "Automobilista 2 한국어로 실행" });
                shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
            }
            finally
            {
                if (shortcut != null && Marshal.IsComObject(shortcut)) Marshal.FinalReleaseComObject(shortcut);
                if (shell != null && Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell);
            }
            if (!File.Exists(path)) throw new InvalidOperationException("바로가기 생성 실패: " + path);
            created.Add(new[] { kind, path, FileOps.Sha256(path) });
            if (log != null) log("바로가기 생성: " + path);
        }
    }

    internal sealed class BetaEngine
    {
        private readonly PackageManifest manifest;
        private readonly Action<string> logCallback;
        private readonly bool mockMode;
        private readonly StringBuilder log = new StringBuilder();
        private string gameDir;
        private string stateRoot;

        public BetaEngine(PackageManifest package, Action<string> logger, bool mock)
        {
            manifest = package;
            logCallback = logger;
            mockMode = mock;
        }

        private void Log(string value)
        {
            log.AppendLine(DateTime.UtcNow.ToString("o") + " " + value);
            if (logCallback != null) logCallback(value);
        }

        public OperationResult Check(GameInfo game)
        {
            try
            {
                Prepare(game);
                ValidateGame(game);
                manifest.ValidateAll();
                string detected = DetectState();
                if (detected == "NOT_INSTALLED" || detected == "RESTORED_EXACT")
                {
                    PreviousInstallInfo previous = FindPreviousInstalled();
                    if (previous != null)
                        return Ok("UPDATE_AVAILABLE", previous.Version + " 버전이 설치되어 있습니다. " + PackageManifest.Version + "로 업데이트가 필요합니다.", null);
                }
                return Ok(detected, "상태 확인 완료: " + detected, null);
            }
            catch (Exception e) { return Fail("CHECK_FAILED", e.Message); }
        }

        public OperationResult Install(GameInfo game) { return Install(game, null); }

        public OperationResult Install(GameInfo game, ShortcutOptions shortcuts)
        {
            InstallState state = null;
            try
            {
                Prepare(game);
                ValidateGame(game);
                manifest.ValidateAll();
                GuardProcesses();
                string detected = DetectState();
                if (detected == "INSTALLED_EXACT")
                {
                    if (shortcuts != null) ShortcutManager.Apply(gameDir, stateRoot, shortcuts, Log);
                    return Ok(detected, shortcuts == null ? "이미 정확히 설치되어 있습니다." : "이미 정확히 설치되어 있습니다. 선택한 바로가기를 갱신했습니다.", SaveLog());
                }
                if (detected == "PARTIAL_OR_DAMAGED") throw new InvalidOperationException("부분 설치 상태입니다. 제거/복구를 먼저 실행하십시오.");
                PreviousInstallInfo previous = FindPreviousInstalled();
                PreflightFiles();
                state = BuildState(game);
                SaveState(state, "PREPARED");
                ApplyFiles(state);
                ValidateInstalled(state);
                ShortcutManager.Apply(gameDir, stateRoot, shortcuts, Log);
                SaveState(state, "INSTALLED");
                Log("설치 완료: AMS2CM/dotnet/Generated Bootfiles/physics post-processing 0");
                string path = SaveLog();
                if (previous != null)
                    return Ok("UPDATED_EXACT", previous.Version + "에서 " + PackageManifest.Version + "로 업데이트했습니다. 반드시 생성한 바로가기 아이콘 또는 'AMS2 Korean Launcher.exe'로 실행하십시오.", path);
                return Ok("INSTALLED_EXACT", PackageManifest.Version + " 설치 완료. 반드시 생성한 바로가기 아이콘 또는 'AMS2 Korean Launcher.exe'로 실행하십시오.", path);
            }
            catch (Exception e)
            {
                Log("설치 실패: " + e.Message);
                bool rollbackAttempted = false;
                try
                {
                    if (state != null)
                    {
                        rollbackAttempted = true;
                        ShortcutManager.RemoveOwned(stateRoot, Log);
                        Rollback(state);
                        SaveState(state, "RESTORED");
                        Log("자동 롤백 완료");
                    }
                }
                catch (Exception rollback) { Log("자동 롤백 실패: " + rollback.Message); }
                return Fail("INSTALL_FAILED", e.Message + (rollbackAttempted ? " (자동 롤백을 시도했습니다)" : ""));
            }
        }

        public OperationResult Uninstall(GameInfo game)
        {
            try
            {
                Prepare(game);
                ValidateGame(game);
                GuardProcesses();
                InstallState state = LoadState();
                if (state == null || (state.Status != "INSTALLED" && state.Status != "PREPARED")) throw new InvalidOperationException("복구할 활성 설치 상태가 없습니다.");
                if (state.Status == "INSTALLED") ValidateInstalled(state);
                ShortcutManager.RemoveOwned(stateRoot, Log);
                Rollback(state);
                ValidateRestored(state);
                SaveState(state, "RESTORED");
                Log("복구 완료: 패치 파일을 설치 전 상태로 복원했습니다.");
                return Ok("RESTORED_EXACT", "한국어 패치를 제거하고 설치 전 상태로 복구했습니다.", SaveLog());
            }
            catch (Exception e) { Log("제거/복구 실패: " + e.Message); return Fail("RESTORE_FAILED", e.Message); }
        }

        public OperationResult LaunchKorean(GameInfo game)
        {
            try
            {
                Prepare(game);
                ValidateGame(game);
                GuardProcesses();
                InstallState state = LoadState();
                if (state == null || state.Status != "INSTALLED") throw new InvalidOperationException("한국어 패치가 정확히 설치되지 않았습니다.");
                ValidateInstalled(state);
                ProcessStartInfo p = new ProcessStartInfo(Path.Combine(gameDir, "AMS2.exe"), "-novr -lang=Korean -looseloadtext");
                p.WorkingDirectory = gameDir;
                p.UseShellExecute = true;
                Process.Start(p);
                Log("한국어 실행: AMS2.exe -novr -lang=Korean -looseloadtext");
                return Ok("LAUNCHED_KOREAN", "한국어 모드로 게임을 실행했습니다.", SaveLog());
            }
            catch (Exception e) { return Fail("LAUNCH_FAILED", e.Message); }
        }

        public OperationResult Diagnose(GameInfo game, string outputZip)
        {
            try
            {
                Prepare(game);
                ValidateGame(game);
                string temp = Path.Combine(Path.GetTempPath(), "AMS2-KR-BETA053-DIAG-" + Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(temp);
                try
                {
                    InvariantState inv = CaptureInvariant();
                    StringBuilder s = new StringBuilder();
                    s.AppendLine("version=" + PackageManifest.Version);
                    s.AppendLine("build=" + game.BuildId);
                    s.AppendLine("state=" + DetectState());
                    s.AppendLine("install_mode=LOCALIZATION_ONLY_LOOSELOADTEXT");
                    s.AppendLine("bootflow_sha256=" + inv.BootflowSha);
                    s.AppendLine("physicspersistent_sha256=" + inv.PhysicsSha);
                    s.AppendLine("physicspersistent_remove_marker=" + (inv.PhysicsMarker ? "true" : "false"));
                    s.AppendLine("vehicle_files=" + inv.VehicleFiles);
                    s.AppendLine("vehicle_tree_sha256=" + inv.VehicleTreeSha);
                    s.AppendLine("track_files=" + inv.TrackFiles);
                    s.AppendLine("track_tree_sha256=" + inv.TrackTreeSha);
                    s.AppendLine("ams2cm_helper=false");
                    s.AppendLine("crd_trd_driveline_postprocessing=0");
                    File.WriteAllText(Path.Combine(temp, "diagnostic-summary.txt"), s.ToString(), new UTF8Encoding(false));
                    StringBuilder files = new StringBuilder("path\texists\tbytes\tsha256\texpected\n");
                    foreach (DirectFile f in manifest.DirectFiles)
                    {
                        string p = PackageManifest.SafeJoin(gameDir, f.RelativePath);
                        bool exists = File.Exists(p);
                        files.Append(f.RelativePath).Append('\t').Append(exists ? "1" : "0").Append('\t')
                            .Append(exists ? new FileInfo(p).Length.ToString(CultureInfo.InvariantCulture) : "0").Append('\t')
                            .Append(exists ? FileOps.Sha256(p) : "").Append('\t').Append(f.Sha256).AppendLine();
                    }
                    File.WriteAllText(Path.Combine(temp, "payload-hashes.tsv"), files.ToString(), new UTF8Encoding(false));
                    if (Directory.Exists(stateRoot)) foreach (string n in new[] { "install-state.tsv", "files.tsv", "invariants.tsv", "events.log", "shortcuts.tsv" })
                    {
                        string source = Path.Combine(stateRoot, n);
                        if (File.Exists(source)) File.Copy(source, Path.Combine(temp, n));
                    }
                    if (File.Exists(outputZip)) throw new InvalidOperationException("진단 ZIP 대상이 이미 존재합니다.");
                    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outputZip)));
                    ZipFile.CreateFromDirectory(temp, outputZip, CompressionLevel.Optimal, false);
                }
                finally { try { Directory.Delete(temp, true); } catch { } }
                return Ok("DIAGNOSTIC_CREATED", "진단 ZIP을 생성했습니다.", outputZip);
            }
            catch (Exception e) { return Fail("DIAGNOSTIC_FAILED", e.Message); }
        }

        private void Prepare(GameInfo game)
        {
            gameDir = Path.GetFullPath(game.GameDir).TrimEnd(Path.DirectorySeparatorChar);
            stateRoot = Path.Combine(gameDir, "Backup", "AMS2-Korean", PackageManifest.PackageId);
        }

        private void ValidateGame(GameInfo game)
        {
            if (!File.Exists(Path.Combine(gameDir, "AMS2.exe")) || !File.Exists(Path.Combine(gameDir, "AMS2AVX.exe"))) throw new InvalidOperationException("게임 실행 파일 검증 실패");
            if (game.BuildId != PackageManifest.BuildId) Log("경고: 이 패치는 build " + PackageManifest.BuildId + " 기준으로 최적화되었습니다. 현재 build: " + game.BuildId);
            if (!game.Branch.Equals(PackageManifest.Branch, StringComparison.OrdinalIgnoreCase)) Log("경고: 이 패치는 " + PackageManifest.Branch + " branch 기준으로 최적화되었습니다. 현재 branch: " + game.Branch);
        }

        private void GuardProcesses()
        {
            if (mockMode && File.Exists(Path.Combine(gameDir, ".mock_process_running"))) throw new InvalidOperationException("AMS2 실행 중 (mock)");
            List<string> found = new List<string>();
            foreach (string n in new[] { "AMS2", "AMS2AVX", "procmon", "procmon64", "procmon64a" })
                foreach (Process p in Process.GetProcessesByName(n)) { found.Add(p.ProcessName + "#" + p.Id); p.Dispose(); }
            if (found.Count > 0) throw new InvalidOperationException("종료해야 할 프로세스: " + String.Join(",", found.ToArray()));
        }

        private void PreflightFiles()
        {
            foreach (DirectFile f in manifest.DirectFiles)
            {
                string target = PackageManifest.SafeJoin(gameDir, f.RelativePath);
                if (!File.Exists(target))
                {
                    if (f.Role == "modified") throw new InvalidOperationException("패치에 필요한 대상 파일이 없습니다: " + f.RelativePath);
                    continue;
                }
            }
        }

        private InstallState BuildState(GameInfo game)
        {
            InstallState s = new InstallState { Status = "PREPARED", InstalledUtc = DateTime.UtcNow.ToString("o"), GameDir = gameDir, BuildId = game.BuildId, BackupId = Guid.NewGuid().ToString("N").Substring(0, 12), Invariants = CaptureInvariant() };
            Directory.CreateDirectory(stateRoot);
            string backupRoot = Path.Combine(stateRoot, "original", s.BackupId);
            foreach (DirectFile f in manifest.DirectFiles)
            {
                string live = PackageManifest.SafeJoin(gameDir, f.RelativePath);
                bool existed = File.Exists(live);
                DirectState d = new DirectState { RelativePath = f.RelativePath, Action = existed ? "modified" : "created", BeforeSha = "ABSENT", BeforeBytes = 0, AfterSha = f.Sha256, AfterBytes = f.Bytes };
                if (existed)
                {
                    d.BeforeSha = FileOps.Sha256(live);
                    d.BeforeBytes = new FileInfo(live).Length;
                    string backup = PackageManifest.SafeJoin(backupRoot, f.RelativePath);
                    if (File.Exists(backup)) PackageManifest.RequireFile(backup, d.BeforeBytes, d.BeforeSha, "기존 backup");
                    else FileOps.CopyNewExact(live, backup, d.BeforeSha);
                }
                s.Files.Add(d);
            }
            return s;
        }

        private void ApplyFiles(InstallState state)
        {
            Dictionary<string, DirectFile> table = manifest.DirectFiles.ToDictionary(x => x.RelativePath, StringComparer.OrdinalIgnoreCase);
            foreach (DirectState d in state.Files)
            {
                DirectFile f = table[d.RelativePath];
                string target = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                if (d.Action == "modified") FileOps.ReplaceExact(manifest.DirectSource(f), target, d.AfterSha);
                else FileOps.CopyNewExact(manifest.DirectSource(f), target, d.AfterSha);
            }
        }

        private void Rollback(InstallState state)
        {
            string backupRoot = String.IsNullOrWhiteSpace(state.BackupId) ? Path.Combine(stateRoot, "original") : Path.Combine(stateRoot, "original", state.BackupId);
            foreach (DirectState d in state.Files.AsEnumerable().Reverse())
            {
                string live = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                if (d.Action == "modified")
                {
                    string backup = PackageManifest.SafeJoin(backupRoot, d.RelativePath);
                    PackageManifest.RequireFile(backup, d.BeforeBytes, d.BeforeSha, "복구 원본");
                    if (File.Exists(live) && FileOps.Sha256(live) != d.AfterSha && FileOps.Sha256(live) != d.BeforeSha) throw new InvalidOperationException("변경된 설치 파일은 덮어쓰지 않습니다: " + d.RelativePath);
                    if (!File.Exists(live) || FileOps.Sha256(live) != d.BeforeSha) FileOps.ReplaceExact(backup, live, d.BeforeSha);
                }
                else if (File.Exists(live))
                {
                    if (FileOps.Sha256(live) != d.AfterSha) throw new InvalidOperationException("변경된 생성 파일은 삭제하지 않습니다: " + d.RelativePath);
                    File.Delete(live);
                }
            }
        }

        private void ValidateInstalled(InstallState state)
        {
            if (state.Files.Count != manifest.DirectFiles.Count) throw new InvalidOperationException("설치 상태 계약 불일치");
            foreach (DirectState d in state.Files) PackageManifest.RequireFile(PackageManifest.SafeJoin(gameDir, d.RelativePath), d.AfterBytes, d.AfterSha, "설치 파일");
        }

        private void ValidateRestored(InstallState state)
        {
            foreach (DirectState d in state.Files)
            {
                string p = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                if (d.Action == "modified") PackageManifest.RequireFile(p, d.BeforeBytes, d.BeforeSha, "복구 파일");
                else if (File.Exists(p)) throw new InvalidOperationException("생성 파일 잔류: " + d.RelativePath);
            }
        }

        private InvariantState CaptureInvariant()
        {
            string physics = Path.Combine(gameDir, "Pakfiles", "PHYSICSPERSISTENT.bff");
            return new InvariantState {
                BootflowSha = "IGNORED", PhysicsSha = "IGNORED",
                PhysicsMarker = File.Exists(physics + "-remove"), VehicleFiles = -1, VehicleTreeSha = "IGNORED",
                TrackFiles = -1, TrackTreeSha = "IGNORED"
            };
        }

        private string DetectState()
        {
            InstallState s = LoadState();
            if (s != null && s.Status == "INSTALLED")
            {
                try { ValidateInstalled(s); return "INSTALLED_EXACT"; } catch { return "PARTIAL_OR_DAMAGED"; }
            }
            if (s != null && s.Status == "PREPARED") return "PARTIAL_OR_DAMAGED";
            if (s != null && s.Status == "RESTORED") return "RESTORED_EXACT";
            return "NOT_INSTALLED";
        }

        private PreviousInstallInfo FindPreviousInstalled()
        {
            string root = Path.Combine(gameDir, "Backup", "AMS2-Korean");
            if (!Directory.Exists(root)) return null;
            List<PreviousInstallInfo> candidates = new List<PreviousInstallInfo>();
            foreach (string directory in Directory.GetDirectories(root, "AMS2-KR-BETA-*", SearchOption.TopDirectoryOnly))
            {
                string packageId = Path.GetFileName(directory);
                if (packageId.Equals(PackageManifest.PackageId, StringComparison.OrdinalIgnoreCase)) continue;
                string statePath = Path.Combine(directory, "install-state.tsv");
                if (!File.Exists(statePath)) continue;
                try
                {
                    Dictionary<string, string> values = ReadMap(statePath);
                    if (!values.ContainsKey("status") || values["status"] != "INSTALLED") continue;
                    DateTime installed;
                    if (!values.ContainsKey("installed_utc") || !DateTime.TryParse(values["installed_utc"], CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out installed))
                        installed = File.GetLastWriteTimeUtc(statePath);
                    string version = packageId.Substring("AMS2-KR-BETA-".Length);
                    version = Regex.Replace(version, "-PRETENDARD$", "", RegexOptions.IgnoreCase);
                    version = Regex.Replace(version, "-HOTFIX$", " Hotfix", RegexOptions.IgnoreCase);
                    candidates.Add(new PreviousInstallInfo { PackageId = packageId, Version = version, InstalledUtc = installed.ToUniversalTime() });
                }
                catch { }
            }
            return candidates.OrderByDescending(item => item.InstalledUtc).FirstOrDefault();
        }

        private void SaveState(InstallState state, string status)
        {
            Directory.CreateDirectory(stateRoot);
            state.Status = status;
            StringBuilder head = new StringBuilder();
            head.AppendLine("status\t" + status);
            head.AppendLine("installed_utc\t" + state.InstalledUtc);
            head.AppendLine("game_dir\t" + state.GameDir);
            head.AppendLine("buildid\t" + state.BuildId);
            head.AppendLine("backup_id\t" + state.BackupId);
            FileOps.WriteTextAtomic(Path.Combine(stateRoot, "install-state.tsv"), head.ToString());
            StringBuilder files = new StringBuilder("relative_path\taction\tbefore_bytes\tbefore_sha256\tafter_bytes\tafter_sha256\n");
            foreach (DirectState d in state.Files) files.Append(d.RelativePath).Append('\t').Append(d.Action).Append('\t').Append(d.BeforeBytes).Append('\t').Append(d.BeforeSha).Append('\t').Append(d.AfterBytes).Append('\t').Append(d.AfterSha).AppendLine();
            FileOps.WriteTextAtomic(Path.Combine(stateRoot, "files.tsv"), files.ToString());
            InvariantState i = state.Invariants;
            StringBuilder inv = new StringBuilder();
            inv.AppendLine("bootflow_sha256\t" + i.BootflowSha);
            inv.AppendLine("physicspersistent_sha256\t" + i.PhysicsSha);
            inv.AppendLine("physicspersistent_remove_marker\t" + (i.PhysicsMarker ? "1" : "0"));
            inv.AppendLine("vehicle_files\t" + i.VehicleFiles);
            inv.AppendLine("vehicle_tree_sha256\t" + i.VehicleTreeSha);
            inv.AppendLine("track_files\t" + i.TrackFiles);
            inv.AppendLine("track_tree_sha256\t" + i.TrackTreeSha);
            FileOps.WriteTextAtomic(Path.Combine(stateRoot, "invariants.tsv"), inv.ToString());
        }

        private InstallState LoadState()
        {
            string headPath = Path.Combine(stateRoot, "install-state.tsv");
            string filesPath = Path.Combine(stateRoot, "files.tsv");
            string invPath = Path.Combine(stateRoot, "invariants.tsv");
            if (!File.Exists(headPath)) return null;
            if (!File.Exists(filesPath) || !File.Exists(invPath)) throw new InvalidOperationException("설치 상태 파일이 불완전합니다.");
            Dictionary<string, string> h = ReadMap(headPath);
            Dictionary<string, string> v = ReadMap(invPath);
            InstallState s = new InstallState { Status = h["status"], InstalledUtc = h["installed_utc"], GameDir = h["game_dir"], BuildId = h["buildid"], BackupId = h.ContainsKey("backup_id") ? h["backup_id"] : "" };
            s.Invariants = new InvariantState {
                BootflowSha = v["bootflow_sha256"], PhysicsSha = v["physicspersistent_sha256"], PhysicsMarker = v["physicspersistent_remove_marker"] == "1",
                VehicleFiles = Int32.Parse(v["vehicle_files"], CultureInfo.InvariantCulture), VehicleTreeSha = v["vehicle_tree_sha256"],
                TrackFiles = Int32.Parse(v["track_files"], CultureInfo.InvariantCulture), TrackTreeSha = v["track_tree_sha256"]
            };
            foreach (string line in File.ReadAllLines(filesPath, Encoding.UTF8).Skip(1))
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                string[] p = line.Split('\t');
                if (p.Length != 6) throw new InvalidOperationException("files.tsv 형식 오류");
                s.Files.Add(new DirectState { RelativePath = PackageManifest.NormalizeRelative(p[0]), Action = p[1], BeforeBytes = Int64.Parse(p[2], CultureInfo.InvariantCulture), BeforeSha = p[3], AfterBytes = Int64.Parse(p[4], CultureInfo.InvariantCulture), AfterSha = PackageManifest.NormalizeHash(p[5]) });
            }
            return s;
        }

        private static Dictionary<string, string> ReadMap(string path)
        {
            Dictionary<string, string> d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string line in File.ReadAllLines(path, Encoding.UTF8)) { string[] p = line.Split(new[] { '\t' }, 2); if (p.Length == 2) d[p[0]] = p[1]; }
            return d;
        }

        private string SaveLog()
        {
            Directory.CreateDirectory(stateRoot);
            string path = Path.Combine(stateRoot, "logs", DateTime.UtcNow.ToString("yyyyMMddTHHmmss.fffZ") + ".log");
            FileOps.WriteTextAtomic(path, log.ToString());
            FileOps.WriteTextAtomic(Path.Combine(stateRoot, "events.log"), log.ToString());
            return path;
        }

        private static OperationResult Ok(string status, string message, string path) { return new OperationResult { Success = true, Status = status, Message = message, LogPath = path }; }
        private static OperationResult Fail(string status, string message) { return new OperationResult { Success = false, Status = status, Message = message }; }
    }
}
