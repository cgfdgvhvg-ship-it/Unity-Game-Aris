using System;
using System.IO;
using Unity.Collections;
using UnityEditor;
using UnityEngine;
namespace Aaris.MapReview.Editor {
[InitializeOnLoad] public static class AarisRoadClearanceAudit {
const string Marker="/tmp/aaris-codespaces/run-road-audit";
static AarisRoadClearanceAudit() {
 EditorApplication.delayCall += () => {
  if (!EditorApplication.isPlayingOrWillChangePlaymode && File.Exists(Marker)) {
   File.Delete(Marker); Audit();
  }
 };
}
[MenuItem("Aaris/Review/Audit Road Clearance")]
public static void Audit() {
 var root=GameObject.Find("RoadNetwork");
 var tiles=Terrain.activeTerrains;
 if(root==null || tiles.Length!=4) {Debug.LogError("AARIS_ROAD_AUDIT_SCENE_REQUIRED");return;}
 int roads=0, samples=0, hidden=0, shallow=0; float min=float.PositiveInfinity, max=float.NegativeInfinity;
 foreach(var filter in root.GetComponentsInChildren<MeshFilter>(true)) {
  if(filter.name.EndsWith("_Markings",StringComparison.Ordinal)||filter.sharedMesh==null)continue;
  roads++;
  using(var data=Mesh.AcquireReadOnlyMeshData(filter.sharedMesh))
  using(var verts=new NativeArray<Vector3>(data[0].vertexCount,Allocator.Temp))
  using(var indices=new NativeArray<int>(data[0].GetSubMesh(0).indexCount,Allocator.Temp)) {
   data[0].GetVertices(verts);data[0].GetIndices(indices,0);
   for(int i=0;i+2<indices.Length;i+=3) {
    var a=filter.transform.TransformPoint(verts[indices[i]]);
    var b=filter.transform.TransformPoint(verts[indices[i+1]]);
    var c=filter.transform.TransformPoint(verts[indices[i+2]]);
    foreach(float w in new float[]{.33f,.1f,.65f}) {
     var p=a*w+b*(1f-w)*.5f+c*(1f-w)*.5f;
     foreach(var t in tiles) {
      if(t==null||t.terrainData==null) continue;
      var o=t.transform.position;var size=t.terrainData.size;
      if(p.x<o.x||p.z<o.z||p.x>o.x+size.x||p.z>o.z+size.z)continue;
      float gap=p.y-(t.SampleHeight(p)+o.y);samples++;
      min=Mathf.Min(min,gap);max=Mathf.Max(max,gap);
      if(gap<0f)hidden++;if(gap<.05f)shallow++;
      break;
     }
    }
   }
  }
 }
 string result="AARIS_ROAD_AUDIT roads="+roads+" samples="+samples+
 " occluded="+hidden+" shallow="+shallow+" minimum="+min.ToString("F4")+
 " maximum="+max.ToString("F4");
 Directory.CreateDirectory("/tmp/aaris-codespaces");
 File.WriteAllText("/tmp/aaris-codespaces/road-clearance.txt",result+"\n");
 Debug.Log(result);
}
}
}

// one-time clearance retest after native core mesh upgrade
