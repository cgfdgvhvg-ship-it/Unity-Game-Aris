# Working on the Aaris Unity world

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


