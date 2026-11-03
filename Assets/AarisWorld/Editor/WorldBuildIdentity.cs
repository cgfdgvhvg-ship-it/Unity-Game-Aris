using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace Aaris.WorldAutomation
{
    // Sidecar belongs with the build, not the temporary AI query reports.
    public sealed class WorldBuildIdentity : IPostprocessBuildWithReport
    {
        public int callbackOrder => 100;
        [Serializable] private sealed class Source { public string path, sha256; }
        [Serializable] private sealed class Identity
        {
            public string schemaVersion = "1", buildGuid, commit, utc, unityVersion, version;
            public Source[] coreSources;
        }
        public void OnPostprocessBuild(BuildReport report)
        {
            string commit = Environment.GetEnvironmentVariable("GITHUB_SHA");
            if (string.IsNullOrEmpty(commit))
            {
                try
                {
                    var info = new ProcessStartInfo("git", "rev-parse HEAD") { RedirectStandardOutput = true, RedirectStandardError = true,
                        UseShellExecute = false, CreateNoWindow = true };
                    using (var p = Process.Start(info))
                    { if (p.WaitForExit(3000) && p.ExitCode == 0) commit = p.StandardOutput.ReadToEnd().Trim(); }
                }
                catch (Exception) { commit = "unknown"; }
            }
            var paths = new[] { "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity", "Packages/manifest.json",
                "ProjectSettings/QualitySettings.asset", "ProjectSettings/GraphicsSettings.asset", "ProjectSettings/ProjectSettings.asset" }
                .Concat(AssetDatabase.FindAssets("t:TerrainData", new[] { "Assets/TerrainDemoScene_URP/Terrain/Data" }).Select(AssetDatabase.GUIDToAssetPath))
                .Concat(Directory.GetFiles("Assets/AarisWorld/Scripts", "*.cs")).Distinct().OrderBy(x => x).ToArray();
            var sources = paths.Where(File.Exists).Select(path =>
            {
                using (var hash = SHA256.Create()) using (var file = File.OpenRead(path))
                    return new Source { path = path.Replace('\\', '/'), sha256 = BitConverter.ToString(hash.ComputeHash(file)).Replace("-", "").ToLowerInvariant() };
            }).ToArray();
            var identity = new Identity { buildGuid = report.summary.guid.ToString(), commit = commit ?? "unknown",
                utc = DateTime.UtcNow.ToString("O"), unityVersion = Application.unityVersion, version = Application.version, coreSources = sources };
            string output = report.summary.outputPath;
            string sidecar = Directory.Exists(output) ? Path.Combine(output, "world-build.json") : output + ".world-build.json";
            File.WriteAllText(sidecar, JsonUtility.ToJson(identity, true));
        }
    }
}
