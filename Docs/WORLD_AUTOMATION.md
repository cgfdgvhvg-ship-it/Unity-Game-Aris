# AI inspection and core editing

This is a source inspection and controlled authoring toolkit, not a replacement game engine. Python can inspect saved Unity YAML, resolve GUIDs and hierarchy transforms, decode the native TerrainData, prepare precise patches and run verification. Actual collision movement, imported prefab resolution, URP rendering and native terrain writes use the matching Unity Editor through `WorldBridge.cs` in a temporary project copy. No map layout or graphic-quality change is applied merely by installing this toolkit.

## Start locally

Use Python 3.11 or later in a virtual environment:

```bash
git clone https://github.com/Aaris-khan-don/Unity-Game-Aris.git
cd Unity-Game-Aris
python -m venv .venv
. .venv/bin/activate
python -m pip install -r Tools/World/requirements.txt
python Tools/World/world.py context
```

`context` reports what is available, the scene GUID/hash, engine prerequisites, commands and limitations. For full engine work run `git lfs pull`; allow enough disk for both the full project and an imported disposable copy. For a read query, the selective fetcher avoids downloading the entire archive:

```bash
export WORLD_REQUEST='{"command":"scan","search":"Garage","details":true,"limit":5}'
python Tools/World/fetch_assets.py
python Tools/World/world.py request
```

The fetcher downloads actual terrain assets for terrain queries and referenced mesh assets for detailed object queries. It limits each request to 1GiB of advertised LFS bytes. Narrow an oversized query. Source textures are fetched with an explicit `asset` request rather than silently downloading every texture. GitHub/LFS access, quotas and network availability still apply.

## Read the world

| Need | Command after `python Tools/World/world.py` |
|---|---|
| Object index, terrain size/counts/hashes | `scan --limit 100` |
| Names matching Garage, bounds and materials | `scan --search Garage --details --limit 5` |
| Continue a page | `scan --offset 100 --limit 100` |
| One object, hierarchy, components, materials | `object --target scene:<scene-guid>:<game-object-fileID>` |
| Ground height, gradient, slope, normal | `height --x -496 --z -212` |
| Grid over a selected region | `region --xmin -510 --zmin -220 --xmax -490 --zmax -200 --step 2` |
| Native trees, rocks or shrubs in an area | `instances --category tree --xmin -600 --zmin -300 --xmax -400 --zmax -100 --limit 100` |
| List serialized objects in a binary/YAML file | `asset --path Assets/.../Terrain_1_1_....asset` |
| Read a particular native field | `asset --path Assets/.../Terrain_1_1_....asset --file-id 15600000 --field m_Heightmap.m_Heights --offset 1000 --limit 100` |
| Material properties | `asset --path Assets/.../Wall.mat --file-id 2100000 --field m_SavedProperties` |
| Source code lines | `asset --path Assets/AarisWorld/Scripts/AarisNearbyColliders.cs --file-id 0 --field lines --limit 100` |
| Actual phone measurements | `performance --report /path/to/current.jsonl` |

Replace placeholder asset paths with a real path returned by `context`, `object` or `asset`. JSON requests use the same command names and underscore keys (`file_id`, not `file-id`). Output includes timestamps, the actual files read and SHA256 fingerprints. Re-query after a source change. `--root <project>` and `--out <file>` are global options and go before the command.

The scene is currently a four-tile 2km by 2km world. Each native terrain has a 2049 by 2049 height grid. The reader derives spacing/size/origin from the asset and scene rather than applying a single map-wide Y offset. This project's stored integer normalization is `/32766`; unsupported encodings/transforms fail explicitly. At a tile boundary `height` returns both sides and their difference. Bilinear height/slope are numerical estimates of the stored grid, not measurements of a roof, building floor or Unity's rendered triangle. For exact engine terrain values and collider movement, use the engine bridge.

`scan` indexes saved inline GameObjects and pages results to keep AI context usable. `instances` covers the native vegetation/rock database. `asset` exposes other serialized fields without dumping a 53MB binary as an enormous JSON message. Arrays are paginated; dictionaries are compact summaries with keys and samples. Unknown/importer-only data is reported as unavailable and requires Unity. External prefab instances use Unity's complete GlobalObjectId in engine exports; their prefab instance ID must not be discarded. The Python write adapter intentionally supports inline scene objects only.

Object bounds are transformed mesh AABBs, including descendants/LODs. Missing LFS meshes produce `bounds_incomplete`, not invented dimensions. Texture files can be queried for image dimensions/format. Serialized `_BaseColor` or `_Color` often is white while the texture supplies the visible wall color. A screenshot from the real URP pipeline is the appropriate evidence for visible colors, lighting and silhouettes.

## Edit the actual core files

Use `Tools/World/patch.schema.json` and this structure. Obtain hashes from current files (for example `sha256sum <path>`), not old reports. Include both each target file and its existing `.meta`:

```json
{
  "schema_version": 1,
  "reason": "Adjust this house after checking its road access and foundation",
  "expected_files": {
    "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity": "<current SHA256>",
    "Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity.meta": "<current SHA256>"
  },
  "operations": [{
    "op": "set_transform",
    "target": "scene:<scene-guid>:<game-object-fileID>",
    "local_position": [350, -11.9368, 167.3]
  }]
}
```

The position is **parent-local**, as in Unity's Transform inspector. Query the world matrix/parent before choosing values. Supported transform fields: `local_position`, normalized `local_rotation_xyzw`, positive `local_scale` (up to 100 per axis). To change a tint use `set_material_color` with `path`, `file_id`, an already-existing `property` such as `_BaseColor`, and `rgba`. A shared material edit affects all its users.

```bash
python Tools/World/world.py plan --patch change.json
python Tools/World/world.py apply --patch change.json
python Tools/World/world.py apply --patch change.json --write
python Tools/World/world.py verify --native
python Tools/World/world.py verify --project-checks
```

The first two commands are dry runs. Python replaces only the selected YAML documents, preserves the remaining scene bytes, fileIDs and `.meta` files, checks precondition hashes immediately before writing, stages/parses the result, and restores original bytes if its post-write structural validation fails. Work in a branch; multi-file writes are rolled back on handled errors but are not a filesystem-wide transaction against a machine crash. Check your Git diff.

`terrain_brush` is a bounded, smooth vertical delta (radius 0..100m, delta up to +/-20m). Supply `center_xz`, `radius_m`, `delta_m`, plus expected hashes for the saved scene, all four native terrains, and all five `.meta` files. Then use:

```bash
export UNITY_EDITOR_PATH=/absolute/path/to/Unity
python Tools/World/world.py apply --patch terrain-change.json --backend unity --write
```

The launcher applies YAML edits to a disposable copy, runs Unity `TerrainData.GetHeights/SetHeights`, lets Unity recalculate native LOD/vegetation information, saves native assets, checks seams and current original hashes, then copies back only allowed core files. All tiles touched by a brush use the same world-space falloff. A missing editor/license, incomplete checkout, engine error, stale hash, invalid brush or seam over 5cm prevents copying back. Python does not hex-edit the serialized terrain. Saving may upgrade the terrain's serialization version to the project's Unity version.

Terrain changes can bury roads, float buildings, shift trees or expose the sea edge. The adapter does not redesign foundations or relocate vegetation for you. The AI must inspect these impacts and implement/review the needed core changes. Historical authoring reports/layout JSON are not silently regenerated; project checks may correctly reject a change that makes them stale. This is deliberate evidence, not a reason to rewrite a report to claim success. New operation types or C# behavior can be added as source changes with appropriate tests; the adapter does not promise safe arbitrary field/binary mutations.

## Temporary walking probes and real captures

These require a complete Git checkout with all LFS files plus installed/licensed **Unity 6000.3.26f1**, matching `ProjectVersion.txt`. The supplied cloud workspace has no Unity Editor; Python/static verification here does not establish engine compilation or a successful walking/render test.

Save a request JSON with either explicit walking waypoints (world-space foot positions) or a stable target object ID for four automatic candidates:

```json
{"command":"probe","target":"scene:<scene-guid>:<house-fileID>","maxSteps":10000}
```

```json
{"command":"probe","waypoints":[{"x":350,"y":-11.8,"z":155},{"x":350,"y":-11.8,"z":160}],"maxSteps":4000}
```

```bash
python Tools/World/world.py engine --request route.json
```

The probe uses the player's 1.78m height, .28m radius, .30m step and 46-degree slope limit with controlled walking/gravity. It temporarily enables saved environment colliders (including those initially disabled by distance gating), disables original CharacterControllers, syncs physics, and removes/restores everything in `finally` without saving the probe scene. Reports include start/target/reached positions, terrain height/slope/normal, route status, and nearby capsule-sweep contact candidates with object IDs/bounds. A collider candidate is not proof of the sole blocker. Colliders absent from the original asset are not invented.

Automatic attempts start just outside the renderer AABB on four sides and aim at its center on the terrain. They are geometry hypotheses: a center may be an exterior courtyard or solid volume rather than a room. A blocked straight candidate does not prove a house has no entrance. For an actual entrance/interior test, inspect the model and supply the doorway/stair/interior waypoints. No bot decides to alter a wall automatically. Repeat selected probes after the AI makes a reviewed change; the total step budget bounds each request.

`{"command":"export"}` returns engine-resolved objects, world positions, bounds and components. For an actual URP view:

```json
{"command":"capture","cameraPosition":{"x":350,"y":30,"z":120},"cameraTarget":{"x":350,"y":0,"z":170}}
```

```bash
python Tools/World/world.py engine --request capture.json --capture-dir /path/to/temporary-output
```

Capture needs a graphics-capable runner/display. It uses a URP single-camera render request and returns a real 1280 by 720 image; a null graphics device fails instead of fabricating a preview. Dispose of explicitly retained capture files when finished. None of these Editor results measures Android FPS or native crash stability.

## GitHub execution

Opening a file or attaching a GitHub connector does not run Python. A permitted AI/terminal can dispatch Actions, wait, then read/download the report:

```bash
gh workflow run world-query.yml --ref main -f request_json='{"command":"height","x":-496,"z":-212}' -f ttl_hours=2
gh run list --workflow world-query.yml --limit 3
gh run watch <run-id> --exit-status
gh run download <run-id> --dir /path/to/temporary-output
```

Use the returned run ID, not an unqualified "latest" when multiple AIs are querying. Python-only queries work on GitHub's hosted Linux runner; they need Actions enabled and available LFS quota. The current ChatGPT GitHub connector supports repository reads/writes but has no workflow-dispatch endpoint; use Actions UI or an authenticated terminal/API with Actions write permission when dispatch is required.

For engine queries, register a self-hosted Linux runner with sufficient RAM/disk, a matching licensed editor, Python/git-lfs and a display/GPU for captures. Set repository variables `WORLD_UNITY_RUNNER` to its runner label and `UNITY_EDITOR_PATH` to the executable. Dispatch `world-engine-query.yml` with the same request JSON and TTL. When the runner variable is missing, the engine job is skipped and the availability job explains why; it is not a successful engine test. Concurrency prevents simultaneous automation on that runner. Each invocation imports a disposable project; this is heavier than a cached editor and is not an instant service.

`world-core-edit.yml` takes `patch_json` and `backend=python|unity`, checks out current main, enforces hash preconditions, applies actual core changes, runs saved-file checks and pushes a new `ai/world-edit-...` branch/PR. It does not auto-merge. Actions needs repository permission to create PRs; if that setting blocks PR creation, the verified branch remains available and the error names it. Events created using `GITHUB_TOKEN` may not trigger another workflow, so the edit job runs the project checks itself. Native edits require the configured Unity runner; an unavailable runner skips that job. Normal scan/query jobs have read-only repository permission; only the explicit edit workflow has source-write permission.

## Retention and diagnostics

Default local queries print JSON to stdout and leave no report file/cache or background service. Python/Unity temporary directories are removed on normal return, errors and handled cancellation; hard power/process kills cannot guarantee a cleanup callback. On the engine query runner the temporary project is under the job's temporary output directory and an `always` step removes it. Source scripts/instructions remain in Git for reuse. Caller-selected `--out`/capture outputs are retained by the caller; remove them when done. Git does not delete downloaded copies or content pasted into chats.

GitHub query artifacts have a one-day retention fallback. `world-query-cleanup.yml` runs hourly and deletes only completed manual runs of `world-query.yml` and `world-engine-query.yml` whose exact TTL title has expired (choices 1/2/6/24h, default 2h). Run deletion removes their query logs/artifacts too. Effective deletion is TTL plus the delay until the next successful cleanup; schedules can be delayed/disabled and are not an exact timer. Source, releases, build deliverables, edit PRs and ordinary verification history are outside this cleanup's fixed scope. Do not rely on deletion as permission to log credentials.

Android diagnostics now include `Application.buildGUID`. Future builds write `<apk>.world-build.json` (or `world-build.json` in a directory build) linking BuildReport GUID, commit and selected core hashes. This build provenance stays with the build. `performance` reads actual device JSONL; it does not estimate performance from map geometry. Managed error logs alone cannot prove the cause of a native crash, GPU fault or Android memory kill—collect logcat/exit reason and correlate the exact build.

## Verify the toolkit and a source change

```bash
python -m pip install tree-sitter==0.26.0 tree-sitter-c-sharp==0.23.5
python -m unittest discover -s Tools/World/tests -v
python Tools/World/check_contracts.py
python Tools/World/world.py verify --native
python Tools/World/world.py verify --project-checks
```

Tests cover parent transforms, precise height/slope interpolation, missing/pointer data, ambiguous IDs, stale source/metadata, read-only plans, actual material/transform writes, identity preservation, rollback and cleanup scope. CI also checks the actual four-tile scene, spawn markers, C# syntax and workflow boundaries. Existing project checks cover saved bindings/materials/road geometry. A Unity import/compile, engine probes/captures and an Android device pass remain separate necessary evidence for changes that affect those behaviors.
