# Aaris — persistent live Unity Editor and map AI bridge

**Target**: `Aaris-khan-don/Unity-Game-Aris`, Codespace `musical-carnival-jjxp9r6vw45wfjgvg`, Unity 6000.3.26f1, map scene `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`.

## Startup, recovery and source of truth

Start with a new owner-authored file on `ai/codespace-jobs`:

```json
{"id":"unity-start-example-001","operation":"unity_gui","args":[]}
```

GitHub Actions (not an old issue worker or an open Termux) starts the Codespace if stopped and triggers the external desktop manager. It recreates the Xvfb / Openbox / VNC / browser transport, then checks a real Unity Editor process. It starts one instance with `-projectPath`, saves startup logs under `~/.aaris-desktop/` and **never deletes `Library`**. The staged live bridge `.cs` and `.meta` are created only if absent, otherwise their bytes must match exactly. Do not overwrite user-modified assets. The existing dirty map branch is left unchanged, apart from adding two new Editor bridge files when they did not already exist.

The project may take a long time to import on its first open; `unity_gui` reporting an Editor PID is **not** proof that the map is ready. Inspect `~/.aaris-desktop/unity-editor.log`, Unity compilation, available storage and the Editor response. A low-disk guard blocks the first launch below 3 GiB, and a watchdog requests Unity shutdown below 1 GiB. If import fails from insufficient space, do not delete or re-checkout map assets. Free known safe caches, move to a larger persistent volume, or use an appropriately sized development machine; avoid promising that a 32 GB Codespace can hold arbitrary Unity Library growth.

After a Codespace restart, running processes are lost; `Library`, native saved scenes, the session camera/selection file and pending jobs are disk-persistent. The next queued AI operation recreates the Editor/desktop and attempts to reopen the saved scene. There can still be Unity asset scans, a login/license prompt or graphics failures. The browser port must stay private; **never put VNC passwords or GitHub tokens in job files or screenshot artifacts**.

## World sensing and live native edits

An AI submits a `unity_live` job with one **JSON string** inside the `args` array. The command ID is the outer job `id`; it is not supplied inside the nested object.

```json
{"id":"unity-inspect-example-001","operation":"unity_live","args":["{\"action\":\"inspect\",\"cameraTarget\":{\"x\":120,\"y\":5,\"z\":75},\"radius\":40,\"limit\":16}"]}
```

The response includes stable editor object IDs, names, physical positions, nearby object distances, renderer bounds/material names, nearby TerrainData tree-instance coordinates and ground height/slope. A serialized local-map query, independent of the Editor, can also use:

```json
{"id":"unity-site-example-001","operation":"world_site","args":["120","75","50"]}
```

For an exact game object returned by an inspection, supply its ID and a bounded relative translation:

```json
{"id":"unity-move-example-001","operation":"unity_live","args":["{\"action\":\"move\",\"target\":\"<stable-id-from-inspect>\",\"delta\":{\"x\":0.5,\"y\":0,\"z\":0}}"]}
```

For a native TerrainData tree (no separate GameObject), the ID from `nearbyTerrainTrees` must be used with the exact previously observed position:

```json
{"id":"unity-tree-example-001","operation":"unity_live","args":["{\"action\":\"move_tree\",\"target\":\"terrain-tree:<terrain-id>:14\",\"expectedPosition\":{\"x\":120,\"y\":4,\"z\":75},\"delta\":{\"x\":0.5,\"y\":0,\"z\":0}}"]}
```

Native `scale_tree` similarly requires `expectedPosition` and `scale`: x adjusts width, y adjusts height, z must remain 1. Scene `scale` uses 0.5–2 multipliers per axis. Unity records changes through scene/asset APIs and saves the **actual** native project files. This is neither an Android build-time transformation nor a Python imitation. Ask a read-after-write `inspect` and check `git status` and relevant file diffs before confirming the edit.

If the Editor is still compiling/importing, the command returns `pending:true` and its JSON request survives outside Git under `~/.aaris-desktop/unity-commands`. Poll by a **new job**:

```json
{"id":"unity-poll-example-001","operation":"unity_result","args":["unity-move-example-001"]}
```

## Visual screenshots without persistent Git commits

```json
{"id":"unity-camera-example-001","operation":"unity_live","args":["{\"action\":\"capture\",\"cameraPosition\":{\"x\":140,\"y\":35,\"z\":110},\"cameraTarget\":{\"x\":120,\"y\":5,\"z\":75}}"]}
```

After `unity_result` confirms capture succeeded, request:

```json
{"id":"unity-photo-example-001","operation":"unity_frame","args":["unity-camera-example-001"]}
```

The Python executor validates the already-generated JPEG, Actions copies it from the Codespace and verifies the copied byte length, then removes the Codespace original. An Actions artifact contains the image for **1 day** only; no screenshot is committed to the map repo and the AI can retrieve and view that artifact without a phone upload. Local unclaimed captures expire automatically after 30 minutes. If the image is not ready or Unity cannot render, report the failure rather than providing a fake scene photo. Do not use `-nographics` for real capture.

## Completion checklist

1. Project Unity Editor 6000.3.26f1 launched in the graphical Codespace.
2. Project import finished, Unity license valid, no C# compile errors.
3. Exact native map scene is loaded, preserved `Library` reused after a controlled restart.
4. Inspector returns real nearby props/terrain and stable target IDs.
5. Test a small reversible move/scale on a safe target, verify saved `.unity` or `.asset` bytes changed, and inspect again.
6. Render a real perspective screenshot, retrieve and inspect the one-day image artifact.
7. Keep the previously modified 15 tracked + 3 untracked core-authoring files intact. Never `git clean`, reset or fetch the already verified 764/764 LFS objects simply to force a clean tree.

## Limitations

A stopped Codespace does not keep its CPU/RAM, process or live video stream active. The AI can auto-start it on demand and rebuild an equivalent editing session from persistent files. Unity may still scan assets after a restart, and a low-disk or license issue can prevent complete startup. Automatic resurrection is not a substitute for tested native Unity import, GPU support or sufficient persistent storage.

---

## 2026-11-04 verified Unity Terms and low-disk recovery

- Work on the existing Codespace musical-carnival-jjxp9r6vw45wfjgvg only. Preserve ALL intentionally modified and untracked source/core files, including any Unity-generated ProjectSettings and live bridge sources. Never reset, git clean, re-clone, delete Library or re-fetch the 764 already-verified Git LFS assets.
- The owner explicitly authorized acceptance of Unity 6000.3.26f1 Editor Software Terms. The exact X11 Unity terms dialog was accepted and its disappearance verified: [run 41855189075](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41855189075).
- Real Unity import started, including native materials, prefabs and textures; the Library grew beyond 2.6 GiB. Import and C# compilation remain unfinished. The map SceneView is NOT verified loaded; no native tree move/capture/readback may be claimed.
- Persistent /workspaces has 32 GiB total; free space dropped to 0.585 GiB. A bounded SIGTERM request did not terminate Unity. A guarded SIGSTOP paused its own process group 40121, confirmed by real ps state T<sl: [run 41858218549](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41858218549). Library is intact. Do not resume without more *persistent* disk capacity.
- The owner can select a higher persistent-storage Codespace machine type (e.g. 64 GiB if available) after reviewing billing; this can stop/restart the Codespace. Never change paid resources without explicit owner authorization. Codespace stop destroys the paused process/RAM but preserves Library on disk.
- The ai/codespace-jobs branch presently includes tested one-purpose Unity terms confirmation, staged Python world-site sensor fallback, guarded unity_low_disk_pause and unity_resume_paused operations. These extra operations are NOT in main at this checkpoint; read queue branch code before using. The resume operation requires at least 4 GiB free and only continues a matching Unity process group.
- Read-only world-site sensing succeeded from the reviewed staged Python source: [run 41856938356](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41856938356). Source-file coordinates and native TreeInstances are not Unity-rendered pixels or collision tests.
- IMPORTANT queue discipline: push exactly ONE new .aaris/jobs/<unique-id>.json job per completed Actions workflow and matching result artifact. GitHub Actions permits one running and one pending per concurrency group; further job pushes can CANCEL a previous pending run, even when cancel-in-progress is false. Do not assume FIFO. Retry cancelled work with a fresh unique ID.
- After persistent disk expansion, verify free space and worktree; restore private desktop on the same Codespace; resume/restart Unity using the retained Library, finish compile and exact TerrainDemoScene load; perform native inspect, small reversible tree move/scale plus saved core readback and true camera screenshot. Keep screenshot artifacts short-lived, not committed to Git.
