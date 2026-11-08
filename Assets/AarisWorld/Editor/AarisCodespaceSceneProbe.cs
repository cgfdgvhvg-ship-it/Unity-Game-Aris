using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace Aaris.MapReview.Editor
{
    // Independent of noVNC/scrot: the actual licensed Unity Editor opens the
    // checked-in LFS scene, renders pixels, and exercises Play Mode.
    // Invoked ONLY by the bounded Codespace controller.
    [InitializeOnLoad]
    public static class AarisCodespaceSceneProbe
    {
        private const string Scene = AarisExplorerBuild.ScenePath;
        private const string Output = "/tmp/aaris-codespaces/scene-probe";
        private const string State = "aaris.codespace.probe.state";
        private const string Deadline = "aaris.codespace.probe.deadline";
        private const string Errors = "aaris.codespace.probe.errors";
        private const string Began = "aaris.codespace.probe.began";
        private const string ExitCode = "aaris.codespace.probe.exit";
        private const int PlayFrames = 60;

        [Serializable]
        private sealed class Result
        {
            public string mode;
            public string status;
            public string scene;
            public string unityVersion;
            public string graphicsDevice;
            public string reason;
            public int terrainTiles;
            public int frames;
            public int runtimeErrors;
            public bool playerPresent;
            public bool cameraPresent;
            public bool vehicleManagerPresent;
            public float pixelStandardDeviation;
        }

        static AarisCodespaceSceneProbe()
        {
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            Application.logMessageReceived -= OnLog;
            Application.logMessageReceived += OnLog;
        }

        private static void OnLog(string message, string trace, LogType type)
        {
            if (SessionState.GetString(State, "") != "running") return;
            if (type == LogType.Exception || type == LogType.Error || type == LogType.Assert)
                SessionState.SetInt(Errors, Math.Min(10000, SessionState.GetInt(Errors, 0) + 1));
        }

        private static Terrain[] LoadNativeScene()
        {
            if (!File.Exists(Scene)) throw new InvalidOperationException("SCENE_FILE_MISSING");
            using (var input = File.OpenRead(Scene))
            {
                byte[] first = new byte[Math.Min(100, (int)Math.Min(100, input.Length))];
                input.Read(first, 0, first.Length);
                if (System.Text.Encoding.ASCII.GetString(first).StartsWith(
                    "version https://git-lfs.github.com/spec/v1", StringComparison.Ordinal))
                    throw new InvalidOperationException("SCENE_IS_LFS_POINTER");
            }
            var loaded = EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single);
            if (!loaded.IsValid() || !loaded.isLoaded || loaded.path != Scene)
                throw new InvalidOperationException("NATIVE_SCENE_NOT_LOADED");
            var terrains = UnityEngine.Object.FindObjectsByType<Terrain>(FindObjectsSortMode.None);
            if (terrains.Length != 4 || terrains.Any(t => t.terrainData == null))
                throw new InvalidOperationException("FOUR_NATIVE_TERRAINS_REQUIRED");
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                throw new InvalidOperationException("NO_GRAPHICS_DEVICE");
            return terrains;
        }

        private static void Save(Result report, string name)
        {
            Directory.CreateDirectory(Output);
            File.WriteAllText(Path.Combine(Output, name), JsonUtility.ToJson(report, true));
        }

        // Returns an actual GPU/URP camera readback, not an Xvfb desktop picture.
        private static float Render(Camera cam, int width, int height, string file)
        {
            RenderTexture old = RenderTexture.active;
            RenderTexture rt = RenderTexture.GetTemporary(width, height, 24, RenderTextureFormat.ARGB32);
            Texture2D image = new Texture2D(width, height, TextureFormat.RGB24, false);
            RenderTexture oldTarget = cam.targetTexture;
            try
            {
                cam.targetTexture = rt;
                cam.Render();
                RenderTexture.active = rt;
                image.ReadPixels(new Rect(0, 0, width, height), 0, 0, false);
                image.Apply(false);
                Color32[] pixels = image.GetPixels32();
                double sum = 0, sq = 0;
                int magenta = 0, count = 0;
                int step = Math.Max(1, pixels.Length / 6000);
                for (int i = 0; i < pixels.Length; i += step)
                {
                    Color32 p = pixels[i];
                    float y = (p.r * 0.2126f + p.g * 0.7152f + p.b * 0.0722f);
                    sum += y;
                    sq += y * y;
                    if (p.r > 195 && p.g < 95 && p.b > 195) magenta++;
                    count++;
                }
                float deviation = (float)Math.Sqrt(Math.Max(0, sq / count - (sum / count) * (sum / count)));
                if (deviation < 6f) throw new InvalidOperationException("FRAME_NEARLY_UNIFORM");
                if (magenta * 4 > count * 3) throw new InvalidOperationException("FRAME_MAGENTA_SHADER_FAILURE");
                byte[] png = image.EncodeToPNG();
                if (png.Length < 8192) throw new InvalidOperationException("FRAME_SUSPICIOUSLY_SMALL");
                File.WriteAllBytes(file, png);
                return deviation;
            }
            finally
            {
                cam.targetTexture = oldTarget;
                RenderTexture.active = old;
                UnityEngine.Object.DestroyImmediate(image);
                RenderTexture.ReleaseTemporary(rt);
            }
        }

        [MenuItem("Aaris/CI/Native 2km overhead screenshot")]
        public static void Capture()
        {
            Directory.CreateDirectory(Output);
            Result report = new Result {
                mode = "render", status = "failed", scene = Scene,
                unityVersion = Application.unityVersion,
                graphicsDevice = SystemInfo.graphicsDeviceType.ToString()
            };
            GameObject go = null;
            try
            {
                var terrains = LoadNativeScene();
                report.terrainTiles = terrains.Length;
                if (RenderSettings.sun == null || RenderSettings.skybox == null)
                    throw new InvalidOperationException("SCENE_LIGHTING_MISSING");
                go = new GameObject("__Aaris_Transient_Overhead_Camera");
                go.hideFlags = HideFlags.HideAndDontSave;
                var cam = go.AddComponent<Camera>();
                cam.enabled = false;
                cam.orthographic = true;
                cam.orthographicSize = 1120f; // full 2000m vertical world plus 120m margin
                cam.nearClipPlane = 0.1f;
                cam.farClipPlane = 4000f;
                cam.clearFlags = CameraClearFlags.Skybox;
                cam.transform.position = new Vector3(0f, 1600f, 0f);
                cam.transform.rotation = Quaternion.Euler(90f, 0f, 0f);
                report.pixelStandardDeviation = Render(cam, 1600, 1600,
                    Path.Combine(Output, "map-overview.png"));
                report.status = "passed";
                report.reason = "REAL_UNITY_CAMERA_RENDER";
                Debug.Log("AARIS_NATIVE_SCENE_CAPTURE_PASSED");
            }
            catch (Exception e)
            {
                report.reason = e is InvalidOperationException ? e.Message : e.GetType().Name;
                Debug.LogError("AARIS_NATIVE_SCENE_CAPTURE_FAILED:" + report.reason);
                throw;
            }
            finally
            {
                if (go != null) UnityEngine.Object.DestroyImmediate(go);
                Save(report, "render-report.json");
            }
        }

        [MenuItem("Aaris/CI/Native Play Mode smoke test")]
        public static void Play()
        {
            Directory.CreateDirectory(Output);
            SessionState.SetString(State, "");
            SessionState.SetInt(Errors, 0);
            try
            {
                var terrains = LoadNativeScene();
                if (terrains.Length != 4 ||
                    UnityEngine.Object.FindFirstObjectByType<AarisThirdPersonPlayer>() == null ||
                    Camera.main == null)
                    throw new InvalidOperationException("PLAY_PREFLIGHT_FAILED");
                if (EditorApplication.isPlayingOrWillChangePlaymode)
                    throw new InvalidOperationException("EDITOR_ALREADY_PLAYING");
                SessionState.SetFloat(Deadline, (float)(EditorApplication.timeSinceStartup + 240));
                SessionState.SetFloat(Began, 0f);
                SessionState.SetString(State, "starting");
                EditorApplication.isPlaying = true;
                Debug.Log("AARIS_NATIVE_PLAY_REQUESTED");
            }
            catch (Exception e)
            {
                Save(new Result { mode = "play", status = "failed", scene = Scene,
                    reason = e is InvalidOperationException ? e.Message : e.GetType().Name },
                    "play-report.json");
                EditorApplication.Exit(1);
            }
        }

        private static void Tick()
        {
            string state = SessionState.GetString(State, "");
            if (state != "starting" && state != "running" && state != "stopping") return;
            if (state == "stopping")
            {
                if (!EditorApplication.isPlayingOrWillChangePlaymode)
                {
                    int exit = SessionState.GetInt(ExitCode, 1);
                    SessionState.SetString(State, "");
                    EditorApplication.Exit(exit);
                }
                return;
            }
            if (EditorApplication.timeSinceStartup > SessionState.GetFloat(Deadline, 0))
            {
                Finish(false, "PLAY_MODE_TIMED_OUT");
                return;
            }
            if (!EditorApplication.isPlaying) return;
            if (state == "starting")
            {
                SessionState.SetString(State, "running");
                SessionState.SetFloat(Began, (float)EditorApplication.timeSinceStartup);
                return;
            }
            if (Time.frameCount < PlayFrames ||
                EditorApplication.timeSinceStartup - SessionState.GetFloat(Began, 0) < 3)
                return;
            try
            {
                var terrains = UnityEngine.Object.FindObjectsByType<Terrain>(FindObjectsSortMode.None);
                var player = UnityEngine.Object.FindFirstObjectByType<AarisThirdPersonPlayer>();
                var manager = UnityEngine.Object.FindFirstObjectByType<AarisVehicleWorld>();
                Camera camera = Camera.main;
                bool sceneCorrect = SceneManager.GetActiveScene().path == Scene;
                var report = new Result {
                    mode = "play", status = "failed", scene = Scene,
                    unityVersion = Application.unityVersion,
                    graphicsDevice = SystemInfo.graphicsDeviceType.ToString(),
                    frames = Time.frameCount, terrainTiles = terrains.Length,
                    runtimeErrors = SessionState.GetInt(Errors, 0),
                    playerPresent = player != null,
                    cameraPresent = camera != null,
                    vehicleManagerPresent = manager != null
                };
                bool valid = sceneCorrect && terrains.Length == 4 && player != null &&
                    camera != null && manager != null && report.runtimeErrors == 0;
                if (valid)
                    report.pixelStandardDeviation = Render(camera, 1280, 720,
                        Path.Combine(Output, "play-frame.png"));
                report.status = valid ? "passed" : "failed";
                report.reason = valid ? "PLAY_MODE_SCENE_AND_CAMERA_VERIFIED" :
                    "PLAY_RUNTIME_ASSERTIONS_FAILED";
                Save(report, "play-report.json");
                Finish(valid, report.reason, false);
            }
            catch (Exception e)
            {
                Finish(false, e is InvalidOperationException ? e.Message : e.GetType().Name);
            }
        }

        private static void Finish(bool passed, string reason, bool writeReport = true)
        {
            if (writeReport)
                Save(new Result { mode = "play", status = "failed", scene = Scene,
                    reason = reason, runtimeErrors = SessionState.GetInt(Errors, 0) },
                    "play-report.json");
            SessionState.SetInt(ExitCode, passed ? 0 : 1);
            SessionState.SetString(State, "stopping");
            if (EditorApplication.isPlaying)
                EditorApplication.isPlaying = false;
        }
    }
}
