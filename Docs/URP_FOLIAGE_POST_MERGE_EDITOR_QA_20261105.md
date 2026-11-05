# URP foliage: saved-main verification in the actual Unity Editor

**Date:** 2026-11-05. **Confirmed source commit:** `08c57c62a64f99ed0745deae3c44f189f9ec711c` (merged PR #71).

## What was actually verified

A private, owner-authorized GitHub Actions job read this exact `main` commit with an **ephemeral read-only Actions token** and staged a strictly allowlisted source archive to the running Codespace. The project under `/workspaces/Unity-Game-Aris` remained untouched. The source archive was opened only in the separate disposable Unity 6000.3.26f1 editor copy under `/tmp/aaris-unity-batch/project`.

**All twelve original leaf/billboard `.mat` files** (Conifer, Cypress, Pine A–D) were verified SHA256-identical to merged `main`. Thus the earlier SpeedTree8 PBRLit A/B shader preview and the actual merged core materials have the same file bytes. The player C# was updated to merged `main` in the test copy as well.

The Unity Editor then successfully rendered the native scene at the **same camera** `(119,7,108)` toward `(112,-8,65)`, 960 × 540, with 7,508 native Terrain tree instances available in the scene readback.

| Frame | SHA256 | Magenta-color mask |
| --- | --- | ---: |
| Old project-local SpeedTree Shader Graph | `8693f18c5f3e1ba9acfb2b560258180a9915fb8a1c0c080e170db44dd1d63c2d` | 8,173 pixels |
| Isolated stock URP17 Shader A/B test | `1abdd54cdd495616d1f1c739fc25c2ae2c14d9e3d0ccdca0205d0bc20f3b59b9` | 0 pixels |
| **SHA-verified merged-main foliage materials in Unity** | `2feef0039797cc9bac588ff63dd3ebdfa3afb8aaa63360120907e073443f5287` | **0 pixels** |

Pixel mask (RGB8): `R>130, B>105, G<0.7*R, G<0.75*B`. This is an image color indicator, not definitive shader diagnostics or Android benchmarks. New real Unity capture: https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42019277235 ; original same-angle A/B export: https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42015242845 .

## Protected differences — do not erase them

The isolated Editor copy is **not** identical to the whole `main` checkout. The sync tool verified 13 of the 19 selected saved core files byte-for-byte. It refused to overwrite six pre-existing scratch tree prefabs because their blobs did not match either current-main or the reviewed historical source baseline. It also reported existing drift in the scene, GraphicsSettings and QualitySettings. Those source differences were **left intact**, including all `.meta` GUIDs, native TerrainData and Unity scenes. This is a *verified foliage-material import and screenshot*, not a full project checkout or new Android build.

The user's potentially dirty owner Codespace worktree was not reset, checked out, force-pulled, or modified by this test. The export frame is ephemeral; do not assume its artifact link will remain available indefinitely.

## Safe continuation

1. Read `AGENTS.md` and the actual `main` asset manifests. Never merge the old draft tree PRs wholesale into the newer reviewed source.
2. Identify the six scratch prefab differences using explicit semantic diffs (tree bounds, local transforms, LOD renderer shadow flags) before synchronizing any of them. Do not replace the original worktree's scene or settings simply to make snapshots equal.
3. Confirm GPU/render/shader warnings and full Unity import on a **separate clean checkout of current main**; execute controlled Android GLES3/Vulkan builds and real 2–3 GB device tests for wind, alpha clipping, distance transition, FPS/frametimes, memory and thermal stability.
4. The merged SHA-verifiable stock URP17 SpeedTree8 material fix must not be rolled back in an attempt to repair the older software renderer magenta bug.

**Release status:** Custom-shader magenta foliage remedied in the tested Unity screenshot and merged-main material bytes verified. Full Android device performance and complete project integration remain unverified.
