using System;
using System.IO;
using System.IO.Compression;
using System.Threading;
using System.Drawing;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;

namespace Ams2KoreanBeta
{
    internal static class LauncherUpdateTest
    {
        private static void Require(bool value, string message) { if (!value) throw new Exception(message); }
        private static void Refuses(Action action, string message)
        {
            try { action(); } catch (Exception) { return; }
            throw new Exception(message);
        }

        [STAThread]
        public static int Main(string[] args)
        {
            try { return Run(args); }
            catch (Exception error) { Console.Error.WriteLine(error.GetType().Name + ": " + error.Message); return 1; }
        }

        private static int Run(string[] args)
        {
            string output = Path.GetFullPath(args[0]);
            Directory.CreateDirectory(output);
            Require(!GithubUpdater.IsNewer("v0.7", "0.7.0.0"), "two-part version equality");
            Require(GithubUpdater.IsNewer("v0.7", "Closed Beta 0.6.87"), "0.7 upgrade ordering");
            Require(GithubUpdater.IsNewer("v0.7.1", "Closed Beta 0.7"), "patch upgrade ordering");
            Require(!GithubUpdater.IsNewer("v0.6.87", "0.7"), "downgrade blocked");
            Require(GithubUpdater.IsNewer("v0.88", "Open Beta 0.81"), "open beta upgrade ordering");
            Require(!GithubUpdater.IsNewer("v0.88", "Open Beta 0.88"), "open beta version equality");
            Refuses(() => GithubUpdater.ParseVersion("not-a-version"), "malformed version accepted");
            Refuses(() => GithubUpdater.ParseVersion("v0.88-test1"), "prerelease accepted");
            string json = "{\"tag_name\":\"v0.88\",\"html_url\":\"https://github.com/choi3724/AMS2_KR/releases/tag/v0.88\",\"draft\":false,\"prerelease\":false,\"author\":{\"html_url\":\"https://example.com\"},\"assets\":[{\"name\":\"AMS2.0.88.zip\",\"size\":100,\"digest\":\"sha256:" + new string('a', 64) + "\",\"browser_download_url\":\"https://github.com/choi3724/AMS2_KR/releases/download/v0.88/AMS2.0.88.zip\"}]}";
            GithubReleaseInfo release = GithubUpdater.ParseRelease(json);
            Require(GithubUpdater.ParseRelease(json.Replace("AMS2.0.88.zip", "AMS2.CB.0.88.zip")).AssetUrl != null, "legacy ZIP naming rejected");
            Require(release.AssetBytes == 100 && release.Sha256.Length == 64, "release asset extraction");
            Refuses(() => GithubUpdater.ParseRelease(json.Replace("\"draft\":false", "\"draft\":true")), "draft accepted");
            Refuses(() => GithubUpdater.ParseRelease(json.Replace("sha256:", "sha1:")), "wrong digest accepted");
            Refuses(() => GithubUpdater.ParseRelease(json.Replace("/releases/download/", "/other/download/")), "untrusted asset path accepted");

            string zip = Path.Combine(output, "valid.zip");
            using (var archive = ZipFile.Open(zip, ZipArchiveMode.Create))
            using (var writer = new StreamWriter(archive.CreateEntry("package/manifest/direct-files.tsv").Open())) writer.Write("valid");
            string extracted = Path.Combine(output, "valid");
            GithubUpdater.ExtractPackage(zip, extracted, CancellationToken.None);
            Require(File.ReadAllText(Path.Combine(extracted, "package/manifest/direct-files.tsv")) == "valid", "valid extraction");
            string[] unsafeNames = { "../escaped.txt", "C:/escaped.txt", "file.txt:stream", "/rooted.txt" };
            for (int i = 0; i < unsafeNames.Length; i++)
            {
                string bad = Path.Combine(output, "bad" + i + ".zip");
                using (var archive = ZipFile.Open(bad, ZipArchiveMode.Create)) archive.CreateEntry(unsafeNames[i]);
                int index = i;
                Refuses(() => GithubUpdater.ExtractPackage(bad, Path.Combine(output, "bad" + index), CancellationToken.None), "unsafe zip path accepted");
            }
            Require(!File.Exists(Path.Combine(output, "escaped.txt")), "archive escaped extraction root");
            string duplicate = Path.Combine(output, "duplicate.zip");
            using (var archive = ZipFile.Open(duplicate, ZipArchiveMode.Create)) { archive.CreateEntry("file.txt"); archive.CreateEntry("FILE.TXT"); }
            Refuses(() => GithubUpdater.ExtractPackage(duplicate, Path.Combine(output, "duplicate"), CancellationToken.None), "duplicate Windows path accepted");
            Refuses(() => GithubUpdater.ExtractPackage(zip, Path.Combine(output, "cancelled"), new CancellationToken(true)), "cancel ignored");

            string package = Path.Combine(output, "installer");
            Directory.CreateDirectory(Path.Combine(package, "manifest"));
            File.WriteAllText(Path.Combine(package, "manifest/direct-files.tsv"), "header");
            File.Copy(args[1], Path.Combine(package, "AMS2 한국어 패치 오픈베타 0.88.exe"));
            Require(File.Exists(GithubUpdater.FindInstaller(package, "v0.88")), "new installer protocol not recognized");
            Refuses(() => GithubUpdater.FindInstaller(package, "v0.85"), "installer version mismatch accepted");
            Require(GameLauncher.Arguments(false) == "-applaunch 1066890 -novr -lang=Korean -looseloadtext", "desktop Steam arguments");
            Require(GameLauncher.Arguments(true) == "-applaunch 1066890 -forcevr -lang=Korean -looseloadtext", "VR Steam arguments");
            Console.WriteLine("PASS: version ordering, release validation, extraction boundaries, cancellation, installer protocol, desktop/VR launch arguments. No game or installer executed.");
            if (args.Length > 2 && args[2] == "--render")
            {
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                Render(output, "countdown-dialog.png", false, null, 1);
                Render(output, "update-dialog.png", false, release, 1);
                Render(output, "vr-dialog-150.png", true, null, 1.5F);
                Console.WriteLine("PASS: countdown, update choice, and VR 150% dialogs rendered; labels fit.");
            }
            if (args.Length > 2 && args[2] == "--startup")
            {
                Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                VerifyStartup(output, "current", Task.FromResult(new GithubReleaseInfo { Tag = "v0.88" }), false, false);
                var offline = new TaskCompletionSource<GithubReleaseInfo>(); offline.SetException(new IOException("offline test"));
                VerifyStartup(output, "offline", offline.Task, false, false);
                var slow = new TaskCompletionSource<GithubReleaseInfo>();
                VerifyStartup(output, "slow lookup", slow.Task, false, false);
                slow.SetResult(release); Application.DoEvents();
                VerifyStartup(output, "new version waits", Task.FromResult(new GithubReleaseInfo { Tag = "v" + new Version(0, 89) }), true, false);
                VerifyStartup(output, "manual launch", Task.FromResult(new GithubReleaseInfo { Tag = "v0.88" }), false, true);
                Console.WriteLine("PASS: five-second countdown, offline/slow fallback, new-version pause, and immediate launch. No game or installer executed.");
            }
            if (args.Length > 2 && (args[2] == "--live" || args[2] == "--download-legacy"))
            {
                GithubReleaseInfo live = GithubUpdater.Check();
                Console.WriteLine("LIVE: " + live.Tag + " / " + live.AssetName + " / " + live.AssetBytes + " / " + live.Sha256);
                if (args[2] == "--download-legacy")
                {
                    Require(live.Tag == "v0.7", "legacy-download test is pinned to v0.7");
                    try
                    {
                        GithubUpdater.DownloadPackage(live, text => { if (!text.Contains("%") || text.EndsWith("100%")) Console.WriteLine(text); }, CancellationToken.None);
                        throw new Exception("legacy installer unexpectedly accepted");
                    }
                    catch (InvalidDataException error)
                    {
                        Require(error.Message.Contains("실행 규약"), "download failed before legacy protocol check: " + error.Message);
                        Console.WriteLine("PASS: real ZIP downloaded, SHA-256 verified, extraction completed; legacy installer without update protocol refused. No installer executed.");
                    }
                }
            }
            return 0;
        }

        private static void HideTestWindow(Form form)
        {
            form.StartPosition = FormStartPosition.Manual; form.Location = new Point(-10000, -10000); form.ShowInTaskbar = false;
        }

        private static void CheckLabels(Control parent)
        {
            foreach (Control control in parent.Controls)
            {
                if (!control.Visible) continue;
                if (control is Button || control.Name == "LaunchCountdown" || control.Name == "PatchCreator" || control.Name == "PatchVersion")
                {
                    Require(control.Font.FontFamily.Name.StartsWith("Pretendard", StringComparison.Ordinal), "font fallback: " + control.Name);
                    using (Graphics graphics = control.CreateGraphics())
                        Require(control.Width >= graphics.MeasureString(control.Text, control.Font).Width + 8, "label does not fit: " + control.Text);
                    if (control is Label) Require(((Label)control).UseCompatibleTextRendering, "private label font must use GDI+");
                    if (control is Button) Require(((Button)control).UseCompatibleTextRendering, "private button font must use GDI+");
                    Require(parent.ClientRectangle.Contains(control.Bounds), "control outside parent: " + control.Name + " " + control.Bounds + " / " + parent.ClientRectangle);
                }
                CheckLabels(control);
            }
        }

        private static void Render(string output, string name, bool vr, GithubReleaseInfo info, float scale)
        {
            using (var form = new LauncherUpdateForm(output, vr))
            {
                HideTestWindow(form); form.Show();
                if (scale != 1) form.Scale(new SizeF(scale, scale));
                if (info != null) form.OfferUpdate(info, "0.88");
                form.PerformLayout();
                Require(form.Controls.Find("PatchCreator", true)[0].Text == "한글 패치 제작자 : ENGIceBlasT", "creator wording differs");
                Require(form.Controls.Find("PatchVersion", true)[0].Text.Contains("0.88"), "launcher must display 0.88");
                Console.WriteLine("FONT: " + form.Font.FontFamily.Name + " / " + name);
                using (var bitmap = new Bitmap(form.Width, form.Height))
                {
                    form.DrawToBitmap(bitmap, new Rectangle(0, 0, bitmap.Width, bitmap.Height));
                    bitmap.Save(Path.Combine(output, name));
                }
                CheckLabels(form);
            }
        }

        private static void VerifyStartup(string output, string name, Task<GithubReleaseInfo> check, bool offer, bool immediate)
        {
            using (var form = new LauncherUpdateForm(output, false))
            using (var deadline = new System.Windows.Forms.Timer { Interval = offer ? 5500 : 8000 })
            {
                HideTestWindow(form);
                Control counter = form.Controls.Find("LaunchCountdown", true)[0];
                HashSet<string> values = new HashSet<string>(); values.Add(counter.Text);
                counter.TextChanged += delegate { values.Add(counter.Text); };
                Stopwatch watch = new Stopwatch(); bool timedOut = false;
                deadline.Tick += delegate { timedOut = true; form.Close(); };
                form.Shown += async delegate
                {
                    watch.Start(); deadline.Start();
                    Task startup = form.RunStartup(check);
                    if (immediate) ((Button)form.AcceptButton).PerformClick();
                    await startup;
                };
                DialogResult result = form.ShowDialog(); deadline.Stop(); watch.Stop();
                if (offer) Require(timedOut && result != DialogResult.OK && counter.Text.Contains("새 한글패치"), "new release auto-launched");
                else if (immediate) Require(result == DialogResult.OK && watch.ElapsedMilliseconds < 1000, "manual launch did not skip countdown");
                else
                {
                    Require(!timedOut && result == DialogResult.OK && watch.ElapsedMilliseconds >= 4900 && watch.ElapsedMilliseconds < 7500, name + " countdown duration");
                    for (int n = 1; n <= 5; n++) Require(values.Contains(n + "초 후에 게임이 시작됩니다"), name + " missing countdown " + n);
                }
                Console.WriteLine("PASS: " + name + " / " + watch.ElapsedMilliseconds + " ms / " + result);
            }
            Application.DoEvents();
        }
    }
}
