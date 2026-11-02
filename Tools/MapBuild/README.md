# Offline native map assembly

The saved scene requires no map-generation scripts or pre-export menu action.
These Python tools run only when deliberately rebuilding the source assets.

Inputs are four original, hash-recorded vendor TerrainData assets plus 17 unique
CC0 model sources (the original seven supplied GLBs contained one duplicate).
The public downloads are pinned by SHA-256 in `model_sources.json`; changed bytes
are rejected. Existing people, vehicle, weapon and loot nodes in the starter
scenes are excluded during conversion. No drivable vehicle assets are added.

Generated geometry is Unity native `.asset` Mesh data, authored using the original
vendor's Mesh serialization fixture. Materials use URP Lit, packed glTF metallic
and roughness textures are converted to Unity metallic/smoothness, and static
non-convex MeshColliders follow the actual building mesh. Native source
TerrainData is edited through its embedded Unity type tree, preserving detail
prototypes, splat textures, terrain layers and external references.

## Reproduction

Use Python 3.11 and install `requirements.txt`. Start from the original vendor
archive commit `3550c283405fbf02ec000e0d97a7ad8ff69f70b0`, bring in these tools,
fetch the four main TerrainData LFS objects, and run from repository root:

```
python Tools/MapBuild/build_map.py
python Tools/MapBuild/validate_map.py
```

Do not run `build_map.py` on already sculpted TerrainData: its input heights are
the original archive heights. The Actions workflow explicitly restores those
four source files from the original archive commit before each build. Downloaded
GLBs remain a build cache; final Unity assets and provenance are committed.

`MAP_BUILD_REPORT.json` records spatial assertions. `MAP_STRUCTURE_REPORT.json`
records Mesh-buffer, scene-reference and GUID checks. Neither constitutes a Unity
Editor import, render, physics simulation, lighting bake or target-device test.
The user performs those checks in Unity 6000.3.26f1 / URP 17.3.

The old TRANSFER files describe only the historical vendor import. The current
map layout, removals, new model hashes and terrain output hashes are in `Docs/`.
