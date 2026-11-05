# Proven AI-only Unity Editor workflow — 5 November 2026

## Actual successful outcome

The full official **Unity 6000.3.26f1 graphical Editor** ran in the existing
GitHub Codespace on private Xvfb display :12, with **no phone/browser/noVNC
interaction required**. The real scene opened in Unity Editor's native
AssetDatabase. The Editor's file-based bridge completed native inspect, native
TerrainData tree move, independent readback, reversible restore, tree width
scale, inverse restore, and actual URP camera JPG rendering.

**This proof was on an isolated scratch copy**, not on the original tracked
working directory. Avoid misrepresenting it as a committed permanent map edit.

Repository: Aaris-khan-don/Unity-Game-Aris
Codespace: musical-carnival-jjxp9r6vw45wfjgvg
Original project: /workspaces/Unity-Game-Aris
Scratch project: /tmp/aaris-unity-batch/project
Scratch AI command root: /tmp/aaris-unity-batch/control
Original Unity executable: /home/codespace/Unity/Hub/Editor/6000.3.26f1/Editor/Unity
Exact scene: Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity

## Grounded results from actual Unity Editor

- [Scene readback, run 41946828885](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41946828885):
  scene valid/loaded, 7 roots, 4 Terrain components, **7,508 native terrain
  trees**, 84 Prefab assets and 256 Material assets. Root objects: Sun,
  Main Camera, Aaris_Island_2km, AarisPlayer, DaylightWind,
  BattleRoyaleProps, MobileRuntime.
- [Native site inspect, run 41946965648](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41946965648):
  near X=120 Z=75, ground Y=-10.2052m, slope 4.7938 degrees, two trees
  inside radius 45m.
- Native tree 778 from Terrain_2_2_b6e03cf0-de91-4cae-b6af-0128d856ae43.asset
  began at (102.307, -10.84896, 62.974), width scale ~1.1643 and height
  scale ~1.1936. [Unity Move result](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41947696009)
  shows the Editor moved it exactly 1m horizontally, saved its TerrainData,
  and reported X=103.307. [Independent inspect](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41947800955)
  read back the changed native tree from Unity. Reversed it with a second
  exact-identity/expected-position guarded command, then
  [independently verified original position](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41948099158).
- [Unity native width-scale result](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41948859975):
  width multiplier 1.1 changed widthScale 1.1643 -> 1.28073,
  heightScale unchanged. Reversed with 0.90909090909 multiplier:
  [restore result](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41948963579)
  and [final independent Unity inspect](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41949158546)
  show original location and width ~1.164300084, height ~1.193600059.
  Tiny floating-point differences are normal. This is a test-only
  edit/restore; do not merge test changes to the real map.
- [Actual URP camera render](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41948390862)
  produced a 960x540 JPEG at a position near the inspected tree. The
  [private short-lived Actions artifact](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41948498188)
  contained a 68,118-byte JPEG, SHA-256:
  e954a645932c26c4dabda956871b79ff0cea1920fefc2c007cb5be720e55c2d9.
  AI downloaded and viewed this image without a VNC screen. The rendered
  image shows ground vegetation, several narrow tree silhouettes, their
  shadows and a distant dark roadway. A render is not a gameplay/collision test.

## Actual control mechanism

**Currently tested implementation lives on the dedicated `ai/codespace-jobs`
branch**, in `Tools/World/ai_codespace_remote.py`,
`Tools/World/ai_codespace_executor.py`, and temporary
`Tools/World/AarisBatchProbe.cs`. Do not assume all experimental operations
have already been merged to `main`. The existing Actions queue checks out
the dedicated branch and uses the owner's authorized Codespace token to
start that exact Codespace (if stopped) and run reviewed SSH operations.

Submit **exactly ONE** new commit adding `.aaris/jobs/<unique-id>.json` to
`ai/codespace-jobs`. Wait until matching GitHub Actions run completes and
read `AARIS_RESULT_JSON` or its 1-day artifact before committing a second
job. GitHub Actions concurrency may cancel earlier pending jobs if multiple
pushes are made before previous ones finish.

The job JSON schema is `{"id":"<unique-id>","operation":"...","args":[]}`.
Relevant guarded operations:

- `unity_batch_launch`: creates a scratch project copy and tries
  `-batchmode -nographics`. **Do not use this on the existing Personal
  entitlement**: it failed with `com.unity.editor.headless` absent,
  exit code 198, in [run 41944846107](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41944846107).
- `unity_virtual_gui_launch`: launches a normal licensed Unity **GUI
  Editor on private Xvfb :12**, NOT `-batchmode`. It reuses scratch project;
  never launch another duplicate if `unity_virtual_gui_status` already
  shows a valid scratch Unity PID.
- `unity_virtual_gui_status`: process state, real Editor import log, scene
  JSON readback, scratch and original disk free, queued/completed AI responses.
- `unity_virtual_live`: single bounded JSON string in `args[0]`, with
  action `status`, `inspect`, `move_tree`, `scale_tree`, `move`,
  `scale`, or `capture`. All are implemented by the **real Unity
  Editor C# bridge**. A command may return `pending: true` while Unity
  compiles/imports. It is not an edit success until its result says
  `status: "ok"`.
- `unity_virtual_result`: `args: ["<previous-job-id>"]`, reads durable
  Unity native result and changed asset; verify by a separate `inspect`.
- `unity_virtual_frame`: `args: ["<capture-job-id>"]`, copies Unity camera
  JPG to a private GitHub Actions artifact with **one-day retention**. AI
  can fetch artifact, download ZIP and inspect image. **Never commit
  screenshots to Git LFS or Git history.**

Example native read request:

    {"id":"my-site-001","operation":"unity_virtual_live","args":["{\"action\":\"inspect\",\"cameraTarget\":{\"x\":120,\"y\":5,\"z\":75},\"radius\":45,\"limit\":16}"]}

For `move_tree` and `scale_tree`, copy the exact stable
`terrain-tree:GlobalObjectId...:index` from a fresh Unity inspect and
supply exact `expectedPosition`; that is the optimistic concurrency
guard preventing edit of a different tree after another AI changes it.
The native Editor writes TerrainData directly and calls
`AssetDatabase.SaveAssets()`; use a readback after each change.

## Critical persistence and operational limitations

1. **The imported scratch Library is on /tmp, which is temporary, NOT
   durable across Codespace stop/rebuild.** A successful test session does
   not yet deliver restart-safe import-cache persistence. The original
   retained project Library under /workspaces was deliberately untouched.
2. The original 32GiB persistent disk had only ~0.355 GiB free at these
   tests; the **separate /tmp disk had >95 GiB free**. Never force new
   import onto the original disk, delete Assets/Library, move the actual
   Unity Editor into /tmp or overwrite uncommitted source.
3. **No permanent game-map change was committed/pushed.** The reversible
   tree changes were made ONLY in the scratch project and restored.
   Permanent editing requires safe copy/PR/Git LFS synchronization from
   the scratch Unity-saved core asset, preserving the owner's existing
   uncommitted source changes and verifying asset hashes and Unity IDs.
   That *promotion/sync* mechanism has NOT yet been proven.
4. The source preflight proved **764/764 LFS tracked assets present**
   without refetch. See
   [Unity LFS preflight run 41875410235](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41875410235).
   Avoid global LFS pull/prune/reset.
5. Repeated shader/material import and shader warnings were seen on
   llvmpipe OpenGL; the Editor still opened the scene, read native trees,
   saved scratch TerrainData and rendered a JPG. Do not imply mobile FPS,
   Android build success or full visual fidelity is validated.
6. Do not ask the user to open noVNC; it is NOT part of this workflow.
   A virtual X11 display is still required to provide the normal
   licensed graphical Editor process.

## Next production-hardening steps

- Safely merge reviewed and tested scratch controller functions into
  `main` as an isolated tested Python module (do NOT merge the entire
  experimental queue branch or its hundreds of job JSON files).
- Add an authenticated, optimistic-concurrency, checksum-validated,
  backup-first mechanism to promote selected scratch Unity-saved
  `.unity`, `.prefab`, `.asset` or `.mat` updates to a clean new
  Git LFS PR, without changing `.meta` except when needed.
- Add persistent remote cache/recovery for scratch `Library` or use
  an appropriately sized persistent development disk; do not pretend
  that /tmp is restart-safe.
- Keep snapshots ephemeral; inspect output/scene for visual issues
  (thin/sparse trees, modest ground detail) and address mobile
  collisions/LOD/performance separately after functional tests.
