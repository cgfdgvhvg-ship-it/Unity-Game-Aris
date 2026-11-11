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
