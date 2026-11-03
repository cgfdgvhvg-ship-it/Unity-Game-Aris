# Working on the Aaris Unity world

Read `Docs/WORLD_AUTOMATION.md`, then start with:

```bash
python -m pip install -r Tools/World/requirements.txt
python Tools/World/world.py schema
python Tools/World/world.py context
python Tools/World/world.py scan --limit 100
```

The AI/caller is the map planner and final judge. The tools are sensors, typed actuators and transaction guards; they must not choose an artistic placement, silently move an object, or rewrite the AI's intent. Start broad, drill down, preview, inspect the resulting facts, then keep or revise the transaction.

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

