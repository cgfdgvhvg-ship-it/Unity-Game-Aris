using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.Profiling;
#if UNITY_ANDROID && !UNITY_EDITOR
using System.Threading.Tasks;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
#endif

namespace Aaris.MapReview
{
    // The APK reviews a fixed terrain. Editor assets stay readable and editable.
    [DisallowMultipleComponent, DefaultExecutionOrder(-300)]
    public sealed class AarisMobileRuntime : MonoBehaviour
    {
        [SerializeField] private Terrain[] terrains;
        [SerializeField] private bool releaseTerrainPaintCpuCopies = false;
        [SerializeField] private int targetFrameRate = 60;
        private readonly float[] frameTimes = new float[180];
        private readonly float[] sortedTimes = new float[180];
        private int frameIndex, frameCount;
        private float sampleAt, unloadAfter;
        private bool lowMemoryPending;
        private AsyncOperation unloading;
        private string logPath;
        private long releasedPaintBytes;
        private string lastError = "";
        private int auditedTiles, visibleHeightmaps, paintedTiles;
        private int alphamapCount, invalidTerrainMaterials;
        private bool terrainLitAvailable;
        private const float ReportInterval = 15f;
#if UNITY_ANDROID && !UNITY_EDITOR
        private long androidPssKB = -1;
        private Task<string> pendingLogWrite;
#endif
        public static string LatestReport { get; private set; } = "Starting map...";

        private void Awake()
        {
            Application.targetFrameRate = targetFrameRate;
            sampleAt = Time.unscaledTime + ReportInterval;
            Application.lowMemory += OnLowMemory;
            Application.logMessageReceived += OnLog;
            try
            {
                string folder = Path.Combine(Application.persistentDataPath, "AarisDiagnostics");
                Directory.CreateDirectory(folder);
                logPath = Path.Combine(folder, "current.jsonl");
                string previous = Path.Combine(folder, "previous.jsonl");
                if (File.Exists(logPath)) File.Copy(logPath, previous, true);
                File.WriteAllText(logPath, "");
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            { Debug.LogWarning("Aaris diagnostics file unavailable: " + e.Message); logPath = null; }
            Record("start");
        }

        private IEnumerator Start()
        {
            // DO NOT re-upload or change readability of TerrainData control
            // splatmaps on Android. Unity owns these GPU textures. The scene's
            // serialized flag might still be true in older projects; ignore it
            // rather than changing the four native TerrainData assets or
            // forcing a platform-specific renderer/material substitution.
            yield return null; // Let URP initialize its first terrain frame.
            if (releaseTerrainPaintCpuCopies)
                Debug.LogWarning("AARIS_TERRAIN_PAINT_RELEASE_DISABLED: preserve original alphamap GPU uploads.");
            AuditNativeTerrain();
            Record("terrain-render-audit");
        }

        private void AuditNativeTerrain()
        {
            if (terrains == null || terrains.Length == 0)
                terrains = Terrain.activeTerrains;
            auditedTiles = visibleHeightmaps = paintedTiles = alphamapCount =
                invalidTerrainMaterials = 0;
            Shader lit = Shader.Find("Universal Render Pipeline/Terrain/Lit");
            terrainLitAvailable = lit != null && lit.isSupported;
            if (terrains != null)
            {
                for (int i = 0; i < terrains.Length; i++)
                {
                    Terrain tile = terrains[i];
                    if (tile == null || tile.terrainData == null) continue;
                    auditedTiles++;
                    if (tile.gameObject.activeInHierarchy && tile.enabled && tile.drawHeightmap)
                        visibleHeightmaps++;
                    var layers = tile.terrainData.terrainLayers;
                    var control = tile.terrainData.alphamapTextures;
                    if (layers != null && layers.Length > 0 && control != null && control.Length > 0)
                        paintedTiles++;
                    if (control != null) alphamapCount += control.Length;
                    Material material = tile.materialTemplate;
                    if (material != null && (material.shader == null || !material.shader.isSupported))
                        invalidTerrainMaterials++;
                }
            }
            // One bounded diagnostic on startup, not a per-frame scan.
            Debug.Log("AARIS_TERRAIN_RENDER_AUDIT" +
                " tiles=" + auditedTiles +
                " visible_heightmaps=" + visibleHeightmaps +
                " painted_tiles=" + paintedTiles +
                " alphamaps=" + alphamapCount +
                " invalid_materials=" + invalidTerrainMaterials +
                " urp_terrain_lit=" + (terrainLitAvailable ? "supported" : "missing") +
                " api=" + SystemInfo.graphicsDeviceType);
        }

        private void Update()
        {
            float dt = Time.unscaledDeltaTime;
            if (dt > 0)
            {
                frameTimes[frameIndex] = dt;
                frameIndex = (frameIndex + 1) % frameTimes.Length;
                frameCount = Mathf.Min(frameCount + 1, frameTimes.Length);
            }
            if (lowMemoryPending)
            {
                lowMemoryPending = false;
                Record("low-memory");
                if (Time.unscaledTime >= unloadAfter && (unloading == null || unloading.isDone))
                {
                    unloading = Resources.UnloadUnusedAssets();
                    unloadAfter = Time.unscaledTime + 30;
                }
            }
            if (Time.unscaledTime >= sampleAt)
            {
                Record("sample");
                sampleAt = Time.unscaledTime + ReportInterval;
            }
        }

        private void OnLowMemory() { lowMemoryPending = true; }
        private void OnApplicationPause(bool paused)
        {
            if (paused) Record("pause");
        }
        private void OnApplicationQuit() { Record("quit"); }
        private void OnDestroy()
        {
            Application.lowMemory -= OnLowMemory;
            Application.logMessageReceived -= OnLog;
        }

        private void OnLog(string message, string stackTrace, LogType type)
        {
            if (type != LogType.Error && type != LogType.Exception && type != LogType.Assert) return;
            string detail = message + "\n" + stackTrace;
            lastError = detail.Length > 1536 ? detail.Substring(0, 1536) : detail;
        }

        [Serializable]
        private sealed class Sample
        {
            public string reason, utc, version, device, gpu, api, lastError;
            public int systemRamMB, targetFps, warningCount, framesOver50Ms;
            public float seconds, averageFps, p95FrameMs, p99FrameMs, renderScale = 1f;
            public long unityAllocatedBytes, unityReservedBytes, managedBytes, androidPssKB;
            public ulong textureBytes, desiredTextureBytes;
            public long terrainCpuPaintBytesReleased;
            public int terrainTiles, visibleTerrainHeightmaps, paintedTerrainTiles;
            public int terrainAlphamaps, unsupportedTerrainMaterials;
            public bool terrainLitSupported;
        }
        private int warningCount;
        private void Record(string reason)
        {
            if (reason == "low-memory") warningCount++;
            float total = 0;
            int framesOver50Ms = 0;
            for (int i = 0; i < frameCount; i++)
            {
                float frameTime = frameTimes[i];
                total += frameTime;
                sortedTimes[i] = frameTime;
                if (frameTime > .05f) framesOver50Ms++;
            }
            Array.Sort(sortedTimes, 0, frameCount);
            var s = new Sample {
                reason = reason, utc = DateTime.UtcNow.ToString("O"), version = Application.version,
                device = SystemInfo.deviceModel, gpu = SystemInfo.graphicsDeviceName, api = SystemInfo.graphicsDeviceType.ToString(),
                systemRamMB = SystemInfo.systemMemorySize, targetFps = Application.targetFrameRate,
                seconds = Time.unscaledTime, averageFps = total > 0 ? frameCount / total : 0,
                p95FrameMs = frameCount > 0 ? sortedTimes[Mathf.Clamp(Mathf.CeilToInt(frameCount * .95f) - 1, 0, frameCount - 1)] * 1000 : 0,
                p99FrameMs = frameCount > 0 ? sortedTimes[Mathf.CeilToInt(frameCount * .99f) - 1] * 1000 : 0,
                framesOver50Ms = framesOver50Ms,
                unityAllocatedBytes = Profiler.GetTotalAllocatedMemoryLong(), unityReservedBytes = Profiler.GetTotalReservedMemoryLong(),
                managedBytes = GC.GetTotalMemory(false), textureBytes = Texture.currentTextureMemory,
                desiredTextureBytes = Texture.desiredTextureMemory, terrainCpuPaintBytesReleased = releasedPaintBytes,
                terrainTiles = auditedTiles, visibleTerrainHeightmaps = visibleHeightmaps,
                paintedTerrainTiles = paintedTiles, terrainAlphamaps = alphamapCount,
                unsupportedTerrainMaterials = invalidTerrainMaterials,
                terrainLitSupported = terrainLitAvailable,
                androidPssKB = -1, warningCount = warningCount, lastError = lastError
            };
#if UNITY_ANDROID && !UNITY_EDITOR
            // PSS is a synchronous kernel memory query. Keep it off the routine gameplay sample path.
            if (reason == "terrain-render-audit" || reason == "low-memory" || reason == "pause")
            {
                try { using (var debug = new AndroidJavaClass("android.os.Debug")) androidPssKB = debug.CallStatic<long>("getPss"); }
                catch (Exception e) { Debug.LogWarning("Android PSS unavailable: " + e.GetType().Name); }
            }
            s.androidPssKB = androidPssKB;
            if (GraphicsSettings.currentRenderPipeline is UniversalRenderPipelineAsset pipeline)
                s.renderScale = pipeline.renderScale;
#endif
            LatestReport = JsonUtility.ToJson(s);
            if (logPath == null) return;
#if UNITY_ANDROID && !UNITY_EDITOR
            if (pendingLogWrite != null)
            {
                // Keep at most one outstanding write. Pause/quit flush in order
                // because Android can suspend the process after the callback.
                if (!pendingLogWrite.IsCompleted && reason != "pause" && reason != "quit") return;
                string previousError = pendingLogWrite.GetAwaiter().GetResult();
                pendingLogWrite = null;
                if (previousError != null)
                {
                    StopLogging(previousError);
                    return;
                }
            }
            if (reason != "start" && reason != "pause" && reason != "quit")
            {
                string path = logPath, report = LatestReport;
                pendingLogWrite = Task.Run(() => AppendReport(path, report));
                return;
            }
#endif
            string error = AppendReport(logPath, LatestReport);
            if (error != null) StopLogging(error);
        }

        private static string AppendReport(string path, string report)
        {
            try
            {
                if (new FileInfo(path).Length > 256 * 1024) File.WriteAllText(path, "");
                File.AppendAllText(path, report + "\n");
                return null;
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                return e.Message;
            }
        }

        private void StopLogging(string error)
        {
            Debug.LogWarning("Aaris diagnostics write stopped: " + error);
            logPath = null;
        }
    }
}
