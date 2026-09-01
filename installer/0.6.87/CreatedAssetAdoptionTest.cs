using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

namespace Ams2KoreanBeta
{
    internal static class CreatedAssetAdoptionTest
    {
        public static int Main()
        {
            MethodInfo resolve = typeof(BetaEngine).GetMethod("ResolveCanonicalOriginal", BindingFlags.Instance | BindingFlags.NonPublic);
            if (resolve == null) throw new InvalidOperationException("ResolveCanonicalOriginal not found");

            BetaEngine engine = new BetaEngine(new PackageManifest(), null, true);
            ExpectCreated(resolve, engine, false, "ABSENT", "CURRENT", new string[0]);
            ExpectCreated(resolve, engine, true, "CURRENT", "CURRENT", new string[0]);
            ExpectCreated(resolve, engine, true, "PREVIOUS", "CURRENT", new[] { "PREVIOUS" });
            ExpectUnknownPreserved(resolve, true);
            ExpectUnknownPreserved(resolve, false);
            Console.WriteLine("PASS: existing file preserve-and-overwrite contract");
            return 0;
        }

        private static void ExpectCreated(MethodInfo resolve, BetaEngine engine, bool exists, string before, string after, string[] accepted)
        {
            DirectState target = new DirectState { RelativePath = "gui/test.bgui", InstallBeforeExists = exists, InstallBeforeSha = before, AfterSha = after };
            resolve.Invoke(engine, new object[] { target, true, accepted, new List<PreviousInstallInfo>(), "test" });
            if (target.Action != "created" || target.BeforeSha != "ABSENT") throw new InvalidOperationException("created asset was not adopted");
        }

        private static void ExpectUnknownPreserved(MethodInfo resolve, bool stockIsAbsent)
        {
            string root = Path.Combine(Path.GetTempPath(), "AMS2-KR-0687-PRESERVE-" + Guid.NewGuid().ToString("N"));
            string game = Path.Combine(root, "game");
            string state = Path.Combine(root, "state");
            string relative = stockIsAbsent ? "text/created-test.tdb" : "gui/modified-test.bgui";
            try
            {
                string live = Path.Combine(game, relative.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(live));
                File.WriteAllBytes(live, Encoding.UTF8.GetBytes(stockIsAbsent ? "unknown-created-file" : "unknown-modified-file"));
                string before = FileOps.Sha256(live);
                long beforeBytes = new FileInfo(live).Length;

                BetaEngine engine = new BetaEngine(new PackageManifest(), null, true);
                SetField(engine, "gameDir", game);
                SetField(engine, "stateRoot", state);
                DirectState target = new DirectState
                {
                    RelativePath = relative,
                    InstallBeforeExists = true,
                    InstallBeforeSha = before,
                    InstallBeforeBytes = beforeBytes,
                    AfterSha = new string('A', 64),
                    AfterBytes = 1
                };
                resolve.Invoke(engine, new object[] { target, stockIsAbsent, new string[0], new List<PreviousInstallInfo>(), "test" });
                if (target.Action != "modified" || target.BeforeSha != before || target.BeforeBytes != beforeBytes)
                    throw new InvalidOperationException("unknown existing file was not preserved");

                string backup = Path.Combine(state, "original", "test", relative.Replace('/', Path.DirectorySeparatorChar));
                if (!File.Exists(backup) || FileOps.Sha256(backup) != before)
                    throw new InvalidOperationException("unknown existing file backup mismatch");
            }
            finally
            {
                if (Directory.Exists(root)) Directory.Delete(root, true);
            }
        }

        private static void SetField(BetaEngine engine, string name, string value)
        {
            FieldInfo field = typeof(BetaEngine).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null) throw new InvalidOperationException(name + " not found");
            field.SetValue(engine, value);
        }
    }
}
