// One-time *Editor-only* forest core authoring. Staged exclusively in scratch Unity;
// deliverables are TerrainData .asset bytes, not runtime or importer modifiers.
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Aaris.WorldAutomation
{
    public static class AarisForestCoreAuthoring
    {
        [Serializable]
        public sealed class ForestReport
        {
            public string asset, beforeSha256, afterSha256;
            public int treeCount, changedCount, mature, young, landmark, competitionTrees, steepTrees;
            public float widthBefore, widthAfter, heightBefore, heightAfter;
            public float projectedCanopyBefore, projectedCanopyAfter;
        }

        private sealed class Planned
        {
            public ForestReport report;
            public TreeInstance[] proposed;
        }

        // Fixed world-position hash: no random seeds, no frame-dependent choices.
        private static float Noise(Vector3 p, int species, uint salt)
        {
            unchecked
            {
                uint h = (uint)Mathf.RoundToInt(p.x * 100f) * 73856093u;
                h ^= (uint)Mathf.RoundToInt(p.z * 100f) * 19349663u;
                h ^= (uint)(species + 23) * 83492791u;
                h ^= salt;
                h ^= h >> 16;
                h *= 0x7feb352du;
                h ^= h >> 15;
                h *= 0x846ca68bu;
                h ^= h >> 16;
                return (h & 0xFFFFFFu) / 16777216f;
            }
        }

        private static long Cell(int x, int z)
        {
            return ((long)x << 32) | (uint)z;
        }

        private static string Sha256(string path)
        {
            using (var stream = File.OpenRead(path))
            using (var hash = SHA256.Create())
                return BitConverter.ToString(hash.ComputeHash(stream))
                    .Replace("-", "").ToLowerInvariant();
        }

        private static float SpeciesScale(TreePrototype[] prototypes, int index)
        {
            if (index < 0 || index >= prototypes.Length || prototypes[index].prefab == null)
                return 1f;
            string species = prototypes[index].prefab.name.ToLowerInvariant();
            if (species.Contains("cypress")) return .92f;
            if (species.Contains("conifer")) return 1.03f;
            if (species.Contains("pine_a")) return 1.02f;
            if (species.Contains("pine_b")) return .99f;
            if (species.Contains("pine_c")) return 1.01f;
            if (species.Contains("pine_d")) return .97f;
            return 1f;
        }

        private static Planned Build(Terrain terrain, string source)
        {
            TerrainData data = terrain.terrainData;
            TreeInstance[] original = data.treeInstances;
            TreeInstance[] proposed = (TreeInstance[])original.Clone();
            var report = new ForestReport
            {
                asset = source, beforeSha256 = Sha256(source), treeCount = original.Length
            };
            Vector3 origin = terrain.GetPosition();
            Vector3 size = data.size;
            TreePrototype[] prototypes = data.treePrototypes;

            // 11 m cells; only adjacent cells are considered for local competition.
            // This is a bounded O(N*k) spatial neighborhood, not all-pairs O(N^2).
            var positions = new Vector3[original.Length];
            var cells = new Dictionary<long, List<int>>();
            const float spacing = 11f;
            for (int i = 0; i < original.Length; i++)
            {
                positions[i] = origin + Vector3.Scale(original[i].position, size);
                int cx = Mathf.FloorToInt(positions[i].x / spacing);
                int cz = Mathf.FloorToInt(positions[i].z / spacing);
                long key = Cell(cx, cz);
                if (!cells.TryGetValue(key, out List<int> entries))
                {
                    entries = new List<int>();
                    cells.Add(key, entries);
                }
                entries.Add(i);
            }

            var plannedWidths = new float[original.Length];
            for (int i = 0; i < original.Length; i++)
            {
                TreeInstance tree = original[i];
                if (!float.IsFinite(tree.widthScale) || !float.IsFinite(tree.heightScale)
                    || tree.widthScale <= 0f || tree.heightScale <= 0f)
                    throw new InvalidOperationException("Invalid original tree dimensions: " + i);
                Vector3 p = positions[i];
                float luck = Noise(p, tree.prototypeIndex, 0x713C59A3u);
                float varWidth = Noise(p, tree.prototypeIndex, 0x391E5B7Au);
                float varHeight = Noise(p, tree.prototypeIndex, 0x62A09BC1u);
                float oldWidth = tree.widthScale;
                float oldHeight = tree.heightScale;

                // Mostly mature/strong, some healthy young, rare landmarks.
                float age;
                if (luck < .75f)
                {
                    report.mature++;
                    age = Mathf.Lerp(1.04f, 1.23f, varWidth);
                }
                else if (luck < .93f)
                {
                    report.young++;
                    age = Mathf.Lerp(.83f, 1.00f, varWidth);
                }
                else
                {
                    report.landmark++;
                    age = Mathf.Lerp(1.23f, 1.44f, varWidth);
                }

                float slope = data.GetSteepness(Mathf.Clamp01(tree.position.x),
                                                Mathf.Clamp01(tree.position.z));
                bool steep = slope >= 27f;
                if (steep) report.steepTrees++;
                int cx = Mathf.FloorToInt(p.x / spacing);
                int cz = Mathf.FloorToInt(p.z / spacing);
                bool crowded = false;
                for (int dx = -1; dx <= 1 && !crowded; dx++)
                    for (int dz = -1; dz <= 1 && !crowded; dz++)
                    {
                        if (!cells.TryGetValue(Cell(cx + dx, cz + dz), out List<int> nearby))
                            continue;
                        foreach (int j in nearby)
                        {
                            if (j == i) continue;
                            Vector3 q = positions[j];
                            float x = p.x - q.x, z = p.z - q.z;
                            if (x * x + z * z < 49f)
                            {
                                crowded = true;
                                break;
                            }
                        }
                    }
                if (crowded) report.competitionTrees++;

                // Preserve most of the previously authored species-specific shape
                // and large silhouette while reducing extreme canopy size.
                float ecology = (steep ? .93f : 1f) * (crowded ? .95f : 1f);
                float species = SpeciesScale(prototypes, tree.prototypeIndex);
                float width = Mathf.Clamp((oldWidth * .61f + age * species * .39f)
                                           * ecology, .78f, 1.90f);
                float height = Mathf.Clamp(oldHeight * .91f +
                                   (.87f + .37f * varHeight) * .09f, .78f, 2.08f);
                if (steep) height *= .98f;
                plannedWidths[i] = width;
                proposed[i].heightScale = height;
                report.widthBefore += oldWidth;
                report.heightBefore += oldHeight;
                report.projectedCanopyBefore += oldWidth * oldWidth * oldHeight;
            }

            // 2 GB-friendly *proxy budget*: no growth in total width^2*height,
            // which approximates crown envelope/overdraw, not actual FPS.
            float rawAfter = 0f;
            for (int i = 0; i < original.Length; i++)
                rawAfter += plannedWidths[i] * plannedWidths[i] * proposed[i].heightScale;
            float limit = report.projectedCanopyBefore * .985f;
            float reduction = rawAfter > limit && rawAfter > 0f
                ? Mathf.Sqrt(limit / rawAfter) : 1f;
            for (int i = 0; i < original.Length; i++)
            {
                proposed[i].widthScale = Mathf.Max(.68f, plannedWidths[i] * reduction);
                report.widthAfter += proposed[i].widthScale;
                report.heightAfter += proposed[i].heightScale;
                report.projectedCanopyAfter += proposed[i].widthScale *
                    proposed[i].widthScale * proposed[i].heightScale;
                if (Mathf.Abs(proposed[i].widthScale - original[i].widthScale) > .0001f
                    || Mathf.Abs(proposed[i].heightScale - original[i].heightScale) > .0001f)
                    report.changedCount++;
            }
            if (original.Length > 0)
            {
                report.widthBefore /= original.Length;
                report.widthAfter /= original.Length;
                report.heightBefore /= original.Length;
                report.heightAfter /= original.Length;
            }
            if (report.projectedCanopyAfter > report.projectedCanopyBefore * 1.001f)
                throw new InvalidOperationException("Forest envelope budget increased unexpectedly");
            return new Planned { report = report, proposed = proposed };
        }

        public static void Run(AarisLiveEditorBridge.Request request,
                               AarisLiveEditorBridge.Response result, bool write)
        {
            if (write && (string.IsNullOrEmpty(request.expectedDigest)
                || !System.Text.RegularExpressions.Regex.IsMatch(request.expectedDigest,
                    @"^[0-9a-f]{64}$")))
                throw new InvalidOperationException("Exact preflight SHA256 is required");
            bool all = !write && request.target == "all";
            var candidates = UnityEngine.Object.FindObjectsByType<Terrain>(
                FindObjectsInactive.Include, FindObjectsSortMode.None)
                .Where(t => t.gameObject.scene.IsValid()
                    && t.gameObject.scene.path == "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity"
                    && t.terrainData != null)
                .GroupBy(t => AssetDatabase.GetAssetPath(t.terrainData))
                .Select(g => g.First())
                .OrderBy(t => AssetDatabase.GetAssetPath(t.terrainData))
                .ToArray();
            if (candidates.Length != 4)
                throw new InvalidOperationException("Expected 4 saved terrain data tiles");
            var reports = new List<ForestReport>();
            int count = 0;
            foreach (Terrain terrain in candidates)
            {
                TerrainData data = terrain.terrainData;
                string asset = AssetDatabase.GetAssetPath(data);
                if (string.IsNullOrEmpty(asset) || !asset.StartsWith(
                    "Assets/TerrainDemoScene_URP/Terrain/Data/", StringComparison.Ordinal)
                    || !asset.EndsWith(".asset", StringComparison.Ordinal))
                    throw new InvalidOperationException("Non-allowlisted native TerrainData");
                if (!all && asset != request.target) continue;
                string physical = Path.GetFullPath(asset);
                var plan = Build(terrain, physical);
                plan.report.asset = asset;
                count += plan.report.treeCount;
                if (write)
                {
                    if (plan.report.beforeSha256 != request.expectedDigest)
                        throw new InvalidOperationException("Stale asset preflight SHA256: " + asset);
                    if (plan.report.changedCount == 0)
                        throw new InvalidOperationException("No revised trees in core asset");
                    Undo.RegisterCompleteObjectUndo(data, "Aaris world-scale native forest rebalance");
                    // False is essential: preserve every original position and elevation.
                    data.SetTreeInstances(plan.proposed, false);
                    EditorUtility.SetDirty(data);
                    AssetDatabase.SaveAssets();
                    terrain.Flush();
                    TreeInstance[] readback = data.treeInstances;
                    if (readback.Length != plan.proposed.Length)
                        throw new InvalidOperationException("Unity tree count changed");
                    for (int i = 0; i < readback.Length; i++)
                    {
                        var a = readback[i];
                        var b = plan.proposed[i];
                        if (a.prototypeIndex != b.prototypeIndex
                            || Vector3.Distance(a.position, b.position) > .000001f
                            || Mathf.Abs(a.widthScale - b.widthScale) > .0001f
                            || Mathf.Abs(a.heightScale - b.heightScale) > .0001f)
                            throw new InvalidOperationException("Native tree readback mismatch " + i);
                    }
                    plan.report.afterSha256 = Sha256(physical);
                    if (plan.report.afterSha256 == plan.report.beforeSha256)
                        throw new InvalidOperationException("Native core asset bytes unchanged");
                    result.changedAsset = asset;
                    result.targetId = asset;
                    SceneView.RepaintAll();
                }
                reports.Add(plan.report);
            }
            if (all && count != 7508)
                throw new InvalidOperationException("Native forest size changed; expected 7508");
            if (write && reports.Count != 1)
                throw new InvalidOperationException("Exactly one TerrainData asset per transaction");
            result.forestReports = reports.ToArray();
            result.terrainTreeCount = count;
        }
    }
}
#endif
