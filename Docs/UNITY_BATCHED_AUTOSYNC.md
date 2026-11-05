# AI Unity map edits — automatic batched Git LFS save (Nov 5, 2026)

## Why this is necessary

The real Unity Editor runs on invisible Xvfb :12 using
`/tmp/aaris-unity-batch/project`. Its native C# bridge edits and
saves actual `.unity` scene objects or TerrainData `.asset` files.
**Unity saving a file in /tmp does NOT make it durable.** Codespaces
clears /tmp when stopped; /workspaces and GitHub commits persist.
Never wait for a shutdown hook as the only protection.

The previous verified test confirmed 7,508 trees, actual Unity native
move/scale/Save/readback, and screenshots without noVNC.
Original `/workspaces/Unity-Game-Aris` may contain dozens of unrelated
user-modified/untracked files. Do not Git reset/clean/pull over them.

## Default save policy (not one push per edit)

- The normal Unity C# bridge writes a `unity-results/<job-id>.json`
  for every successful `move`, `scale`, `move_tree`, `scale_tree`.
  Failed requests, `inspect`, `capture`, reimport noise or screenshot
  files NEVER authorize a GitHub source upload.
- `Tools/World/unity_batched_autosync.py` groups **all changes to the
  same native Core File**. 10 successive tree edits to the same Terrain
  become ONE file snapshot and ONE Git commit per batch.
- **Three minutes (180 seconds) without a new edit** opens the batch;
  after **ten minutes (600 seconds) of continuous edits**, a batch
  becomes eligible even if work continued. It won't snapshot while
  unprocessed Unity commands are in the queue.
- The on-Codespace watcher only writes a tiny `pending_assets`
  journal into /workspaces every ~15 seconds. It cannot push Git by
  itself (real owner Codespace credential probe reported
  `git_credentials_unavailable`, Actions run
  [41959914477](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41959914477)).
- The **authorized GitHub Actions writer** at
  `.github/workflows/unity-batched-github-upload.yml`
  runs on an optional explicit `Save Session` command and on a
  10-minute schedule. It uses **GitHub Actions' temporary GITHUB_TOKEN**
  with repository contents write permission, rather than storing a
  GitHub Push secret in the Codespace. It checks whether the same named
  Codespace is already running. It does NOT start a stopped Codespace
  to attempt recovering already deleted /tmp.
- GitHub Actions copies only the selected verified binary Assets
  to its temporary runner, validates remote Git base and every SHA-256
  hash, uses a **separate ephemeral Git checkout** and Git LFS clean
  filter, then uploads all LFS objects, pushes one batch commit to
  `ai/unity-batched-...` review branch and verifies the remote
  SHA. It acknowledges saved hashes in the persistent journal.
  GitHub Actions attempts to open/update a PR; that step can be blocked
  by GitHub org/repo Actions PR permissions. **Never auto-merge**.
- Never copy changed scratch files directly over dirty original source.
  Never force-push, Git reset or prune current LFS objects. Git history
  retains old asset revisions; they are not physically deleted
  immediately when the PR is merged.

## AI commands

Use the existing owner-only GitHub Actions queue
(`ai/codespace-jobs`, one newly added JSON per turn):
`.aaris/jobs/<unique-id>.json`.

1. `unity_session_recover` — restore original scratch project and
   native Unity Editor on hidden Xvfb if necessary.
2. `unity_sync_arm` — arm autosync after the actual Unity scene has
   been loaded. This records current time to intentionally ignore
   historic scratch move/restore test results.
3. `unity_sync_watch_start` — verify Unity scene, start (or reuse)
   Codespace auto-journal watcher. It is NOT a keepalive and can't
   survive a Codespace stop.
4. `unity_virtual_live` — read/edit tree or objects via native Unity
   Editor as usual, verify response and independent readback.
5. `unity_sync_status` — inspect pending assets, quiet time,
   GitHub branch and last acknowledgement (read-only).
6. `unity_sync_dry_run` — detect Core File/.meta conflicts without
   writing or pushing.
7. `unity_sync_save_session` — **explicit AI Save Session**. To
   trigger the privileged GitHub Actions writer, use this one job JSON:
   `{"id":"unity-save-your-unique-id","operation":"unity_sync_save_session","args":[]}`
   and commit to the dedicated queue branch with a message **starting
   exactly `Unity Batch Save:`**. The existing read-only Codespace
   workflow will report `delegated_to_github_actions_writer`.
   The separate privileged writer workflow will carry out the upload.
   Read the latter workflow's log for `verified_github_batch_saved`
   and its branch/commit; DO NOT infer success from the first job alone.

## Fail-closed guards

- Only **tracked** Unity native `.asset`, `.unity`, `.prefab`, `.mat`
  files named by **successful Unity Editor** mutation results can
  enter the batch. No arbitrary new `.meta`, executable, Unity C#
  Editor script or ephemeral Camera JPEG can enter the batch.
- Refuse original dirty selected file; refuse source/.meta SHA mismatch
  against current remote Git/LFS; reject symlink, traversal, >12 Assets,
  >600 MiB total, low disk, pending Unity commands or in-flight Edit.
- After copy/export, verify SHA again to detect file changes mid-upload.
  Upload LFS **before** updating Git branch ref, then verify branch
  SHA and explicitly acknowledge a receipt in the persistent journal.
- If Actions/SSH/LFS/auth fails, state is **UNSAVED**, not successful.
  Never delete scratch or reset user's source to retry.
- An Action can complete after another Unity edit occurred: the
  acknowledgement saves only the SHA actually uploaded; a new digest
  will remain pending for the next batch.
- Explicit saves may occur before the normal 3-minute idle timer,
  but *not* while the Unity command queue is nonempty.

## Restart, retention and billing

A real Codespace stop clears **all** /tmp, including unpushed Unity
edits. The 10-minute scheduled Actions task is best-effort; GitHub
schedule delays, short idle timeouts and abrupt shutdowns mean it is
**not a guaranteed last-moment backup**. For crucial work, the AI
should send `Save Session` and verify the remote commit before
finishing its editing workflow or allowing the machine to stop.
The watcher and Actions schedule don't intentionally keep the
Codespace awake. Codespaces idle timeout was **not increased**.

A prior successfully pushed session branch and file SHA remain in
`/workspaces/.aaris-world-bridge/ondemand/unity-autosync-state.json`.
The engine includes a guarded `restore` operation for reapplying
verified remote session data to a *recreated scratch only*, but it
requires repository read credentials. The original Codespace lacks
working Git credentials, so **automated Actions-based restoration
must be added and tested** before claiming a complete post-stop
restore of unmerged PR branch edits. Until then, merge reviewed Git
branch changes through ordinary authorized Git/Git LFS workflows
and rehydrate the original source before reopening the project.

Tests live in:
- `Tools/World/tests/test_unity_batched_autosync.py`
  (including a real disposable local Git + LFS two-commit session)
- `Tools/World/tests/test_unity_actions_batch_sync.py`
  (owner-only write workflow and manifest/archive input checks)

Source: `Tools/World/unity_batched_autosync.py` and
`Tools/World/unity_actions_batch_sync.py`. Full tmp recovery:
`Docs/UNITY_TMP_AI_HANDOFF.md`.
