# Aaris Unity CI agent instructions

Repository: sundamunda289-art/Unity-Game-Aris; branch: main. Public repository: NEVER commit or release passwords, tokens, Unity license files, Hub state, private content or secrets.

## Canonical world
Unity 6000.3.26f1, URP 17.3.0. Native source scene: Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity; 2km by 2km world on four real TerrainData tiles. See Docs/MAP_LAYOUT.json, README.md, the existing AarisExplorerBuild.cs and Tools/Validation before edits. Many assets are Git LFS tracked: a pointer is NOT a valid Unity scene. A Release checkpoint does not replace permanent Git history.

## GitHub Actions only; no Codespaces
- Primary workflow: .github/workflows/aaris-unity-photographer.yml. Main branch pushes trigger it. workflow_dispatch accepts intent=all, houses, roads, tiles or sky.
- Unity executes Aaris.MapReview.Editor.AarisCICapture.Capture. It opens the checked-in native scene and captures genuine HD PNGs. No -nographics; Xvfb plus Mesa and a real graphics device required.
- Photos and photo-audit.json are uploaded to Actions artifacts and live-photos Release. Black/white/flat images are diagnosed; no success claim for unverified visuals.
- Cache release tags: engine-cache for the compatible Library, project-checkpoint for changed project assets. Archives are SHA-256 verified and individual assets are kept under 2 GiB.
- Never publish credentials, license folders or the Git working database. Library is an expendable import cache, not a source-of-truth snapshot.
- Jobs are ephemeral and limited to 6h maximum. Periodic saves plus if: always() are best-effort; hard termination/cancellation can bypass final cleanup. Persist final project changes in Git.
- CI cannot be a permanently reachable interactive Unity Editor screen. It can automate Editor operations with intent commands; no exposed VNC server or Codespace needed.
- Reproducible cold starts depend on Docker image availability, license, LFS access, disk, cache and network; 1-2 minutes is not guaranteed.
- Do not overwrite real terrain, mesh, scene, prefab, material or .meta files just to make screenshots pass. Capture errors require investigation.
- Test Python checkpoint with: python Tools/CI/session_store.py selftest. Treat Unity activation as a separate required dependency; only use configured GitHub Secrets, never print them.

## 2026-11-06: Separate production pipelines (authoritative)
- **Python (always license-free):** .github/workflows/python-map-operations.yml runs blueprint auditing on relevant pushes; workflow_dispatch supports audit, inspect and review-only material sync. It never blocks on Unity credentials. Source checker: Tools/CI/map_static_check.py. Its PASS is a data/geometry consistency result, not proof that URP renders correctly.
- **Rendering (requires valid license):** .github/workflows/aaris-unity-photographer.yml probes UNITY_LICENSE in a masked step. Missing license SKIPS the expensive photo job while its preflight remains green. UNITY_EMAIL and UNITY_PASSWORD may enable the optional GameCI activation action; these are Unity ID credentials, never Gmail credentials. A ULF from an authorized activation remains essential for Personal.
- **Security:** Never publish .ulf, OAuth tokens, service-account keys, Google credentials or any credential to a public GitHub Release, artifact, cache, Git commit, or logs. No spoofed machine IDs or unapproved automation of licensing.
- **Ops reference:** Docs/UNITY_CI_SECRETS.md contains the three Secrets, mobile setup, limitations and verification links. The Unity CLI service-account flow does not activate Unity Personal; no guaranteed perpetual login on ephemeral hosted runners.

## License-free visual fallback
- Workflow `.github/workflows/python-map-operations.yml` generates five 1920x1080 coordinate-accurate **schematic** map review PNGs from `Docs/MAP_LAYOUT.json` on relevant pushes and dispatches.
- Download from `https://github.com/sundamunda289-art/Unity-Game-Aris/releases/tag/layout-review` or the Actions artifact. Each diagram is labelled **NOT A UNITY RENDER**; never interpret these as evidence that Unity houses, skybox, colors, trees or URP shaders render correctly.
- The schematic workflow stays independent of Unity login, GameCI, `.ulf` files and runner identity. Its outputs can be regenerated on any fresh runner.

## Cloudflare email-protected live Unity session
- Workflow: .github/workflows/aaris-live-unity.yml starts on-demand Xvfb + noVNC through a Cloudflare Quick Tunnel restricted with --allowed-mail, using the UNITY_EMAIL GitHub Secret.
- Local Python camera API: Tools/CI/live_camera_server.py. Editor-only bridge: Assets/AarisWorld/Editor/AarisLiveCameraBridge.cs. Numeric requests cannot execute shell commands or save scene assets.
- No valid UNITY_LICENSE means an accessible Linux desktop, not a functioning Unity Editor. Unity Personal can require interactive Unity Hub activation on a fresh machine.
- Phone guide: Docs/UNITY_LIVE_CLOUDFLARE.md. Quick Tunnel sessions are temporary and cannot supply persistent cloud computing or a stable hostname.

## Free Cloudflare camera hub / GitHub Issue commands
- Persistent read-only Cloudflare hub: https://aaris-unity-live-hub.aaris-game-control-6f9c.workers.dev
- Camera control GitHub issue #77: https://github.com/sundamunda289-art/Unity-Game-Aris/issues/77
- While an explicit live GitHub Actions session runs, Tools/CI/issue_camera_bridge.py polls for CAMERA x y z yaw pitch distance comments from repository owner sundamunda289-art only. It can upload actual Editor PNGs to the public live-photos Release, and responds with immutable PNG links.
- Cloudflare hub has no KV/R2 writes and no paid components. It cannot run Unity; GitHub Actions hosts the temporary desktop. Live view requires email PIN; Unity Editor itself needs authorized Unity licensing.
- ChatGPT can request and read snapshots via the GitHub connector, but cannot receive a continuously streaming video in this chat. See Docs/UNITY_LIVE_CLOUDFLARE.md.


## Verified intent-driven control and license boundary
- Post START_DESKTOP 15, START_DESKTOP 45, or START_DESKTOP 90 as the
  sundamunda289-art repo owner on GitHub Issue #77; ChatGPT with the linked
  GitHub app can post this owner-authorized command. It triggers a temporary
  GitHub Actions desktop without running any phone commands.
- The runner advertises its PIN-protected temporary Cloudflare Tunnel URL in
  a bot issue comment; the stable free Cloudflare Worker hub discovers it.
- Post CAMERA x y z yaw pitch distance on the same issue. The runner polls
  and responds with an actual Unity PNG link only after successful Editor
  camera rendering; otherwise it returns a clear error.
- Test run 42239962330 confirmed start/issue relay; camera request 6688056483
  returned a license-not-available timeout. Real Unity render remains BLOCKED.
- Do not infer that the live desktop is Unity itself without valid activation.

## Fresh-runner Unity Personal activation attempt (2026-11-06)
- Authorized bootstrap: Tools/CI/unity_personal_bootstrap.py. The live workflow uses the pinned GameCI container and tries a legitimately issued UNITY_LICENSE ULF, or official Unity CLI OAuth login followed by "unity license activate --personal --accept-eula --non-interactive", then the actual GUI Unity Editor and initial camera framing.
- For any OAuth request, the one-time Unity sign-in URL is stored only in ci-live-control/license-status.json inside the ephemeral runner, served on the protected Cloudflare noVNC page via /api/license, and never posted publicly or archived. The user may need to approve via phone each new runner. Unity Cloud service accounts and passwords do NOT automatically activate Personal.
- Only sanitized, predefined license states can be reported to GitHub issue #77; OAuth URLs and passwords are never included. The stable Cloudflare Worker hub displays those states.
- Restore only Unity Library import cache with actions/cache@v4; this cache must not contain the license, Hub OAuth state, cookies or other credentials. A cold Docker pull and Git LFS hydration still cost time.
- The CLI path is a documented activation attempt, not a proven entitlement for a new runner. Official Unity 6000.3 Personal docs say Hub sign-in is the supported activation method. Failure is signaled, not bypassed. Do not spoof Machine IDs or fake screenshots.


## Assistant-triggered license retry (owner-only, no keyboard on phone)

A connected GitHub assistant (authorized as repo owner sundamunda289-art)
can now post these exact commands on GitHub Issue #77:
- ACTIVATE_UNITY 15 — start a fresh 15-minute Actions desktop and attempt
  authorized Unity Personal activation (also 45 or 90).
- ACTIVATE_UNITY — retry the official Unity activation process inside the
  currently RUNNING pinned GameCI Unity container; do not replace its host.
- CAMERA -420 22 -210 0 20 22 — move camera if the real Editor is licensed.

The issue relay allows ACTIVATE_UNITY only for owner-authored comments;
it executes a constant, bounded Docker command, not arbitrary shell input.
The container remains alive after an unsuccessful activation so a retry can
be attempted without downloading the same Editor again in that session.

**Important**: An explicit ACTIVATE_UNITY command cannot bypass Unity's
license entitlement, browser sign-in or MFA requirements. It works without
the user's intervention only when a valid authorized ULF / active authorized
session is available in that new container. For Unity Personal, GameCI
documents one-time Hub activation -> ULF -> UNITY_LICENSE GitHub Secret.
There is no supported ALF-to-ULF Personal manual activation at present.
Unity Cloud Service Account credentials alone do not grant an Editor
Personal license. No machine identity spoofing or token caching is used.

Verified repo-level unit test for command handler and the workflow's
issue_comment path ran in GitHub Actions. An actual successful Unity
license activation and true scene PNG have NOT yet been verified.


## 2026-11-07: AI developer hands and eyes (one validated command protocol)

**The canonical GitHub repository is now `sundamunda289-art/Unity-Game-Aris`.** Older owner/repository links may redirect. Use `AGENTS.md` (plural), and never assume that a public dashboard showing Linux proves the Unity Editor was licensed.

**Read-only discovery first.** A GitHub-connected AI should inspect `Docs/MAP_LAYOUT.json` and use the owner-authorized GitHub Issue [#77](https://github.com/sundamunda289-art/Unity-Game-Aris/issues/77) to request a *real* Unity Editor response. Only comments authored by `sundamunda289-art` are processed by the live runner, while a GitHub Actions run is active. A connected AI must use an account/connection authorized as that owner; posting as a different account will not execute the command. Do not broaden this authorization to arbitrary GitHub users.

There are only three operational layers; do not create a separate script per object type:

1. `Tools/CI/ai_world_commands.py`: validates strict owner-issued `MAP {JSON}` intents, exact fields, finite bounded coordinates, object paths, and allowed operations. `python3 Tools/CI/ai_world_commands.py` runs its license-free selftest. No shell or C# execution is accepted in JSON.
2. `Assets/AarisWorld/Editor/AarisAIWorldBridge.cs`: Editor-only adapter; finds unique scene GameObjects, returns hierarchy path, world position/rotation/local scale, world-space renderer/collider bounds (metres), material names, and sampled mesh vertices. It can move/rotate/scale a selected Transform, or inspect/move/scale one native TerrainData tree instance by terrain name and zero-based index. It saves changed scenes/TerrainData through Unity's asset APIs. `blueprint` and `tree_blueprint` yield world-coordinate **PLY mesh-vertex samples** and JSON. Samples are not a watertight volume, a CAD mesh, material texture capture or a full topology reconstruction. Photo requests use a genuine Unity graphics device and reject nearly uniform blank images.
3. `Tools/CI/issue_camera_bridge.py` + `.github/workflows/aaris-live-unity.yml`: owner-only issue relay, timestamped status, public map JSON/PLY/photo Release links, PIN-gated cloud desktop, git-branch saving and best-effort verified session checkpoint. `Tools/CI/session_store.py` handles resumable project deltas, not Unity credentials.

**Supported commands** — one line per comment on Issue #77, with JSON keys/numbers exactly as shown. Start a session first, for example `START_DESKTOP 45`; allowed durations are 15, 45, 90, 240, and 300 minutes. `ACTIVATE_UNITY` can retry only an authorized activation, never bypass it.

```text
MAP {"op":"find","target":"Tree"}
MAP {"op":"nearby","x":-420,"y":20,"z":-210,"radius":40}
MAP {"op":"inspect","target":"Root/House/Wall"}
MAP {"op":"blueprint","target":"Root/Tree","samples":1024}
MAP {"op":"photo","target":"Root/House"}
MAP {"op":"move","target":"Root/Tree","x":2,"y":0,"z":-3}
MAP {"op":"rotate","target":"Root/Car","x":0,"y":15,"z":0}
MAP {"op":"scale","target":"Root/House/Wall","x":1.15,"y":1,"z":1}
MAP {"op":"tree_nearby","terrain":"Terrain","x":-420,"y":20,"z":-210,"radius":40}
MAP {"op":"tree_inspect","terrain":"Terrain","index":12}
MAP {"op":"tree_blueprint","terrain":"Terrain","index":12,"samples":512}
MAP {"op":"tree_photo","terrain":"Terrain","index":12}
MAP {"op":"tree_move","terrain":"Terrain","index":12,"x":2,"z":-3}
MAP {"op":"tree_scale","terrain":"Terrain","index":12,"width":1.25,"height":0.9}
CAMERA -420 22 -210 0 20 22
MAP_SAVE
```

- First run `find`/ `nearby`, then `inspect` for the exact, uniquely identified hierarchy path. Non-unique object names fail safely. `move` uses **world-space metre offsets**; `rotate` uses **degrees**; `scale` multiplies the selected object's **local** X/Y/Z scale by the factors. For a wall's thickness, select the **individual wall child**, not its whole house; for foliage select the leaf mesh child. Confirm the axis/material/mesh before editing. An edit to a prefab instance Transform does not rewrite its source prefab.
- Native TerrainData trees are **not ordinary GameObjects**. Use `tree_nearby` at map coordinates to discover the correct Terrain tree index and prototype, then `tree_inspect` for measured world-space 3D bounds before editing. Identify the correct Terrain and the tree index. `tree_move` uses metre offsets constrained to that Terrain tile; `tree_scale` multiplies width and height independently. This is per-instance; it does not edit shared leaf/trunk source mesh geometry. A PLY of a terrain tree is sampled from its prototype mesh and transformed approximately into world coordinates.
- All map outputs are **discrete** command responses; chat models do not receive continuous screen video. Results are uploaded to the public `live-photos` Release as `ai-world-<comment-id>.json`, `.ply` or `.png` and linked in the issue response. Treat JSON/PLY as data and PNG as a capture to visually verify; screenshot size/variance checks alone do not prove scene quality.
- Edits immediately save to the runner's native Unity scene or TerrainData. Run owner-authorized `MAP_SAVE` after a group of related edits to publish a **reviewable Git branch and PR**, preserving LFS filters. Do not merge automatically; review file diffs, LFS pointers, placement, collision and screenshot evidence first. No change to the source project is inferred from a schematic `Docs/MAP_LAYOUT.json` preview.
- For an interrupted run, a background checkpoint and final `if: always()` step attempt to save changed project assets to the checksummed `project-checkpoint` Release. A fresh runner checks out and hydrates source LFS, then restores the checkpoint **only if its source Git commit SHA matches**. If a Git PR has been saved, the durable edit lives on that branch until reviewed/merged; the checkpoint is not a replacement for merging it. A hard runner kill may interrupt checkpointing. Unity's `Library/` cache is only an import accelerator; no license/password/HUB state is stored.
- For failures, check `aaris-ai-diagnostics` Actions artifact (`issue-camera-relay.log`, `ai-result.json`, cache logs), the job summary, and the PIN-protected `/api/license` page. Never paste private OAuth URLs or license files into issues. If Editor did not activate, output an explicit failure rather than claiming screenshots or edits occurred.
- Keep object edits narrow. Avoid unnecessary modifications to `.meta`, materials, prefabs or LFS scenes. Do not auto-commit generated files from `Library/`, `Temp/`, `ci-live-control/`, license locations or private folders. Validate the actual Editor compilation/scene before declaring the automation production-ready.


## 2026-11-07: Owner-only AI terminal for ephemeral Actions runners

**Purpose:** You do not need Codespaces, Termux, or direct SSH to find out whether the
GitHub Actions computer is ready. Once a fresh live workflow run has started, an
AI connected as `sundamunda289-art` may comment on [Issue #77](https://github.com/sundamunda289-art/Unity-Game-Aris/issues/77)
and read back **sanitized live computer facts**. The bridge lives in
`Tools/CI/terminal_control.py`; the relay is `Tools/CI/issue_camera_bridge.py`.

Exact accepted commands (one comment per request):

```text
TERM PING
TERM HELP
TERM STATUS
TERM DISK
TERM PROCESSES
TERM EDITOR
TERM LICENSE
TERM ERRORS
TERM NETWORK
TERM LFS
TERM HISTORY
TERM ALL
```

- `TERM STATUS`: Editor/license/scene/photo status, last known compiler/error categories,
  free disk. `TERM DISK`: workspace/tmp/root free space and memory/CPU.
  `TERM PROCESSES`: bounded known process counts and Docker/Editor exit info.
  `TERM ERRORS`: only safe compiler error IDs, exception classes and error categories.
  `TERM NETWORK`: localhost VNC/API port checks. `TERM LFS`: checks native
  scene hydration and LFS count. `TERM HISTORY`: recent 30-second sampling.
  `TERM ALL`: comprehensive bounded state. `TERM PING`: confirm relay alive.
- Every owner-authorized command returns `AARIS_TERMINAL #<comment-ID>` with a
  machine-readable JSON response from the **actual current runner**. The output
  is PUBLIC on this GitHub issue; OAuth URLs, email addresses, authentication
  tokens, actual CLI arguments and raw Unity logs are never echoed.
- New sessions also write a sanitized 30-second health timeline to
  `ci-live-control/terminal-timeline-safe.jsonl`; the file is bundled into the
  `aaris-ai-diagnostics` Actions artifact when the job finishes.
- This is an allowlisted read-only terminal, **not general shell access**.
  Never add `bash -c`, arbitrary Docker exec from comments, paths supplied by
  users, raw `tail`/log dumps, or full shell access over public issues.
  To retry authorized licensing, use the existing distinct `ACTIVATE_UNITY`
  command; it cannot bypass Unity Personal entitlement or approvals.
- `editor_starting` means the GUI process was invoked, not that Unity Editor
  imported a scene. Require a real Editor heartbeat, successful map command,
  or genuine PNG capture to claim usable Unity Editor status. A running Docker
  container and a green verify job alone are not enough.
- CI regression test: `python3 Tools/CI/terminal_control.py --selftest`.
  `TERM` commands are supported only in sessions created *after* the changes
  are merged; an already running runner uses its old checked-out code.

## Private direct Unity approval (no Cloudflare email OTP)

When a trusted live GitHub Actions run requests Unity CLI OAuth, the background
`Tools/CI/private_unity_approval_publish.py` sends the short-lived,
Unity-owned `auth_url` to a **separate** Cloudflare Worker using an **OIDC
JWT signed by GitHub**, scoped to this exact repo, workflow, branch, and actor.

- Worker: `aaris-unity-approval-relay.aaris-game-control-6f9c.workers.dev`.
- Worker source: `Tools/CI/cloudflare_private_approval_worker.mjs`.
- Storage: private Cloudflare Workers KV namespace with 480-second expiry;
  public Worker endpoint can **write only when a valid signed GitHub Actions
  OIDC token is verified**. Public GET only exposes `/health`, never auth_url.
- The connected Cloudflare app, authenticated to the user's Cloudflare account,
  is the only available assistant path to read the private namespace via the
  Cloudflare account API and deliver the actual `https://id.unity.com/...`
  link directly in **this private ChatGPT conversation**. The URL does **not**
  go into GitHub public Issues, Actions artifacts, releases, logs, or commits.
- After retrieving the per-run URL, open the **official Unity** webpage from
  the phone and select the necessary Sign in / Allow. No Cloudflare email OTP
  is needed **for that direct Unity approval link**.
- This does not remove the separate email-PIN gate from the full VNC/desktop
  tunnel, which remains protected. It does not bypass Unity account login or
  Unity Personal licensing requirements.
- The bridge writes only a non-sensitive status to
  `ci-live-control/approval-bridge-status.json`, uploaded with diagnostics.
  Worker trust pins immutable GitHub repository/actor IDs and verifies RS256,
  issuer, audience, branch, workflow and timestamps.
- An assistant using the connected Cloudflare account can read KV value under
  key `run-<GITHUB_RUN_ID>` and return the genuine link privately. Delete or
  allow the key to expire after approval. Do not paste it into Issue #77.


## 2026-11-07: GitHub Codespaces AI terminal and screenshots (optional)

New persistent backend: `Docs/CODESPACES_AI_CONTROL.md`, `.github/workflows/aaris-codespaces-control.yml`, `.devcontainer/`, and `Tools/Codespaces/`. This does not replace the existing GitHub Actions world/photographer pipeline.

- As GitHub-linked repo owner `sundamunda289-art`, send one exact owner-only issue comment to Issue #77: `CS MACHINES`, `CS START`, `CS STATUS`, `CS SYNC`, `CS INSTALL`, `CS EDITOR`, `CS LICENSE`, `CS SHOT`, `CS TEST` or `CS STOP`.
- Each comment triggers the dedicated Actions controller (after merge to main). Read the returned issue comment and per-run artifact `aaris-codespace-<run-id>` for bounded terminal output, JSON status and optional PNG. This is not streaming SSH access for the chat.
- `CODESPACE_PAT` is a GitHub Actions Secret switched from Termux after GitHub HTTPS device authorization. The master repository remains unchanged when the Codespace account rotates; never add secrets, PAT, Unity login material, or machine IDs to source or public logs.
- Run `CS MACHINES` before `CS START` to inspect machine availability. `CS STATUS` probes actual CPU, memory, free disk and Editor process. `CS SYNC` hydrates LFS without resetting unsaved native Unity files.
- New Codespaces auto-install Xvfb/tools from `.devcontainer`; Unity Editor 6000.3.26f1 is installed separately on demand to `/tmp/aaris-unity-runtime/editors` and the Library/Temp import cache is symlinked onto /tmp where safe. Editor/cache may be erased by a Codespace restart; source Git/LFS remains authoritative. The project resides in `/workspaces/Unity-Game-Aris`; logs/screens in temporary `/tmp/aaris-codespaces`.
- Do not infer a licensed Unity Editor or real scene render from process launch or nonblank screen alone. Unity Personal still needs authorized Unity Hub sign-in, especially on a different Codespace. Never spoof machine-ID or clone OAuth/license files.
- Only checked-in task IDs can run through issue comments. No arbitrary shell, `eval`, user-provided paths, credential echoes or unsafe background command execution. New tasks require code review and static tests.

## 2026-11-07: Codespace installer remediation
- The optional Codespace Editor installer now uses the official Unity CLI via `Tools/Codespaces/install_unity.sh`; Hub CLI headless commands are deprecated. `CS LFS REPORT` is a read-only diagnostic command with sanitized pointer counts and failure kind. Preserve original LFS pointer SHA-256 and asset bytes; do not replace missing assets with generated surrogates. Genuine Unity Personal authorization may still need a one-time phone approval in the *current* Codespace. Do not print the OAuth URL on the public GitHub issue.

## 2026-11-07 Fast Codespace Resume
- One-time Editor install to persistent \`/workspaces/.aaris-unity-editors/6000.3.26f1\` using Unity CLI's supported portable \`--download-directory\` option; the Editor is reused on same Codespace stop/start.
- On restart, \`CS START\` then \`CS EDITOR\`, followed by \`CS STATUS\` and \`CS SHOT\`. No reinstalls when persistent Editor is available. Unity Library/Temp cache remains on /tmp to avoid running out of persistent disk; import may take longer after ephemeral storage reset.
- New account/new Codespace has its own storage and may require the initial Editor download and official Unity Personal login. Never move authentication cookies, license state, or machine IDs between Codespaces.

## Unity Personal phone approval on existing Codespace

- `CS AUTH` from owner Issue #77 runs Unity CLI browser sign-in on the actual Codespace; an Actions bridge intercepts the Unity-owned authorization URL and publishes it only to the protected Cloudflare OIDC relay.
- Retrieve with connected Cloudflare KV `aaris-unity-approval-private`, key `run-<Github Actions run id>`. Give the URL ONLY privately in ChatGPT, never in a GitHub public Issue, log, artifact or commit.
- User opens official Unity page on phone, signs into Unity (Google/Gmail if configured), taps Allow. Then the automation checks Unity login and attempts Personal entitlement activation, verifying final license status on the Codespace itself. Hub activation fallback may be required.
- User interaction is required when OAuth asks; no reuse of hardware IDs or login cookies across accounts.
