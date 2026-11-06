> **Current master instructions (2026-11-05):** Read [AI_MASTER_CONTROL_AND_AUTH.md](AI_MASTER_CONTROL_AND_AUTH.md) and root [AGENTS.md](../AGENTS.md) first. The command queue here remains valid, but the old 2026-11-04 setup observations (e.g. Unity GUI not verified or only a handful of operations) were superseded by 2026-11-05 real Unity Editor runs. Repository main reads now use the shared ephemeral Actions `GITHUB_TOKEN` authentication bridge (`Tools/World/ai_master_github_auth.py`); Codespace lifecycle uses a **different**, owner-managed `AARIS_CODESPACE_TOKEN` Actions secret; durable native Unity Git LFS writes use a separate, narrowly scoped Actions uploader. Do not request or paste a new personal GitHub credential when an authorized workflow already works.

# Aaris Codespace On-Demand Terminal (Issue #37 is NOT the primary inbox)

**Repository:** `sundamunda289-art/Unity-Game-Aris` (private); **Codespace:**
`redesigned-space-train-gxp5jwvq94wg2wvw6`; **queue branch** `ai/codespace-jobs`.
This controller lets an authorised AI post a **new JSON file** via the GitHub
repo connector, and read the matching **GitHub Actions run/log and JSON artifact**.
No persistent Termux or Codespace polling process is needed for this new path.

## Exact lifecycle / limitations

1. GitHub Actions (`Aaris Codespace On-Demand Terminal`) runs externally when
   a new `.aaris/jobs/<id>.json` is committed to `ai/codespace-jobs` by
   GitHub actor `sundamunda289-art`. Push must add EXACTLY one job file, and
   change/delete no other file. The job ID must match the new filename.
2. Action validates repository, sender, commit SHA and schema BEFORE using
   the credential. It checks the existing Codespace's name and repo via
   `GET /user/codespaces/{name}`. When stopped it calls
   `POST /user/codespaces/{name}/start`, polls the state until Available,
   then uses authenticated `gh codespace ssh`/`gh codespace cp` to transfer
   only the executor+job into `/workspaces/.aaris-world-bridge/ondemand/`.
   The active Git worktree is **not** checked out/reset/cleaned.
3. The executor runs a bounded, allowlisted action and returns JSON with
   `id`, `operation`, `ok`, `exit_code`, `stdout`, `stderr`. GitHub Actions
   includes `AARIS_RESULT_JSON=...` in the step log and uploads an
   `aaris-terminal-result-<commit-sha>` artifact. AI reads via the connected
   GitHub app's Actions run / job logs / artifact APIs, matching job ID. If no
   run/result exists, it MUST NOT claim the command ran.
4. GitHub Actions starting a stopped Codespace is best effort: account billing
   quotas, permission failure, `gh codespace ssh` failure, missing SSHD, and
   Codespace expiration/deletion can prevent success. If start API is down,
   a script running *inside* the stopped Codespace cannot self-recover.
   This service starts **on new AI job commits only**, not 24/7.
5. Launching a Codespace can incur compute charges and may resume an Editor
   that continues consuming RAM/disk. It will not invent a new Codespace or
   switch machine/branch; no changes to working tree.

## ONE-TIME OWNER BOOTSTRAP, via Termux, with credentials kept secret

This feature uses a **separate GitHub Actions secret** named
`AARIS_CODESPACE_TOKEN`. The ordinary Actions `GITHUB_TOKEN` is not authorised
for the account's personal Codespace lifecycle. Recommended: create a
**short-expiring fine-grained token** for account `sundamunda289-art` restricted
as much as GitHub allows to this repository, with **Codespaces lifecycle admin:
write** and **Codespaces: read**. It also needs Codespace SSH access through
GitHub CLI; GitHub API permissions may not by themselves guarantee SSH access.
Follow the least-privilege prompt from the linked GitHub docs and validate
against an actual Actions run. Revocation/expiration disables automatic wake.

If the owner deliberately elects to use the existing Termux GitHub CLI
credential (which may carry BROADER account permissions), the one-time command
below copies it directly into the private repository Actions secret over the
CLI, without printing it to chat, a job, logs, or a repository file:

```bash
gh auth status
gh auth token | gh secret set AARIS_CODESPACE_TOKEN -R sundamunda289-art/Unity-Game-Aris
```

Use a dedicated, narrowly scoped token instead where possible. Limit who has
write access to this private repository. GitHub Actions workflow files are
security-sensitive. Rotate/revoke if compromised. Never add credentials to
`.aaris/jobs/`, `AGENTS.md`, or Issue #37.

## New AI: how to send a job WITHOUT Issue #37

1. Read `AGENTS.md`, this document, and the two scripts; authenticate the
   connected GitHub app as `sundamunda289-art` with write access. Fetch the
   `ai/codespace-jobs` branch and the remote Actions workflow before writing.
2. Create one **new unique** file via GitHub's `create_file` action on branch
   `ai/codespace-jobs`, for example:

   File path: `.aaris/jobs/diagnose-20261104-001.json`

   ```json
   {"id":"diagnose-20261104-001","operation":"diagnose","args":[]}
   ```

3. GitHub Actions starts the Codespace if stopped, then delivers the job.
   Fetch the Actions run filtered by commit SHA; use the `Aaris Codespace
   On-Demand Terminal` run's job logs and JSON artifact to get the output.
   Match `id`, check `ok`, `exit_code` and verify actual effect.
4. If the run says `SETUP_REQUIRED`, bootstrap secret **once** in Termux.
   If SSH fails, compare `/user/codespaces/<name>` state and SSH diagnostics.
   Termux can then be used **once** for exception repair; permanent control
   should work from GitHub Actions without the Android phone online.
5. Do not retry by editing/reusing old job files. Give a new ID and file for
   each action. Worktree and LFS files remain untouched unless a future
   explicitly authorised script operation is added and reviewed.

Operations available today:

- `diagnose`, `args:[]` — Unity executable and disk, display status, process
  names, dirty Git tree status. No Unity project import.
- `desktop_xterm`, `args:[]` — launches one xterm GUI on existing Xvfb `:12`.
  This is a GUI smoke test, not a Unity map.
- `unity_version`, `args:[]` — calls Unity Editor `-version`, no import.
- `world_doctor`, `args:[]` — reads `Tools/World/ai_world_observe.py doctor`
  using external sensor venv where available.
- `terminal_readonly`, `args:[...]` — limited diagnostics `pwd`, `df`,
  `free`, `ps`, `stat`, `ls`, `du`, `glxinfo`, `pgrep`; no shell expansion,
  `python -c`, destructive git, arbitrary executable or source rewrite.

**Example:** new file `.aaris/jobs/gui-xterm-20261104-001.json` with content

```json
{"id":"gui-xterm-20261104-001","operation":"desktop_xterm","args":[]}
```

Jobs run serially via GitHub Actions concurrency. They aren't proof that
noVNC Browser screenshot matches a built APK. `unity_gui`/native map import
is **not enabled** yet: the Codespace currently has ~3.4 GiB free, which
is inadequate for reliable Unity Library, compilation or Android modules.
The actual executable was reported as Unity 6000.3.26f1 under
`/home/codespace/Unity/Hub/Editor/6000.3.26f1/Editor/Unity`, but each job
rechecks runtime state. VNC Xvfb :12, Openbox, x11vnc and websockify :6080
were manually verified by the owner on 2026-11-04. All are independent of
the new external controller.

## Verification bar (never overclaim)

- Local/CI unit tests mock Codespaces start/ready and reject job path,
  actor, schema and dangerous command operations. They **do not** prove
  authenticated access to the real Codespace.
- End-to-end proof requires one real job commit and a successful Actions run,
  including `id`-matched JSON from remote `ai_codespace_executor.py`.
- Keep the older Issue #37 worker as a historical/manual fallback only.
  It stopped responding to several recent commands; do not keep posting
  there as the default route and do not assume it self-starts.
## Restoring the phone-accessible Linux desktop after restart

An AI job with `operation: "desktop_xterm"` checks and revives Xvfb display
`:12`, Openbox, loopback-only x11vnc at `5900`, and websockify/noVNC at
`6080`. It then opens an xterm window and returns structured port and
process checks in `stdout`. Repeated jobs reuse existing processes rather
than installing packages or replacing the VNC password. The private
`~/.aaris-desktop/vnc.pass` must already exist; a missing password fails
closed. Do not include the password in any job file, CI logs, or chat.
The browser must reach a **private** Codespace-forwarded 6080 port.
This is only GUI transport: Unity's 6000.3.26f1 Editor and full game map
import are separate steps, and ~3.4 GiB free is currently insufficient
for a trustworthy complete Unity project import.

## VNC failure diagnostics without terminal access

To inspect failed graphical startup, submit a normal new on-demand GitHub
queue job with `"operation":"desktop_diagnose"` and `"args":[]`.
The response includes only whitelisted desktop log tails (Xvfb, Openbox,
x11vnc, websockify, xterm), VNC/non-VNC port statuses, and whether the
password file exists. It does not read or expose password contents.
Use this before guessing at service launch errors or asking the owner to
reopen Termux; all command results are available via the Actions artifact.

## Safe Unity disk audit and cache reclaim

`storage_audit` with empty `args` is read-only. It summarizes the true
local asset size, available disk space, known LFS records, clean-worktree
SHA-256 matches (sampled to 128 MiB so the Codespace job cannot time out),
modified core files to protect, and missing/pointer assets. It never
repairs files; deferred hashes must not be described as verified.

`prune_caches` with empty `args` deletes only two re-downloadable
non-Unity caches: `~/.cache/copilot/pkg` and `~/.npm/_cacache`.
It validates exact paths, avoids symlinks, and verifies the repo's
`git status` is identical before and after. On failure, stop and read
GitHub Actions job logs. Never clean `Assets`, `.git`, Unity Editor,
or any dirty user-authored mesh, LOD, material or scene asset.

## Exact LFS verification of the entire multi-GB saved map

Use an owner-only `lfs_verify_chunk` queue job with one decimal cursor:
`{"id":"lfs-check-unique-001","operation":"lfs_verify_chunk","args":["0"]}`.
After Actions finishes, read its JSON `stdout` and submit another **new**
job with `args:["<next_cursor>"]` until `all_done` is true.
Each job limits hashing to roughly 480 MiB, 145 entries and 75 seconds,
returns a source `head_sha`, and distinguishes `hash_matches`,
`hash_mismatch`, `dirty_protected`, `pointer`, `missing`,
`unreadable` and `large_deferred`. Sum the per-chunk categories and
reject a changing Git HEAD. Never describe deferred or dirty files as
byte-for-byte verified. A clean file with an LFS pointer is not a hydrated
asset. Git LFS transfer is only justified for real missing/pointer files;
no operations may revert modified Unity meshes, scenes, materials or scripts.

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
