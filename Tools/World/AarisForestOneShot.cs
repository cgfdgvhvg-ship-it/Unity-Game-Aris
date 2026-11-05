#if UNITY_EDITOR
// One-shot helper staged ONLY in /tmp scratch Unity project. Real deliverables
// are saved TerrainData .asset binaries, never compiled runtime appearance hacks.
using System;
using System.IO;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Aaris.WorldAutomation
{
    public static class AarisForestOneShot
    {
        private const string Scene = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity";
        private const string Results = "/tmp/aaris-unity-batch/control/unity-results";

        public static void Execute()
        {
            string id = Environment.GetEnvironmentVariable("AARIS_FOREST_JOB_ID") ?? "";
            string mode = Environment.GetEnvironmentVariable("AARIS_FOREST_MODE") ?? "";
            string target = Environment.GetEnvironmentVariable("AARIS_FOREST_TARGET") ?? "";
            string expected = Environment.GetEnvironmentVariable("AARIS_FOREST_SHA256") ?? "";
            var reply = new AarisLiveEditorBridge.Response {
                id = id, action = mode == "apply" ? "forest_apply" : "forest_plan",
                scene = Scene, unityVersion = Application.unityVersion, status = "error"
            };
            int exitCode = 3;
            try
            {
                if (!Regex.IsMatch(id, @"^[a-z][a-z0-9-]{3,55}$"))
                    throw new InvalidOperationException("Invalid forest job ID");
                if (mode != "plan" && mode != "apply")
                    throw new InvalidOperationException("Forest mode unsupported");
                if (mode == "apply" &&
                    (!Regex.IsMatch(target, @"^Assets/TerrainDemoScene_URP/Terrain/Data/Terrain_[a-zA-Z0-9_-]+\.asset$") ||
                     !Regex.IsMatch(expected, @"^[0-9a-f]{64}$")))
                    throw new InvalidOperationException("Expected one native core tile and exact SHA256");
                var current = EditorSceneManager.OpenScene(Scene, OpenSceneMode.Single);
                if (!current.IsValid() || !current.isLoaded)
                    throw new InvalidOperationException("Native map scene was not loaded");
                var request = new AarisLiveEditorBridge.Request {
                    id = id,
                    action = reply.action,
                    target = mode == "plan" ? "all" : target,
                    expectedDigest = expected
                };
                AarisForestCoreAuthoring.Run(request, reply, mode == "apply");
                if (reply.forestReports == null ||
                    (mode == "plan" && reply.forestReports.Length != 4) ||
                    (mode == "apply" && reply.forestReports.Length != 1))
                    throw new InvalidOperationException("Missing native tree-only report");
                int treeTotal = 0, rockTotal = 0, shrubTotal = 0;
                foreach (var tile in reply.forestReports)
                {
                    treeTotal += tile.actualTrees;
                    rockTotal += tile.preservedRocks;
                    shrubTotal += tile.preservedShrubs;
                    if (tile.changedCount != tile.actualTrees)
                        throw new InvalidOperationException("Not every genuine tree was rescaled");
                }
                if (mode == "plan" && (treeTotal != 1939 || rockTotal != 5564 ||
                    shrubTotal != 5 || reply.terrainTreeCount != 7508))
                    throw new InvalidOperationException("Unexpected full-map tree category split");
                reply.status = "ok";
                exitCode = 0;
                Debug.Log("AARIS_FOREST_CORE_ONESHOT_OK mode=" + mode +
                          " tile=" + (mode == "apply" ? target : "all") +
                          " native_trees=" + reply.terrainTreeCount);
            }
            catch (Exception exc)
            {
                reply.status = "error";
                reply.error = exc.GetType().Name + ": " + exc.Message;
                Debug.LogError("AARIS_FOREST_CORE_ONESHOT_BLOCKED " + reply.error);
            }
            finally
            {
                // Only an authorized single-use scratch job may write this
                // result. Autosync must still verify changed .asset SHA + GUID.
                try
                {
                    Directory.CreateDirectory(Results);
                    if (Regex.IsMatch(id, @"^[a-z][a-z0-9-]{3,55}$"))
                    {
                        string path = Path.Combine(Results, id + ".json");
                        if (File.Exists(path))
                            throw new InvalidOperationException("Forest result ID already used");
                        string temp = path + ".new";
                        if (File.Exists(temp))
                            throw new InvalidOperationException("Stale scratch result temp");
                        File.WriteAllText(temp, JsonUtility.ToJson(reply, true));
                        File.Move(temp, path);
                    }
                }
                catch (Exception exc)
                {
                    Debug.LogError("AARIS_FOREST_ONESHOT_RESULT_FAIL " + exc.Message);
                    exitCode = 4;
                }
                EditorApplication.Exit(exitCode);
            }
        }
    }
}
#endif
