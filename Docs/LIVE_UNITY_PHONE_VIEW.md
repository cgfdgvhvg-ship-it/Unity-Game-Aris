# Live Unity desktop on Android — no per-frame GitHub uploads

## Architecture (Actions-free)

ChatGPT/AI writes owner-authored JSON to `.aaris/relay-jobs/` on `ai/codespace-jobs`. The existing Cloudflare Worker polls GitHub once per minute and uses GitHub Codespaces REST to START a sleeping `redesigned-space-train-gxp5jwvq94wg2wvw6`. The **in-Codespace** `github_queue_agent.py` (after one-time installation) uses its own authenticated `gh api` to read approved jobs, launch bounded native Python/Unity actions, and write text-only receipts to `.aaris/relay-results/`. It does **not** require GitHub Actions, third-party SSH, or `AGENT_SHARED_SECRET`.

The live screen runs on that same Codespace: `Unity Editor → Xvfb :12 → x11vnc 127.0.0.1:5900 (password-protected) → websockify/noVNC :6080 → GitHub Codespaces PRIVATE forwarded port → owner phone browser`. Video frames are NOT added to Git, GitHub Actions artifacts, Cloudflare R2 or the chat.

Stable Cloudflare entry link: **https://aaris-codespace-relay.aaris-game-control-6f9c.workers.dev/live**

That Cloudflare route is intentionally a **302 redirect to the GitHub-authenticated PRIVATE forwarded port**, not a video proxy, and cannot bypass GitHub sign-in. Direct URL (only after noVNC is running and forwarded privately):
`https://redesigned-space-train-gxp5jwvq94wg2wvw6-6080.app.github.dev/vnc.html?autoconnect=true&resize=scale`.

**Do not make port 6080 Public.** A public forwarded port exposes a remote desktop and should never be used for this project. If an authenticated port cannot be forwarded, this design fails closed and no alternate public screenshot endpoint is created.

## One-time Codespace bootstrap (not yet independently verified as executed)

As of 2026-11-05 the old Issue #37 terminal bridge did **not** return a receipt for a new harmless `pwd` command after Codespace restart. A legacy owner-authored installer job has been queued for when that bridge resumes; a queued job **does not** prove installation. If it does not resume, in the actual Codespace's own browser Terminal run this once:

```bash
gh api "repos/sundamunda289-art/Unity-Game-Aris/contents/Tools/CodespaceRelay/bootstrap_live.py?ref=ai/codespace-jobs" --jq .content | base64 -d | python3 -
```

Review the source in GitHub before running it. The installer fetches only these already-reviewed GitHub files: `agent.py`, `github_queue_agent.py`, `bootstrap_live.py`, `ai_codespace_executor.py`. It stages to `/workspaces/.aaris-world-bridge/ondemand/`, and attempts two user systemd services, `aaris-github-queue` and `aaris-live-desktop`; it does **not** checkout/reset, commit, change LFS objects, or modify the Unity worktree. If user systemd is unavailable, it installs a `~/.bashrc` fallback and starts the agent in the current Codespace, but **full cold-boot autostart is not proven** until a real restart test.

A secure VNC password must exist in `~/.aaris-desktop/vnc.pass`. If not already configured, create one **privately in the Codespace Terminal** (never paste its value into ChatGPT or a GitHub issue):

```bash
mkdir -p "$HOME/.aaris-desktop" && chmod 700 "$HOME/.aaris-desktop"
x11vnc -storepasswd "$HOME/.aaris-desktop/vnc.pass"
python3 /workspaces/.aaris-world-bridge/ondemand/bootstrap_live.py --desktop-once
systemctl --user restart aaris-live-desktop.service 2>/dev/null || true
```

The desktop runner reuses existing `ensure_desktop()` in `Tools/World/ai_codespace_executor.py`. It refuses to create a passwordless VNC. It starts/revives `Xvfb :12`, `openbox`, `x11vnc`, `websockify :6080` and a small xterm, without changing Unity source or assuming Unity is running.

In Codespaces browser, open **PORTS → Add Port 6080 → Visibility: Private**. The URL above requires signing in as the Codespace owner and then entering the VNC password. Keep the browser tab open to watch the live screen. Codespace idle shutdown and browser/network limits still apply.

## Test that proves it works

1. Independently confirm `gh auth status` inside Codespace and that `aaris-github-queue.service` is active (or fallback process is running).
2. Create a new owner-authored terminal job: `{"id":"r20261105-live-status-01","action":"terminal","command":"system_status","args":[]}`. Verify an actual `.aaris/relay-results/<id>.json` with `source="codespace-github-agent"`, `status="ok"`, `exit_code=0`.
3. Queue `desktop_live_start` with no args, then `desktop_live_status` to confirm noVNC 6080 and local VNC 5900. Check PORTS 6080 is PRIVATE.
4. Open the Cloudflare `/live` link on the phone. GitHub's own authentication protects the screen; no per-frame file upload.
5. After the actual Unity GUI is visible on `DISPLAY=:12`, queue `unity_camera_focus` with numeric `[x,y,z]`. The native Unity live-bridge must be compiled and running; queue acceptance is NOT proof that the camera moved. Check the native result and visually confirm in noVNC.

Sample camera job:
```json
{"id":"r20261105-camera-demo-01","action":"terminal","command":"unity_camera_focus","args":[102.307,-10.849,62.974]}
```

Supported built-in terminal commands after bootstrap: `system_status`, `desktop_live_start`, `desktop_live_status`, `unity_virtual_start`, `unity_virtual_status`, `unity_camera_focus`, and the existing bounded Unity statuses/diagnostics and gallery checks. **No arbitrary shell** goes through this new queue.

## Operational caveats

- Cloudflare **lifecycle** was already verified with real GitHub receipts (`Shutdown → Available → Shutdown → Available`), but the **new in-Codespace queue agent and live screen remain unverified until the first terminal receipt and noVNC browser session**.
- A previous Codespace shutdown wiped `/tmp/aaris-unity-batch`. The Unity Editor/scratch may require safe recovery; a working VNC desktop alone doesn't prove Unity or the map is open.
- The earlier Unity camera capture SIGSEGV remains a separate native Editor issue; this live WebSocket transport removes repeated JPG transfers but is not a fix for a crash.
- If user systemd is absent, the `~/.bashrc` fallback starts when the terminal is opened, not guaranteed immediately on unattended Codespace boot.
- The Cloudflare Worker `/live` link is just an authenticated redirect; Cloudflare does NOT receive the image stream. A true Cloudflare Tunnel would need a domain with proper Cloudflare Access policy; no Cloudflare DNS zone was present when inspected, so this safe GitHub-private route was chosen.

## Fix for the 2026-11-06 Termux error / permanent viewer setup

The owner previously pasted the installer into Android Termux. That is **not** the Codespace; `/workspaces/Unity-Game-Aris` does not exist there, and installing `x11vnc` in Termux cannot show the remote Unity Editor. The installer now detects this and prints a clear error. The viewer's Cloudflare link is already stable but currently returned GitHub HTTP 404 because the remote server/forwarded port had not been initialized.

**One-time bootstrap directly from Termux using its existing authenticated `gh` CLI** (the commands run by SSH inside the real Codespace, not on the phone):

```bash
gh codespace ssh -c redesigned-space-train-gxp5jwvq94wg2wvw6 -- -tt "gh api 'repos/sundamunda289-art/Unity-Game-Aris/contents/Tools/CodespaceRelay/bootstrap_live.py?ref=ai/codespace-jobs' --jq .content | base64 -d | python3 -"
```

The script checks the expected remote project, stages the reviewed Python scripts and Unity camera bridge in the persistent bridge folder, asks **once** on the remote terminal to create the private VNC password (8 character VNC password compatibility), attempts user systemd services, and starts/revives the desktop. It outputs a **read-only LIVE_HEALTH_REPORT** including whether 6080 is listening; no credentials are printed or stored in Git. It stages the new C# focus code for the isolated scratch Unity scene and saves a backup before replacing that scratch-only Editor bridge. The original checked-out Unity scene and assets are unchanged.

One-time in Codespace web editor: forward port `6080` in **PORTS**, and confirm **Private** visibility. A forwarded port and a listening remote `websockify` are both required. The GitHub URL `https://redesigned-space-train-gxp5jwvq94wg2wvw6-6080.app.github.dev/vnc.html` returns HTTP 404 while the server/forwarding is absent. The Cloudflare `/live` entry link is unchanged.

### AI's place and manual navigation

The earlier Unity bridge `Inspect` action only returned nearby entities and **did not move the SceneView camera**. A reviewed C# patch now focuses `SceneView.LookAtDirect(center,...)`, repaints and saves the session when the AI queues `unity_camera_focus`. The patch must be staged and compiled in the **actual running scratch Unity Editor** before this can be considered working. A persisted focus is restored when the Editor can reopen the same scratch/session context; `/tmp` and unsaved scene state may be wiped on Codespace stop. Avoid claiming that every scene or camera state survives an unclean shutdown.

The phone can use noVNC touch gestures for mouse interaction, drag, scroll and zoom. Which gesture actually pans/rotates the **3D map camera** depends on Unity Scene View and noVNC mouse mode; pinch-to-zoom may scale the *viewer* instead. User interaction must be tested on the live Unity scene, not inferred from the protocol alone.

**Important limits:** a stable URL does not itself wake a stopped Codespace. The Worker must first start it through an authorized AI job (which has been verified). Auto-starting Codespace merely because anyone visits the public Cloudflare `/live` link would permit unauthenticated visitors to incur Codespaces charges. Cloudflare Access is not enabled in this account as of the last API read. Do **not** add unauthenticated wakeup-on-GET. If user-authenticated one-link wakeup is required, first enable Cloudflare Access and enforce an owner-only Access policy; then implement and independently test that route. This is a one-time additional authentication setup, not a per-frame transfer.

