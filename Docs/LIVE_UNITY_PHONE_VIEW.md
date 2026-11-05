# Live Unity desktop on Android — no per-frame GitHub uploads

## Architecture (Actions-free)

ChatGPT/AI writes owner-authored JSON to `.aaris/relay-jobs/` on `ai/codespace-jobs`. The existing Cloudflare Worker polls GitHub once per minute and uses GitHub Codespaces REST to START a sleeping `musical-carnival-jjxp9r6vw45wfjgvg`. The **in-Codespace** `github_queue_agent.py` (after one-time installation) uses its own authenticated `gh api` to read approved jobs, launch bounded native Python/Unity actions, and write text-only receipts to `.aaris/relay-results/`. It does **not** require GitHub Actions, third-party SSH, or `AGENT_SHARED_SECRET`.

The live screen runs on that same Codespace: `Unity Editor → Xvfb :12 → x11vnc 127.0.0.1:5900 (password-protected) → websockify/noVNC :6080 → GitHub Codespaces PRIVATE forwarded port → owner phone browser`. Video frames are NOT added to Git, GitHub Actions artifacts, Cloudflare R2 or the chat.

Stable Cloudflare entry link: **https://aaris-codespace-relay.aaris-game-control-6f9c.workers.dev/live**

That Cloudflare route is intentionally a **302 redirect to the GitHub-authenticated PRIVATE forwarded port**, not a video proxy, and cannot bypass GitHub sign-in. Direct URL (only after noVNC is running and forwarded privately):
`https://musical-carnival-jjxp9r6vw45wfjgvg-6080.app.github.dev/vnc.html?autoconnect=true&resize=scale`.

**Do not make port 6080 Public.** A public forwarded port exposes a remote desktop and should never be used for this project. If an authenticated port cannot be forwarded, this design fails closed and no alternate public screenshot endpoint is created.

## One-time Codespace bootstrap (not yet independently verified as executed)

As of 2026-11-05 the old Issue #37 terminal bridge did **not** return a receipt for a new harmless `pwd` command after Codespace restart. A legacy owner-authored installer job has been queued for when that bridge resumes; a queued job **does not** prove installation. If it does not resume, in the actual Codespace's own browser Terminal run this once:

```bash
gh api "repos/Aaris-khan-don/Unity-Game-Aris/contents/Tools/CodespaceRelay/bootstrap_live.py?ref=ai/codespace-jobs" --jq .content | base64 -d | python3 -
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
