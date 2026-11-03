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
    [Serializable] public sealed class ProbeSpec
    {
        public string id, target;
        public Vector3[] waypoints;
        public int maxSteps = 4000;
    }
    [Serializable] public sealed class TerrainEdit
    {
        public string id, action, target, terrainGuid;
        public int originalIndex = -1, prototypeIndex = -1, expectedPrototypeIndex = -1;
        public float worldX, worldZ, widthScale, heightScale, yawDegrees;
        public Vector3 expectedWorldPosition;
        public float expectedWidthScale, expectedHeightScale, expectedYawDegrees;
    }
    [Serializable] public sealed class SceneEdit
    {
        public string id, action, target, prefabPath, parent, name;
        public bool hasWorldPosition, hasWorldRotation, hasLocalScale;
        public Vector3 worldPosition, worldRotationEuler, localScale;
    }
    [Serializable] public sealed class ObservationRequest
    {
        public string target;
        public bool hasPoint, hasY;
        public Vector3 point;
        public float radius = 35;
        public int limit = 100;
    }
    [Serializable] public sealed class Query
    {
        public string command, scene, target, capturePath;
        public Vector3[] waypoints;
        public ProbeSpec[] probes;
        public Brush[] brushes;
        public TerrainEdit[] terrainEdits;
        public SceneEdit[] sceneEdits;
        public ObservationRequest[] observations;
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
        public string probeId, status, interpretation;
        public Vector3 start, target, reached;
        public int steps;
        public float remainingMetres;
        public float groundHeightAtReached, terrainSlopeAtReached;
        public Vector3 terrainNormalAtReached;
        public Contact[] contacts;
    }
    [Serializable] public sealed class Observation
    {
        public string target, supportId, supportName, interpretation;
        public Vector3 center, supportPoint, terrainNormal;
        public float radius, terrainHeight, terrainSlope, pointMinusTerrain, supportGap;
        public bool terrainFound, supportFound;
        public Contact[] nearbyColliders;
    }
    [Serializable] public sealed class IdentityChange
    {
        public string operationId, beforeId, afterId;
    }
    [Serializable] public sealed class Response
    {
        public string status = "ok", command, error, unityVersion, note;
        public Entry[] objects;
        public Route[] routes;
        public Observation[] observations;
        public IdentityChange[] identityChanges;
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
                else if (query.command == "observe") result.observations = Observe(scene, query.observations);
                else if (query.command == "probe") Probe(scene, query, result);
                else if (query.command == "capture") Capture(scene, query, result);
                else if (query.command == "apply" || query.command == "preview")
                {
                    Apply(scene, query, result);
                    result.observations = Observe(scene, query.observations);
                }
                else throw new InvalidOperationException("Unsupported engine command");
                string evidenceNote = "Editor physics/render evidence is separate from Android performance. Original checkout is isolated by the Python launcher.";
                result.note = string.IsNullOrEmpty(result.note) ? evidenceNote : result.note + " " + evidenceNote;
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
            if (query.probes != null && query.probes.Length > 0)
            {
                if (query.probes.Length > 32) throw new InvalidOperationException("At most 32 independent probe bots are allowed per request");
                if (query.probes.Any(p => string.IsNullOrEmpty(p.id)) || query.probes.Select(p => p.id).Distinct().Count() != query.probes.Length)
                    throw new InvalidOperationException("Every probe bot needs a unique non-empty id");
                var combined = new List<Route>();
                foreach (var spec in query.probes)
                {
                    var one = new Query { command = "probe", scene = query.scene, target = spec.target,
                        waypoints = spec.waypoints, maxSteps = spec.maxSteps > 0 ? spec.maxSteps : query.maxSteps };
                    var oneResult = new Response();
                    Probe(scene, one, oneResult);
                    foreach (var route in oneResult.routes ?? Array.Empty<Route>()) route.probeId = spec.id;
                    combined.AddRange(oneResult.routes ?? Array.Empty<Route>());
                }
                result.routes = combined.ToArray();
                result.temporaryBotDestroyed = true;
                result.note = "Independent deterministic probe bots ran in one isolated editor import. They do not plan routes or simulate combat AI.";
                return;
            }
            bool automaticCandidates = query.waypoints == null || query.waypoints.Length == 0;
            var attempts = new List<Vector3[]>();
            if (automaticCandidates)
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
                            var capsuleHits = Physics.CapsuleCastAll(before+Vector3.up*.28f, before+Vector3.up*1.50f,
                                .28f, move.normalized, move.magnitude+.035f, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
                            foreach (var hit in capsuleHits)
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
                        interpretation = automaticCandidates ? "Automatic AABB-side-to-center candidate only: center may not be an interior; blocked candidate is not proof of no entrance. Contacts are nearby sweep candidates."
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

        private static Observation[] Observe(Scene scene, ObservationRequest[] requests)
        {
            if (requests == null || requests.Length == 0) return Array.Empty<Observation>();
            if (requests.Length > 32) throw new InvalidOperationException("At most 32 observation requests are allowed");
            var temporarilyEnabled = new List<Collider>();
            try
            {
                foreach (var root in scene.GetRootGameObjects())
                    foreach (var collider in root.GetComponentsInChildren<Collider>(true))
                        if (!(collider is CharacterController) && !collider.enabled)
                        { collider.enabled = true; temporarilyEnabled.Add(collider); }
                Physics.SyncTransforms();
                var output = new List<Observation>();
                foreach (var request in requests)
                {
                    if (!(request.radius > 0 && request.radius <= 500) || request.limit < 1 || request.limit > 500)
                        throw new InvalidOperationException("Observation radius must be 0..500 and limit 1..500");
                    GameObject target = null;
                    Vector3 center;
                    Bounds targetBounds = new Bounds();
                    bool hasBounds = false;
                    if (!string.IsNullOrEmpty(request.target))
                    {
                        target = Resolve(scene, request.target);
                        center = target.transform.position;
                        var renderers = target.GetComponentsInChildren<Renderer>(true);
                        if (renderers.Length > 0)
                        {
                            targetBounds = renderers[0].bounds;
                            foreach (var renderer in renderers.Skip(1)) targetBounds.Encapsulate(renderer.bounds);
                            hasBounds = true;
                        }
                    }
                    else if (request.hasPoint && Finite(request.point)) center = request.point;
                    else throw new InvalidOperationException("Observation requires a stable target or finite point");

                    float slope = 0; Vector3 normal = Vector3.up; float ground = 0; bool groundFound = false;
                    try
                    {
                        ground = Ground(scene, center, out slope, out normal); groundFound = true;
                        if (request.hasPoint && !request.hasY) center.y = ground;
                    }
                    catch (InvalidOperationException) { }

                    float bottom = hasBounds ? targetBounds.min.y : center.y;
                    Vector3 rayOrigin = new Vector3(center.x, bottom + .20f, center.z);
                    var rayHits = Physics.RaycastAll(rayOrigin, Vector3.down, 5000, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore)
                        .OrderBy(hit => hit.distance).ToArray();
                    RaycastHit? support = null;
                    foreach (var hit in rayHits)
                    {
                        if (target != null && hit.collider.transform.IsChildOf(target.transform)) continue;
                        support = hit; break;
                    }

                    var contacts = Physics.OverlapSphere(center, request.radius, Physics.DefaultRaycastLayers, QueryTriggerInteraction.Collide)
                        .Where(c => target == null || !c.transform.IsChildOf(target.transform))
                        .GroupBy(c => Id(c.gameObject)).Select(group => group.First())
                        .OrderBy(c => Vector3.Distance(center, c.ClosestPoint(center))).Take(request.limit)
                        .Select(c => new Contact { id = Id(c.gameObject), name = c.name, point = c.ClosestPoint(center),
                            normal = Vector3.zero, boundsCenter = c.bounds.center, boundsSize = c.bounds.size }).ToArray();
                    var observation = new Observation { target = request.target, center = center, radius = request.radius,
                        terrainFound = groundFound, terrainHeight = ground, terrainSlope = slope, terrainNormal = normal,
                        pointMinusTerrain = groundFound ? center.y-ground : 0, nearbyColliders = contacts,
                        interpretation = "Exact active collider/terrain evidence in the isolated matching Unity Editor. The AI/caller decides whether the measured relationship is intended." };
                    if (support.HasValue)
                    {
                        var hit = support.Value; observation.supportFound = true;
                        observation.supportId = Id(hit.collider.gameObject); observation.supportName = hit.collider.name;
                        observation.supportPoint = hit.point; observation.supportGap = bottom-hit.point.y;
                    }
                    output.Add(observation);
                }
                return output.ToArray();
            }
            finally
            {
                foreach (var collider in temporarilyEnabled) if (collider != null) collider.enabled = false;
                Physics.SyncTransforms();
            }
        }

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

        private static string TerrainGuid(Terrain terrain)
        { return AssetDatabase.AssetPathToGUID(AssetDatabase.GetAssetPath(terrain.terrainData)); }

        private static Vector3 TreeWorldPosition(Terrain terrain, TreeInstance instance)
        {
            Vector3 origin = terrain.transform.position, size = terrain.terrainData.size;
            return new Vector3(origin.x+instance.position.x*size.x, origin.y+instance.position.y*size.y,
                origin.z+instance.position.z*size.z);
        }

        private static void ValidateTreePrecondition(Terrain terrain, TerrainEdit edit, TreeInstance instance)
        {
            Vector3 actual = TreeWorldPosition(terrain, instance);
            if (edit.expectedPrototypeIndex != instance.prototypeIndex || Vector3.Distance(actual, edit.expectedWorldPosition) > .05f
                || Mathf.Abs(instance.widthScale-edit.expectedWidthScale) > .0001f
                || Mathf.Abs(instance.heightScale-edit.expectedHeightScale) > .0001f
                || Mathf.Abs(Mathf.DeltaAngle(instance.rotation*Mathf.Rad2Deg, edit.expectedYawDegrees)) > .02f)
                throw new InvalidOperationException("Native terrain instance changed since inspection: " + edit.target);
        }

        private static void ApplyTerrainInstances(Terrain[] terrains, TerrainEdit[] edits,
            HashSet<string> changed, List<IdentityChange> identities)
        {
            if (edits == null || edits.Length == 0) return;
            foreach (var group in edits.GroupBy(edit => edit.terrainGuid))
            {
                Terrain terrain = terrains.SingleOrDefault(t => TerrainGuid(t) == group.Key);
                if (terrain == null) throw new InvalidOperationException("Terrain GUID not present in the saved scene: " + group.Key);
                if (terrain.transform.rotation != Quaternion.identity || terrain.transform.lossyScale != Vector3.one)
                    throw new InvalidOperationException("Terrain must be unrotated with unit scale");
                TerrainData data = terrain.terrainData; Vector3 origin = terrain.transform.position, size = data.size;
                TreeInstance[] original = data.treeInstances;
                var modified = original.ToArray(); var removed = new HashSet<int>();
                var additions = new List<KeyValuePair<TerrainEdit, TreeInstance>>();
                foreach (var edit in group)
                {
                    if (edit.action == "add")
                    {
                        if (edit.prototypeIndex < 0 || edit.prototypeIndex >= data.treePrototypes.Length)
                            throw new InvalidOperationException("Native prototype index is outside the terrain table");
                        float nx=(edit.worldX-origin.x)/size.x, nz=(edit.worldZ-origin.z)/size.z;
                        if (nx < 0 || nx > 1 || nz < 0 || nz > 1) throw new InvalidOperationException("Native add lies outside selected terrain");
                        var instance = new TreeInstance { prototypeIndex=edit.prototypeIndex,
                            position=new Vector3(nx, data.GetInterpolatedHeight(nx,nz)/size.y, nz),
                            widthScale=edit.widthScale, heightScale=edit.heightScale,
                            rotation=edit.yawDegrees*Mathf.Deg2Rad, color=Color.white, lightmapColor=Color.white };
                        additions.Add(new KeyValuePair<TerrainEdit, TreeInstance>(edit, instance));
                        continue;
                    }
                    int index = edit.originalIndex;
                    if (index < 0 || index >= original.Length || edit.target != "terrain:"+group.Key+":"+index)
                        throw new InvalidOperationException("Invalid original native instance identity: " + edit.target);
                    ValidateTreePrecondition(terrain, edit, original[index]);
                    if (removed.Contains(index)) throw new InvalidOperationException("The same native instance was removed twice");
                    TreeInstance current = modified[index];
                    if (edit.action == "remove") removed.Add(index);
                    else if (edit.action == "move")
                    {
                        float nx=(edit.worldX-origin.x)/size.x, nz=(edit.worldZ-origin.z)/size.z;
                        if (nx < 0 || nx > 1 || nz < 0 || nz > 1) throw new InvalidOperationException("Native move crosses its TerrainData tile");
                        current.position=new Vector3(nx, data.GetInterpolatedHeight(nx,nz)/size.y, nz); modified[index]=current;
                    }
                    else if (edit.action == "scale")
                    { current.widthScale=edit.widthScale; current.heightScale=edit.heightScale; modified[index]=current; }
                    else if (edit.action == "rotate")
                    { current.rotation=edit.yawDegrees*Mathf.Deg2Rad; modified[index]=current; }
                    else throw new InvalidOperationException("Unsupported native instance action: " + edit.action);
                }
                var rebuilt = new List<TreeInstance>(); var newIndex = new Dictionary<int,int>();
                for (int i=0;i<modified.Length;i++) if (!removed.Contains(i))
                { newIndex[i]=rebuilt.Count; rebuilt.Add(modified[i]); }
                foreach (var addition in additions) rebuilt.Add(addition.Value);
                data.SetTreeInstances(rebuilt.ToArray(), true); EditorUtility.SetDirty(data);
                changed.Add(AssetDatabase.GetAssetPath(data));
                foreach (var edit in group.Where(e => e.action != "add"))
                    identities.Add(new IdentityChange { operationId=edit.id, beforeId=edit.target,
                        afterId=removed.Contains(edit.originalIndex) ? null : "terrain:"+group.Key+":"+newIndex[edit.originalIndex] });
                for (int i=0;i<additions.Count;i++)
                    identities.Add(new IdentityChange { operationId=additions[i].Key.id, beforeId=null,
                        afterId="terrain:"+group.Key+":"+(rebuilt.Count-additions.Count+i) });
            }
        }

        private static void ApplySceneEdits(Scene scene, SceneEdit[] edits, HashSet<string> changed,
            List<IdentityChange> identities)
        {
            if (edits == null || edits.Length == 0) return;
            var created = new List<KeyValuePair<SceneEdit, GameObject>>();
            foreach (var edit in edits)
            {
                if (edit.action == "delete")
                {
                    GameObject target = Resolve(scene, edit.target);
                    UnityEngine.Object.DestroyImmediate(target);
                    identities.Add(new IdentityChange { operationId=edit.id, beforeId=edit.target, afterId=null });
                    continue;
                }
                GameObject go;
                if (edit.action == "instantiate")
                {
                    GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(edit.prefabPath);
                    if (prefab == null) throw new InvalidOperationException("Prefab failed to import: " + edit.prefabPath);
                    go = PrefabUtility.InstantiatePrefab(prefab, scene) as GameObject;
                    if (go == null) throw new InvalidOperationException("Prefab instantiation failed");
                }
                else if (edit.action == "duplicate")
                {
                    GameObject source = Resolve(scene, edit.target);
                    go = UnityEngine.Object.Instantiate(source);
                    SceneManager.MoveGameObjectToScene(go, scene);
                }
                else throw new InvalidOperationException("Unsupported scene edit action: " + edit.action);
                if (!string.IsNullOrEmpty(edit.parent)) go.transform.SetParent(Resolve(scene, edit.parent).transform, true);
                if (edit.hasWorldPosition) go.transform.position=edit.worldPosition;
                if (edit.hasWorldRotation) go.transform.rotation=Quaternion.Euler(edit.worldRotationEuler);
                if (edit.hasLocalScale) go.transform.localScale=edit.localScale;
                if (!string.IsNullOrEmpty(edit.name)) go.name=edit.name;
                created.Add(new KeyValuePair<SceneEdit, GameObject>(edit, go));
            }
            EditorSceneManager.MarkSceneDirty(scene);
            if (!EditorSceneManager.SaveScene(scene)) throw new InvalidOperationException("Unity failed to save the authored map scene");
            changed.Add(scene.path);
            foreach (var pair in created)
                identities.Add(new IdentityChange { operationId=pair.Key.id,
                    beforeId=pair.Key.action == "duplicate" ? pair.Key.target : null, afterId=Id(pair.Value) });
        }

        private static void Apply(Scene scene, Query query, Response result)
        {
            if (query.brushes == null) query.brushes = Array.Empty<Brush>();
            var changed = new HashSet<string>(); var identities = new List<IdentityChange>();
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
            ApplyTerrainInstances(terrains, query.terrainEdits, changed, identities);
            ApplySceneEdits(scene, query.sceneEdits, changed, identities);
            AssetDatabase.SaveAssets(); result.changedAssets = changed.OrderBy(x => x).ToArray();
            result.identityChanges = identities.ToArray();
            result.sceneSaved = query.sceneEdits != null && query.sceneEdits.Length > 0;
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

