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
        public string PreparedSource, PreparedSha;
        public string PreparedBeforeSha;
        public long PreparedBytes;
    }

    internal sealed class PackageManifest
    {
        public const string PackageId = "AMS2-KR-BETA-0.88-PRETENDARD";
        public const string Version = "Open Beta 0.88";
        public const string AppId = "1066890";
        public const string BuildId = "25271800";
        public const string Branch = "public";
        public const string StockBootflowSha256 = "806BE47D41676BA56FD986109459AFD9C0C8E0F19B3717516A6BF9E0E5FB790F";
        public const string StockPhysicsSha256 = "39B720D1DC4CE529AC06AE10D0CF756E602ABD97772C5A24D7F31065C289C434";
        public const string IgphaseHudRelativePath = "Pakfiles\\IGPHASEHUD.bff";
        public const string KnownStockIgphaseHudSha256 = "0F4EC40436B7AD92988C959996A66FBE05C45421C6EEA18D6B4843D2D8004DFB";
        public const string KnownLegacyPatchedIgphaseHudSha256 = "D1618BB1F6E09F53E8BB86F4A163C2934B91814F5F326670381C5496B3D7C398";
        public const long BffPatcherBytes = 72352297;
        public const string BffPatcherSha256 = "252AF942BB9F4268616E4F45D1D18A4B2D40778413ABE1953EB3406CB0B09F05";

        public string ReleaseRoot;
        public List<DirectFile> DirectFiles = new List<DirectFile>();
        public ErsArchivePatch Ers = new ErsArchivePatch(false);
        private bool legacyBuild;
        private readonly HashSet<string> alternateFiles = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        public static PackageManifest Load(string releaseRoot, string tableName = "direct-files.tsv")
        {
            PackageManifest m = new PackageManifest();
            m.ReleaseRoot = Path.GetFullPath(releaseRoot);
            string table = Path.Combine(m.ReleaseRoot, "manifest", tableName);
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

        public void SelectBuild(string build)
        {
            legacyBuild = build == "24132163";
            DirectFiles = Load(ReleaseRoot, legacyBuild ? "direct-files-24132163.tsv" : "direct-files.tsv").DirectFiles;
            alternateFiles.Clear();
            if (legacyBuild)
                foreach (string path in GameUpdateCompatibility.ForBuild(build).menus.Keys) alternateFiles.Add(path.Replace('/', '\\'));
            Ers = new ErsArchivePatch(legacyBuild);
        }

        public string DirectSource(DirectFile f)
        {
            if (!String.IsNullOrEmpty(f.PreparedSource)) return f.PreparedSource;
            return SafeJoin(Path.Combine(ReleaseRoot, "payload", alternateFiles.Contains(f.RelativePath) ? "24132163" : "direct"), f.RelativePath);
        }

        public string DirectSha(DirectFile f) { return String.IsNullOrEmpty(f.PreparedSha) ? f.Sha256 : f.PreparedSha; }
        public long DirectBytes(DirectFile f) { return String.IsNullOrEmpty(f.PreparedSha) ? f.Bytes : f.PreparedBytes; }
        public string BffPatcherSource { get { return Path.Combine(ReleaseRoot, "runtime", "AMS2.DynamicBffPatcher.exe"); } }

        public void ValidateAll()
        {
            foreach (DirectFile f in DirectFiles) RequireFile(DirectSource(f), f.Bytes, f.Sha256, "payload");
            RequireFile(BffPatcherSource, BffPatcherBytes, BffPatcherSha256, "IGPHASEHUD dynamic patcher");
            Ers.ValidatePackage(ReleaseRoot);
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
        internal static string Sha256TextBytes(byte[] bytes)
        { using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", ""); }
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
            string tmp = TemporarySibling(target);
            try
            {
                File.Copy(source, tmp, false);
                File.SetAttributes(tmp, File.GetAttributes(tmp) & ~FileAttributes.ReadOnly);
                if (Sha256(tmp) != expected) throw new InvalidOperationException("임시 복사 hash 불일치");
                File.Move(tmp, target);
            }
            finally { if (File.Exists(tmp)) File.Delete(tmp); }
        }

        private static string TemporarySibling(string target)
        {
            return Path.Combine(Path.GetDirectoryName(target), Guid.NewGuid().ToString("N") + ".tmp");
        }

        public static void ReplaceExact(string source, string target, string expected)
        {
            EnsureDirectoryFor(target);
            string tmp = TemporarySibling(target);
            try
            {
                File.Copy(source, tmp, false);
                File.SetAttributes(tmp, File.GetAttributes(tmp) & ~FileAttributes.ReadOnly);
                if (Sha256(tmp) != expected) throw new InvalidOperationException("임시 교체 hash 불일치");
                if (File.Exists(target)) File.Replace(tmp, target, null); else File.Move(tmp, target);
                if (Sha256(target) != expected) throw new InvalidOperationException("교체 후 hash 불일치");
            }
            finally { if (File.Exists(tmp)) File.Delete(tmp); }
        }

        public static void WriteTextAtomic(string target, string text)
        {
            EnsureDirectoryFor(target);
            string tmp = TemporarySibling(target);
            try
            {
                File.WriteAllText(tmp, text, new UTF8Encoding(false));
                if (File.Exists(target)) File.Replace(tmp, target, null); else File.Move(tmp, target);
            }
            finally { if (File.Exists(tmp)) File.Delete(tmp); }
        }

        public static void ApplyIgphaseHudCandidate(string candidatePath, string target, long expectedBytes, string expectedSha)
        {
            PackageManifest.RequireFile(candidatePath, expectedBytes, expectedSha, "dynamic IGPHASEHUD candidate");
            ReplaceExact(candidatePath, target, expectedSha);
            PackageManifest.RequireFile(target, expectedBytes, expectedSha, "dynamic IGPHASEHUD live");
        }

        public static string RunBffTool(string toolPath, string mode, string gameDir, string pakPath, string outputPath, string reportPath)
        {
            var arguments = new List<string> { mode, gameDir, pakPath };
            if (mode.StartsWith("patch", StringComparison.Ordinal)) arguments.Add(outputPath);
            arguments.Add(reportPath);
            var start = new ProcessStartInfo(toolPath, String.Join(" ", arguments.Select(QuoteArgument)))
            {
                WorkingDirectory = Path.GetDirectoryName(toolPath),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            using (Process process = Process.Start(start))
            {
                string stdout = process.StandardOutput.ReadToEnd();
                string stderr = process.StandardError.ReadToEnd();
                if (!process.WaitForExit(120000))
                {
                    try { process.Kill(); } catch { }
                    throw new InvalidOperationException("동적 BFF 적용기 시간이 초과되었습니다: " + mode);
                }
                if (process.ExitCode != 0)
                    throw new InvalidOperationException("BFF 구조 검증 실패 (" + mode + "): " + (String.IsNullOrWhiteSpace(stderr) ? stdout : stderr).Trim());
                if (!File.Exists(reportPath)) throw new InvalidOperationException("BFF 검증 보고서가 생성되지 않았습니다: " + mode);
                return stdout;
            }
        }

        private static string QuoteArgument(string value)
        {
            return "\"" + (value ?? "").Replace("\"", "\\\"") + "\"";
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
        public bool InstallBeforeExists;
        public string InstallBeforeSha;
        public long InstallBeforeBytes;
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
        public string RestorePolicy = "INHERITED_ORIGINAL";
        public string Status;
        public string InstalledUtc;
        public string GameDir;
        public string BuildId;
        public string BackupId;
        public string PredecessorPackageId;
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
        public string StateRoot;
        public InstallState State;
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

        internal static void RefreshShell()
        {
            SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
        }

        public static void Apply(string gameDir, string stateRoot, ShortcutOptions options, Action<string> log, string previousStateRoot = null)
        {
            RemoveOwned(stateRoot, log);
            string launcher = Path.Combine(gameDir, "AMS2 Korean Launcher.exe");
            string vrLauncher = Path.Combine(gameDir, "AMS2 Korean VR Launcher.exe");
            PackageManifest.RequireFile(launcher, new FileInfo(launcher).Length, FileOps.Sha256(launcher), "한국어 런처");
            PackageManifest.RequireFile(vrLauncher, new FileInfo(vrLauncher).Length, FileOps.Sha256(vrLauncher), "한국어 VR 런처");
            List<string[]> created = new List<string[]>();
            AdoptHistoricalOwnership(stateRoot, previousStateRoot, options, created, log);
            if (options != null && options.Desktop) CreatePair("DESKTOP", Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), launcher, vrLauncher, created, log);
            if (options != null && options.StartMenu) CreatePair("START_MENU", Environment.GetFolderPath(Environment.SpecialFolder.Programs), launcher, vrLauncher, created, log);
            if (options != null && options.Taskbar)
            {
                string pinned = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar");
                CreatePair("TASKBAR", pinned, launcher, vrLauncher, created, log);
                SHChangeNotify(0x08000000, 0, IntPtr.Zero, IntPtr.Zero);
            }
            if (created.Count == 0) return;
            StringBuilder state = new StringBuilder("kind\tpath\tsha256\r\n");
            foreach (string[] row in created) state.AppendLine(String.Join("\t", row));
            FileOps.WriteTextAtomic(Path.Combine(stateRoot, "shortcuts.tsv"), state.ToString());
        }

        private static void AdoptHistoricalOwnership(string stateRoot, string previousStateRoot, ShortcutOptions options, List<string[]> owned, Action<string> log)
        {
            List<string> roots = new List<string>();
            if (!String.IsNullOrWhiteSpace(previousStateRoot)) roots.Add(previousStateRoot);
            string packageRoot = Directory.GetParent(stateRoot) == null ? null : Directory.GetParent(stateRoot).FullName;
            if (!String.IsNullOrWhiteSpace(packageRoot) && Directory.Exists(packageRoot))
            {
                foreach (string root in Directory.GetDirectories(packageRoot))
                    if (!String.Equals(Path.GetFullPath(root).TrimEnd('\\'), Path.GetFullPath(stateRoot).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase)) roots.Add(root);
            }
            HashSet<string> seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string root in roots.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase))
            {
                string statePath = Path.Combine(root, "shortcuts.tsv");
                if (!File.Exists(statePath)) continue;
                foreach (string line in File.ReadAllLines(statePath, Encoding.UTF8).Skip(1))
                {
                    if (String.IsNullOrWhiteSpace(line)) continue;
                    string[] row = line.Split('\t');
                    if (row.Length != 3 || !File.Exists(row[1]) || FileOps.Sha256(row[1]) != row[2] || !seen.Add(row[1])) continue;
                    bool keep = options == null || (row[0].StartsWith("DESKTOP", StringComparison.OrdinalIgnoreCase) && options.Desktop)
                        || (row[0].StartsWith("START_MENU", StringComparison.OrdinalIgnoreCase) && options.StartMenu)
                        || (row[0].StartsWith("TASKBAR", StringComparison.OrdinalIgnoreCase) && options.Taskbar);
                    if (keep)
                    {
                        owned.Add(row);
                        if (log != null) log("이전 버전 바로가기 소유권 승계: " + row[1]);
                    }
                    else
                    {
                        File.Delete(row[1]);
                        if (log != null) log("선택 해제된 이전 버전 바로가기 제거: " + row[1]);
                    }
                }
            }
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

    internal sealed partial class BetaEngine
    {
        private readonly PackageManifest manifest;
        private readonly Action<string> logCallback;
        private readonly bool mockMode;
        private readonly StringBuilder log = new StringBuilder();
        private string gameDir;
        private string stateRoot;
        private string igphaseHudCandidatePath;
        private string igphaseHudPatchReportPath;
        private string ersCandidatePath;
        private string ersOriginalPath;
        private string candidateRoot;
        private string igphaseBefore, ersBefore;
        private readonly List<string> preflightWarnings = new List<string>();

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
                if (GameUpdateCompatibility.NeedsRepair(gameDir))
                    return Ok("GAME_UPDATE_DETECTED", "게임 업데이트 또는 파일 변경이 감지되었습니다. 설치를 누르면 호환성을 확인하고 필요한 한글 연결을 다시 적용합니다.", null);
                string detected = DetectState();
                if (detected == "UPDATE_AVAILABLE")
                {
                    PreviousInstallInfo installed = FindPreviousInstalled();
                    return Ok("UPDATE_AVAILABLE", installed.Version + " 버전이 설치되어 있습니다. " + PackageManifest.Version + "로 업데이트가 필요합니다.", null);
                }
                if (detected == "STOCK_ENGLISH" || detected == "NOT_INSTALLED" || detected == "RESTORED_EXACT" || detected == "ROLLED_BACK")
                {
                    PreviousInstallInfo previous = FindPreviousInstalled();
                    if (previous != null)
                        return Ok("UPDATE_AVAILABLE", previous.Version + " 버전이 설치되어 있습니다. " + PackageManifest.Version + "로 업데이트가 필요합니다.", null);
                }
                if (detected == "STOCK_ENGLISH") return Ok(detected, "한국어 패치 미설치 상태를 확인했습니다.", null);
                if (detected == "RESTORED_EXACT") return Ok(detected, "제거 완료 및 설치 직전 상태 복원 검증 완료", null);
                return Ok(detected, "상태 확인 완료: " + detected, null);
            }
            catch (Exception e) { return Fail("CHECK_FAILED", e.Message); }
        }

        public OperationResult Install(GameInfo game) { return Install(game, null); }

        public OperationResult Install(GameInfo game, ShortcutOptions shortcuts)
        {
            InstallState state = null;
            UpgradeTransaction transaction = null;
            System.Threading.Mutex operation = null;
            bool operationOwned = false;
            bool recovering = false, recovered = false;
            try
            {
                Prepare(game);
                ValidateGame(game);
                manifest.ValidateAll();
                GuardProcesses();
                operation = new System.Threading.Mutex(false, @"Local\AMS2-Korean-GameUpdate-" + FileOps.Sha256Text(Path.GetFullPath(gameDir).ToUpperInvariant()).Substring(0, 24));
                try { operationOwned = operation.WaitOne(0); } catch (System.Threading.AbandonedMutexException) { operationOwned = true; }
                if (!operationOwned) throw new InvalidOperationException("다른 설치 또는 재적용 작업이 진행 중입니다.");
                recovering = true;
                recovered = UpgradeTransaction.Recover(gameDir, Log);
                recovered = GameUpdateCompatibility.RecoverInterruptedOnly(gameDir, Log) || recovered;
                recovering = false;
                string detected = DetectState();
                if (detected == "INSTALLED_EXACT")
                {
                    // Also compare the package: a newer build of the installer can
                    // have the same display version while shipping different files.
                    if (manifest.DirectFiles.All(f => f.Role != "created" || FileOps.Sha256(PackageManifest.SafeJoin(gameDir, f.RelativePath)) == f.Sha256))
                    {
                        if (shortcuts != null) ShortcutManager.Apply(gameDir, stateRoot, shortcuts, Log);
                        return Ok(detected, "이미 정확히 설치되어 있습니다.", SaveLog());
                    }
                }
                PreviousInstallInfo previous = FindPreviousInstalled();
                upgradeHistory = LoadHistoryStates();
                string cmToken = ContentManagerOverlay.StateToken(gameDir);
                PreflightFiles();
                PlanRetiredFiles();
                state = BuildState(game, previous);
                var targets = state.Files.ToDictionary(x => x.RelativePath, x => x.AfterSha, StringComparer.OrdinalIgnoreCase);
                foreach (RetiredFile retired in retiredFiles) targets[retired.Path] = retired.After;
                foreach (string root in UpgradeOwnership.Roots(gameDir).Concat(new[] { stateRoot }).Distinct(StringComparer.OrdinalIgnoreCase))
                    foreach (string name in new[] { "install-state.tsv", "files.tsv", "invariants.tsv", "shortcuts.tsv" })
                        targets[Path.Combine(root, name).Substring(gameDir.Length + 1)] = "METADATA";
                transaction = UpgradeTransaction.Begin(gameDir, targets);
                if (cmToken != ContentManagerOverlay.StateToken(gameDir)) throw new IOException("검사 중 CM 상태가 변경되었습니다.");
                SaveState(state, "PREPARED");
                ApplyFiles(state);
                ApplyRetiredFiles();
                ValidateInstalled(state);
                PersistRuntimeSupport();
                SaveState(state, "INSTALLED");
                MarkPreviousInstallationsSuperseded();
                transaction.Commit(); transaction = null;
                try { ShortcutManager.Apply(gameDir, stateRoot, shortcuts, Log, previous == null ? null : previous.StateRoot); }
                catch (Exception shortcut) { Log("경고: 패치는 설치되었지만 바로가기를 완전히 갱신하지 못했습니다: " + shortcut.Message); }
                Log("설치 완료: AMS2CM/dotnet/Generated Bootfiles/physics post-processing 0");
                string path = "";
                try { path = SaveLog(); }
                catch (Exception logging) { Log("설치는 완료되었지만 로그 저장에 실패했습니다: " + logging.Message); }
                bool warning = preflightWarnings.Count > 0;
                string warningText = warning ? " " + String.Join(" / ", preflightWarnings.Take(4)) + " 핵심 한글 자산은 적용되었습니다." : "";
                if (previous != null)
                    return Ok(warning ? "UPDATED_WITH_WARNINGS" : "UPDATED_EXACT", previous.Version + "에서 " + PackageManifest.Version + "로 업데이트했습니다." + warningText + " 반드시 생성한 바로가기 아이콘 또는 'AMS2 Korean Launcher.exe'로 실행하십시오.", path);
                return Ok(warning ? "INSTALLED_WITH_WARNINGS" : "INSTALLED_EXACT", PackageManifest.Version + " 설치 완료." + warningText + " 반드시 생성한 바로가기 아이콘 또는 'AMS2 Korean Launcher.exe'로 실행하십시오.", path);
            }
            catch (Exception e)
            {
                Log("설치 실패: " + e.Message);
                if (recovering) return Fail("RESTORE_FAILED", "이전 중단 작업 복구 실패: " + e.Message + ". 복구 기록을 보존했습니다.");
                bool rollbackAttempted = false;
                Exception rollbackFailure = null;
                try
                {
                    if (transaction != null)
                    {
                        rollbackAttempted = true;
                        UpgradeTransaction.Recover(gameDir, Log);
                    }
                }
                catch (Exception rollback) { rollbackFailure = rollback; Log("자동 롤백 실패: " + rollback.Message); }
                if (rollbackFailure != null) return Fail("RESTORE_FAILED", e.Message + " (자동 롤백 실패: " + rollbackFailure.Message + ")");
                return Fail("INSTALL_FAILED", e.Message + (recovered ? " (이전 중단 작업은 먼저 복구했습니다.)" : "") + (rollbackAttempted ? " (업그레이드 전 파일·설치 기록 복구 완료)" : " (후보 검증 단계에서 중단; 새 후보의 게임 파일 반영 없음)"));
            }
            finally { CleanupIgphaseHudCandidate(); if (operationOwned) operation.ReleaseMutex(); if (operation != null) operation.Dispose(); }
        }

        public OperationResult Uninstall(GameInfo game)
        {
            try
            {
                Prepare(game);
                ValidateGame(game);
                GuardProcesses();
                if (ContentManagerOverlay.Owned(gameDir).Count > 0) throw new InvalidOperationException("CM에서 모드를 비활성화한 후 한글패치를 제거해주세요. 모드 파일과 백업을 보호하기 위해 제거를 중단했습니다.");
                GameUpdateCompatibility.Ensure(gameDir, false, Log);
                InstallState state = LoadState();
                if (state == null || (state.Status != "INSTALLED" && state.Status != "PREPARED")) throw new InvalidOperationException("복구할 활성 설치 상태가 없습니다.");
                ValidateBackupContract(state);
                foreach (DirectState d in state.Files) ValidateRestorableFile(state, d);
                ShortcutManager.RemoveOwned(stateRoot, Log);
                RestoreOriginal(state);
                ValidateRestored(state);
                SaveState(state, "RESTORED");
                Log("제거 완료: 패치 생성 파일 제거 및 설치 직전 파일 SHA 검증 완료");
                return Ok("RESTORED_EXACT", "설치 직전 상태 복원 완료. 제거 완료와 원복 검증 완료를 모두 확인했습니다.", SaveLog());
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
                GameUpdateCompatibility.CompatibilityOutcome compatibility = GameUpdateCompatibility.Ensure(gameDir, true, Log);
                InstallState state = LoadState();
                if (state == null || state.Status != "INSTALLED") throw new InvalidOperationException("한국어 패치가 정확히 설치되지 않았습니다.");
                ValidateInstalled(state);
                GameLauncher.StartVerified(gameDir, false);
                Log("한국어 실행: Steam " + GameLauncher.Arguments(false));
                return Ok("LAUNCHED_KOREAN", (compatibility.ShouldNotify ? compatibility.Notice + "\r\n" : "") + "Steam에 한국어 모드 실행을 요청했습니다. 실제 게임 내 한글 표시는 게임 화면에서 확인해주세요.", SaveLog());
            }
            catch (Exception e) { return Fail(e.Message.StartsWith("Steam 실행 요청 실패", StringComparison.Ordinal) ? "STEAM_LAUNCH_FAILED" : "LAUNCH_FAILED", e.Message); }
        }

        public OperationResult Diagnose(GameInfo game, string outputZip)
        {
            try
            {
                Prepare(game);
                ValidateGame(game);
                string temp = Path.Combine(Path.GetTempPath(), "AMS2-KR-BETA07-DIAG-" + Guid.NewGuid().ToString("N"));
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
                    string bff = PackageManifest.SafeJoin(gameDir, PackageManifest.IgphaseHudRelativePath);
                    string bffRoute = "MISSING";
                    if (File.Exists(bff))
                    {
                        string inspectReport = Path.Combine(temp, "IGPHASEHUD-inspect.json");
                        string inspectOutput = FileOps.RunBffTool(manifest.BffPatcherSource, "inspect", gameDir, bff, null, inspectReport);
                        bffRoute = ParseRoute(inspectOutput);
                    }
                    files.Append(PackageManifest.IgphaseHudRelativePath).Append('\t').Append(File.Exists(bff) ? "1" : "0").Append('\t')
                        .Append(File.Exists(bff) ? new FileInfo(bff).Length.ToString(CultureInfo.InvariantCulture) : "0").Append('\t')
                        .Append(File.Exists(bff) ? FileOps.Sha256(bff) : "").Append('\t').Append("DYNAMIC_PROFILE_NAME_ROUTE").AppendLine();
                    files.Append("IGPHASEHUD ProfileName route\t1\t0\t").Append(bffRoute).Append('\t').Append("GUI\\kr13_driver_name_semibold.bfont").AppendLine();
                    files.Append("known stock IGPHASEHUD SHA\t1\t0\t").Append(PackageManifest.KnownStockIgphaseHudSha256).Append('\t').Append("diagnostic only").AppendLine();
                    files.Append("known legacy patched IGPHASEHUD SHA\t1\t0\t").Append(PackageManifest.KnownLegacyPatchedIgphaseHudSha256).Append('\t').Append("diagnostic only").AppendLine();
                    string hud = PackageManifest.SafeJoin(gameDir, ErsArchivePatch.RelativePath);
                    files.Append(ErsArchivePatch.RelativePath).Append('\t').Append(File.Exists(hud) ? "1" : "0").Append('\t')
                        .Append(File.Exists(hud) ? new FileInfo(hud).Length.ToString(CultureInfo.InvariantCulture) : "0").Append('\t')
                        .Append(File.Exists(hud) ? FileOps.Sha256(hud) : "").Append('\t').Append(manifest.Ers.PatchedSha).AppendLine();
                    File.WriteAllText(Path.Combine(temp, "payload-hashes.tsv"), files.ToString(), new UTF8Encoding(false));
                    if (Directory.Exists(stateRoot)) foreach (string n in new[] { "install-state.tsv", "files.tsv", "invariants.tsv", "events.log", "shortcuts.tsv" })
                    {
                        string source = Path.Combine(stateRoot, n);
                        if (File.Exists(source)) File.Copy(source, Path.Combine(temp, n));
                    }
                    string logRoot = Path.Combine(stateRoot, "logs");
                    if (Directory.Exists(logRoot))
                    {
                        Directory.CreateDirectory(Path.Combine(temp, "logs"));
                        foreach (string recent in Directory.GetFiles(logRoot, "*.log").OrderByDescending(File.GetLastWriteTimeUtc).Take(10))
                            File.Copy(recent, Path.Combine(temp, "logs", Path.GetFileName(recent)));
                    }
                    string repairRoot = Path.Combine(stateRoot, "game-updates");
                    if (Directory.Exists(repairRoot))
                        foreach (string folder in Directory.GetDirectories(repairRoot).OrderByDescending(Directory.GetLastWriteTimeUtc).Take(5))
                            foreach (string name in new[] { "before.tsv", "result.txt" })
                            {
                                string source = Path.Combine(folder, name);
                                if (!File.Exists(source)) continue;
                                string destination = Path.Combine(temp, "game-updates", Path.GetFileName(folder), name);
                                FileOps.EnsureDirectoryFor(destination); File.Copy(source, destination);
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
            manifest.SelectBuild(game.BuildId);
        }

        private void ValidateGame(GameInfo game)
        {
            if (!File.Exists(Path.Combine(gameDir, "AMS2.exe")) || !File.Exists(Path.Combine(gameDir, "AMS2AVX.exe"))) throw new InvalidOperationException("게임 실행 파일 검증 실패");
            if (GameUpdateCompatibility.SupportedBuild(game.BuildId)) Log("검증 이력이 있는 게임 빌드 " + game.BuildId + "의 패치 정책을 선택했습니다.");
            else Log("참고: 미검증 게임 빌드 " + game.BuildId + "입니다. 빌드 번호 대신 전체 대상 파일의 실제 구조를 검사합니다.");
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
            preflightWarnings.Clear();
            var failures = new List<string>();
            foreach (DirectFile f in manifest.DirectFiles)
            {
                f.PreparedSource = null; f.PreparedSha = null; f.PreparedBytes = 0;
                string target = PackageManifest.SafeJoin(gameDir, f.RelativePath);
                if (!File.Exists(target))
                {
                    if (f.Role == "modified") failures.Add(f.RelativePath + " | 필수 대상 파일 누락");
                    continue;
                }
            }
            if (failures.Count > 0) throw new InvalidOperationException("필수 한글 대상 파일을 확인하지 못했습니다.\r\n" + String.Join("\r\n", failures));
            string igphaseHud = PackageManifest.SafeJoin(gameDir, PackageManifest.IgphaseHudRelativePath);
            if (!File.Exists(igphaseHud) || new FileInfo(igphaseHud).Length == 0)
                throw new InvalidOperationException("IGPHASEHUD.bff가 없거나 비어 있습니다.");
            CleanupIgphaseHudCandidate();
            candidateRoot = Path.Combine(Path.GetTempPath(), "AMS2-KR-BETA087-BFF-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(candidateRoot);
            igphaseHudCandidatePath = Path.Combine(candidateRoot, "IGPHASEHUD.candidate.bff");
            igphaseHudPatchReportPath = Path.Combine(candidateRoot, "IGPHASEHUD.dynamic-patch.json");
            ersCandidatePath = Path.Combine(candidateRoot, "HUDDISPLAY.candidate.bff");
            ersOriginalPath = Path.Combine(candidateRoot, "HUDDISPLAY.original.bff");
            GameUpdateCompatibility.Rules rules = GameUpdateCompatibility.ForBuild(SteamLocator.FromGameDirectory(gameDir).BuildId);
            foreach (DirectFile f in manifest.DirectFiles.Where(x => x.Role == "modified" && x.RelativePath.EndsWith(".bgui", StringComparison.OrdinalIgnoreCase)))
            {
                string relative = f.RelativePath.Replace('\\', '/').ToLowerInvariant();
                try
                {
                    GameUpdateCompatibility.MenuRule rule;
                    if (!rules.menus.TryGetValue(relative, out rule)) throw new InvalidDataException("구조 기반 BGUI 규칙이 없습니다.");
                    byte[] source = File.ReadAllBytes(PackageManifest.SafeJoin(gameDir, f.RelativePath));
                    f.PreparedBeforeSha = FileOps.Sha256TextBytes(source);
                    byte[] candidate = PatchUpgradeMenu(f, source, rule);
                    string path = PackageManifest.SafeJoin(candidateRoot, "direct/" + f.RelativePath);
                    FileOps.EnsureDirectoryFor(path); File.WriteAllBytes(path, candidate);
                    f.PreparedSource = path; f.PreparedSha = FileOps.Sha256(path); f.PreparedBytes = candidate.LongLength;
                }
                catch (Exception error) { failures.Add(f.RelativePath + " | 구조 재적용 실패 | " + error.Message); }
            }
            HashSet<string> cmOwned = ContentManagerOverlay.Owned(gameDir);
            foreach (DirectFile f in manifest.DirectFiles.Where(x => x.Role == "created"))
            {
                string target = PackageManifest.SafeJoin(gameDir, f.RelativePath);
                string key = f.RelativePath.Replace('\\', '/').ToLowerInvariant();
                if (!File.Exists(target)) { f.PreparedBeforeSha = "ABSENT"; continue; }
                if ((!cmOwned.Contains(key) || FileOps.Sha256(target) == f.Sha256) && CanAdoptCreated(f, target)) continue;
                try
                {
                    byte[] candidate;
                    byte[] currentBytes = File.ReadAllBytes(target);
                    f.PreparedBeforeSha = FileOps.Sha256TextBytes(currentBytes);
                    if (!cmOwned.Contains(key) || !ContentManagerOverlay.TryPatchCurrent(key, currentBytes, out candidate))
                        throw new InvalidDataException("다른 모드가 소유한 생성 파일과 충돌합니다.");
                    string path = PackageManifest.SafeJoin(candidateRoot, "direct/" + f.RelativePath);
                    FileOps.EnsureDirectoryFor(path); File.WriteAllBytes(path, candidate);
                    f.PreparedSource = path; f.PreparedSha = FileOps.Sha256(path); f.PreparedBytes = candidate.LongLength;
                }
                catch (Exception error) { failures.Add(f.RelativePath + " | 기존 생성 파일 보존 실패 | " + error.Message); }
            }
            if (failures.Count > 0) throw new InvalidOperationException("필수 한글 파일 후보 생성에 실패했습니다.\r\n" + String.Join("\r\n", failures.Take(40)));
            try
            {
                igphaseBefore = FileOps.Sha256(igphaseHud);
                FileOps.RunBffTool(manifest.BffPatcherSource, "patch", gameDir, igphaseHud, igphaseHudCandidatePath, igphaseHudPatchReportPath);
                if (FileOps.Sha256(igphaseHud) != igphaseBefore) throw new IOException("후보 생성 중 IGPHASEHUD 동시 변경");
                if (!File.Exists(igphaseHudCandidatePath) || new FileInfo(igphaseHudCandidatePath).Length != new FileInfo(igphaseHud).Length) throw new InvalidOperationException("후보 크기 검증 실패");
                Log("IGPHASEHUD 구조 기반 후보 생성 PASS");
            }
            catch (Exception error) { igphaseHudCandidatePath = null; preflightWarnings.Add("Pakfiles\\IGPHASEHUD.bff | 부가 항목 생략 | " + error.Message); }
            try
            {
                string live = PackageManifest.SafeJoin(gameDir, ErsArchivePatch.RelativePath);
                ersBefore = FileOps.Sha256(live);
                FileOps.RunBffTool(manifest.BffPatcherSource, "patch-huddisplay", gameDir, live, ersCandidatePath, Path.Combine(candidateRoot, "HUDDISPLAY.dynamic-patch.json"));
                if (FileOps.Sha256(live) != ersBefore) throw new IOException("후보 생성 중 HUDDISPLAY 동시 변경");
                if (!File.Exists(ersCandidatePath) || new FileInfo(ersCandidatePath).Length != new FileInfo(live).Length) throw new InvalidOperationException("후보 크기 검증 실패");
                Log("HUDDISPLAY 구조 기반 후보 생성 PASS");
            }
            catch (Exception error) { ersCandidatePath = null; preflightWarnings.Add("Pakfiles\\HUDDISPLAY.bff | 부가 항목 생략 | " + error.Message); }
            foreach (string warning in preflightWarnings) Log("경고: " + warning);
        }

        private InstallState BuildState(GameInfo game, PreviousInstallInfo previous)
        {
            InstallState s = new InstallState {
                Status = "PREPARED", InstalledUtc = DateTime.UtcNow.ToString("o"), GameDir = gameDir,
                BuildId = game.BuildId, BackupId = Guid.NewGuid().ToString("N").Substring(0, 12),
                PredecessorPackageId = previous == null ? "" : previous.PackageId, Invariants = CaptureInvariant()
            };
            s.RestorePolicy = preservePreUpgradeBaseline ? "PRE_UPGRADE" : "INHERITED_ORIGINAL";
            Directory.CreateDirectory(stateRoot);
            List<PreviousInstallInfo> history = LoadHistoryStates();
            foreach (DirectFile f in manifest.DirectFiles)
            {
                DirectState d = CreateTransactionRecord(f.RelativePath, manifest.DirectSha(f), manifest.DirectBytes(f), s.BackupId);
                if (f.PreparedBeforeSha != null && f.PreparedBeforeSha != d.InstallBeforeSha) throw new IOException("후보 검사 후 파일 변경: " + f.RelativePath);
                ResolveCanonicalOriginal(d, f.Role == "created", f.AllowedBefore, history, s.BackupId);
                s.Files.Add(d);
            }
            if (!String.IsNullOrWhiteSpace(igphaseHudCandidatePath) && File.Exists(igphaseHudCandidatePath))
            {
                DirectState bff = CreateTransactionRecord(PackageManifest.IgphaseHudRelativePath, FileOps.Sha256(igphaseHudCandidatePath), new FileInfo(igphaseHudCandidatePath).Length, s.BackupId);
                if (bff.InstallBeforeSha != igphaseBefore) throw new IOException("후보 검사 후 IGPHASEHUD 변경");
                ResolveCanonicalOriginal(bff, false, Enumerable.Empty<string>(), history, s.BackupId); s.Files.Add(bff);
            }
            if (!String.IsNullOrWhiteSpace(ersCandidatePath) && File.Exists(ersCandidatePath))
            {
                DirectState ers = CreateTransactionRecord(ErsArchivePatch.RelativePath, FileOps.Sha256(ersCandidatePath), new FileInfo(ersCandidatePath).Length, s.BackupId);
                if (ers.InstallBeforeSha != ersBefore) throw new IOException("후보 검사 후 HUDDISPLAY 변경");
                ResolveCanonicalOriginal(ers, false, Enumerable.Empty<string>(), history, s.BackupId); s.Files.Add(ers);
            }
            ValidateBackupContract(s);
            return s;
        }

        private DirectState CreateTransactionRecord(string relativePath, string afterSha, long afterBytes, string backupId)
        {
            string live = PackageManifest.SafeJoin(gameDir, relativePath);
            DirectState d = new DirectState { RelativePath = relativePath, BeforeSha = "ABSENT", AfterSha = afterSha, AfterBytes = afterBytes };
            d.InstallBeforeExists = File.Exists(live);
            d.InstallBeforeSha = d.InstallBeforeExists ? FileOps.Sha256(live) : "ABSENT";
            d.InstallBeforeBytes = d.InstallBeforeExists ? new FileInfo(live).Length : 0;
            if (d.InstallBeforeExists)
            {
                string transaction = PackageManifest.SafeJoin(Path.Combine(stateRoot, "transaction", backupId), relativePath);
                FileOps.CopyNewExact(live, transaction, d.InstallBeforeSha);
            }
            return d;
        }

        private void ResolveCanonicalOriginal(DirectState target, bool stockIsAbsent, IEnumerable<string> stockHashes, List<PreviousInstallInfo> history, string backupId)
        {
            HashSet<string> accepted = new HashSet<string>(stockHashes ?? Enumerable.Empty<string>(), StringComparer.OrdinalIgnoreCase);
            if (preservePreUpgradeBaseline && target.InstallBeforeExists)
            {
                target.Action = "modified"; target.BeforeSha = target.InstallBeforeSha; target.BeforeBytes = target.InstallBeforeBytes;
                CopyCanonicalBackup(PackageManifest.SafeJoin(gameDir, target.RelativePath), target, backupId); return;
            }
            if (stockIsAbsent && UpgradeOwnership.Owns(target.RelativePath, target.InstallBeforeSha, target.InstallBeforeBytes, history)) accepted.Add(target.InstallBeforeSha);
            if (stockIsAbsent && !target.InstallBeforeExists)
            {
                target.Action = "created"; target.BeforeSha = "ABSENT"; target.BeforeBytes = 0; return;
            }
            // A matching prior installation owns its verified original, including unknown preinstall files.
            foreach (PreviousInstallInfo item in history.OrderByDescending(x => x.InstalledUtc))
            {
                DirectState old = item.State.Files.FirstOrDefault(x => x.RelativePath.Equals(target.RelativePath, StringComparison.OrdinalIgnoreCase));
                if (old == null || !(target.InstallBeforeSha.Equals(old.AfterSha, StringComparison.OrdinalIgnoreCase) ||
                    (target.InstallBeforeSha.Equals(target.AfterSha, StringComparison.OrdinalIgnoreCase) && accepted.Contains(old.AfterSha)))) continue;
                if (old.Action == "created" && old.BeforeSha == "ABSENT")
                {
                    target.Action = "created"; target.BeforeSha = "ABSENT"; target.BeforeBytes = 0; return;
                }
                if (old.Action == "modified")
                {
                    // The live file must match the recorded patch result above.
                    // An updated game file with different bytes never inherits this backup.
                    string source = PackageManifest.SafeJoin(Path.Combine(item.StateRoot, "original", item.State.BackupId), target.RelativePath);
                    PackageManifest.RequireFile(source, old.BeforeBytes, old.BeforeSha, "이전 버전 설치 전 백업");
                    target.Action = "modified"; target.BeforeSha = old.BeforeSha; target.BeforeBytes = old.BeforeBytes;
                    CopyCanonicalBackup(source, target, backupId);
                    return;
                }
            }
            if (!stockIsAbsent && target.InstallBeforeSha == target.AfterSha && accepted.Count == 1 && ErsArchivePatch.IsNewLooseLayout(target.RelativePath))
            {
                string recovered = Path.Combine(Path.GetDirectoryName(ersOriginalPath), Path.GetFileName(target.RelativePath));
                ErsArchivePatch.RestoreLooseOriginal(PackageManifest.SafeJoin(gameDir, target.RelativePath), recovered, accepted.Single());
                target.Action = "modified"; target.BeforeSha = accepted.Single(); target.BeforeBytes = new FileInfo(recovered).Length;
                CopyCanonicalBackup(recovered, target, backupId);
                return;
            }
            if (stockIsAbsent && target.InstallBeforeExists &&
                (target.InstallBeforeSha.Equals(target.AfterSha, StringComparison.OrdinalIgnoreCase) || accepted.Contains(target.InstallBeforeSha)))
            {
                target.Action = "created"; target.BeforeSha = "ABSENT"; target.BeforeBytes = 0;
                Log("기존 한국어 패치 생성 파일을 승계합니다: " + target.RelativePath);
                return;
            }
            if (!stockIsAbsent && target.InstallBeforeExists && accepted.Contains(target.InstallBeforeSha))
            {
                target.Action = "modified"; target.BeforeSha = target.InstallBeforeSha; target.BeforeBytes = target.InstallBeforeBytes;
                CopyCanonicalBackup(PackageManifest.SafeJoin(gameDir, target.RelativePath), target, backupId);
                return;
            }
            if (target.InstallBeforeExists)
            {
                target.Action = "modified";
                target.BeforeSha = target.InstallBeforeSha;
                target.BeforeBytes = target.InstallBeforeBytes;
                CopyCanonicalBackup(PackageManifest.SafeJoin(gameDir, target.RelativePath), target, backupId);
                Log("알 수 없는 기존 SHA를 설치 직전 상태로 보존하고 패치합니다: " + target.RelativePath);
                return;
            }
            throw new InvalidOperationException("필수 게임 파일이 없습니다: " + target.RelativePath);
        }

        private void CopyCanonicalBackup(string source, DirectState target, string backupId)
        {
            string destination = PackageManifest.SafeJoin(Path.Combine(stateRoot, "original", backupId), target.RelativePath);
            if (File.Exists(destination)) PackageManifest.RequireFile(destination, target.BeforeBytes, target.BeforeSha, "설치 직전 파일 백업");
            else FileOps.CopyNewExact(source, destination, target.BeforeSha);
        }

        private void ApplyFiles(InstallState state)
        {
            Dictionary<string, DirectFile> table = manifest.DirectFiles.ToDictionary(x => x.RelativePath, StringComparer.OrdinalIgnoreCase);
            var cmFiles = ContentManagerOverlay.Owned(gameDir);
            int applied = 0;
            foreach (DirectState d in state.Files)
            {
                if (mockMode && File.ReadAllText(Path.Combine(gameDir, "AMS2.exe")) == "INERT TEST FIXTURE - NEVER EXECUTE")
                {
                    string failure = Path.Combine(gameDir, ".mock_failure_after"), crash = Path.Combine(gameDir, ".mock_crash_after");
                    if (File.Exists(failure) && File.ReadAllText(failure) == applied.ToString()) throw new IOException("TEST: injected upgrade failure");
                    if (File.Exists(crash) && File.ReadAllText(crash) == applied.ToString()) Process.GetCurrentProcess().Kill();
                }
                applied++;
                string live = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                bool exists = File.Exists(live);
                if (exists != d.InstallBeforeExists || (exists && FileOps.Sha256(live) != d.InstallBeforeSha))
                    throw new IOException("후보 생성 후 다른 프로그램이 파일을 변경했습니다: " + d.RelativePath);
                if (d.RelativePath.Equals(ErsArchivePatch.RelativePath, StringComparison.OrdinalIgnoreCase))
                {
                    FileOps.ReplaceExact(ersCandidatePath, live, d.AfterSha);
                    continue;
                }
                if (d.RelativePath.Equals(PackageManifest.IgphaseHudRelativePath, StringComparison.OrdinalIgnoreCase))
                {
                    FileOps.ApplyIgphaseHudCandidate(igphaseHudCandidatePath, live, d.AfterBytes, d.AfterSha);
                    continue;
                }
                DirectFile f = table[d.RelativePath];
                bool preserveTimes = exists && cmFiles.Contains(d.RelativePath.Replace('\\','/').ToLowerInvariant());
                DateTime creation = preserveTimes ? File.GetCreationTimeUtc(live) : DateTime.MinValue;
                DateTime modified = preserveTimes ? File.GetLastWriteTimeUtc(live) : DateTime.MinValue;
                if (d.InstallBeforeExists) FileOps.ReplaceExact(manifest.DirectSource(f), live, d.AfterSha);
                else FileOps.CopyNewExact(manifest.DirectSource(f), live, d.AfterSha);
                if (preserveTimes) { File.SetCreationTimeUtc(live, creation); File.SetLastWriteTimeUtc(live, modified); }
            }
        }

        private void PersistRuntimeSupport()
        {
            string target = Path.Combine(stateRoot, "runtime", "AMS2.DynamicBffPatcher.exe");
            FileOps.EnsureDirectoryFor(target);
            if (File.Exists(target) && FileOps.Sha256(target) == PackageManifest.BffPatcherSha256) return;
            if (File.Exists(target)) FileOps.ReplaceExact(manifest.BffPatcherSource, target, PackageManifest.BffPatcherSha256);
            else FileOps.CopyNewExact(manifest.BffPatcherSource, target, PackageManifest.BffPatcherSha256);
        }

        private void RollbackTransaction(InstallState state)
        {
            string transactionRoot = Path.Combine(stateRoot, "transaction", state.BackupId);
            foreach (DirectState d in state.Files.AsEnumerable().Reverse())
            {
                string live = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                if (d.InstallBeforeExists)
                {
                    string backup = PackageManifest.SafeJoin(transactionRoot, d.RelativePath);
                    PackageManifest.RequireFile(backup, d.InstallBeforeBytes, d.InstallBeforeSha, "설치 직전 백업");
                    if (!File.Exists(live) || FileOps.Sha256(live) != d.InstallBeforeSha) FileOps.ReplaceExact(backup, live, d.InstallBeforeSha);
                }
                else if (File.Exists(live))
                {
                    File.Delete(live);
                }
            }
        }

        private void ValidateTransactionRestored(InstallState state)
        {
            foreach (DirectState d in state.Files)
            {
                string live = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                if (d.InstallBeforeExists) PackageManifest.RequireFile(live, d.InstallBeforeBytes, d.InstallBeforeSha, "설치 직전 상태");
                else if (File.Exists(live)) throw new InvalidOperationException("롤백 후 생성 파일 잔류: " + d.RelativePath);
            }
        }

        private void RestoreOriginal(InstallState state)
        {
            string backupRoot = Path.Combine(stateRoot, "original", state.BackupId);
            foreach (DirectState d in state.Files.AsEnumerable().Reverse())
            {
                string live = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                ValidateRestorableFile(state, d);
                if (d.Action == "modified")
                {
                    string backup = PackageManifest.SafeJoin(backupRoot, d.RelativePath);
                    PackageManifest.RequireFile(backup, d.BeforeBytes, d.BeforeSha, "설치 직전 파일 백업");
                    if (!File.Exists(live) || FileOps.Sha256(live) != d.BeforeSha) FileOps.ReplaceExact(backup, live, d.BeforeSha);
                }
                else if (File.Exists(live))
                {
                    File.Delete(live);
                }
            }
        }

        private void ValidateRestorableFile(InstallState state, DirectState d)
        {
            string live = PackageManifest.SafeJoin(gameDir, d.RelativePath);
            if (!File.Exists(live)) return;
            string current = FileOps.Sha256(live);
            if (current == d.AfterSha || (d.Action == "modified" && current == d.BeforeSha)) return;
            if (state.Status == "PREPARED")
            {
                if (d.InstallBeforeExists && current == d.InstallBeforeSha) return;
                DirectFile known = manifest.DirectFiles.FirstOrDefault(f => f.RelativePath.Equals(d.RelativePath, StringComparison.OrdinalIgnoreCase));
                if (known != null && known.AllowedBefore.Contains(current)) return;
            }
            throw new InvalidOperationException("설치 후 수동 변경된 파일은 덮어쓰거나 삭제하지 않습니다: " + d.RelativePath);
        }

        private void ValidateBackupContract(InstallState state)
        {
            string backupRoot = Path.Combine(stateRoot, "original", state.BackupId);
            foreach (DirectState d in state.Files.Where(x => x.Action == "modified"))
                PackageManifest.RequireFile(PackageManifest.SafeJoin(backupRoot, d.RelativePath), d.BeforeBytes, d.BeforeSha, "설치 직전 파일 백업");
        }

        private void ValidateInstalled(InstallState state)
        {
            if (state.Files.Count < manifest.DirectFiles.Count || state.Files.Count > manifest.DirectFiles.Count + 2 || state.Files.Select(x => x.RelativePath).Distinct(StringComparer.OrdinalIgnoreCase).Count() != state.Files.Count)
                throw new InvalidOperationException("설치 상태 계약 불일치");
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
            InstallState s;
            try { s = LoadState(); }
            catch { return "BACKUP_MISSING_OR_DAMAGED"; }
            if (s != null && s.Status == "INSTALLED")
            {
                try { ValidateBackupContract(s); } catch { return "BACKUP_MISSING_OR_DAMAGED"; }
                try { ValidateInstalled(s); return "INSTALLED_EXACT"; }
                catch { return HasManualChanges(s) ? "MANUAL_CHANGES_DETECTED" : "MIXED_OR_INCOMPLETE"; }
            }
            if (s != null && s.Status == "PREPARED") return "MIXED_OR_INCOMPLETE";
            if (s != null && s.Status == "RESTORED")
            {
                try { ValidateBackupContract(s); } catch { return "BACKUP_MISSING_OR_DAMAGED"; }
                try { ValidateRestored(s); return "RESTORED_EXACT"; }
                catch { return InspectUnmanagedState(); }
            }
            if (s != null && s.Status == "ROLLED_BACK")
            {
                try { ValidateTransactionRestored(s); return "ROLLED_BACK"; } catch { return "MIXED_OR_INCOMPLETE"; }
            }
            if (s == null && FindPreviousInstalled() != null) return "UPDATE_AVAILABLE";
            return InspectUnmanagedState();
        }

        private bool HasManualChanges(InstallState state)
        {
            foreach (DirectState d in state.Files)
            {
                string live = PackageManifest.SafeJoin(gameDir, d.RelativePath);
                if (!File.Exists(live)) continue;
                string sha = FileOps.Sha256(live);
                if (sha != d.AfterSha && sha != d.BeforeSha) return true;
            }
            return false;
        }

        private string InspectUnmanagedState()
        {
            bool unsafeResidue = false;
            bool installableExistingState = false;
            foreach (DirectFile f in manifest.DirectFiles)
            {
                string live = PackageManifest.SafeJoin(gameDir, f.RelativePath);
                if (!File.Exists(live)) { if (f.Role == "modified") unsafeResidue = true; continue; }
                if (f.Role == "modified")
                {
                    installableExistingState = true;
                }
                else
                {
                    installableExistingState = true;
                }
            }
            string bff = PackageManifest.SafeJoin(gameDir, PackageManifest.IgphaseHudRelativePath);
            if (!File.Exists(bff)) return "MIXED_OR_INCOMPLETE";
            try
            {
                string report = Path.Combine(Path.GetTempPath(), "AMS2-KR-BFF-INSPECT-" + Guid.NewGuid().ToString("N") + ".json");
                try
                {
                    string route = ParseRoute(FileOps.RunBffTool(manifest.BffPatcherSource, "inspect", gameDir, bff, null, report));
                    if (route.Equals("GUI\\kr13_driver_name_semibold.bfont", StringComparison.OrdinalIgnoreCase) ||
                        route.Equals("GUI\\kr13_font_hud_main.bfont", StringComparison.OrdinalIgnoreCase)) installableExistingState = true;
                    else if (!route.Equals("GUI\\font_phoenix_body_regular.bfont", StringComparison.OrdinalIgnoreCase)) return "MANUAL_CHANGES_DETECTED";
                }
                finally { if (File.Exists(report)) File.Delete(report); }
            }
            catch { return "MANUAL_CHANGES_DETECTED"; }
            if (unsafeResidue) return "MIXED_OR_INCOMPLETE";
            return installableExistingState ? "INSTALLABLE_EXISTING_STATE" : "STOCK_ENGLISH";
        }

        private static string ParseRoute(string output)
        {
            foreach (string line in (output ?? "").Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
                if (line.StartsWith("route=", StringComparison.OrdinalIgnoreCase)) return line.Substring(6).Trim();
            throw new InvalidOperationException("IGPHASEHUD ProfileName route 결과가 없습니다.");
        }

        private PreviousInstallInfo FindPreviousInstalled()
        {
            return LoadHistoryStates().Where(h => !h.StateRoot.Equals(stateRoot, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(h => h.State.Files.Count(f => UpgradeOwnership.Match(gameDir, f)))
                .ThenByDescending(h => h.InstalledUtc).FirstOrDefault(h => h.State.Files.Any(f => UpgradeOwnership.Match(gameDir, f)));
        }

        private void ValidateRecordedInstalledFiles(InstallState state)
        {
            foreach (DirectState file in state.Files)
                PackageManifest.RequireFile(PackageManifest.SafeJoin(gameDir, file.RelativePath), file.AfterBytes, file.AfterSha, "이전 버전 설치 파일");
        }

        private List<PreviousInstallInfo> LoadHistoryStates()
        {
            return UpgradeOwnership.Read(gameDir, Log);
        }

        private void MarkPreviousInstallationsSuperseded()
        {
            string root = Path.Combine(gameDir, "Backup", "AMS2-Korean");
            if (!Directory.Exists(root)) return;
            foreach (string directory in UpgradeOwnership.Roots(gameDir))
            {
                if (Path.GetFullPath(directory).Equals(Path.GetFullPath(stateRoot), StringComparison.OrdinalIgnoreCase)) continue;
                string path = Path.Combine(directory, "install-state.tsv");
                if (!File.Exists(path)) continue;
                try
                {
                    Dictionary<string, string> values = ReadMap(path);
                    if (!values.ContainsKey("status") || values["status"] != "INSTALLED") continue;
                    string[] lines = File.ReadAllLines(path, Encoding.UTF8);
                    for (int i = 0; i < lines.Length; i++) if (lines[i].StartsWith("status\t", StringComparison.OrdinalIgnoreCase)) lines[i] = "status\tSUPERSEDED";
                    FileOps.WriteTextAtomic(path, String.Join(Environment.NewLine, lines) + Environment.NewLine);
                    Log("이전 버전 상태 승계: " + Path.GetFileName(directory));
                }
                catch (Exception e)
                {
                    Log("경고: 이전 버전 상태 표시는 갱신하지 못했지만 현재 설치는 유지합니다: " + e.Message);
                }
            }
        }

        private void SaveState(InstallState state, string status)
        {
            Directory.CreateDirectory(stateRoot);
            state.Status = status;
            StringBuilder head = new StringBuilder();
            head.AppendLine("status\t" + status);
            head.AppendLine("schema_version\t2");
            head.AppendLine("package_version\t" + PackageManifest.Version);
            head.AppendLine("ownership\tverified-record-or-official-catalog");
            head.AppendLine("restore_policy\t" + state.RestorePolicy);
            head.AppendLine("installed_utc\t" + state.InstalledUtc);
            head.AppendLine("game_dir\t" + state.GameDir);
            head.AppendLine("buildid\t" + state.BuildId);
            head.AppendLine("backup_id\t" + state.BackupId);
            head.AppendLine("predecessor_package_id\t" + (state.PredecessorPackageId ?? ""));
            FileOps.WriteTextAtomic(Path.Combine(stateRoot, "install-state.tsv"), head.ToString());
            StringBuilder files = new StringBuilder("relative_path\taction\tbefore_bytes\tbefore_sha256\tafter_bytes\tafter_sha256\tinstall_before_exists\tinstall_before_bytes\tinstall_before_sha256\n");
            foreach (DirectState d in state.Files) files.Append(d.RelativePath).Append('\t').Append(d.Action).Append('\t').Append(d.BeforeBytes).Append('\t').Append(d.BeforeSha).Append('\t').Append(d.AfterBytes).Append('\t').Append(d.AfterSha).Append('\t').Append(d.InstallBeforeExists ? "1" : "0").Append('\t').Append(d.InstallBeforeBytes).Append('\t').Append(d.InstallBeforeSha ?? "ABSENT").AppendLine();
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

        private InstallState LoadState() { return LoadStateFromRoot(stateRoot); }

        private InstallState LoadStateFromRoot(string root)
        {
            string headPath = Path.Combine(root, "install-state.tsv");
            string filesPath = Path.Combine(root, "files.tsv");
            string invPath = Path.Combine(root, "invariants.tsv");
            if (!File.Exists(headPath)) return null;
            if (!File.Exists(filesPath) || !File.Exists(invPath)) throw new InvalidOperationException("설치 상태 파일이 불완전합니다.");
            Dictionary<string, string> h = ReadMap(headPath);
            Dictionary<string, string> v = ReadMap(invPath);
            InstallState s = new InstallState { Status = h["status"], InstalledUtc = h["installed_utc"], GameDir = h["game_dir"], BuildId = h["buildid"], BackupId = h.ContainsKey("backup_id") ? h["backup_id"] : "", PredecessorPackageId = h.ContainsKey("predecessor_package_id") ? h["predecessor_package_id"] : "" };
            if (h.ContainsKey("restore_policy")) s.RestorePolicy = h["restore_policy"];
            s.Invariants = new InvariantState {
                BootflowSha = v["bootflow_sha256"], PhysicsSha = v["physicspersistent_sha256"], PhysicsMarker = v["physicspersistent_remove_marker"] == "1",
                VehicleFiles = Int32.Parse(v["vehicle_files"], CultureInfo.InvariantCulture), VehicleTreeSha = v["vehicle_tree_sha256"],
                TrackFiles = Int32.Parse(v["track_files"], CultureInfo.InvariantCulture), TrackTreeSha = v["track_tree_sha256"]
            };
            foreach (string line in File.ReadAllLines(filesPath, Encoding.UTF8).Skip(1))
            {
                if (String.IsNullOrWhiteSpace(line)) continue;
                string[] p = line.Split('\t');
                if (p.Length != 6 && p.Length != 9) throw new InvalidOperationException("files.tsv 형식 오류");
                DirectState d = new DirectState { RelativePath = PackageManifest.NormalizeRelative(p[0]), Action = p[1], BeforeBytes = Int64.Parse(p[2], CultureInfo.InvariantCulture), BeforeSha = p[3], AfterBytes = Int64.Parse(p[4], CultureInfo.InvariantCulture), AfterSha = PackageManifest.NormalizeHash(p[5]) };
                d.InstallBeforeExists = p.Length == 9 ? p[6] == "1" : d.Action == "modified";
                d.InstallBeforeBytes = p.Length == 9 ? Int64.Parse(p[7], CultureInfo.InvariantCulture) : d.BeforeBytes;
                d.InstallBeforeSha = p.Length == 9 ? p[8] : d.BeforeSha;
                s.Files.Add(d);
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

        private void CleanupIgphaseHudCandidate()
        {
            string directory = candidateRoot;
            candidateRoot = null;
            igphaseHudCandidatePath = null;
            igphaseHudPatchReportPath = null;
            ersCandidatePath = null;
            ersOriginalPath = null;
            if (String.IsNullOrWhiteSpace(directory)) return;
            try
            {
                directory = Path.GetFullPath(directory);
                string temp = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
                if (directory.StartsWith(temp, StringComparison.OrdinalIgnoreCase) && Path.GetFileName(directory).StartsWith("AMS2-KR-BETA087-BFF-", StringComparison.Ordinal))
                    Directory.Delete(directory, true);
            }
            catch { }
        }

        private static OperationResult Ok(string status, string message, string path) { return new OperationResult { Success = true, Status = status, Message = message, LogPath = path }; }
        private OperationResult Fail(string status, string message)
        {
            string path = null;
            try { if (!String.IsNullOrEmpty(stateRoot)) path = SaveLog(); }
            catch (Exception e) { message += " (오류 로그 저장 실패: " + e.Message + ")"; }
            return new OperationResult { Success = false, Status = status, Message = message, LogPath = path };
        }
    }
}
