using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Ams2KoreanBeta
{
    internal sealed class InstallerForm : Form
    {
        private readonly TextBox gamePath = new TextBox();
        private readonly Label status = new Label();
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
        private PackageManifest manifest;

        public InstallerForm()
        {
            Text = "AMS2 Korean Patch Closed Beta 0.6.3";
            Font = new Font("Malgun Gothic", 9F);
            Width = 860; Height = 735;
            StartPosition = FormStartPosition.CenterScreen;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;

            Label title = new Label { Text = "Automobilista 2 한국어 패치 — Closed Beta 0.6.3", Left = 20, Top = 18, Width = 780, Height = 30, Font = new Font("Malgun Gothic", 15F, FontStyle.Bold) };
            Label warning = new Label { Text = "이 한글 패치는 Steam public build 24132163 기준으로 최적화되어 있습니다.", Left = 20, Top = 55, Width = 800, Height = 24, ForeColor = Color.DarkRed };
            Label creator = new Label { Text = "한글패치 제작자명 : ENGIceBlasT", Left = 20, Top = 82, Width = 400, Height = 24, ForeColor = Color.DarkBlue, Font = new Font("Malgun Gothic", 9F, FontStyle.Bold) };
            Label pathLabel = new Label { Text = "Automobilista 2 경로", Left = 20, Top = 112, Width = 180 };
            gamePath.SetBounds(20, 135, 630, 28);
            detect.Text = "자동 감지"; detect.SetBounds(660, 133, 80, 30); detect.Click += delegate { AutoDetect(); };
            browse.Text = "찾기"; browse.SetBounds(745, 133, 75, 30); browse.Click += delegate { Browse(); };

            status.Text = "상태: 확인 전"; status.SetBounds(20, 176, 800, 32); status.Font = new Font("Malgun Gothic", 10F, FontStyle.Bold);
            consent.Text = "이 프로그램은 비 공식 패치이며, 코드가 서명되지 않았음을 확인했습니다."; consent.SetBounds(20, 213, 720, 28);

            Label shortcutLabel = new Label { Text = "한국어 런처 바로가기", Left = 20, Top = 246, Width = 180, Height = 24, Font = new Font("Malgun Gothic", 9F, FontStyle.Bold) };
            desktopShortcut.Text = "바탕화면"; desktopShortcut.SetBounds(200, 244, 110, 28); desktopShortcut.Checked = true;
            startMenuShortcut.Text = "시작 화면/메뉴"; startMenuShortcut.SetBounds(320, 244, 150, 28); startMenuShortcut.Checked = true;
            taskbarShortcut.Text = "작업표시줄"; taskbarShortcut.SetBounds(480, 244, 120, 28);
            Label taskbarHelp = new Label { Text = "※ 작업표시줄 고정은 Windows 정책에 따라 즉시 표시되지 않을 수 있습니다.", Left = 20, Top = 274, Width = 700, Height = 24, ForeColor = Color.DimGray };

            install.Text = "설치"; install.SetBounds(20, 310, 105, 38); install.Click += delegate { if (!consent.Checked) MessageBox.Show("안내 확인란을 선택하십시오."); else Run("install"); };
            remove.Text = "제거 / 복구"; remove.SetBounds(135, 310, 120, 38); remove.Click += delegate { Run("remove"); };
            check.Text = "상태 확인"; check.SetBounds(265, 310, 105, 38); check.Click += delegate { Run("check"); };
            launch.Text = "한국어로 실행"; launch.SetBounds(380, 310, 125, 38); launch.Click += delegate { Run("launch"); };
            diagnostic.Text = "진단 ZIP"; diagnostic.SetBounds(515, 310, 105, 38); diagnostic.Click += delegate { Run("diagnostic"); };
            updateCheck.Text = "업데이트 확인"; updateCheck.SetBounds(625, 310, 85, 38); updateCheck.Click += delegate { CheckGithubUpdate(false); };
            Button close = new Button { Text = "닫기", Left = 715, Top = 310, Width = 105, Height = 38 }; close.Click += delegate { Close(); };

            Label launchHelp = new Label { Text = "중요: Steam의 기본 '플레이' 대신 이 버튼, 생성한 바로가기 아이콘 또는 'AMS2 Korean Launcher.exe'를 사용하십시오.", Left = 20, Top = 357, Width = 800, Height = 25, ForeColor = Color.DarkBlue };
            log.SetBounds(20, 389, 800, 285); log.ReadOnly = true; log.BackColor = Color.White; log.WordWrap = false;
            Controls.AddRange(new Control[] { title, warning, creator, pathLabel, gamePath, detect, browse, status, consent, shortcutLabel, desktopShortcut, startMenuShortcut, taskbarShortcut, taskbarHelp, install, remove, check, launch, diagnostic, updateCheck, close, launchHelp, log });
            Shown += delegate { LoadManifest(); AutoDetect(); CheckGithubUpdate(true); };
        }

        private void CheckGithubUpdate(bool silent)
        {
            updateCheck.Enabled = false;
            Task.Factory.StartNew(delegate { return GithubUpdater.Check(); }).ContinueWith(delegate(Task<GithubReleaseInfo> t)
            {
                BeginInvoke((MethodInvoker)delegate
                {
                    updateCheck.Enabled = true;
                    if (t.IsFaulted)
                    {
                        if (!silent) MessageBox.Show(this, "GitHub 업데이트 정보를 가져오지 못했습니다. 저장소가 비공개이면 외부 PC에서 자동 업데이트를 사용할 수 없습니다.", "업데이트 확인", MessageBoxButtons.OK, MessageBoxIcon.Information);
                        return;
                    }
                    GithubReleaseInfo info = t.Result;
                    if (!GithubUpdater.IsNewer(info.Tag, PackageManifest.Version))
                    {
                        if (!silent) MessageBox.Show(this, "현재 최신 버전입니다.", "업데이트 확인", MessageBoxButtons.OK, MessageBoxIcon.Information);
                        return;
                    }
                    DialogResult answer = MessageBox.Show(this, info.Tag + " 버전이 있습니다. GitHub 배포 페이지를 여시겠습니까?", "업데이트 가능", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                    if (answer == DialogResult.Yes) Process.Start(info.PageUrl);
                });
            });
        }

        private void LoadManifest()
        {
            try { manifest = PackageManifest.Load(AppDomain.CurrentDomain.BaseDirectory); }
            catch (Exception e) { SetStatus("패키지 오류: " + e.Message, true); SetEnabled(false); }
        }

        private void AutoDetect()
        {
            if (manifest == null) return;
            try
            {
                var list = SteamLocator.Detect();
                if (list.Count == 0) throw new InvalidOperationException("Steam 설치를 자동 감지하지 못했습니다.");
                gamePath.Text = list[0].GameDir;
                Append("자동 감지: " + list[0].GameDir);
                Run("check");
            }
            catch (Exception e) { SetStatus(e.Message + " 찾기 버튼으로 직접 선택할 수 있습니다.", true); }
        }

        private void Browse()
        {
            using (FolderBrowserDialog d = new FolderBrowserDialog())
            {
                d.Description = "Automobilista 2 게임 폴더를 선택하십시오.";
                d.SelectedPath = gamePath.Text;
                if (d.ShowDialog(this) == DialogResult.OK) { gamePath.Text = d.SelectedPath; Run("check"); }
            }
        }

        private void Run(string action)
        {
            if (manifest == null || String.IsNullOrWhiteSpace(gamePath.Text)) return;
            string selected = gamePath.Text;
            string diag = null;
            if (action == "diagnostic")
            {
                using (SaveFileDialog d = new SaveFileDialog())
                {
                    d.Filter = "ZIP 파일|*.zip";
                    d.FileName = "AMS2-Korean-Beta063-Diagnostic-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".zip";
                    if (d.ShowDialog(this) != DialogResult.OK) return;
                    diag = d.FileName;
                }
            }
            ShortcutOptions shortcuts = action == "install" ? new ShortcutOptions { Desktop = desktopShortcut.Checked, StartMenu = startMenuShortcut.Checked, Taskbar = taskbarShortcut.Checked } : null;
            SetEnabled(false); Append(action + " 작업 시작");
            Task.Factory.StartNew(delegate
            {
                try
                {
                    GameInfo game = SteamLocator.FromGameDirectory(selected);
                    BetaEngine engine = new BetaEngine(manifest, AppendThreadSafe, false);
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
                    SetEnabled(true);
                    OperationResult r = t.Result;
                    ApplyInstallButton(r.Status);
                    string message = DisplayText(r.Message);
                    SetStatus(DisplayStatus(r.Status) + " — " + message, !r.Success);
                    Append("완료: " + DisplayStatus(r.Status) + " / " + message);
                    if (!String.IsNullOrEmpty(r.LogPath)) Append("증거/로그: " + r.LogPath);
                    if (!r.Success && action != "check") MessageBox.Show(this, r.Message, "작업 실패", MessageBoxButtons.OK, MessageBoxIcon.Error);
                });
            });
        }

        private void AppendThreadSafe(string text) { if (!IsDisposed) BeginInvoke((MethodInvoker)delegate { Append(text); }); }
        private void Append(string text) { log.AppendText("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + text + Environment.NewLine); log.SelectionStart = log.TextLength; log.ScrollToCaret(); }
        private void SetStatus(string text, bool error) { status.Text = "상태: " + text; status.ForeColor = error ? Color.DarkRed : Color.DarkGreen; }
        private static string DisplayStatus(string value)
        {
            if (value == "UPDATE_AVAILABLE") return "업데이트 필요";
            if (value == "UPDATED_EXACT") return "한글 패치 업데이트 완료";
            if (value == "INSTALLED_EXACT") return "한글 패치 설치 완료";
            if (value == "RESTORED_EXACT") return "한글 패치 제거 완료";
            if (value == "NOT_INSTALLED") return "한글 패치 미설치";
            if (value == "LAUNCHED_KOREAN") return "한국어 게임 실행 완료";
            if (value == "DIAGNOSTIC_CREATED") return "진단 ZIP 생성 완료";
            return value;
        }
        private void ApplyInstallButton(string state)
        {
            install.Text = state == "UPDATE_AVAILABLE" ? "업데이트" : "설치";
        }
        private static string DisplayText(string value)
        {
            return (value ?? "")
                .Replace("INSTALLED_EXACT", "한글 패치 설치 완료")
                .Replace("RESTORED_EXACT", "한글 패치 제거 완료")
                .Replace("NOT_INSTALLED", "한글 패치 미설치");
        }
        private void SetEnabled(bool enabled) { install.Enabled = enabled; remove.Enabled = enabled; check.Enabled = enabled; launch.Enabled = enabled; diagnostic.Enabled = enabled; updateCheck.Enabled = enabled; browse.Enabled = enabled; detect.Enabled = enabled; desktopShortcut.Enabled = enabled; startMenuShortcut.Enabled = enabled; taskbarShortcut.Enabled = enabled; }
    }

    internal sealed class GithubReleaseInfo
    {
        public string Tag;
        public string PageUrl;
    }

    internal static class GithubUpdater
    {
        private const string LatestReleaseApi = "https://api.github.com/repos/choi3724/AMS2/releases/latest";

        public static GithubReleaseInfo Check()
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(LatestReleaseApi);
            request.UserAgent = "AMS2-Korean-Patch-Updater/0.6.3";
            request.Accept = "application/vnd.github+json";
            request.Timeout = 6000;
            string json;
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            using (StreamReader reader = new StreamReader(response.GetResponseStream())) json = reader.ReadToEnd();
            string tag = ReadJsonString(json, "tag_name");
            string page = ReadJsonString(json, "html_url");
            if (String.IsNullOrWhiteSpace(tag) || String.IsNullOrWhiteSpace(page)) throw new InvalidOperationException("GitHub release metadata is incomplete.");
            return new GithubReleaseInfo { Tag = tag, PageUrl = page };
        }

        public static bool IsNewer(string remote, string current)
        {
            System.Version remoteVersion = ParseVersion(remote);
            System.Version currentVersion = ParseVersion(current);
            return remoteVersion.CompareTo(currentVersion) > 0;
        }

        private static System.Version ParseVersion(string value)
        {
            Match match = Regex.Match(value ?? "", "(?<major>\\d+)\\.(?<minor>\\d+)\\.(?<patch>\\d+)");
            if (!match.Success) return new System.Version(0, 0, 0);
            return new System.Version(Int32.Parse(match.Groups["major"].Value), Int32.Parse(match.Groups["minor"].Value), Int32.Parse(match.Groups["patch"].Value));
        }

        private static string ReadJsonString(string json, string name)
        {
            Match match = Regex.Match(json ?? "", "\\\"" + Regex.Escape(name) + "\\\"\\s*:\\s*\\\"(?<value>(?:\\\\.|[^\\\"])*)\\\"");
            return match.Success ? match.Groups["value"].Value.Replace("\\/", "/") : null;
        }
    }

    internal static class InstallerProgram
    {
        [STAThread]
        public static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
        }
    }
}
