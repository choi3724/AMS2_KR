using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Diagnostics;
using System.Collections.Generic;
using System.Web.Script.Serialization;

class OverlaySearchTest
{
    static Type type, editType;
    static MethodInfo patch;
    static byte[] Apply(byte[] source, byte[] from, byte[] to, int offset)
    {
        object edit = Activator.CreateInstance(editType);
        editType.GetField("remove").SetValue(edit, Convert.ToBase64String(from));
        editType.GetField("insert").SetValue(edit, Convert.ToBase64String(to));
        editType.GetField("offset").SetValue(edit, offset);
        return (byte[])patch.Invoke(null, new object[] { source, edit, false });
    }
    static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
    static void Refuse(byte[] source, byte[] from, byte[] to)
    {
        try { Apply(source, from, to, -1); }
        catch (TargetInvocationException e) { if (e.InnerException is InvalidDataException) return; throw; }
        throw new Exception("Expected refusal");
    }
    static int Main(string[] args)
    {
        var assembly = Assembly.LoadFrom(args[0]);
        type = assembly.GetType("Ams2KoreanBeta.ContentManagerOverlay");
        editType = type.GetNestedType("Edit");
        patch = type.GetMethod("Patch", BindingFlags.Static | BindingFlags.NonPublic);
        var watch = Stopwatch.StartNew();
        Assert(Apply(new byte[]{9,1,2,8},new byte[]{1,2},new byte[]{3},1).SequenceEqual(new byte[]{9,3,8}), "fixed offset");
        Assert(Apply(new byte[]{9,1,2,8},new byte[]{1,2},new byte[]{3},0).SequenceEqual(new byte[]{9,3,8}), "relocated");
        Assert(Apply(new byte[]{9,3,8},new byte[]{1,2},new byte[]{3},0).SequenceEqual(new byte[]{9,3,8}), "already applied");
        Assert(Apply(new byte[]{1,2,3,1,2},new byte[]{1,2},new byte[]{3},2).SequenceEqual(new byte[]{1,2,3,1,2}), "other languages retain original block");
        Refuse(new byte[]{1,2,1,2},new byte[]{1,2},new byte[]{3});
        Refuse(new byte[]{1,1,1},new byte[]{1,1},new byte[]{3});
        Refuse(new byte[]{3,3},new byte[]{1,2},new byte[]{3});
        Refuse(new byte[]{9},new byte[]{1,2},new byte[]{3});
        Refuse(new byte[]{9},new byte[0],new byte[]{3});
        byte[] large = Enumerable.Repeat((byte)1, 8000000).ToArray();
        byte[] pattern = Enumerable.Repeat((byte)1, 4000).Concat(new byte[]{2}).ToArray();
        Refuse(large, pattern, new byte[]{3});
        Assert(watch.Elapsed.TotalSeconds < 10, "search performance regression");
        Console.WriteLine("PASS: 10 search cases, " + watch.ElapsedMilliseconds + "ms");
        var json = new JavaScriptSerializer { MaxJsonLength = 32*1024*1024 };
        using(var zip = new GZipStream(File.OpenRead(args[1]), CompressionMode.Decompress))
        using(var reader = new StreamReader(zip))
        {
            var profile = (Dictionary<string,object>)json.DeserializeObject(reader.ReadToEnd());
            foreach(var pair in (Dictionary<string,object>)profile["files"])
            {
                string file = Path.Combine(args[2],pair.Key);
                if (!File.Exists(file)) { Console.WriteLine("MISSING " + pair.Key); continue; }
                object edit = json.Deserialize(json.Serialize(pair.Value),editType);
                byte[] original = File.ReadAllBytes(file);
                watch.Restart();
                try {
                    var result = (byte[])patch.Invoke(null,new object[]{original,edit,false});
                    var repeat = (byte[])patch.Invoke(null,new object[]{result,edit,false});
                    Assert(result.SequenceEqual(repeat),"idempotence " + pair.Key);
                    Console.WriteLine("PASS " + pair.Key + " " + original.Length + " bytes " + watch.ElapsedMilliseconds + "ms unchanged="+original.SequenceEqual(result));
                } catch(TargetInvocationException e) { Console.WriteLine("REFUSED " + pair.Key + " " + watch.ElapsedMilliseconds + "ms " + e.InnerException.Message); }
            }
        }
        return 0;
    }
}
