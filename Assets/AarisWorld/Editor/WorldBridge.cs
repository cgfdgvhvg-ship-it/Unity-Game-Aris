// Editor-only: inspection/probes never save a scene. Native writes happen only on explicit apply.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Aaris.WorldAutomation
{
    [Serializable] public sealed class Brush { public float x, z, radius, delta; }
    [Serializable] public sealed class Query
    {
        public string command, scene, target, capturePath;
        public Vector3[] waypoints;
        public Brush[] brushes;
        public int maxSteps = 4000;
        public Vector3 cameraPosition, cameraTarget;
    }
    [Serializable] public sealed class Entry
    {
        public string id, name, parentId;
        public Vector3 position, boundsCenter, boundsSize;
        public bool hasRendererBounds;
        public string[] components;
    }
    [Serializable] public sealed class Contact
    {
        public string id, name;
        public Vector3 point, normal, boundsCenter, boundsSize;
    }
    [Serializable] public sealed class Route
    {
        public string status, interpretation;
        public Vector3 start, target, reached;
        public int steps;
        public float remainingMetres;
        public float groundHeightAtReached, terrainSlopeAtReached;
        public Vector3 terrainNormalAtReached;
        public Contact[] contacts;
    }
    [Serializable] public sealed class Response
    {
        public string status = "ok", command, error, unityVersion, note;
        public Entry[] objects;
        public Route[] routes;
        public string[] changedAssets;
        public bool sceneSaved, temporaryBotDestroyed;
    }

    public static class WorldBridge
    {
        public static string Id(GameObject go)
        {
            var id = GlobalObjectId.GetGlobalObjectIdSlow(go);
            // Prefab instances require targetPrefabId too; use Unity's complete ID there.
            return id.targetPrefabId == 0 ? "scene:" + id.assetGUID + ":" + unchecked((long)id.targetObjectId) : id.ToString();
        }

        private static GameObject Resolve(Scene scene, string target)
        {
            var all = scene.GetRootGameObjects().SelectMany(g => g.GetComponentsInChildren<Transform>(true))
                .Select(t => t.gameObject).Where(g => Id(g) == target).ToArray();
            if (all.Length != 1) throw new InvalidOperationException("Target must be an exact stable scene object ID");
            return all[0];
        }

        public static void Run()
        {
            string responsePath = Environment.GetEnvironmentVariable("AARIS_WORLD_RESPONSE");
            var result = new Response { unityVersion = Application.unityVersion };
            try
            {
                string path = Environment.GetEnvironmentVariable("AARIS_WORLD_REQUEST");
                if (string.IsNullOrEmpty(path) || string.IsNullOrEmpty(responsePath))
                    throw new InvalidOperationException("Use Tools/World/world.py engine; request/response paths are required");
                var query = JsonUtility.FromJson<Query>(File.ReadAllText(path));
                if (query.scene != "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity")
                    throw new InvalidOperationException("Only the authored map scene is supported");
                result.command = query.command;
                Scene scene = EditorSceneManager.OpenScene(query.scene, OpenSceneMode.Single);
                if (query.command == "export") result.objects = Export(scene);
                else if (query.command == "probe") Probe(scene, query, result);
                else if (query.command == "capture") Capture(scene, query, result);
                else if (query.command == "apply") Apply(scene, query, result);
                else throw new InvalidOperationException("Unsupported engine command");
                result.note = "Editor physics/render evidence is separate from Android performance. Original checkout is isolated by the Python launcher.";
            }
            catch (Exception e) { result.status = "error"; result.error = e.ToString(); }
            if (!string.IsNullOrEmpty(responsePath)) File.WriteAllText(responsePath, JsonUtility.ToJson(result, true));
            if (result.status != "ok") EditorApplication.Exit(1);
        }

        private static Entry[] Export(Scene scene)
        {
            return scene.GetRootGameObjects().SelectMany(g => g.GetComponentsInChildren<Transform>(true)).Select(t =>
            {
                var renderers = t.GetComponentsInChildren<Renderer>(true);
                Bounds b = new Bounds();
                if (renderers.Length > 0) { b = renderers[0].bounds; foreach (var r in renderers.Skip(1)) b.Encapsulate(r.bounds); }
                return new Entry { id = Id(t.gameObject), name = t.name, parentId = t.parent == null ? null : Id(t.parent.gameObject),
                    position = t.position, hasRendererBounds = renderers.Length > 0, boundsCenter = b.center, boundsSize = b.size,
                    components = t.GetComponents<Component>().Select(c => c == null ? "MissingScript" : c.GetType().FullName).ToArray() };
            }).ToArray();
        }

        private static void Probe(Scene scene, Query query, Response result)
        {
            bool candidates = query.waypoints == null || query.waypoints.Length == 0;
            var attempts = new List<Vector3[]>();
            if (candidates)
            {
                var target = Resolve(scene, query.target);
                var renderers = target.GetComponentsInChildren<Renderer>(true);
                if (renderers.Length == 0) throw new InvalidOperationException("Automatic candidates need renderer bounds; provide explicit waypoints instead");
                Bounds bounds = renderers[0].bounds; foreach (var r in renderers.Skip(1)) bounds.Encapsulate(r.bounds);
                Vector3 center = bounds.center;
                foreach (var offset in new[] { new Vector3(bounds.extents.x+2,0,0), new Vector3(-bounds.extents.x-2,0,0),
                    new Vector3(0,0,bounds.extents.z+2), new Vector3(0,0,-bounds.extents.z-2) })
                {
                    Vector3 start = center+offset, end = center;
                    start.y = Ground(scene, start)+.05f; end.y = Ground(scene, end)+.05f;
                    attempts.Add(new[] { start, end });
                }
            }
            else if (query.waypoints.Length < 2 || query.waypoints.Length > 33)
                throw new InvalidOperationException("Probe needs 2..33 world-space foot-position waypoints");
            else attempts.Add(query.waypoints);
            if (query.maxSteps < 10 || query.maxSteps > 20000) throw new InvalidOperationException("maxSteps must be 10..20000");
            foreach (var p in attempts.SelectMany(a => a))
                if (!Finite(p) || Mathf.Abs(p.x) > 1000 || Mathf.Abs(p.z) > 1000 || Mathf.Abs(p.y) > 2000)
                    throw new InvalidOperationException("Invalid probe waypoint");
            var disabled = new List<Collider>();
            var controllers = new List<CharacterController>();
            GameObject bot = null;
            try
            {
                foreach (var root in scene.GetRootGameObjects())
                {
                    foreach (var c in root.GetComponentsInChildren<Collider>(true))
                    {
                        if (c is CharacterController controller) { if (controller.enabled) { controllers.Add(controller); controller.enabled = false; } }
                        else if (!c.enabled) { disabled.Add(c); c.enabled = true; }
                    }
                }
                bot = new GameObject("__AarisTemporaryEntryProbe");
                bot.hideFlags = HideFlags.HideAndDontSave;
                bot.layer = 2; // IgnoreRaycast: casts below do not hit the probe itself.
                var cc = bot.AddComponent<CharacterController>();
                cc.height = 1.78f; cc.radius = .28f; cc.center = new Vector3(0, .89f, 0);
                cc.stepOffset = .30f; cc.slopeLimit = 46; cc.skinWidth = .035f; cc.minMoveDistance = 0;
                var hits = new List<Contact>();
                var routes = new List<Route>();
                const float dt = 1f / 60f;
                int totalSteps = 0;
                foreach (var attempt in attempts)
                {
                  cc.enabled = false; bot.transform.position = attempt[0]; cc.enabled = true; Physics.SyncTransforms();
                  for (int leg = 1; leg < attempt.Length; leg++)
                  {
                    Vector3 start = bot.transform.position, target = attempt[leg];
                    hits.Clear(); int stalled = 0, steps = 0; float vertical = 0;
                    string status = "step_budget_exhausted";
                    for (; totalSteps < query.maxSteps; totalSteps++, steps++)
                    {
                        Vector3 delta = target - bot.transform.position;
                        if (new Vector2(delta.x, delta.z).magnitude < .20f && Mathf.Abs(delta.y) < .45f)
                        { status = "tested_route_passed"; break; }
                        Vector3 before = bot.transform.position;
                        Vector3 planar = new Vector3(delta.x, 0, delta.z);
                        Vector3 move = Vector3.ClampMagnitude(planar, 4.2f*dt);
                        if (move.sqrMagnitude > 0)
                        {
                            var candidates = Physics.CapsuleCastAll(before+Vector3.up*.28f, before+Vector3.up*1.50f,
                                .28f, move.normalized, move.magnitude+.035f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
                            foreach (var hit in candidates)
                            {
                                string id = Id(hit.collider.gameObject);
                                if (hit.normal.y > .65f || hits.Count >= 32 || hits.Any(c => c.id == id)) continue;
                                hits.Add(new Contact { id = id, name = hit.collider.name, point = hit.point, normal = hit.normal,
                                    boundsCenter = hit.collider.bounds.center, boundsSize = hit.collider.bounds.size });
                            }
                        }
                        vertical = cc.isGrounded ? -2 : Mathf.Max(vertical-24*dt, -40);
                        cc.Move(move + Vector3.up*(vertical*dt)); Physics.SyncTransforms();
                        float progress = new Vector2(bot.transform.position.x-before.x, bot.transform.position.z-before.z).magnitude;
                        stalled = progress < .001f ? stalled+1 : 0;
                        if (stalled > 90) { status = "tested_route_blocked"; break; }
                    }
                    float slope; Vector3 normal;
                    float ground = Ground(scene, bot.transform.position, out slope, out normal);
                    routes.Add(new Route { status = status, start = start, target = target, reached = bot.transform.position,
                        steps = steps, remainingMetres = Vector3.Distance(bot.transform.position, target), contacts = hits.ToArray(),
                        groundHeightAtReached = ground, terrainSlopeAtReached = slope, terrainNormalAtReached = normal,
                        interpretation = candidates ? "Automatic AABB-side-to-center candidate only: center may not be an interior; blocked candidate is not proof of no entrance. Contacts are nearby sweep candidates."
                            : "Contacts are capsule-sweep candidates near the walking path, not proof of the sole blocker. Result does not prove all entrances are blocked or that visible walls have colliders." });
                    if (status != "tested_route_passed") break;
                  }
                }
                result.routes = routes.ToArray();
            }
            finally
            {
                if (bot != null) UnityEngine.Object.DestroyImmediate(bot);
                foreach (var c in disabled) if (c != null) c.enabled = false;
                foreach (var c in controllers) if (c != null) c.enabled = true;
                Physics.SyncTransforms(); result.temporaryBotDestroyed = true;
            }
            // No SaveScene, SaveAssets, navigation bake or permanent bot assets.
        }

        private static bool Finite(Vector3 v)
        { return !(float.IsNaN(v.x) || float.IsInfinity(v.x) || float.IsNaN(v.y) || float.IsInfinity(v.y) || float.IsNaN(v.z) || float.IsInfinity(v.z)); }

        private static float Ground(Scene scene, Vector3 point)
        { float slope; Vector3 normal; return Ground(scene, point, out slope, out normal); }

        private static float Ground(Scene scene, Vector3 point, out float slope, out Vector3 normal)
        {
            foreach (var t in scene.GetRootGameObjects().SelectMany(g => g.GetComponentsInChildren<Terrain>(true)))
            {
                var o = t.transform.position; var s = t.terrainData.size;
                if (point.x >= o.x && point.x <= o.x+s.x && point.z >= o.z && point.z <= o.z+s.z)
                {
                    float x=(point.x-o.x)/s.x, z=(point.z-o.z)/s.z;
                    slope=t.terrainData.GetSteepness(x,z); normal=t.terrainData.GetInterpolatedNormal(x,z);
                    return t.SampleHeight(point)+o.y;
                }
            }
            throw new InvalidOperationException("Candidate lies outside saved terrain; choose explicit waypoints");
        }

        private static void Apply(Scene scene, Query query, Response result)
        {
            if (query.brushes == null) query.brushes = Array.Empty<Brush>();
            var changed = new HashSet<string>();
            var terrains = scene.GetRootGameObjects().SelectMany(g => g.GetComponentsInChildren<Terrain>(true)).ToArray();
            foreach (var brush in query.brushes)
            {
                if (!(brush.radius > 0 && brush.radius <= 100) || Mathf.Abs(brush.delta) > 20)
                    throw new InvalidOperationException("Brush exceeds the reviewed bounds");
                int touched = 0;
                foreach (var t in terrains)
                {
                    if (t.transform.rotation != Quaternion.identity || t.transform.lossyScale != Vector3.one)
                        throw new InvalidOperationException("Terrain must be unrotated with unit scale");
                    var data = t.terrainData; Vector3 o = t.transform.position, size = data.size;
                    if (brush.x+brush.radius < o.x || brush.x-brush.radius > o.x+size.x || brush.z+brush.radius < o.z || brush.z-brush.radius > o.z+size.z) continue;
                    int n = data.heightmapResolution;
                    int x0 = Mathf.Clamp(Mathf.FloorToInt((brush.x-brush.radius-o.x)/size.x*(n-1)), 0, n-1);
                    int z0 = Mathf.Clamp(Mathf.FloorToInt((brush.z-brush.radius-o.z)/size.z*(n-1)), 0, n-1);
                    int x1 = Mathf.Clamp(Mathf.CeilToInt((brush.x+brush.radius-o.x)/size.x*(n-1)), 0, n-1);
                    int z1 = Mathf.Clamp(Mathf.CeilToInt((brush.z+brush.radius-o.z)/size.z*(n-1)), 0, n-1);
                    var h = data.GetHeights(x0, z0, x1-x0+1, z1-z0+1);
                    for (int z = 0; z < h.GetLength(0); z++) for (int x = 0; x < h.GetLength(1); x++)
                    {
                        float wx = o.x+(x0+x)*size.x/(n-1), wz = o.z+(z0+z)*size.z/(n-1);
                        float q = Mathf.Clamp01(1-Vector2.Distance(new Vector2(wx, wz), new Vector2(brush.x, brush.z))/brush.radius);
                        float next = h[z,x] + brush.delta*q*q*(3-2*q)/size.y;
                        if (next < 0 || next > 1) throw new InvalidOperationException("Brush would clip terrain height range");
                        h[z,x] = next;
                    }
                    data.SetHeights(x0, z0, h); EditorUtility.SetDirty(data); touched++;
                    changed.Add(AssetDatabase.GetAssetPath(data));
                }
                if (touched == 0) throw new InvalidOperationException("Brush lies outside the saved terrain");
            }
            AssetDatabase.SaveAssets(); result.changedAssets = changed.OrderBy(x => x).ToArray();
            result.sceneSaved = false;
        }

        private static void Capture(Scene scene, Query query, Response result)
        {
            if (SystemInfo.graphicsDeviceType == UnityEngine.Rendering.GraphicsDeviceType.Null)
                throw new InvalidOperationException("Capture needs a graphics-capable Unity runner; no fake image is produced");
            if (!Finite(query.cameraPosition) || !Finite(query.cameraTarget) || Vector3.Distance(query.cameraPosition, query.cameraTarget) < .01f)
                throw new InvalidOperationException("Capture requires finite, distinct cameraPosition and cameraTarget");
            var go = new GameObject("__AarisTemporaryCapture"); RenderTexture rt = null; Texture2D tex = null;
            var old = RenderTexture.active;
            try
            {
                var camera = go.AddComponent<Camera>(); if (Camera.main != null) camera.CopyFrom(Camera.main);
                camera.transform.position = query.cameraPosition; camera.transform.LookAt(query.cameraTarget);
                rt = new RenderTexture(1280, 720, 24); rt.Create(); camera.targetTexture = rt;
                var request = new UniversalRenderPipeline.SingleCameraRequest { destination = rt };
                if (!RenderPipeline.SupportsRenderRequest(camera, request)) throw new InvalidOperationException("Active pipeline does not support URP camera requests");
                RenderPipeline.SubmitRenderRequest(camera, request); RenderTexture.active = rt;
                tex = new Texture2D(1280, 720, TextureFormat.RGB24, false); tex.ReadPixels(new Rect(0,0,1280,720),0,0); tex.Apply();
                File.WriteAllBytes(query.capturePath, tex.EncodeToPNG());
            }
            finally
            {
                RenderTexture.active = old;
                if (tex != null) UnityEngine.Object.DestroyImmediate(tex);
                if (rt != null) { rt.Release(); UnityEngine.Object.DestroyImmediate(rt); }
                UnityEngine.Object.DestroyImmediate(go);
            }
        }
    }
}
