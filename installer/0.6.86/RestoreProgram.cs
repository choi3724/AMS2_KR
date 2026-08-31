using System;
using System.Drawing;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Ams2KoreanBeta
{
    internal sealed class RestoreForm : Form
    {
        private TextBox path = new TextBox();
        private Label status = new Label();
        private Button restore = new Button();
        private PackageManifest manifest;

        public RestoreForm()
        {
            Text = "AMS2 한국어 패치 CB 0.6.86 — 긴급 원복";
            Font = new Font("Malgun Gothic", 9F); Width = 720; Height = 340; BackColor = Color.FromArgb(244, 246, 250); AutoScaleMode = AutoScaleMode.Dpi;
            StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
            Panel header = new Panel { Dock = DockStyle.Top, Height = 92, BackColor = Color.FromArgb(26, 31, 43) };
            header.Controls.Add(new Label { Text = "긴급 제거 및 영문 원본 복원", Left = 24, Top = 20, Width = 620, Height = 34, ForeColor = Color.White, Font = new Font("Malgun Gothic", 17F, FontStyle.Bold) });
            header.Controls.Add(new Label { Text = "CLOSED BETA 0.6.86", Left = 26, Top = 58, Width = 240, Height = 20, ForeColor = Color.FromArgb(190, 199, 214), Font = new Font("Segoe UI", 8.5F, FontStyle.Bold) });
            Controls.Add(header);
            Controls.Add(new Label { Text = "활성 설치 상태와 영문 원본 백업을 검증한 뒤 패치가 만든 파일을 제거합니다.", Left = 24, Top = 110, Width = 650, Height = 28, ForeColor = Color.FromArgb(70, 78, 92) });
            path.SetBounds(24, 145, 540, 30); Controls.Add(path);
            Button browse = new Button { Text = "찾기", Left = 576, Top = 143, Width = 100, Height = 34, FlatStyle = FlatStyle.Flat, BackColor = Color.White }; browse.Click += delegate { Browse(); }; Controls.Add(browse);
            restore.Text = "영문 원본으로 복원"; restore.SetBounds(24, 195, 190, 42); restore.FlatStyle = FlatStyle.Flat; restore.BackColor = Color.FromArgb(185, 28, 28); restore.ForeColor = Color.White; restore.Click += delegate { Run(); }; Controls.Add(restore);
            Button close = new Button { Text = "닫기", Left = 566, Top = 195, Width = 110, Height = 42, FlatStyle = FlatStyle.Flat, BackColor = Color.White }; close.Click += delegate { Close(); }; Controls.Add(close);
            status.SetBounds(24, 254, 652, 44); status.Font = new Font("Malgun Gothic", 9F, FontStyle.Bold); Controls.Add(status);
            Shown += delegate
            {
                try { manifest = PackageManifest.Load(AppDomain.CurrentDomain.BaseDirectory); var g = SteamLocator.Detect(); if (g.Count > 0) path.Text = g[0].GameDir; }
                catch (Exception e) { status.Text = "패키지 오류: " + e.Message; restore.Enabled = false; }
            };
        }

        private void Browse() { using (FolderBrowserDialog d = new FolderBrowserDialog()) { if (d.ShowDialog(this) == DialogResult.OK) path.Text = d.SelectedPath; } }
        private void Run()
        {
            if (MessageBox.Show(this, "게임과 Procmon을 종료했습니까? 설치 전 상태로 복구합니다.", "확인", MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
            restore.Enabled = false; status.Text = "복구 중...";
            Task.Factory.StartNew(delegate
            {
                try { GameInfo g = SteamLocator.FromGameDirectory(path.Text); return new BetaEngine(manifest, null, false).Uninstall(g); }
                catch (Exception e) { return new OperationResult { Success = false, Status = "FAILED", Message = e.Message }; }
            }).ContinueWith(delegate(Task<OperationResult> t) { BeginInvoke((MethodInvoker)delegate { restore.Enabled = true; status.Text = t.Result.Status + " — " + t.Result.Message; MessageBox.Show(this, t.Result.Message, t.Result.Success ? "복구 완료" : "복구 실패", MessageBoxButtons.OK, t.Result.Success ? MessageBoxIcon.Information : MessageBoxIcon.Error); }); });
        }
    }

    internal static class RestoreProgram
    {
        [STAThread]
        public static void Main() { Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false); Application.Run(new RestoreForm()); }
    }
}
