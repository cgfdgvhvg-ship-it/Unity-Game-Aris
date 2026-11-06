using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Aaris.MapReview.Editor
{
    // One allowlisted AI scene operator: no shell execution, no arbitrary asset paths,
    // no execution of C# received from GitHub or HTTP.
    [InitializeOnLoad]
    internal static class AarisAIControlBridge
    {
        [Serializable] private sealed class Intent
        {
            public string op, target, query;
            public float x, y, z, radius, dx, dy, dz, sx, sy, sz, distance;
            public int max_points;
            public long nonce;
            public bool dry_run;
        }

        [Serializable] private sealed class Item
        {
            public string id, name, type, accuracy;
            public Vector3 position, boundsCenter, boundsSize, localScale;
            public bool hasBounds;
        }

        [Serializable] private sealed class Result
        {
            public string state, op, error, target, photo, meshMode;
            public long nonce;
            public int count, totalPoints;
            public Item[] objects = new Item[0];
            public Vector3[] points = new Vector3[0];
            public string changedAsset;
        }

        private static readonly string Root = Path.Combine(Directory.GetCurrentDirectory(), "ci-live-control");
        private static double nextPoll;
        private const int MaxResults = 80;
        private const int MaxVertexSamples = 2048;

        static AarisAIControlBridge() { EditorApplication.update += Poll; }

        private static void Poll()
        {
            if (EditorApplication.timeSinceStartup < nextPoll) return;
            nextPoll = EditorApplication.timeSinceStartup + 0.45;
            if (EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlaying) return;
            string file = Path.Combine(Root, "ai-command.json");
            if (!File.Exists(file)) return;
            Intent input = null;
            Result result = new Result { state = "error" };
            try
            {
                input = JsonUtility.FromJson<Intent>(File.ReadAllText(file));
                File.Delete(file);
                if (input == null || input.nonce <= 0) throw new ArgumentException("Invalid request");
                result.nonce = input.nonce;
                result.op = input.op;
                Validate(input);
                EnsureScene();
                Execute(input, result);
                result.state = "ok";
            }
            catch (Exception ex)
            {
                result.error = ex.GetType().Name + ": " + ex.Message;
                Debug.LogWarning("[Aaris AI] " + result.error);
            }
            finally
            {
                try
                {
                    Directory.CreateDirectory(Root);
                    string temp = Path.Combine(Root, "ai-result.tmp");
                    File.WriteAllText(temp, JsonUtility.ToJson(result, false));
                    if (File.Exists(Path.Combine(Root, "ai-result.json")))
                        File.Delete(Path.Combine(Root, "ai-result.json"));
                    File.Move(temp, Path.Combine(Root, "ai-result.json"));
                }
                catch (Exception ex) { Debug.LogError("[Aaris AI] Result save failed: " + ex.Message); }
            }
        }

        private static bool Finite(float value) { return !float.IsNaN(value) && !float.IsInfinity(value); }

        private static void Validate(Intent i)
        {
            if (!new[] { "find", "inspect", "bounds", "outline", "move", "scale", "photo" }.Contains(i.op))
                throw new ArgumentException("Unknown AI operation");
            if (!new[] { i.x, i.y, i.z, i.radius, i.dx, i.dy, i.dz,
                         i.sx, i.sy, i.sz, i.distance }.All(Finite))
                throw new ArgumentException("Non-finite numeric input");
            if (i.op == "find" && (string.IsNullOrWhiteSpace(i.query) || i.query.Length > 80))
                throw new ArgumentException("Query required (1-80 chars)");
            if (i.op == "inspect" && (i.radius < 1 || i.radius > 200 ||
                    Mathf.Abs(i.x) > 2500 || Mathf.Abs(i.z) > 2500 || Mathf.Abs(i.y) > 5000))
                throw new ArgumentException("Invalid inspection sphere");
            if (new[] { "bounds", "outline", "move", "scale", "photo" }.Contains(i.op) &&
                (string.IsNullOrWhiteSpace(i.target) || i.target.Length > 300))
                throw new ArgumentException("Exact target ID required");
            if (i.op == "outline" && (i.max_points < 8 || i.max_points > MaxVertexSamples))
                throw new ArgumentException("max_points must be 8-2048");
            if (i.op == "move" && (Mathf.Abs(i.dx) > 100 || Mathf.Abs(i.dy) > 100 ||
                                   Mathf.Abs(i.dz) > 100))
                throw new ArgumentException("Move exceeds 100m limit");
            if (i.op == "scale" && (i.sx < 0.25f || i.sx > 4 ||
                                    i.sy < 0.25f || i.sy > 4 ||
                                    i.sz < 0.25f || i.sz > 4))
                throw new ArgumentException("Scale factors must be 0.25-4");
            if (i.op == "photo" && (i.distance < 2 || i.distance > 200))
                throw new ArgumentException("Camera distance must be 2-200");
        }

        private static void EnsureScene()
        {
            if (SceneManager.GetActiveScene().path != AarisExplorerBuild.ScenePath)
                EditorSceneManager.OpenScene(AarisExplorerBuild.ScenePath, OpenSceneMode.Single);
        }

        private static string Id(Transform t)
        {
            var parts = new List<string>();
            for (var p = t; p != null; p = p.parent)
                parts.Add(p.name + "[" + p.GetSiblingIndex() + "]");
            parts.Reverse();
            return string.Join("/", parts.ToArray());
        }

        private static IEnumerable<Transform> Walk()
        {
            var scene = SceneManager.GetActiveScene();
            var stack = new Stack<Transform>(scene.GetRootGameObjects().Reverse().Select(g => g.transform));
            int visited = 0;
            while (stack.Count != 0)
            {
                var t = stack.Pop();
                if (++visited > 150000) throw new InvalidOperationException("Scene hierarchy exceeds safe limit");
                yield return t;
                for (int j = t.childCount - 1; j >= 0; j--) stack.Push(t.GetChild(j));
            }
        }

        private static Transform Resolve(string id)
        {
            foreach (var t in Walk()) if (Id(t) == id) return t;
            throw new ArgumentException("Target not found; use find to get an exact hierarchy ID");
        }

        private static Terrain[] Tiles()
        {
            return Terrain.activeTerrains.OrderBy(t => t.transform.position.x)
                .ThenBy(t => t.transform.position.z).ToArray();
        }

        private static bool ParseTree(string id, out Terrain terrain, out int index)
        {
            terrain = null; index = -1;
            if (!id.StartsWith("terrain-tree:", StringComparison.Ordinal)) return false;
            string[] parts = id.Substring("terrain-tree:".Length).Split(':');
            int tile;
            if (parts.Length != 2 || !int.TryParse(parts[0], out tile) ||
                !int.TryParse(parts[1], out index))
                throw new ArgumentException("Invalid terrain-tree ID");
            var tiles = Tiles();
            if (tile < 0 || tile >= tiles.Length || index < 0 ||
                index >= tiles[tile].terrainData.treeInstanceCount)
                throw new ArgumentException("Terrain tree index not found");
            terrain = tiles[tile];
            return true;
        }

        private static Item TreeItem(Terrain terrain, int tile, int index, TreeInstance tree)
        {
            Vector3 point = terrain.transform.position +
                            Vector3.Scale(tree.position, terrain.terrainData.size);
            int prototypeIndex = tree.prototypeIndex;
            var prototypes = terrain.terrainData.treePrototypes;
            string name = prototypeIndex >= 0 && prototypeIndex < prototypes.Length &&
                          prototypes[prototypeIndex].prefab != null
                ? prototypes[prototypeIndex].prefab.name : "Tree";
            // Native Terrain trees are not GameObjects. Width/height scales are real,
            // but a mesh-accurate bounding box requires resolving its prototype.
            return new Item { id = "terrain-tree:" + tile + ":" + index,
                name = name, type = "native-terrain-tree", accuracy = "scale-only",
                position = point,
                localScale = new Vector3(tree.widthScale, tree.heightScale, tree.widthScale),
                hasBounds = false };
        }

        private static bool TryBounds(Transform t, out Bounds bounds)
        {
            bounds = new Bounds(t.position, Vector3.zero);
            bool any = false;
            foreach (var r in t.GetComponentsInChildren<Renderer>(true))
            {
                if (r == null || r is ParticleSystemRenderer) continue;
                if (!any) { bounds = r.bounds; any = true; }
                else bounds.Encapsulate(r.bounds);
            }
            if (!any)
            {
                foreach (var c in t.GetComponentsInChildren<Collider>(true))
                {
                    if (!any) { bounds = c.bounds; any = true; }
                    else bounds.Encapsulate(c.bounds);
                }
            }
            return any;
        }

        private static Item Describe(Transform t)
        {
            Bounds b;
            bool has = TryBounds(t, out b);
            return new Item { id = Id(t), name = t.name,
                type = t.GetComponent<Terrain>() != null ? "terrain" : "scene-object",
                accuracy = has ? "world-renderer-bounds" : "position-only",
                position = t.position, localScale = t.localScale,
                hasBounds = has, boundsCenter = b.center, boundsSize = b.size };
        }

        private static void Execute(Intent i, Result r)
        {
            if (i.op == "find" || i.op == "inspect")
            {
                var chosen = new List<Item>();
                string needle = (i.query ?? "").Trim();
                Vector3 center = new Vector3(i.x, i.y, i.z);
                foreach (var t in Walk())
                {
                    if (i.op == "find"
                        ? t.name.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0
                        : (t.position - center).sqrMagnitude <= i.radius * i.radius)
                    {
                        chosen.Add(Describe(t));
                        if (chosen.Count >= MaxResults) break;
                    }
                }
                if (i.op == "inspect" && chosen.Count < MaxResults)
                {
                    var tiles = Tiles();
                    for (int tile = 0; tile < tiles.Length && chosen.Count < MaxResults; tile++)
                    {
                        var data = tiles[tile].terrainData;
                        var trees = data.treeInstances;
                        for (int t = 0; t < trees.Length && chosen.Count < MaxResults; t++)
                        {
                            var item = TreeItem(tiles[tile], tile, t, trees[t]);
                            if ((item.position - center).sqrMagnitude <= i.radius * i.radius)
                                chosen.Add(item);
                        }
                    }
                }
                r.objects = chosen.ToArray();
                r.count = r.objects.Length;
                return;
            }

            Terrain terrain;
            int treeIndex;
            if (ParseTree(i.target, out terrain, out treeIndex))
            {
                var data = terrain.terrainData;
                var trees = data.treeInstances;
                var tree = trees[treeIndex];
                int tile = Array.IndexOf(Tiles(), terrain);
                r.target = i.target;
                r.objects = new[] { TreeItem(terrain, tile, treeIndex, tree) };
                if (i.op == "outline") throw new NotSupportedException(
                    "Native tree outline requires readable prefab geometry; use bounds/scale or scene-object outline");
                if (i.op == "move")
                {
                    Vector3 point = terrain.transform.position + Vector3.Scale(tree.position, data.size);
                    Vector3 next = point + new Vector3(i.dx, i.dy, i.dz);
                    Vector3 local = next - terrain.transform.position;
                    if (local.x < 0 || local.z < 0 || local.x > data.size.x || local.z > data.size.z)
                        throw new ArgumentException("Tree would leave its terrain tile");
                    if (!i.dry_run)
                    {
                        Undo.RecordObject(data, "Aaris AI move native tree");
                        tree.position = new Vector3(local.x / data.size.x,
                            Mathf.Clamp01(local.y / data.size.y), local.z / data.size.z);
                        trees[treeIndex] = tree;
                        data.treeInstances = trees;
                        EditorUtility.SetDirty(data);
                        AssetDatabase.SaveAssets();
                        r.changedAsset = AssetDatabase.GetAssetPath(data);
                    }
                }
                else if (i.op == "scale")
                {
                    if (!Mathf.Approximately(i.sx, i.sz))
                        throw new ArgumentException("Native Terrain tree uses one horizontal widthScale; sx must equal sz");
                    if (!i.dry_run)
                    {
                        Undo.RecordObject(data, "Aaris AI resize native tree");
                        tree.widthScale = Mathf.Clamp(tree.widthScale * i.sx, 0.1f, 5f);
                        tree.heightScale = Mathf.Clamp(tree.heightScale * i.sy, 0.1f, 5f);
                        trees[treeIndex] = tree;
                        data.treeInstances = trees;
                        EditorUtility.SetDirty(data);
                        AssetDatabase.SaveAssets();
                        r.changedAsset = AssetDatabase.GetAssetPath(data);
                    }
                }
                else if (i.op == "photo")
                {
                    Vector3 point = r.objects[0].position;
                    Photo(point, Mathf.Max(8, i.distance), i.nonce, r);
                }
                r.count = 1;
                return;
            }

            Transform target = Resolve(i.target);
            r.target = Id(target);
            r.objects = new[] { Describe(target) };
            r.count = 1;
            if (i.op == "bounds") return;
            if (i.op == "outline")
            {
                var points = new List<Vector3>();
                int total = 0;
                var filters = target.GetComponentsInChildren<MeshFilter>(true);
                foreach (var filter in filters)
                {
                    if (filter.sharedMesh == null) continue;
                    try
                    {
                        var vertices = filter.sharedMesh.vertices;
                        total += vertices.Length;
                        int left = Math.Max(0, i.max_points - points.Count);
                        int stride = Math.Max(1, (int)Math.Ceiling((double)vertices.Length / Math.Max(1, left)));
                        for (int j = 0; j < vertices.Length && points.Count < i.max_points; j += stride)
                            points.Add(filter.transform.TransformPoint(vertices[j]));
                    }
                    catch (Exception) { /* Nonreadable mesh uses renderer bounds fallback. */ }
                    if (points.Count >= i.max_points) break;
                }
                if (points.Count == 0)
                {
                    Bounds b;
                    if (!TryBounds(target, out b)) throw new ArgumentException("Target has no readable mesh or bounds");
                    for (int n = 0; n < 8; n++)
                        points.Add(b.center + Vector3.Scale(b.extents,
                            new Vector3((n & 1) == 0 ? -1 : 1, (n & 2) == 0 ? -1 : 1,
                                        (n & 4) == 0 ? -1 : 1)));
                    r.meshMode = "bounds-corners-fallback";
                }
                else r.meshMode = "sampled-mesh-vertices";
                r.points = points.ToArray();
                r.totalPoints = total;
                return;
            }
            if (i.op == "photo")
            {
                Bounds b;
                Vector3 center = TryBounds(target, out b) ? b.center : target.position;
                Photo(center, Mathf.Max(i.distance, b.extents.magnitude * 2.6f), i.nonce, r);
                return;
            }
            if (target.GetComponent<Terrain>() != null || target.GetComponent<Camera>() != null ||
                PrefabUtility.IsPartOfPrefabAsset(target.gameObject))
                throw new InvalidOperationException("Terrain root, camera or prefab asset cannot be transformed");
            if (i.op == "move")
            {
                Vector3 next = target.position + new Vector3(i.dx, i.dy, i.dz);
                if (Mathf.Abs(next.x) > 2500 || Mathf.Abs(next.z) > 2500 ||
                    Mathf.Abs(next.y) > 5000)
                    throw new ArgumentException("Target would leave supported world bounds");
                if (!i.dry_run)
                {
                    Undo.RecordObject(target, "Aaris AI move");
                    target.position = next;
                }
            }
            else if (i.op == "scale")
            {
                Vector3 next = Vector3.Scale(target.localScale, new Vector3(i.sx, i.sy, i.sz));
                if (next.x < 0.01f || next.y < 0.01f || next.z < 0.01f ||
                    next.x > 100 || next.y > 100 || next.z > 100)
                    throw new ArgumentException("Resulting object scale outside allowed range");
                if (!i.dry_run)
                {
                    Undo.RecordObject(target, "Aaris AI resize");
                    target.localScale = next;
                }
            }
            if (!i.dry_run)
            {
                EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
                EditorSceneManager.SaveScene(SceneManager.GetActiveScene());
                r.changedAsset = AarisExplorerBuild.ScenePath;
                r.objects = new[] { Describe(target) };
            }
        }

        private static void Photo(Vector3 center, float distance, long nonce, Result r)
        {
            Vector3 cameraPos = center + new Vector3(0.45f, 0.3f, -1f).normalized * distance;
            Quaternion rotation = Quaternion.LookRotation(center - cameraPos, Vector3.up);
            string filename = "ai-photo-" + nonce + ".png";
            AarisLiveCameraBridge.TakePhoto(cameraPos, rotation, Path.Combine(Root, filename));
            r.photo = filename;
        }
    }
}
