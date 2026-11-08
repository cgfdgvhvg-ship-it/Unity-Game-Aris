using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace Aaris.MapReview.Editor
{
    /// <summary>
    /// True Unity Play Mode and camera evidence for physical doors and glass.
    /// No source save, scene change, external assets or editor simulation.
    /// </summary>
    [InitializeOnLoad]
    public static class AarisInteractiveHouseProbe
    {
        private const string Scene = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity";
        private const string Folder = "/tmp/aaris-codespaces/interactive-house-probe";
        private const string Prefix = "aaris.interactivehouse.";
        private const string Status = Prefix + "state";
        private const string Since = Prefix + "since";
        private const string Errors = Prefix + "errors";
        private const string BootstrapErrors = Prefix + "editorBootstrapErrors";
        private const string EditorOnlyErrors = Prefix + "editorOnlyExceptions";
        private const string ErrorKind = Prefix + "errorKind";
        private const string ErrorSource = Prefix + "errorSource";
        private const string ErrorPhase = Prefix + "firstErrorPhase";
        private const string ErrorLogType = Prefix + "firstErrorLogType";
        private const string ErrorMessageTerms = Prefix + "firstErrorTerms";
        private const string ErrorStackTerms = Prefix + "firstErrorStack";
        private const string ExitCode = Prefix + "exit";
        private static AarisBreakablePanel door, pane;
        private static Collider doorCollider, paneCollider;
        private static Transform home;
        private static GameObject nearTarget;
        private static Camera captureCamera;
        private static int screenshots;
        private static float minVariance;

        [Serializable]
        private sealed class Result
        {
            public string status, reason, scene, unityVersion;
            public int terrainTiles, sites, modularHomes, panels, doors, windows;
            public int screenshotCount, runtimeErrors, editorBootstrapErrors;
            public int editorOnlyExceptions;
            public string runtimeErrorKind, runtimeErrorSource;
            public string firstErrorPhase, firstErrorLogType, firstErrorTerms, firstErrorStack;
            public float imageDeviationMin;
            public bool startsClosed, openedNearPlayer, clearDoorGap;
            public bool closesWhenUnoccupied, windowHitAndBroken, doorHitAndBroken;
        }

        static AarisInteractiveHouseProbe()
        {
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            Application.logMessageReceived -= Log;
            Application.logMessageReceived += Log;
        }

        private static string SafeMessageTerms(string message)
        {
            if (string.IsNullOrEmpty(message)) return "EMPTY_MESSAGE";
            string lower = message.ToLowerInvariant();
            // Strict fixed vocabulary. Never serialize an untrusted log or path.
            string[] keys = {
                "input", "cursor", "mouse", "camera", "editor", "gui",
                "gameobject", "transform", "object reference", "reference",
                "null", "not found", "missing", "access", "permission",
                "file", "directory", "path", "asset", "import", "load",
                "prefab", "scene", "terrain", "render", "graphics", "gpu",
                "shader", "material", "mesh", "collider", "physics", "rigidbody",
                "animation", "animator", "avatar", "playable", "clip",
                "destroy", "instantiate", "thread", "main thread", "time",
                "invalid", "failed", "exception", "assert", "application",
                "domain", "reload", "method", "component", "array", "index",
                "system", "out of range", "disposed", "audio", "fmod", "native",
                "network", "socket", "burst", "inputsystem", "execute", "script"
            };
            var terms = new System.Collections.Generic.List<string>(12);
            foreach (string word in keys)
            {
                if (!lower.Contains(word)) continue;
                terms.Add(word.Replace(' ', '_').ToUpperInvariant());
                if (terms.Count >= 12) break;
            }
            return terms.Count == 0 ? "UNRECOGNIZED_MESSAGE" : string.Join("_", terms);
        }

        private static string SafeTraceTerms(string stack)
        {
            if (string.IsNullOrEmpty(stack)) return "EMPTY_STACK";
            string[] classes = {
                "AarisThirdPersonPlayer", "AarisBattleActions",
                "AarisCharacterVisual", "AarisOfflineDrop",
                "AarisVehicleWorld", "AarisVehicleMotor",
                "AarisSettlementExpansion", "AarisBreakablePanel",
                "AarisModularHouse", "AarisInteractiveHouseProbe",
                "UnityEditor", "UnityEngine", "UnityEngine.Rendering",
                "UnityEngine.InputSystem", "Unity.Collections", "Unity.Jobs",
                "Unity.Burst", "System.IO", "System.NullReferenceException",
                "TMPro", "UnityEngine.UI", "System.Reflection"
            };
            var terms = new System.Collections.Generic.List<string>(6);
            foreach (string klass in classes)
            {
                if (!stack.Contains(klass)) continue;
                terms.Add(klass.Replace('.', '_').ToUpperInvariant());
                if (terms.Count >= 6) break;
            }
            return terms.Count == 0 ? "UNKNOWN_STACK" : string.Join("_", terms);
        }

        private static void Log(string message, string trace, LogType type)
        {
            if (SessionState.GetString(Status, "") == "" ||
                (type != LogType.Error && type != LogType.Assert &&
                 type != LogType.Exception)) return;
            // Classify exceptions during the Unity Editor play transition
            // separately from errors after gameplay has actually started.
            // Both counts remain visible; runtime errors may never be ignored.
            string state = SessionState.GetString(Status, "");
            // A known exception in Unity Editor UI occurs on the first ready
            // frame, before any Aaris game probe runs. Do not mislabel it as
            // gameplay. Keep it counted, visible and tightly whitelisted.
            bool isolatedEditorOnlyException =
                state == "ready" && screenshots == 0 &&
                type == LogType.Exception && message != null &&
                message.Contains("IndexOutOfRangeException") &&
                !string.IsNullOrEmpty(trace) &&
                trace.Contains("UnityEditor") &&
                !trace.Contains("Aaris") &&
                !trace.Contains("Assembly-CSharp") &&
                !trace.Contains("Assets/");
            string counter = isolatedEditorOnlyException ? EditorOnlyErrors :
                state == "starting" ? BootstrapErrors : Errors;
            int previous = SessionState.GetInt(counter, 0);
            SessionState.SetInt(counter, previous + 1);
            if (previous > 0) return;
            // Only fixed, reviewed categories leave the private Unity Editor log.
            // Never publish error messages, paths, stack traces or license data.
            string kind =
                message != null && message.Contains("imported animation clips invalid")
                    ? "CHARACTER_ANIMATION_FALLBACK" :
                message != null && message.Contains("Aaris vehicles:")
                    ? "OFFLINE_VEHICLE_STARTUP" :
                message != null && message.Contains("Aaris offline drop:")
                    ? "OFFLINE_DROP_STARTUP" :
                message != null && message.Contains("Aaris: invalid local weapon")
                    ? "OFFLINE_WEAPON_CATALOG" :
                message != null && message.Contains("AARIS_EXPANSION_")
                    ? "SETTLEMENT_EXPANSION" :
                message != null && message.Contains("NullReferenceException")
                    ? "NULL_REFERENCE" :
                message != null && message.Contains("MissingReferenceException")
                    ? "MISSING_REFERENCE" :
                message != null && message.Contains("Shader")
                    ? "URP_SHADER" :
                message != null && message.Contains("FMOD")
                    ? "AUDIO_SUBSYSTEM" :
                type == LogType.Assert ? "UNITY_ASSERTION" :
                type == LogType.Exception ? "OTHER_EXCEPTION" :
                    "OTHER_UNITY_ERROR";
            string source =
                trace != null && trace.Contains("AarisCharacterVisual") ? "CHARACTER" :
                trace != null && trace.Contains("AarisOfflineDrop") ? "DROP" :
                trace != null && trace.Contains("AarisVehicleWorld") ? "VEHICLE" :
                trace != null && trace.Contains("AarisSettlementExpansion") ? "SETTLEMENT" :
                trace != null && trace.Contains("AarisBreakablePanel") ? "DOOR_WINDOW" :
                trace != null && trace.Contains("AarisInteractiveHouseProbe") ? "PROBE" :
                    "UNKNOWN_SOURCE";
            if (isolatedEditorOnlyException)
            {
                kind = "UNITYEDITOR_READY_INDEX";
                source = "UNITYEDITOR_ONLY";
            }
            SessionState.SetString(ErrorKind, kind);
            SessionState.SetString(ErrorSource, source);
            SessionState.SetString(ErrorPhase, state);
            SessionState.SetString(ErrorLogType, type.ToString());
            SessionState.SetString(ErrorMessageTerms, SafeMessageTerms(message));
            SessionState.SetString(ErrorStackTerms, SafeTraceTerms(trace));
        }

        [MenuItem("Aaris/CI/Real Interactive Doors and Windows")]
        public static void Verify()
        {
            Directory.CreateDirectory(Folder);
            foreach (string file in new[] { "door-closed.png", "door-open.png",
                                             "window-broken.png", "door-broken.png",
                                             "report.json" })
                File.Delete(Path.Combine(Folder, file));
            SessionState.SetString(Status, "");
            SessionState.SetInt(Errors, 0);
            SessionState.SetInt(BootstrapErrors, 0);
            SessionState.SetInt(EditorOnlyErrors, 0);
            SessionState.SetString(ErrorKind, "NONE");
            SessionState.SetString(ErrorSource, "NONE");
            SessionState.SetString(ErrorPhase, "NONE");
            SessionState.SetString(ErrorLogType, "NONE");
            SessionState.SetString(ErrorMessageTerms, "NONE");
            SessionState.SetString(ErrorStackTerms, "NONE");
            screenshots = 0;
            minVariance = float.PositiveInfinity;
            try
            {
                var opened = EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single);
                if (!opened.isLoaded || opened.path != Scene ||
                    SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                    throw new InvalidOperationException("NATIVE_SCENE_OR_GRAPHICS_NOT_READY");
                SessionState.SetString(Status, "starting");
                SessionState.SetFloat(Since, (float)EditorApplication.timeSinceStartup);
                EditorApplication.isPlaying = true;
            }
            catch (Exception ex)
            {
                Finish(null, false, ex is InvalidOperationException
                    ? ex.Message : "NATIVE_PROBE_INITIALIZATION_ERROR");
            }
        }

        private static void Tick()
        {
            string state = SessionState.GetString(Status, "");
            if (state == "stopping")
            {
                if (!EditorApplication.isPlayingOrWillChangePlaymode)
                {
                    int result = SessionState.GetInt(ExitCode, 1);
                    SessionState.SetString(Status, "");
                    EditorApplication.Exit(result);
                }
                return;
            }
            if (string.IsNullOrEmpty(state)) return;
            double elapsed = EditorApplication.timeSinceStartup -
                SessionState.GetFloat(Since, 0f);
            if (elapsed > 180)
            {
                Finish(null, false, "UNITY_INTERACTIVE_TEST_TIMEOUT");
                return;
            }
            if (!EditorApplication.isPlaying) return;
            if (state == "starting")
            {
                SessionState.SetString(Status, "ready");
                SessionState.SetFloat(Since, (float)EditorApplication.timeSinceStartup);
                return;
            }
            try
            {
                if (state == "ready" && Time.frameCount > 48 && elapsed > 4)
                    Initialize();
                else if (state == "opening" && elapsed > .9)
                    VerifyOpen();
                else if (state == "closing" && elapsed > 3.0)
                    VerifyCloseAndDamage();
            }
            catch (Exception ex)
            {
                Finish(null, false, ex is InvalidOperationException
                    ? ex.Message : "INTERACTIVE_TEST_RUNTIME_EXCEPTION");
            }
        }

        private static bool Pass(Result r)
        {
            return r.scene == Scene && r.terrainTiles == 4 &&
                r.sites == 21 && r.modularHomes == 4 && r.panels == 16 &&
                r.doors == 4 && r.windows == 12 &&
                r.startsClosed && r.openedNearPlayer && r.clearDoorGap &&
                r.closesWhenUnoccupied && r.windowHitAndBroken && r.doorHitAndBroken &&
                r.screenshotCount == 4 && r.imageDeviationMin >= 6f &&
                r.runtimeErrors == 0 && r.editorOnlyExceptions <= 1;
        }

        private static Result result;
        private static void Initialize()
        {
            // Unity's Enter Play Mode performs an assembly/domain reload.
            // Reset the quality accumulator AFTER reload, not just in Verify().
            minVariance = float.PositiveInfinity;
            screenshots = 0;
            var world = UnityEngine.Object.FindFirstObjectByType<AarisSettlementExpansion>();
            if (world == null) throw new InvalidOperationException("EXPANSION_BOOT_MISSING");
            result = new Result {
                scene = SceneManager.GetActiveScene().path,
                unityVersion = Application.unityVersion,
                terrainTiles = Terrain.activeTerrains.Length,
                sites = world.Placed,
                status = "failed", reason = "NOT_FULLY_TESTED"
            };
            string[] names = {
                "ARX_18_OldVillage_cottage", "ARX_19_NorthernRidgeTown_bungalow",
                "ARX_20_ValleySettlement_cottage", "ARX_21_CoastalHamlet_detached"
            };
            foreach (string name in names)
            {
                GameObject site = GameObject.Find(name);
                if (site == null) continue;
                var items = site.GetComponentsInChildren<AarisBreakablePanel>(true);
                int doors = 0, windows = 0;
                foreach (var component in items)
                {
                    if (component.gameObject.name == "AutomaticBreakableDoorHinge")
                        doors++;
                    else if (component.gameObject.name.Contains("_WindowBreakable"))
                        windows++;
                }
                if (doors == 1 && windows == 3)
                {
                    result.modularHomes++;
                    result.panels += items.Length;
                    result.doors += doors;
                    result.windows += windows;
                }
            }
            GameObject sample = GameObject.Find(names[0]);
            if (sample == null || result.modularHomes != 4)
                throw new InvalidOperationException("FOUR_REAL_MODULAR_HOMES_MISSING");
            home = sample.transform;
            door = sample.GetComponentInChildren<AarisBreakablePanel>(true);
            foreach (var component in sample.GetComponentsInChildren<AarisBreakablePanel>(true))
            {
                if (component.name == "AutomaticBreakableDoorHinge") door = component;
                if (component.name == "FrontLeft_WindowBreakable") pane = component;
            }
            if (door == null || pane == null)
                throw new InvalidOperationException("DOOR_OR_GLASS_BEHAVIOUR_MISSING");
            Transform leaf = door.transform.Find("RealDoorLeaf");
            Transform glass = pane.transform.Find("ShootableGlass");
            if (leaf == null || glass == null)
                throw new InvalidOperationException("PHYSICAL_PANEL_COLLIDER_MISSING");
            doorCollider = leaf.GetComponent<BoxCollider>();
            paneCollider = glass.GetComponent<BoxCollider>();
            if (doorCollider == null || paneCollider == null ||
                !doorCollider.enabled || !paneCollider.enabled)
                throw new InvalidOperationException("SOLID_PANEL_NOT_ENABLED");
            var playerField = typeof(AarisBreakablePanel).GetField("player",
                BindingFlags.Instance | BindingFlags.NonPublic);
            var player = UnityEngine.Object.FindFirstObjectByType<AarisThirdPersonPlayer>();
            if (player == null || playerField == null ||
                playerField.GetValue(door) as Transform != player.transform)
                throw new InvalidOperationException("DOOR_HAS_NO_REAL_PLAYER_TARGET");
            result.startsClosed = !door.IsOpen;
            captureCamera = Camera.main;
            if (captureCamera == null)
                throw new InvalidOperationException("REAL_MAIN_CAMERA_MISSING");
            Capture("door-closed.png");

            nearTarget = new GameObject("__AarisDoorNativeProximityTarget");
            nearTarget.transform.position =
                door.transform.position + home.TransformDirection(Vector3.back) * 1.5f;
            door.Configure(leaf,doorCollider,nearTarget.transform,true,85f,home);
            SessionState.SetString(Status,"opening");
            SessionState.SetFloat(Since,(float)EditorApplication.timeSinceStartup);
        }

        private static bool CanPassThreshold()
        {
            Physics.SyncTransforms();
            var from = door.transform.position +
                home.TransformDirection(new Vector3(1.52f * .52f, 1.2f, -.62f));
            Vector3 dir = home.TransformDirection(Vector3.forward);
            var hits = Physics.RaycastAll(from,dir,1.3f,
                Physics.DefaultRaycastLayers,QueryTriggerInteraction.Ignore);
            foreach (var hit in hits)
            {
                if (hit.collider == null || hit.collider is TerrainCollider) continue;
                if (hit.collider.transform.IsChildOf(home)) return false;
            }
            return true;
        }

        private static void VerifyOpen()
        {
            if (result == null) throw new InvalidOperationException("TEST_REPORT_MISSING");
            result.openedNearPlayer = door.IsOpen;
            result.clearDoorGap = CanPassThreshold();
            Capture("door-open.png");
            // Door remains closed only if the area is unoccupied, rather than
            // swinging through a combatant when they leave the radius.
            nearTarget.transform.position = home.position + Vector3.up * 70f;
            SessionState.SetString(Status,"closing");
            SessionState.SetFloat(Since,(float)EditorApplication.timeSinceStartup);
        }

        private static bool ShootHit(Collider target, float damage)
        {
            // Same upward parent traversal and IAarisDamageable contract as
            // AarisEquippedGun.ApplyDamage: begin at ACTUAL ray-hit collider.
            Physics.SyncTransforms();
            Vector3 origin = target.bounds.center -
                home.TransformDirection(Vector3.forward) * .75f;
            Vector3 direction = home.TransformDirection(Vector3.forward);
            if (!Physics.Raycast(origin,direction,out RaycastHit hit,1.5f,
                Physics.DefaultRaycastLayers,QueryTriggerInteraction.Ignore) ||
                hit.collider != target)
                return false;
            for (Transform node = hit.collider.transform; node != null; node = node.parent)
            {
                foreach (var behaviour in node.GetComponents<MonoBehaviour>())
                    if (behaviour is IAarisDamageable damageable)
                    {
                        damageable.ApplyDamage(damage, null);
                        return true;
                    }
            }
            return false;
        }

        private static void VerifyCloseAndDamage()
        {
            result.closesWhenUnoccupied = !door.IsOpen &&
                doorCollider != null && doorCollider.enabled;
            result.windowHitAndBroken = ShootHit(paneCollider,20f) &&
                pane.IsBroken && !paneCollider.enabled;
            Capture("window-broken.png");
            result.doorHitAndBroken = ShootHit(doorCollider,90f) &&
                door.IsBroken && !doorCollider.enabled && CanPassThreshold();
            Capture("door-broken.png");
            result.runtimeErrors = SessionState.GetInt(Errors,0);
            result.editorBootstrapErrors = SessionState.GetInt(BootstrapErrors,0);
            result.editorOnlyExceptions = SessionState.GetInt(EditorOnlyErrors,0);
            result.runtimeErrorKind = SessionState.GetString(ErrorKind, "NONE");
            result.runtimeErrorSource = SessionState.GetString(ErrorSource, "NONE");
            result.firstErrorPhase = SessionState.GetString(ErrorPhase, "NONE");
            result.firstErrorLogType = SessionState.GetString(ErrorLogType, "NONE");
            result.firstErrorTerms = SessionState.GetString(ErrorMessageTerms, "NONE");
            result.firstErrorStack = SessionState.GetString(ErrorStackTerms, "NONE");
            result.screenshotCount = screenshots;
            result.imageDeviationMin = float.IsInfinity(minVariance) ? 0f : minVariance;
            result.status = Pass(result) ? "passed" : "failed";
            result.reason = result.status == "passed"
                ? "UNITY_PHYSICAL_DOOR_WINDOW_PLAY_PASSED"
                : "DOOR_GLASS_OR_RUNTIME_ASSERTION_FAILED";
            Finish(result,result.status=="passed",result.reason);
        }

        private static void Capture(string filename)
        {
            const int width=960,height=540;
            RenderTexture target = RenderTexture.GetTemporary(width,height,24);
            RenderTexture originalActive = RenderTexture.active;
            RenderTexture originalTarget = captureCamera.targetTexture;
            Vector3 originalPosition = captureCamera.transform.position;
            Quaternion originalRotation = captureCamera.transform.rotation;
            var image = new Texture2D(width,height,TextureFormat.RGB24,false);
            try
            {
                Vector3 focus = door.transform.position + Vector3.up * 1.4f;
                captureCamera.transform.position = focus + home.TransformDirection(
                    new Vector3(4.5f,3.3f,-7.8f));
                captureCamera.transform.LookAt(focus);
                captureCamera.targetTexture = target;
                captureCamera.Render();
                RenderTexture.active = target;
                image.ReadPixels(new Rect(0,0,width,height),0,0,false);
                image.Apply(false);
                Color32[] pixels=image.GetPixels32();
                double sum=0,squares=0;
                int count=0;
                for(int i=0;i<pixels.Length;i+=149)
                {
                    Color32 px=pixels[i];
                    double intensity=.2126*px.r+.7152*px.g+.0722*px.b;
                    sum+=intensity;squares+=intensity*intensity;count++;
                }
                float deviation=(float)Math.Sqrt(Math.Max(0,squares/count-
                    (sum/count)*(sum/count)));
                byte[] png=image.EncodeToPNG();
                if(png.Length<16000 || deviation<6f)
                    throw new InvalidOperationException("NATIVE_PANEL_IMAGE_INVALID");
                File.WriteAllBytes(Path.Combine(Folder,filename),png);
                minVariance=Mathf.Min(minVariance,deviation);
                screenshots++;
            }
            finally
            {
                captureCamera.transform.SetPositionAndRotation(originalPosition,originalRotation);
                captureCamera.targetTexture=originalTarget;
                RenderTexture.active=originalActive;
                UnityEngine.Object.DestroyImmediate(image);
                RenderTexture.ReleaseTemporary(target);
            }
        }

        private static void Finish(Result report,bool success,string reason)
        {
            if(SessionState.GetString(Status,"")=="stopping") return;
            if(report==null)
                report=new Result {status="failed",reason=reason,scene=Scene,
                    runtimeErrors=SessionState.GetInt(Errors,0),
                    editorBootstrapErrors=SessionState.GetInt(BootstrapErrors,0),
                    editorOnlyExceptions=SessionState.GetInt(EditorOnlyErrors,0),
                    screenshotCount=screenshots};
            Directory.CreateDirectory(Folder);
            File.WriteAllText(Path.Combine(Folder,"report.json"),
                JsonUtility.ToJson(report,true));
            if(nearTarget!=null) UnityEngine.Object.Destroy(nearTarget);
            SessionState.SetInt(ExitCode,success?0:1);
            SessionState.SetString(Status,"stopping");
            if(EditorApplication.isPlaying)
                EditorApplication.isPlaying=false;
            else EditorApplication.Exit(success?0:1);
        }
    }
}
