# Residential house visual artifact triage — 2026-11-05

**Status:** source geometry diagnostics verified; native Unity rendering root cause **not yet established**. No original mesh triangles, material colors, texture bytes, shader GUIDs, .meta identities, or terrain trees/rocks were edited for this triage.

## Reproducible source evidence

In PR #75's read-only [world context CI workflow](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42060139673), Git LFS hydrated the real residential `Geometry.asset`, `Geometry_LOD1.asset`, and `Geometry_LOD2.asset` meshes. Run:

```
python Tools/World/diagnose_house_geometry.py
python Tools/World/diagnose_suspicious_house_faces.py
```

The second command emits machine-readable `AARIS_HOUSE_SUSPICIOUS_FACES=` JSON with counts **per submesh and per LOD**, up to four representative triangles' actual XYZ vertices, minimum altitude, long-edge length and needle aspect. A long or slender triangle alone is **not** proof of corruption; intentional walls, floors, trim strips and roof tiles have long narrow faces.

| Source model | LOD0 long faces >80% diagonal | LOD0 thin faces: edge ≥2m, min altitude <5cm | LOD1 thin | LOD2 thin |
|---|---:|---:|---:|---:|
| `bungalow_house` | 4 | 1,122 | 214 | 70 |
| `pitched_roof_cottage` | 0 | 1,156 | 256 | 75 |
| `detached_two_storey_house` | 0 | 699 | 148 | 47 |

In the bungalow, the **four exceptionally long faces are in material submesh 2** (warm sandstone). A representative triangle lies on **Y=0**, with vertices (-6,0,5.56), (-6,0,-4.44), (6,0,-4.44). The longest edge is **15.6205m**, with about **7.68m altitude**, aspect about **2.03** — geometrically consistent with a large flat surface, **not** a spike.

Its LOD0 submesh 0 (material name `bungalow_house_Original black finished iron`) has **872** thin faces. The pitched-roof cottage's same slot has **872** thin faces, illustrating that the symptom is not bungalow-specific. The bungalow roof tile (slot 7) has four thin faces; this is not in itself abnormal. All eight saved bungalow materials use GUID `933532a4fcc9baf4fa0491de14d08ed7` as their shader reference; the source analysis does not verify the shader's actual Unity-rendered pixels.

## Remaining root-cause gate

The owner previously reported black/white spiky imagery for `ClockTowerTown_bungalow_house_03`. The native triangle counts **neither confirm nor refute** its visible defect. Before any mesh removal or all-house replacement, inspect multiple authentic Unity Editor viewpoints with **LOD0 forced versus LOD1/LOD2, same camera and lighting**, including backface culling, imported normals, renderer/material assignments, UVs and transparent shader rendering. Compare source prefab at world scale with scene instance. Investigate whether the artifact is caused by shader/device/backend rather than native geometry.

A native software-renderer house gallery can fail with Unity `SIGSEGV` in `AarisLiveEditorBridge.Capture`; that is not a trustworthy measure of the bungalow's final appearance. Preserve all incomplete images with their exact scene/import identity. Do not present synthetic geometry previews as verified real Unity screenshots.

The `AarisResidentialRoutePhysicsAudit` script remains **source-checked only**. Static XZ tests and actual TerrainData center/height samples do not establish real vehicle Rigidbody/wheel/steering gameplay or finished house interiors. PR #75 must remain Draft until visual and physics gates pass.
