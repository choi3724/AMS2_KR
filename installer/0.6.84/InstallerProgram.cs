using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Text;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Ams2KoreanBeta
{
    internal static class NativeWindowDrag
    {
        [DllImport("user32.dll")]
        public static extern bool ReleaseCapture();
        [DllImport("user32.dll")]
        public static extern IntPtr SendMessage(IntPtr handle, int message, IntPtr wParam, IntPtr lParam);
    }

    internal sealed class BorderedPanel : Panel
    {
        public Color BorderColor { get; set; }
        public BorderedPanel() { DoubleBuffered = true; }
        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            using (Pen pen = new Pen(BorderColor, 1F)) e.Graphics.DrawRectangle(pen, 0, 0, Math.Max(0, Width - 1), Math.Max(0, Height - 1));
        }
    }

    internal sealed class InstallerHero : Panel
    {
        private Image hero;
        private string heroPath;
        public string HeroPath
        {
            get { return heroPath; }
            set
            {
                heroPath = value;
                if (hero != null) { hero.Dispose(); hero = null; }
                if (!String.IsNullOrWhiteSpace(value) && File.Exists(value))
                {
                    using (Image source = Image.FromFile(value)) hero = new Bitmap(source);
                }
                Invalidate();
            }
        }

        public InstallerHero() { DoubleBuffered = true; BackColor = Color.FromArgb(22, 18, 19); }

        protected override void Dispose(bool disposing)
        {
            if (disposing && hero != null) { hero.Dispose(); hero = null; }
            base.Dispose(disposing);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            Rectangle bounds = ClientRectangle;
            if (hero != null && bounds.Width > 0 && bounds.Height > 0)
                e.Graphics.DrawImage(hero, bounds);
            using (Pen border = new Pen(Color.FromArgb(191, 35, 37), 2F)) e.Graphics.DrawRectangle(border, 1, 1, Math.Max(0, Width - 3), Math.Max(0, Height - 3));
        }
    }

    internal sealed class ActionButtonArtwork : IDisposable
    {
        public Image Normal;
        public Image Hover;
        public void Dispose()
        {
            if (Normal != null) { Normal.Dispose(); Normal = null; }
            if (Hover != null) { Hover.Dispose(); Hover = null; }
        }
    }

    internal sealed class InstallerForm : Form
    {
        private static readonly Color Canvas = Color.FromArgb(10, 10, 12);
        private static readonly Color Surface = Color.FromArgb(23, 20, 21);
        private static readonly Color SurfaceRaised = Color.FromArgb(31, 27, 28);
        private static readonly Color Line = Color.FromArgb(91, 61, 63);
        private static readonly Color TextPrimary = Color.FromArgb(245, 240, 238);
        private static readonly Color Muted = Color.FromArgb(185, 171, 170);
        private static readonly Color Accent = Color.FromArgb(202, 32, 34);
        private static readonly Color AccentBright = Color.FromArgb(242, 68, 62);
        private static readonly Color Success = Color.FromArgb(61, 190, 103);
        private static readonly Color Warning = Color.FromArgb(242, 171, 49);
        private static readonly Color Danger = Color.FromArgb(242, 68, 62);
        private static readonly PrivateFontCollection EmbeddedFonts = new PrivateFontCollection();
        private static FontFamily embeddedFontFamily;

        private readonly TextBox gamePath = new TextBox();
        private readonly Label statusBadge = new Label();
        private readonly Label statusDetail = new Label();
        private readonly RichTextBox log = new RichTextBox();
        private readonly CheckBox consent = new CheckBox();
        private readonly CheckBox desktopShortcut = new CheckBox();
        private readonly CheckBox startMenuShortcut = new CheckBox();
        private readonly CheckBox taskbarShortcut = new CheckBox();
        private readonly Button install = new Button();
        private readonly Button remove = new Button();
        private readonly Button check = new Button();
        private readonly Button diagnostic = new Button();
        private readonly Button launch = new Button();
        private readonly Button browse = new Button();
        private readonly Button detect = new Button();
        private readonly Button updateCheck = new Button();
        private readonly Button close = new Button();
        private readonly Label statusIcon = new Label();
        private PackageManifest manifest;

        public InstallerForm()
        {
            EnsureEmbeddedTypeface();
            Text = "Automobilista 2 한국어 패치 — Closed Beta 0.6.84";
            Font = UiFont(9F);
            BackColor = Color.FromArgb(115, 18, 21);
            Rectangle workArea = Screen.PrimaryScreen.WorkingArea;
            int targetWidth = Math.Min(1200, Math.Max(640, workArea.Width - 24));
            int targetHeight = Math.Min(860, Math.Max(640, workArea.Height - 24));
            ClientSize = new Size(targetWidth, targetHeight);
            MinimumSize = new Size(Math.Min(960, targetWidth), Math.Min(700, targetHeight));
            StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi;
            FormBorderStyle = FormBorderStyle.None;
            Padding = new Padding(2);
            ForeColor = TextPrimary;

            try
            {
                string iconPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "ams2-korean.ico");
                if (File.Exists(iconPath)) Icon = new Icon(iconPath);
            }
            catch { }

            TableLayoutPanel root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 4, BackColor = Canvas, Padding = new Padding(12, 0, 12, 0) };
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 45F));
            RowStyle heroRow = new RowStyle(SizeType.Absolute, 300F);
            root.RowStyles.Add(heroRow);
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 43F));
            root.Controls.Add(BuildTitleBar(), 0, 0);
            root.Controls.Add(BuildHeader(), 0, 1);
            root.Controls.Add(BuildBody(), 0, 2);
            root.Controls.Add(BuildFooter(), 0, 3);
            Controls.Add(root);
            EventHandler resizeLayout = delegate
            {
                heroRow.Height = Math.Max(160F, Math.Min(340F, root.ClientSize.Height - 560F));
            };
            root.Resize += resizeLayout;
            resizeLayout(root, EventArgs.Empty);
            Shown += delegate { FitWindowToWorkingArea(); LoadManifest(); AutoDetect(); CheckGithubUpdate(true); };
        }

        private void FitWindowToWorkingArea()
        {
            Rectangle workArea = Screen.FromControl(this).WorkingArea;
            int maxWidth = Math.Max(640, workArea.Width - 24);
            int maxHeight = Math.Max(640, workArea.Height - 24);
            MinimumSize = new Size(Math.Min(MinimumSize.Width, maxWidth), Math.Min(MinimumSize.Height, maxHeight));
            Size = new Size(Math.Min(Width, maxWidth), Math.Min(Height, maxHeight));
            Location = new Point(workArea.Left + Math.Max(0, (workArea.Width - Width) / 2), workArea.Top + Math.Max(0, (workArea.Height - Height) / 2));
        }

        private Control BuildTitleBar()
        {
            Panel bar = new Panel { Dock = DockStyle.Fill, BackColor = Color.FromArgb(15, 13, 15), Margin = new Padding(-12, 0, -12, 0) };
            Label icon = new Label { Text = "▰", ForeColor = AccentBright, Font = new Font("Segoe UI Symbol", 12F, FontStyle.Bold), TextAlign = ContentAlignment.MiddleCenter, Location = new Point(14, 0), Size = new Size(35, 43) };
            Label title = new Label { Text = "Automobilista 2 한국어 패치 — Closed Beta 0.6.84", ForeColor = TextPrimary, Font = UiFont(10.5F), TextAlign = ContentAlignment.MiddleLeft, Location = new Point(49, 0), Size = new Size(720, 43) };
            Button minimize = TitleButton("—"); Button maximize = TitleButton("□"); Button exit = TitleButton("×");
            minimize.Click += delegate { WindowState = FormWindowState.Minimized; };
            maximize.Click += delegate { WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized; };
            exit.Click += delegate { Close(); };
            bar.Controls.AddRange(new Control[] { icon, title, minimize, maximize, exit });
            bar.Resize += delegate { exit.Left = bar.ClientSize.Width - 48; maximize.Left = bar.ClientSize.Width - 96; minimize.Left = bar.ClientSize.Width - 144; };
            MouseEventHandler drag = delegate(object sender, MouseEventArgs e) { if (e.Button == MouseButtons.Left) { NativeWindowDrag.ReleaseCapture(); NativeWindowDrag.SendMessage(Handle, 0xA1, new IntPtr(2), IntPtr.Zero); } };
            bar.MouseDown += drag; title.MouseDown += drag; icon.MouseDown += drag;
            return bar;
        }

        private static Button TitleButton(string text)
        {
            Button button = new Button { Text = text, FlatStyle = FlatStyle.Flat, BackColor = Color.FromArgb(15, 13, 15), ForeColor = TextPrimary, Font = new Font("Segoe UI", 12F), Size = new Size(48, 43), Location = new Point(0, 0), Anchor = AnchorStyles.Top | AnchorStyles.Right, TabStop = false };
            button.FlatAppearance.BorderSize = 0; button.FlatAppearance.MouseOverBackColor = text == "×" ? Color.FromArgb(191, 31, 34) : Color.FromArgb(51, 44, 46);
            return button;
        }

        private Control BuildFooter()
        {
            Panel footer = new Panel { Dock = DockStyle.Fill, BackColor = Color.FromArgb(28, 13, 15), Margin = new Padding(-12, 6, -12, 0) };
            Label ready = new Label { Text = "●   준비 완료", ForeColor = Color.FromArgb(210, 201, 198), Font = UiFont(9F, FontStyle.Bold), TextAlign = ContentAlignment.MiddleLeft, Location = new Point(24, 0), Size = new Size(180, 37) };
            Label version = new Label { Text = "Automobilista 2 한국어 패치 — Closed Beta 0.6.84", ForeColor = Color.FromArgb(131, 118, 117), Font = UiFont(8.5F), TextAlign = ContentAlignment.MiddleRight, Anchor = AnchorStyles.Top | AnchorStyles.Right, Size = new Size(430, 37) };
            footer.Controls.AddRange(new Control[] { ready, version });
            footer.Resize += delegate { version.Left = footer.ClientSize.Width - version.Width - 26; };
            return footer;
        }

        private Control BuildHeader()
        {
            string heroPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "installer-hero.png");
            return new InstallerHero { Dock = DockStyle.Fill, Margin = new Padding(0, 0, 0, 10), HeroPath = heroPath };
        }

        private Control BuildBody()
        {
            TableLayoutPanel body = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = Canvas, Padding = new Padding(0), ColumnCount = 1, RowCount = 7 };
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 96F));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 78F));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 124F));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 64F));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 0F));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 34F));
            body.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));
            body.Controls.Add(BuildStatusCard(), 0, 0);
            body.Controls.Add(BuildPathCard(), 0, 1);
            body.Controls.Add(BuildOptionsCard(), 0, 2);
            body.Controls.Add(BuildActions(), 0, 3);
            body.Controls.Add(BuildLaunchNotice(), 0, 4);
            body.Controls.Add(BuildLogHeader(), 0, 5);
            ConfigureLog();
            body.Controls.Add(log, 0, 6);
            return body;
        }

        private Control BuildStatusCard()
        {
            Panel card = Card(new Padding(14, 10, 14, 8));
            ApplyPanelArtwork(card, "status-card-base.png");
            statusIcon.Visible = false;
            statusBadge.Text = "상태: 확인 전"; statusBadge.AutoSize = false; statusBadge.BackColor = Color.Transparent; statusBadge.ForeColor = AccentBright; statusBadge.Font = UiFont(12F, FontStyle.Bold); statusBadge.TextAlign = ContentAlignment.MiddleLeft; statusBadge.SetBounds(92, 18, 520, 28);
            statusDetail.Text = "게임 경로를 감지한 뒤 설치 상태를 확인합니다."; statusDetail.BackColor = Color.Transparent; statusDetail.ForeColor = Muted; statusDetail.Font = UiFont(9F); statusDetail.TextAlign = ContentAlignment.MiddleLeft; statusDetail.AutoEllipsis = true; statusDetail.SetBounds(92, 47, 535, 24);
            Label patchVersion = new Label { Text = PatchVersionValue(), BackColor = Color.FromArgb(15, 14, 15), ForeColor = Color.FromArgb(220, 207, 204), Font = UiFont(8.5F), TextAlign = ContentAlignment.MiddleLeft, AutoEllipsis = true };
            card.Resize += delegate
            {
                statusDetail.Width = Math.Max(300, card.ClientSize.Width - 700);
                int versionWidth = ScalePx(card, 135);
                int versionRight = ScalePx(card, 20);
                patchVersion.SetBounds(Math.Max(0, card.ClientSize.Width - versionWidth - versionRight), ScalePx(card, 43), versionWidth, ScalePx(card, 28));
                patchVersion.BringToFront();
            };
            card.Controls.AddRange(new Control[] { statusBadge, statusDetail, patchVersion });
            return card;
        }

        private static string PatchVersionValue()
        {
            const string prefix = "Closed Beta ";
            return PackageManifest.Version.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
                ? PackageManifest.Version.Substring(prefix.Length)
                : PackageManifest.Version;
        }

        private static int ScalePx(Control control, int value)
        {
            return (int)Math.Round(value * control.DeviceDpi / 96F);
        }

        private Control BuildPathCard()
        {
            Panel card = Card(new Padding(14, 7, 14, 7));
            Label label = new Label { Text = "Automobilista 2 경로", AutoSize = true, ForeColor = Muted, Font = UiFont(8.5F, FontStyle.Bold), Location = new Point(14, 6) };
            gamePath.BorderStyle = BorderStyle.FixedSingle; gamePath.BackColor = Color.FromArgb(13, 13, 15); gamePath.ForeColor = TextPrimary; gamePath.Font = UiFont(10F); gamePath.SetBounds(14, 28, 855, 30); gamePath.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            StyleSecondary(detect, "자동 감지", "detect"); detect.SetBounds(880, 27, 120, 32); detect.Anchor = AnchorStyles.Top | AnchorStyles.Right; detect.Click += delegate { AutoDetect(); };
            StyleSecondary(browse, "찾기", "browse"); browse.SetBounds(1010, 27, 110, 32); browse.Anchor = AnchorStyles.Top | AnchorStyles.Right; browse.Click += delegate { Browse(); };
            card.Resize += delegate { gamePath.Width = Math.Max(500, card.ClientSize.Width - 295); detect.Left = card.ClientSize.Width - 250; browse.Left = card.ClientSize.Width - 120; };
            card.Controls.AddRange(new Control[] { label, gamePath, detect, browse });
            return card;
        }

        private Control BuildActions()
        {
            TableLayoutPanel actions = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 7, Padding = new Padding(0, 5, 0, 5), BackColor = Canvas };
            for (int i = 0; i < 7; i++) actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 14.2857F));
            StylePrimary(install, "↓  설치", "install"); install.Click += delegate { if (!consent.Checked) MessageBox.Show(this, "비공식 패치 안내를 확인해 주세요.", "확인 필요", MessageBoxButtons.OK, MessageBoxIcon.Information); else Run("install"); };
            StyleDanger(remove, "↻  제거 / 복구", "restore"); remove.Click += delegate { ConfirmRemove(); };
            StyleSecondary(check, "⌕  상태 확인", "check"); check.Click += delegate { Run("check"); };
            StyleSuccess(launch, "▶  한국어로 실행", "launch"); launch.Click += delegate { Run("launch"); };
            StyleSecondary(diagnostic, "▣  진단 ZIP", "diagnostic"); diagnostic.Click += delegate { Run("diagnostic"); };
            StyleSecondary(updateCheck, "↻  업데이트 확인", "update"); updateCheck.Click += delegate { CheckGithubUpdate(false); };
            StyleGhost(close, "×  닫기", "close"); close.Click += delegate { Close(); };
            actions.Controls.Add(install, 0, 0); actions.Controls.Add(remove, 1, 0); actions.Controls.Add(check, 2, 0); actions.Controls.Add(launch, 3, 0); actions.Controls.Add(diagnostic, 4, 0); actions.Controls.Add(updateCheck, 5, 0); actions.Controls.Add(close, 6, 0);
            return actions;
        }

        private Control BuildOptionsCard()
        {
            Panel card = Card(new Padding(14, 9, 14, 7));
            Label heading = new Label { Text = "설치 옵션", AutoSize = true, ForeColor = TextPrimary, Font = UiFont(9.5F, FontStyle.Bold), Location = new Point(14, 10) };
            consent.Text = "이 프로그램은 비공식 패치이며, 코드가 서명되지 않았음을 확인했습니다."; consent.AutoSize = true; consent.ForeColor = Muted; consent.Location = new Point(14, 48);
            desktopShortcut.Text = "바탕화면에 바로가기 만들기"; desktopShortcut.AutoSize = true; desktopShortcut.ForeColor = TextPrimary; desktopShortcut.Location = new Point(125, 12); desktopShortcut.Checked = true;
            startMenuShortcut.Text = "시작 메뉴에 바로가기 만들기"; startMenuShortcut.AutoSize = true; startMenuShortcut.ForeColor = TextPrimary; startMenuShortcut.Location = new Point(370, 12); startMenuShortcut.Checked = true;
            taskbarShortcut.Text = "작업 표시줄에 고정"; taskbarShortcut.AutoSize = true; taskbarShortcut.ForeColor = TextPrimary; taskbarShortcut.Location = new Point(625, 12);
            Label hint = new Label { Text = "※ 작업표시줄 고정은 Windows 정책에 따라 즉시 표시되지 않을 수 있습니다.", AutoSize = false, AutoEllipsis = true, ForeColor = Muted, Location = new Point(625, 42), Size = new Size(500, 25), TextAlign = ContentAlignment.MiddleLeft, Anchor = AnchorStyles.Top | AnchorStyles.Right };
            consent.AutoSize = false;
            consent.AutoEllipsis = true;
            desktopShortcut.Margin = new Padding(0, 7, 28, 0);
            startMenuShortcut.Margin = new Padding(0, 7, 28, 0);
            taskbarShortcut.Margin = new Padding(0, 7, 28, 0);
            FlowLayoutPanel optionFlow = new FlowLayoutPanel { FlowDirection = FlowDirection.LeftToRight, WrapContents = true, AutoScroll = false, BackColor = Color.Transparent, Margin = new Padding(0), Padding = new Padding(0) };
            optionFlow.Controls.AddRange(new Control[] { desktopShortcut, startMenuShortcut, taskbarShortcut });
            card.Resize += delegate
            {
                int sidePadding = ScalePx(card, 14);
                int flowLeft = ScalePx(card, 115);
                int flowWidth = Math.Max(ScalePx(card, 260), card.ClientSize.Width - flowLeft - sidePadding);
                optionFlow.SetBounds(flowLeft, ScalePx(card, 3), flowWidth, ScalePx(card, 60));
                Size preferred = optionFlow.GetPreferredSize(new Size(flowWidth, 0));
                bool wrapped = preferred.Height > ScalePx(card, 38);
                optionFlow.Height = ScalePx(card, wrapped ? 60 : 38);
                int noticeY = ScalePx(card, wrapped ? 68 : 47);
                if (card.ClientSize.Width < ScalePx(card, 1100))
                {
                    int contentWidth = Math.Max(ScalePx(card, 200), card.ClientSize.Width - sidePadding * 2);
                    consent.SetBounds(sidePadding, noticeY, contentWidth, ScalePx(card, 24));
                    hint.SetBounds(sidePadding, noticeY + ScalePx(card, 25), contentWidth, ScalePx(card, 24));
                }
                else
                {
                    consent.SetBounds(sidePadding, noticeY, Math.Max(ScalePx(card, 300), card.ClientSize.Width - ScalePx(card, 560)), ScalePx(card, 24));
                    int hintLeft = Math.Max(ScalePx(card, 520), card.ClientSize.Width - ScalePx(card, 505));
                    hint.SetBounds(hintLeft, noticeY, Math.Max(ScalePx(card, 200), card.ClientSize.Width - hintLeft - sidePadding), ScalePx(card, 24));
                }
            };
            card.Controls.AddRange(new Control[] { heading, optionFlow, consent, hint });
            return card;
        }

        private Control BuildLaunchNotice()
        {
            return new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft, Padding = new Padding(14, 0, 14, 0), BackColor = Color.FromArgb(45, 20, 22), ForeColor = Color.FromArgb(242, 178, 174), Font = UiFont(9F, FontStyle.Bold), Text = "실행 안내  ·  반드시 생성된 바로가기 또는 ‘AMS2 Korean Launcher.exe’로 실행하십시오." };
        }

        private Control BuildLogHeader()
        {
            Panel header = new Panel { Dock = DockStyle.Fill, BackColor = Canvas };
            Label title = new Label { Text = "작업 로그", AutoSize = true, ForeColor = TextPrimary, Font = UiFont(9.5F, FontStyle.Bold), Location = new Point(2, 8) };
            Label hint = new Label { Text = "설치·복원 결과와 원본 검증 상태", AutoSize = true, ForeColor = Muted, Location = new Point(84, 9) };
            Button clear = new Button { Text = "로그 지우기", FlatStyle = FlatStyle.Flat, BackColor = Surface, ForeColor = Muted, Font = UiFont(8F), Size = new Size(90, 26), Anchor = AnchorStyles.Top | AnchorStyles.Right };
            clear.FlatAppearance.BorderColor = Line; clear.FlatAppearance.BorderSize = 1; clear.Location = new Point(1070, 3); clear.Click += delegate { log.Clear(); };
            header.Resize += delegate { clear.Left = header.ClientSize.Width - clear.Width; };
            header.Controls.AddRange(new Control[] { title, hint, clear }); return header;
        }

        private void ConfigureLog()
        {
            log.Dock = DockStyle.Fill; log.ReadOnly = true; log.BackColor = Color.FromArgb(8, 9, 11); log.ForeColor = Color.FromArgb(220, 214, 212); log.BorderStyle = BorderStyle.FixedSingle; log.Font = UiFont(8.5F); log.WordWrap = false; log.DetectUrls = false; log.Margin = new Padding(0);
        }

        private static Panel Card(Padding padding) { return new BorderedPanel { Dock = DockStyle.Fill, BackColor = Surface, BorderColor = Line, Padding = padding, Margin = new Padding(0, 0, 0, 8) }; }
        private static void StyleButton(Button button, string text, string artworkKey, Color back, Color fore, Color border)
        {
            button.Text = text; button.AccessibleName = text; button.Dock = DockStyle.Fill; button.Margin = new Padding(0, 0, 8, 0); button.FlatStyle = FlatStyle.Flat; button.BackColor = back; button.ForeColor = fore; button.FlatAppearance.BorderColor = border; button.FlatAppearance.BorderSize = 0; button.Font = UiFont(9F, FontStyle.Bold); button.Cursor = Cursors.Hand; button.BackgroundImageLayout = ImageLayout.Stretch;
            button.MouseEnter += delegate(object sender, EventArgs e) { ActionButtonArtwork art = ((Button)sender).Tag as ActionButtonArtwork; if (art != null) ((Button)sender).BackgroundImage = art.Hover; };
            button.MouseLeave += delegate(object sender, EventArgs e) { ActionButtonArtwork art = ((Button)sender).Tag as ActionButtonArtwork; if (art != null) ((Button)sender).BackgroundImage = art.Normal; };
            button.Disposed += delegate(object sender, EventArgs e) { Button b = (Button)sender; ActionButtonArtwork art = b.Tag as ActionButtonArtwork; b.BackgroundImage = null; if (art != null) art.Dispose(); b.Tag = null; };
            SetButtonArtwork(button, artworkKey, text);
        }

        private static void SetButtonArtwork(Button button, string key, string fallbackText)
        {
            ActionButtonArtwork old = button.Tag as ActionButtonArtwork;
            button.BackgroundImage = null;
            if (old != null) old.Dispose();
            button.Tag = null;
            string directory = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "buttons");
            string normalPath = Path.Combine(directory, key + ".png");
            string hoverPath = Path.Combine(directory, key + "-hover.png");
            if (!File.Exists(normalPath) || !File.Exists(hoverPath)) { button.Text = fallbackText; return; }
            ActionButtonArtwork art = new ActionButtonArtwork { Normal = LoadUnlockedImage(normalPath), Hover = LoadUnlockedImage(hoverPath) };
            button.Tag = art; button.Text = ""; button.AccessibleName = fallbackText; button.BackgroundImage = art.Normal;
        }

        private static Image LoadUnlockedImage(string path)
        {
            using (Image source = Image.FromFile(path)) return new Bitmap(source);
        }

        private static void ApplyPanelArtwork(Control control, string fileName)
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", fileName);
            if (!File.Exists(path)) return;
            Image image = LoadUnlockedImage(path);
            control.BackgroundImage = image;
            control.BackgroundImageLayout = ImageLayout.Stretch;
            control.Disposed += delegate { control.BackgroundImage = null; image.Dispose(); };
        }

        private static void EnsureEmbeddedTypeface()
        {
            if (embeddedFontFamily != null) return;
            try
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "assets", "Pretendard-Medium.otf");
                if (File.Exists(path)) { EmbeddedFonts.AddFontFile(path); if (EmbeddedFonts.Families.Length > 0) embeddedFontFamily = EmbeddedFonts.Families[0]; }
            }
            catch { embeddedFontFamily = null; }
        }

        private static Font UiFont(float size) { return UiFont(size, FontStyle.Regular); }
        private static Font UiFont(float size, FontStyle style)
        {
            EnsureEmbeddedTypeface();
            float renderedSize = size * 1.15F;
            if (embeddedFontFamily != null)
            {
                FontStyle available = embeddedFontFamily.IsStyleAvailable(style) ? style : FontStyle.Regular;
                return new Font(embeddedFontFamily, renderedSize, available, GraphicsUnit.Point);
            }
            return new Font("Malgun Gothic", size, style, GraphicsUnit.Point);
        }

        private static void StylePrimary(Button b, string t, string key) { StyleButton(b, t, key, Accent, Color.White, Accent); }
        private static void StyleSuccess(Button b, string t, string key) { StyleButton(b, t, key, SurfaceRaised, Color.FromArgb(242, 163, 158), Line); }
        private static void StyleDanger(Button b, string t, string key) { StyleButton(b, t, key, SurfaceRaised, Color.FromArgb(242, 163, 158), Line); }
        private static void StyleSecondary(Button b, string t, string key) { StyleButton(b, t, key, SurfaceRaised, TextPrimary, Line); }
        private static void StyleGhost(Button b, string t, string key) { StyleButton(b, t, key, Color.FromArgb(18, 17, 19), Muted, Line); }

        private void ConfirmRemove()
        {
            DialogResult answer = MessageBox.Show(this, "한국어 패치가 덮어쓴 파일은 설치 전 원본으로 복원하고, 패치가 만든 파일과 바로가기는 제거합니다.\n\n복원 후 파일 해시까지 검증합니다. 계속하시겠습니까?", "영문 원본으로 복원", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (answer == DialogResult.Yes) Run("remove");
        }

        private void CheckGithubUpdate(bool silent)
        {
            updateCheck.Enabled = false;
            Task.Factory.StartNew(delegate { return GithubUpdater.Check(); }).ContinueWith(delegate(Task<GithubReleaseInfo> t)
            {
                BeginInvoke((MethodInvoker)delegate
                {
                    updateCheck.Enabled = true;
                    if (t.IsFaulted) { if (!silent) MessageBox.Show(this, "GitHub 업데이트 정보를 가져오지 못했습니다.", "업데이트 확인", MessageBoxButtons.OK, MessageBoxIcon.Information); return; }
                    GithubReleaseInfo info = t.Result;
                    if (!GithubUpdater.IsNewer(info.Tag, PackageManifest.Version)) { if (!silent) MessageBox.Show(this, "현재 최신 버전입니다.", "업데이트 확인", MessageBoxButtons.OK, MessageBoxIcon.Information); return; }
                    DialogResult answer = MessageBox.Show(this, info.Tag + " 버전이 있습니다. GitHub 배포 페이지를 여시겠습니까?", "업데이트 가능", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                    if (answer == DialogResult.Yes) Process.Start(info.PageUrl);
                });
            });
        }

        private void LoadManifest() { try { manifest = PackageManifest.Load(AppDomain.CurrentDomain.BaseDirectory); } catch (Exception e) { SetStatus("PACKAGE_ERROR", "패키지 오류: " + e.Message, true); SetEnabled(false); } }

        private void AutoDetect()
        {
            if (manifest == null) return;
            try { var list = SteamLocator.Detect(); if (list.Count == 0) throw new InvalidOperationException("Steam 설치를 자동 감지하지 못했습니다."); gamePath.Text = list[0].GameDir; Append("자동 감지: " + list[0].GameDir); Run("check"); }
            catch (Exception e) { SetStatus("PATH_REQUIRED", e.Message + " 찾기 버튼으로 직접 선택할 수 있습니다.", true); }
        }

        private void Browse()
        {
            using (FolderBrowserDialog d = new FolderBrowserDialog()) { d.Description = "Automobilista 2 게임 폴더를 선택하십시오."; d.SelectedPath = gamePath.Text; if (d.ShowDialog(this) == DialogResult.OK) { gamePath.Text = d.SelectedPath; Run("check"); } }
        }

        private void Run(string action)
        {
            if (manifest == null || String.IsNullOrWhiteSpace(gamePath.Text)) return;
            string selected = gamePath.Text; string diag = null;
            if (action == "diagnostic")
            {
                using (SaveFileDialog d = new SaveFileDialog()) { d.Filter = "ZIP 파일|*.zip"; d.FileName = "AMS2-Korean-Beta0684-Diagnostic-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".zip"; if (d.ShowDialog(this) != DialogResult.OK) return; diag = d.FileName; }
            }
            ShortcutOptions shortcuts = action == "install" ? new ShortcutOptions { Desktop = desktopShortcut.Checked, StartMenu = startMenuShortcut.Checked, Taskbar = taskbarShortcut.Checked } : null;
            SetEnabled(false); SetStatus("WORKING", ActionText(action) + " 작업을 진행하고 있습니다.", false); Append(ActionText(action) + " 작업 시작");
            Task.Factory.StartNew(delegate
            {
                try
                {
                    GameInfo game = SteamLocator.FromGameDirectory(selected); BetaEngine engine = new BetaEngine(manifest, AppendThreadSafe, false);
                    if (action == "install") return engine.Install(game, shortcuts);
                    if (action == "remove") return engine.Uninstall(game);
                    if (action == "launch") return engine.LaunchKorean(game);
                    if (action == "diagnostic") return engine.Diagnose(game, diag);
                    return engine.Check(game);
                }
                catch (Exception e) { return new OperationResult { Success = false, Status = "FAILED", Message = e.Message }; }
            }).ContinueWith(delegate(Task<OperationResult> t)
            {
                BeginInvoke((MethodInvoker)delegate
                {
                    SetEnabled(true); OperationResult r = t.Result; ApplyInstallButton(r.Status); string message = DisplayText(r.Message); SetStatus(r.Status, message, !r.Success); Append("완료: " + DisplayStatus(r.Status) + " / " + message); if (!String.IsNullOrEmpty(r.LogPath)) Append("증거/로그: " + r.LogPath); if (!r.Success && action != "check") MessageBox.Show(this, r.Message, "작업 실패", MessageBoxButtons.OK, MessageBoxIcon.Error);
                });
            });
        }

        private static string ActionText(string action) { if (action == "install") return "설치"; if (action == "remove") return "제거 및 원복"; if (action == "check") return "상태 확인"; if (action == "launch") return "한국어 실행"; if (action == "diagnostic") return "진단 ZIP 생성"; return action; }
        private void AppendThreadSafe(string text) { if (!IsDisposed) BeginInvoke((MethodInvoker)delegate { Append(text); }); }
        private void Append(string text) { log.AppendText("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + text + Environment.NewLine); log.SelectionStart = log.TextLength; log.ScrollToCaret(); }

        private void SetStatus(string state, string detail, bool error)
        {
            statusBadge.Text = "상태: " + DisplayStatus(state); statusDetail.Text = detail; Color color = error ? Danger : StatusColor(state); statusBadge.BackColor = Color.Transparent; statusBadge.ForeColor = color; statusIcon.ForeColor = color; statusIcon.BackColor = StatusBackColor(state, error); statusIcon.Text = error ? "!" : (state == "WORKING" ? "…" : "✓");
        }

        private static Color StatusBackColor(string value, bool error)
        {
            if (error || value == "MIXED_OR_INCOMPLETE" || value == "BACKUP_MISSING_OR_DAMAGED" || value == "MANUAL_CHANGES_DETECTED") return Color.FromArgb(76, 24, 27);
            if (value == "INSTALLED_EXACT" || value == "UPDATED_EXACT" || value == "RESTORED_EXACT" || value == "STOCK_ENGLISH" || value == "LAUNCHED_KOREAN" || value == "DIAGNOSTIC_CREATED") return Color.FromArgb(21, 57, 37);
            if (value == "UPDATE_AVAILABLE" || value == "WORKING") return Color.FromArgb(68, 49, 18);
            return Color.FromArgb(72, 29, 31);
        }

        private static Color StatusColor(string value)
        {
            if (value == "INSTALLED_EXACT" || value == "UPDATED_EXACT" || value == "RESTORED_EXACT" || value == "STOCK_ENGLISH" || value == "LAUNCHED_KOREAN" || value == "DIAGNOSTIC_CREATED") return Success;
            if (value == "UPDATE_AVAILABLE" || value == "WORKING") return Warning;
            if (value == "MIXED_OR_INCOMPLETE" || value == "BACKUP_MISSING_OR_DAMAGED" || value == "MANUAL_CHANGES_DETECTED") return Danger;
            return TextPrimary;
        }

        private static string DisplayStatus(string value)
        {
            if (value == "UPDATE_AVAILABLE") return "업데이트 필요"; if (value == "UPDATED_EXACT") return "한국어 패치 업데이트 완료"; if (value == "INSTALLED_EXACT") return "한국어 패치 설치 완료"; if (value == "RESTORED_EXACT") return "영문 원본 복원 완료"; if (value == "STOCK_ENGLISH") return "순정 영문 원본"; if (value == "MIXED_OR_INCOMPLETE") return "혼합 / 불완전 상태"; if (value == "BACKUP_MISSING_OR_DAMAGED") return "백업 손상 / 누락"; if (value == "MANUAL_CHANGES_DETECTED") return "수동 변경 감지"; if (value == "NOT_INSTALLED") return "한글 패치 미설치"; if (value == "LAUNCHED_KOREAN") return "한국어 게임 실행 완료"; if (value == "DIAGNOSTIC_CREATED") return "진단 ZIP 생성 완료"; if (value == "WORKING") return "처리 중"; if (value == "PATH_REQUIRED") return "경로 선택 필요"; if (value == "PACKAGE_ERROR") return "패키지 오류"; return value;
        }

        private void ApplyInstallButton(string state) { bool update = state == "UPDATE_AVAILABLE"; SetButtonArtwork(install, update ? "install-update" : "install", update ? "↓  업데이트" : "↓  설치"); }
        private static string DisplayText(string value) { return (value ?? "").Replace("INSTALLED_EXACT", "한글 패치 설치 완료").Replace("RESTORED_EXACT", "영문 원본 복원 완료").Replace("STOCK_ENGLISH", "순정 영문 원본").Replace("NOT_INSTALLED", "한글 패치 미설치"); }
        private void SetEnabled(bool enabled) { install.Enabled = enabled; remove.Enabled = enabled; check.Enabled = enabled; launch.Enabled = enabled; diagnostic.Enabled = enabled; updateCheck.Enabled = enabled; browse.Enabled = enabled; detect.Enabled = enabled; desktopShortcut.Enabled = enabled; startMenuShortcut.Enabled = enabled; taskbarShortcut.Enabled = enabled; }
    }

    internal sealed class GithubReleaseInfo { public string Tag; public string PageUrl; }

    internal static class GithubUpdater
    {
        private const string LatestReleaseApi = "https://api.github.com/repos/choi3724/AMS2_KR/releases/latest";
        public static GithubReleaseInfo Check()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12; HttpWebRequest request = (HttpWebRequest)WebRequest.Create(LatestReleaseApi); request.UserAgent = "AMS2-Korean-Patch-Updater/0.6.84"; request.Accept = "application/vnd.github+json"; request.Timeout = 6000; string json;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse()) using (StreamReader reader = new StreamReader(response.GetResponseStream())) json = reader.ReadToEnd();
            string tag = ReadJsonString(json, "tag_name"); string page = ReadJsonString(json, "html_url"); if (String.IsNullOrWhiteSpace(tag) || String.IsNullOrWhiteSpace(page)) throw new InvalidOperationException("GitHub release metadata is incomplete."); return new GithubReleaseInfo { Tag = tag, PageUrl = page };
        }
        public static bool IsNewer(string remote, string current) { return ParseVersion(remote).CompareTo(ParseVersion(current)) > 0; }
        private static System.Version ParseVersion(string value) { Match match = Regex.Match(value ?? "", "(?<major>\\d+)\\.(?<minor>\\d+)\\.(?<patch>\\d+)"); if (!match.Success) return new System.Version(0, 0, 0); return new System.Version(Int32.Parse(match.Groups["major"].Value), Int32.Parse(match.Groups["minor"].Value), Int32.Parse(match.Groups["patch"].Value)); }
        private static string ReadJsonString(string json, string name) { Match match = Regex.Match(json ?? "", "\\\"" + Regex.Escape(name) + "\\\"\\s*:\\s*\\\"(?<value>(?:\\\\.|[^\\\"])*)\\\""); return match.Success ? match.Groups["value"].Value.Replace("\\/", "/") : null; }
    }

    internal static class InstallerProgram
    {
        [STAThread]
        public static void Main() { Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false); Application.Run(new InstallerForm()); }
    }
}
