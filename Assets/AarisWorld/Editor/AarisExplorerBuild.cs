using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    public sealed class AarisExplorerBuild : IPreprocessBuildWithReport
    {
        public const string ScenePath = "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity";
        public int callbackOrder => 0;

        public void OnPreprocessBuild(BuildReport report) { Configure(); ValidateSavedScene(); }

        [MenuItem("Aaris/Build Android Map Explorer APK")]
        public static void BuildAndroid()
        {
            Configure();
            EditorUserBuildSettings.buildAppBundle = false;
            Build("Builds/Android/AarisMapExplorer.apk", BuildTarget.Android);
        }

        [MenuItem("Aaris/Build Web Map Explorer")]
        public static void BuildWebGL() { Configure(); Build("Builds/WebGL", BuildTarget.WebGL); }

        public static void Configure()
        {
            PlayerSettings.companyName = "Aaris";
            PlayerSettings.productName = "Aaris Map Explorer";
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.AutoRotation;
            PlayerSettings.allowedAutorotateToLandscapeLeft = true;
            PlayerSettings.allowedAutorotateToLandscapeRight = true;
            PlayerSettings.allowedAutorotateToPortrait = false;
            PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
            PlayerSettings.SetApplicationIdentifier(UnityEditor.Build.NamedBuildTarget.Android, "com.aaris.mapexplorer");
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel26;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
            PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
            // The review UI uses the built-in Input API; no Input Actions asset is required.
            UnityEngine.Object[] settings = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset");
            if (settings.Length > 0)
            {
                var serialized = new SerializedObject(settings[0]);
                var input = serialized.FindProperty("activeInputHandler");
                if (input != null) { input.intValue = 0; serialized.ApplyModifiedPropertiesWithoutUndo(); }
            }
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
        }

        public static void ValidateSavedScene()
        {
            var scene = EditorSceneManager.OpenScene(ScenePath, OpenSceneMode.Single);
            var camera = UnityEngine.Object.FindFirstObjectByType<AarisMapExplorer>();
            if (camera == null || !camera.enabled || camera.GetComponent<Camera>() == null)
                throw new BuildFailedException("The saved review scene must have an enabled AarisMapExplorer camera.");
            var terrains = UnityEngine.Object.FindObjectsByType<Terrain>(FindObjectsSortMode.None);
            if (terrains.Length != 4 || terrains.Any(t => t.terrainData == null))
                throw new BuildFailedException("Expected the four saved 1km TerrainData tiles; check Git LFS downloads.");
            var spawns = UnityEngine.Object.FindObjectsByType<Transform>(FindObjectsSortMode.None)
                .Count(t => t.parent != null && t.parent.name == "VehicleSpawns"
                    && t.name.StartsWith("VehicleSpawnPoint_", StringComparison.Ordinal));
            if (spawns != 45) throw new BuildFailedException("Expected all 45 empty vehicle spawn markers.");
            foreach (var root in scene.GetRootGameObjects())
                foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                    if (GameObjectUtility.GetMonoBehavioursWithMissingScriptCount(transform.gameObject) != 0)
                        throw new BuildFailedException("Missing script on " + transform.name);
            Debug.Log("Aaris explorer verified: camera, four terrains, 45 markers, no missing scene scripts.");
        }

        private static void Build(string path, BuildTarget target)
        {
            ValidateSavedScene();
            Directory.CreateDirectory(target == BuildTarget.Android ? Path.GetDirectoryName(path) : path);
            BuildReport report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { ScenePath }, locationPathName = path, target = target, options = BuildOptions.None
            });
            if (report.summary.result != BuildResult.Succeeded)
                throw new BuildFailedException("Map explorer build failed: " + report.summary.result);
            Debug.Log("Aaris map explorer built: " + report.summary.outputPath);
        }
    }
}
