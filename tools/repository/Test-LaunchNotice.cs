using System;
using System.Reflection;
class LaunchNoticeTest
{
    static int Main(string[] args)
    {
        var t = Assembly.LoadFrom(args[0]).GetType("Ams2KoreanBeta.GameUpdateCompatibility+CompatibilityOutcome", true);
        int count = 0;
        foreach(bool unknown in new[]{false,true})
        foreach(bool changed in new[]{false,true})
        foreach(int repaired in new[]{0,13})
        foreach(int skipped in new[]{0,2})
        {
            object outcome = Activator.CreateInstance(t, true);
            t.GetField("BuildId").SetValue(outcome,"25391793");
            t.GetField("UnknownBuild").SetValue(outcome,unknown);
            t.GetField("BuildChanged").SetValue(outcome,changed);
            t.GetField("Reapplied").SetValue(outcome,repaired);
            t.GetField("SkippedOptional").SetValue(outcome,skipped);
            bool notify = (bool)t.GetProperty("ShouldNotify").GetValue(outcome,null);
            string notice = (string)t.GetProperty("Notice").GetValue(outcome,null);
            if (notify != (unknown && changed || skipped > 0)) throw new Exception("Notification policy mismatch");
            if (notice.Contains("새 게임 빌드") != (unknown && changed)) throw new Exception("Repeated new-build wording");
            if (repaired > 0 && !notice.Contains("13개")) throw new Exception("Repair result lost");
            count++;
        }
        Console.WriteLine("PASS: " + count + " notification states; routine repair silent, new-build/warnings retained");
        return 0;
    }
}
