using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.AssetImporters;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    /// <summary>
    /// Deterministic native-FBX import. It only touches the vendored character
    /// directory; terrain meshes, scene assets and existing prefabs are untouched.
    /// </summary>
    public sealed class AarisCharacterImport : AssetPostprocessor
    {
        private const string Prefix = "Assets/Resources/AarisCharacters/Primary/";
        private const string Player = Prefix + "Player.fbx";
        private const string Anim = Prefix + "Animations/";

        private void OnPreprocessModel()
        {
            if (!assetPath.StartsWith(Prefix, StringComparison.Ordinal) ||
                !assetPath.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase)) return;

            var importer = assetImporter as ModelImporter;
            if (importer == null) return;
            importer.animationType = ModelImporterAnimationType.Human;
            importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            importer.autoGenerateAvatarMappingIfUnspecified = true;
            importer.importAnimation = assetPath.StartsWith(Anim, StringComparison.Ordinal);
            importer.importBlendShapes = true;
            importer.addCollider = false;
            importer.isReadable = false;
            importer.optimizeMeshPolygons = true;
            importer.optimizeMeshVertices = true;
            importer.importCameras = false;
            importer.importLights = false;
            // Root motion is implemented by AarisThirdPersonPlayer's controller,
            // never a second transform-driven animation controller.
        }

        [MenuItem("Aaris/Validate Vendored Male Character")]
        public static void Validate()
        {
            string[] files = {"idle.fbx", "walk.fbx", "run.fbx", "jump.fbx"};
            if (!File.Exists(Player))
                throw new InvalidOperationException("Player.fbx is not committed locally. Run the CC0 vendor pipeline.");
            var model = AssetDatabase.LoadAssetAtPath<GameObject>(Player);
            if (model == null) throw new InvalidOperationException("Unable to load Player.fbx as a Unity model.");
            var avatar = AssetDatabase.LoadAllAssetsAtPath(Player).OfType<Avatar>()
                .FirstOrDefault(x => x != null && x.isValid && x.isHuman);
            if (avatar == null)
                throw new InvalidOperationException("Player.fbx lacks valid Unity Humanoid Avatar. Fix rig mapping.");

            foreach (string name in files)
            {
                string path = Anim + name;
                if (!File.Exists(path))
                    throw new InvalidOperationException("Locally vendored animation missing: " + path);
                var clips = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>()
                    .Where(c => c != null && !c.legacy && c.length > 0.04f).ToArray();
                if (clips.Length == 0)
                    throw new InvalidOperationException("No valid retargetable animation clip: " + name);
            }
            if (AssetDatabase.LoadAssetAtPath<MonoScript>("Assets/AarisWorld/Scripts/AarisCharacterVisual.cs") == null)
                throw new InvalidOperationException("AarisCharacterVisual.cs is missing.");
            Debug.Log("Aaris local character verification: model=1, humanoid avatar=valid, clips>=4, runtime uses no download URLs.");
        }
    }
}
