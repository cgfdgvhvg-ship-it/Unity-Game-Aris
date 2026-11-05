#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace Aaris.WorldAutomation
{
    /// <summary>Native Editor-only, file-based live world sensor/editor.
    /// Jobs/results/captures live outside Assets and outside Git.
    /// The only permanent edit is a saved Unity Scene or TerrainData asset.</summary>
    [InitializeOnLoad]
    public static class AarisLiveEditorBridge
    {
        private const string MapScene = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity";
        private static readonly string Root = "/home/codespace/.aaris-desktop";
        private static readonly string Inbox = Path.Combine(Root, "unity-commands");
        private static readonly string Results = Path.Combine(Root, "unity-results");
        private static readonly string Frames = Path.Combine(Root, "frames");
        private static readonly string SessionFile = Path.Combine(Root, "unity-session.json");
        private static double nextPoll;
        private static double nextSave;
        private static bool restored;

        [Serializable] public sealed class Request
        {
            public string id, action, target;
            public Vector3 delta, scale, cameraPosition, cameraTarget, expectedPosition;
            public bool hasExpectedPosition;
            public float radius = 40f;
            public int limit = 24;
        }
        [Serializable] private sealed class Session
        {
            public string scenePath, selectedId;
            public Vector3 pivot;
            public Quaternion rotation;
            public float size;
        }
        [Serializable] public sealed class Item
        {
            public string id, name, category, material, sourceAsset;
            public Vector3 position, scale, rendererSize;
            public float distance;
            public bool hasCollider;
        }
        [Serializable] public sealed class Response
        {
            public string id, action, status = "ok", error, unityVersion, scene, changedAsset, screenshotPath;
            public string targetId;
            public float groundY, groundSlopeDegrees;
            public Vector3 groundNormal, position, scale;
            public int sceneObjectCount, terrainTreeCount;
            public Item[] nearbyObjects, nearbyTerrainTrees;
        }

        static AarisLiveEditorBridge()
        {
            EditorApplication.update -= Update;
            EditorApplication.update += Update;
            EditorApplication.delayCall += RestoreScene;
        }
        private static void RestoreScene()
        {
            if (restored || EditorApplication.isCompiling || EditorApplication.isUpdating) return;
            try
            {
                Scene active = SceneManager.GetActiveScene();
                if (!active.IsValid() || (active.path != MapScene && !active.isDirty))
                {
                    Scene scene = SceneManager.GetSceneByPath(MapScene);
                    if (!scene.IsValid() || !scene.isLoaded)
                        EditorSceneManager.OpenScene(MapScene, OpenSceneMode.Single);
                }
                restored = true;
                if (File.Exists(SessionFile))
                {
                    Session state = JsonUtility.FromJson<Session>(File.ReadAllText(SessionFile));
                    if (state != null && state.scenePath == MapScene)
                    {
                        SceneView view = SceneView.lastActiveSceneView;
                        if (view != null && state.size > .1f)
                            view.LookAtDirect(state.pivot, state.rotation, state.size);
                        if (!string.IsNullOrEmpty(state.selectedId))
                        {
                            GameObject selected = FindObject(state.selectedId);
                            if (selected != null) Selection.activeGameObject = selected;
                        }
                    }
                }
                Debug.Log("AARIS_LIVE_EDITOR_READY scene=" + SceneManager.GetActiveScene().path);
            }
            catch (Exception e) { Debug.LogError("AARIS_LIVE_RESTORE_FAILED " + e.Message); }
        }
        private static void Update()
        {
            if (EditorApplication.timeSinceStartup < nextPoll) return;
            nextPoll = EditorApplication.timeSinceStartup + .7;
            if (!restored) RestoreScene();
            try
            {
                Directory.CreateDirectory(Inbox);
                Directory.CreateDirectory(Results);
                if (EditorApplication.timeSinceStartup > nextSave)
                {
                    nextSave = EditorApplication.timeSinceStartup + 12;
                    SaveSession();
                    DeleteExpiredFrames();
                }
                if (EditorApplication.isCompiling || EditorApplication.isUpdating ||
                    EditorApplication.isPlayingOrWillChangePlaymode) return;
                foreach (string path in Directory.GetFiles(Inbox, "*.json").OrderBy(x => x).Take(2))
                    Process(path);
            }
            catch (Exception e) { Debug.LogError("AARIS_LIVE_POLL_ERROR " + e.Message); }
        }
        private static string Id(GameObject go)
        {
            return GlobalObjectId.GetGlobalObjectIdSlow(go).ToString();
        }
        private static GameObject FindObject(string id)
        {
            if (string.IsNullOrEmpty(id)) return null;
            GameObject match = null;
            foreach (GameObject go in UnityEngine.Object.FindObjectsByType<GameObject>(
                         FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (!go.scene.IsValid() || go.scene.path != MapScene) continue;
                if (Id(go) == id) return go;
                if (go.name == id)
                {
                    if (match != null) throw new InvalidOperationException("Ambiguous object name; use stable id");
                    match = go;
                }
            }
            return match;
        }
        private static void SaveSession()
        {
            Scene scene = SceneManager.GetActiveScene();
            if (!scene.IsValid() || scene.path != MapScene) return;
            SceneView view = SceneView.lastActiveSceneView;
            if (view == null) return;
            var state = new Session
            {
                scenePath = MapScene, pivot = view.pivot, rotation = view.rotation,
                size = view.size,
                selectedId = Selection.activeGameObject != null &&
                             Selection.activeGameObject.scene.path == MapScene
                    ? Id(Selection.activeGameObject) : null
            };
            AtomicWrite(SessionFile, JsonUtility.ToJson(state, true));
        }
        private static void AtomicWrite(string path, string text)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            File.WriteAllText(temp, text);
            if (File.Exists(path)) File.Delete(path);
            File.Move(temp, path);
        }
        private static void Process(string path)
        {
            Request request = null;
            var result = new Response { unityVersion = Application.unityVersion, scene = MapScene };
            try
            {
                request = JsonUtility.FromJson<Request>(File.ReadAllText(path));
                if (request == null || string.IsNullOrEmpty(request.id) ||
                    !System.Text.RegularExpressions.Regex.IsMatch(request.id, @"^[a-z][a-z0-9-]{3,55}$") ||
                    Path.GetFileName(path) != request.id + ".json")
                    throw new InvalidOperationException("Invalid command identity");
                result.id = request.id;
                result.action = request.action;
                string output = Path.Combine(Results, request.id + ".json");
                if (File.Exists(output)) return; // durable, at-most-once response
                if (SceneManager.GetActiveScene().path != MapScene)
                    throw new InvalidOperationException("Authored map scene not loaded");
                switch (request.action)
                {
                    case "inspect": Inspect(request, result); break;
                    case "move": Modify(request, result, false); break;
                    case "scale": Modify(request, result, true); break;
                    case "move_tree": ModifyNativeTree(request, result, false); break;
                    case "scale_tree": ModifyNativeTree(request, result, true); break;
                    case "capture": Capture(request, result); break;
                    case "status": result.status = "ok"; break;
                    default: throw new InvalidOperationException("Unsupported Unity command");
                }
            }
            catch (Exception e) { result.status = "error"; result.error = e.Message; }
            finally
            {
                if (request != null && !string.IsNullOrEmpty(result.id) &&
                    System.Text.RegularExpressions.Regex.IsMatch(result.id, @"^[a-z][a-z0-9-]{3,55}$"))
                    AtomicWrite(Path.Combine(Results, result.id + ".json"), JsonUtility.ToJson(result, true));
                File.Delete(path);
            }
        }
        private static void Inspect(Request request, Response result)
        {
            if (!(request.radius > 0 && request.radius <= 200) || request.limit < 1 || request.limit > 80)
                throw new InvalidOperationException("Radius/limit exceeds safety bounds");
            GameObject go = string.IsNullOrEmpty(request.target) ? null : FindObject(request.target);
            if (!string.IsNullOrEmpty(request.target) && go == null)
                throw new InvalidOperationException("Unknown target");
            Vector3 center = go != null ? go.transform.position : request.cameraTarget;
            if (!Finite(center))
                throw new InvalidOperationException("Camera focus coordinates must be finite");
            // Keep the human-readable SceneView at the inspected world location.
            // Important: the old Inspect implementation only reported objects;
            // it never changed the viewport the phone's noVNC viewer sees.
            SceneView view = SceneView.lastActiveSceneView;
            if (view == null)
                throw new InvalidOperationException("No Unity Scene View available for camera focus");
            float focusSize = Mathf.Clamp(view.size, 9f, 28f);
            view.LookAtDirect(center, view.rotation, focusSize);
            view.Repaint();
            SaveSession(); // persist focus between viewer reconnects/restarts
            result.targetId = go != null ? Id(go) : null;
            result.position = center;
            if (go != null) result.scale = go.transform.localScale;
            var objs = new List<Item>();
            foreach (GameObject item in UnityEngine.Object.FindObjectsByType<GameObject>(
                         FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (!item.scene.IsValid() || item.scene.path != MapScene) continue;
                float d = Vector3.Distance(item.transform.position, center);
                if (d > request.radius) continue;
                Renderer renderer = item.GetComponent<Renderer>();
                Collider collider = item.GetComponent<Collider>();
                if (renderer == null && collider == null && item != go) continue;
                objs.Add(new Item
                {
                    id = Id(item), name = item.name, category = "scene_object",
                    position = item.transform.position, scale = item.transform.localScale,
                    rendererSize = renderer != null ? renderer.bounds.size : Vector3.zero,
                    material = renderer != null && renderer.sharedMaterial != null ?
                        renderer.sharedMaterial.name : null,
                    hasCollider = collider != null && collider.enabled, distance = d
                });
            }
            result.sceneObjectCount = objs.Count;
            result.nearbyObjects = objs.OrderBy(x => x.distance).Take(request.limit).ToArray();
            var nearbyTrees = new List<Item>();
            int treeTotal = 0;
            foreach (Terrain t in UnityEngine.Object.FindObjectsByType<Terrain>(
                         FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (t.gameObject.scene.path != MapScene || t.terrainData == null) continue;
                TreeInstance[] trees = t.terrainData.treeInstances;
                treeTotal += trees.Length;
                Vector3 origin = t.GetPosition(), size = t.terrainData.size;
                string terrainId = Id(t.gameObject);
                for (int i = 0; i < trees.Length; i++)
                {
                    Vector3 pos = origin + Vector3.Scale(trees[i].position, size);
                    float d = Vector3.Distance(pos, center);
                    if (d > request.radius) continue;
                    nearbyTrees.Add(new Item
                    {
                        id = "terrain-tree:" + terrainId + ":" + i.ToString(),
                        name = "TerrainTree_" + i, category = "native_terrain_tree",
                        position = pos,
                        scale = new Vector3(trees[i].widthScale, trees[i].heightScale, trees[i].widthScale),
                        distance = d, hasCollider = false,
                        sourceAsset = AssetDatabase.GetAssetPath(t.terrainData)
                    });
                }
            }
            result.terrainTreeCount = treeTotal;
            result.nearbyTerrainTrees = nearbyTrees.OrderBy(x => x.distance).Take(request.limit).ToArray();
            foreach (Terrain terrain in UnityEngine.Object.FindObjectsByType<Terrain>(
                         FindObjectsInactive.Include, FindObjectsSortMode.None))
            {
                if (terrain.terrainData == null || terrain.gameObject.scene.path != MapScene) continue;
                Vector3 o=terrain.GetPosition(), extent=terrain.terrainData.size;
                if (center.x < o.x || center.x > o.x+extent.x ||
                    center.z < o.z || center.z > o.z+extent.z) continue;
                float u=(center.x-o.x)/extent.x, v=(center.z-o.z)/extent.z;
                result.groundY=terrain.SampleHeight(center)+o.y;
                result.groundSlopeDegrees=terrain.terrainData.GetSteepness(u,v);
                result.groundNormal=terrain.terrainData.GetInterpolatedNormal(u,v);
                break;
            }
        }
        private static bool Finite(Vector3 p) =>
            !float.IsNaN(p.x) && !float.IsNaN(p.y) && !float.IsNaN(p.z) &&
            !float.IsInfinity(p.x) && !float.IsInfinity(p.y) && !float.IsInfinity(p.z);
        private static void Modify(Request request, Response result, bool scale)
        {
            if (string.IsNullOrEmpty(request.target)) throw new InvalidOperationException("Target required");
            GameObject go = FindObject(request.target);
            if (go == null) throw new InvalidOperationException("Target not found");
            if (PrefabUtility.IsPartOfPrefabAsset(go))
                throw new InvalidOperationException("Cannot edit prefab source via scene transform");
            if (scale)
            {
                if (!Finite(request.scale) || request.scale.x < .5f || request.scale.y < .5f ||
                    request.scale.z < .5f || request.scale.x > 2f || request.scale.y > 2f || request.scale.z > 2f)
                    throw new InvalidOperationException("Scale multiplier must be 0.5..2 on each axis");
            }
            else if (!Finite(request.delta) || request.delta.magnitude > 5)
                throw new InvalidOperationException("Move delta must be within 5 metres");
            Undo.RecordObject(go.transform, "Aaris live Unity map edit");
            if (scale) go.transform.localScale = Vector3.Scale(go.transform.localScale, request.scale);
            else go.transform.position += request.delta;
            PrefabUtility.RecordPrefabInstancePropertyModifications(go.transform);
            EditorUtility.SetDirty(go.transform);
            Scene scene=go.scene;
            EditorSceneManager.MarkSceneDirty(scene);
            if (!EditorSceneManager.SaveScene(scene))
                throw new IOException("Unity failed to save native .unity scene");
            AssetDatabase.SaveAssets();
            result.changedAsset = scene.path;
            result.targetId = Id(go);
            result.position = go.transform.position;
            result.scale = go.transform.localScale;
            SceneView.RepaintAll();
            SaveSession();
        }
        private static void ModifyNativeTree(Request request, Response result, bool isScale)
        {
            if (string.IsNullOrEmpty(request.target) || !request.target.StartsWith("terrain-tree:"))
                throw new InvalidOperationException("Use exact terrain-tree ID from inspect");
            int sep=request.target.LastIndexOf(':');
            if (sep < 0 || !int.TryParse(request.target.Substring(sep+1),out int index))
                throw new InvalidOperationException("Invalid tree index");
            string terrainId=request.target.Substring("terrain-tree:".Length,
                                                       sep-"terrain-tree:".Length);
            GameObject terrainObject=FindObject(terrainId);
            Terrain t=terrainObject != null ? terrainObject.GetComponent<Terrain>() : null;
            if (t == null || t.terrainData == null) throw new InvalidOperationException("Terrain not found");
            TreeInstance[] trees=t.terrainData.treeInstances;
            if (index < 0 || index >= trees.Length) throw new InvalidOperationException("Tree index changed");
            Vector3 size=t.terrainData.size, original=t.GetPosition()+Vector3.Scale(trees[index].position,size);
            if (!request.hasExpectedPosition || Vector3.Distance(original,request.expectedPosition) > .2f)
                throw new InvalidOperationException("Tree moved since inspection; inspect again");
            if (!isScale && (!Finite(request.delta) || Mathf.Abs(request.delta.x)>5 || Mathf.Abs(request.delta.z)>5 ||
                Mathf.Abs(request.delta.y)>0.001f))
                throw new InvalidOperationException("Tree horizontal move must be under 5m");
            Vector3 p=trees[index].position;
            if (isScale)
            {
                if (!Finite(request.scale) || request.scale.x < .5f || request.scale.x > 2f ||
                    request.scale.y < .5f || request.scale.y > 2f ||
                    Mathf.Abs(request.scale.z-1f) > .001f)
                    throw new InvalidOperationException("Tree scales: x=width and y=height multipliers 0.5..2; z=1");
                trees[index].widthScale *= request.scale.x;
                trees[index].heightScale *= request.scale.y;
            }
            else
            {
                p.x+=request.delta.x/size.x;
                p.z+=request.delta.z/size.z;
                if (p.x < 0 || p.x > 1 || p.z < 0 || p.z > 1)
                    throw new InvalidOperationException("Tree cannot leave terrain");
                trees[index].position=p;
            }
            TerrainData data=t.terrainData;
            Undo.RegisterCompleteObjectUndo(data,"Aaris move native terrain tree");
            data.SetTreeInstances(trees,true);
            EditorUtility.SetDirty(data);
            AssetDatabase.SaveAssets();
            t.Flush();
            result.changedAsset=AssetDatabase.GetAssetPath(data);
            result.targetId=request.target;
            result.position=t.GetPosition()+Vector3.Scale(p,size);
            result.scale=new Vector3(trees[index].widthScale,trees[index].heightScale,trees[index].widthScale);
            SceneView.RepaintAll();
        }
        private static void Capture(Request request, Response result)
        {
            if (!Finite(request.cameraPosition) || !Finite(request.cameraTarget) ||
                Vector3.Distance(request.cameraPosition, request.cameraTarget)<.5f)
                throw new InvalidOperationException("Camera position/target must be distinct and finite");
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                throw new InvalidOperationException("Unity Editor has no render graphics device");
            Directory.CreateDirectory(Frames);
            string path=Path.Combine(Frames,request.id+".jpg");
            var cameraObject = new GameObject("__AarisTemporarySceneCapture");
            RenderTexture render = null;
            Texture2D photo = null;
            RenderTexture before = RenderTexture.active;
            try
            {
                Camera camera=cameraObject.AddComponent<Camera>();
                camera.transform.position=request.cameraPosition;
                camera.transform.LookAt(request.cameraTarget);
                camera.fieldOfView=65f;
                camera.nearClipPlane=.1f;
                camera.farClipPlane=3000f;
                render=new RenderTexture(960,540,24,RenderTextureFormat.ARGB32);
                render.Create();
                camera.targetTexture=render;
                var req = new UniversalRenderPipeline.SingleCameraRequest { destination=render };
                if (!RenderPipeline.SupportsRenderRequest(camera,req))
                    throw new InvalidOperationException("URP SingleCameraRequest unsupported");
                RenderPipeline.SubmitRenderRequest(camera,req);
                RenderTexture.active=render;
                photo=new Texture2D(960,540,TextureFormat.RGB24,false);
                photo.ReadPixels(new Rect(0,0,960,540),0,0);
                photo.Apply();
                File.WriteAllBytes(path,photo.EncodeToJPG(67));
                result.screenshotPath=path;
            }
            finally
            {
                RenderTexture.active=before;
                if(photo!=null) UnityEngine.Object.DestroyImmediate(photo);
                if(render!=null) {render.Release();UnityEngine.Object.DestroyImmediate(render);}
                UnityEngine.Object.DestroyImmediate(cameraObject);
            }
        }
        private static void DeleteExpiredFrames()
        {
            if (!Directory.Exists(Frames)) return;
            foreach (string file in Directory.GetFiles(Frames,"*.jpg"))
            {
                if (DateTime.UtcNow-File.GetLastWriteTimeUtc(file)>TimeSpan.FromMinutes(30))
                    File.Delete(file);
            }
        }
    }
}
#endif
