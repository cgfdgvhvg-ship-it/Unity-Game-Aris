using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace Aaris.MapReview.Editor
{
    // Safe first pass: native source import inspection. Never mutates prefabs,
    // SpeedTree .st meshes, TerrainData, scenes, material or any existing .meta.
    public static class AarisTreeMassAudit
    {
        private const string Root = "Assets/TerrainDemoScene_URP/Prefabs/Trees/";
        private const string Output = "/tmp/aaris-codespaces/tree-mass/audit.json";
        private static readonly string[] Species = {
            "Conifer/Conifer.prefab",
            "Cypress/Cypress_Forest_Desktop.prefab",
            "Pines/Pine_A/Pine_A.prefab",
            "Pines/Pine_B/Pine_B.prefab",
            "Pines/Pine_C/Pine_C.prefab",
            "Pines/Pine_D/Pine_D.prefab"
        };

        [Serializable] public class SubMeshInfo {
            public int index, indices;
            public string material, topology;
        }
        [Serializable] public class LodInfo {
            public string name;
            public int vertices, triangles, subMeshes;
            public bool readable;
            public float height, width, depth;
            public SubMeshInfo[] sections;
        }
        [Serializable] public class SpeciesInfo {
            public string path, prefabGuid;
            public float rootX, rootY, rootZ;
            public int colliders, lodCount;
            public LodInfo[] lods;
        }
        [Serializable] public class Report {
            public string status, editorVersion, reason;
            public int treeCount, speciesCount;
            public SpeciesInfo[] species;
        }

        [MenuItem("Aaris/CI/Audit native SpeedTree mesh mass")]
        public static void Inspect()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Output));
            var report = new Report { status="failed", editorVersion=Application.unityVersion, reason="INCOMPLETE" };
            try {
                var list = new List<SpeciesInfo>();
                foreach (var relative in Species) {
                    var path = Root + relative;
                    GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                    if (prefab == null) throw new InvalidOperationException("TREE_PREFAB_MISSING");
                    var root = prefab.transform.localScale;
                    var lodGroup = prefab.GetComponent<LODGroup>();
                    if (lodGroup == null || lodGroup.lodCount != 4)
                        throw new InvalidOperationException("TREE_LOD_GROUP_INVALID");
                    var info = new SpeciesInfo {
                        path=path, prefabGuid=AssetDatabase.AssetPathToGUID(path),
                        rootX=root.x, rootY=root.y, rootZ=root.z,
                        lodCount=lodGroup.lodCount,
                        colliders=prefab.GetComponentsInChildren<Collider>(true).Length
                    };
                    var lods = new List<LodInfo>();
                    foreach (var lod in lodGroup.GetLODs()) {
                        if (lod.renderers.Length != 1 || !(lod.renderers[0] is MeshRenderer))
                            throw new InvalidOperationException("TREE_LOD_RENDERERS_UNEXPECTED");
                        var renderer = (MeshRenderer)lod.renderers[0];
                        MeshFilter filter = renderer.GetComponent<MeshFilter>();
                        Mesh mesh = filter != null ? filter.sharedMesh : null;
                        if (mesh == null) throw new InvalidOperationException("TREE_MESH_MISSING");
                        var materials = renderer.sharedMaterials;
                        if (mesh.subMeshCount != materials.Length)
                            throw new InvalidOperationException("TREE_SUBMESH_MATERIAL_MISMATCH");
                        var sections = new List<SubMeshInfo>();
                        int triangles = 0;
                        for (int i=0; i<mesh.subMeshCount; i++) {
                            var sub = mesh.GetSubMesh(i);
                            if (sub.topology != MeshTopology.Triangles)
                                throw new InvalidOperationException("TREE_TOPOLOGY_UNSUPPORTED");
                            triangles += (int)sub.indexCount / 3;
                            sections.Add(new SubMeshInfo {
                                index=i, indices=(int)sub.indexCount,
                                material=materials[i] ? materials[i].name : "NONE",
                                topology=sub.topology.ToString()
                            });
                        }
                        lods.Add(new LodInfo {
                            name=renderer.name, vertices=mesh.vertexCount,
                            triangles=triangles, subMeshes=mesh.subMeshCount,
                            readable=mesh.isReadable,
                            width=mesh.bounds.size.x,
                            height=mesh.bounds.size.y,
                            depth=mesh.bounds.size.z,
                            sections=sections.ToArray()
                        });
                    }
                    info.lods=lods.ToArray();
                    list.Add(info);
                }
                report.species=list.ToArray();
                report.speciesCount=list.Count;
                if (list.Count!=6) throw new InvalidOperationException("SPECIES_COUNT_CHANGED");
                report.status="passed";
                report.reason="NATIVE_SPEEDTREE_MESH_TOPOLOGY_AUDITED";
                Debug.Log("AARIS_TREE_MASS_AUDIT_PASSED");
            }
            catch (Exception e) {
                report.reason=e is InvalidOperationException ? e.Message : e.GetType().Name;
                Debug.LogError("AARIS_TREE_MASS_AUDIT_FAILED:" + report.reason);
                throw;
            }
            finally {
                File.WriteAllText(Output, JsonUtility.ToJson(report, true));
            }
        }
    }
}
