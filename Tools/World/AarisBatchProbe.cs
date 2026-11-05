// Temporary scratch-copy only. Never place this script in original project's Assets.
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class AarisBatchProbe
{
    [Serializable]
    private class Readback
    {
        public string projectVersion;
        public string scenePath;
        public bool sceneValid;
        public bool sceneLoaded;
        public int rootObjects;
        public int terrainComponents;
        public int terrainTreeInstances;
        public int prefabAssets;
        public int materialAssets;
        public string[] rootNames;
        public string timestampUtc;
    }

    public static void OpenMapAndAudit()
    {
        const string scenePath = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity";
        string output = Environment.GetEnvironmentVariable("AARIS_BATCH_REPORT");
        if (String.IsNullOrEmpty(output)) throw new Exception("Missing AARIS_BATCH_REPORT");
        if (AssetDatabase.LoadAssetAtPath<SceneAsset>(scenePath) == null) throw new Exception("Scene asset not imported: " + scenePath);
        var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
        if (!scene.IsValid() || !scene.isLoaded) throw new Exception("Scene not loaded");
        var roots = scene.GetRootGameObjects();
        int trees = 0;
        var terrains = UnityEngine.Object.FindObjectsByType<Terrain>(FindObjectsSortMode.None);
        foreach (var t in terrains)
            if (t && t.terrainData) trees += t.terrainData.treeInstanceCount;
        var names = new string[Math.Min(roots.Length, 25)];
        for (int i = 0; i < names.Length; i++) names[i] = roots[i].name;
        var report = new Readback {
            projectVersion = Application.unityVersion,
            scenePath = scene.path,
            sceneValid = scene.IsValid(),
            sceneLoaded = scene.isLoaded,
            rootObjects = roots.Length,
            terrainComponents = terrains.Length,
            terrainTreeInstances = trees,
            prefabAssets = AssetDatabase.FindAssets("t:Prefab", new[]{"Assets"}).Length,
            materialAssets = AssetDatabase.FindAssets("t:Material", new[]{"Assets"}).Length,
            rootNames = names,
            timestampUtc = DateTime.UtcNow.ToString("o")
        };
        File.WriteAllText(output, JsonUtility.ToJson(report, true));
        Debug.Log("AARIS_BATCH_MAP_OPENED " + scene.path + " terrain=" + terrains.Length +
                  " treeInstances=" + trees + " roots=" + roots.Length);
    }
}
