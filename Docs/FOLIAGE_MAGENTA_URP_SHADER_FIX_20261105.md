# SpeedTree/Foliage Magenta: verified native URP material fix (2026-11-05)

## Cause isolation

The 2×2 km Unity scene renders bright magenta leaves in a real licensed Unity 6000.3.26f1 screenshot on Codespaces private Xvfb `:12`, with **Mesa llvmpipe (CPU software GL)**. The tree colors in the twelve native leaf/billboard `.mat` files were ordinary greens/grays rather than magenta; their `m_Shader` fields all referenced the same project-local `SpeedTreeURP_Branch.shadergraph` GUID `d4fdc026464a42041be7fe785babd90e`. The graph is a URP Lit Shader Graph, so a blanket "Built-in pipeline shader" migration does not diagnose this case.

Unity's error shader is magenta if a material's shader cannot compile, has no supported subshader, or required variants are missing. The exact failing internal graph operation on every Android GPU has **not** been proven; this was a controlled remedy for the observed software-renderer artifact.

## Reproducible A/B Unity Editor test

The owner worktree and original core assets were protected. A strictly bounded scratch-only script checked the original byte identity and `.meta` of twelve leaf/billboard materials and verified stock `Packages/com.unity.render-pipelines.universal/Shaders/Nature/SpeedTree8_PBRLit.shadergraph.meta` GUID `9920c1f1781549a46ba081a2a15a16ec` in the installed Unity URP 17.3 package. It backed up all twelve materials, replaced only the single `m_Shader.guid` field in each isolated `.mat` copy, and Unity reimported them automatically.

Matched full 960×540 camera captures: camera (119, 7, 108) aimed at (112, -8, 65), same native scene and trees.

| Snapshot | SHA256 | Magenta-mask pixel count |
| --- | --- | ---: |
| Original custom shader | `8693f18c5f3e1ba9acfb2b560258180a9915fb8a1c0c080e170db44dd1d63c2d` | 8,173 |
| Built-in URP SpeedTree8 shader | `1abdd54cdd495616d1f1c739fc25c2ae2c14d9e3d0ccdca0205d0bc20f3b59b9` | 0 |

The measurement is a **heuristic screenshot color mask**: `R>130, B>105, G<0.7R, G<0.75B` in 8-bit pixels. It is not a semantic pixel classifier, Unity shader diagnostic, a proof of zero error materials anywhere else, or a device FPS result. The image visibly showed foliage turning green and retaining texture. GitHub Actions native capture export: https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42015242845 and the earlier before export https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42009310875 .

## Exact saved core edit

This reviewed GitHub branch transplants the **same one-GUID change to twelve original native `.mat` assets**: six leaf materials and their six billboard variants (Conifer, Cypress, Pine A–D). The actual material `m_Colors`, `_MainTex` / normal / subsurface textures, WindQuality keywords, alpha clipping, render settings, render order and subshader fileID stay byte-identical to the old reviewed materials except for this shader GUID. Source `.st`, imported tree geometry, trunk/crown scale, LOD thresholds, scene, TerrainData LFS bytes, materials' `.meta` GUIDs and prefabs are not modified.

The new `Tools/World/tests/test_foliage_magenta_shader_core.py` reverses **only** the shader GUID and demands exact old Git blob SHA-1 for all twelve saved assets. The dedicated GitHub CI workflow rejects unreviewed asset edits.

## Release and visual gates

This fixes magenta in the tested *Unity Editor software-rendered screenshot*. Reimport all saved merged source into Unity Editor and build/test on **real 2 GB and 3 GB Android devices**, verifying Android GLES3/Vulkan shader variants, tree wind behavior, vertex LOD crossfade, billboard transition, double-sided foliage and shadows, missing variants and frame times. Do not claim Android launch success, lower GPU time, a 60 FPS guarantee or an improved commercial-quality look from screenshot QA alone.

Unity reference: https://docs.unity.com/en-us/engine/6000.3/manual/materials-and-shaders/shaders/shader-troubleshooting/shader-error
