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

## AI scene developer protocol (2026-11-06; proposed branch `ai/scene-operator-v1`)

**Mission: give a GitHub-connected AI read / measure / inspect / move / resize / photograph abilities without giving it a general shell over a public Issue.**

The canonical scene remains `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`. The new system reuses the existing Cloudflare/noVNC desktop and Issue #77 instead of creating many separate executables.

### Only two agent-facing tools

1. `Tools/CI/ai_intents.py` is the validated JSON intent schema, Issue queue dispatcher, response/blueprint publisher, and **safe LFS commit** layer. The existing `issue_camera_bridge.py` imports it and polls owner-authored comments.
2. `Assets/AarisWorld/Editor/AarisAIControlBridge.cs` is the Unity Editor eye/hand. It reads `ci-live-control/ai-command.json` (not untrusted C#), inspects the Unity scene/meshes/terrain trees and writes `ai-result.json`. The existing `AarisLiveCameraBridge.cs` provides the real camera render method.

No terminal/codespace required for a GitHub-connected AI. A GitHub issue comment authored by `sundamunda289-art` on [Issue #77](https://github.com/sundamunda289-art/Unity-Game-Aris/issues/77) is the command transport.

### Start / license / see

- Start owner Issue comment `START_DESKTOP 45` (or `15`, `90`, `240`, `300`). This starts an **ephemeral** Actions Linux desktop and pinned Unity 6000.3.26f1 container. The protected temporary Cloudflare Tunnel is announced in Issue #77. See the stable [Cloudflare hub](https://aaris-unity-live-hub.aaris-game-control-6f9c.workers.dev).
- Use the email-PIN-protected desktop to complete any **official** Unity sign-in / Personal activation. License status is shown at `/api/license`; only a licensed running Editor can return a genuine PNG. OAuth links and ULF files must never appear in issue comments, public photos, Git history, or logs.
- The phone may use noVNC to watch the live screen. AI clients see discrete JSON + authentic PNG snapshots via the GitHub issue/release interface, **not continuous screen video**.
- The 240/300-minute sessions do not extend GitHub's maximum job lifetime. A new runner starts from Git + LFS, and cached `Library/` only accelerates Unity imports; it is **not** permanent compute.

### AI JSON commands: exact format

Post a single line beginning with `AI ` followed by a small valid JSON object. No markdown code fences. Examples (target IDs are illustrative: always find before editing):

```text
AI {"op":"find","query":"House"}
AI {"op":"inspect","x":-420,"y":22,"z":-210,"radius":40}
AI {"op":"bounds","target":"Village[2]/House[1]/Wall[0]"}
AI {"op":"outline","target":"Village[2]/House[1]","max_points":512}
AI {"op":"photo","target":"Village[2]/House[1]","distance":30}
AI {"op":"move","target":"Village[2]/House[1]","dx":1,"dy":0,"dz":-2,"dry_run":true}
AI {"op":"move","target":"Village[2]/House[1]","dx":1,"dy":0,"dz":-2}
AI {"op":"scale","target":"Village[2]/House[1]/Wall[0]","sx":1.15,"sy":1,"sz":1}
```

`find` searches active-scene GameObject names; `inspect` reports near a position (including real Terrain tree instances); both return at most 80 objects. `bounds` reports world-space renderer bounds and world metre dimensions, or position-only if unavailable. `outline` samples up to 2048 readable mesh vertices in world XYZ (and produces a three-view *dot blueprint* SVG); this is not a complete mesh export, convex hull, foliage physics simulation, nor proof of realistic materials.

A native Terrain tree is identified as `terrain-tree:<tile-index>:<instance-index>` from the `inspect` report. This is an instance in a TerrainData asset, not an ordinary GameObject: `move` and `scale` use the Terrain API and save its asset. Native tree `widthScale` is horizontal (so `sx` must equal `sz`) and `heightScale` is vertical; a per-leaf or per-trunk edit requires a separately reviewed prototype/mesh authoring feature. Native tree `outline` is not implemented yet and returns a clear unsupported error. Do not substitute a fake 3D outline for it.

Each `move`/`scale` is limited to bounded numeric deltas/factors and can be previewed with `dry_run:true`. A write saves its Unity scene/TerrainData source, then commits **only the exact allowlisted changed asset** to Git LFS (when LFS-tracked) on `ai-map-edits`, not to main. For big changes: first inspect dimensions, then dry-run, then write one small change, inspect again, capture photo, and review the diff/PR. There is no user-provided shell, path, or arbitrary code execution. A failed Git push reports persistence failure even if Unity saved locally; do not claim the new runner will remember it.

The result JSON and optionally three-view blueprint SVG or genuine PNG are published under unique issue-comment IDs to the public `live-photos` Release. The PNG is a real Unity Editor camera render, **only if** license, Editor launch, mesh import and graphics actually worked. The report carries the exact `nonce` so stale photos/results are rejected. Public artifacts should contain no personal data or secrets.

### Persistence / restore / cross-session safety

- `.github/workflows/aaris-live-unity.yml` checks out main with history and either creates `ai-map-edits` or fetches/merges the existing remote edit branch before Unity starts. Conflicts stop the run; never force-push or discard a player's scene silently.
- Native `.unity` and `TerrainData .asset` can be LFS binaries; `git lfs pull` must hydrate before Editor launch. The Git branch holds permanent source changes; `Library/`, `Temp/` and login data never become source-of-truth.
- Because host runners can be killed, all progress must be committed after each authorized write. Running an Editor on a new VM still depends on legitimate Unity activation each session, if needed. There is **no** promise of unattended activation or guaranteed screenshot latency.
- Always retain separate distinction: `PASS` in Python static tests vs compile PASS in Unity Editor vs real rendered PNG verified from actual scene.

### Safe validation

```bash
python3 -m py_compile Tools/CI/ai_intents.py Tools/CI/issue_camera_bridge.py
python3 Tools/CI/ai_intents.py
python3 Tools/CI/issue_camera_bridge.py --selftest
python3 Tools/CI/session_store.py selftest
```

The `verify` job checks Python intent handling without a Unity license. Real Editor compile test and authorized capture cannot be asserted until a Unity license is active and the live `ai-map-edits` branch is running.
