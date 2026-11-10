using System;
using System.Collections;
using System.IO;
using UnityEngine;
using UnityEngine.Profiling;
#if UNITY_ANDROID && !UNITY_EDITOR
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
        [SerializeField] private bool releaseTerrainPaintCpuCopies = true;
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
        private const float ReportInterval = 15f;
#if UNITY_ANDROID && !UNITY_EDITOR
        private UniversalRenderPipelineAsset mobilePipeline;
        private RenderPipelineAsset originalQualityPipeline;
        private float maximumScale, minimumScale;
        private float budgetSeconds, budgetSampleAt;
        private int budgetFrames, slowWindows, fastWindows;
        private long androidPssKB = -1;
#endif
        public static string LatestReport { get; private set; } = "Starting map...";

        private void Awake()
        {
            Application.targetFrameRate = targetFrameRate;
#if UNITY_ANDROID && !UNITY_EDITOR
            ConfigureMobileRendering();
#endif
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
            // Apply uploads the existing mip chain; it does not resize, recompress or regenerate it.
            // Only the Android read-only review discards CPU paint copies. No GetPixels arrays.
#if UNITY_ANDROID && !UNITY_EDITOR
            if (releaseTerrainPaintCpuCopies && terrains != null)
            {
                foreach (Terrain terrain in terrains)
                {
                    if (terrain == null || terrain.terrainData == null) continue;
                    foreach (Texture2D texture in terrain.terrainData.alphamapTextures)
                    {
                        if (texture == null || !texture.isReadable) continue;
                        long bytes = 0;
                        for (int mip = 0; mip < texture.mipmapCount; mip++)
                            bytes += (long)Mathf.Max(1, texture.width >> mip) * Mathf.Max(1, texture.height >> mip) * 4;
                        try
                        {
                            texture.Apply(false, true);
                            if (!texture.isReadable) releasedPaintBytes += bytes;
                        }
                        catch (UnityException e) { Debug.LogWarning("Terrain CPU paint copy retained: " + e.Message); }
                        // At most one 2048-pixel paint upload per frame during initial preparation.
                        yield return null;
                    }
                }
            }
#endif
            Record("terrain-cpu-copy-pass");
            yield return null;
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
#if UNITY_ANDROID && !UNITY_EDITOR
            TuneRenderScale(dt);
#endif
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
#if UNITY_ANDROID && !UNITY_EDITOR
            ResetRenderBudget();
#endif
        }
        private void OnApplicationQuit() { Record("quit"); }
        private void OnDestroy()
        {
            Application.lowMemory -= OnLowMemory;
            Application.logMessageReceived -= OnLog;
#if UNITY_ANDROID && !UNITY_EDITOR
            if (mobilePipeline != null)
            {
                if (QualitySettings.renderPipeline == mobilePipeline)
                    QualitySettings.renderPipeline = originalQualityPipeline;
                Destroy(mobilePipeline);
            }
#endif
        }

#if UNITY_ANDROID && !UNITY_EDITOR
        private void ConfigureMobileRendering()
        {
            var source = GraphicsSettings.currentRenderPipeline as UniversalRenderPipelineAsset;
            if (source == null) return;
            int ramMb = SystemInfo.systemMemorySize;
            bool lowMemoryDevice = ramMb > 0 && ramMb <= 2600;
            originalQualityPipeline = QualitySettings.renderPipeline;
            mobilePipeline = Instantiate(source);
            mobilePipeline.name = "Aaris Android Runtime Quality";
            maximumScale = Mathf.Min(source.renderScale, lowMemoryDevice ? 0.85f : 1f);
            minimumScale = Mathf.Min(maximumScale, lowMemoryDevice ? 0.70f : 0.78f);
            mobilePipeline.renderScale = lowMemoryDevice ? Mathf.Min(maximumScale, 0.80f) : maximumScale;
            mobilePipeline.shadowDistance = Mathf.Min(source.shadowDistance, lowMemoryDevice ? 90f : 150f);
            mobilePipeline.shadowCascadeCount = Mathf.Min(source.shadowCascadeCount, 2);
            mobilePipeline.mainLightShadowmapResolution = Mathf.Min(source.mainLightShadowmapResolution,
                lowMemoryDevice ? 1024 : 2048);
            QualitySettings.renderPipeline = mobilePipeline;
            ResetRenderBudget();
        }

        private void ResetRenderBudget()
        {
            budgetSeconds = 0f;
            budgetFrames = slowWindows = fastWindows = 0;
            budgetSampleAt = Time.unscaledTime + 4f;
        }

        private void TuneRenderScale(float dt)
        {
            if (mobilePipeline == null || dt <= 0f) return;
            budgetSeconds += Mathf.Min(dt, 0.1f);
            budgetFrames++;
            if (Time.unscaledTime < budgetSampleAt) return;
            float refresh = (float)Screen.currentResolution.refreshRateRatio.value;
            float target = Mathf.Max(30f, Application.targetFrameRate);
            if (refresh > 0f) target = refresh / Mathf.Max(1f, Mathf.Ceil(refresh / (target + 0.1f)));
            float mean = budgetSeconds / budgetFrames;
            slowWindows = mean > 1.18f / target ? slowWindows + 1 : 0;
            fastWindows = mean < 1.04f / target ? fastWindows + 1 : 0;
            float scale = mobilePipeline.renderScale;
            // Two slow windows lower pixel cost. Recover slowly to avoid oscillation.
            if (slowWindows >= 2 || fastWindows >= 4)
            {
                float nextScale = Mathf.Clamp(scale + (slowWindows >= 2 ? -0.07f : 0.04f),
                    minimumScale, maximumScale);
                if (!Mathf.Approximately(nextScale, scale)) mobilePipeline.renderScale = nextScale;
                slowWindows = fastWindows = 0;
            }
            budgetSeconds = 0f;
            budgetFrames = 0;
            budgetSampleAt = Time.unscaledTime + 3f;
        }
#endif
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
            public int systemRamMB, targetFps, warningCount;
            public float seconds, averageFps, p95FrameMs, renderScale = 1f;
            public long unityAllocatedBytes, unityReservedBytes, managedBytes, androidPssKB;
            public ulong textureBytes, desiredTextureBytes;
            public long terrainCpuPaintBytesReleased;
        }
        private int warningCount;
        private void Record(string reason)
        {
            if (reason == "low-memory") warningCount++;
            float total = 0;
            for (int i = 0; i < frameCount; i++) { total += frameTimes[i]; sortedTimes[i] = frameTimes[i]; }
            Array.Sort(sortedTimes, 0, frameCount);
            var s = new Sample {
                reason = reason, utc = DateTime.UtcNow.ToString("O"), version = Application.version,
                device = SystemInfo.deviceModel, gpu = SystemInfo.graphicsDeviceName, api = SystemInfo.graphicsDeviceType.ToString(),
                systemRamMB = SystemInfo.systemMemorySize, targetFps = Application.targetFrameRate,
                seconds = Time.unscaledTime, averageFps = total > 0 ? frameCount / total : 0,
                p95FrameMs = frameCount > 0 ? sortedTimes[Mathf.Clamp(Mathf.CeilToInt(frameCount * .95f) - 1, 0, frameCount - 1)] * 1000 : 0,
                unityAllocatedBytes = Profiler.GetTotalAllocatedMemoryLong(), unityReservedBytes = Profiler.GetTotalReservedMemoryLong(),
                managedBytes = GC.GetTotalMemory(false), textureBytes = Texture.currentTextureMemory,
                desiredTextureBytes = Texture.desiredTextureMemory, terrainCpuPaintBytesReleased = releasedPaintBytes,
                androidPssKB = -1, warningCount = warningCount, lastError = lastError
            };
#if UNITY_ANDROID && !UNITY_EDITOR
            // PSS is a synchronous kernel memory query. Keep it off the routine gameplay sample path.
            if (reason == "terrain-cpu-copy-pass" || reason == "low-memory" || reason == "pause")
            {
                try { using (var debug = new AndroidJavaClass("android.os.Debug")) androidPssKB = debug.CallStatic<long>("getPss"); }
                catch (Exception e) { Debug.LogWarning("Android PSS unavailable: " + e.GetType().Name); }
            }
            s.androidPssKB = androidPssKB;
            if (mobilePipeline != null) s.renderScale = mobilePipeline.renderScale;
#endif
            LatestReport = JsonUtility.ToJson(s);
            if (logPath == null) return;
            try
            {
                if (new FileInfo(logPath).Length > 256 * 1024) File.WriteAllText(logPath, "");
                File.AppendAllText(logPath, LatestReport + "\n");
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            { Debug.LogWarning("Aaris diagnostics write stopped: " + e.Message); logPath = null; }
        }
    }
}
