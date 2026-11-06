# Native building LOD face/normal audit — 2026-11-06

**State: candidate logic tested, NO native game-asset fix applied.** This document records a reproducible observation and a safe next step, not a rendered defect resolution.

## Evidence from actual LFS bytes
- PR #76 source branch: `fix/diagnose-black-buildings-sky-20261106`.
- GitHub Actions [run 42184886477](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42184886477), successful.
- All 17 original models and their LOD1/LOD2 meshes (51 hydrated `Geometry*.asset` files) passed vertex/index/bounds/material-slot integrity validation.
- `Tools/Validation/check_building_mesh_health.py` now reports geometric face versus averaged saved vertex-normal alignment. This is **not** actual Unity front-face proof or graphics testing.
- Among source LOD0 files, the mesh for CanalTown had 0 opposing faces; LOD1 had **9,599/257,511**, LOD2 had **18,491/125,672**. HanokVillage LOD2 had **11,001/55,215**. Some original imported models have intentional/degenerate geometry, so a bulk global winding change is not justified.
- The optional conservative face-index reorder candidate from `Tools/Validation/preview_lod_face_winding.py` dry-ran all **34** LOD1/LOD2 files: **31** had proposed changes, **66,095** triangle index orders were proposed for reversal, **20,349** opposing faces remain under the deliberately strict threshold. This is a **candidate**, not a visually approved asset. The CI run confirmed no tracked model/scene bytes were modified.

## Prevention / reproducibility
- `Tools/MapBuild/lod_winding.py` contains shared deterministic geometry-only candidate logic. It flips only strongly opposed triangle index order, without changing triangle membership, vertex attributes, positions, UVs, tangents, collider meshes, material slots or GUIDs.
- `Tools/MapBuild/ground_native.py` uses that guard when creating **future** LOD meshes. **Do not rerun the historical full map/terrain generator over the owner's saved current scene.** Re-running may overwrite valuable later doorway, collider, road, terrain or human-scale edits.
- Read-only diagnostic: `python Tools/Validation/check_building_mesh_health.py --require-native --json-out /tmp/aaris-mesh-health.json` (after `git lfs pull`).
- Safe dry-run candidate: `python Tools/Validation/preview_lod_face_winding.py --root . --json-out /tmp/aaris-winding.json`. This does not create assets.
- To generate isolated proposed mesh files only: `python Tools/Validation/preview_lod_face_winding.py --root . --candidate-dir /tmp/aaris-lod-candidate --json-out /tmp/aaris-winding.json`. The candidate directory must be **outside** the repo; no `.meta` is written.
- Unit tests: `python -m unittest discover -s Tools/World/tests -p test_building_mesh_health.py -v` and `python -m unittest discover -s Tools/World/tests -p test_lod_winding.py -v`. CI is `.github/workflows/building-mesh-health.yml`.

## How a new AI must complete the visual repair
1. Start or reconnect the **same authorized stopped Codespace** through its approved owner lifecycle, or use another authorized GPU-backed Unity 6000.3.26f1 Editor. Check exact main/PR source and authenticated LFS hydration. Never overwrite the original dirty Codespace worktree.
2. In an **isolated Unity scratch copy**, first reproduce the issue using saved ThirdPersonPlayer at 1.78 m and identical positions/camera headings across LOD0→LOD2. Capture baseline house exteriors, interiors, the horizon/sky at different pitches, Unity Console shader/import errors, and exact mesh/material/LOD scene references.
3. Apply *only* isolated candidate LOD1/LOD2 `.asset` files to the scratch copy, preserving `.meta`, original LOD0 and all materials; inspect same-camera before/after images, culling, shading, transitions and collision. Reject if holes/inside-out walls/new spikes appear. If candidate is wrong, fix algorithm, add regression tests and rerun CI. Do not silently publish.
4. Diagnose the **white sky separately**, using `Camera.clearFlags`, `RenderSettings.skybox`, URP shader variants, fog/environment, exposure, device graphics API and whether a bright surface/horizon occludes the sky. Existing `Sky.mat` uses procedural shader and exposure 1.15; that does not prove what Android renders. Do not recolor arbitrary materials to hide the problem.
5. Only after engine and real device verification: commit the exact tested native assets via guarded LFS writer, compare SHA256 and original `.meta`/GUID, open a reviewed PR, and merge after all tests. Record evidence and final result here and in `AGENTS.md`.

**Limitations:** Native Unity test, actual corrected Android screenshot, GPU-side mesh culling and successful durable LFS upload of corrected LOD assets are **not yet demonstrated**. A green offline CI is not a game graphics release gate.
