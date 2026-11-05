#if UNITY_EDITOR
// Read-only real Unity in-scene building measurement + JPG survey.
// Scratch-only bridge; never copies files to original project, commits or saves scene.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace Aaris.WorldAutomation
{
    [InitializeOnLoad]
    public static class AarisHousePhotoSurvey
    {
        private const string ScenePath = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity";
        private const string Control = "/tmp/aaris-unity-batch/control";
        private static double next;
        [Serializable] public sealed class Request { public string id; }
        [Serializable] public sealed class HouseRecord
        {
            public string name, unityObjectId, prefabPath;
            public Vector3 center, origin, forward, right;
            public float widthXMetres, heightMetres, lengthZMetres, bottomY, topY;
            public int renderers, colliders;
        }
        [Serializable] public sealed class Picture
        {
            public string file, houseName, view, sha256;
            public Vector3 cameraPosition, cameraTarget;
            public int bytes;
        }
        [Serializable] public sealed class Report
        {
            public string id, status, error, scene, unityVersion;
            public int candidatesFound, picturesMade;
            public HouseRecord[] houses;
            public Picture[] photos;
        }
        private sealed class Candidate
        {
            public GameObject go;
            public Bounds b;
            public int renderers, colliders;
            public string prefab;
            public string id;
        }
        static AarisHousePhotoSurvey() { EditorApplication.update -= Tick; EditorApplication.update += Tick; }
        private static void Tick()
        {
            if (EditorApplication.timeSinceStartup < next) return;
            next = EditorApplication.timeSinceStartup + 1.4;
            if (EditorApplication.isCompiling || EditorApplication.isUpdating ||
                EditorApplication.isPlayingOrWillChangePlaymode) return;
            var dir = Control + "/house-requests";
            if (!Directory.Exists(dir)) return;
            foreach (string path in Directory.GetFiles(dir, "*.json").OrderBy(x => x).Take(1))
                Process(path);
        }
        private static bool HouseTerm(string name)
        {
            if (string.IsNullOrEmpty(name)) return false;
            string s = name.ToLowerInvariant().Replace(" ","_");
            return s.Contains("house") || s.Contains("cottage") ||
                   s.Contains("cabin") || s.Contains("bungalow") ||
                   s.Contains("townhouse") || s.Contains("hanok") ||
                   s.Contains("residential") || s.Contains("home_");
        }
        private static List<Candidate> Discover()
        {
            var all = UnityEngine.Object.FindObjectsByType<GameObject>(
                FindObjectsInactive.Include, FindObjectsSortMode.None);
            var candidates = new List<Candidate>();
            var seen = new HashSet<int>();
            foreach (var go in all)
            {
                if (go == null || !go.scene.IsValid() || go.scene.path != ScenePath ||
                    !HouseTerm(go.name) || !seen.Add(go.GetInstanceID())) continue;
                // Candidate is an actual scene object, never an unused prefab asset.
                var renderers = go.GetComponentsInChildren<Renderer>(true)
                    .Where(x => x != null && x.enabled && x is MeshRenderer)
                    .ToArray();
                if (renderers.Length == 0) continue;
                bool started = false; Bounds bounds = new Bounds();
                foreach (var rend in renderers)
                {
                    if (!started) { bounds=rend.bounds; started=true; }
                    else bounds.Encapsulate(rend.bounds);
                }
                if (!started || bounds.size.y < 1.7f || bounds.size.y > 70 ||
                    bounds.size.x < 2 || bounds.size.x > 145 ||
                    bounds.size.z < 2 || bounds.size.z > 145) continue;
                string src="";
                var source = PrefabUtility.GetCorrespondingObjectFromSource(go);
                if (source != null) src=AssetDatabase.GetAssetPath(source);
                candidates.Add(new Candidate {
                    go=go,b=bounds,renderers=renderers.Length,
                    colliders=go.GetComponentsInChildren<Collider>(true).Length,
                    prefab=src,
                    id=GlobalObjectId.GetGlobalObjectIdSlow(go).ToString()
                });
            }
            // Deduplicate nested building labels; prefer top-level models with
            // meaningful bounds, then prefer a variety of real source buildings.
            candidates=candidates.OrderByDescending(c=>c.b.size.x*c.b.size.y*c.b.size.z).ToList();
            var unique = new List<Candidate>();
            foreach (var c in candidates)
                if (!unique.Any(u => c.go.transform.IsChildOf(u.go.transform) ||
                                     u.go.transform.IsChildOf(c.go.transform)))
                    unique.Add(c);
            return unique;
        }
        private static string Hash(byte[] b)
        {
            using(var sha=SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(b)).Replace("-","").ToLowerInvariant();
        }
        private static void Process(string path)
        {
            var id=Path.GetFileNameWithoutExtension(path);
            var report=new Report{id=id,status="error",scene=ScenePath,unityVersion=Application.unityVersion};
            var results=Control+"/house-results";
            var photosRoot=Control+"/house-photos/"+id;
            var infoPath=results+"/"+id+".json";
            Directory.CreateDirectory(results);
            try
            {
                if (!System.Text.RegularExpressions.Regex.IsMatch(id,@"^[a-z][a-z0-9-]{3,55}$") ||
                    File.Exists(infoPath) || Directory.Exists(photosRoot))
                    throw new InvalidOperationException("Job ID, results or photo folder already exist");
                if (SceneManager.GetActiveScene().path != ScenePath ||
                    SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                    throw new InvalidOperationException("Real scene or graphics backend unavailable");
                var candidates=Discover();
                report.candidatesFound=candidates.Count;
                if (candidates.Count==0)
                    throw new InvalidOperationException("No renderer-backed real residential scene objects found");
                // Prefer variety of building model names, with enough separation
                // to avoid accidentally photographing the same building repeatedly.
                var chosen=new List<Candidate>();
                var usedNames=new HashSet<string>();
                foreach(var c in candidates.OrderBy(c=>c.go.name).ThenBy(c=>c.b.center.x))
                {
                    string group=c.go.name.ToLowerInvariant().Split('(')[0];
                    if (usedNames.Contains(group) && candidates.Count>3) continue;
                    if (chosen.Any(x => Vector3.Distance(x.b.center,c.b.center)<20)) continue;
                    chosen.Add(c);
                    usedNames.Add(group);
                    if (chosen.Count==3) break;
                }
                if(chosen.Count<2)
                    foreach(var c in candidates)
                    {
                        if(chosen.Contains(c)) continue;
                        if(chosen.Any(x=>Vector3.Distance(x.b.center,c.b.center)<15)) continue;
                        chosen.Add(c);
                        if(chosen.Count==3) break;
                    }
                if(chosen.Count==0) throw new InvalidOperationException("No separated actual house models");
                var houses=new List<HouseRecord>();
                var pictures=new List<Picture>();
                Directory.CreateDirectory(photosRoot);
                foreach(var c in chosen)
                {
                    houses.Add(new HouseRecord {
                        name=c.go.name,unityObjectId=c.id,prefabPath=c.prefab,
                        center=c.b.center, origin=c.go.transform.position,
                        forward=c.go.transform.forward,right=c.go.transform.right,
                        widthXMetres=c.b.size.x,heightMetres=c.b.size.y,
                        lengthZMetres=c.b.size.z,bottomY=c.b.min.y,topY=c.b.max.y,
                        renderers=c.renderers,colliders=c.colliders
                    });
                }
                RenderTexture old=RenderTexture.active;
                GameObject cameraObject=null;
                RenderTexture rt=null;
                Texture2D tex=null;
                try
                {
                    cameraObject=new GameObject("__AarisReadOnlyHouseSurveyCamera");
                    cameraObject.hideFlags=HideFlags.HideAndDontSave;
                    var cam=cameraObject.AddComponent<Camera>();
                    cam.enabled=false;
                    cam.fieldOfView=69;
                    cam.nearClipPlane=.09f;
                    cam.farClipPlane=2200;
                    cam.clearFlags=CameraClearFlags.Skybox;
                    rt=new RenderTexture(960,540,24,RenderTextureFormat.ARGB32);
                    if(!rt.Create())throw new InvalidOperationException("Render target allocation failed");
                    cam.targetTexture=rt;
                    tex=new Texture2D(960,540,TextureFormat.RGB24,false);
                    var req=new UniversalRenderPipeline.SingleCameraRequest{destination=rt};
                    if(!RenderPipeline.SupportsRenderRequest(cam,req))
                        throw new InvalidOperationException("Unity URP SingleCameraRequest unsupported");
                    int index=0;
                    foreach(var c in chosen)
                    {
                        var b=c.b;
                        Vector3 center=b.center;
                        float h=b.size.y;
                        float d=Mathf.Max(9f,Mathf.Max(b.size.x,b.size.z)*1.65f);
                        Vector3 forward=c.go.transform.forward;
                        Vector3 right=c.go.transform.right;
                        forward.y=0;right.y=0;
                        if(forward.sqrMagnitude<.4f)forward=Vector3.forward;
                        if(right.sqrMagnitude<.4f)right=Vector3.right;
                        forward.Normalize();right.Normalize();
                        var aim=new Vector3(center.x,b.min.y+h*.55f,center.z);
                        var views=new []{
                            new {name="front", from=aim-forward*d+Vector3.up*Mathf.Max(1f,h*.12f), to=aim},
                            new {name="left-side", from=aim-right*d+Vector3.up*Mathf.Max(1f,h*.1f),to=aim},
                            new {name="rear", from=aim+forward*d+Vector3.up*Mathf.Max(1f,h*.1f),to=aim},
                            new {name="top-roof",from=center+Vector3.up*Mathf.Max(14f,h*2.3f)-forward*(d*.35f),to=center},
                            // Camera is genuinely inside the exterior renderer's
                            // world AABB; not proof of navigable/furnished interior.
                            new {name="inside-volume",from=new Vector3(center.x,b.min.y+h*.37f,center.z),
                                to=new Vector3(center.x,b.min.y+h*.37f,center.z)+forward*Mathf.Max(2f,b.extents.z*.55f)}
                        };
                        foreach(var view in views)
                        {
                            if ((view.to-view.from).sqrMagnitude < .3f)
                                throw new InvalidOperationException("Invalid interior camera");
                            index++;
                            string file=index.ToString("00")+"-house-"+(houses.Count>0?(chosen.IndexOf(c)+1):1)+"-"+view.name+".jpg";
                            string output=photosRoot+"/"+file;
                            if(File.Exists(output))throw new InvalidOperationException("Photo filename reused");
                            cam.transform.position=view.from;
                            cam.transform.LookAt(view.to,Vector3.up);
                            RenderPipeline.SubmitRenderRequest(cam,req);
                            RenderTexture.active=rt;
                            tex.ReadPixels(new Rect(0,0,960,540),0,0);
                            tex.Apply(false);
                            byte[] bytes=tex.EncodeToJPG(78);
                            if(bytes.Length<6000 || bytes.Length>2500000)
                                throw new InvalidOperationException("Unexpected JPG size for "+file);
                            File.WriteAllBytes(output,bytes);
                            pictures.Add(new Picture{file=file,houseName=c.go.name,
                                view=view.name, cameraPosition=view.from,
                                cameraTarget=view.to,bytes=bytes.Length,sha256=Hash(bytes)});
                        }
                    }
                }
                finally
                {
                    RenderTexture.active=old;
                    if(tex!=null)UnityEngine.Object.DestroyImmediate(tex);
                    if(rt!=null){rt.Release();UnityEngine.Object.DestroyImmediate(rt);}
                    if(cameraObject!=null)UnityEngine.Object.DestroyImmediate(cameraObject);
                }
                report.houses=houses.ToArray();
                report.photos=pictures.ToArray();
                report.picturesMade=pictures.Count;
                if(pictures.Count<10)
                    throw new InvalidOperationException("Less than ten distinct Unity-rendered photos");
                report.status="ok";
            }
            catch(Exception ex)
            {
                report.error=ex.GetType().Name+": "+ex.Message;
                Debug.LogError("AARIS_HOUSE_SURVEY_FAILED "+report.error);
            }
            finally
            {
                File.WriteAllText(infoPath,JsonUtility.ToJson(report,true));
                try { File.Delete(path); } catch(Exception) {}
                Debug.Log("AARIS_HOUSE_SURVEY_COMPLETE "+id+" "+report.status+
                          " pictures="+report.picturesMade);
            }
        }
    }
}
#endif
