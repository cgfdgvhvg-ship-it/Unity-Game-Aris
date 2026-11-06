using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

namespace Aaris.MapReview.Editor
{
    // Called by Actions via -executeMethod Aaris.MapReview.Editor.AarisCICapture.Capture.
    // Optional -aarisCaptureIntent=all|houses|roads|tiles|sky.
    public static class AarisCICapture
    {
        [Serializable] private sealed class CaptureManifest
        {
            public string utc;
            public string unityVersion;
            public string graphicsDevice;
            public string intent;
            public string[] files;
        }
        private struct Shot
        {
            public string name, group;
            public float x, z;
            public Vector3 offset, aim;
            public Shot(string n, string g, float px, float pz, Vector3 off, Vector3 target)
            { name = n; group = g; x = px; z = pz; offset = off; aim = target; }
        }

        [MenuItem("Aaris/CI/Capture map photographs")]
        public static void Capture()
        {
            string intent = "all";
            foreach (string arg in Environment.GetCommandLineArgs())
                if (arg.StartsWith("-aarisCaptureIntent=", StringComparison.Ordinal))
                    intent = arg.Substring("-aarisCaptureIntent=".Length).ToLowerInvariant();
            if (!new[] { "all", "houses", "roads", "tiles", "sky" }.Contains(intent))
                throw new ArgumentException("Unsupported intent: " + intent);
            string directory = Path.Combine(Directory.GetCurrentDirectory(), "ci-photos");
            Directory.CreateDirectory(directory);
            EditorSceneManager.OpenScene(AarisExplorerBuild.ScenePath, OpenSceneMode.Single);
            Terrain[] terrains = UnityEngine.Object.FindObjectsByType<Terrain>(FindObjectsSortMode.None);
            if (terrains.Length != 4 || terrains.Any(t => t.terrainData == null))
                throw new InvalidOperationException("Four native TerrainData tiles required; check LFS.");
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                throw new InvalidOperationException("Null graphics device: do not pass -nographics.");
            if (RenderSettings.skybox == null || RenderSettings.sun == null)
                throw new InvalidOperationException("Scene skybox or sun is missing.");
            var shots = new[]
            {
                new Shot("house_valley", "houses", -420,-210, new Vector3(13,7,-30), new Vector3(0,5,0)),
                new Shot("house_village", "houses", -530,-590, new Vector3(-26,8,-24), new Vector3(0,5,0)),
                new Shot("house_clocktower", "houses", 350,220, new Vector3(25,12,-36), new Vector3(0,10,0)),
                new Shot("house_coastal", "houses", 650,650, new Vector3(22,9,-30), new Vector3(0,6,0)),
                new Shot("house_lakeside", "houses", -720,65, new Vector3(22,8,-25), new Vector3(0,5,0)),
                new Shot("road_valley", "roads", -447,-327, new Vector3(0,3,-10), new Vector3(0,3,35)),
                new Shot("road_clocktower", "roads", 320,93, new Vector3(0,3,-10), new Vector3(0,3,35)),
                new Shot("road_north", "roads", 271,533, new Vector3(0,4,-12), new Vector3(0,3,38)),
                new Shot("tile_southwest", "tiles", -500,-500, new Vector3(0,440,0), Vector3.zero),
                new Shot("tile_southeast", "tiles", 500,-500, new Vector3(0,440,0), Vector3.zero),
                new Shot("tile_northwest", "tiles", -500,500, new Vector3(0,440,0), Vector3.zero),
                new Shot("tile_northeast", "tiles", 500,500, new Vector3(0,440,0), Vector3.zero),
                new Shot("daylight_sky", "sky", -420,-210, new Vector3(0,3,0), new Vector3(20,100,50))
            };
            var go = new GameObject("__Aaris_CI_ScreenshotCamera");
            go.hideFlags = HideFlags.HideAndDontSave;
            Camera cam = go.AddComponent<Camera>();
            cam.enabled = false;
            cam.clearFlags = CameraClearFlags.Skybox;
            cam.fieldOfView = 65f;
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 5500f;
            cam.allowHDR = true;
            var written = new List<string>();
            try
            {
                foreach (Shot shot in shots)
                {
                    if (intent != "all" && shot.group != intent) continue;
                    float elevation = Ground(terrains, shot.x, shot.z);
                    Vector3 center = new Vector3(shot.x, elevation + 1.8f, shot.z);
                    cam.transform.position = center + shot.offset;
                    cam.transform.LookAt(center + shot.aim, Vector3.up);
                    string name = shot.name + ".png";
                    WritePng(cam, Path.Combine(directory, name));
                    written.Add(name);
                    Debug.Log("[Aaris Capture] " + name + " camera=" + cam.transform.position);
                }
                if (written.Count == 0) throw new InvalidOperationException("Empty camera selection.");
                File.WriteAllText(Path.Combine(directory, "capture-manifest.json"),
                    JsonUtility.ToJson(new CaptureManifest {
                        utc = DateTime.UtcNow.ToString("O"),
                        unityVersion = Application.unityVersion,
                        graphicsDevice = SystemInfo.graphicsDeviceType.ToString(),
                        intent = intent, files = written.ToArray() }, true));
                Debug.Log("[Aaris Capture] Wrote " + written.Count + " genuine Unity PNGs.");
            }
            finally { UnityEngine.Object.DestroyImmediate(go); }
        }

        private static float Ground(Terrain[] terrains, float x, float z)
        {
            foreach (Terrain t in terrains)
            {
                Vector3 origin = t.transform.position;
                Vector3 size = t.terrainData.size;
                if (x >= origin.x && x <= origin.x + size.x &&
                    z >= origin.z && z <= origin.z + size.z)
                    return t.SampleHeight(new Vector3(x,0f,z)) + origin.y;
            }
            throw new InvalidOperationException("No TerrainData at (" + x + "," + z + ")");
        }

        private static void WritePng(Camera cam, string destination)
        {
            const int width = 1920, height = 1080;
            RenderTexture target = RenderTexture.GetTemporary(width,height,24,RenderTextureFormat.ARGB32);
            RenderTexture previous = RenderTexture.active;
            var texture = new Texture2D(width,height,TextureFormat.RGB24,false);
            try
            {
                cam.targetTexture = target;
                cam.Render();
                RenderTexture.active = target;
                texture.ReadPixels(new Rect(0,0,width,height),0,0,false);
                texture.Apply(false);
                byte[] png = texture.EncodeToPNG();
                if (png.Length < 8192) throw new InvalidOperationException("Suspiciously tiny PNG: " + destination);
                File.WriteAllBytes(destination,png);
            }
            finally
            {
                cam.targetTexture = null;
                RenderTexture.active = previous;
                UnityEngine.Object.DestroyImmediate(texture);
                RenderTexture.ReleaseTemporary(target);
            }
        }
    }
}
