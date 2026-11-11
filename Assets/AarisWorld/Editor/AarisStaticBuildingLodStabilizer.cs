using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Aaris.MapReview.Editor
{
    // Author-only, one-shot correction of dither flicker on static building LODs.
    // Do not change terrain, trees, characters or runtime scripts.
    [InitializeOnLoad]
    public static class AarisStaticBuildingLodStabilizer
    {
        const string Marker = "/tmp/aaris-codespaces/fix-static-building-lods.request";
        const string Result = "/tmp/aaris-codespaces/fix-static-building-lods.txt";

        static AarisStaticBuildingLodStabilizer()
        {
            EditorApplication.delayCall += () =>
            {
                if (File.Exists(Marker) && !EditorApplication.isPlayingOrWillChangePlaymode)
                {
                    File.Delete(Marker);
                    Stabilize();
                }
            };
        }

        [MenuItem("Aaris/Review/Fix Static Building LOD Flicker")]
        public static void Stabilize()
        {
            string status;
            try
            {
                Scene scene = SceneManager.GetActiveScene();
                var districts = GameObject.Find("Districts");
                if (EditorApplication.isPlayingOrWillChangePlaymode ||
                    scene.path != "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity" ||
                    districts == null)
                    throw new InvalidOperationException("NATIVE_SCENE_EDITMODE_REQUIRED");

                int count = 0;
                foreach (var lod in UnityEngine.Object.FindObjectsByType<LODGroup>(FindObjectsSortMode.None))
                    if (lod != null && lod.transform.IsChildOf(districts.transform))
                        count++;
                if (count != 59)
                    throw new InvalidOperationException("UNEXPECTED_ARCHITECTURE_LOD_COUNT_" + count);

                foreach (var lod in UnityEngine.Object.FindObjectsByType<LODGroup>(FindObjectsSortMode.None))
                {
                    if (lod == null || !lod.transform.IsChildOf(districts.transform)) continue;
                    Undo.RecordObject(lod, "Remove static architecture temporal LOD dither");
                    lod.fadeMode = LODFadeMode.None;
                    lod.animateCrossFading = false;
                    EditorUtility.SetDirty(lod);
                }
                EditorSceneManager.MarkSceneDirty(scene);
                if (!EditorSceneManager.SaveScene(scene))
                    throw new InvalidOperationException("NATIVE_SCENE_SAVE_FAILED");
                status = "AARIS_BUILDING_LOD_STABLE count=" + count + " animated_dither=off scene_saved=true";
                Debug.Log(status);
            }
            catch (Exception e)
            {
                status = "AARIS_BUILDING_LOD_STABLE status=FAILED reason=" + e.GetType().Name +
                         " message=" + e.Message;
                Debug.LogError(status);
            }
            Directory.CreateDirectory(Path.GetDirectoryName(Result));
            File.WriteAllText(Result, status + "\n");
        }
    }
}
