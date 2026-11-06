# UPDATE — authenticated native LOD normal/winding investigation (2026-11-06)

**Read this first if buildings render as black/white spikes or disappear with camera movement.** Exact Git LFS 17×3 building meshes are structurally valid, but some **LOD1/LOD2 face orientations disagree with their saved normals**, particularly CanalTown LOD2 18,491/125,672 and HanokVillage LOD2 11,001/55,215. This is a reproducible source-level warning, **not proof of the cause of the Android screenshots**. See [Docs/LOD_NORMAL_WINDING_DIAGNOSTIC_20261106.md](Docs/LOD_NORMAL_WINDING_DIAGNOSTIC_20261106.md).

**Working corrective scripts:** `Tools/MapBuild/lod_winding.py` (conservative index-order candidate), `Tools/MapBuild/ground_native.py` (guards future generated LODs), `Tools/Validation/preview_lod_face_winding.py` (safe dry-run; optional candidate files outside repository), `Tools/Validation/check_building_mesh_health.py` (read-only native check), and regression tests `test_lod_winding.py` and `test_building_mesh_health.py`. The actual native CI [run 42184886477](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42184886477) passed; it checked 34 LOD1/LOD2 assets and proposed **66,095 index reorderings across 31 meshes** without changing any tracked Unity asset. These changes are **not yet applied to production meshes**, as actual Unity/Android visual validation is blocked by the stopped Codespace. Do not misstate candidate as fixed game graphics.

**Required from any AI encountering a script error:** diagnose the exact traceback/CLI or CI step; fix the smallest source bug; add a regression test reproducing the failure; rerun all affected unit tests and native-LFS validation; update this `AGENTS.md` and incident document with **actual tested results and remaining blockers**. Never suppress a failed check, mutate protected `.meta` GUIDs, bypass signed owner-only jobs, overwrite a dirty Codespace worktree or claim screenshot/device success from Python-only evidence.

---

# ACTIVE VISUAL-RENDERING INCIDENT — black spiky buildings / white sky (2026-11-06)

**Owner evidence:** Six actual third-person mobile screenshots show black/white spiky or planar building silhouettes, white-looking sky/horizon, and camera-dependent white/black occlusion. The player, terrain and nearby trees render in at least some views. These are observed symptoms; **do not infer that all 3D source meshes, sky shader, LFS blobs, or device GPU are definitively corrupt without tests**. Do not turn the screenshots into replacement assets.

**Repository:** Sunda account `sundamunda289-art/Unity-Game-Aris`; this incident does not authorize editing the other Aaris-khan-don repository. The checked-in source has 59 scene buildings and three saved model LOD levels; original native meshes `Assets/AarisWorld/Models/<model>/Geometry*.asset` are **Git LFS**. `Sky.mat` already contains the Procedural Sky shader; the player camera is supposed to clear to Skybox. Offline reports are **not** Unity GPU/Android test results.

**Real blocker recorded:** The AI's read-only owner job `unity-sky-mesh-status-20261106-1217`, commit `9045ed6089a8d5a29eb96aa019234043616cf6d2`, GitHub Actions run [42176739276](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42176739276), passed all eight workflow preflight tests but **did not reach Unity**. The result was `AARIS_JOB_ERROR=Codespace is stopped: request Cloudflare lifecycle start before queuing SSH commands`. Do not call this a Unity import, render, repair, or screenshot. Resume the **same** authorized Codespace through its owner-approved lifecycle control before queuing another owner-only job. Never bypass Codespace credentials or delete/overwrite the owner's dirty worktree.

**Mandatory AI remediation sequence:**
1. Read this document and `Docs/UNITY_TMP_AI_HANDOFF.md`, `Docs/AI_MASTER_CONTROL_AND_AUTH.md` and `Docs/UNITY_BATCHED_AUTOSYNC.md`. In a **fresh isolated** project with Git LFS hydrated, use `python Tools/Validation/check_building_mesh_health.py --require-native --json-out /tmp/aaris-building-mesh-health.json`. A Git LFS pointer is not geometry. This preflight reads original plus LOD1/LOD2 mesh buffers, vertex/index/submesh windows, bounds, materials slots, and triangle counts relative to the authored `Docs/MAP_LAYOUT.json` and `Docs/GROUND_REVIEW_REPORT.json`. If it fails, record **exact model/LOD and error**, fix that specific native source through reviewed Unity/LFS authoring, rerun, and capture before/after camera views.
2. When the Codespace is running, check `unity_virtual_gui_status`, the loaded saved scene and real Unity Editor log. Inspect `MeshFilter.sharedMesh`, mesh bounds, `MeshRenderer.sharedMaterials`, `LODGroup` transition and source `.mat` textures on affected houses. Compare real camera images from identical player height/position/direction under LOD0, LOD1, LOD2 and camera swipes. Then isolate sky separately: `Camera.clearFlags`, `RenderSettings.skybox`, Procedural Sky shader imported, sun/exposure/fog, clip planes, URP renderer masks, Android GLES3 variants. Never recolor or globally replace geometry on guesswork.
3. Repair the verified *cause*, not only a runtime visual camouflage. Preserve existing saved scene, prefabs, terrain, material GUIDs and original backup; modify `.meta` only when importing new explicitly identified assets. If editing any helper/validation script causes an error, repair the script and add a regression test, then rerun its tests and native checks. No blind generator rebuilds against an LFS pointer and no reset/clean on the original Codespace tree.
4. Ensure the fixed native model/sky is tested with a **licensed actual Unity Editor**, valid scene readback, matched screenshots including player-height view and camera orbit, plus a **real Android phone** if claiming device rendering fixed. Check sky colors while aiming toward the horizon; do not mistake white beyond an unbounded terrain edge for a mesh issue. Save through the guarded writer with LFS SHA-256 receipt, open PR, pass CI, and merge only after visual approval. Distinguish offline validation, Unity Editor screenshots, Android results, and GitHub merged commit explicitly.

**Measured progress (2026-11-06):** Draft PR [#76](https://github.com/sundamunda289-art/Unity-Game-Aris/pull/76) added the LFS-native reader and regression tests. [Successful Actions run 42179200790](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42179200790) hydrated ALL 17 building types × LOD0/LOD1/LOD2 (**51 actual mesh files**) and validated their readable vertex buffers, 32-bit index windows, triangle bounds, model bounds, and authored submesh slot counts. The seven synthetic regression tests also passed. Some valid materials reserve an empty submesh with `indexCount: 0`, and 21 changed mesh files have fewer triangles than the original `MAP_LAYOUT`/`GROUND_REVIEW_REPORT` count: the QA now accepts empty slots and bounded triangle removals to avoid misdiagnosing intended prior geometry edits. **Native buffer validity does not prove triangles visually match their source, nor rule out bad shader/material/LOD/camera rendering.** Do not replace meshes or undo door openings simply to restore the historical triangle counts.

**Current disposition:** Source-level mesh buffer corruption of these 51 checked files was **not reproduced**. The photographed black/white jagged house and white sky **remain unverified/unfixed in rendered Unity/Android gameplay**; the Codespace is stopped and native Unity rendering was not accessible. Future AI must prioritize actual URP/mobile shader, house material import, LOD transition/renderers, camera near-plane clipping/occlusion, skybox/background, logs and real before/after device captures. Do not claim completion or invent images.

---

# AI MASTER CONTROL AND GITHUB CREDENTIALS — READ THIS FIRST (2026-11-05)

## ACTIVE SUNDA CODESPACE ROUTING — verified 2026-11-06

Current owner/repo: `sundamunda289-art/Unity-Game-Aris`; existing Codespace: `redesigned-space-train-gxp5jwvq94wg2wvw6`. **Cloudflare `aaris-codespace-relay` handles START/STOP/STATUS only; it does NOT execute terminal commands.** Its previously installed GitHub secret `GITHUB_CONTROL_TOKEN` must be refreshed from the Sunda account once, without storing the token in this repository. AI terminal operations use the existing `.aaris/jobs/*.json` queue on `ai/codespace-jobs`, GitHub Actions and direct Codespaces SSH, with machine-readable results in the workflow logs/artifact.

**Verified direct SSH test:** [run 42157472720](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42157472720) returned `ok:true`, `exit_code:0` and native Codespace diagnostics, including ~10.76 GiB free and protected dirty worktree. Unity Editor was not installed at that check. The old `musical-carnival-...` Codespace and old owner's HTTP 402 reports below are historical and do not reflect the Sunda Codespace. Do not reset/clean or overwrite its dirty Unity LFS assets.

## SUNDA TMP UNITY EDITOR + VERIFIED LFS SAVE — 2026-11-06

**Active machine confirmed by [readback](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42161483406):** `standardLinux32gb`, 4 CPU cores, 16 GiB RAM, 32 GiB persistent volume. Separate `/tmp` has 117.556 GiB total, 108.844 GiB free before Editor installation (see verified runtime mount job `sunda-upgraded-tmp-check-20261106-c06`). It is EPHEMERAL and cleared on Codespace stop/restart.

**Official Unity 6000.3.26f1 is installed in this running Codespace:** `/tmp/aaris-unity-editor/6000.3.26f1/Editor/Unity`. Native `-version` returned `6000.3.26f1` (successful [Actions run](https://github.com/sundamunda289-art/Unity-Game-Aris/actions/runs/42161922440)). Install source and exact-version guard: `ai/codespace-jobs/Tools/World/unity_tmp_editor_installer.py`; supported operations `unity_tmp_install_start` and `unity_tmp_install_status` on the EXISTING owner-authorized Actions SSH queue. If Codespace stopped and /tmp was lost, the Editor must be reinstalled or restored from verified external cache; do not claim it survives automatically.

**Map copy/import:** the old `unity_session_recover` operation was invoked successfully and reported `scratch_reimport_started`, launching worker PID 3760 to copy the original Unity project into `/tmp/aaris-unity-batch/project`; this is NOT yet proof that the scene loaded or Unity license is active. Read `unity_recovery_diagnostics` and `unity_virtual_gui_status`; require real `scene-readback.json`, Unity GUI PID, loaded 4 Terrain components and a successful native inspect before editing.

**Native LFS save contract:** after loading and verifying the genuine scratch scene, run `unity_sync_watch_start` to arm the existing batching journal, perform reviewed `unity_virtual_live` edits, inspect native changes and readback, then queue ONE `unity_sync_save_session` job with commit message prefix **`Unity Batch Save:`**. The separate `unity-batched-github-upload.yml` Actions writer uses an ephemeral scoped `GITHUB_TOKEN` to push LFS to a review branch and verify SHA. Codespace direct git credentials are NOT available; `unity_sync_auth` correctly reports `git_credentials_unavailable`. No sync completion may be claimed without the writer's remote receipt. Git stores historical versions; NEVER prune/reset the prior LFS blobs or overwrite the owner's 11 dirty source Assets. Before stopping, force a verified Save Session for all current reviewed edits. Never leak GitHub, Cloudflare, Unity or VNC credentials to issue/job/log/source.

---



**Authoritative agent entrypoint:** [Docs/AI_MASTER_CONTROL_AND_AUTH.md](Docs/AI_MASTER_CONTROL_AND_AUTH.md). This is the current GitHub/Codespace/Unity/LFS operating contract, overriding historical terminal guidance below (especially the old Issue #37 bridge). Owner/repo: `sundamunda289-art/Unity-Game-Aris`. The default code source is `main`; the dedicated, owner-only command queue is a **different** branch, `ai/codespace-jobs`.

**One straightforward route for any authorized AI:** (1) use its owner-approved GitHub connector to read this repo; (2) submit exactly one `.aaris/jobs/<unique-id>.json` on `ai/codespace-jobs` with a supported, reviewed `operation`; (3) watch the `Aaris Codespace On-Demand Terminal` Actions run; (4) parse the matching `AARIS_RESULT_JSON`, validate `ok`/exit and native Unity readback; (5) save verified native changes through the **separate** `unity-batched-github-upload.yml` LFS writer, then validate the remote branch/receipt and PR before merge. No Issue #37 command is the default. No arbitrary shell/unsafe repo mutation is permitted from job JSON.

**Preflight security gate LIVE:** every queued owner Codespace job now runs `python3 -m unittest discover -s Tools/World/tests -p test_ai_master_github_auth.py -v` before using the Codespace secret or calling SSH. Eight no-network tests passed and the latest `main` SHA was fetched through the temporary read-only GitHub auth helper in [verified workflow #42027193573](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42027193573). This gate lives on **`ai/codespace-jobs`** in `.github/workflows/ai-codespace-on-demand.yml`; inspect that branch's workflow, not only `main`.

**Pinned fetch for any later main:** The reviewed `unity_main_core_sync` job requires `args:["<actual-current-main-40-hex-sha>"]`. Read the HEAD from GitHub first; this avoids hard-coded stale commits and requires the fetched HEAD to match exactly. Import is scratch-only and conflicts are preserved. No raw GitHub token is passed in the job.

**Master auth router:** `Tools/World/ai_master_github_auth.py` uses a short-lived `GITHUB_TOKEN` (or already-minted limited GitHub App installation token) to fetch *only this repo/main* into an ephemeral GitHub Actions checkout, using temporary `GIT_ASKPASS`. `AARIS_CODESPACE_TOKEN` is a **separate GitHub Actions secret** for the existing Codespace lifecycle and SSH, not for source git writes. Git LFS commits use Actions `GITHUB_TOKEN` with narrowly scoped `contents: write` ONLY in the dedicated verified uploader. This corrects the earlier private `git fetch` password-prompt failure; the later exact-main read/sync succeeded. Original Codespace git credentials may still be unavailable, so never assume you can push directly from the dirty checkout.

**No global master password:** NEVER ask the owner to send tokens in chat, store them in source/AGENTS/jobs/logs, grant an AI all GitHub account permissions, or silently change/create Codespace machines. Other AIs need their own authorized connector or an owner-installed repo-scoped GitHub App. Check `python Tools/World/ai_master_github_auth.py status` in Actions for **boolean readiness only**. User worktree and `.meta` files are protected; `/tmp` Unity scratch is disposable and does not survive shutdown.

---

# CURRENT POST-MERGE UNITY FOLIAGE QA — 2026-11-05

The **saved PR #71 SpeedTree8 PBRLit shader fix is verified in the native Unity 6000.3.26f1 Editor against the actual merged-main material bytes**, not just an unsynced A/B preview. Frozen main `08c57c62` was read through one ephemeral read-only Actions token and 12/12 foliage/billboard `.mat` core files exactly matched the isolated Unity Editor copy. Matching 960×540 forest capture had **0 detected magenta-color pixels**, versus **8,173** in the original custom-ShaderGraph render (heuristic RGB color mask). Source evidence and image hash: [Docs/URP_FOLIAGE_POST_MERGE_EDITOR_QA_20261105.md](Docs/URP_FOLIAGE_POST_MERGE_EDITOR_QA_20261105.md).

**Do not confuse material success with full project sync.** Six scratch-only tree prefabs have unknown deviations and remain untouched, as do a drifting scene/QualitySettings/GraphicsSettings. The owner worktree and `.meta` GUIDs were not modified by this QA; one player C# scratch copy was updated. Do not overwrite protected differences, merge stale tree PRs, or claim an Android FPS benchmark. The screenshot represents a real software-GPU Editor render of SHA-verified merged foliage material bytes; real Android graphics and thermal/device validation remain required.

---

# FOLIAGE MAGENTA SHADER REMEDY — NATIVE MATERIALS (2026-11-05)

**Read [Docs/FOLIAGE_MAGENTA_URP_SHADER_FIX_20261105.md](Docs/FOLIAGE_MAGENTA_URP_SHADER_FIX_20261105.md) before touching tree colors.** Twelve original foliage/billboard `.mat` files (Conifer, Cypress, Pines A–D) have one reviewed `m_Shader.guid` change from project-local `SpeedTreeURP_Branch` to the package's stock URP 17.3 `SpeedTree8_PBRLit`, GUID `9920c1f1781549a46ba081a2a15a16ec`. This exact fix was A/B-tested in the licensed Unity Editor on an isolated scratch copy: same-camera magenta-mask pixels 8,173→0 and visible green trees, with true before/after JPEG readback. Do **not** change `_Color` arbitrarily: original tint, textures, alpha, billboard/wind, collider, LOD, tree geometry, TerrainData LFS and all material `.meta` identities are preserved. The old local Shader Graph remains available and is not deleted. CI: `Tools/World/tests/test_foliage_magenta_shader_core.py`, workflow `foliage-magenta-urp-core.yml`. This proves the **software-GL Editor** rendering result, not Android graphics, thermal, FPS or complete ShaderGraph compatibility. Reimport merged files and test 2/3 GB Android devices before release.

---

# CURRENT MOBILE CORE AND UNITY EDITOR EVIDENCE — 2026-11-05, PR #68 / #69 MERGED

**These are newer than the older status sections below.** Both updates are saved on `main`; neither is a claim of measured Android FPS or a new native tree mesh bake.

- [PR #68](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/68), merge `94ced3f0696ca45ddbe8b222406810af5ee70c4a`: Six real SpeedTree `.prefab` core files (Conifer, Cypress, Pine A–D) each have exactly LOD2+LOD3 shadow casting disabled; near LOD0/LOD1 shadows and all four LOD silhouettes/receivers, improved v2 trunk/collider bounds, SpeedTree sources, TerrainData LFS objects, `.meta` GUIDs and scene bytes remain unchanged. A fail-closed historical Git-blob restoration test `Tools/World/tests/test_speedtree_far_shadow_current_core.py` verifies only 12 scalar flags were changed; four GitHub PR workflows SUCCESS. **Do not merge old draft PR #36 wholesale**: it contains stale pre-v2 prefab bounds and collider values.
- [PR #69](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/69), merge `deba5ae6b1a7d89173ed32cedbf75c1a5fbf09a0`: Real `Assets/AarisWorld/Scripts/AarisThirdPersonPlayer.cs` skips terrain/bridge SafeFooting checks for zero horizontal input, but retains shoreline checks on all movement, gravity, jumping, CharacterController.Move, camera and nearby-collider semantics. Source guard and C# syntax check added; four GitHub CI workflows SUCCESS. **Do not merge stale draft PR #35 without rebase/review.**
- AI Codespace recovery **succeeded after the asynchronous /tmp rebuild and Unity import completed**, despite an intermediate `blocked_incomplete_scratch_copy` status. Official Unity 6000.3.26f1 native GUI on Xvfb :12 loaded 4 Terrains, 7,508 real Terrain TreeInstances; native inspect near (120,75) returned Y=-10.2052 m, slope 4.7938°, tree identities and positions. [Readback workflow](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42007957319).
- Native Unity Editor produced a real 960×540 forest JPEG at (119,7,108) aimed toward (112,-8,65), SHA-256 `8693f18c5f3e1ba9acfb2b560258180a9915fb8a1c0c080e170db44dd1d63c2d`, in a **one-day ephemeral workflow artifact** [here](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42009310875). It shows bright magenta/pink foliage and sparse foreground. Existing tree materials reference `Assets/TerrainDemoScene_URP/ShaderGraphs/SpeedTreeURP_Branch.shadergraph` by GUID `d4fdc026464a42041be7fe785babd90e`. The screenshot could reflect software-OpenGL shader support/compilation rather than production color; **do not blindly recolor/reassign all shared materials**. Compare Android GLES3 render and shader diagnostics before editing actual material color or graph.
- The captured Unity GUI was running on an **isolated scratch copy from before the two GitHub merges**. The screenshot proves native Editor inspection/render of that snapshot, **not import/readback of the PR #68 or #69 merged bytes**. Original owner Codespace worktree remains dirty/protected and must not be reset, force-updated or overwritten. The branch merges saved tracked core files in GitHub; they did not require a Git LFS write because neither modified any LFS-tracked binary.
- Outstanding release gates: re-import latest merged `main` in a verified isolated Unity project, compare LOD0/1→LOD2/3 forest visuals, test shader errors/grass/house interiors, then collect GPU CPU/frame P95, memory/PSS and thermals on real 2 GB and 3 GB Android devices. **Do not advertise guaranteed 60 FPS or a finished commercial-grade world.**

---

# CURRENT MERGED RENDER CORE STATUS — PR #65, #66, #67 (2026-11-05)

**Authoritative current state:** Three exact, reviewed **native Unity core-asset** mobile rendering passes have been merged to `main`. Older handoff blocks below that still say these branches are pending review are historical; they do not describe current GitHub state.

- [PR #65](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/65), merge `a5554018366fc68473d01eaf547c0b4c8ee4f6ff`: `ProjectSettings/QualitySettings.asset` streaming texture budget 384→192 MB, shadow distance 100→72 m, renderer streaming updates 128→96, max file requests 64→24, and 17 building/landmark + 3 prop source prefabs with **only distant LOD2 MeshRenderer shadow casting disabled**. LOD0/LOD1 shadow casting, geometry, materials and colliders retained.
- [PR #66](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/66), merge `bcf76ab4210556c6eaad2c989033096796353417`: the actual expanded native `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity` has **101 far-LOD (LOD2) shadow caster flags** disabled. **202 near-LOD shadow caster flags** stay enabled. Other scene geometry, transforms, colliders and material bindings unchanged.
- [PR #67](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/67), merge `c8bae8c8a75bcd3ce51c374975fd0e558aca3f21`: actual `Fern_A`, `Fern_B`, `Fern_C`, `Heather_A`, `Heather_B` foliage-detail `.prefab` core files each have **exactly one m_CastShadows:1→0**; all five current `main` prefabs have been re-fetched and confirmed `m_CastShadows:0`, `m_ReceiveShadows:1`. Across 20 detail types, **18 do not cast realtime shadows and 2 larger bush types retain shadows**. Exact historical Git blob SHA1 reconstruction: `Tools/World/tests/test_detail_foliage_shadow_core.py`, seven of seven PR checks passed.

**No low-quality replacement meshes, gameplay scripts or runtime scaling wrappers** were introduced in these passes. The four native TerrainData files with 1,939 real tree scales merged earlier in [PR #64](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/64) remain unchanged; so do 5,564 rocks, 5 shrubs and `.meta` GUIDs. The terrain-detail prototypes listed in `Docs/TERRAIN_INDEX.json` have `useInstancing:1` in the captured index; the exact runtime effect of changed detail source prefab flags still requires Unity hardware render validation.

**Unmet release criteria:** Actual 2–3 GB Android phone FPS, memory/thermals, shader correctness, foliage/house visual quality, and distant landmark screenshots were **not measured**. Codespace Xvfb software OpenGL/Vulkan renderer crashes on scene render; passing GitHub checks is not a full GPU/device qualification. Do NOT promise 60 FPS, perfect graphics, or superiority to Free Fire/PUBG. Future work must use the exact reviewed core files + real hardware profiling, with guarded PRs; never blindly apply a generic bulk tree scaling to rocks or low-poly replacements.

---

# SECOND MOBILE RENDER CORE PASS — foliage detail shadow casters (2026-11-05)

Branch `ai/mobile-foliage-shadow-core-20261105`: *five true existing Unity prefab core files* `Fern_A`, `Fern_B`, `Fern_C`, `Heather_A`, `Heather_B` each changed **exactly one renderer shadow flag 1→0**, leaving meshes, leaves, materials, colliders, transforms, GUIDs, and shadow receiving untouched. All 20 detail prefabs audited: only prominent `Bush_A` and `Bush_Red` retain realtime shadow casting. Verify `Tools/World/tests/test_detail_foliage_shadow_core.py`, which reverses the flag and proves historical source Git blob SHA1 byte equality. Additional report: `Docs/MOBILE_FOLIAGE_SHADOW_CORE_20261105.md`. **No device FPS or actual Unity render verified yet; do not claim guaranteed 2 GB smoothness.** Do not change the prior main scene or merged PR #65.

---

# ACTUAL MAP SCENE LOD2 SHADOW CORE FIX — native serialized scene (2026-11-05)

**Branch `ai/mobile-scene-far-lod-shadow-20261105`, review pending:** The prior PR #65 had updated 20 model/prop source prefabs, but the actual scene is made from **expanded GameObjects**. A saved-scene audit found **101 active LODGroups with all 3 LOD levels casting shadows**. This upgrade changes **only the 101 farthest LOD2 MeshRenderer `m_CastShadows` flags** to 0 in real `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`, preserving all scene objects, 202 near-LOD shadows, materials, geometry, collision, placements and four merged TerrainData LFS objects. Source scene Git blob prior `ea741c769e1f13a992d734a23b0d355eabd6541e`; modified scene blob `84af0f04fd49a90ed25a978a34db9bc3c7bbdc38`. To audit, use `Tools/World/tests/test_scene_far_shadow_core.py` and the strict historical hash restoration in `Tools/World/verify_tree_house_upgrade.py`. More details in `Docs/ANDROID_2GB_RENDER_CORE_PASS_20261105.md`.

**This is actual serialized Unity map core editing, not a script that modifies meshes at runtime.** Still requires GPU-backed Editor import and 2–3 GB Android profiling. Do not claim measured mobile FPS. Keep owner Codespace original dirty worktree safe.

---

# CURRENT MAIN — mobile rendering core changes MERGED (2026-11-05)

**Verified merge:** [PR #65](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/65) merged to `main` at `a5554018366fc68473d01eaf547c0b4c8ee4f6ff`. Exactly **21 existing serialized Unity core assets** were changed: `ProjectSettings/QualitySettings.asset` streaming memory 384→192 MB, file I/O requests 64→24, renderer updates 128→96 per frame, realtime shadow range 100→72 m; 17 `Assets/AarisWorld/Models/*/*.prefab` and 3 `Assets/AarisWorld/Props/*/*.prefab` changed only their third/farthest LOD2 `MeshRenderer.m_CastShadows: 1→0`. Near LOD0/LOD1 continue casting shadows and all distant models remain visible. **No core meshes, `.unity` scenes, tree/rock TerrainData, `.meta`, house scale, collision, doors, windows or material textures were touched.**

**Validation:** 9/9 PR CI workflows SUCCESS on final head `a76cb7bcc9b0b96341acabe4ad80af662a3ab8e0`, including historical building mesh/LOD hash restoration, map explorer, SpeedTree source integrity, world automation, LFS preflight. Corrected `Docs/MAP_BUILD_REPORT.json` LFS hashes/sizes to the *already-merged* PR #64 tree-only TerrainData versions, preserving the native `.asset` bytes. Detailed reason, limits and reproducibility are in `Docs/ANDROID_2GB_RENDER_CORE_PASS_20261105.md`; static checks in `Tools/World/tests/test_mobile_render_core.py`. `AGENTS.md` previous prose below calling PR #65 unmerged is now historical.

**Not yet proved:** smooth/high FPS on real 2GB Android, visible quality versus other games, GPU/CPU frame times, memory or thermal behavior, actual 3D screenshot (Codespace Xvfb OpenGL and Vulkan previously crash), realistic interior / door / window dimensions, selective thick-trunk mesh baking. Treat these as next tested tasks and do not claim them completed. Preserve the existing 1,939 tree scales and 5,569 rock/shrub instances from PR #64. For future quality tiers, use real Android profiling before changing resolution, textures, silhouettes or stronger streaming budgets.

---

# Android 2–3 GB real serialized render-core budget pass (2026-11-05)

Review branch `ai/mobile-render-core-budget-20261105` directly reduces ProjectSettings texture streaming budget from 384 to 192 MB, renderer updates 128→96/frame, concurrent mip requests 64→24, shadow distance 100→72 m, while preserving full-resolution mip availability, LOD bias 1 and two shadow cascades. Across 17 existing structure prefabs and 3 existing prop prefabs, only the LOD2 MeshRenderer casts no realtime shadow; all near renderers, colliders, house dimensions, windows, doors, textures and LOD meshes stay intact. No game runtime wrapper is introduced. Full file-by-file specification and test: `Docs/ANDROID_2GB_RENDER_CORE_PASS_20261105.md` and `Tools/World/tests/test_mobile_render_core.py`. This is a proposed branch until merged; **never assert measured Android FPS / 2 GB compatibility or better visuals than commercial games without real device profiling**.

---

# CURRENT MAIN STATUS — PR #64 MERGED, REAL UNITY RENDER SCREENSHOTS BLOCKED (2026-11-05)

**Authoritative current state:** Owner explicitly requested merge; [PR #64](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/64) was **successfully merged to `main`**, GitHub-reported merge commit `4c6d9ccc60eb1263297b0d7caadc696d7c998957`. Its four Git LFS native TerrainData files contain saved tree-only scaling for **1,939 real trees**, while **5,564 rocks and 5 shrubs retain original scales**. Historical statements below saying PR #64 is unmerged are obsolete.

**Rendering/screenshot status:** Authentic post-merge 3D screenshots were **not produced** from this Codespace. The native Unity 6000.3.26f1 Editor on Xvfb `:12` uses non-accelerated Mesa `llvmpipe`; the URP SceneView and scratch camera render crash with `SIGSEGV / signal 11`. An OpenGL one-shot screenshot attempt (owner queue job `unity-map-forest-west-image-20261105-s02`, [run 41986025136](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41986025136)) failed without JPEG. A second attempt with software Vulkan/Lavapipe, `-batchmode -force-vulkan` (job `unity-map-forest-west-vulkan-20261105-s04`, [run 41986563098](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41986563098)) also crashed after scene import, reporting `meshVD.GetDataPtr() == NULL`. **Do not claim that game-view screenshots exist or invent rendered results.** For real screenshot verification, use a compatible GPU-backed Unity Editor/device (then inspect/compare screenshots and test Android RAM/FPS). Scratch-only attempted capture helpers remain in the owner job queue branch `ai/codespace-jobs`; not game runtime code.

---

# VERIFIED TREE-ONLY CORE ASSET FIX — CURRENT LATEST (2026-11-05)

**Use this section as authoritative for forest tree scale.** Previous notes about “all 7,508 trees” were discovered to be incorrect: Unity's TerrainData TreeInstance container holds **1,939 real trees, 5,564 rocks, and 5 shrubs**. The earlier whole-instance pass was quarantined; it was **replaced**, not merged.

## Verified deliverable
Unity **6000.3.26f1** in the owner's isolated `/tmp/aaris-unity-batch/project` ran an audited `AarisForestOneShot` *editor-only* authoring pass against the exact original LFS-hydrated baseline. It saved actual native Unity `TerrainData .asset` bytes for **all 1,939 real trees**, via species-aware, world-coordinate deterministic scaling. No runtime/compiler-time “make tree thicker” script is part of the delivered branch. `main` still has the old baseline; the updated native assets are on the review branch until PR is merged.

- Review branch: `ai/unity-batched-20261105-049503278c`
- Verified remote commit: `d2b827c7815e7b3027d23265f1477a84ce28d47a`
- Draft [PR #64](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/64), not merged; diff versus main is **exactly four LFS native TerrainData `.asset` files**, not scripts, metadata, scenes or materials.
- Licensed Unity saved each tile, checked native TreeInstance readback, and verified exact new SHA-256. Independent GitHub LFS pointer readback matched all four after the privileged uploader [run #41984006426](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41984006426), which returned `verified_github_batch_saved`, `count:4`, `codespace_acknowledged:true`, and `original_unmodified:true`.

| Tile | Actual trees saved | Rocks untouched | Shrubs untouched | New native .asset Git LFS SHA256 |
|---|---:|---:|---:|---|
| `Terrain_1_1` | 374 | 1,330 | 0 | `896b2d29b2d5b71afffe1f64a17863c8fa99cd06104c833b679ca117dd4d4609` |
| `Terrain_1_2` | 618 | 3,442 | 5 | `b92e9099868cabd8040db632d0cfac3c38075b2e292519b0edd8629723edecf8` |
| `Terrain_2_1` | 519 | 388 | 0 | `d26aa11e1e6bb8edc65ca52c8c3210d477711b091e86e7ead42e75407dcc29a3` |
| `Terrain_2_2` | 428 | 404 | 0 | `cfd96176947a1e75da285458ad6198ebf56a80195aa2138a5f202f5dc7f814e6` |
| **Total** | **1,939** | **5,564** | **5** | **4 verified LFS assets** |

The tree-only Unity plan [run #41982858123](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41982858123) classified prefab assets under `/Trees/`, `/Rocks/`, and `/Foliage/` and applied changes **only to tree indices**. **1,622 trees became wider** (mostly mature), **317 became slightly narrower** (younger/variation). Width/height factors are controlled by species, local tree-only neighbor competition, slope, and a deterministic per-tree hash. The total `sum(widthScale² × heightScale)` canopy-envelope proxy decreased approximately **2.1%** (approx. 8,949 → 8,760 across 1,939 trees). This is an approximate volume/overdraw *proxy*, NOT a verified 2 GB Android FPS improvement. Tree mesh topology, leaf materials, LOD/wind prefabs, tree count, coordinates, and GUIDs were kept intact. TreeInstance width scales the whole crown too; **selective trunk vertex baking has still not been completed**.

## Reproduce safely / QA remaining
1. Read `Docs/TERRAIN_INDEX.json` for **category inventory**, but be aware `Docs/TerrainInstances/*.jsonl` contain historical pre-upgrade width/height values; the **four new native LFS assets are authoritative** for final scaling. Regenerate those indexes only after a validated, fully LFS-hydrated remote Unity readback.
2. Owner-only staging/queue branch `ai/codespace-jobs` contains one-time, scratch-only `Tools/World/AarisForestCoreAuthoring.cs`, `AarisForestOneShot.cs`, and guarded job functions. The corrected actor knows `actualTrees`, `preservedRocks`, `preservedShrubs` and refuses a write on unexpected per-tile tree/rock/shrub counts. Source original `/workspaces/Unity-Game-Aris` is dirty and **must never be reset or overwritten**. Do not run a non-idempotent scaling pass again on the saved review assets.
3. The corrected Unity preview used queue job `unity-forest-1939-wide-trunks-plan-20261105-f33`, with final tile jobs `unity-forest-treeonly-apply-11-20261105-f34`, `...-12-20261105-f35`, `...-21-20261105-f36`, `...-22-20261105-f37`. `unity_sync_status` job `...-final-status-20261105-f38` returned `pending:4`, `pending_unity_commands:0`, `safe_to_push:true`. `unity_sync_save_session` job `unity-forest-treeonly-gitlfs-save-20261105-f39` delegated to the *separate* privileged Git LFS workflow above.
4. **Release gate not yet passed:** in a clean scratch/hydrated review-branch Unity project, verify final four native assets again, matched camera screenshots for forests/roads/hills, wind+four LOD transitions, physics/colliders, mobile device GPU frame times, memory and thermals, particularly a real 2 GB Android phone. GitHub PR audit workflow may show `action_required` because GitHub has not approved running it. Keep PR draft until visual/functional/device QA completes. Do not claim the result is visually better than any particular commercial game or guaranteed smooth on 2 GB phones.

**Older text below is retained as an audit trail, not the current tree-count or release status.**

---

# HISTORICAL QA HOLD — incorrect 7,508-instance attempt (now superseded)

**Historical only: Do not merge the invalid attempt at old commit `1c327d9`. That attempt is now superseded by verified tree-only commit `d2b827c`.** A read of the existing saved `Docs/TERRAIN_INDEX.json` discovered that the 7,508 `TerrainData.m_TreeInstances` are **not all trees**: 1,939 are true tree prefabs (`/Trees/`), 5,564 are rock prefabs (`/Rocks/`), and 5 are shrubs (`/Foliage/`). Tile breakdown: 1_1 = 374 trees + 1,330 rocks; 1_2 = 618 trees + 3,442 rocks + 5 shrubs; 2_1 = 519 trees + 388 rocks; 2_2 = 428 trees + 404 rocks. Previous bulk editor pass incorrectly scaled all 7,508; its four verified Git LFS blobs are a **quarantined review attempt, not a production-ready tree upgrade**. The user asked to scale **every tree**, not to resize rocks/shrubs.

**Required before release:** restore the original four TerrainData baseline blobs in a guarded scratch Unity project, run a corrected species/prefab-aware plan *only* on the 1,939 actual trees, prove all 5,569 other instances retain their previous exact numeric scales/positions/prototype identities, and save four new verified LFS native assets on PR #64. Do **not** blindly rerun non-idempotent scaling on already-mutated review assets. `main` currently has not received these bad bulk core files. The 7,508-tree assertions in the historical handoff immediately below describe the **discovered error**, not an accepted result; do not use them as planning counts.

---

# Verified FULL-MAP native tree scaling handoff — 7,508 trees (2026-11-05)

**IMPORTANT latest state:** Unity 6000.3.26f1 successfully edited **all 7,508 existing Terrain TreeInstances in all four native TerrainData `.asset` files** inside the owner's isolated scratch Unity project, *not merely one or two example trees*. Native SaveAssets, post-write in-Editor readback, exact SHA-256 and Git LFS upload of **all four** core files were independently verified. GitHub **review branch** `ai/unity-batched-20261105-049503278c` at commit `1c327d978d82d3647194c41ac32eb1bb169c9282` contains the four changed core assets; [draft PR #64](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/64) is **NOT merged to main**. Do not falsely treat main as updated, and do not rerun a non-idempotent forest scaling pass onto an already scaled branch.

## What was physically saved

Four tiles, exactly **7,508 changed native tree instances**, without inserting/removing trees, altering tree positions/prototype IDs, replacing existing high-detail SpeedTree models, editing scenes or modifying .meta GUIDs. The per-instance `widthScale` and `heightScale` vary deterministically by world coordinate, tree species, age class and local neighbor competition/slope. Distribution in actual Unity preview: **5,639 mature**, **1,347 younger**, **522 landmark** trees (approximately 75/18/7 percent). No added geometry/polygons or new runtime tree scaling script. Existing SpeedTree wind, leaves and LOD prefab meshes are retained. A bounded canopy-envelope proxy (`sum(widthScale² * heightScale)`) fell from approximately 16,952 to 12,780 across the four tiles; this is **not measured GPU overdraw, FPS or guaranteed 2 GB Android performance**.

| Native TerrainData core path suffix | Trees saved | Original SHA-256 | New SHA-256 |
|---|---:|---|---|
| `Terrain_1_1_4bf22c8f-eb55-436d-84e3-dedfa85665b1.asset` | 1,704 | `4798dfe0edf6cec43be1417e519271fbc4b98b99de553a981195e13c321714ae` | `17522c8e230240894e76d08fd483992e63ebd06a2a767486ab1a91a404820857` |
| `Terrain_1_2_1694bb0f-cffe-402c-b6f9-cf47692fbb78.asset` | 4,065 | `9053935547655ccf39744e0b5ab475514598734bdffcf19f4f1760a452b559e4` | `4a1c4577f690a0bfea4748e38b4049dec6c3d49137149b601fa3fd162e543d2c` |
| `Terrain_2_1_82fc4922-5564-4a18-858e-787f6d901556.asset` | 907 | `9aa00e637163f52f559683eb837e12799f39f499bcd16535d60838d49f8d5f65` | `d10d4cb2a92f86ab8718c5f27cdfb1a750a90a0fcc9fdf1ad1e1897a5fe3631b` |
| `Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset` | 832 | `be8b587035c201a5b24f6bfb513201d562ae99699a0ec7a0d96f7e16290fa34e` | `0a6c967a5bd1e0a73c05f759b1d599ec26d370759d399d5152f2180eab9051cc` |

All paths begin with `Assets/TerrainDemoScene_URP/Terrain/Data/`. GitHub API readback of all four Git LFS pointers **exactly matched** the new SHA-256 values above. Git LFS upload [run 41979969587](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41979969587) returned `verified_github_batch_saved`, `count:4`, `codespace_acknowledged:true`, `original_unmodified:true`.

## Exact repeatable, protected owner workflow

1. Read this AGENTS file and prior section below. Only operate on repository `Aaris-khan-don/Unity-Game-Aris`. The owner-only queue branch is `ai/codespace-jobs`. Submit **exactly one new** `.aaris/jobs/<unique-id>.json` per commit and check matching "Aaris Codespace On-Demand Terminal" run's machine-readable `AARIS_RESULT_JSON`. Do **not** submit multiple jobs in one commit. Preserve dirty original `/workspaces/Unity-Game-Aris` and its LFS.
2. A one-time authoring helper (only in owner queue/scratch; **not part of game deliverables**) exists at `Tools/World/AarisForestCoreAuthoring.cs` and `Tools/World/AarisForestOneShot.cs` on `ai/codespace-jobs`. The dedicated scratch Unity session can crash from **SceneView/OpenGL SIGSEGV** during repaints. Avoid repeated GUI operation on that render path. Safe one-shot licensed Unity Editor opens `/tmp/aaris-unity-batch/project`, runs `Aaris.WorldAutomation.AarisForestOneShot.Execute` using reviewed env values and exits before heavy SceneView repaint; it is an editor authoring operation, **not an imported game runtime modifier**.
3. The full-map preview was **successfully run** by queue job `unity-forest-oneshot-all-plan-20261105-f22`, [run 41978680293](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41978680293), via `{"operation":"unity_forest_one_shot_plan","args":[]}`. It found 4 tiles, 7,508 trees and reported original per-tile SHA-256. **Do not reapply blindly:** compute a fresh plan against the exact intended current baseline. One-shot mutations require tile key and the exact `beforeSha256` (`{"operation":"unity_forest_one_shot_apply","args":["1_1","<64-char-sha256>"]}`). Fail on stale SHA, unresolved tile, missing .meta or working-copy conflict. Jobs `unity-forest-native-apply-tile11-20261105-f23`, `...tile12-20261105-f24`, `...tile21-20261105-f25`, `...tile22-20261105-f26` completed one native tile each. Each checked every tree's prototype, position and final scale in Unity and saved a new native asset SHA.
4. Before sync, `unity_sync_status` (job `unity-forest-all-7508-sync-status-20261105-f27`, [run 41979883515](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41979883515)) reported `pending:4`, `pending_unity_commands:0` and `safe_to_push:true`. The strict batching validator in `Tools/World/unity_batched_autosync.py` on `ai/codespace-jobs` includes `forest_apply` in its *bounded successful native mutation* allowlist. Submit `unity_sync_save_session` as an owner queue job with commit message beginning exactly `Unity Batch Save:`; the privileged "Unity AI Automatic Verified Git LFS Session Save" workflow actually pushes and independently validates the four LFS assets. The sample real save used job `unity-forest-all-7508-gitlfs-save-20261105-f28` and receipt above. Always wait for the **privileged** receipt; merely seeing the queue worker return "delegated" is not a successful GitHub upload.
5. For next changes, use the new **four-file Git LFS review branch** as baseline. Because the branch is behind main, reconcile with current main while preserving all four asset blobs; never force-push or overwrite dirty source. Before merging PR #64, require a LFS-hydrated Unity import of saved remote assets and matched before/after screenshots for forest, road, village, slope; validate terrain tree counts/placement, materials, wind, collision, LOD and Android device FPS/memory/thermal budget. Latest "Read-only world context audit" on PR was `action_required` (run 41980085610), **not a passing check**. Keep review draft until remaining independent checks are satisfied.

**Clear limit:** A `TreeInstance.widthScale` edit enlarges/shrinks entire tree, **including its canopy**, even though it is saved to the real TerrainData core file. **Selective thicker trunks/branch geometry is not baked into source SpeedTree mesh yet.** Draft importer-only PR #63 is not a substitute. Do not advertise the visual result as better than PUBG/Free Fire or 2 GB smooth until tested on actual Android hardware.

---

# Verified native core TreeInstance edit + LFS handoff (2026-11-05)

**Real successful example, not a synthetic workflow:**

1. GitHub owner queue submitted `unity_virtual_gui_status` job
   `unity-core-tree-status-20261105-r11`: Unity 6000.3.26f1 Scene
   loaded with 7,508 native trees
   ([run 41969663382](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41969663382)).
   `unity_sync_dry_run` initially returned `no_changes`,
   `pushed:false` ([41970219166](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41970219166)).
2. `unity-native-forest-inspect-20261105-r14` used
   `unity_virtual_live` with
   `{"action":"inspect","cameraTarget":{"x":120,"y":0,"z":75},"radius":95,"limit":40}`
   and returned real native `terrain-tree:GlobalObjectId...:index`
   IDs, exact `expectedPosition`, `widthScale`, `heightScale`,
   and `sourceAsset`. See
   [run 41970371200](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41970371200).
3. `unity-native-tree-710-mature-20261105-r15` invoked
   `unity_virtual_live` using `action:"scale_tree"` with tree
   index **710**, `scale:{"x":1.10,"y":1,"z":1}`, and
   the exact previous position `(97.196,-11.720,75.802)`.
   Unity reported saved
   `Assets/TerrainDemoScene_URP/Terrain/Data/Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset`;
   width `0.8439 -> 0.9282901`, height stayed `0.8593`.
   Separate job `unity-native-tree-710-verify-20261105-r16`
   independently re-read the exact value in the Unity Editor
   ([41970674238](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41970674238)).
   Second Unity edit `unity-native-tree-573-mature-20261105-r17`
   saved index **573**, width `0.8609 -> 0.9555990` and
   height unchanged `0.8896`
   ([41970787240](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41970787240)).
   Independent `unity-native-tree-573-verify-20261105-r21` readback
   confirmed the saved width `0.9555990`, original position and
   height `0.8896` in the real Editor
   ([41971374870](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41971374870)).
   These are *saved whole-tree width instance edits*, NOT selective
   baked trunk meshes.
4. `unity_sync_watch_start` returned `watch_already_running`.
   `unity_sync_status` returned `changes_pending`, 1 tracked
   TerrainData asset, 0 queued commands, safe_to_push true
   ([41970968091](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41970968091)).
5. Commit exactly one job
   `{"id":"unity-native-core-save-20261105-r20","operation":"unity_sync_save_session","args":[]}`
   with commit title starting `Unity Batch Save:`.
   Do NOT treat the delegate workflow as completion. The **privileged**
   Git LFS writer completed
   [41971035263](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41971035263)
   with `verified_github_batch_saved`,
   `codespace_acknowledged:true`, `original_unmodified:true`,
   **1 native asset**, review branch
   `ai/unity-batched-20261105-049503278c`, commit
   `bdfd20d297475e4c01bdf8b10bd38675da404edf`.
   Read-back GitHub LFS pointer for that tracked `.asset`:
   new SHA256 `be8b587035c201a5b24f6bfb513201d562ae99699a0ec7a0d96f7e16290fa34e`
   versus main `113c4b11ab5f7e6cba20f60a6b8bbc061d0f72d335827d48c98fff855a7faf07`.
   Draft [PR #64](https://github.com/Aaris-khan-don/Unity-Game-Aris/pull/64) is
   **not merged**; it is the native core save review, not a global tree bake.

**For a new AI:** repeat the guarded native Editor inspection/edit/readback,
explicit Save Session and verified LFS writer receipt. The **user's larger
requirement remains unmet**: bake species-aware bark/trunk meshes into actual
Unity mesh core assets for the full map, with preserved SpeedTree UV/wind/LOD
semantics and exact prefab mesh references, then extend reviewed LFS
authoring if new `.asset`/`.meta` identities are needed. Never substitute
an importer-only PR or global TreeInstance scaling and claim it is full
baked mesh geometry. Do not blindly merge PR #63 or #64 without native
Unity and LFS semantic/collision validation.

---

# PRIMARY RULE — EDIT AND SAVE REAL UNITY TREE CORE ASSETS (2026-11-05)

**User requirement (highest priority for tree geometry work):** Do not
deliver a code-only/importer-only change and call it a map tree upgrade.
Perform authoring inside the **real running Unity Editor**, save actual
native **core asset** bytes, verify Unity readback and then Git LFS-sync
those reviewed bytes to GitHub. A Python/C# helper may orchestrate a
one-time editor operation, but the delivered art must remain in
`.asset` / `.prefab` / `.unity` or original editable SpeedTree source
files, not depend on a new compile/import-time "make trunk thicker"
script. Do not change the game at runtime just to simulate a baked mesh.

## Existing AI-to-Unity route (read carefully; no phone/noVNC needed)

- Owner repo: `Aaris-khan-don/Unity-Game-Aris`, branch `main`.
  The owner-only job queue is **separate** branch `ai/codespace-jobs`;
  `.github/workflows/ai-codespace-on-demand.yml` stages the reviewed
  executor and uses owner Codespace `musical-carnival-jjxp9r6vw45wfjgvg`.
  No arbitrary shell command is authorized through this queue.
- Editor tested **2026-11-05**: Unity `6000.3.26f1`, normal licensed GUI
  on Xvfb `:12`, scratch copy
  `/tmp/aaris-unity-batch/project`, working scene
  `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`,
  **4 Terrains, 7,508 native Terrain TreeInstances**. This is a
  timestamped observation, not a promise the Editor still runs later.
- The original `/workspaces/Unity-Game-Aris` contains important
  owner-modified/untracked files and very little persistent free disk.
  Never reset, clean, overwrite, copy scratch blindly into it, move the
  project to /tmp by symlink, delete Unity Library, force-push, rehydrate
  all Git LFS, change paid machine type or rebuild it without a verified
  recovery plan. Scratch /tmp **disappears on Codespace STOP**.
- Exactly **one** JSON job per GitHub commit:
  `.aaris/jobs/<new-unique-id>.json` on `ai/codespace-jobs`.
  Format: `{"id":"new-unique-id","operation":"unity_virtual_gui_status","args":[]}`.
  Wait for the matching "Aaris Codespace On-Demand Terminal" Actions
  run and parse its `AARIS_RESULT_JSON` before posting the next job;
  queue concurrency does not mean multiple edits are safe.
- Read-only checks: `unity_virtual_gui_status`, `unity_session_status`,
  `unity_sync_status`, `unity_sync_dry_run`, `unity_scratch_reconcile`.
  `unity_session_recover` can re-open/re-import scratch when safe.
  A native `unity_virtual_live` request uses a **single short JSON
  argument**. Supported actions include `inspect`, `move_tree`,
  `scale_tree`, `capture`; use exact native tree ID and
  `expectedPosition` from a *fresh* inspect for mutations.
  After every write, get `unity_virtual_result` if pending, and
  separately `inspect` exact saved coordinates before trusting success.
- **Critical distinction:** `scale_tree` saves a native TerrainData
  `.asset` width/height-scale change, which ALSO changes canopy width.
  It is **not** selective bark/trunk mesh geometry authoring. Existing
  `AarisTreeShapeImporter.cs` + six reviewed `.st.meta` profiles
  thicken bark at import time; a version bump in that importer by
  itself is **NOT** the user's requested persistent core geometry bake.
  Code-only draft PR **#63** is not evidence of a saved mesh upgrade.
- For genuine selective trunk shape, use the Unity Editor to create and
  validate persistent *mesh asset geometry* (or change true original
  SpeedTree source) and link matching LODs/prefabs, preserving material
  slots, vertex attributes, SpeedTree 8 UV wind/LOD morph channels,
  collider, hierarchy, tree prototype references and GUID integrity.
  **Do not claim a baked mesh until the actual mesh bytes and prefab
  references are committed and reloaded successfully in Unity.**
  New `.asset` + `.meta` pairs are NOT supported by the current
  strict batched writer: add a separately reviewed, fail-closed writer
  path with exact GUID/allowlist/backup/source SHA validation before
  trying to upload them. Do not bypass this by committing fake
  pointers, transient Library meshes or an Editor-only script.
- Save sequence for **currently supported tracked** native core files:
  run `unity_sync_arm` / `unity_sync_watch_start` as needed; verify
  `unity_sync_status`, `unity_sync_dry_run`; then send
  `unity_sync_save_session` in one job with commit message starting
  exactly `Unity Batch Save:`. The first workflow only **delegates**;
  verify the separate privileged "Unity AI Automatic Verified Git LFS
  Session Save" workflow's
  `verified_github_batch_saved` receipt, remote branch SHA, LFS OIDs
  and intended changed-file diff before reporting GitHub sync success.
  It pushes to a **separate review branch**, never overwrites dirty
  original files and does **not** auto-merge.
- Read `Docs/UNITY_TMP_AI_HANDOFF.md`,
  `Docs/UNITY_AI_NO_VNC_VERIFIED_20261105.md`,
  `Docs/UNITY_BATCHED_AUTOSYNC.md`,
  `Tools/World/unity_batched_autosync.py`, and the strict workflow
  `.github/workflows/unity-batched-github-upload.yml`.
  Test before/after camera images at the same positions, native
  save/readback, tree collision and 4 SpeedTree LOD transitions; report
  Android GPU/FPS only after an actual device test. Prefer controlled
  mature-tree variation over multiplying all 7,508 widths globally.

**Evidence at handoff:** Native Editor live/scene loaded, PID 5599,
original untouched: GitHub Actions
[41969663382](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41969663382).
Batch sync status clean, no pending assets:
[41969849999](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41969849999).
Native core dry-run returned `no_changes` and `pushed:false`:
[41970219166](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41970219166).
**Those checks prove a working control route, not that a new baked
tree-geometry core file has been produced or synced.**

---

## Tree trunk realism v2 — six reviewed native SpeedTree prototypes (2026-11-05)

**See `Docs/TREE_REALISM_V2.md` and
`Tools/World/tree-realism-v2-reviewed.json` before editing trees.**
Six existing SpeedTree import profiles now use stronger natural lower-trunk
taper (+10-12% horizontal base width), only 3-4% crown broadening,
unchanged heights and four LOD transitions. Their prefab BoxColliders
and LOD bounds were adjusted together to avoid mismatched visual
trunks and physics. `AarisTreeShapeImporter.GetVersion()=2` causes
Unity to reimport source SpeedTrees while preserving wind/morph UVs
and normals/tangents. **Source .st files, native TerrainData
instances, scenes, materials and prefab .meta GUIDs are untouched.**

The standalone `verify_tree_realism_v2.py` and unchanged historical
tree/house checks must pass before merging. A SOURCE check does
NOT replace real native Unity Editor import, camera rendering,
collision and mobile FPS checks; do not claim those before testing.
Avoid making all 7,508 TreeInstances globally wider: that fattens
crowns as much as trunks. Use the existing import-time graduated
mesh taper plus species-aware prefab colliders.

---

## START HERE — Unity AI Safe Batched Git LFS Save (2026-11-05)

**New AI workflow:** `Docs/UNITY_BATCHED_AUTOSYNC.md`.
Unity Editor C# commands save native `.asset` / `.unity` data in
`/tmp/aaris-unity-batch/project`; this does NOT survive Codespace STOP.
GitHub saving is done in BATCHES: 180 seconds of edit silence
or 600 seconds of continuous work, never per individual tree.
AI can invoke `unity_sync_save_session` via a new owner job
under `.aaris/jobs/<id>.json` on branch `ai/codespace-jobs` with
Git commit message starting exactly `Unity Batch Save:`.
The privileged workflow `.github/workflows/unity-batched-github-upload.yml`
uses GitHub Actions `GITHUB_TOKEN` to copy only SHA-256-verified
Unity saved Assets from TMP and commit to a separate Git LFS review
branch, not the dirty original `/workspaces/Unity-Game-Aris`.
Verify the privileged workflow's remote commit and receipt;
the ordinary terminal action merely delegates the upload.

Codespace Git auth probe returned `git_credentials_unavailable`;
the Codespace watcher journals pending data but does not Push.
A scheduled Actions writer checks approximately every ten minutes
ONLY if the same Codespace is already running. No stop hook is a
guaranteed last-minute backup. Send Save Session explicitly before
finishing valuable edits or risking Codespace stop.

**Restart caveat:** An unmerged review branch must be restored
to the new Unity TMP project or merged through normal Git LFS.
Do not claim automatic restoration of unmerged assets has been
proven while Codespace lacks Git read credentials. Never delete
or overwrite the owner's existing source Assets or `.meta` files.

---
## START HERE — Unity /tmp and Codespace shutdown handoff (2026-11-05)

**Read `Docs/UNITY_TMP_AI_HANDOFF.md` before touching the Unity
Editor, /tmp, original assets or Codespace lifecycle.** This is the
single concise operational map for the next AI, including actual
working directories, job JSON schema, license-safe hidden Xvfb
Editor, 7,508 trees, screenshot retrieval and Git LFS safety.

Official GitHub behavior: **/workspaces persists** across
stop/start and rebuild, but **/tmp is wiped on Codespace STOP**,
and all running Unity processes end. Existing Unity Personal
Editor is installed in the container's /home and survives stop/start
but not necessarily a container rebuild. On restart, refuse to reopen **partially copied /tmp assets** without
verified Unity scene readback or an atomic, original-source-fingerprint
scratch-copy completion marker. The checkpoint JSON
under /workspaces saves scene/version/source fingerprints and last
AI-inspected camera target; it is NOT an imported Library backup.

For a previously stopped Codespace, the owner-authorized GitHub
Actions workflow on `ai/codespace-jobs` can wake the SAME named
Codespace, then `unity_session_recover` safely reopens or recreates
the TMP Unity copy. Run `unity_session_stop_simulation` if a
nondestructive rehearsal is needed: actual
[41954790293](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41954790293)
returned `recreate_scratch_and_reimport` and remembered the
camera position without stopping the live process.

**Do not assume immediate, cache-preserving restart until adequate
persistent disk or an authenticated external Unity Library cache
exists.** Do not stop a working Editor to test this, replay past
tree mutations, overwrite original Core Files, rebuild a dirty
Codespace or modify charged machine type without approval.

---

## Unity restart-safe checkpoint and AI recovery (2026-11-05)

**Never assume /tmp survives Codespace STOP.** GitHub clears /tmp on
stop; the original /workspaces/Unity-Game-Aris project survives.
Running Editor PIDs never survive stop. The successful no-VNC
Unity session used /tmp scratch, therefore its large imported
Library is NOT restart-persistent.

New read-only preflight: `python3 Tools/World/unity_session_checkpoint.py`.
Small durable JSON after a valid live scratch scene:
`python3 Tools/World/unity_session_checkpoint.py --checkpoint`.
File lives under persistent
`/workspaces/.aaris-world-bridge/ondemand/unity-session-checkpoint.json`,
never inside Assets/Library. It records pinned Scene and core source SHA
fingerprints, not imported assets or token data. The reviewed queue
operation `unity_session_recover` should, on the next authorized
Codespace AI job, reuse an existing Unity Editor, reopen a compatible
scratch Library if still present, or restart safe scratch copy+import
if /tmp was cleared. It may NOT replay previous mutating commands,
overwrite any dirty source files or claim an instant exact resume.

An on-demand AI job can auto-wake the *same* stopped Codespace through
the existing owner GitHub Actions queue, but an untriggered Codespace
tab opening does NOT run an AI job by itself. Do not change/rebuild
devcontainer startup hooks on the user's dirty machine.
See `Docs/UNITY_AI_RESTART_RECOVERY.md`.

---

## Verified scratch-to-original Unity core diff (2026-11-05)

Run `python3 Tools/World/unity_scratch_reconcile.py` to compare the real
original project at `/workspaces/Unity-Game-Aris` against the temporary
Unity-opened scratch project at `/tmp/aaris-unity-batch/project`.
This **read-only** tool SHA-256 checks selected `.asset`, `.unity`,
`.prefab`, `.mat`, `.cs` and matching `.meta` paths, marks
owner-modified/untracked files and **never promotes or writes** changes.
It has strict path/symlink/file-count/size guards and CI tests.
On the original Codespace its verified output showed **4 identical,
2 different, 2 missing** selected paths: the scene and main `.meta`
matched, but the scratch native TerrainData `.asset` serialized differently
even after the test tree position/scale were restored; the scratch
AI Bridge had a deliberate isolated control-root patch; and the temporary
`AarisBatchProbe.cs` exists only on scratch. **Never overwrite the original
TerrainData or AI bridge with these scratch copies.**
See [real Codespace audit](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41950632194).

---

## 2026-11-05 VERIFIED — AI-controlled native Unity Editor without noVNC

**Read this newer result before the historical 2026-11-04 blocked-import notes below.**
The actual Unity **6000.3.26f1 graphical Editor** was launched with an
invisible Xvfb display :12 (NOT headless `-batchmode`, no phone/noVNC).
On the existing Codespace, the **scratch project copy**
`/tmp/aaris-unity-batch/project` loaded
`Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity` in Unity:
**4 Terrains, 7,508 native terrain trees, 84 Prefabs, 256 Materials**.
The Editor Bridge's `inspect` returned real terrain/nearby-tree positions,
slope and native IDs; `move_tree` saved an exact 1m change to the native
TerrainData, independently verified it and reversed it. `scale_tree` saved
+10% tree width, reversed it and independently verified original scale.
A **real URP Camera JPG** was rendered, downloaded from a 1-day
private GitHub Actions artifact, and visually inspected by AI.
**ALL edits and imports were on /tmp scratch only**, not on the original
dirty /workspaces game project; test edits were restored.

The tested controller operations currently reside on the dedicated
`ai/codespace-jobs` branch, NOT all merged to main:
`unity_virtual_gui_launch`, `unity_virtual_gui_status`,
`unity_virtual_live`, `unity_virtual_result`, `unity_virtual_frame`.
Wait for each Actions run + result before submitting the next unique
`.aaris/jobs/*.json` job. A virtual X11 display is needed for normal
Unity Personal licensing but **VNC is not needed**. The `-batchmode
-nographics` experiment failed with missing
`com.unity.editor.headless` entitlement; do not repeat it.

**CRITICAL LIMITATION:** /tmp is NONPERSISTENT and the original Codespace
persistent disk had only 0.355 GiB free. If Codespace stops, the
successful scratch Unity import cache disappears. Do NOT claim
restart-safe caching, do NOT write promoted core assets into the original
working tree, and do NOT reset its modified/untracked files. Permanent
Git LFS PR promotion from scratch is not yet implemented/verified.

**Full verified audit, run links and API examples:**
`Docs/UNITY_AI_NO_VNC_VERIFIED_20261105.md`.

---

## Unity full-Editor image and targeted LFS sync (2026-11-04)

**No graphics downgrade:** keep complete official Unity 6000.3.26f1,
URP/VFX Graph 17.3.0, Terrain and every saved asset. Optional (NOT
yet built or deployed) image config is under
.devcontainer/aaris-unity-image/devcontainer.json. It bakes the Editor
into an image layer during build, avoiding a separate writable-layer
Editor installation on a fresh Codespace. Do NOT rebuild the existing
dirty Codespace until its source and Library are safely backed up and
a new image has been smoke-tested. See Docs/UNITY_LEAN_IMAGE_LFS_SYNC.md.

AI may run read-only python3 Tools/World/unity_lfs_preflight.py to
check exact Unity version, Editor binary and LFS hydration. Present
LFS files are never fetched again. The explicit --hydrate-missing
command only allows at most 12 clean missing files, 512 MiB of LFS,
exact HEAD OID validation and >=8 GiB persistent free disk. It
must NEVER reset uncommitted assets or the paused Import.


---
## OverlayFS and RAM safety (verified 2026-11-04)

The exact Codespace /dev/shm capacity is **64 MiB**, not 8-16 GiB; it cannot hold a multi-GiB Unity PackageManager. Read-only probe result: https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41870345402 . The separate /tmp filesystem has ~101.63 GiB free but it is nonpersistent; never move active Unity Editor/PackageManager, Assets, Library, or .meta into it and leave a persistent symlink. Current Unity process 40121 is paused with 0.585 GiB free. Do not resume it at this capacity.

OverlayFS lower layers are immutable: removing files with rm -rf from a running container masks them and need not reclaim base-image bytes. To really slim the image, review a **new devcontainer/Dockerfile base** and rebuild only after an owner-approved backup/recovery plan for all Unity Editor files and dirty workspace changes. Keep the current Codespace's worktree and Library intact. Future agents: call owner-only `layered_storage_probe` with empty args to recheck actual mounts and capacity. Full recovery procedure in `Docs/CODESPACE_OVERLAY_RECOVERY.md`.


---
### Native Unity low-disk guard (2026-11-04)

The Codespace launch controller now refuses a first Unity import unless at least **8 GiB** is free on the persistent project filesystem, or a restart with a retained partial Library unless at least **4 GiB** is free. A watchdog checks real free space while Unity runs and uses `SIGSTOP` on the verified Unity process/session below 1.5 GiB instead of relying on delayed SIGTERM; this preserves current source files and the partial Library. The Editor status includes `paused_pids`. A paused Editor is **not** a loaded/interactive map.

After obtaining sufficient **persistent** disk, the owner may issue the argument-free `unity_resume_paused` operation to continue the same live process; it refuses to resume below 4 GiB and reinstalls its watchdog. If the Codespace was stopped and the PID no longer exists, use `unity_gui` to reopen the *retained* Library instead. The 32 GiB-only machine options observed for this account mean this may require a different persistent environment or available storage policy change. Never delete the project Library/Assets or regenerate/re-fetch intact Git LFS assets to make room.

---

## 2026-11-04 verified Unity Terms and low-disk recovery

- Work on the existing Codespace musical-carnival-jjxp9r6vw45wfjgvg only. Preserve ALL intentionally modified and untracked source/core files, including any Unity-generated ProjectSettings and live bridge sources. Never reset, git clean, re-clone, delete Library or re-fetch the 764 already-verified Git LFS assets.
- The owner explicitly authorized acceptance of Unity 6000.3.26f1 Editor Software Terms. The exact X11 Unity terms dialog was accepted and its disappearance verified: [run 41855189075](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41855189075).
- Real Unity import started, including native materials, prefabs and textures; the Library grew beyond 2.6 GiB. Import and C# compilation remain unfinished. The map SceneView is NOT verified loaded; no native tree move/capture/readback may be claimed.
- Persistent /workspaces has 32 GiB total; free space dropped to 0.585 GiB. A bounded SIGTERM request did not terminate Unity. A guarded SIGSTOP paused its own process group 40121, confirmed by real ps state T<sl: [run 41858218549](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41858218549). Library is intact. Do not resume without more *persistent* disk capacity.
- Actual owner Codespaces machine-options API [run 41859040745](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41859040745) offered ONLY basicLinux32gb (2 cores, 32 GiB) and standardLinux32gb (4 cores, 32 GiB): no higher persistent-storage tier is currently available in this account. GitHub documents that /tmp is cleared whenever the Codespace stops ([official docs](https://docs.github.com/en/codespaces/developing-in-a-codespace/persisting-environment-variables-and-temporary-files)); NEVER move the permanent Unity Library to /tmp as a purported restart-safe fix. A larger account-supported tier/policy or external persistent development environment is needed. Do not change paid resources without explicit owner approval. Codespace stop destroys the paused process/RAM but preserves the Library under /workspaces.
- The ai/codespace-jobs branch presently includes tested one-purpose Unity terms confirmation, staged Python world-site sensor fallback, guarded unity_low_disk_pause and unity_resume_paused operations. These extra operations are NOT in main at this checkpoint; read queue branch code before using. The resume operation requires at least 4 GiB free and only continues a matching Unity process group.
- Read-only world-site sensing succeeded from the reviewed staged Python source: [run 41856938356](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41856938356). Source-file coordinates and native TreeInstances are not Unity-rendered pixels or collision tests.
- IMPORTANT queue discipline: push exactly ONE new .aaris/jobs/<unique-id>.json job per completed Actions workflow and matching result artifact. GitHub Actions permits one running and one pending per concurrency group; further job pushes can CANCEL a previous pending run, even when cancel-in-progress is false. Do not assume FIFO. Retry cancelled work with a fresh unique ID.
- After persistent disk expansion, verify free space and worktree; restore private desktop on the same Codespace; resume/restart Unity using the retained Library, finish compile and exact TerrainDemoScene load; perform native inspect, small reversible tree move/scale plus saved core readback and true camera screenshot. Keep screenshot artifacts short-lived, not committed to Git.

---
**If Unity GUI hangs before Library import:** do NOT claim that a Unity PID
means the map is open. Use owner Actions `unity_diagnostics` (no args) to
inspect Unity logs, process state, X11 windows, import cache and pending bridge
jobs. If `xwininfo`/`scrot` are unavailable, the `desktop_tools` (no args)
operation installs only x11-utils + scrot with a disk guard. A
`desktop_snapshot` (no args) captures the actual current Xvfb `:12` screen
into a **one-day private Actions artifact** (without Git commits); the source
image is deleted after validated transfer. This X11 screenshot works even if
the Unity Editor has not finished importing and is preferable to guessing what
dialog is blocking startup. Read its artifact before changing Unity lifecycle.
Never upload Unity project files or private passwords as screen artifacts.

# Persistent Unity Editor and native live map editing (2026-11-04)

Use the **owner-only GitHub Actions job queue** (`ai/codespace-jobs`, `.aaris/jobs/<unique-id>.json`) for Codespace commands; never Issue #37. Details: [Docs/UNITY_LIVE_EDITOR.md](Docs/UNITY_LIVE_EDITOR.md).

1. `unity_gui` with `args:[]` starts the actual Unity Editor 6000.3.26f1 on existing Xvfb `:12` / noVNC `:6080`, when not already running, with `-projectPath /workspaces/Unity-Game-Aris`. It **retains** on-disk `Library`, project files, `.meta` and local uncommitted core edits. A disk watchdog requests shutdown if free space falls below 1 GiB; a first launch requires at least 3 GiB. Codespace stopped → Actions starts Codespace first; Editor itself cannot execute while its container is stopped.
2. Reviewed `Assets/AarisWorld/Editor/AarisLiveEditorBridge.cs` and matching stable-GUID `.meta` are transferred to a temporary Codespace staging folder, then **only created if absent or identical**; any locally modified version causes a conflict rather than overwrite. Unity imports scripts normally. In-Editor requests/responses are outside the Git worktree under `~/.aaris-desktop/unity-commands` and `unity-results`.
3. `unity_live` accepts a **single JSON string in `args`** with only structured `action`: `inspect`, `move`, `scale`, `move_tree`, `scale_tree`, `capture`, `status`. The command ID is the job's ID. No arbitrary shell, paths or build-time resizing instructions. `inspect` returns object IDs, nearby scene objects, native Terrain trees, dimensions, ground elevation/slope, and distances. Transform changes use Unity's APIs and save the actual `.unity` scene; native tree changes edit/save the original TerrainData `.asset`, with a previously observed position precondition. The **core file on disk changes**, not just the build output.
4. If a `unity_live` response says `pending:true`, the request was queued but the Editor has not yet replied (for example during first import or domain reload). Request `unity_result` with `args:["<original-job-id>"]` to retrieve the durable result. On a Codespace restart the next job can restart Unity and the queued command survives on disk.
5. `capture` renders the real loaded Editor scene from explicit camera position/target and writes a JPEG only under `~/.aaris-desktop/frames` (never into Git). `unity_frame` with `args:["<capture-job-id>"]` puts it into a **one-day Actions artifact** and removes the original after checked transfer. The AI can retrieve the image artifact directly, inspect it, then it expires—no accumulating screenshot commits or manual phone upload.
6. `world_site` with `args:["x","z","radius"]` uses the existing saved-map Python spatial intelligence for detailed offscreen surroundings; evidence from serialized files must not be represented as a Unity-rendered screenshot. Live context should be confirmed by `unity_live` `inspect` once the Editor is ready.
7. SceneView camera pivot/rotation/zoom and selected object are periodically saved outside the Git worktree and restored when the map scene reopens. No process can preserve transient RAM or GUI windows while Codespace is actually stopped; recovery is reconstruction from persistent scene, Library cache, session file, command inbox and stable IDs. This is best-effort recovery, **not** a promise of zero import work or uninterrupted VNC.

**Must verify before claiming success:** a real Editor PID, complete initial import, Unity compilation without errors, loading of `TerrainDemoScene.unity`, one `inspect` response, saved core edit and post-edit readback, then a genuine camera frame. Installing scripts or passing Python unit tests alone is insufficient. The last observed free disk was ~3.6 GiB. Preserve 15 intentional modified tracked + 3 untracked core-authoring files; do not `reset`, `clean`, overwrite, or re-fetch intact 764 LFS assets. Never remove the project `Library` after its initial import, otherwise expensive re-import occurs.

---

# Preserve intentional baked Unity core files (2026-11-04)

**Do not treat the dirty map worktree as garbage.** The user reports the existing
15 modified and 3 untracked files were intentionally authored to bake foliage,
LOD and shared prop geometry into the Unity project's actual source assets.
Before any disk cleanup or Git LFS restoration, record dirty path names and
preserve their exact contents. Never run `git reset --hard`, `git clean`,
`git checkout --`, re-clone over the worktree, or overwrite dirty scene,
mesh, texture or Editor-code files with an LFS checkout. Avoid changing the
current checked-out branch or importing the entire project on a nearly-full disk.

The desired final deliverable is **saved Unity core source assets** (scene,
TerrainData, mesh LOD geometry, prefabs, materials, collider bindings), not a
script that tells the Unity compiler/importer to reshape trees only on each
build. Existing importer-time helpers are not proof that changes are baked.
When Unity has enough disk, inspect and test saved core mesh/LOD data and
project import behavior independently, then save permanent asset changes and
verify a clean re-import without relying on temporary build-time transforms.

**Verified 2026-11-04:** All **764/764** hydrated Git LFS map assets on
Codespace HEAD `8225f4346df94ca5e2a2edb671976a49866d04bf` matched their
Git LFS SHA-256 OIDs across 11 real on-demand Actions jobs. **No missing or
corrupt LFS assets, so do not waste 4 GB refetching this checkout.** Preserve
the 15 modified plus 3 untracked intentional Unity core-authoring files.
See the evidence report: [Docs/LFS_INTEGRITY_20261104.md](Docs/LFS_INTEGRITY_20261104.md).

**Full LFS verification without an SSH timeout:** submit an owner-authorized
`lfs_verify_chunk` job with exactly one numeric `args` cursor, beginning
with `["0"]`. Read the Actions JSON result: `cursor`, `next_cursor`,
`total`, `head_sha`, and per-chunk `categories`. Repeat from
`next_cursor` until `all_done=true`, requiring the same `head_sha`
throughout. Aggregate hash matches/mismatches across all chunks; do not
claim that deferred files from `storage_audit` were verified. The chunked
checker is read-only and excludes all locally modified tracked files.
If the index changes or a chunk reports corruption, stop and diagnose before
any LFS restore. Skip downloading files already fully hydrated. Never restore
or overwrite the intentional baked core mesh/LOD edits.

**Storage audit and cleanup:** The `storage_audit` AI terminal operation compares
LFS file paths and expected Git SHA-256 with a **bounded 128 MiB clean-file
hash sample**, and reports dirty files without treating them as invalid.
A deferred hash is not a verified match. Use `prune_caches` (no args) only
to remove the two explicitly allowlisted re-downloadable caches:
`/home/codespace/.cache/copilot/pkg` and `/home/codespace/.npm/_cacache`.
It verifies the Git working tree is unchanged. Never delete Unity Editor,
Unity Library/import assets, `Assets/`, `.git/`, or any modified file.
Restore LFS only after confirming missing/pointer cases and free-disk budget.

If any existing modified source is an LFS object, restore only OTHER clean
LFS pointer files. `.mat`, `.prefab`, and `.unity` may be ordinary Git
blobs; do not blindly reinterpret them as missing LFS. See the repository's
on-demand `storage_audit` operation and `Docs/AI_CODESPACE_ON_DEMAND.md`.

---

# Default remote Codespace terminal for ALL future AI sessions (2026-11-04)

**Use GitHub Actions on-demand controller first; DO NOT post terminal jobs to Issue #37.**
Read [Docs/AI_CODESPACE_ON_DEMAND.md](Docs/AI_CODESPACE_ON_DEMAND.md) and
[Tools/World/ai_codespace_remote.py](Tools/World/ai_codespace_remote.py)
before attempting terminal access. AI can use its authorised GitHub repository
connector without opening Termux, provided the owner has configured the
`AARIS_CODESPACE_TOKEN` GitHub **Actions repository secret** exactly once.

## End-to-end AI command protocol (preferred, not Issue #37)

- Repository: `Aaris-khan-don/Unity-Game-Aris`; Codespace:
  `musical-carnival-jjxp9r6vw45wfjgvg`; dedicated GitHub queue branch:
  `ai/codespace-jobs`. Read the current runbook/runner and validate the
  connected GitHub account's authority to write as `Aaris-khan-don`.
- Submit a brand-new **one-file commit** via the GitHub connector's
  `create_file` action: path `.aaris/jobs/<unique-id>.json`, branch
  `ai/codespace-jobs`. Example file `.aaris/jobs/diagnose-20261104-001.json`:

  ```json
  {"id":"diagnose-20261104-001","operation":"diagnose","args":[]}
  ```

- The repo workflow `.github/workflows/ai-codespace-on-demand.yml` detects
  that push, verifies owner/repo/commit/ID, obtains the **Actions secret**,
  checks the Codespace lifecycle API, **starts a stopped Codespace** when
  authorised, polls until available, then uses SSH to run the bounded task.
  Its controller is outside the Codespace, so no continuously running Termux,
  issue-worker, or terminal session is needed. Neither repo checkout nor git
  reset/clean is performed inside the live dirty worktree.
- Read the matching GitHub Actions run and result artifact
  `aaris-terminal-result-<job-commit-sha>`; confirm `id`, `operation`,
  `ok`, and `exit_code`. The old Issue #37 `AARIS_JOB/AARIS_RESULT` worker
  is a **legacy/manual fallback only**. A queued commit or running workflow is
  not proof of execution or an actual Unity screenshot.
- The operations listed in the older 2026-11-04 paragraphs are **historical examples**, not the current exhaustive set. For any new job, read `validate_job()` in `ai/codespace-jobs/Tools/World/ai_codespace_remote.py` AND the matching reviewed executor on that branch. Never pass arbitrary shell/Python, unreviewed paths, or credentials from prompts.
- If Actions shows `SETUP_REQUIRED`, check the owner-managed `AARIS_CODESPACE_TOKEN` repository Actions secret in GitHub Settings; use GitHub's private Secrets UI or a local authenticated CLI for one-time setup, not a credential in chat. A working Codespace workflow already demonstrates this credential exists; do not demand a replacement token without an actual permission/expiry failure.
  A separate fine-grained token with GitHub Codespaces lifecycle permission is
  preferred. If SSHD is broken or the Codespace is deleted/out of quota, a
  stopped container cannot repair itself; present the actual error and a
  one-time Termux recovery if appropriate. Never fabricate automatic success.
- Unity Editor 6000.3.26f1 was installed and `-version` returned correctly
  in this Codespace on 2026-11-04. Xvfb :12/Openbox/x11vnc/noVNC :6080 were
  verified by the owner and VNC Desktop was visible on Android. Unity GUI and
  real map import have **not** been verified. Available disk was about 3.4 GiB;
  never launch a full Unity project import or Android module install without
  much more verified free space and separate approval.

**Desktop recovery after Codespace restart:** `desktop_xterm` automatically checks
and starts Xvfb `:12`, Openbox, authenticated x11vnc on loopback port 5900,
and noVNC/websockify on port 6080 before opening xterm. It **requires** the
pre-existing private `/home/codespace/.aaris-desktop/vnc.pass`; never generate
or reveal VNC credentials through Actions logs. Keep forwarded port 6080
private. `diagnose` only observes and does not start the desktop. Use `desktop_diagnose` to read bounded VNC log tails and exact display/port/process status when restart fails; never read or print the password file. A running
noVNC desktop does **not** prove Unity GUI or map import is complete;
check disk headroom first (last observed free space ~3.4 GiB).


---

# Working on the Aaris Unity world

## Precision coordinates and relative motion (AI planning; Unity apply later)

The [AI World Motion planner](https://github.com/Aaris-khan-don/Unity-Game-Aris/blob/ai/codespace-terminal-bridge/Tools/World/ai_world_motion.py) extends the [Codespace runbook](https://github.com/Aaris-khan-don/Unity-Game-Aris/blob/ai/codespace-terminal-bridge/Docs/AI_CODESPACE_BRIDGE.md) with safe, read-only relative movement. It does NOT directly shift a loaded Unity Editor object. The installed motion planner, when deployed, is `/workspaces/.aaris-world-bridge/ai_world_motion.py`. New AI agents must recheck that it exists and returns a real AARIS_RESULT before assuming it is available.

To plan a **50 m world-left** move for a stable scene object, publish to issue #37:

```text
AARIS_JOB
{"id":"move-unique-001","argv":["python3","/workspaces/.aaris-world-bridge/ai_world_motion.py","plan","--target","scene:<actual-guid>:<actual-file-id>","--direction","left","--metres","50","--frame","world","--limit","3"]}
```

For **100 m world-right** use `--direction right --metres 100`, with a real `terrain:<guid>:<index>` native tree ID. To move according to the *object's rotation* use `--frame target-local`; to move relative to a camera or another explicit scene Transform, use `--frame reference-local --reference scene:<camera-guid>:<camera-fileID>` after inspecting that reference's orientation. To move by exact world deltas use `--dx -50 --dy 0 --dz 20`. Never guess what “left of the camera” means without the camera's orientation; screen-left, world-left and object-left are distinct. World axes are +X right, +Y up, +Z forward, in metres. A native TerrainData tree's vertical position is terrain-supported; arbitrary Y offsets and tile-crossing movements are rejected. A connected prefab cannot be moved via the Python-only inline-object route.

The planner inspects the original and proposed locations, reports precise coordinates, ground height, nearby saved scene/native objects, separate pagination markers, and a schema-v2 transaction with current SHA256 hashes of each touched core file and `.meta`. Those findings are source evidence, NOT final rendered collisions, clearance or camera visibility. The source worker still has a powerful owner-controlled Python execution path; protect the issue and tokens. For a validated write, follow `world.py plan` → `preview` → inspected postconditions → explicit `apply --write` in an **isolated clean checkout**, with the matching Unity Editor for native TerrainData writes. Do not edit the currently dirty Codespace branch or claim that installing a motion planner installed Unity.

## AI remote Codespace access (2026-11-04)

**HISTORICAL / DEPRECATED PRIMARY PATH:** For new AI sessions first read [the current master controller](Docs/AI_MASTER_CONTROL_AND_AUTH.md) and use the owner-only `ai/codespace-jobs` GitHub Actions queue, **not Issue #37**. The following older paragraph documents a legacy owner-authorised GitHub Issue command bridge connected to Codespace `musical-carnival-jjxp9r6vw45wfjgvg`. To inspect live saved map files without copying terminal output manually, follow the complete [AI Codespace Bridge runbook](https://github.com/Aaris-khan-don/Unity-Game-Aris/blob/ai/codespace-terminal-bridge/Docs/AI_CODESPACE_BRIDGE.md) and read [the AI world sensor](https://github.com/Aaris-khan-don/Unity-Game-Aris/blob/ai/codespace-terminal-bridge/Tools/World/ai_world_observe.py). These files currently live on branch `ai/codespace-terminal-bridge`; **do not assume that branch is checked out in Codespace**.

The [authenticated command inbox is Issue #37](https://github.com/Aaris-khan-don/Unity-Game-Aris/issues/37). With permission to post as GitHub user `Aaris-khan-don`, an AI may submit a comment whose first line is `AARIS_JOB` followed by a JSON command, for example:

```text
AARIS_JOB
{"id":"ai-doctor-new-001","argv":["python3","/workspaces/.aaris-world-bridge/ai_world_observe.py","doctor"]}
```

Fetch issue comments until an `AARIS_RESULT` with the exact same job ID appears; check `status` and `exit_code`. For nearby map evidence, the sensor accepts `site --x 350 --z 167.3 --radius 35 --limit 3`, as well as `scan`, `inspect`, `describe`, `height`, `instances`, `usages`, and `unity`. Read the runbook for full examples, pagination and output limits. The AI should report actual saved coordinates, nearby objects, materials/colors, native tree/rock/grass evidence, uncertainties and source hashes—not invent world data.

This is NOT an automatic API granted to every ChatGPT account. A different ChatGPT account must be given access to the same private GitHub repo and authenticated as the allowed owner identity. Never expose tokens or request them in issue comments. Issue commands can run powerful Python; only submit trusted instructions. The worker operates only while Codespace is running. On 2026-11-04, the read-only world Python dependencies were installed under `/workspaces/.aaris-world-bridge/venv`, but the Unity Editor was not found, so Python saved-world inspection must not be presented as Unity rendering or collision testing.

Protect the Codespace's outstanding map changes on branch `ai/bake-tree-core-20261104` (15 modified and 3 untracked files when inspected). Do not reset, clean, switch branch, rebuild, install Unity over the project, regenerate native terrain, or alter any core file merely to check its contents. Follow the existing schema-v2 `plan` → `preview` → guarded `apply` protocol before any authorised edit. This bridge's tooling and documentation live on a separate GitHub branch and the installed sensor lives **outside** the working checkout.


## Tree proportions and residential openings migration

The reviewed 2026-11-03 migration is reproducible with `Tools/World/apply_tree_house_upgrade.py`; it writes actual saved core meshes/import metadata and verifies the authored postconditions in `tree-house-20261103.postconditions.json`. `verify_tree_house_upgrade.py` checks exact hashes, preserved vertex attributes/material slots, 47 saved residential collider bindings and 900 discrete doorway rays across all three LODs. Those sampled rays are **not** continuous capsule physics or a full interior playtest. Do not re-run historical world generators over these edits.

`remove_mesh_triangles` is a schema-v2 Python operation for explicit original triangle indices per submesh in uncompressed static YAML meshes. Inspect the actual geometry first: a material called oak can include both a door and an entire structural wall. Material slots and all vertex attributes remain intact, and non-convex MeshColliders keep the same mesh reference. Cooked, compressed or streamed geometry requires Unity. Never disable an entire building collider to obtain an entrance.

Tree heights are authored in each existing SpeedTree source `.st.meta`. The tagged `AarisTreeShapeImporter` performs a continuous shared deformation of bark, branches, foliage, next-LOD positions and leaf-facing/wind anchors during the **next matching Unity import**. Matching saved prototype colliders are authored separately. Python does not decode/hex-edit proprietary SpeedTree source or claim that this Editor code has already run. Existing native instance records, positions, terrain heights, roads and vehicle pads stay unchanged. Check Unity compilation/import, LOD transitions, wind, billboards, captures and the selected player routes before claiming final visible/collision quality.

Parent/child world-space edits are resolved through the final transaction hierarchy. Competing writes to the same transform field are rejected. Saved values and exact output bytes are checked against the caller's request before reporting success; a mismatch rolls back.

Read `Docs/WORLD_AUTOMATION.md`, then start with:

```bash
python -m pip install -r Tools/World/requirements.txt
python Tools/World/world.py schema
python Tools/World/world.py context
python Tools/World/world.py scan --limit 100
```

The AI/caller is the map planner and final judge. The tools are sensors, typed actuators and transaction guards; they must not choose an artistic placement, silently move an object, or rewrite the AI's intent. Start broad, drill down, preview, inspect the resulting facts, then keep or revise the transaction.

## Python-only static model workflow

No Codespace or Unity Editor is required to inspect the native terrain, import a supported static FBX/PBR ZIP, or add a static prop to the saved scene. Use `import-model` (dry-run first), then a schema-v2 `place_static_prefab` operation with AI-supplied position, yaw, scale, parent and name. The operation expands explicit static prefab YAML into inline scene objects, preserves existing IDs/metadata, and returns new stable IDs plus neighbourhood measurements. It deliberately does not create a connected PrefabInstance. Supply current hashes for the source prefab and its complete mesh/material/texture dependency closure and their metadata. If this scene's distance-based collider registry should own the new colliders, explicitly supply its `collider_registry_file_id` after inspection.

The import supports one static mesh/material, binary FBX, and BaseColor/Roughness/Metallic/Normal textures. Units-to-metres must be explicit. Animation records require explicit `--freeze-static-pose`; this discards animation and imports authored default geometry only. Unsupported nested prefabs, scripts, skins and other component types fail explicitly. Never turn the adapter into a location recommender: AI queries context, chooses and commands a location, reads preview/apply facts, then decides whether to keep or revise it. Numeric/hash/serialization checks are mechanical integrity checks, not a design verdict.

`inspect` includes target-relative right/up/forward vectors, orientations/scales, renderer and saved collider envelopes, nearby native records, collider-based tree diameter estimates when source prefab data exists, native grass/detail patch occupancy, and nine terrain samples under a target footprint. Collider diameter is not proven visible trunk thickness; patch density is not exact grass-blade positions. Missing LFS geometry is reported explicitly. Optional engine rendering/physics commands remain separate; they are not a prerequisite for this Python authoring path.

Use `describe --target <stable-id> --texture-analysis` when the AI needs the object's complete live structure rather than only its neighbourhood. It pages descendants and binds each renderer material slot to the exact saved part, reports world AABB dimensions/height/footprint, follows bounded serialized dependencies, exposes attached MonoBehaviour fields plus static C# class/method symbols, samples source-texture color distribution, and ranks semantic roles such as building/door/window/roof/wall/tree/rock. Each material slot carries separate surface-part and material-family evidence, so a generic house prefix cannot hide a labelled door, glass, timber or floor slot. Saved names and material labels are evidence; geometry-only roles remain confidence-scored hypotheses such as `door_or_window_panel`. Never turn an ambiguous panel into an asserted door. Static script symbols are not executed behavior, and source-raster colors do not include UV placement, shader, lighting or weather; use Unity/runtime probes and capture for those claims.

`inspect` now pages scene and native results independently with `scene_offset` and `native_offset`; always follow the returned next offsets before claiming an area is fully covered. Native instance records include the serialized TerrainData `color` and `lightmap_color`. Stripped imported-prefab transforms no longer abort the whole reader: their source, overrides and best available transform are reported separately, and `describe` resolves a materialized YAML prefab or bounded FBX source when possible. Unresolved imported geometry is never counted as clear space.

Continue with `next_offset`; a page is not the entire map. Use `scan --search Garage --details --limit 5`, then `object --target <stable-id>` or `inspect --target <stable-id> --radius 50`. `inspect` returns terrain relation, nearby scene objects, native vegetation/rocks, support candidates, AABB relations, coverage and hashes. These are measurements, not a valid/invalid placement verdict. All coordinates are Unity world metres: X right, Y up, Z forward. `object` also exposes local transforms and the complete world matrix. Do not confuse parent-local coordinates with world coordinates; schema-v2 `world_position` is converted through the current parent matrix.

Use `usages --path Assets/...` before editing a shared material/mesh and `runtime` to locate static loading, culling, LOD, frame pacing and memory-related code/config. Static source evidence is not measured device performance.

## Source of truth

- Saved core: `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`, its `.meta`, referenced meshes/materials/prefabs, and four native TerrainData assets under `Assets/TerrainDemoScene_URP/Terrain/Data/`.
- Git LFS pointers are not the assets. Materialize required files, never report pointers/missing geometry as empty terrain or a zero-sized building.
- `height`, `region`, `instances` decode the actual binary TerrainData. Height is a bilinear grid estimate, not a physics raycast. The native grid is much finer than the historical CSV exports. Never silently substitute the CSVs.
- Native tree/rock/shrub instances belong to TerrainData, not the scene GameObject list. Grass is procedural density data, not saved individual grass positions.
- `Docs/MAP_LAYOUT.json` and old `*REPORT.json` describe previous authoring passes. They can be stale after edits. The new commands scan current core files and attach hashes. Do not edit a report to make a failed test look successful.
- Material tint alone does not describe a textured, lit building's appearance. Query texture/shader references, and request Unity `capture` when a visual decision needs a real rendering.

## Edits

Inspect first. Use a schema-v2 transaction with a unique `transaction_id`, `idempotency_key`, operation IDs, current SHA256 preconditions for each touched file and its `.meta`, and `observe_after` requests. Run `plan`, then `preview --backend auto`. Preview mutates only an isolated project and returns post-edit context. The AI must read that context before `apply --backend auto --write`.

For Python-backed edits, `plan` records automatic pre-edit operation/neighbourhood state; preview/apply returns exact before/after file hashes and sizes, post-edit state, paged neighbour changes, target position/size deltas and added/removed scene/native neighbour IDs. Default observations include native instances, appearance and semantic evidence. Read `operation_deltas`, `observation_deltas` and `written_file_changes`; do not infer success merely from a textual diff.

Python edits actual saved YAML for inline transforms/state and existing material color/float properties. The Unity backend edits actual native TerrainData instances and heightmaps, instantiates/duplicates/deletes scene objects or prefab instances, saves the scene/assets, and returns resolved identities plus exact physics observations. Current typed operations are returned by `schema`; never guess an operation name or bypass an unsupported type with arbitrary binary writes.

For every operation choose scope deliberately: selected scene/native instance, shared material asset, prefab source, or terrain prototype. `usages` and `plan` must expose shared impact. A native terrain tree/rock/shrub remains terrain-supported. Use a scene/prefab object when the AI intentionally needs a prop on a roof, bridge or other non-terrain surface.

Physical relationships such as “8 m above terrain but 2 cm above a roof”, an AABB overlap, or being outside an authored boundary are observations. They may be intentional. The AI can acknowledge a specific observation ID/hash/reason in a new current-hash transaction. Integrity failures—stale hashes, invalid identities/numbers, missing LFS bytes, failed Unity import/save/compile, or serialization corruption—are never forceable.

Preserve GUIDs, fileIDs, metadata and asset references. Do not recreate `.meta` files for existing assets. Terrain brushes must consider neighbouring tiles, roads, foundations, water and vegetation. Placement edits must preserve the 2km by 2km boundary, vehicle pads, access routes and scale. Empty `VehicleSpawns/VehicleSpawnPoint_XX` markers are reserved for the later dynamic-vehicle phase; decorative wrecks are separate.

The Python authoring generators are not automatic scene importers. Some regenerate entire historical authoring passes and overwrite hand edits. Do not run them merely because a test fails; inspect their inputs and scope first.

## Verification and evidence

```bash
python -m unittest discover -s Tools/World/tests -v
python Tools/World/check_contracts.py
python Tools/World/world.py verify --native
python Tools/World/world.py verify --project-checks
```

Project checks additionally need the pinned Pillow/tree-sitter packages in CI; optional historical authoring tools have their own larger requirements. Static C# syntax checks are not a Unity compilation. Run Unity import, physics/capture probes and relevant player/device tests on a configured runner when the change requires them. If unavailable, report that explicitly. Never claim a phone FPS, RAM saving, crash diagnosis or interior accessibility from source inspection alone. Device JSONL reports can be read with `performance`; correlate `buildGuid` with the APK's `world-build.json` sidecar.

Probe reports apply only to the tested paths and existing colliders. Automatic AABB-side candidates are hypotheses, not guaranteed doors/interiors. A blocked candidate does not prove there is no entrance. A passed path does not prove visible walls are solid. Inspect collider coverage and screenshots before changing a building. A `probe` request may contain up to 32 uniquely named `probes`; they run as independent deterministic 1.78 m CharacterController route bots in one isolated Unity import. They verify the supplied routes, not combat AI or global navigation.

## Execution and retention

Reading a GitHub repository does not execute Python. Use a terminal or dispatch the supplied GitHub Actions workflows, with appropriate account permissions. `world-query.yml` is read-only and fetches relevant LFS assets within a 1GiB request budget. Unity operations need the licensed matching editor plus a complete checkout and configured self-hosted Linux runner. Never invent an available runner/editor or say a skipped job ran.

Read commands write to stdout by default; no background agent, persistent report cache or runtime bot is installed. Explicit `--out` files are retained by the caller. Unity uses disposable project copies and deletes temporary bots/copies on normal completion, failures and handled cancellation. Query workflow reports/logs expire after selected TTL at the next successful scheduled cleanup; deletion is not an exact wall-clock guarantee. Do not commit raw temporary query reports, screenshots, probe objects, Unity caches or credentials. Keep scripts, schemas, instructions and actual source edits in Git.

For changes: a fresh branch, meaningful checks and a concrete PR. The automated edit workflow never auto-merges future patches. Follow the current user's merge authorization; do not infer permission to deploy unrelated builds or send messages.



## Area intelligence and live local reinspection

```bash
python Tools/World/world.py site --x 350 --z 167.3 --radius 50 --limit 100
python Tools/World/world.py watch --x 350 --z 167.3 --radius 50 --poll-seconds 2 --quiet-seconds 1
```

`site` wraps `inspect` with an evidence-scoped AI capsule: terrain/grass, exact saved material RGBA, texture references, available geometry sizes, nearest *paged* semantic objects, all-radius native tree/rock/shrub counts and independent scene/native next offsets. Iterate both offsets. `serialized_candidate_coverage_complete` is an index-completeness hint, **never** proof of free physical space. Source color properties are not final UV/shader/lighted pixel colors. Check `describe` on a building part and use Unity capture for rendered appearance.

`watch` runs in the **foreground only** in a local checkout with the command open. It polls relevant saved core files, re-runs the selected spatial query after changes, and emits JSON Lines with changed paths, available hashes, new site conditions and before/after distances, colors and dimensions. Stop with Ctrl+C; running GitHub search or a one-shot Actions query does not start this watcher. Save stdout explicitly if desired, keeping generated reports outside version control. Changes mid-save are retried, not silently treated as valid. It never edits/commits/merges core assets.

Explicit `observe_after` now **adds to** automatic per-operation and saved-scene material-user observations (up to 32 per transaction; split large edits). Reports distinguish a neighbour entering/leaving a *page* from actual creation/removal. Review `observation_deltas` and `operation_deltas` and never infer a collider or color rendered outcome from serialized data alone.
