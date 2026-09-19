using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace Ams2KoreanBeta
{
    internal sealed class GithubReleaseInfo
    {
        public string Tag, PageUrl, AssetUrl, AssetName, Sha256;
        public long AssetBytes;
    }

    internal static class GithubUpdater
    {
        internal const string RepositoryUrl = "https://github.com/choi3724/AMS2_KR";
        internal const string UpdateProtocol = "AMS2 Korean Patch Launcher Update Protocol 1";
        private const long MaxPackageBytes = 1024L * 1024 * 1024;

        public static Version ParseVersion(string value)
        {
            Match match = Regex.Match(value ?? "", @"^(?:v|(?:Closed|Open) Beta\s+)?(?<version>\d+\.\d+(?:\.\d+){0,2})$", RegexOptions.IgnoreCase);
            Version version;
            if (!match.Success || !Version.TryParse(match.Groups["version"].Value, out version)) throw new FormatException("버전 형식을 인식하지 못했습니다: " + value);
            return new Version(version.Major, version.Minor, Math.Max(0, version.Build), Math.Max(0, version.Revision));
        }

        public static bool IsNewer(string remote, string current) { return ParseVersion(remote) > ParseVersion(current); }

        private static HttpWebRequest Request(string url, int timeout)
        {
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12;
            HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
            request.UserAgent = "AMS2-Korean-Patch-Updater";
            request.Accept = "application/vnd.github+json";
            request.Timeout = timeout;
            request.ReadWriteTimeout = timeout;
            return request;
        }

        public static GithubReleaseInfo Check()
        {
            HttpWebRequest request = Request("https://api.github.com/repos/choi3724/AMS2_KR/releases/latest", 6000);
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            using (StreamReader reader = new StreamReader(response.GetResponseStream()))
            {
                // Bound both metadata size and total lookup time; a slow response must not prevent offline play.
                Stopwatch elapsed = Stopwatch.StartNew();
                char[] buffer = new char[4096];
                System.Text.StringBuilder json = new System.Text.StringBuilder();
                int count;
                while ((count = reader.Read(buffer, 0, buffer.Length)) > 0)
                {
                    if (elapsed.ElapsedMilliseconds > 6000 || json.Length + count > 1024 * 1024) throw new IOException("업데이트 응답이 너무 크거나 느립니다.");
                    json.Append(buffer, 0, count);
                }
                return ParseRelease(json.ToString());
            }
        }

        internal static GithubReleaseInfo ParseRelease(string json)
        {
            var data = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024 }.Deserialize<Dictionary<string, object>>(json);
            if (data == null || !data.ContainsKey("draft") || !data.ContainsKey("prerelease") || Convert.ToBoolean(data["draft"]) || Convert.ToBoolean(data["prerelease"])) throw new InvalidDataException("정식 배포가 아닙니다.");
            string tag = Text(data, "tag_name");
            ParseVersion(tag);
            string page = RepositoryUrl + "/releases/tag/" + tag;
            if (!String.Equals(Text(data, "html_url"), page, StringComparison.Ordinal)) throw new InvalidDataException("배포 페이지 경로가 다릅니다.");
            var info = new GithubReleaseInfo { Tag = tag, PageUrl = page };
            object raw;
            var assets = data.TryGetValue("assets", out raw) ? raw as System.Collections.IEnumerable : null;
            if (assets == null) return info;
            foreach (var item in assets.Cast<object>().OfType<Dictionary<string, object>>())
            {
                string name = Text(item, "name");
                if (name == null || !Regex.IsMatch(name, @"^AMS2\.(?:(?:CB|OB)\.)?\d+\.\d+(?:\.\d+){0,2}\.zip$", RegexOptions.IgnoreCase)) continue;
                if (info.AssetUrl != null) throw new InvalidDataException("자동 업데이트 패키지가 둘 이상입니다.");
                string url = Text(item, "browser_download_url"), digest = Text(item, "digest");
                if (url != RepositoryUrl + "/releases/download/" + tag + "/" + name || !Regex.IsMatch(digest ?? "", "^sha256:[0-9a-fA-F]{64}$")) throw new InvalidDataException("패키지 주소 또는 SHA-256이 유효하지 않습니다.");
                long size = Convert.ToInt64(item["size"]);
                if (size <= 0 || size > MaxPackageBytes) throw new InvalidDataException("패키지 크기가 유효하지 않습니다.");
                info.AssetUrl = url; info.AssetName = name; info.Sha256 = digest.Substring(7); info.AssetBytes = size;
            }
            return info;
        }

        private static string Text(Dictionary<string, object> data, string name)
        {
            object value;
            return data.TryGetValue(name, out value) ? value as string : null;
        }

        public static string DownloadPackage(GithubReleaseInfo info, Action<string> progress, CancellationToken cancel)
        {
            if (info.AssetUrl == null) throw new InvalidOperationException("이 배포에는 자동 업데이트용 ZIP이 없습니다.");
            string stage = Path.Combine(Path.GetTempPath(), "AMS2-KR-UPDATE-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(stage);
            string zip = Path.Combine(stage, "package.zip");
            HttpWebRequest request = Request(info.AssetUrl, 15000);
            using (cancel.Register(request.Abort))
            using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
            using (Stream source = response.GetResponseStream())
            using (FileStream output = new FileStream(zip, FileMode.CreateNew))
            using (SHA256 hash = SHA256.Create())
            {
                if (response.ResponseUri.Scheme != Uri.UriSchemeHttps) throw new InvalidDataException("HTTPS 다운로드가 아닙니다.");
                byte[] buffer = new byte[65536];
                long received = 0;
                int count, lastPercent = -1;
                Stopwatch elapsed = Stopwatch.StartNew();
                while ((count = source.Read(buffer, 0, buffer.Length)) > 0)
                {
                    cancel.ThrowIfCancellationRequested();
                    received += count;
                    if (received > info.AssetBytes || elapsed.Elapsed.TotalMinutes > 10) throw new InvalidDataException("패키지 크기 또는 다운로드 시간 제한을 초과했습니다.");
                    hash.TransformBlock(buffer, 0, count, buffer, 0);
                    output.Write(buffer, 0, count);
                    int percent = (int)(received * 100 / info.AssetBytes);
                    if (percent != lastPercent) { progress("업데이트 다운로드 중… " + percent + "%"); lastPercent = percent; }
                }
                hash.TransformFinalBlock(new byte[0], 0, 0);
                if (received != info.AssetBytes || !String.Equals(BitConverter.ToString(hash.Hash).Replace("-", ""), info.Sha256, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("다운로드한 패키지의 SHA-256이 일치하지 않습니다.");
            }
            progress("다운로드 확인 완료. 설치 파일을 준비하고 있습니다…");
            string extracted = Path.Combine(stage, "extracted");
            ExtractPackage(zip, extracted, cancel);
            return FindInstaller(extracted, info.Tag);
        }

        internal static void ExtractPackage(string zip, string destination, CancellationToken cancel)
        {
            string root = Path.GetFullPath(destination).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            Directory.CreateDirectory(root);
            using (ZipArchive archive = ZipFile.OpenRead(zip))
            {
                long total = 0;
                var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                if (archive.Entries.Count > 20000) throw new InvalidDataException("압축 파일의 항목이 너무 많습니다.");
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    cancel.ThrowIfCancellationRequested();
                    string name = entry.FullName.Replace('/', '\\');
                    string path = Path.GetFullPath(Path.Combine(root, name));
                    if (name.Contains(":") || Path.IsPathRooted(name) || !path.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !paths.Add(path)) throw new InvalidDataException("압축 파일에 잘못된 경로가 있습니다.");
                    total = checked(total + entry.Length);
                    if (total > 2 * MaxPackageBytes) throw new InvalidDataException("압축 해제 크기가 너무 큽니다.");
                    if (name.EndsWith("\\", StringComparison.Ordinal)) { Directory.CreateDirectory(path); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(path));
                    using (Stream input = entry.Open())
                    using (FileStream output = new FileStream(path, FileMode.CreateNew))
                    {
                        byte[] buffer = new byte[65536]; int count; long copied = 0;
                        while ((count = input.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            cancel.ThrowIfCancellationRequested(); copied += count;
                            if (copied > entry.Length) throw new InvalidDataException("압축 해제 크기가 다릅니다.");
                            output.Write(buffer, 0, count);
                        }
                        if (copied != entry.Length) throw new InvalidDataException("불완전한 압축 항목입니다.");
                    }
                }
            }
        }

        internal static string FindInstaller(string directory, string version)
        {
            string[] installers = Directory.GetFiles(directory, "*.exe", SearchOption.AllDirectories).Where(path =>
                Regex.IsMatch(Path.GetFileName(path), @"^(?:AMS2-Korean-Patch-(?:CB|OB)-|AMS2 한국어 패치 (?:CB |오픈베타 ))\d+\.\d+(?:\.\d+){0,2}\.exe$", RegexOptions.IgnoreCase)
                && File.Exists(Path.Combine(Path.GetDirectoryName(path), "manifest", "direct-files.tsv"))).ToArray();
            if (installers.Length != 1) throw new InvalidDataException("업데이트 설치 프로그램을 하나로 식별하지 못했습니다.");
            FileVersionInfo info = FileVersionInfo.GetVersionInfo(installers[0]);
            if (info.Comments != UpdateProtocol || ParseVersion(info.FileVersion) != ParseVersion(version)) throw new InvalidDataException("이 설치 프로그램은 자동 업데이트 실행 규약 또는 배포 버전과 맞지 않습니다.");
            return installers[0];
        }
    }
}
