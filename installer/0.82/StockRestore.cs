using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Ams2KoreanBeta
{
    internal sealed class StockFile
    {
        internal string Relative, Action, Sha, BeforeSha, BackupName, ShortcutPath;
        internal long Bytes;
        internal FileAttributes BeforeAttributes;
    }

    internal static class StockRestore
    {
        internal static string AuditFonts(string directory, string output)
        {
            GameInfo game = SteamLocator.FromGameDirectory(directory);
            output = Path.GetFullPath(output);
            if (output.StartsWith(game.GameDir.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("진단 ZIP은 게임 폴더 밖에 저장해주세요.");
            var report = new StringBuilder("relative_path\tstatus\tbytes\tactual_sha1\tstock_sha1\tactual_sha256\n");
            int count = 0, different = 0, missing = 0, errors = 0;
            using (var reader = new StreamReader(Assembly.GetExecutingAssembly().GetManifestResourceStream("Ams2KoreanBeta.FontBaseline"), Encoding.UTF8))
            {
                reader.ReadLine();
                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    string[] row = line.Split('\t');
                    if (row.Length != 3) throw new InvalidDataException("폰트 기준 목록 오류");
                    count++;
                    try
                    {
                        string path = SafeTarget(game.GameDir, row[0]);
                        if (!File.Exists(path)) { missing++; report.AppendLine(row[0] + "\tMISSING\t0\t\t" + row[2] + "\t"); continue; }
                        string hash;
                        using (SHA1 sha = SHA1.Create())
                        using (var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                            hash = BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "");
                        bool match = hash == row[2] && new FileInfo(path).Length.ToString(CultureInfo.InvariantCulture) == row[1];
                        if (!match) different++;
                        report.AppendLine(row[0] + "\t" + (match ? "STOCK" : "DIFFERENT") + "\t" + new FileInfo(path).Length + "\t" + hash + "\t" + row[2] + "\t" + FileOps.Sha256(path));
                    }
                    catch (Exception e) { errors++; report.AppendLine(row[0] + "\tERROR\t0\t\t" + row[2] + "\t" + e.Message.Replace('\t', ' ').Replace('\r', ' ').Replace('\n', ' ')); }
                }
            }
            string summary = "read_only=true\nreference_build=24132163\ncurrent_build=" + game.BuildId + "\nchecked=" + count + "\ndifferent=" + different + "\nmissing=" + missing + "\nerrors=" + errors + "\n";
            var textures = new StringBuilder("relative_path\tbytes\tsha256\tnote\n");
            string gui = Path.GetDirectoryName(SafeTarget(game.GameDir, "gui/font-audit-placeholder"));
            if (Directory.Exists(gui)) foreach (string file in Directory.GetFiles(gui, "*.dds", SearchOption.TopDirectoryOnly))
            {
                string name = Path.GetFileName(file).ToLowerInvariant();
                if (!new[] { "font", "aries", "phoenix", "arial" }.Any(name.Contains)) continue;
                string relative = "gui/" + Path.GetFileName(file);
                try
                {
                    string path = SafeTarget(game.GameDir, relative);
                    textures.AppendLine(relative + "\t" + new FileInfo(path).Length + "\t" + FileOps.Sha256(path) + "\tLOOSE_TEXTURE_NOT_VERIFIED_AGAINST_ARCHIVE");
                }
                catch (Exception e) { textures.AppendLine(relative + "\t0\t\tREAD_ERROR: " + e.GetType().Name); }
            }
            FileOps.EnsureDirectoryFor(output);
            using (var file = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
            using (var zip = new ZipArchive(file, ZipArchiveMode.Create))
            {
                WriteZipText(zip, "summary.txt", summary);
                WriteZipText(zip, "default-fonts.tsv", report.ToString());
                WriteZipText(zip, "loose-font-textures.tsv", textures.ToString());
                string backups = PackageManifest.SafeJoin(game.GameDir, "Backup/AMS2-Korean-StockRestore");
                if (Directory.Exists(backups))
                {
                    string latest = Directory.GetDirectories(backups).OrderByDescending(Path.GetFileName).FirstOrDefault();
                    if (latest != null) foreach (string name in new[] { "events.log", "before.tsv" })
                    {
                        string relative = "Backup/AMS2-Korean-StockRestore/" + Path.GetFileName(latest) + "/" + name;
                        string path = SafeTarget(game.GameDir, relative);
                        if (File.Exists(path) && new FileInfo(path).Length < 1024 * 1024)
                            WriteZipText(zip, "last-recovery/" + name, File.ReadAllText(path, Encoding.UTF8));
                    }
                }
            }
            return "기본 폰트 진단을 저장했습니다. 게임 파일은 변경하지 않았습니다.\n순정과 다름: " + different + " / 없음: " + missing + " / 읽기 실패: " + errors + "\n\n" + output;
        }

        private static void WriteZipText(ZipArchive zip, string name, string text)
        {
            using (var writer = new StreamWriter(zip.CreateEntry(name).Open(), new UTF8Encoding(false))) writer.Write(text);
        }

        // Only the embedded, verified 0.7-0.82 localization file list is authoritative.
        // Old installer records and current file hashes never supply restoration data.
        internal static string Run(string directory, Action<string> progress)
        {
            GameInfo game = SteamLocator.FromGameDirectory(directory);
            if (game.BuildId != PackageManifest.BuildId)
                throw new InvalidOperationException("이 복구 도구의 순정 파일은 게임 빌드 " + PackageManifest.BuildId + "용입니다. 현재 빌드: " + game.BuildId);
            string root = Path.GetFullPath(game.GameDir);
            using (Mutex mutex = new Mutex(false, "Local\\AMS2StockRestore-" + FileOps.Sha256Text(root.ToUpperInvariant())))
            {
                bool owned = false;
                try
                {
                    try { owned = mutex.WaitOne(0); } catch (AbandonedMutexException) { owned = true; }
                    if (!owned) throw new InvalidOperationException("이 게임 폴더를 복구하는 도구가 이미 실행 중입니다.");
                    GuardProcesses();
                    return Restore(root, progress);
                }
                finally { if (owned) mutex.ReleaseMutex(); }
            }
        }

        internal static string SafeTarget(string root, string relative)
        {
            if (relative.Contains(":") || relative.Split('/', '\\').Any(x => x == "." || x == ".." || x.EndsWith(".") || x.EndsWith(" ")))
                throw new InvalidOperationException("허용되지 않는 파일 경로: " + relative);
            string target = PackageManifest.SafeJoin(root, relative);
            for (string p = target; p != null; p = Path.GetDirectoryName(p))
                if ((File.Exists(p) || Directory.Exists(p)) && (File.GetAttributes(p) & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidOperationException("연결된 폴더/파일은 복구 대상으로 사용할 수 없습니다: " + p);
            if (Directory.Exists(target)) throw new InvalidOperationException("파일 위치에 폴더가 있습니다: " + target);
            return target;
        }

        private static string Target(string root, StockFile file)
        {
            if (file.ShortcutPath == null) return SafeTarget(root, file.Relative);
            string volume = Path.GetPathRoot(file.ShortcutPath);
            return SafeTarget(volume, file.ShortcutPath.Substring(volume.Length));
        }

        private static void AddShortcuts(string root, List<StockFile> files, Action<string> log)
        {
            var folders = new[] {
                Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory),
                Environment.GetFolderPath(Environment.SpecialFolder.Programs),
                Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms),
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar")
            };
#if STOCK_RESTORE_TEST
            // Tests may inspect only their disposable shortcut folder, never the real desktop.
            folders = new[] { Environment.GetEnvironmentVariable("AMS2_STOCK_TEST_SHORTCUTS") };
#endif
            var candidates = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string folder in folders.Where(p => !String.IsNullOrWhiteSpace(p) && Directory.Exists(p)))
                foreach (string path in Directory.GetFiles(folder, "*.lnk", SearchOption.TopDirectoryOnly)) candidates.Add(Path.GetFullPath(path));
            foreach (StockFile record in files.Where(f => f.Relative.EndsWith("/shortcuts.tsv", StringComparison.OrdinalIgnoreCase)))
                foreach (string line in File.ReadAllLines(SafeTarget(root, record.Relative), Encoding.UTF8).Skip(1))
                {
                    string[] row = line.Split('\t');
                    try
                    {
                        if (row.Length == 3 && Path.IsPathRooted(row[1]) && row[1].EndsWith(".lnk", StringComparison.OrdinalIgnoreCase) && File.Exists(row[1]))
                            candidates.Add(Path.GetFullPath(row[1]));
                    }
                    catch (ArgumentException) { }
                    catch (NotSupportedException) { }
                    catch (PathTooLongException) { }
                }
            if (candidates.Count == 0) return;
            string normal = SafeTarget(root, "AMS2 Korean Launcher.exe"), vr = SafeTarget(root, "AMS2 Korean VR Launcher.exe");
            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType == null) throw new InvalidOperationException("Windows 바로가기 확인 기능을 사용할 수 없습니다.");
            object shell = Activator.CreateInstance(shellType);
            try
            {
                foreach (string path in candidates.OrderBy(p => p, StringComparer.OrdinalIgnoreCase))
                {
                    object shortcut = null;
                    try
                    {
                        shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
                        string target = shortcut.GetType().InvokeMember("TargetPath", BindingFlags.GetProperty, null, shortcut, null) as string;
                        if (!String.Equals(target, normal, StringComparison.OrdinalIgnoreCase) && !String.Equals(target, vr, StringComparison.OrdinalIgnoreCase)) continue;
                        files.Add(new StockFile { Relative = "shortcut/" + files.Count + "/" + Path.GetFileName(path), Action = "remove", ShortcutPath = path });
                    }
                    catch (TargetInvocationException) { log("연결 대상을 읽지 못한 바로가기는 보존했습니다: " + path); }
                    catch (COMException) { log("연결 대상을 읽지 못한 바로가기는 보존했습니다: " + path); }
                    finally { if (shortcut != null && Marshal.IsComObject(shortcut)) Marshal.FinalReleaseComObject(shortcut); }
                }
            }
            finally { if (Marshal.IsComObject(shell)) Marshal.FinalReleaseComObject(shell); }
        }

        private static void GuardProcesses()
        {
            foreach (string name in new[] { "AMS2", "AMS2AVX", "AMS2 Korean Launcher", "AMS2 Korean VR Launcher" })
                foreach (Process process in Process.GetProcessesByName(name))
                    using (process) { throw new InvalidOperationException("게임과 한글 런처를 종료한 뒤 다시 실행해주세요: " + name); }
        }

        private static string Restore(string root, Action<string> progress)
        {
            string backup = SafeTarget(root, "Backup/AMS2-Korean-StockRestore/" + DateTime.Now.ToString("yyyyMMdd-HHmmss", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(backup);
            var touched = new List<StockFile>();
            Action<string> log = delegate(string value)
            {
                File.AppendAllText(Path.Combine(backup, "events.log"), DateTime.UtcNow.ToString("o") + " " + value + Environment.NewLine, new UTF8Encoding(false));
                if (progress != null) progress(value);
            };
            try
            {
                log("순정 파일을 검증하고 있습니다...");
                List<StockFile> files = ExtractStock(backup);
                AddRecords(root, files);
                AddShortcuts(root, files, log);
                foreach (StockFile f in files) Target(root, f);
                log("현재 파일을 백업하고 있습니다...");
                int backupIndex = 0;
                foreach (StockFile f in files)
                {
                    f.BackupName = (backupIndex++).ToString("D4", CultureInfo.InvariantCulture);
                    string live = Target(root, f);
                    f.BeforeSha = "ABSENT";
                    if (!File.Exists(live)) continue;
                    using (new FileStream(live, FileMode.Open, FileAccess.Read, FileShare.None)) { }
                    f.BeforeAttributes = File.GetAttributes(live);
                    f.BeforeSha = FileOps.Sha256(live);
                    FileOps.CopyNewExact(live, SafeTarget(backup, "before/" + f.BackupName), f.BeforeSha);
                }
                File.WriteAllText(Path.Combine(backup, "before.tsv"), "relative_path\tbefore_sha256\tattributes\tbackup_file\ttarget_path\n" +
                    String.Join("\n", files.Select(f => f.Relative + "\t" + f.BeforeSha + "\t" + (int)f.BeforeAttributes + "\tbefore/" + f.BackupName + "\t" + Target(root, f))) + "\n", new UTF8Encoding(false));
                GuardProcesses();
                log("완전 제거 / 순정 복구하고 있습니다...");
                int count = 0;
                foreach (StockFile f in files)
                {
                    string live = Target(root, f);
                    string current = File.Exists(live) ? FileOps.Sha256(live) : "ABSENT";
                    if (current != f.BeforeSha) throw new InvalidOperationException("백업 후 파일이 변경되었습니다: " + f.Relative);
                    if (f.Action == "keep") continue;
                    if (f.Action == "restore" && current == f.Sha || f.Action == "remove" && current == "ABSENT") continue;
                    touched.Add(f);
                    if (File.Exists(live)) File.SetAttributes(live, File.GetAttributes(live) & ~FileAttributes.ReadOnly);
                    if (f.Action == "restore") FileOps.ReplaceExact(SafeTarget(backup, "stock/" + f.Relative), live, f.Sha);
                    else File.Delete(live);
                    if (++count % 50 == 0) log("순정 복구 진행: " + count + "개 파일 처리");
#if STOCK_RESTORE_TEST
                    if (Environment.GetEnvironmentVariable("AMS2_STOCK_TEST_FAIL_AFTER") == count.ToString(CultureInfo.InvariantCulture))
                        throw new IOException("TEST: simulated interruption");
#endif
                }
                foreach (StockFile f in files)
                {
                    string live = Target(root, f);
                    if (f.Action == "restore") PackageManifest.RequireFile(live, f.Bytes, f.Sha, "순정 복구 검증");
                    else if (f.Action == "remove" && File.Exists(live)) throw new InvalidOperationException("패치 파일이 남아 있습니다: " + f.Relative);
                }
                ShortcutManager.RefreshShell();
                log("완전 제거 완료: 원본 " + StockPayload.RestoreCount + "개 검증 / 추가 파일 " + StockPayload.RemoveCount + "개 제거 확인 / 바로가기 " + files.Count(f => f.ShortcutPath != null) + "개 제거 / 설치 기록 백업 완료");
                return backup;
            }
            catch (Exception failure)
            {
                var errors = new List<string>();
                foreach (StockFile f in touched.AsEnumerable().Reverse())
                {
                    try
                    {
                        string live = Target(root, f);
                        if (File.Exists(live)) File.SetAttributes(live, File.GetAttributes(live) & ~FileAttributes.ReadOnly);
                        if (f.BeforeSha == "ABSENT") File.Delete(live);
                        else
                        {
                            string before = SafeTarget(backup, "before/" + f.BackupName);
                            if (FileOps.Sha256(before) != f.BeforeSha) throw new IOException("백업 검증 실패");
                            FileOps.ReplaceExact(before, live, f.BeforeSha);
                            File.SetAttributes(live, f.BeforeAttributes);
                        }
                    }
                    catch (Exception rollback) { errors.Add(f.Relative + ": " + rollback.Message); }
                }
                string result = failure.Message + Environment.NewLine + (errors.Count == 0 ? "복구 전 상태가 보존되었습니다." : "일부 파일을 되돌리지 못했습니다: " + String.Join("; ", errors)) + Environment.NewLine + "백업 및 로그: " + backup;
                try { log("실패: " + result); } catch { }
                throw new InvalidOperationException(result, failure);
            }
        }

        private static void AddRecords(string root, List<StockFile> files)
        {
            SafeTarget(root, "Backup/AMS2-Korean/install-state.tsv");
            string parent = PackageManifest.SafeJoin(root, "Backup/AMS2-Korean");
            if (!Directory.Exists(parent)) return;
            foreach (string directory in Directory.GetDirectories(parent, "AMS2-KR-BETA-*", SearchOption.TopDirectoryOnly))
            {
                foreach (string name in new[] { "install-state.tsv", "files.tsv", "invariants.tsv", "events.log", "shortcuts.tsv" })
                {
                    string relative = "Backup/AMS2-Korean/" + Path.GetFileName(directory) + "/" + name;
                    string state = SafeTarget(root, relative);
                    if (File.Exists(state)) files.Add(new StockFile { Relative = relative, Action = name == "install-state.tsv" || name == "shortcuts.tsv" ? "remove" : "keep" });
                }
            }
        }

        private static List<StockFile> ExtractStock(string backup)
        {
            using (Stream embedded = Assembly.GetExecutingAssembly().GetManifestResourceStream("Ams2KoreanBeta.Stock"))
            using (var data = new MemoryStream())
            {
                if (embedded == null) throw new InvalidOperationException("내장 순정 파일이 없습니다.");
                embedded.CopyTo(data);
                data.Position = 0;
                using (SHA256 hash = SHA256.Create())
                    if (BitConverter.ToString(hash.ComputeHash(data)).Replace("-", "") != StockPayload.Sha256)
                        throw new InvalidOperationException("복구 실행파일이 손상되었습니다. 다시 받아주세요.");
                data.Position = 0;
                using (var zip = new ZipArchive(data, ZipArchiveMode.Read))
                {
                    var files = new List<StockFile>();
                    using (var reader = new StreamReader(zip.GetEntry("stock-files.tsv").Open(), Encoding.UTF8))
                    {
                        if (reader.ReadLine() != "relative_path\taction\tbytes\tsha256") throw new InvalidOperationException("순정 목록 형식 오류");
                        string line;
                        while ((line = reader.ReadLine()) != null)
                        {
                            string[] row = line.Split('\t');
                            if (row.Length != 4 || row[1] != "restore" && row[1] != "remove") throw new InvalidOperationException("순정 목록 오류");
                            files.Add(new StockFile { Relative = row[0], Action = row[1], Bytes = Int64.Parse(row[2], CultureInfo.InvariantCulture), Sha = row[3] });
                        }
                    }
                    int total = StockPayload.RestoreCount + StockPayload.RemoveCount;
                    if (files.Count != total || files.Select(f => f.Relative).Distinct(StringComparer.OrdinalIgnoreCase).Count() != total || files.Count(f => f.Action == "restore") != StockPayload.RestoreCount || zip.Entries.Count != StockPayload.RestoreCount + 1)
                        throw new InvalidOperationException("순정 파일 수 검증 실패");
                    foreach (StockFile f in files.Where(f => f.Action == "restore"))
                    {
                        string target = SafeTarget(backup, "stock/" + f.Relative);
                        FileOps.EnsureDirectoryFor(target);
                        using (Stream input = zip.GetEntry("original/" + f.Relative).Open())
                        using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write)) input.CopyTo(output);
                        PackageManifest.RequireFile(target, f.Bytes, f.Sha, "내장 순정 파일");
                    }
                    return files;
                }
            }
        }
    }

    internal sealed class StockRestoreForm : Form
    {
#if FONT_AUDIT_ONLY
        private const bool AuditOnly = true;
#else
        private const bool AuditOnly = false;
#endif
        private readonly TextBox path = new TextBox();
        private readonly Label status = new Label();
        private readonly Button restore = new Button();
        private readonly Button browse = new Button();
        private readonly Button audit = new Button();
        private bool busy;

        internal StockRestoreForm()
        {
            Text = AuditOnly ? "AMS2 기본 폰트 진단" : "AMS2 한국어 패치 완전 제거";
            Font = new Font("Malgun Gothic", 10F);
            ClientSize = new Size(740, 390); AutoScaleMode = AutoScaleMode.Dpi;
            BackColor = Color.FromArgb(245, 246, 249);
            FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
            var header = new Panel { Dock = DockStyle.Top, Height = 100, BackColor = Color.FromArgb(26, 31, 43) };
            header.Controls.Add(new Label { Text = AuditOnly ? "AMS2 한국어 패치  |  폰트 진단" : "AMS2 한국어 패치  |  완전 제거", Left = 24, Top = 20, Width = 690, Height = 36, ForeColor = Color.White, Font = new Font(Font.FontFamily, 19F, FontStyle.Bold) });
            header.Controls.Add(new Label { Text = "한글 패치 제작자 : ENGIceBlasT", Left = 26, Top = 65, Width = 660, Height = 24, ForeColor = Color.LightGray });
            Controls.Add(header);
            Controls.Add(new Label { Text = AuditOnly ? "기본 폰트 파일을 Steam 원본 목록과 비교해 진단 ZIP을 저장합니다.\n게임 파일을 변경하지 않으며, 한글패치를 제거할 필요가 없습니다." : "한글패치와 한글판 바로가기를 제거하고 기본 폰트까지 순정으로 복구합니다.\n현재 파일과 설치 기록은 게임 폴더의 Backup에 먼저 보관합니다.", Left = 26, Top = 118, Width = 690, Height = 50 });
            Controls.Add(new Label { Text = "Automobilista 2 게임 폴더", Left = 26, Top = 181, Width = 600, Height = 24 });
            path.SetBounds(26, 210, 570, 28); Controls.Add(path);
            browse.Text = "폴더 선택"; browse.SetBounds(608, 207, 104, 34); browse.Click += delegate { using (var d = new FolderBrowserDialog()) if (d.ShowDialog(this) == DialogResult.OK) path.Text = d.SelectedPath; }; Controls.Add(browse);
            restore.Text = "완전 제거 / 순정 복구"; restore.SetBounds(26, 263, 190, 43); restore.BackColor = Color.FromArgb(177, 26, 32); restore.ForeColor = Color.White; restore.FlatStyle = FlatStyle.Flat; restore.Font = new Font(Font, FontStyle.Bold); restore.Click += async delegate { await Run(); }; Controls.Add(restore);
            restore.Visible = !AuditOnly;
            audit.Text = "폰트 진단 저장"; audit.SetBounds(AuditOnly ? 26 : 232, 263, 190, 43); audit.Click += async delegate { await Audit(); }; Controls.Add(audit);
            var close = new Button { Text = "닫기", Left = 608, Top = 263, Width = 104, Height = 43 }; close.Click += delegate { Close(); }; Controls.Add(close);
            status.SetBounds(26, 326, 686, 50); status.Text = "대상: 한글패치 0.7~0.82 / 게임 빌드 24132163"; Controls.Add(status);
            Shown += delegate { try { var games = SteamLocator.Detect(); if (games.Count > 0) path.Text = games[0].GameDir; } catch (Exception e) { status.Text = e.Message; } };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { e.Cancel = busy; };
        }

        private async Task Audit()
        {
            using (var dialog = new SaveFileDialog { Filter = "진단 ZIP|*.zip", FileName = "AMS2-Font-Diagnostic-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".zip", InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments) })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                string directory = path.Text.Trim();
                busy = true; restore.Enabled = audit.Enabled = browse.Enabled = path.Enabled = false;
                status.Text = "기본 폰트 파일을 읽고 있습니다...";
                try
                {
                    string result = await Task.Run(() => StockRestore.AuditFonts(directory, dialog.FileName));
                    status.Text = "폰트 진단 ZIP을 저장했습니다. 파일을 전달해주세요.";
                    MessageBox.Show(this, result, "폰트 진단 완료", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                catch (Exception e) { status.Text = "진단 파일을 저장하지 못했습니다."; MessageBox.Show(this, e.Message, "폰트 진단 오류", MessageBoxButtons.OK, MessageBoxIcon.Error); }
                finally { busy = false; restore.Enabled = audit.Enabled = browse.Enabled = path.Enabled = true; }
            }
        }

        private async Task Run()
        {
            string directory = path.Text.Trim();
            if (MessageBox.Show(this, "선택한 게임 폴더:\n" + directory + "\n\n기본 폰트와 패치 대상 파일은 백업 후 순정으로 교체합니다.\n추가 폰트 이미지, 한글 런처, 한글판 바로가기, 설치 기록을 제거합니다.\n같은 폰트 파일을 바꾼 다른 모드도 순정으로 돌아갑니다.\n세이브와 리플레이는 유지하며, 안전 백업은 남겨 둡니다.\n게임과 한글 런처를 종료한 상태에서 진행해주세요.", "한글패치 완전 제거", MessageBoxButtons.OKCancel, MessageBoxIcon.Warning) != DialogResult.OK) return;
            busy = true; restore.Enabled = audit.Enabled = browse.Enabled = path.Enabled = false;
            try
            {
                string backup = await Task.Run(() => StockRestore.Run(directory, text => BeginInvoke((MethodInvoker)delegate { status.Text = text; })));
                status.Text = "완전 제거와 순정 파일 검증이 완료되었습니다.";
                MessageBox.Show(this, "한글패치를 제거하고 기본 폰트까지 순정 파일로 복구했습니다.\nSteam 라이브러리에서 게임을 실행해주세요.\n\n백업 및 로그:\n" + backup, "완전 제거 완료", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception e) { status.Text = "복구 실패 — 오류 내용과 백업 경로를 확인해주세요."; MessageBox.Show(this, e.Message, "복구 실패", MessageBoxButtons.OK, MessageBoxIcon.Error); }
            finally { busy = false; restore.Enabled = audit.Enabled = browse.Enabled = path.Enabled = true; }
        }
    }

    internal static class StockRestoreProgram
    {
        [STAThread]
        public static int Main(string[] args)
        {
            AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
            AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
#if STOCK_RESTORE_TEST
            Console.OutputEncoding = Encoding.UTF8;
            if (args.Length == 3 && args[0] == "--font-audit")
            {
                try { Console.WriteLine(StockRestore.AuditFonts(args[1], args[2])); return 0; }
                catch (Exception e) { Console.Error.WriteLine(e.Message); return 1; }
            }
            if (args.Length == 2 && args[0] == "--render")
            {
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                using (var form = new StockRestoreForm())
                {
                    form.StartPosition = FormStartPosition.Manual; form.Location = new Point(-20000, -20000); form.ShowInTaskbar = false;
                    form.Show(); Application.DoEvents();
                    using (var bitmap = new Bitmap(form.Width, form.Height)) { form.DrawToBitmap(bitmap, new Rectangle(0, 0, form.Width, form.Height)); bitmap.Save(args[1]); }
                    form.Close();
                }
                return 0;
            }
            if (args.Length == 2 && args[0] == "--restore")
            {
                try { Console.WriteLine("BACKUP=" + StockRestore.Run(args[1], Console.WriteLine)); return 0; }
                catch (Exception e) { Console.Error.WriteLine(e.Message); return 1; }
            }
#endif
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new StockRestoreForm()); return 0;
        }
    }
}
