using System;
using System.Linq;
using System.Reflection;
using PCarsTools.Encryption;
using PCarsTools.Pak;

namespace BffReflection
{
    internal static class Program
    {
        private static void Main()
        {
            var types = new[]
            {
                typeof(BPakFileEncryption),
                typeof(BPakFile),
                typeof(PakFileHeader),
                typeof(PakFileTocEntry),
            };
            foreach (var type in types.OrderBy(t => t.FullName))
            {
                Console.WriteLine($"TYPE {type.FullName}");
                foreach (var member in type.GetMembers(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                             .Where(m => m.DeclaringType == type)
                             .OrderBy(m => m.MemberType).ThenBy(m => m.Name))
                {
                    Console.WriteLine($"  {member.MemberType} {member}");
                }
                foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                             .Where(m => m.Name == "GetEncKey" || m.Name == "DecryptKey" || m.Name == "DecryptTwoFish"))
                {
                    var body = method.GetMethodBody()?.GetILAsByteArray();
                    Console.WriteLine($"  IL {method}: {(body == null ? "<none>" : BitConverter.ToString(body))}");
                }
                foreach (var method in type.GetMethods(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly)
                             .Where(m => m.Name == "DecryptData"))
                    Console.WriteLine($"  PARAMS {method}: {string.Join(", ", method.GetParameters().Select(p => $"{p.ParameterType.Name} {p.Name}"))}");
            }
        }
    }
}
