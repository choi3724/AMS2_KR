using System;
using System.IO;
using System.Linq;
using System.Collections;
using System.Reflection;
using System.Text;

class VerifyMenus
{
    static object Invoke(MethodInfo method, params object[] args) { return method.Invoke(null, args); }
    static int Main(string[] args)
    {
        try { Run(args); return 0; }
        catch (Exception error) { Console.Error.WriteLine(error.ToString()); return 1; }
    }
    static void Run(string[] args)
    {
        var assembly = Assembly.LoadFile(Path.GetFullPath(args[0]));
        if (assembly.GetName().Version.ToString() != String.Join(".", args[2].Split('.').Concat(Enumerable.Repeat("0", 4 - args[2].Split('.').Length)))) throw new Exception("Unexpected release version");
        var type = assembly.GetType("Ams2KoreanBeta.GameUpdateCompatibility", true);
        var flags = BindingFlags.NonPublic | BindingFlags.Static;
        var patch = type.GetMethod("PatchMenu", flags);
        foreach (string build in new[] { "25271800", "24132163" })
        {
            var rules = Invoke(type.GetMethod("ForBuild", flags), build);
            var menus = (IDictionary)rules.GetType().GetField("menus").GetValue(rules);
            foreach (DictionaryEntry entry in menus)
            {
                string name = (string)entry.Key;
                string suffix = build == "24132163" ? "-24132163" : "";
                byte[] source = File.ReadAllBytes(Path.Combine(args[1], "original" + suffix, name));
                byte[] expected = File.ReadAllBytes(Path.Combine(args[1], "candidate" + suffix, name));
                byte[] result = (byte[])Invoke(patch, source, entry.Value);
                if (!result.SequenceEqual(expected)) throw new Exception("Menu mismatch: " + name);
            }
        }
        var current = Invoke(type.GetMethod("ForBuild", flags), "25271800");
        var currentMenus = (IDictionary)current.GetType().GetField("menus").GetValue(current);
        string main = "gui/menu_mainmenu_1_6.bgui";
        var rule = currentMenus[main];
        var literal = (string[])rule.GetType().GetField("literalText").GetValue(rule);
        byte[] input = File.ReadAllBytes(Path.Combine(args[1], "original", main));
        byte[] needle = BitConverter.GetBytes(literal[0].Length).Concat(Encoding.Unicode.GetBytes(literal[0])).ToArray();
        byte[] changed = (byte[])input.Clone();
        int position = Enumerable.Range(0, input.Length - needle.Length + 1).First(i => input[i] == needle[0] && input.Skip(i).Take(needle.Length).SequenceEqual(needle));
        changed[position + 4] ^= 1;
        foreach (byte[] bad in new[] { changed, input.Concat(needle).ToArray() })
        {
            try { Invoke(patch, bad, rule); }
            catch (TargetInvocationException e)
            {
                if (!(e.InnerException is InvalidDataException)) throw;
                continue;
            }
            throw new Exception("Unsafe literal accepted");
        }
        Console.WriteLine("PASS: " + Path.GetFileName(args[0]) + "; 8 menu outputs; changed/duplicate literal rejected");
    }
}
