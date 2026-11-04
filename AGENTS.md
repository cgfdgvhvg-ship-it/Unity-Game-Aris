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
- Supported operations today: `diagnose`, `desktop_xterm`, `desktop_diagnose`, `unity_version`,
  `world_doctor` (empty args), and limited `terminal_readonly` with a
  diagnostic argv array. New mutating operations require explicit authorisation,
  review, tests and disk/dirty-worktree protections. Do not pass arbitrary
  shell/Python from untrusted prompts.
- If Actions shows `SETUP_REQUIRED`, no Codespaces token is configured:
  request the **one-time Termux** secret bootstrap documented in the runbook;
  do not ask for credentials in chat, AGENTS.md, PRs, Issues or job files.
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

**New AI sessions: read this first.** This private repo has an owner-authorised GitHub Issue command bridge connected to Codespace `musical-carnival-jjxp9r6vw45wfjgvg`. To inspect live saved map files without copying terminal output manually, follow the complete [AI Codespace Bridge runbook](https://github.com/Aaris-khan-don/Unity-Game-Aris/blob/ai/codespace-terminal-bridge/Docs/AI_CODESPACE_BRIDGE.md) and read [the AI world sensor](https://github.com/Aaris-khan-don/Unity-Game-Aris/blob/ai/codespace-terminal-bridge/Tools/World/ai_world_observe.py). These files currently live on branch `ai/codespace-terminal-bridge`; **do not assume that branch is checked out in Codespace**.

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
