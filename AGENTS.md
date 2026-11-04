# Working on the Aaris Unity world

## Live Codespace access for new AI sessions (November 2026)

**First read this section, then \`Docs/AI_CODESPACE_BRIDGE.md\`, and only then \`Docs/WORLD_AUTOMATION.md\`.** This repository has a separate, owner-controlled GitHub Issue command bridge which was tested end-to-end. Do not confuse a GitHub connection with automatic terminal or Unity Editor access.

- Repository: \`Aaris-khan-don/Unity-Game-Aris\` (private). The ONLY supported command inbox for the currently installed worker is [GitHub Issue #37](https://github.com/Aaris-khan-don/Unity-Game-Aris/issues/37). Worker source is \`Tools/World/ai_terminal_bridge.py\` on branch \`ai/codespace-terminal-bridge\`. The Codespace is \`musical-carnival-jjxp9r6vw45wfjgvg\`. Its working project is \`/workspaces/Unity-Game-Aris\`.
- An assistant **with access to the owner's repository through an authorised GitHub connector** can post an issue comment with exact first line \`AARIS_JOB\` and a JSON payload of \`{"id":"unique-lowercase-id","argv":["python3","Tools/World/ai_world_observe.py","doctor"]}\`. Then fetch comments on #37 until an \`AARIS_RESULT\` with the same \`id\` is received. Check \`exit_code\`, \`status\`, \`output\`, and the source comment ID. **Never say a command ran simply because the comment was posted.** IDs are unique for each attempt; reusing them must not repeat an operation.
- The issue accepts only comments posted as GitHub user \`Aaris-khan-don\` (not an arbitrary ChatGPT identity). A different ChatGPT account needs permission to this same private GitHub repository and to comment as the authorised GitHub identity; reading this file alone does not grant access. Other agents without connector permissions must use an authenticated terminal or ask for the correct access, not pretend to have executed commands.
- Preferred source-inspection tool for remote calls: \`python3 Tools/World/ai_world_observe.py ...\`, documented below. It runs existing \`world.py\` sensors with bounded JSON output; no Unity install is required to inspect available serialized assets. Use \`doctor\`, \`context\`, \`scan\`, \`site\`, \`inspect\`, \`describe\`, \`height\` and \`unity\`. The wrapper reports missing dependencies/assets and never invents rendered geometry.
- **Current known state**: on 2026-11-04 Unity Editor/Unity Hub were NOT found in an installed-binary/package/cache scan; \`UNITY_EDITOR_PATH\` was unset. This is a snapshot, not a promise about future state. Always re-run \`unity\` or \`doctor\` before engine/capture work. Until a licensed matching Unity 6000.3.26f1 Editor is confirmed, avoid claims of rendering, frame rates, physics or actual GUI interaction.
- **Preserve uncommitted work.** When initially checked, the Codespace was on branch \`ai/bake-tree-core-20261104\` with 15 modified tracked files (including Unity geometry/LFS pointers) and 3 untracked files. A local snapshot was made at \`/workspaces/.aaris-backups/bridge-preflight-20261104-085644.tar.gz\`, but backup existence should be rechecked before any new writes. Do NOT run \`git reset\`, \`clean\`, \`checkout\`, \`switch\`, \`stash\`, \`pull\`, rebuild Codespace, or rerun historical generators against this working tree. Use an isolated GitHub branch/PR or dedicated worktree and test changes before merging.
- **Read vs edit**: issue jobs are remote commands with high privilege; the currently installed worker permits a restricted set of executable names but \`python3 -c\` can execute arbitrary Python and modify files. The owner-controlled issue and credentials are security-critical; never place secrets, OAuth tokens, or private file contents in an issue comment/result. Use the typed read-only \`ai_world_observe.py\` wrapper for exploration. For actual edits, read the current \`world.py schema\`, collect exact GUID/fileIDs and SHA256 preconditions, use \`plan\` then \`preview\` on a disposable copy, inspect after-state, and apply only with explicit authorisation and successful rollback-capable checks. Do not blindly run Python snippets that alter core assets.
- **This is not a 24/7 cloud API**: the worker polls while Codespace is running; a paused/deleted Codespace or unauthenticated/expired \`gh\` session stops it. Check actual results. GitHub issue output is truncated to about 12k characters: narrow the query, paginate both \`scene_offset\` and \`native_offset\` and never claim complete coverage from a truncated result.
- Unity map source of truth remains the saved core scene + four TerrainData files, NOT this issue or generated reports. Collect scene/object identity, transforms, extents, textures, material shader properties, saved colliders and neighbour relationships. Treat semantic names as evidence, not proof that something is a door/roof. Cross-check appearances in Unity Editor captures only when the Editor truly works.


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
