using System;
using System.Collections.Generic;
using System.Reflection;

namespace Ams2KoreanBeta
{
    internal static class CreatedAssetAdoptionTest
    {
        public static int Main()
        {
            BetaEngine engine = new BetaEngine(new PackageManifest(), null, true);
            MethodInfo resolve = typeof(BetaEngine).GetMethod("ResolveCanonicalOriginal", BindingFlags.Instance | BindingFlags.NonPublic);
            if (resolve == null) throw new InvalidOperationException("ResolveCanonicalOriginal not found");

            ExpectCreated(resolve, engine, false, "ABSENT", "CURRENT", new string[0]);
            ExpectCreated(resolve, engine, true, "CURRENT", "CURRENT", new string[0]);
            ExpectCreated(resolve, engine, true, "PREVIOUS", "CURRENT", new[] { "PREVIOUS" });
            ExpectBlocked(resolve, engine, "UNKNOWN", "CURRENT", new[] { "PREVIOUS" });
            Console.WriteLine("PASS: created asset adoption contract");
            return 0;
        }

        private static void ExpectCreated(MethodInfo resolve, BetaEngine engine, bool exists, string before, string after, string[] accepted)
        {
            DirectState target = new DirectState { RelativePath = "gui/test.bgui", InstallBeforeExists = exists, InstallBeforeSha = before, AfterSha = after };
            resolve.Invoke(engine, new object[] { target, true, accepted, new List<PreviousInstallInfo>(), "test" });
            if (target.Action != "created" || target.BeforeSha != "ABSENT") throw new InvalidOperationException("created asset was not adopted");
        }

        private static void ExpectBlocked(MethodInfo resolve, BetaEngine engine, string before, string after, string[] accepted)
        {
            DirectState target = new DirectState { RelativePath = "gui/test.bgui", InstallBeforeExists = true, InstallBeforeSha = before, AfterSha = after };
            try
            {
                resolve.Invoke(engine, new object[] { target, true, accepted, new List<PreviousInstallInfo>(), "test" });
            }
            catch (TargetInvocationException e)
            {
                if (e.InnerException is InvalidOperationException) return;
                throw;
            }
            throw new InvalidOperationException("unknown created asset was accepted");
        }
    }
}
