using System;
using UnityEditor;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    /// <summary>Real licensed Unity importer smoke-test, separate from Python QA.</summary>
    public static class AarisVehicleImportValidation
    {
        [MenuItem("Aaris/Validate 2km CC0 Vehicles")]
        public static void Run()
        {
            // Preserves the original 45 saved spawn-marker GameObjects,
            // four native TerrainData assets and the actual source scene.
            AarisExplorerBuild.ValidateSavedScene();
            string[] models =
            {
                "sedan", "suv", "sedan-sports",
                "hatchback-sports", "van", "truck-flat"
            };
            foreach (string name in models)
            {
                string path = "Assets/Resources/AarisVehicles/Models/" + name + ".fbx";
                GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (prefab == null)
                    throw new InvalidOperationException("Unity cannot import vendored CC0 model: " + name);
                if (Resources.Load<GameObject>("AarisVehicles/Models/" + name) == null)
                    throw new InvalidOperationException("Resources API failed: " + name);
                var meshes = prefab.GetComponentsInChildren<MeshFilter>(true);
                var skins = prefab.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                int triangles = 0;
                foreach (var filter in meshes)
                    if (filter.sharedMesh != null) triangles += filter.sharedMesh.triangles.Length / 3;
                foreach (var skin in skins)
                    if (skin.sharedMesh != null) triangles += skin.sharedMesh.triangles.Length / 3;
                if (triangles < 10 || triangles > 100000)
                    throw new InvalidOperationException("Bad model mesh triangle count: " + name + "=" + triangles);
                Debug.Log("AARIS_VEHICLE_IMPORT " + name + " triangles=" + triangles);
            }
            Texture2D palette = Resources.Load<Texture2D>("AarisVehicles/Models/colormap");
            if (palette == null || palette.width < 16 || palette.height < 16)
                throw new InvalidOperationException("Shared CC0 car palette texture missing.");
            if (Shader.Find("Universal Render Pipeline/Lit") == null)
                throw new InvalidOperationException("Missing URP Lit shader for car palette.");
            TextAsset points = Resources.Load<TextAsset>("AarisVehicles/vehicle_candidates");
            TextAsset catalog = Resources.Load<TextAsset>("AarisVehicles/vehicle_catalog");
            if (points == null || catalog == null ||
                !points.text.Contains("\"hubCount\": 45") ||
                !points.text.Contains("\"roadsideCount\": 33"))
                throw new InvalidOperationException("Authored 45+33 car locations not imported.");
            string[] scripts =
            {
                "AarisVehicleMotor", "AarisVehicleWorld",
                "AarisVehicleSession", "AarisVehicleHUD"
            };
            foreach (var name in scripts)
            {
                string path = "Assets/AarisWorld/Scripts/" + name + ".cs";
                var script = AssetDatabase.LoadAssetAtPath<MonoScript>(path);
                if (script == null || script.GetClass() == null)
                    throw new InvalidOperationException("C# script compilation missing: " + path);
            }
            Debug.Log("AARIS_VEHICLE_UNITY_IMPORT_PASS: 6 real local car models, palette, " +
                "4 scripts, 45 author markers + 33 roadside candidates.");
            Debug.LogWarning("VISUAL_QA_PENDING: wheel positions, animated wheels, road driving, " +
                "collision, camera, grip, terrain gradients and Android touch/FPS need Play mode.");
        }
    }
}
