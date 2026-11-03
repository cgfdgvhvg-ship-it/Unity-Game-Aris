# Working on the Aaris Unity world

Read `Docs/WORLD_AUTOMATION.md`, then start with:

```bash
python -m pip install -r Tools/World/requirements.txt
python Tools/World/world.py context
python Tools/World/world.py scan --limit 100
```

Continue with `next_offset`; a page is not the entire map. Use `scan --search Garage --details --limit 5`, then `object --target <stable-id>`. All coordinates are Unity world metres: X right, Y up, Z forward. `object` also exposes local transforms and the complete world matrix. Do not confuse parent-local coordinates with world coordinates.

## Source of truth

- Saved core: `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`, its `.meta`, referenced meshes/materials/prefabs, and four native TerrainData assets under `Assets/TerrainDemoScene_URP/Terrain/Data/`.
- Git LFS pointers are not the assets. Materialize required files, never report pointers/missing geometry as empty terrain or a zero-sized building.
- `height`, `region`, `instances` decode the actual binary TerrainData. Height is a bilinear grid estimate, not a physics raycast. The native grid is much finer than the historical CSV exports. Never silently substitute the CSVs.
- Native tree/rock/shrub instances belong to TerrainData, not the scene GameObject list. Grass is procedural density data, not saved individual grass positions.
- `Docs/MAP_LAYOUT.json` and old `*REPORT.json` describe previous authoring passes. They can be stale after edits. The new commands scan current core files and attach hashes. Do not edit a report to make a failed test look successful.
- Material tint alone does not describe a textured, lit building's appearance. Query texture/shader references, and request Unity `capture` when a visual decision needs a real rendering.

## Edits

Inspect first. Use a versioned patch with current SHA256 preconditions for each touched file and its `.meta`. Run `plan`, inspect its concrete diff and impacts, then `apply --write` within the user's authorized scope. `apply` without `--write` is a dry run. Supported Python operations edit actual saved YAML (`set_transform`, `set_material_color`); native `terrain_brush` requires the Unity backend. See the guide/schema. Other source-code/serialized changes require a deliberate implementation and relevant validation; there is no arbitrary binary overwrite command.

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

Probe reports apply only to the tested paths and existing colliders. Automatic AABB-side candidates are hypotheses, not guaranteed doors/interiors. A blocked candidate does not prove there is no entrance. A passed path does not prove visible walls are solid. Inspect collider coverage and screenshots before changing a building.

## Execution and retention

Reading a GitHub repository does not execute Python. Use a terminal or dispatch the supplied GitHub Actions workflows, with appropriate account permissions. `world-query.yml` is read-only and fetches relevant LFS assets within a 1GiB request budget. Unity operations need the licensed matching editor plus a complete checkout and configured self-hosted Linux runner. Never invent an available runner/editor or say a skipped job ran.

Read commands write to stdout by default; no background agent, persistent report cache or runtime bot is installed. Explicit `--out` files are retained by the caller. Unity uses disposable project copies and deletes temporary bots/copies on normal completion, failures and handled cancellation. Query workflow reports/logs expire after selected TTL at the next successful scheduled cleanup; deletion is not an exact wall-clock guarantee. Do not commit raw temporary query reports, screenshots, probe objects, Unity caches or credentials. Keep scripts, schemas, instructions and actual source edits in Git.

For changes: a fresh branch, meaningful checks and a concrete PR. The automated edit workflow never auto-merges future patches. Follow the current user's merge authorization; do not infer permission to deploy unrelated builds or send messages.
