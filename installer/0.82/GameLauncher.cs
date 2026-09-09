using System;
using System.Diagnostics;
using System.IO;
using Microsoft.Win32;

namespace Ams2KoreanBeta
{
    internal static class GameLauncher
    {
        public static string Arguments(bool vr)
        {
            return "-applaunch 1066890 " + (vr ? "-forcevr" : "-novr") + " -lang=Korean -looseloadtext";
        }

        public static string FindSteam()
        {
            foreach (Process process in Process.GetProcessesByName("steam"))
            {
                using (process)
                {
                    try { string path = process.MainModule.FileName; if (File.Exists(path)) return path; }
                    catch (System.ComponentModel.Win32Exception) { }
                    catch (InvalidOperationException) { }
                }
            }
            foreach (string key in new[] { @"HKEY_CURRENT_USER\Software\Valve\Steam", @"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Valve\Steam", @"HKEY_LOCAL_MACHINE\SOFTWARE\Valve\Steam" })
            {
                string root = Registry.GetValue(key, key.Contains("CURRENT_USER") ? "SteamPath" : "InstallPath", null) as string;
                if (!String.IsNullOrEmpty(root) && File.Exists(Path.Combine(root, "steam.exe"))) return Path.Combine(root, "steam.exe");
            }
            throw new FileNotFoundException("Steam 설치 경로를 찾지 못했습니다. Steam을 먼저 실행해주세요.");
        }

        public static void Start(string game, bool vr)
        {
            if (!File.Exists(Path.Combine(game, "AMS2.exe"))) throw new FileNotFoundException("AMS2.exe를 찾지 못했습니다.");
            string steam = FindSteam();
            Process.Start(new ProcessStartInfo(steam, Arguments(vr)) { WorkingDirectory = Path.GetDirectoryName(steam), UseShellExecute = true });
        }
    }
}
