using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    // Editor-only physics check on genuine native prefabs. Isolated worktree,
    // temporary unsaved empty scene; never edits main scene, native meshes or LFS.
    public static class AarisTreeColliderProbe
    {
        const string Prefix = "Assets/TerrainDemoScene_URP/Prefabs/Trees/";
        const string Output = "/tmp/aaris-codespaces/tree-pr-photo/pr-collider-report.json";

        struct Candidate
        {
            public string Name, Relative;
            public float Width;
            public Candidate(string name, string relative, float width)
            {
                Name = name; Relative = relative; Width = width;
            }
        }

        static readonly Candidate[] Targets = {
            new Candidate("Pine_A", "Pines/Pine_A/Pine_A.prefab", 1.43f),
            new Candidate("Pine_B", "Pines/Pine_B/Pine_B.prefab", 1.45f),
            new Candidate("Pine_C", "Pines/Pine_C/Pine_C.prefab", 1.40f),
        };

        [Serializable] class Result
        {
            public string species;
            public int lods, colliders;
            public float rootX, rootY, rootZ;
            public float trunkCollisionWidth, trunkCollisionDepth;
            public float crownWidth, crownDepth;
            public bool standingHeightRaycastHit;
        }

        [Serializable] class Report
        {
            public string status = "failed";
            public string reason = "NOT_STARTED";
            public string unityVersion;
            public int speciesCount;
            public Result[] trees;
        }

        [MenuItem("Aaris/CI/Verify Pine cover colliders with native Physics.Raycast")]
        public static void Inspect()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Output));
            var report = new Report { unityVersion = Application.unityVersion };
            var rows = new List<Result>();
            try
            {
                EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                foreach (Candidate target in Targets)
                {
                    GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(Prefix + target.Relative);
                    if (prefab == null)
                        throw new InvalidOperationException("TRUNK_PREFAB_MISSING");

                    GameObject copy = PrefabUtility.InstantiatePrefab(prefab) as GameObject;
                    if (copy == null)
                        throw new InvalidOperationException("TRUNK_INSTANCE_MISSING");
                    try
                    {
                        copy.transform.SetPositionAndRotation(Vector3.zero, Quaternion.identity);
                        Vector3 scale = copy.transform.localScale;
                        if (Mathf.Abs(scale.x - target.Width) > .001f ||
                            Mathf.Abs(scale.z - target.Width) > .001f)
                            throw new InvalidOperationException("TRUNK_SCALE_MISMATCH");

                        var lodGroup = copy.GetComponent<LODGroup>();
                        if (lodGroup == null || lodGroup.lodCount != 4)
                            throw new InvalidOperationException("TREE_LODS_CHANGED");
                        var colliders = copy.GetComponentsInChildren<Collider>(true);
                        if (colliders.Length != 1 ||
                            !(colliders[0] is BoxCollider) ||
                            !colliders[0].enabled ||
                            colliders[0].isTrigger)
                            throw new InvalidOperationException("TRUNK_COLLIDER_STRUCTURE_INVALID");
                        var box = (BoxCollider)colliders[0];
                        Physics.SyncTransforms();
                        Bounds physical = box.bounds;
                        if (physical.size.x < 1.45f || physical.size.x > 2.25f ||
                            physical.size.z < 1.45f || physical.size.z > 3.0f ||
                            physical.min.y > 1.8f || physical.max.y < 1.8f)
                            throw new InvalidOperationException("TRUNK_COLLIDER_COVER_INVALID");

                        LOD[] lods = lodGroup.GetLODs();
                        if (lods[0].renderers.Length != 1 ||
                            !(lods[0].renderers[0] is MeshRenderer))
                            throw new InvalidOperationException("TRUNK_LOD_RENDERER_INVALID");
                        var visual = (MeshRenderer)lods[0].renderers[0];
                        Bounds crown = visual.bounds;
                        if (crown.size.x <= physical.size.x * 1.6f ||
                            crown.size.z <= physical.size.z * 1.6f)
                            throw new InvalidOperationException("TRUNK_CROWN_BUDGET_INVALID");

                        Vector3 start = new Vector3(physical.center.x, 1.8f,
                                                   physical.min.z - 2f);
                        RaycastHit hit;
                        bool hitTrunk = Physics.Raycast(
                            start, Vector3.forward, out hit, physical.size.z + 4f,
                            ~0, QueryTriggerInteraction.Ignore)
                            && hit.collider == box;
                        if (!hitTrunk)
                            throw new InvalidOperationException("TRUNK_PHYSICS_RAYCAST_FAILED");

                        rows.Add(new Result {
                            species = target.Name, lods = lodGroup.lodCount,
                            colliders = colliders.Length,
                            rootX = scale.x, rootY = scale.y, rootZ = scale.z,
                            trunkCollisionWidth = physical.size.x,
                            trunkCollisionDepth = physical.size.z,
                            crownWidth = crown.size.x, crownDepth = crown.size.z,
                            standingHeightRaycastHit = hitTrunk
                        });
                    }
                    finally { UnityEngine.Object.DestroyImmediate(copy); }
                }
                report.speciesCount = rows.Count;
                if (rows.Count != 3)
                    throw new InvalidOperationException("TRUNK_SPECIES_COUNT_MISMATCH");
                report.status = "passed";
                report.reason = "PR_NATIVE_COLLIDERS_LODS_RAYCAST_PASSED";
                Debug.Log("AARIS_PR_NATIVE_TREE_COLLIDERS_PASSED");
            }
            catch (Exception e)
            {
                report.reason = e is InvalidOperationException
                    ? e.Message : e.GetType().Name;
                Debug.LogError("AARIS_PR_NATIVE_TREE_COLLIDERS_FAILED:" + report.reason);
                throw;
            }
            finally
            {
                report.trees = rows.ToArray();
                File.WriteAllText(Output, JsonUtility.ToJson(report, true));
            }
        }
    }
}
