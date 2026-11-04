# Aaris Codespace On-Demand Terminal (Issue #37 is NOT the primary inbox)

**Repository:** `Aaris-khan-don/Unity-Game-Aris` (private); **Codespace:**
`musical-carnival-jjxp9r6vw45wfjgvg`; **queue branch** `ai/codespace-jobs`.
This controller lets an authorised AI post a **new JSON file** via the GitHub
repo connector, and read the matching **GitHub Actions run/log and JSON artifact**.
No persistent Termux or Codespace polling process is needed for this new path.

## Exact lifecycle / limitations

1. GitHub Actions (`Aaris Codespace On-Demand Terminal`) runs externally when
   a new `.aaris/jobs/<id>.json` is committed to `ai/codespace-jobs` by
   GitHub actor `Aaris-khan-don`. Push must add EXACTLY one job file, and
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
**short-expiring fine-grained token** for account `Aaris-khan-don` restricted
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
gh auth token | gh secret set AARIS_CODESPACE_TOKEN -R Aaris-khan-don/Unity-Game-Aris
```

Use a dedicated, narrowly scoped token instead where possible. Limit who has
write access to this private repository. GitHub Actions workflow files are
security-sensitive. Rotate/revoke if compromised. Never add credentials to
`.aaris/jobs/`, `AGENTS.md`, or Issue #37.

## New AI: how to send a job WITHOUT Issue #37

1. Read `AGENTS.md`, this document, and the two scripts; authenticate the
   connected GitHub app as `Aaris-khan-don` with write access. Fetch the
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
