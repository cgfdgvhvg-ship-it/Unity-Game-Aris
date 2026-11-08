using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Unity.Collections;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace Aaris.MapReview.Editor
{
    // Editor-only, one-time asset baking. No runtime tree scripts, per-frame work,
    // duplicate tree instances, new renderer/materials, or additional triangles.
    // Never edits the original imported SpeedTree .st / TerrainData / scene.
    public static class AarisTreeMassSculpt
    {
        private const string Trees = "Assets/TerrainDemoScene_URP/Prefabs/Trees/";
        private const string Generated = "Assets/AarisWorld/Generated/TreeMass";
        private const string Output = "/tmp/aaris-codespaces/tree-mass";
        private struct Profile {
            public string id, prefab;
            public float trunk, leaf;
            public Profile(string i,string p,float t,float f) { id=i;prefab=p;trunk=t;leaf=f; }
        }
        private static readonly Profile[] Profiles = {
            new Profile("Conifer","Conifer/Conifer.prefab",0.26f,0.085f),
            new Profile("Cypress","Cypress/Cypress_Forest_Desktop.prefab",0.24f,0.080f),
            new Profile("Pine_A","Pines/Pine_A/Pine_A.prefab",0.18f,0.065f),
            new Profile("Pine_B","Pines/Pine_B/Pine_B.prefab",0.20f,0.070f),
            new Profile("Pine_C","Pines/Pine_C/Pine_C.prefab",0.12f,0.040f),
            new Profile("Pine_D","Pines/Pine_D/Pine_D.prefab",0.28f,0.090f)
        };
        [Serializable] private sealed class Record {
            public string species, prefab;
            public int generatedLods, sourceVertices, outputVertices;
            public int sourceTriangles, outputTriangles, barkVertices, foliageVertices;
            public float trunkFactor, foliageFactor;
        }
        [Serializable] private sealed class Report {
            public string status, reason, unityVersion;
            public int species, meshAssets, originalLods, generatedLods;
            public Record[] records;
        }

        private static int Root(int[] parents, int i) {
            while (parents[i]!=i) { parents[i]=parents[parents[i]]; i=parents[i]; }
            return i;
        }
        private static void Join(int[] parents, int a, int b) {
            a=Root(parents,a); b=Root(parents,b);
            if (a!=b) parents[b]=a;
        }

        private static Mesh Bake(Mesh original, Material[] materials, Profile profile,
                                 int lod, out int barkEdited, out int foliageEdited)
        {
            if (original == null || materials.Length!=original.subMeshCount ||
                original.blendShapeCount!=0 || original.vertexCount<16)
                throw new InvalidOperationException("UNSUPPORTED_SPEEDTREE_MESH");
            barkEdited=0; foliageEdited=0;
            int count=original.vertexCount;
            Vector3[] points=new Vector3[count];
            bool[] bark=new bool[count], leaves=new bool[count];
            int[] parents=Enumerable.Range(0,count).ToArray();
            Mesh baked=null;
            using (var read=Mesh.AcquireReadOnlyMeshData(original)) {
                var src=read[0];
                using (var buffer=new NativeArray<Vector3>(count,Allocator.Temp))
                    { src.GetVertices(buffer); buffer.CopyTo(points); }
                for(int sub=0;sub<original.subMeshCount;sub++) {
                    var section=src.GetSubMesh(sub);
                    if (section.topology!=MeshTopology.Triangles)
                        throw new InvalidOperationException("INVALID_SPEEDTREE_SUBMESH");
                    using (var indices=new NativeArray<int>((int)section.indexCount,Allocator.Temp)) {
                        src.GetIndices(indices,sub,true);
                        var mat=materials[sub];
                        if (!mat) throw new InvalidOperationException("TREE_MATERIAL_MISSING");
                        string n=mat.name.ToLowerInvariant();
                        bool isBark=n.Contains("bark") || n.Contains("cap");
                        bool isFoliage=!isBark && !n.Contains("billboard");
                        for (int i=0;i<indices.Length;i+=3) {
                            int a=indices[i], b=indices[i+1], c=indices[i+2];
                            if (a<0||b<0||c<0||a>=count||b>=count||c>=count)
                                throw new InvalidOperationException("TREE_INDEX_OUT_OF_BOUNDS");
                            if(isBark) { bark[a]=true; bark[b]=true; bark[c]=true; }
                            if(isFoliage) {
                                leaves[a]=true; leaves[b]=true; leaves[c]=true;
                                Join(parents,a,b); Join(parents,b,c);
                            }
                        }
                    }
                }
                // Copy raw vertex streams, all packed SpeedTree wind UVs/colors,
                // original indices and submesh descriptors byte-for-byte.
                var writable=Mesh.AllocateWritableMeshData(1);
                try {
                    var dst=writable[0];
                    dst.SetVertexBufferParams(count,original.GetVertexAttributes());
                    for(int stream=0;stream<original.vertexBufferCount;stream++){
                        var from=src.GetVertexData<byte>(stream);
                        var to=dst.GetVertexData<byte>(stream);
                        if(from.Length!=to.Length)
                            throw new InvalidOperationException("VERTEX_LAYOUT_CHANGED");
                        NativeArray<byte>.Copy(from,to,from.Length);
                    }
                    if(original.indexFormat==IndexFormat.UInt16){
                        var from=src.GetIndexData<ushort>();
                        dst.SetIndexBufferParams(from.Length,IndexFormat.UInt16);
                        NativeArray<ushort>.Copy(from,dst.GetIndexData<ushort>(),from.Length);
                    }else{
                        var from=src.GetIndexData<uint>();
                        dst.SetIndexBufferParams(from.Length,IndexFormat.UInt32);
                        NativeArray<uint>.Copy(from,dst.GetIndexData<uint>(),from.Length);
                    }
                    dst.subMeshCount=original.subMeshCount;
                    for(int s=0;s<original.subMeshCount;s++)
                        dst.SetSubMesh(s,src.GetSubMesh(s),MeshUpdateFlags.DontRecalculateBounds);
                    baked=new Mesh();
                    Mesh.ApplyAndDisposeWritableMeshData(writable,baked,
                        MeshUpdateFlags.DontRecalculateBounds|MeshUpdateFlags.DontValidateIndices);
                    writable=default(Mesh.MeshDataArray);
                }
                finally { if(writable.Length>0) writable.Dispose(); }
            }

            Bounds bounds=original.bounds;
            float minY=bounds.min.y, height=Mathf.Max(.01f,bounds.size.y);
            // The trunk axis comes from the lower bark vertices, not the
            // geometric midpoint of an asymmetric crown.
            float cx=0f,cz=0f;int bases=0;
            for(int i=0;i<count;i++) if(bark[i]&&!leaves[i] &&
                       points[i].y<=minY+0.18f*height) {
                cx+=points[i].x;cz+=points[i].z;bases++;
            }
            if(bases<4) throw new InvalidOperationException("TRUNK_BASE_NOT_IDENTIFIED");
            cx/=bases;cz/=bases;
            float trunkGain=profile.trunk*(lod==0?1f:lod==1?0.94f:0.88f);
            for(int i=0;i<count;i++) if(bark[i]&&!leaves[i]) {
                float fraction=Mathf.Clamp01((points[i].y-minY)/height);
                float t=Mathf.Clamp01(1f-fraction/0.68f);
                float blend=t*t*(3f-2f*t);
                if(blend<.0001f)continue;
                var pos=points[i];
                pos.x=cx+(pos.x-cx)*(1f+trunkGain*blend);
                pos.z=cz+(pos.z-cz)*(1f+trunkGain*blend);
                points[i]=pos;barkEdited++;
            }

            // Individual existing connected leaf cards expand around THEIR OWN
            // centroids. This fills gaps without adding a single triangle/card.
            // Large welded clusters and shared bark vertices are left intact.
            int[] counts=new int[count];
            Vector3[] centers=new Vector3[count];
            for(int i=0;i<count;i++) if(leaves[i]&&!bark[i]) {
                int root=Root(parents,i);counts[root]++;centers[root]+=points[i];
            }
            float leafGain=profile.leaf*(lod==0?1f:lod==1?.85f:.70f);
            for(int i=0;i<count;i++) if(leaves[i]&&!bark[i]) {
                int root=Root(parents,i);
                if(counts[root]<3||counts[root]>24)continue;
                Vector3 center=centers[root]/counts[root];
                Vector3 offset=points[i]-center;
                Vector3 next=center+new Vector3(offset.x*(1f+leafGain),
                    offset.y*(1f+leafGain*0.35f),offset.z*(1f+leafGain));
                // Do not enlarge the original full-tree envelope or height.
                next.x=Mathf.Clamp(next.x,bounds.min.x,bounds.max.x);
                next.y=Mathf.Clamp(next.y,bounds.min.y,bounds.max.y);
                next.z=Mathf.Clamp(next.z,bounds.min.z,bounds.max.z);
                if((next-points[i]).sqrMagnitude>0.000001f)
                    {points[i]=next;foliageEdited++;}
            }
            if(barkEdited<10||foliageEdited<12)
                throw new InvalidOperationException("INSUFFICIENT_BARK_OR_LEAF_COMPONENTS");
            baked.SetVertices(points);
            baked.bounds=bounds;
            if(baked.vertexCount!=original.vertexCount ||
               baked.subMeshCount!=original.subMeshCount)
                throw new InvalidOperationException("TREE_VERTEX_OR_SUBMESH_BUDGET_CHANGED");
            for(int sub=0;sub<original.subMeshCount;sub++)
                if(baked.GetIndexCount(sub)!=original.GetIndexCount(sub))
                    throw new InvalidOperationException("TREE_TRIANGLE_BUDGET_CHANGED");
            baked.name=profile.id+"_Mass_LOD"+lod;
            return baked;
        }

        [MenuItem("Aaris/CI/Apply safe native tree mass and render")]
        public static void ApplyAndPreview()
        {
            Directory.CreateDirectory(Output);
            var report=new Report {status="failed",reason="NOT_STARTED",unityVersion=Application.unityVersion};
            var records=new List<Record>();
            try {
                if(AssetDatabase.IsValidFolder(Generated))
                    throw new InvalidOperationException("TREE_MASS_GENERATED_OUTPUT_ALREADY_EXISTS");
                if(!AssetDatabase.IsValidFolder("Assets/AarisWorld/Generated"))
                    AssetDatabase.CreateFolder("Assets/AarisWorld","Generated");
                AssetDatabase.CreateFolder("Assets/AarisWorld/Generated","TreeMass");
                foreach(var profile in Profiles){
                    string prefabPath=Trees+profile.prefab;
                    GameObject root=PrefabUtility.LoadPrefabContents(prefabPath);
                    if(root==null)throw new InvalidOperationException("TREE_SOURCE_PREFAB_MISSING");
                    try{
                        LODGroup group=root.GetComponent<LODGroup>();
                        BoxCollider collider=root.GetComponent<BoxCollider>();
                        if(group==null||group.lodCount!=4||collider==null)
                            throw new InvalidOperationException("TREE_PROTOTYPE_STRUCTURE_CHANGED");
                        var record=new Record{species=profile.id,prefab=prefabPath,
                            trunkFactor=profile.trunk,foliageFactor=profile.leaf};
                        LOD[] lods=group.GetLODs();
                        for(int i=0;i<3;i++){
                            if(lods[i].renderers.Length!=1)
                                throw new InvalidOperationException("TREE_RENDERER_BUDGET_CHANGED");
                            MeshRenderer renderer=lods[i].renderers[0] as MeshRenderer;
                            MeshFilter filter=renderer?renderer.GetComponent<MeshFilter>():null;
                            if(filter==null||filter.sharedMesh==null)
                                throw new InvalidOperationException("TREE_SOURCE_MESH_MISSING");
                            Mesh source=filter.sharedMesh;
                            int bark,foliage;
                            Mesh result=Bake(source,renderer.sharedMaterials,profile,i,out bark,out foliage);
                            string target=Generated+"/"+profile.id+"_LOD"+i+".asset";
                            AssetDatabase.CreateAsset(result,target);
                            filter.sharedMesh=result;
                            record.generatedLods++;
                            record.sourceVertices+=source.vertexCount;
                            record.outputVertices+=result.vertexCount;
                            record.barkVertices+=bark;
                            record.foliageVertices+=foliage;
                            for(int s=0;s<source.subMeshCount;s++){
                                record.sourceTriangles+=(int)source.GetIndexCount(s)/3;
                                record.outputTriangles+=(int)result.GetIndexCount(s)/3;
                            }
                        }
                        // Physical trunk width follows the modified lower bark.
                        // One BoxCollider per prefab: same physics object budget.
                        Vector3 size=collider.size;
                        size.x*=1f+profile.trunk*0.70f;
                        size.z*=1f+profile.trunk*0.70f;
                        collider.size=size;
                        if(record.generatedLods!=3 ||
                           record.sourceVertices!=record.outputVertices ||
                           record.sourceTriangles!=record.outputTriangles)
                            throw new InvalidOperationException("TREE_GEOMETRY_BUDGET_FAILURE");
                        PrefabUtility.SaveAsPrefabAsset(root,prefabPath);
                        report.meshAssets+=3;report.generatedLods+=3;
                        report.originalLods+=4;
                        records.Add(record);
                    }
                    finally{PrefabUtility.UnloadPrefabContents(root);}
                }
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
                report.records=records.ToArray();
                report.species=records.Count;
                if(report.species!=6||report.meshAssets!=18||report.originalLods!=24)
                    throw new InvalidOperationException("TREE_COUNT_OR_LOD_STRUCTURE_CHANGED");
                report.status="passed";
                report.reason="TREE_MASS_SCULPT_GENERATED_AND_BUDGET_VERIFIED";
                // Native scene cameras read new prefab meshes from this worktree.
                AarisCodespaceSceneProbe.DiagnoseFoliage();
                Debug.Log("AARIS_NATIVE_TREE_MASS_PREVIEW_PASSED");
            }
            catch(Exception e){
                report.status="failed";
                report.reason=e is InvalidOperationException?e.Message:e.GetType().Name;
                Debug.LogError("AARIS_NATIVE_TREE_MASS_PREVIEW_FAILED:"+report.reason);
                throw;
            }
            finally{
                report.records=records.ToArray();
                File.WriteAllText(Path.Combine(Output,"mass-report.json"),
                    JsonUtility.ToJson(report,true));
            }
        }
    }
}
