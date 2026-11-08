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
        private const string ErrorKind = "aaris.codespace.probe.errorKind";
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
            public string runtimeErrorKind;
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
            {
                SessionState.SetInt(Errors, Math.Min(10000, SessionState.GetInt(Errors, 0) + 1));
                // Classify without storing/publishing the raw message or stack.
                if (SessionState.GetString(ErrorKind, "") == "")
                    SessionState.SetString(ErrorKind, CategorizePlayError(message, trace, type));
            }
        }


        private static string CategorizePlayError(string message, string trace, LogType type)
        {
            if (message == null) message = "";
            if (trace == null) trace = "";
            if (message.Contains("Aaris vehicles: authored offline candidates/catalog")) return "VEHICLE_SOURCE_MISSING";
            if (message.Contains("Aaris vehicles: malformed offline data")) return "VEHICLE_CATALOG_INVALID";
            if (message.Contains("Aaris vehicles: source data does not match")) return "VEHICLE_CATALOG_MAP_MISMATCH";
            if (message.Contains("Aaris vehicles: not all required local")) return "VEHICLE_MODEL_MISSING";
            if (message.Contains("Aaris vehicles: verified URP palette/shader")) return "VEHICLE_SHADER_MISSING";
            if (message.Contains("Aaris: no embedded offline authored loot locations")) return "LOOT_SOURCE_MISSING";
            if (message.Contains("Aaris: invalid loot JSON")) return "LOOT_DATA_INVALID";
            if (message.Contains("Aaris: loot candidates do not describe")) return "LOOT_DATA_MAP_MISMATCH";
            if (message.Contains("Saved player camera is missing")) return "PLAYER_CAMERA_MISSING";
            if (message.Contains("Aaris: imported animation clips invalid")) return "PLAYER_ANIMATION_CLIPS_INVALID";
            if (message.Contains("Aaris: invalid weapon state configured")) return "WEAPON_STATE_INVALID";
            if (message.Contains("NullReferenceException")) return "NULL_REFERENCE";
            if (message.Contains("MissingReferenceException")) return "MISSING_REFERENCE";
            if (message.Contains("UnassignedReferenceException")) return "UNASSIGNED_REFERENCE";
            if (message.Contains("IndexOutOfRangeException")) return "ARRAY_INDEX";
            if (message.Contains("MissingComponentException")) return "MISSING_COMPONENT";
            if (trace.Contains("AarisVehicleWorld")) return "VEHICLE_RUNTIME_EXCEPTION";
            if (trace.Contains("AarisWeaponLootWorld")) return "LOOT_RUNTIME_EXCEPTION";
            if (trace.Contains("AarisThirdPersonPlayer")) return "PLAYER_RUNTIME_EXCEPTION";
            if (trace.Contains("AarisVehicleMotor")) return "VEHICLE_MOTOR_EXCEPTION";
            return type == LogType.Assert ? "GAME_ASSERTION" :
                type == LogType.Exception ? "UNCLASSIFIED_EXCEPTION" : "UNCLASSIFIED_ERROR";
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


        // Owner-approved map coordinates and azimuth. Terrain elevation is
        // sampled from the real LFS TerrainData, not guessed from a blueprint.
        private static float PhotoOption(string key, float fallback, float low, float high)
        {
            string prefix = "-aaris" + key + "=";
            foreach (string arg in Environment.GetCommandLineArgs())
            {
                if (!arg.StartsWith(prefix, StringComparison.Ordinal)) continue;
                float result;
                if (!float.TryParse(arg.Substring(prefix.Length),
                    System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out result) ||
                    float.IsNaN(result) || float.IsInfinity(result) ||
                    result < low || result > high)
                    throw new ArgumentException("INVALID_PHOTO_" + key.ToUpperInvariant());
                return result;
            }
            return fallback;
        }

        private static float Elevation(Terrain[] terrains, float x, float z, float fallback)
        {
            foreach (Terrain t in terrains)
            {
                Vector3 p = t.transform.position;
                Vector3 size = t.terrainData.size;
                if (x >= p.x && x <= p.x + size.x && z >= p.z && z <= p.z + size.z)
                    return t.SampleHeight(new Vector3(x, 0, z)) + p.y;
            }
            return fallback; // Camera can be outside the saved map, target cannot.
        }

        [Serializable]
        private sealed class PhotoReport
        {
            public string mode;
            public string status;
            public string reason;
            public string scene;
            public string unityVersion;
            public string graphicsDevice;
            public int terrainTiles;
            public float targetX, targetY, targetZ;
            public float cameraX, cameraY, cameraZ;
            public float yaw, pitch, distance;
            public float detailVariation, contextVariation;
            public string[] images;
        }

        // Frame any requested X/Z in the saved world. Its Y is the true terrain
        // height, and the requested yaw/pitch/distance fix the viewing direction.
        // A second wider view allows AI to identify landmarks around the target.
        [MenuItem("Aaris/CI/Take coordinate photo")]
        public static void CaptureAt()
        {
            Directory.CreateDirectory(Output);
            PhotoReport result = new PhotoReport {
                mode = "photo", status = "failed", scene = Scene,
                unityVersion = Application.unityVersion,
                graphicsDevice = SystemInfo.graphicsDeviceType.ToString()
            };
            GameObject go = null;
            try
            {
                float x = PhotoOption("X", 0f, -1000f, 1000f);
                float z = PhotoOption("Z", 0f, -1000f, 1000f);
                float yaw = PhotoOption("Yaw", 35f, -360f, 360f);
                float pitch = PhotoOption("Pitch", 30f, 12f, 75f);
                float distance = PhotoOption("Distance", 85f, 20f, 450f);
                Terrain[] terrains = LoadNativeScene();
                result.terrainTiles = terrains.Length;
                float ground = Elevation(terrains, x, z, float.NaN);
                if (float.IsNaN(ground)) throw new InvalidOperationException("TARGET_NOT_ON_NATIVE_TERRAIN");

                // Frame the nearest modest-size renderer if its center is
                // close to the selected coordinate. This avoids cutting off a
                // nearby roof or tree, but never substitutes a different target.
                float aimHeight = ground + 3f;
                float best = 28f * 28f;
                foreach (Renderer renderer in UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None))
                {
                    Bounds bounds = renderer.bounds;
                    if (bounds.size.magnitude > 130f) continue;
                    float dx = bounds.center.x - x, dz = bounds.center.z - z;
                    float score = dx * dx + dz * dz;
                    if (score < best && bounds.max.y > ground + 2f)
                    {
                        best = score;
                        aimHeight = Mathf.Clamp(bounds.center.y, ground + 2f, ground + 55f);
                    }
                }
                Vector3 target = new Vector3(x, aimHeight, z);
                float angle = yaw * Mathf.Deg2Rad;
                Vector3 backward = new Vector3(-Mathf.Sin(angle), 0, -Mathf.Cos(angle));
                Vector3 cameraPosition = target + backward * distance
                    + Vector3.up * (distance * Mathf.Tan(pitch * Mathf.Deg2Rad));
                cameraPosition.y = Mathf.Max(cameraPosition.y,
                    Elevation(terrains, cameraPosition.x, cameraPosition.z, ground) + 5f);

                // Lift the camera above every sampled point of the terrain
                // along the view ray, so a mountain cannot simply fill the shot.
                for (int i = 1; i <= 24; i++)
                {
                    float t = i / 25f;
                    Vector3 sample = Vector3.Lerp(cameraPosition, target, t);
                    float terrainY = Elevation(terrains, sample.x, sample.z, -100000f);
                    float needed = (terrainY + 3f - t * target.y) / (1f - t);
                    if (terrainY > -99999f) cameraPosition.y = Mathf.Max(cameraPosition.y, needed);
                }
                cameraPosition.y = Mathf.Min(cameraPosition.y, target.y + 1800f);

                go = new GameObject("__Aaris_Coordinate_Photo_Camera");
                go.hideFlags = HideFlags.HideAndDontSave;
                Camera camera = go.AddComponent<Camera>();
                camera.enabled = false;
                camera.orthographic = false;
                camera.fieldOfView = 62f;
                camera.nearClipPlane = 0.1f;
                camera.farClipPlane = 5500f;
                camera.clearFlags = CameraClearFlags.Skybox;
                camera.allowHDR = true;
                camera.transform.position = cameraPosition;
                camera.transform.LookAt(target, Vector3.up);
                result.detailVariation = Render(camera, 1600, 900, Path.Combine(Output, "photo-detail.png"));
                result.cameraX = cameraPosition.x;
                result.cameraY = cameraPosition.y;
                result.cameraZ = cameraPosition.z;

                // Context frame is deliberately wider, from the same azimuth,
                // to show roads/trees/buildings around the inspection point.
                Vector3 widePosition = target + backward * Mathf.Max(130f, distance * 2.25f)
                    + Vector3.up * Mathf.Max(95f, distance * 1.8f);
                widePosition.y = Mathf.Max(widePosition.y,
                    Elevation(terrains, widePosition.x, widePosition.z, ground) + 12f);
                camera.transform.position = widePosition;
                camera.transform.LookAt(target, Vector3.up);
                result.contextVariation = Render(camera, 1600, 900,
                    Path.Combine(Output, "photo-context.png"));
                result.targetX = x;
                result.targetY = aimHeight;
                result.targetZ = z;
                result.yaw = yaw;
                result.pitch = pitch;
                result.distance = distance;
                result.images = new[] { "photo-detail.png", "photo-context.png" };
                result.status = "passed";
                result.reason = "NATIVE_COORDINATE_CAMERA_AND_CONTEXT_RENDERED";
                Debug.Log("AARIS_NATIVE_COORDINATE_PHOTO_PASSED");
            }
            catch (Exception e)
            {
                result.reason = e is InvalidOperationException || e is ArgumentException
                    ? e.Message : e.GetType().Name;
                Debug.LogError("AARIS_NATIVE_COORDINATE_PHOTO_FAILED:" + result.reason);
                throw;
            }
            finally
            {
                if (go != null) UnityEngine.Object.DestroyImmediate(go);
                File.WriteAllText(Path.Combine(Output, "photo-report.json"),
                    JsonUtility.ToJson(result, true));
            }
        }


        [Serializable]
        private sealed class FoliageReport
        {
            public string mode;
            public string status;
            public string reason;
            public string unityVersion;
            public string graphicsDevice;
            public int terrainTiles;
            public int treePrototypes;
            public int foliageRenderers;
            public int customFoliageMaterials;
            public float originalVariation;
            public float distantLodVariation;
            public float ambientVariation;
            public string[] images;
        }

        // The test changes only the in-memory view settings and immediately
        // restores them. No TerrainData, prefab, material or scene is saved.
        // SpeedTree's LODGroup controls the actual LOD on painted SpeedTrees;
        // lower treeLODBiasMultiplier and QualitySettings.lodBias force the
        // long-distance presentation in an otherwise identical camera view.
        [MenuItem("Aaris/CI/Diagnose SpeedTree foliage rendering")]
        public static void DiagnoseFoliage()
        {
            Directory.CreateDirectory(Output);
            FoliageReport report = new FoliageReport {
                mode = "foliage", status = "failed",
                unityVersion = Application.unityVersion,
                graphicsDevice = SystemInfo.graphicsDeviceType.ToString()
            };
            GameObject rig = null;
            Terrain[] terrains = null;
            float[] originalBiases = null;
            float qualityBias = QualitySettings.lodBias;
            ShadowQuality shadowQuality = QualitySettings.shadows;
            UnityEngine.Rendering.AmbientMode ambientMode = RenderSettings.ambientMode;
            Color ambientColor = RenderSettings.ambientLight;
            float ambientIntensity = RenderSettings.ambientIntensity;
            try
            {
                terrains = LoadNativeScene();
                report.terrainTiles = terrains.Length;
                originalBiases = terrains.Select(t => t.treeLODBiasMultiplier).ToArray();
                var prototypes = terrains.SelectMany(t => t.terrainData.treePrototypes)
                    .Select(p => p.prefab).Where(p => p != null).Distinct().ToArray();
                report.treePrototypes = prototypes.Length;
                report.foliageRenderers = prototypes.Sum(p =>
                    p.GetComponentsInChildren<MeshRenderer>(true).Length);
                report.customFoliageMaterials = prototypes
                    .SelectMany(p => p.GetComponentsInChildren<MeshRenderer>(true))
                    .SelectMany(r => r.sharedMaterials)
                    .Where(m => m != null && m.shader != null &&
                        m.shader.name.IndexOf("SpeedTree", StringComparison.OrdinalIgnoreCase) >= 0)
                    .Distinct().Count();

                // Reproduce the verified dark foliage at coordinates 350/220.
                rig = new GameObject("__Aaris_Transient_Foliage_Test_Camera");
                rig.hideFlags = HideFlags.HideAndDontSave;
                Camera camera = rig.AddComponent<Camera>();
                camera.enabled = false;
                camera.fieldOfView = 62f;
                camera.nearClipPlane = 0.1f;
                camera.farClipPlane = 5500f;
                camera.clearFlags = CameraClearFlags.Skybox;
                camera.allowHDR = true;
                camera.transform.position = new Vector3(265f, 67.18f, 220f);
                camera.transform.LookAt(new Vector3(350f, 7.66f, 220f), Vector3.up);
                report.originalVariation = Render(camera, 1280, 720,
                    Path.Combine(Output, "foliage-original.png"));

                // For SpeedTree on terrain, the per-terrain LOD bias multiplier
                // controls which LODGroup level is used, unlike the standard
                // Tree Editor billboard settings.
                QualitySettings.lodBias = 0.05f;
                foreach (Terrain t in terrains) t.treeLODBiasMultiplier = 0.05f;
                report.distantLodVariation = Render(camera, 1280, 720,
                    Path.Combine(Output, "foliage-far-lod.png"));

                // Restore LOD; compare a no-shadows, ambient-lit capture to
                // distinguish bad LOD textures from lighting/AO/shadow artifacts.
                QualitySettings.lodBias = qualityBias;
                for (int i = 0; i < terrains.Length; i++)
                    terrains[i].treeLODBiasMultiplier = originalBiases[i];
                QualitySettings.shadows = ShadowQuality.Disable;
                RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
                RenderSettings.ambientLight = new Color(0.69f, 0.70f, 0.65f);
                RenderSettings.ambientIntensity = 1.2f;
                report.ambientVariation = Render(camera, 1280, 720,
                    Path.Combine(Output, "foliage-ambient-test.png"));

                report.images = new[] { "foliage-original.png",
                    "foliage-far-lod.png", "foliage-ambient-test.png" };
                report.status = "passed";
                report.reason = "REAL_SPEEDTREE_LOD_AND_LIGHTING_COMPARISON";
                Debug.Log("AARIS_NATIVE_FOLIAGE_DIAG_PASSED");
            }
            catch (Exception e)
            {
                report.reason = e is InvalidOperationException
                    ? e.Message : e.GetType().Name;
                Debug.LogError("AARIS_NATIVE_FOLIAGE_DIAG_FAILED:" + report.reason);
                throw;
            }
            finally
            {
                QualitySettings.lodBias = qualityBias;
                QualitySettings.shadows = shadowQuality;
                RenderSettings.ambientMode = ambientMode;
                RenderSettings.ambientLight = ambientColor;
                RenderSettings.ambientIntensity = ambientIntensity;
                if (terrains != null && originalBiases != null)
                    for (int i = 0; i < terrains.Length; i++)
                        terrains[i].treeLODBiasMultiplier = originalBiases[i];
                if (rig != null) UnityEngine.Object.DestroyImmediate(rig);
                File.WriteAllText(Path.Combine(Output, "foliage-report.json"),
                    JsonUtility.ToJson(report, true));
            }
        }

        [MenuItem("Aaris/CI/Native Play Mode smoke test")]
        public static void Play()
        {
            Directory.CreateDirectory(Output);
            SessionState.SetString(State, "");
            SessionState.SetInt(Errors, 0);
            SessionState.SetString(ErrorKind, "");
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
                    runtimeErrorKind = SessionState.GetString(ErrorKind, ""),
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
                    reason = reason, runtimeErrors = SessionState.GetInt(Errors, 0),
                    runtimeErrorKind = SessionState.GetString(ErrorKind, "") },
                    "play-report.json");
            SessionState.SetInt(ExitCode, passed ? 0 : 1);
            SessionState.SetString(State, "stopping");
            if (EditorApplication.isPlaying)
                EditorApplication.isPlaying = false;
        }
    }
}
