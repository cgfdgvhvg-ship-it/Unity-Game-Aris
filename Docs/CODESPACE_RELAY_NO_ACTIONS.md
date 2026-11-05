## New live viewer and GitHub-direct agent (2026-11-05)

The new preferred terminal path is documented in **Docs/LIVE_UNITY_PHONE_VIEW.md**. It runs `github_queue_agent.py` inside Codespace using its existing GitHub CLI authentication and DOES NOT need `AGENT_SHARED_SECRET`; that second secret applies only to the earlier Worker `/v1/next` polling design. Cloudflare is still used for lifecycle and the `/live` entry redirect. The new installer has been committed to the review branch, but there is **no confirmed receipt that the Codespace boot service was installed or that noVNC port 6080 is live**. One-time installation in the Codespace terminal is still required if the old Issue #37 bridge does not resume. Until then do not queue persistent `terminal` jobs, because a pending job can repeatedly wake a sleeping Codespace and consume quota.

---

# AI → GitHub → Codespace relay without GitHub Actions

**State:** source is ready for one-time external deployment. **Not active until a Cloudflare Worker and an in-Codespace startup agent have been installed and tested.** This is not a workaround for a *Codespaces* account-payment block; it removes the dependency on **GitHub Actions runner minutes** only.

## Design

- Authorized AI posts one JSON file in `.aaris/relay-jobs/<id>.json` on the existing `ai/codespace-jobs` branch. No Actions workflow watches this separate directory.
- A **Cloudflare Worker Cron Trigger**, hosted outside Codespaces, polls this branch once a minute. It validates the job schema and confirms the latest job-file commit belongs to `Aaris-khan-don`. It uses GitHub's authenticated Codespaces REST API to **start**, **stop**, or inspect **only** `musical-carnival-jjxp9r6vw45wfjgvg` after verifying owner and repository. It records terminal lifecycle results in `.aaris/relay-results/<id>.json`. In `ShuttingDown` state, it does **not** send a conflicting Start call.
- For `terminal` requests, it starts the stopped Codespace if possible, then exposes exactly one bounded job through an authenticated endpoint. A **separate Codespace agent** polls this endpoint on boot, runs only approved actions, and sends a bounded result back. The Worker writes the result in the same GitHub result directory. Arbitrary shell, file deletions, private credential reads, and unreviewed commands are not supported.
- The agent keeps an append-only local command receipt in `/workspaces/.aaris-world-bridge/relay-local-results/`. A failed network upload cannot cause the same accepted command to be executed again on retry.
- GitHub Actions is **not** in the execution path. `main` and the active Unity worktree are not checked out, reset, or merged by the relay.

## Source

- `Tools/CodespaceRelay/worker.mjs`: scheduled controller + signed-agent interface
- `Tools/CodespaceRelay/wrangler.toml`: one-minute schedule, **disabled by default**
- `Tools/CodespaceRelay/agent.py`: guarded Codespace agent, 0600 config setup, optional systemd user service
- `Tools/CodespaceRelay/test_worker.mjs`, `test_agent.py`: local protocol/auth/idempotency checks

## One-time deployment (requires user's Cloudflare account)

**Do not paste tokens, secrets, credentials, access codes, or full `gh auth token` output into a conversation, an issue, or the repository.** A token for this private repository needs GitHub repository Contents read/write and Codespaces lifecycle admin write, using the narrowest permissions and expiry possible. It is kept only as a **Cloudflare Worker secret**. The agent uses a *different* randomly generated shared secret, not the GitHub token.

1. Log in to Cloudflare and deploy the Worker `worker.mjs` and `wrangler.toml`. The `wrangler.toml` sets `RELAY_ENABLED="false"` so initial deployment cannot start or stop the Codespace. Cloudflare Cron is configured by `crons = ["* * * * *"]` and may take a short time to propagate.
2. Use `npx wrangler login` then, from a directory holding the two Worker files, `npx wrangler deploy`. Set **both** secrets via Wrangler prompts: `npx wrangler secret put GITHUB_CONTROL_TOKEN` and `npx wrangler secret put AGENT_SHARED_SECRET`. Do not put their values in source, shell history, or `wrangler.toml`.
3. Edit only the local `wrangler.toml` variable to `RELAY_ENABLED="true"` and deploy again. Confirm `https://<your-worker>.workers.dev/health` responds `{ "service": "aaris-codespace-relay", "version": 1 }`. This proves the HTTP Worker is deployed, **not** that a Codespace command ran.
4. Copy the approved agent script to a **persistent, separate staging directory** within the Codespace (`/workspaces/.aaris-world-bridge/ondemand/agent.py`). Also stage the reviewed `ai_codespace_executor.py`, its `unity_session_checkpoint.py` and `AarisBatchProbe.cs` if Unity recovery will be used. Never overwrite the original dirty Unity source or delete existing staged files without checking content.
5. Inside Codespace, run `python3 /workspaces/.aaris-world-bridge/ondemand/agent.py --setup` and enter the **Worker HTTPS origin** and the distinct **agent shared secret** through the non-echoing prompt. The resulting private configuration is `~/.config/aaris-relay/config.json` (mode 0600). Test `python3 /workspaces/.aaris-world-bridge/ondemand/agent.py --once` with a harmless queued `system_status` job.
6. To start the agent on every Codespace boot, try `python3 /workspaces/.aaris-world-bridge/ondemand/agent.py --install-service`. This creates an optional **user systemd service** and only claims success if `systemctl --user` actually accepted it. **Some Codespaces lack a user systemd session.** If it fails, explicitly configure the actual Codespace's `.devcontainer/devcontainer.json` `postStartCommand` to launch the agent, preserving existing postStart commands. The existing Codespace source branch must be checked before changing devcontainer settings; do not assume this review branch is the running source branch. **Without a working boot hook the Worker can wake a Codespace, but cannot execute a terminal command inside it.**
7. Test jobs in sequence using owner-authorized GitHub `create_file` on **branch `ai/codespace-jobs`**. Read the actual result from `relay-results`, not an Actions run. Verify a real shutdown → boot → `system_status` sequence before claiming end-to-end operation. Respect Codespaces usage/billing and avoid an endless start/stop loop.

## Jobs to create (each in a new file)

Start: `.aaris/relay-jobs/r20261105-demo-start.json`

```json
{"id":"r20261105-demo-start","action":"start"}
```

Status: `.aaris/relay-jobs/r20261105-demo-status.json`

```json
{"id":"r20261105-demo-status","action":"status"}
```

Terminal test: `.aaris/relay-jobs/r20261105-demo-terminal.json`

```json
{"id":"r20261105-demo-terminal","action":"terminal","command":"system_status","args":[]}
```

Explicit stop, only when it is safe to discard `/tmp` files: `.aaris/relay-jobs/r20261105-demo-stop.json`

```json
{"id":"r20261105-demo-stop","action":"stop"}
```

Allowed terminal commands: `system_status`, `unity_status`, `unity_recover`, `unity_gallery_start`, `unity_gallery_diagnose` (one existing gallery ID), `unity_gallery_partial_export` (one existing gallery ID), `unity_frame_check` (one existing frame ID). `unity_recover` uses the existing scratch-only guarded Unity recovery code and requires the trusted staged files. The `unity_gallery_start` command queues real Unity cameras only **after** a verified live Unity Editor and bridge exist. This architecture does **not** fix the previously observed native Unity SIGSEGV in camera capture.

**Important:** `start_requested` and `stop_requested` receipts prove GitHub accepted the API request, not that the final state was reached. Submit a **new `status` job** to verify `Available` or `Shutdown`. For `terminal` jobs, require a result with `source: "codespace-agent"`, `status: "ok"`, and `exit_code: 0`. If there is no result, no successful terminal operation is proven.

## Photos after recovery

Codespace's `/tmp` is ephemeral and previous real JPGs were lost when it stopped. After regenerated real scene photos are confirmed, **download them to the phone immediately**, before stopping Codespace:

```bash
CS=musical-carnival-jjxp9r6vw45wfjgvg
mkdir -p "$HOME/aaris-house-photos"
# Replace EXACT_FRAME_ID with a verified existing filename from the agent's Unity gallery status.
gh codespace cp -e -c "$CS" \
  'remote:/tmp/aaris-unity-batch/control/frames/EXACT_FRAME_ID.jpg' \
  "$HOME/aaris-house-photos/EXACT_FRAME_ID.jpg"
```

A photo is not created by this relay itself; the existing native Editor bridge must succeed. Do not fabricate images or downloadable URLs.

## Scope and security

- This is a narrow automation on one account, repo, Codespace, and protected queue branch. GitHub permissions and trusted commit authors are verified for every request. Treat branch write permissions and Worker deployment permissions as sensitive.
- No arbitrary command execution: IDs, operations, argument counts, and native operations are explicitly allowlisted twice.
- There is no interactive public terminal, open SSH port, or API route taking shell strings. Worker `/health` has no secrets; agent endpoints require a separate bearer secret.
- Only a successful deployment plus real Codespace CLI/REST state and terminal receipt will prove this works; unit tests alone are not evidence of cloud execution.
- Cloudflare usage limits, Codespaces usage budgets, and GitHub API permissions remain applicable. A Codespaces API `402` or `403` is **not** bypassed by an external Worker.

## Actual Cloudflare deployment — 2026-11-05

- Connected Cloudflare account: the existing owner account (never publish its ID or tokens).
- Worker script **`aaris-codespace-relay`** uploaded successfully to Cloudflare from this GitHub review branch, Git blob `91cf65dcd4f535bf1a4d3c20a0ea6e59629fe2d2`.
- Account workers.dev subdomain created: `aaris-game-control-6f9c.workers.dev`. Worker route: `https://aaris-codespace-relay.aaris-game-control-6f9c.workers.dev/health` (route enabled and previews disabled by Cloudflare API; public HTTP reachability has **not** been confirmed from this runtime).
- Scheduled cron successfully configured and read back as `* * * * *` (every minute, UTC).
- Worker bindings successfully read back as `RELAY_ENABLED=false`; **no Worker secrets are currently configured**. The relay is therefore **inert** and cannot start, stop, or run commands in Codespaces. Do not describe it as operational.
- The ChatGPT GitHub connector has repository operations but does not expose the account's GitHub credential for use by a different provider. The Cloudflare connector cannot read Github Actions repository secrets either. A scoped GitHub token must be installed as `GITHUB_CONTROL_TOKEN` directly through the Cloudflare dashboard, **not in chat, GitHub repo, or logs**. A distinct generated `AGENT_SHARED_SECRET` must also be configured for the Codespace agent. Do not enable the relay before those secrets and the agent startup hook are verified.
- If Cloudflare or the GitHub Codespaces API reports the account's own billing/quota restriction, **do not** attempt to circumvent billing; use the provider's normal account remediation. GitHub Actions billing is separate from whether the Codespaces REST API can start an available Codespace.

## Verified GitHub Actions-free lifecycle — 2026-11-05

Cloudflare account `aaris-codespace-relay` uses the protected `ai/codespace-jobs` queue. Direct GitHub connector-written relay jobs and independent Cloudflare-cron receipts verified:

- `r20261105-initial-status-a1`: `Shutdown` (18:01:40 UTC).
- `r20261105-start-after-shutdown-a1`: `start_requested` from `Shutdown` (18:02:42 UTC).
- `r20261105-verify-start-a1`: `Available` (18:03:40 UTC), confirming an actual wake.
- `r20261105-stop-via-cloudflare-a1`: `stop_requested` from `Available` (18:04:42 UTC).
- `r20261105-verify-stop-a1`: `ShuttingDown` (18:05:41 UTC).
- `r20261105-verify-stop-b2`: `Shutdown` (18:06:41 UTC), confirming an actual stop.
- `r20261105-start-final-after-stop-a1`: `start_requested` from `Shutdown` (18:07:43 UTC); a status receipt in the same cron tick still showed `Shutdown`, so require a **later** independent observation to certify the final boot.

The Worker now has `RELAY_ENABLED=true` and `GITHUB_CONTROL_TOKEN` stored as a Cloudflare Secret. Do not commit or reveal its value. `AGENT_SHARED_SECRET` and an in-Codespace agent autostart hook are **not yet configured**. Therefore remote **terminal command execution has not been demonstrated**, even though lifecycle is working. Preserve the original dirty Unity worktree and keep PR #75 unmerged.

