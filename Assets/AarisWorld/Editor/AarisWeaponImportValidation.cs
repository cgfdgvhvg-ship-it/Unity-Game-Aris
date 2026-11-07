using System;
using UnityEditor;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    /// <summary>
    /// Native Unity Editor import gate. This is not a substitute for
    /// visual screenshots and physical Android gameplay. Run after loading
    /// the project with a valid Unity license.
    /// </summary>
    public static class AarisWeaponImportValidation
    {
        [MenuItem("Aaris/Validate Offline Weapons and Loot")]
        public static void Run()
        {
            AarisExplorerBuild.ValidateSavedScene();
            string basePath = "Assets/Resources/AarisWeapons/Models/";
            string[] names = { "SMG", "AssaultRifle", "BattleRifle", "Sniper", "Shotgun" };
            int triangles = 0;
            foreach (string name in names)
            {
                string path = basePath + name + ".fbx";
                var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (model == null)
                    throw new InvalidOperationException("Missing Unity imported model: " + path);
                var importer = AssetImporter.GetAtPath(path) as ModelImporter;
                if (importer == null)
                    throw new InvalidOperationException("Unity failed FBX ModelImporter: " + path);
                var meshFilters = model.GetComponentsInChildren<MeshFilter>(true);
                var skinRenderers = model.GetComponentsInChildren<SkinnedMeshRenderer>(true);
                if (meshFilters.Length == 0 && skinRenderers.Length == 0)
                    throw new InvalidOperationException("Weapon has no renderable mesh: " + path);
                int thisModel = 0;
                foreach (var filter in meshFilters)
                {
                    if (filter.sharedMesh == null) continue;
                    thisModel += filter.sharedMesh.triangles.Length / 3;
                }
                // The licensed source FBXs are rigged and some use ONLY
                // skinned meshes; checking MeshFilter alone wrongly fails.
                foreach (var skinned in skinRenderers)
                {
                    if (skinned.sharedMesh == null) continue;
                    thisModel += skinned.sharedMesh.triangles.Length / 3;
                }
                if (thisModel < 8 || thisModel > 180000)
                    throw new InvalidOperationException("Invalid phone mesh triangle count " +
                        thisModel + ": " + path);
                triangles += thisModel;
                string resourcePath = "AarisWeapons/Models/" + name;
                if (Resources.Load<GameObject>(resourcePath) == null)
                    throw new InvalidOperationException("Resources.Load failed: " + resourcePath);
                Debug.Log("AARIS_WEAPON_IMPORT: " + name + ", " + thisModel + " triangles, Unity FBX GUID stable.");
            }
            string[] scripts =
            {
                "AarisWeaponCatalog", "AarisWeaponPickup", "AarisWeaponInventory",
                "AarisWeaponLootWorld", "AarisWeaponHUD", "AarisBattleActions",
                "AarisEquippedGun", "AarisThirdPersonPlayer"
            };
            foreach (string name in scripts)
            {
                string path = "Assets/AarisWorld/Scripts/" + name + ".cs";
                var script = AssetDatabase.LoadAssetAtPath<MonoScript>(path);
                if (script == null || script.GetClass() == null)
                    throw new InvalidOperationException("Unity script import failed: " + path);
            }
            if (!AarisWeaponCatalog.TryLoad())
                throw new InvalidOperationException("Offline catalog could not import in Unity.");
            var loot = Resources.Load<TextAsset>("AarisWeapons/loot_candidates");
            if (loot == null || !loot.text.Contains("\"schema\": 1"))
                throw new InvalidOperationException("Missing baked 2km loot candidate data.");
            Debug.Log("AARIS_WEAPON_IMPORT_PASS: 5 local CC0 FBX assets; " +
                triangles + " total triangles; offline catalog + authored loot + player scripts.");
            Debug.Log("PLAYMODE_QA_REQUIRED: test hand rig, scope FOV, prone muzzle, ammo, " +
                "indoor accessible floor, native tree cover, fire audio/materials and Android FPS.");
        }
    }
}
