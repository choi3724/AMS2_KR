using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Ams2KoreanBeta
{
    internal sealed class InstallerUpdateForm : Form
    {
        private readonly string[] args;
        private readonly Label message = new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft, Text = "한글패치 업데이트를 준비하고 있습니다…" };
        private bool busy = true;
        public int ExitCode = 1;

        public InstallerUpdateForm(string[] args)
        {
            this.args = args;
            Text = "AMS2 한글패치 업데이트"; ClientSize = new Size(560, 160); Padding = new Padding(18);
            Font = new Font("Malgun Gothic", 10F); AutoScaleMode = AutoScaleMode.Dpi;
            FormBorderStyle = FormBorderStyle.FixedDialog; StartPosition = FormStartPosition.CenterScreen;
            MaximizeBox = false; MinimizeBox = false; Controls.Add(message);
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) e.Cancel = true; };
            Shown += RunUpdate;
        }

        private async void RunUpdate(object sender, EventArgs e)
        {
            try
            {
                GameInfo game = await Task.Run(() => InstallAndVerify(args));
                await ShowCompletionAsync();
                await Task.Run(() => GameLauncher.Start(game.GameDir, args.Length == 7));
                ExitCode = 0;
            }
            catch (Exception error)
            {
                MessageBox.Show(this, error.Message + "\r\n업데이트 완료를 확인하지 못해 게임을 자동 실행하지 않았습니다.", "한글패치 업데이트 실패", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally { busy = false; Close(); }
        }

        internal async Task ShowCompletionAsync()
        {
            message.Text = "업데이트가 완료되었습니다. 게임을 실행합니다.";
            await Task.Delay(2000);
        }

        internal static GameInfo InstallAndVerify(string[] args)
        {
            int parentId;
            if ((args.Length != 6 && args.Length != 7) || args[0] != "--update-and-launch" || args[2] != "--parent" || !Int32.TryParse(args[3], out parentId) || parentId <= 0 || args[4] != "--expected-version" || (args.Length == 7 && args[6] != "--vr")) throw new ArgumentException("잘못된 업데이트 실행 요청입니다.");
            if (GithubUpdater.ParseVersion(args[5]) != GithubUpdater.ParseVersion(PackageManifest.Version)) throw new InvalidDataException("다운로드한 설치 프로그램의 버전이 다릅니다.");
            GameInfo game = SteamLocator.FromGameDirectory(args[1]);
            Process parent = null;
            try { parent = Process.GetProcessById(parentId); } catch (ArgumentException) { }
            if (parent != null)
            {
                using (parent)
                {
                    string file = null;
                    try { if (!parent.HasExited) file = parent.MainModule.FileName; }
                    catch (System.ComponentModel.Win32Exception) { if (!parent.HasExited) throw; }
                    catch (InvalidOperationException) { if (!parent.HasExited) throw; }
                    if (file != null)
                    {
                        string name = Path.GetFileName(file);
                        if (!String.Equals(Path.GetDirectoryName(file), game.GameDir, StringComparison.OrdinalIgnoreCase) || (!name.Equals("AMS2 Korean Launcher.exe", StringComparison.OrdinalIgnoreCase) && !name.Equals("AMS2 Korean VR Launcher.exe", StringComparison.OrdinalIgnoreCase))) throw new InvalidOperationException("업데이트를 요청한 런처를 확인하지 못했습니다.");
                        if (!parent.WaitForExit(30000)) throw new InvalidOperationException("한글패치 런처가 종료되지 않았습니다.");
                    }
                }
            }
            PackageManifest manifest = PackageManifest.Load(AppDomain.CurrentDomain.BaseDirectory);
            var engine = new BetaEngine(manifest, text => { }, false);
            OperationResult installed = engine.Install(game);
            if (!installed.Success) throw new InvalidOperationException(installed.Message);
            OperationResult verified = engine.Check(game);
            if (!verified.Success || verified.Status != "INSTALLED_EXACT") throw new InvalidOperationException("설치 후 파일 검증 실패: " + verified.Message);
            return game;
        }
    }
}
