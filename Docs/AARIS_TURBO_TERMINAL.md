# Aaris Turbo: dynamic low-latency Codespace terminal

This is an opt-in, private terminal connection independent of existing Unity and
APK workflows. It controls Codespaces visible to the currently configured
CODESPACE_PAT account. It does not create/delete/reset workspaces, touch native
Unity scenes, or publish command logs in a public GitHub repository.

## Architecture

ChatGPT Cloudflare connector -> authenticated private Cloudflare management SQL
API -> Durable Object queue for machine:<exact-name> -> Codespace Python agent
over outbound HTTPS -> durable output chunks -> Cloudflare account API.

No new GitHub Actions runner is launched for each terminal command.

## Initial start and recovery

Owner-only Issue #77: TURBO START <exact-codespace-name>
Or: TURBO START (only when exactly one Codespace is eligible).
The workflow_dispatch machine input accepts the exact machine name.

The isolated .github/workflows/aaris-turbo-bootstrap.yml starts an existing
stopped Codespace if necessary, obtains GitHub Actions OIDC credentials,
authenticates to the Cloudflare Worker, and installs/detaches Python agent
through one SSH session. A new start revokes the old token. Credentials remain
in owner-only Codespace home, not Git or public logs; they expire in 7 days.

The Codespace agent uses Python standard library only (no pip); it makes outbound
HTTPS requests. It maintains the session after Actions finishes. A stopped
Codespace cannot answer commands and needs a new bootstrap after restart.
Changing Codespace accounts still requires the right CODESPACE_PAT permission.

## Command submission from the existing connected Cloudflare account

Cloudflare Worker name: aaris-turbo-terminal
Namespace name: aaris-turbo-terminal_TurboMachine
Endpoint: https://aaris-turbo-terminal.aaris-game-control-6f9c.workers.dev/health

Read current machines using Cloudflare REST management API:
POST /accounts/{account_id}/workers/durable_objects/namespaces/{namespace_id}/query/v2

JSON body:
{
 "durable_object_name":"registry",
 "jurisdiction":"none",
 "queries":[{"sql":"SELECT name,stage,last_seen FROM machines ORDER BY last_seen DESC"}]
}

To submit a command to a specific machine use the same endpoint with:
{
 "durable_object_name":"machine:<exact-codespace-name>",
 "jurisdiction":"none",
 "queries":[{
   "sql":"INSERT INTO commands(id,argv_json,cwd,max_seconds,expires_at,status) VALUES(?,?,?,?,unixepoch()+600,'queued')",
   "params":["unique-job-id","[\"pwd\"]","/workspaces/Unity-Game-Aris",30]
 }]
}

The agent executes argv arrays without shell=True. To run a small Python script
submit argv_json equal to ["python3","-c","print(123)"] as a JSON-encoded string.
The active Codespace command cwd must be under /workspaces and exist on disk.
The agent can execute up to two jobs concurrently, with timeouts and private
stdout/stderr chunks. Its process environment excludes credential-related names.

Read status/output using the same endpoint with:
{
 "durable_object_name":"machine:<exact-codespace-name>",
 "jurisdiction":"none",
 "queries":[
  {"sql":"SELECT status,exit_code,error FROM commands WHERE id=?","params":["unique-job-id"]},
  {"sql":"SELECT seq,kind,text FROM chunks WHERE command_id=? AND seq>? ORDER BY seq LIMIT 100","params":["unique-job-id",-1]}
 ]
}
Continue using seq > last_seen_seq to read only new chunks. Agent polling every
1 second allows quick dispatch but total latency depends on network and API
timing; no fixed end-to-end latency is guaranteed.

## Safety and verification

- Only GitHub Actions OIDC signed for the exact main-branch owner workflow
  can provision agent grants; unauthenticated public command submission is off.
- Only privileged Cloudflare API permissions can add commands to the queue.
  Do not install/enable any unauthenticated public shell endpoint.
- Never put passwords, Unity licenses, API secrets, or OAuth links into any
  public Issue, workflow output or Git commit.
- Preserve any dirty Unity workspace and LFS assets; don't run a broad
  cleanup or reset. Consult AGENTS.md for all existing project invariants.
- A command INSERT is not proof of execution. Verify a matching command ID,
  an actual output chunk, and an exit code. For real Unity screenshots and
  Android build correctness use their independent validation procedures.
- An offline Codespace is detected through missing heartbeat; invoke one
  bootstrap workflow only when necessary.

## One Termux command for future account switches

The reviewed `Tools/Codespaces/termux_switch.sh` script now rotates the
selected account's `CODESPACE_PAT` and dispatches just ONE
`aaris-turbo-bootstrap.yml` GitHub workflow with `machine=auto`.
No manual Codespaces list/start commands or second workflow dispatch.

Install/refresh the phone helper from the canonical public repository:

```bash
pkg install -y gh curl jq
curl -fsSL https://raw.githubusercontent.com/sundamunda289-art/Unity-Game-Aris/main/Tools/Codespaces/termux_switch.sh -o "$HOME/aaris-switch.sh"
bash "$HOME/aaris-switch.sh"
```

The user authorizes a new Codespaces GitHub account in the browser once per
switch; the main account login is reused. To reuse both saved identities
and launch the same one-workflow bootstrap without a second browser login:

```bash
bash "$HOME/aaris-switch.sh" --resume
```

Bootstrap `auto` uses only the currently selected Codespaces token. If a
unique machine is visible it reuses that machine, including a stopped machine.
If none exists it creates one minimal Ubuntu SSH Codespace under the account's
own quota, then installs the private Cloudflare agent. If the account owns
multiple ambiguous Codespaces it fails closed, never chooses randomly.
Use an explicit exact machine instead when selection is ambiguous.

It cannot bypass GitHub Codespaces monthly quotas, temporary GitHub
provisioning delays, account permissions, or an absent Unity Personal license.
A successful GitHub bootstrap proves an agent was installed, not that the
Cloudflare command channel has passed a real end-to-end test. Verify registry
heartbeat and the stdout/exit code for a concrete command.

## Safe reconnect on minimal Codespace restart

The new minimal Ubuntu devcontainer uses postStartCommand to invoke
Tools/Turbo/ensure_agent.sh. After a successful, authenticated one-time
bootstrap, the installer stores the endpoint and seven-day grant expiry as
owner-private files in ~/.config/aaris-turbo alongside a mode-0600 token.
On a normal stop/start, an unexpired grant resumes the agent automatically
without a second GitHub Actions bootstrap. The hook is idempotent and does
nothing if its session files do not exist, are unsafe, or have expired.

This behavior applies to minimal Codespaces created with the updated
devcontainer configuration. Existing full Unity Codespaces and their
postStartCommand are deliberately unchanged. If the selected new account
has no permission, its capacity/quota is exhausted, or the Codespace remains
Provisioning/Shutdown, the agent cannot start; do not invent an online
heartbeat. Only read command status/output from the real Cloudflare broker.

## Private screen vision and GUI actions

The existing authenticated terminal channel also supports screenshot-on-demand:
Tools/Turbo/gui_agent.py. No temporary public trycloudflare.com URL is created.
This is NOT a continuous WebRTC/video feed, and the chat does not run a
background process indefinitely. A trusted assistant requests an action and
reads the new frame from the Cloudflare Durable Object private command output.

The owner-only Turbo bootstrap installs gui.py and gui_setup.sh in the private
~/.local/share/aaris-turbo directory. The basic desktop dependencies
(Xvfb, Fluxbox, xterm, scrot, xdotool, xclip, Python Pillow) are provisioned
non-blockingly after the terminal handshake. An existing Unity DISPLAY is
reused when set; otherwise the helper creates its own 1280x720 Xvfb :99
virtual display. No native Unity scene changes are made.

Run via the private Cloudflare commands queue (same machine object as terminal):
argv_json = ["python3","/home/vscode/.local/share/aaris-turbo/gui.py","look"]
Other allowlisted CLI subcommands are init, click x y, double_click x y,
right_click x y, move x y, key keysym, scroll integer, type bounded-text,
paste bounded-text. Never use them to bypass sign-in, license or other gates.
Each command emits AARIS_GUI_FRAME_SIZE, AARIS_GUI_FRAME_BASE64 and
AARIS_GUI_FRAME_COMPLETE to private output chunks. The agent stores these
chunks in the same authenticated Durable Object and reports the exit code.

The assistant can query chunks in order, join their text exactly, extract
the JPEG base64 value and view the actual screenshot privately. Do not
post screenshots or their base64 into public GitHub Issues, Actions logs,
releases or source. GUI screenshots may contain private on-screen content.
The snapshot includes a 100px coordinate grid and the current cursor.
Maximum JPEG payload 96,000 bytes; adaptive resolution and saved click-coordinate mapping preserve accurate GUI targeting. New frames are explicitly requested, never
uploaded continuously.

A screen showing an Xterm or desktop is NOT evidence that Unity has rendered
the game scene; inspect real Editor and scene camera render separately.

## Low-latency fast preview and private retention

Use the same trusted screenshot CLI with `--fast` to request a compact
image (at most 32,768 JPEG bytes) and avoid transmitting a full-resolution
frame for routine cursor/click feedback:

```
python3 ~/.local/share/aaris-turbo/gui.py look --fast
python3 ~/.local/share/aaris-turbo/gui.py click 400 200 --fast
python3 ~/.local/share/aaris-turbo/gui.py key Return --fast
```

The flag must be the **last argument**. Normal `look`, `click` and `key`
return a higher-resolution image (up to 96,000 JPEG bytes). The helper saves
the last frame dimensions privately and scales subsequent click coordinates
back to the real X11 desktop, including after a fast preview. Send coordinates
relative to the screenshot most recently received. Use full resolution when
inspecting Unity settings, small labels or fine visual defects.

For data minimization, the Cloudflare Durable Object automatically prunes
completed/failed command records and their stdout/stderr/screenshot chunks
after 24 hours. Expired unstarted commands are also pruned; active commands
are never pruned mid-run. Cleanup checks are throttled to hourly intervals
and require a valid authenticated agent ping. Avoid sensitive on-screen content
and never publish base64 frames to GitHub issues or Actions logs.
