using System;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    // Editor-only offline asset audit: tests the resources consumed by the actual runtime.
    [InitializeOnLoad]
    public static class AarisMotionAndIceAssetAudit
    {
        private const string Request = "/tmp/aaris-codespaces/check-motion-ice-assets.request";
        private const string Result = "/tmp/aaris-codespaces/motion-ice-assets.txt";

        static AarisMotionAndIceAssetAudit()
        {
            EditorApplication.delayCall += () =>
            {
                if (File.Exists(Request) && !EditorApplication.isPlayingOrWillChangePlaymode)
                {
                    File.Delete(Request);
                    Inspect();
                }
            };
        }

        [MenuItem("Aaris/Review/Audit Humanoid Clips And Curved Ice")]
        public static void Inspect()
        {
            string[] motion = { "idle", "walk", "run", "sprint", "jump", "jump_start",
                "jump_land", "crouch", "crouch_walk", "prone", "crawl", "punch", "shoot" };
            int valid = 0;
            var log = new StringBuilder("AARIS_MOTION_ICE_AUDIT\n");
            foreach (string name in motion)
            {
                var clips = Resources.LoadAll<AnimationClip>(
                    "AarisCharacters/Primary/Animations/" + name);
                bool found = false;
                foreach (var clip in clips)
                    if (clip != null && clip.humanMotion && !clip.legacy && clip.length > .02f)
                    {
                        log.AppendLine("CLIP " + name + " OK seconds=" + clip.length.ToString("F3")
                            + " imported=" + clip.name);
                        valid++;
                        found = true;
                        break;
                    }
                if (!found) log.AppendLine("CLIP " + name + " MISSING_VALID_HUMANOID");
            }
            var avatarPrefab = Resources.Load<GameObject>("AarisCharacters/Primary/Player");
            var avatarComponent = avatarPrefab != null ?
                avatarPrefab.GetComponentInChildren<Animator>(true) : null;
            log.AppendLine("PLAYER_AVATAR " +
                (avatarComponent != null && avatarComponent.avatar != null &&
                 avatarComponent.avatar.isValid && avatarComponent.avatar.isHuman));
            var wall = Resources.Load<GameObject>("AarisCombat/GlooWall");
            var ice = Resources.Load<Material>("AarisCombat/Materials/GlooWall-ArcticBlue");
            var frost = Resources.Load<Material>("AarisCombat/Materials/GlooWall-FrostHighlight");
            int submeshes = 0;
            if (wall != null)
                foreach (var filter in wall.GetComponentsInChildren<MeshFilter>(true))
                    if (filter.sharedMesh != null)
                        submeshes += filter.sharedMesh.subMeshCount;
            log.AppendLine("CURVED_ICE mesh=" + (wall != null) + " submeshes=" + submeshes +
                " blue=" + (ice != null) + " frost=" + (frost != null));
            bool passed = valid == motion.Length && wall != null &&
                ice != null && frost != null && submeshes >= 2;
            log.AppendLine("RESULT " + (passed ? "PASS" : "FAIL") + " " + valid +
                "/" + motion.Length);
            Directory.CreateDirectory(Path.GetDirectoryName(Result));
            File.WriteAllText(Result, log.ToString());
            if (passed) Debug.Log("AARIS_MOTION_ICE_AUDIT_PASS");
            else Debug.LogError("AARIS_MOTION_ICE_AUDIT_FAIL");
        }
    }
}
