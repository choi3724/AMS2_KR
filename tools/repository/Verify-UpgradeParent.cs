using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;

internal static class VerifyUpgradeParent
{
    static int Main(string[] args)
    {
        try
        {
            if (args[0] == "parent") { Thread.Sleep(1500); return 0; }
            var assembly = Assembly.LoadFile(Path.GetFullPath(args[0]));
            var updater = assembly.GetType("Ams2KoreanBeta.InstallerUpdateForm", true);
            using (var parent = Process.Start(new ProcessStartInfo(args[2], "parent") { UseShellExecute = false, CreateNoWindow = true }))
            {
                var watch = Stopwatch.StartNew();
                string[] request = { "--update-and-launch", args[1], "--parent", parent.Id.ToString(), "--expected-version", "0.87" };
                if (args.Length > 3) request = request.Concat(new[] { "--vr" }).ToArray();
                updater.GetMethod("InstallAndVerify", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, new object[] { request });
                if (!parent.HasExited || watch.ElapsedMilliseconds < 1000) throw new Exception("Parent wait was skipped");
                Console.WriteLine("PASS: actual updater waited for " + Path.GetFileName(args[2]) + " and installed/verified without requesting Steam launch");
            }
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine(e); return 1; }
    }
}
