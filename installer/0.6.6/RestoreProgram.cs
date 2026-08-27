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
            Text = "AMS2 Korean Patch Emergency Restore 0.6.6";
            Font = new Font("Malgun Gothic", 9F); Width = 680; Height = 300;
            StartPosition = FormStartPosition.CenterScreen; FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
            Controls.Add(new Label { Text = "Closed Beta 0.6.6 Emergency Restore", Left = 20, Top = 18, Width = 560, Height = 30, Font = new Font("Malgun Gothic", 14F, FontStyle.Bold) });
            Controls.Add(new Label { Text = "활성 설치 상태와 exact backup이 모두 검증될 때만 설치 전 상태로 복구합니다.", Left = 20, Top = 58, Width = 620, Height = 36 });
            path.SetBounds(20, 105, 520, 28); Controls.Add(path);
            Button browse = new Button { Text = "찾기", Left = 550, Top = 104, Width = 90, Height = 30 }; browse.Click += delegate { Browse(); }; Controls.Add(browse);
            restore.Text = "긴급 제거 / 복구"; restore.SetBounds(20, 150, 160, 40); restore.Click += delegate { Run(); }; Controls.Add(restore);
            Button close = new Button { Text = "닫기", Left = 540, Top = 150, Width = 100, Height = 40 }; close.Click += delegate { Close(); }; Controls.Add(close);
            status.SetBounds(20, 210, 620, 40); Controls.Add(status);
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
