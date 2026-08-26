using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace Ams2KoreanBeta
{
    internal static class LauncherProgram
    {
        [STAThread]
        public static int Main()
        {
            try
            {
                string game = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
                string exe = Path.Combine(game, "AMS2.exe");
                if (!File.Exists(exe)) throw new FileNotFoundException("AMS2.exe를 찾지 못했습니다.", exe);
#if VR_LAUNCHER
                ProcessStartInfo p = new ProcessStartInfo(exe, "-forcevr -lang=Korean -looseloadtext");
#else
                ProcessStartInfo p = new ProcessStartInfo(exe, "-novr -lang=Korean -looseloadtext");
#endif
                p.WorkingDirectory = game;
                p.UseShellExecute = true;
                Process.Start(p);
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
