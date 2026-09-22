using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Text;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Ams2KoreanBeta
{
    internal sealed class LauncherLabel : Label
    {
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.TextRenderingHint = TextRenderingHint.AntiAlias;
            base.OnPaint(e);
        }
    }

    internal sealed class LauncherButton : Button
    {
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.TextRenderingHint = TextRenderingHint.AntiAlias;
            base.OnPaint(e);
        }
    }

    internal sealed class LauncherUpdateForm : Form
    {
        private readonly string game;
        private readonly bool vr;
        private readonly PrivateFontCollection typeface = new PrivateFontCollection();
        private GCHandle fontMemory;
        private Font bodyFont, headingFont, creditFont;
        private readonly Label message = new LauncherLabel { Name = "UpdateStatus", Text = "한글패치 업데이트를 확인하고 있습니다…", UseCompatibleTextRendering = true, AutoEllipsis = true, ForeColor = Color.FromArgb(180, 183, 189) };
        private readonly Label countdown = new LauncherLabel { Name = "LaunchCountdown", Text = "5초 후에 게임이 시작됩니다", UseCompatibleTextRendering = true };
        private readonly Button play = ActionButton("지금 실행", false);
        private readonly Button update = ActionButton("업데이트 후 실행", true);
        private readonly Panel progress = new Panel { BackColor = Color.FromArgb(218, 35, 42), Width = 0, Dock = DockStyle.Left };
        private readonly PictureBox hero = new PictureBox { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.StretchImage, Margin = Padding.Empty };
        private readonly System.Windows.Forms.Timer ticker = new System.Windows.Forms.Timer { Interval = 100 };
        private readonly Stopwatch elapsed = new Stopwatch();
        private readonly CancellationTokenSource cancel = new CancellationTokenSource();
        private GithubReleaseInfo release;
        private readonly string current;
        private bool started;
        private const int StartupMilliseconds = 5000;

        public LauncherUpdateForm(string game, bool vr)
        {
            this.game = game; this.vr = vr;
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("Ams2KoreanBeta.Pretendard"))
            {
                if (resource == null) throw new InvalidDataException("런처에 포함된 Pretendard 폰트를 찾지 못했습니다.");
                using (MemoryStream buffer = new MemoryStream())
                {
                    resource.CopyTo(buffer);
                    byte[] bytes = buffer.ToArray();
                    fontMemory = GCHandle.Alloc(bytes, GCHandleType.Pinned);
                    typeface.AddMemoryFont(fontMemory.AddrOfPinnedObject(), bytes.Length);
                }
            }
            bodyFont = new Font(typeface.Families[0], 10F, FontStyle.Regular);
            headingFont = new Font(typeface.Families[0], 18F, FontStyle.Bold);
            creditFont = new Font(typeface.Families[0], 12F, FontStyle.Bold);
            countdown.Font = headingFont;
            Version version = Assembly.GetExecutingAssembly().GetName().Version;
            current = version.ToString(version.Revision > 0 ? 4 : version.Build > 0 ? 3 : 2);
            Text = "Automobilista 2 | 한국어 패치 런처"; ClientSize = new Size(720, 496);
            Font = bodyFont; ForeColor = Color.FromArgb(245, 246, 248); BackColor = Color.FromArgb(18, 19, 22);
            AutoScaleDimensions = new SizeF(96F, 96F); AutoScaleMode = AutoScaleMode.Dpi;
            StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false; MinimizeBox = false;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            using (Stream artwork = Assembly.GetExecutingAssembly().GetManifestResourceStream("Ams2KoreanBeta.LauncherHero"))
                if (artwork != null) using (Image original = Image.FromStream(artwork)) hero.Image = new Bitmap(original);

            TableLayoutPanel root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3, Margin = Padding.Empty, Padding = Padding.Empty };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 240));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 56));
            root.Controls.Add(hero, 0, 0);
            Panel body = new Panel { Size = new Size(720, 200), Dock = DockStyle.Fill, Margin = Padding.Empty, Padding = new Padding(24, 16, 24, 16) };
            message.SetBounds(24, 16, 672, 25); message.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            countdown.SetBounds(21, 48, 675, 44); countdown.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            Panel track = new Panel { BackColor = Color.FromArgb(49, 50, 55), Height = 3, Dock = DockStyle.Top };
            track.Controls.Add(progress);
            Panel progressHolder = new Panel { Height = 18, Dock = DockStyle.Bottom };
            progressHolder.Controls.Add(track);
            FlowLayoutPanel buttons = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 44, FlowDirection = FlowDirection.RightToLeft, WrapContents = false };
            buttons.Controls.Add(update); buttons.Controls.Add(play);
            body.Controls.Add(message); body.Controls.Add(countdown); body.Controls.Add(progressHolder); body.Controls.Add(buttons);
            root.Controls.Add(body, 0, 1);
            Panel footer = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty, BackColor = Color.FromArgb(10, 11, 13), Padding = new Padding(24, 0, 24, 0) };
            Label creator = new LauncherLabel { Name = "PatchCreator", Text = "한글 패치 제작자 : ENGIceBlasT", UseCompatibleTextRendering = true, Dock = DockStyle.Left, Width = 360, TextAlign = ContentAlignment.MiddleLeft, Font = creditFont };
            Label patchVersion = new LauncherLabel { Name = "PatchVersion", Text = "한글패치 " + current + (vr ? "  ·  VR 실행" : "  ·  일반 실행"), UseCompatibleTextRendering = true, Dock = DockStyle.Right, Width = 270, TextAlign = ContentAlignment.MiddleRight, ForeColor = message.ForeColor, Font = creditFont };
            footer.Controls.Add(creator); footer.Controls.Add(patchVersion); root.Controls.Add(footer, 0, 2);
            Controls.Add(root); update.Visible = false;
            play.DialogResult = DialogResult.OK; AcceptButton = play;
            ticker.Tick += delegate { RenderCountdown(); };
            update.Click += InstallUpdate;
            FormClosed += delegate { ticker.Stop(); cancel.Cancel(); };
        }

        private static Button ActionButton(string text, bool primary)
        {
            Button button = new LauncherButton { Text = text, UseCompatibleTextRendering = true, Size = new Size(178, 40), Margin = new Padding(8, 0, 0, 0), FlatStyle = FlatStyle.Flat,
                ForeColor = Color.White, BackColor = primary ? Color.FromArgb(202, 32, 34) : Color.FromArgb(38, 40, 45), UseVisualStyleBackColor = false };
            button.FlatAppearance.BorderColor = primary ? Color.FromArgb(202, 32, 34) : Color.FromArgb(75, 77, 84);
            button.FlatAppearance.MouseOverBackColor = primary ? Color.FromArgb(230, 43, 46) : Color.FromArgb(57, 59, 65);
            return button;
        }

        private void RenderCountdown()
        {
            int remaining = Math.Max(0, (int)Math.Ceiling((StartupMilliseconds - elapsed.Elapsed.TotalMilliseconds) / 1000));
            countdown.Text = remaining == 0 ? "게임을 시작합니다…" : remaining + "초 후에 게임이 시작됩니다";
            progress.Width = (int)(progress.Parent.ClientSize.Width * Math.Min(1, elapsed.Elapsed.TotalMilliseconds / StartupMilliseconds));
        }

        private static async Task<GithubReleaseInfo> AvailableRelease(Task<GithubReleaseInfo> check)
        {
            try { return await check; } catch { return null; }
        }

        internal async void CheckUpdate(object sender, EventArgs e) { await RunStartup(Task.Run(() => GithubUpdater.Check())); }

        internal async Task RunStartup(Task<GithubReleaseInfo> check)
        {
            if (started || IsDisposed) return;
            started = true; elapsed.Restart(); ticker.Start(); RenderCountdown();
            try
            {
                Task<GithubReleaseInfo> lookup = AvailableRelease(check);
                Task deadline = Task.Delay(StartupMilliseconds, cancel.Token);
                await Task.WhenAny(lookup, deadline);
                if (IsDisposed || cancel.IsCancellationRequested) return;
                GithubReleaseInfo found = lookup.Status == TaskStatus.RanToCompletion ? lookup.Result : null;
                if (found != null && GithubUpdater.IsNewer(found.Tag, current)) { OfferUpdate(found, current); return; }
                message.Text = found == null ? "업데이트 정보를 확인하지 못했습니다. 현재 버전으로 실행합니다." : "최신 한글패치가 적용되어 있습니다.";
                await deadline;
                if (!IsDisposed && !cancel.IsCancellationRequested) { DialogResult = DialogResult.OK; Close(); }
            }
            catch (OperationCanceledException) { }
            catch (Exception error)
            {
                if (!IsDisposed) { ticker.Stop(); countdown.Text = "현재 버전으로 실행할 수 있습니다"; message.Text = error.Message; }
            }
        }

        internal void OfferUpdate(GithubReleaseInfo info, string current)
        {
            ticker.Stop(); release = info;
            message.Text = "현재 버전 " + current + "  →  새 버전 " + release.Tag;
            countdown.Text = "새 한글패치를 사용할 수 있습니다";
            progress.Width = progress.Parent.ClientSize.Width;
            play.Text = "현재 버전으로 실행";
            update.Visible = true; AcceptButton = update;
        }

        private async void InstallUpdate(object sender, EventArgs e)
        {
            play.Enabled = false; update.Enabled = false;
            countdown.Text = "한글패치를 업데이트하고 있습니다";
            IProgress<string> progress = new Progress<string>(text => { if (!IsDisposed) message.Text = text; });
            try
            {
                string installer = await Task.Run(() => GithubUpdater.DownloadPackage(release, progress.Report, cancel.Token));
                if (IsDisposed) return;
                string args = "--update-and-launch \"" + game.TrimEnd('\\') + "\" --parent " + Process.GetCurrentProcess().Id + " --expected-version " + release.Tag + (vr ? " --vr" : "");
                Process.Start(new ProcessStartInfo(installer, args) { WorkingDirectory = Path.GetDirectoryName(installer), UseShellExecute = true, Verb = "runas" });
                // Exit before the installer replaces this running launcher.
                DialogResult = DialogResult.Yes; Close();
            }
            catch (Exception error)
            {
                if (IsDisposed) return;
                countdown.Text = "업데이트를 완료하지 못했습니다";
                message.Text = "업데이트를 완료하지 못했습니다. 현재 버전으로 실행하거나 다시 시도할 수 있습니다.";
                MessageBox.Show(this, error.Message, "업데이트 확인", MessageBoxButtons.OK, MessageBoxIcon.Information);
                play.Enabled = true; update.Enabled = true;
            }
        }

        protected override void Dispose(bool disposing)
        {
            bool releaseResources = disposing && !IsDisposed;
            if (releaseResources)
            {
                ticker.Dispose(); cancel.Cancel(); cancel.Dispose();
                if (hero.Image != null) { hero.Image.Dispose(); hero.Image = null; }
            }
            base.Dispose(disposing);
            if (releaseResources)
            {
                if (bodyFont != null) bodyFont.Dispose();
                if (headingFont != null) headingFont.Dispose();
                if (creditFont != null) creditFont.Dispose();
                typeface.Dispose();
                if (fontMemory.IsAllocated) fontMemory.Free();
            }
        }
    }

    internal static class LauncherProgram
    {
        [STAThread]
        public static int Main(string[] args)
        {
            try
            {
                bool owner;
                using (Mutex single = new Mutex(true, @"Local\AMS2-Korean-Launcher-1066890", out owner))
                {
                    if (!owner) return 0;
                    string game = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
                    if (args.Length != 0)
                    {
                        if (args.Length != 2 || args[0] != "--game-dir") throw new ArgumentException("usage: --game-dir PATH");
                        game = Path.GetFullPath(args[1]).TrimEnd(Path.DirectorySeparatorChar);
                        SteamLocator.FromGameDirectory(game);
                    }
                    if (!File.Exists(Path.Combine(game, "AMS2.exe"))) throw new FileNotFoundException("AMS2.exe를 찾지 못했습니다.");
#if VR_LAUNCHER
                    const bool vr = true;
#else
                    const bool vr = false;
#endif
                    Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                    using (var dialog = new LauncherUpdateForm(game, vr))
                    {
                        dialog.Shown += dialog.CheckUpdate;
                        if (dialog.ShowDialog() == DialogResult.OK) GameLauncher.Start(game, vr);
                    }
                }
                return 0;
            }
            catch (Exception e)
            {
                MessageBox.Show(e.Message, "AMS2 한국어 실행 실패", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }
    }
}
