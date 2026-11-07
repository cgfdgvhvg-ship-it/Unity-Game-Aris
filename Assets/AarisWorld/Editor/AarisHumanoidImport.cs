using System;
using UnityEditor;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    /// <summary>
    /// Import Kenney's externally authored rig and motions as Humanoid so the
    /// runtime Playables bridge can retarget them without manual GUI setup.
    /// Import occurs on normal Unity project import, including batchmode.
    /// </summary>
    public sealed class AarisHumanoidImport : AssetPostprocessor
    {
        private const string Folder = "Assets/Resources/AarisCharacters/Kenney/";
        private const string Rig = Folder + "characterMedium.fbx";

        private void OnPreprocessModel()
        {
            if (!assetPath.StartsWith(Folder, StringComparison.OrdinalIgnoreCase)
                || !assetPath.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase))
                return;

            var model = assetImporter as ModelImporter;
            if (model == null) return;

            model.animationType = ModelImporterAnimationType.Human;
            model.importAnimation = true;
            if (assetPath.Equals(Rig, StringComparison.OrdinalIgnoreCase))
            {
                model.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            }
            else
            {
                Avatar source = null;
                foreach (UnityEngine.Object obj in AssetDatabase.LoadAllAssetsAtPath(Rig))
                {
                    if (obj is Avatar avatar && avatar.isValid && avatar.isHuman)
                    {
                        source = avatar;
                        break;
                    }
                }

                if (source != null)
                {
                    model.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                    model.sourceAvatar = source;
                }
                else
                {
                    // The main model might be importing in the same AssetDatabase
                    // refresh. Do not silently claim an animation-only rig works.
                    model.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                    Debug.LogWarning("Aaris: import characterMedium.fbx first, then reimport animation: " + assetPath);
                }

                ModelImporterClipAnimation[] clips = model.defaultClipAnimations;
                bool loop = assetPath.EndsWith("/idle.fbx", StringComparison.OrdinalIgnoreCase)
                    || assetPath.EndsWith("/run.fbx", StringComparison.OrdinalIgnoreCase);
                foreach (var clip in clips)
                {
                    clip.loopTime = loop;
                    clip.loopPose = loop;
                    clip.lockRootRotation = true;
                    clip.lockRootHeightY = true;
                    clip.lockRootPositionXZ = true;
                }
                if (clips.Length > 0)
                    model.clipAnimations = clips;
            }
        }
    }
}
