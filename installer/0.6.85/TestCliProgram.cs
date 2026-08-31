using System;
using System.Linq;

namespace Ams2KoreanBeta
{
    internal static class TestCliProgram
    {
        public static int Main(string[] args)
        {
            try
            {
                string root = Value(args, "--release-root") ?? AppDomain.CurrentDomain.BaseDirectory;
                string gameDir = Value(args, "--game-dir");
                string action = args.FirstOrDefault(x => x == "--install" || x == "--uninstall" || x == "--check" || x == "--diagnose" || x == "--launch");
                if (gameDir == null || action == null) throw new InvalidOperationException("usage: --game-dir PATH --install|--uninstall|--check|--diagnose|--launch [--mock] [--shortcuts desktop,start,taskbar]");
                PackageManifest m = PackageManifest.Load(root);
                GameInfo g = SteamLocator.FromGameDirectory(gameDir);
                BetaEngine e = new BetaEngine(m, Console.WriteLine, args.Contains("--mock"));
                ShortcutOptions shortcuts = ParseShortcuts(Value(args, "--shortcuts"));
                OperationResult r = action == "--install" ? e.Install(g, shortcuts) : action == "--uninstall" ? e.Uninstall(g) : action == "--diagnose" ? e.Diagnose(g, Value(args, "--output")) : action == "--launch" ? e.LaunchKorean(g) : e.Check(g);
                Console.WriteLine("STATUS=" + r.Status);
                Console.WriteLine("MESSAGE=" + r.Message);
                return r.Success ? 0 : 2;
            }
            catch (Exception e) { Console.Error.WriteLine(e.ToString()); return 1; }
        }

        private static string Value(string[] args, string key)
        {
            for (int i = 0; i + 1 < args.Length; i++) if (args[i] == key) return args[i + 1];
            return null;
        }

        private static ShortcutOptions ParseShortcuts(string value)
        {
            if (String.IsNullOrWhiteSpace(value)) return null;
            string[] names = value.Split(',');
            return new ShortcutOptions
            {
                Desktop = names.Any(x => x.Equals("desktop", StringComparison.OrdinalIgnoreCase)),
                StartMenu = names.Any(x => x.Equals("start", StringComparison.OrdinalIgnoreCase)),
                Taskbar = names.Any(x => x.Equals("taskbar", StringComparison.OrdinalIgnoreCase)),
            };
        }
    }
}
