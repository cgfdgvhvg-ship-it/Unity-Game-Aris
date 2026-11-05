#if UNITY_EDITOR
// Real Unity camera screenshot, editor-only in scratch; no game code changes.
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace Aaris.WorldAutomation
{
    public static class AarisMapCameraOneShot
    {
        [Serializable] public sealed class ShotResult
        {
            public string id, status, error, scene, zone, imagePath, jpegSha256, unityVersion;
            public int terrainComponents, terrainInstances, jpegBytes;
            public float brightnessRange;
        }
        private const string Scene = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity";
        private const string Control = "/tmp/aaris-unity-batch/control";
        private static string Hash(byte[] bytes)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }
        public static void Execute()
        {
            var id = Environment.GetEnvironmentVariable("AARIS_SHOT_ID") ?? "";
            var zone = Environment.GetEnvironmentVariable("AARIS_SHOT_ZONE") ?? "";
            var result = new ShotResult { id=id, zone=zone, status="error",
                unityVersion=Application.unityVersion, scene=Scene };
            int exit=3;
            GameObject temporary = null;
            RenderTexture render = null;
            Texture2D pixels = null;
            RenderTexture old = RenderTexture.active;
            try
            {
                if (!Regex.IsMatch(id, @"^[a-z][a-z0-9-]{3,55}$"))
                    throw new InvalidOperationException("Invalid shot ID");
                Vector3 from, target;
                switch (zone)
                {
                    case "forest-west":
                        from = new Vector3(-430,28,180);
                        target = new Vector3(-355,-18,275);
                        break;
                    case "forest-south":
                        from = new Vector3(-725,83,-345);
                        target = new Vector3(-650,12,-265);
                        break;
                    case "mountain-east":
                        from = new Vector3(440,105,-875);
                        target = new Vector3(500,39,-750);
                        break;
                    default: throw new InvalidOperationException("Unknown mapped camera zone");
                }
                if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                    throw new InvalidOperationException("No GPU graphics device for authentic screenshot");
                Scene current = EditorSceneManager.OpenScene(Scene,OpenSceneMode.Single);
                if (!current.IsValid() || !current.isLoaded)
                    throw new InvalidOperationException("Actual Unity map scene not loaded");
                var terrains = UnityEngine.Object.FindObjectsByType<Terrain>(
                    FindObjectsInactive.Include, FindObjectsSortMode.None);
                int trees=0;
                foreach(var terrain in terrains)
                    if(terrain.terrainData!=null && terrain.gameObject.scene.path==Scene)
                    {
                        result.terrainComponents++;
                        trees += terrain.terrainData.treeInstanceCount;
                    }
                result.terrainInstances=trees;
                if (result.terrainComponents!=4 || trees!=7508)
                    throw new InvalidOperationException("Native map terrain inventory changed");
                temporary = new GameObject("__AarisTemporaryReadOnlyCamera");
                var cam=temporary.AddComponent<Camera>();
                cam.transform.position=from;
                cam.transform.LookAt(target);
                cam.fieldOfView=62f;
                cam.nearClipPlane=0.3f;
                cam.farClipPlane=2300f;
                cam.clearFlags=CameraClearFlags.Skybox;
                render=new RenderTexture(960,540,24,RenderTextureFormat.ARGB32);
                if (!render.Create()) throw new InvalidOperationException("Render texture allocation failed");
                cam.targetTexture=render;
                var req=new UniversalRenderPipeline.SingleCameraRequest { destination=render };
                if (!RenderPipeline.SupportsRenderRequest(cam,req))
                    throw new InvalidOperationException("URP SingleCameraRequest unsupported");
                RenderPipeline.SubmitRenderRequest(cam,req);
                RenderTexture.active=render;
                pixels=new Texture2D(960,540,TextureFormat.RGB24,false);
                pixels.ReadPixels(new Rect(0,0,960,540),0,0);
                pixels.Apply();
                var colors=pixels.GetPixels32();
                float min=1f,max=0f;
                for(int i=0;i<colors.Length;i+=211)
                {
                    var c=colors[i];
                    float v=(c.r*0.2126f+c.g*0.7152f+c.b*0.0722f)/255f;
                    min=Mathf.Min(min,v);max=Mathf.Max(max,v);
                }
                result.brightnessRange=max-min;
                if(result.brightnessRange < .02f)
                    throw new InvalidOperationException("Rendered scene appears blank");
                var bytes=pixels.EncodeToJPG(78);
                if(bytes.Length<8000 || bytes.Length>1800000)
                    throw new InvalidOperationException("Screenshot size outside expected range");
                Directory.CreateDirectory(Control+"/frames");
                var photoPath=Control+"/frames/"+id+".jpg";
                if(File.Exists(photoPath)) throw new InvalidOperationException("Frame already exists");
                File.WriteAllBytes(photoPath,bytes);
                result.imagePath=photoPath;
                result.jpegBytes=bytes.Length;
                result.jpegSha256=Hash(bytes);
                result.status="ok";
                exit=0;
                Debug.Log("AARIS_REAL_UNITY_CAMERA_CAPTURED "+zone+" bytes="+bytes.Length);
            }
            catch(Exception error)
            {
                result.error=error.GetType().Name+": "+error.Message;
                Debug.LogError("AARIS_UNITY_CAPTURE_FAILED "+result.error);
            }
            finally
            {
                RenderTexture.active=old;
                if(pixels!=null) UnityEngine.Object.DestroyImmediate(pixels);
                if(render!=null){render.Release();UnityEngine.Object.DestroyImmediate(render);}
                if(temporary!=null) UnityEngine.Object.DestroyImmediate(temporary);
                try
                {
                    if(Regex.IsMatch(id,@"^[a-z][a-z0-9-]{3,55}$"))
                    {
                        Directory.CreateDirectory(Control+"/unity-results");
                        var path=Control+"/unity-results/"+id+".json";
                        if(File.Exists(path))throw new InvalidOperationException("Result already exists");
                        File.WriteAllText(path,JsonUtility.ToJson(result,true));
                    }
                }
                catch(Exception error)
                {
                    Debug.LogError("AARIS_UNITY_CAPTURE_RESULT_FAILED "+error.Message);
                    exit=4;
                }
                EditorApplication.Exit(exit);
            }
        }
    }
}
#endif
