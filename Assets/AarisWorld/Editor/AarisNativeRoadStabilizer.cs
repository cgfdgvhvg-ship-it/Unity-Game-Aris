using System;
using System.Collections.Generic;
using System.IO;
using Unity.Collections;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace Aaris.MapReview.Editor
{
    /// <summary>
    /// One-off authoring repair for the checked-in native roads. Runs only with
    /// a local opt-in marker, never in a shipped game and never every frame.
    /// Both the asphalt and its paint are sampled from the same four terrains.
    /// Save directly into existing Mesh assets to retain their GUID/fileIDs.
    /// </summary>
    [InitializeOnLoad]
    public static class AarisNativeRoadStabilizer
    {
        const string Marker = "/tmp/aaris-codespaces/stabilize-native-roads.request";
        const string Result = "/tmp/aaris-codespaces/stabilize-native-roads.txt";
        const float AsphaltOffset = 0.12f;
        const float PaintOffset = 0.155f;
        const float MaxSegment = 1.75f;
        const int CrossSections = 4; // three lateral quads; no excessive road tessellation

        static AarisNativeRoadStabilizer()
        {
            EditorApplication.delayCall += () =>
            {
                if (File.Exists(Marker) && !EditorApplication.isPlayingOrWillChangePlaymode)
                {
                    File.Delete(Marker);
                    Rebuild();
                }
            };
        }

        static Vector3[] ReadVertices(Mesh mesh)
        {
            using (var data = Mesh.AcquireReadOnlyMeshData(mesh))
            using (var result = new NativeArray<Vector3>(data[0].vertexCount, Allocator.Temp))
            {
                data[0].GetVertices(result);
                return result.ToArray();
            }
        }

        static int[] ReadIndices(Mesh mesh)
        {
            using (var data = Mesh.AcquireReadOnlyMeshData(mesh))
            using (var result = new NativeArray<int>(data[0].GetSubMesh(0).indexCount, Allocator.Temp))
            {
                data[0].GetIndices(result, 0);
                return result.ToArray();
            }
        }

        static float Ground(Vector3 p, Terrain[] tiles)
        {
            foreach (var tile in tiles)
            {
                if (tile == null || tile.terrainData == null) continue;
                Vector3 origin = tile.transform.position;
                Vector3 size = tile.terrainData.size;
                if (p.x >= origin.x - .002f && p.x <= origin.x + size.x + .002f &&
                    p.z >= origin.z - .002f && p.z <= origin.z + size.z + .002f)
                    return tile.SampleHeight(p) + origin.y;
            }
            throw new InvalidOperationException("ROAD_VERTEX_OUTSIDE_NATIVE_TERRAIN");
        }

        static Vector3 Lift(Vector3 p, Terrain[] tiles, float offset)
        {
            p.y = Ground(p, tiles) + offset;
            return p;
        }

        static void Put(List<Vector3> pos, List<Vector2> uv, Vector3 p)
        {
            pos.Add(p);
            uv.Add(new Vector2(p.x * .25f, p.z * .25f));
        }

        static Mesh Asphalt(Mesh original, Terrain[] tiles)
        {
            Vector3[] source = ReadVertices(original);
            if (source.Length < 4 || source.Length % 2 != 0)
                throw new InvalidOperationException("UNEXPECTED_NATIVE_ROAD_MESH_LAYOUT");
            var pos = new List<Vector3>(source.Length * 5);
            var uv = new List<Vector2>(source.Length * 5);
            var triangles = new List<int>(source.Length * 15);
            int lastRow = 0;
            for (int i = 0; i + 3 < source.Length; i += 2)
            {
                Vector3 left = source[i], right = source[i + 1];
                Vector3 nextLeft = source[i + 2], nextRight = source[i + 3];
                int sections = Mathf.Max(1, Mathf.CeilToInt(Mathf.Max(
                    Vector2.Distance(new Vector2(left.x, left.z), new Vector2(nextLeft.x, nextLeft.z)),
                    Vector2.Distance(new Vector2(right.x, right.z), new Vector2(nextRight.x, nextRight.z))) / MaxSegment));
                for (int step = 0; step < sections; step++)
                {
                    float t = (float)step / sections;
                    AddRow(Vector3.Lerp(left, nextLeft, t), Vector3.Lerp(right, nextRight, t), tiles, pos, uv);
                    lastRow++;
                }
            }
            AddRow(source[source.Length - 2], source[source.Length - 1], tiles, pos, uv);
            for (int row = 0; row < lastRow; row++)
                for (int col = 0; col < CrossSections - 1; col++)
                {
                    int a = row * CrossSections + col;
                    int b = (row + 1) * CrossSections + col;
                    int c = a + 1, d = b + 1;
                    triangles.Add(a); triangles.Add(b); triangles.Add(c);
                    triangles.Add(c); triangles.Add(b); triangles.Add(d);
                }
            if (triangles.Count < 3) throw new InvalidOperationException("NO_ROAD_TRIANGLES");
            // Correct orientation once; the original road uses upward-facing winding.
            Vector3 normal = Vector3.Cross(pos[triangles[1]] - pos[triangles[0]],
                                           pos[triangles[2]] - pos[triangles[0]]);
            if (normal.y < 0f)
                for (int i = 0; i < triangles.Count; i += 3)
                {
                    int tmp = triangles[i + 1];
                    triangles[i + 1] = triangles[i + 2];
                    triangles[i + 2] = tmp;
                }
            return Build(original.name, pos, uv, triangles);
        }

        static void AddRow(Vector3 a, Vector3 b, Terrain[] tiles, List<Vector3> pos, List<Vector2> uv)
        {
            for (int col = 0; col < CrossSections; col++)
                Put(pos, uv, Lift(Vector3.Lerp(a, b, (float)col / (CrossSections - 1)),
                                  tiles, AsphaltOffset));
        }

        static float HorizontalSqr(Vector3 a, Vector3 b)
        {
            return (a.x - b.x) * (a.x - b.x) + (a.z - b.z) * (a.z - b.z);
        }

        static void PaintTri(Vector3 a, Vector3 b, Vector3 c, int depth, Terrain[] tiles,
            List<Vector3> pos, List<Vector2> uv, List<int> triangles)
        {
            float ab = HorizontalSqr(a, b), bc = HorizontalSqr(b, c), ca = HorizontalSqr(c, a);
            if (depth < 8 && Mathf.Max(ab, Mathf.Max(bc, ca)) > MaxSegment * MaxSegment)
            {
                if (ab >= bc && ab >= ca)
                {
                    Vector3 mid = (a + b) * .5f;
                    PaintTri(a, mid, c, depth + 1, tiles, pos, uv, triangles);
                    PaintTri(mid, b, c, depth + 1, tiles, pos, uv, triangles);
                }
                else if (bc >= ca)
                {
                    Vector3 mid = (b + c) * .5f;
                    PaintTri(a, b, mid, depth + 1, tiles, pos, uv, triangles);
                    PaintTri(a, mid, c, depth + 1, tiles, pos, uv, triangles);
                }
                else
                {
                    Vector3 mid = (c + a) * .5f;
                    PaintTri(a, b, mid, depth + 1, tiles, pos, uv, triangles);
                    PaintTri(mid, b, c, depth + 1, tiles, pos, uv, triangles);
                }
                return;
            }
            int first = pos.Count;
            Put(pos, uv, Lift(a, tiles, PaintOffset));
            Put(pos, uv, Lift(b, tiles, PaintOffset));
            Put(pos, uv, Lift(c, tiles, PaintOffset));
            triangles.Add(first);
            triangles.Add(first + 1);
            triangles.Add(first + 2);
        }

        static Mesh Markings(Mesh original, Terrain[] tiles)
        {
            Vector3[] verts = ReadVertices(original);
            int[] indices = ReadIndices(original);
            var pos = new List<Vector3>(verts.Length * 3);
            var uv = new List<Vector2>(verts.Length * 3);
            var triangles = new List<int>(indices.Length * 3);
            for (int i = 0; i + 2 < indices.Length; i += 3)
                PaintTri(verts[indices[i]], verts[indices[i + 1]], verts[indices[i + 2]],
                         0, tiles, pos, uv, triangles);
            if (triangles.Count < 3) throw new InvalidOperationException("NO_PAINT_TRIANGLES");
            return Build(original.name, pos, uv, triangles);
        }

        static Mesh Build(string name, List<Vector3> pos, List<Vector2> uv, List<int> triangles)
        {
            var mesh = new Mesh { name = name, indexFormat = IndexFormat.UInt32 };
            mesh.SetVertices(pos);
            mesh.SetUVs(0, uv);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }

        [MenuItem("Aaris/Review/Fix Native Road Flicker In Core Meshes")]
        public static void Rebuild()
        {
            string summary = "AARIS_ROAD_STABILIZE";
            try
            {
                if (EditorApplication.isPlayingOrWillChangePlaymode)
                    throw new InvalidOperationException("STOP_PLAY_MODE_BEFORE_NATIVE_REBUILD");
                var root = GameObject.Find("RoadNetwork");
                Terrain[] tiles = Terrain.activeTerrains;
                if (root == null || tiles == null || tiles.Length != 4)
                    throw new InvalidOperationException("FOUR_TILE_NATIVE_SCENE_REQUIRED");

                int roads = 0, painted = 0, vertices = 0;
                var filters = root.GetComponentsInChildren<MeshFilter>(true);
                var meshes = new Dictionary<string, Mesh>();
                foreach (var filter in filters)
                {
                    if (filter.sharedMesh == null) continue;
                    string path = AssetDatabase.GetAssetPath(filter.sharedMesh);
                    if (!path.StartsWith("Assets/AarisWorld/Surfaces/Road_", StringComparison.Ordinal) &&
                        !path.StartsWith("Assets/AarisWorld/Surfaces/RoadMark_", StringComparison.Ordinal))
                        continue;
                    var old = filter.sharedMesh;
                    Mesh fresh = filter.name.EndsWith("_Markings", StringComparison.Ordinal)
                        ? Markings(old, tiles) : Asphalt(old, tiles);
                    meshes.Add(path, fresh);
                }
                // Construct all meshes before touching any original assets.
                if (meshes.Count != 78)
                    throw new InvalidOperationException("EXPECTED_39_ROADS_AND_39_MARKINGS");
                foreach (var pair in meshes)
                {
                    Mesh old = AssetDatabase.LoadAssetAtPath<Mesh>(pair.Key);
                    EditorUtility.CopySerialized(pair.Value, old);
                    EditorUtility.SetDirty(old);
                    vertices += pair.Value.vertexCount;
                    if (pair.Key.Contains("/RoadMark_")) painted++; else roads++;
                    UnityEngine.Object.DestroyImmediate(pair.Value);
                }
                AssetDatabase.SaveAssets();
                summary += " roads=" + roads + " markings=" + painted +
                           " vertices=" + vertices + " offset_m=" + AsphaltOffset +
                           " paint_offset_m=" + PaintOffset + " status=SAVED_NATIVE_ASSETS";
            }
            catch (Exception ex)
            {
                summary += " status=FAILED reason=" + ex.GetType().Name +
                           " message=" + ex.Message;
                Debug.LogError(summary);
            }
            Directory.CreateDirectory(Path.GetDirectoryName(Result));
            File.WriteAllText(Result, summary + "\n");
            Debug.Log(summary);
        }
    }
}
