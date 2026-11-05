# Aaris AI Master Control — GitHub, Codespace, Unity and LFS

**Current default playbook, 2026-11-05.** Owner repository: **Aaris-khan-don/Unity-Game-Aris** (private). Read this from the **main branch** alongside root AGENTS.md. This document supersedes the older Issue #37 command inbox guide.

## First: no universal password, no credentials in the repository

An "AI master controller" is a router for existing, separately scoped credentials **and reviewed actions**; it is **not a permanent unrestricted token**. Never put a GitHub PAT, password, SSH private key, VNC password or GitHub App private key in AGENTS.md, .aaris/jobs/*.json, Python source, a git remote, a Git commit, a PR, a chat message, or screenshots/logs. Connecting an AI GitHub app is separate from GitHub Actions secrets. A new AI needs its own authorized GitHub connection or app installation; merely reading AGENTS.md does not give it private repo access.

### Credential matrix (the real master logic)

| Task | Auth source | Lives where | Safe scope |
| --- | --- | --- | --- |
| ChatGPT/other authorized AI inspects/edits code | Its connected GitHub integration, authorized by owner | Connector permission manager | This single private repo, changes through reviewed branches and PRs |
| CI/AI reads main and downloads approved source | Automatically issued GITHUB_TOKEN, job with contents:read | GitHub Actions **environment only** | This repository, short-lived; never persisted |
| Start/reconnect the **existing** Codespace and SSH into it | AARIS_CODESPACE_TOKEN | GitHub Actions **repository secret** | Codespaces lifecycle/read and necessary SSH access; not a general repo-write token |
| Durable verified Unity .asset/.unity/.prefab/.mat and Git LFS upload | Automatically issued GITHUB_TOKEN with contents:write in dedicated privileged uploader | .github/workflows/unity-batched-github-upload.yml | Only SHA-verified native edits to isolated review branch; no auto-merge |
| Optional unattended external CI app requiring separate identity | Short-lived GitHub App installation token, repository-scoped | Minted at run time from GitHub App credentials stored as Actions Secrets | Only approved repo and requested permissions; token expires in approximately 1 hour |

**Do not grant all available account/repo scopes to one PAT.** Built-in Actions GITHUB_TOKEN has the correct repository identity and is preferred for GitHub Actions. Use a GitHub App installation token only if this built-in token does not cover a legitimate cross-workflow use case. GitHub Apps cannot replace a personal Codespace user's own lifecycle/SSH authorization on every endpoint.

## Which authentication error was fixed?

The 2026-11-05 main-source sync initially failed inside an Actions runner with:

  fatal: could not read Username for 'https://github.com'

Reason: the on-demand workflow deliberately runs actions/checkout with persist-credentials:false. A later reviewed run correctly passed the job's read-only GITHUB_TOKEN via a **temporary GIT_ASKPASS helper** and fetched the specific reviewed main commit. The source sync and screenshot succeeded; this is NOT evidence that the original Codespace has persistent git credentials. Evidence: Actions [failed fetch](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42018268487), [verified source sync](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42018998527), [Unity screenshot](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/42019277235).

**Reusable implementation:** Tools/World/ai_master_github_auth.py. It:
- Uses job-scoped GITHUB_TOKEN (or optional already-minted AARIS_GITHUB_APP_INSTALLATION_TOKEN) only in the verified GitHub Actions workspace.
- Validates GITHUB_REPOSITORY == Aaris-khan-don/Unity-Game-Aris and an exact reviewed 40-character main commit.
- Fetches ONLY https://github.com/Aaris-khan-don/Unity-Game-Aris.git main, without a token in the remote URL, git command-line args or persistent credential store.
- Disables interactive prompting and inherited Git credential helper; deletes temporary askpass script immediately.
- Redacts all git fetch stderr/stdout upon failure; never sends the token to the Codespace.
- Refuses to fetch into /workspaces/Unity-Game-Aris or any other owner dirty working copy; a reviewed main mismatch fails closed.
- Has status (boolean capability check, not the secret) and unit tests in Tools/World/tests/test_ai_master_github_auth.py.
- Is a **read-only transport broker**; does not authorize shell, pushes, force merges, dangerous LFS changes or changes outside this game.

One useful diagnostic in a trusted Actions checkout:

  python3 Tools/World/ai_master_github_auth.py status

Do **not** expect this command to report repository read ready when run inside Codespace: there the recommended route is the Actions controller outside the Codespace.

## How any authorized AI should perform a whole task (without Termux)

1. Open **main/AGENTS.md** and this runbook; identify the current scene, source files, versions, commit and owner worktree constraints. Use the GitHub connector for basic repo reads/edits; this does not require the user to paste a token.
2. For Unity map inspection/control, read **ai/codespace-jobs/Tools/World/ai_codespace_remote.py** and its exact allowlisted operations. Create exactly **one brand new** .aaris/jobs/<unique-id>.json per commit to ai/codespace-jobs, from authorized GitHub owner identity. A simple read-only example is {"id":"status-20261105-new-id","operation":"unity_virtual_gui_status","args":[]}. Never reuse IDs.
3. GitHub Actions workflow .github/workflows/ai-codespace-on-demand.yml uses the AARIS_CODESPACE_TOKEN secret to start/reconnect the *same* Codespace and deliver the bounded command through SSH. It receives the GITHUB_TOKEN separately for reading reviewed main source. **For any newest-main source sync, first read GitHub main HEAD and include the exact 40-character SHA in the job's args:** {"id":"sync-main-new-unique-id","operation":"unity_main_core_sync","args":["<actual-main-40-hex-commit>"]}. The executor validates that the fetched main HEAD equals this supplied SHA; it never silently fetches a different revision or overwrites a conflicting native prefab. Validate Actions AARIS_RESULT_JSON id, ok, exit_code and any actual Unity readback before reporting completion.
4. Perform mutations only in an isolated, verified project with guarded native Unity/Python entrypoints. Save in Unity Editor; verify exact .asset/.unity/.prefab/.mat readback and GUIDs. Do not force-pull, git clean/reset, or copy scratch edits over the owner's dirty /workspaces/Unity-Game-Aris.
5. For **durable** native Unity Git LFS saves, follow Docs/UNITY_BATCHED_AUTOSYNC.md: explicit unity_sync_save_session job committed with message starting Unity Batch Save:, or scheduled uploader when eligible. Only the privileged .github/workflows/unity-batched-github-upload.yml, with scoped contents:write, may perform verified Git LFS push. Confirm remote commit and acknowledgement; no "saved" claim based solely on queued job or scratch save.
6. Use a review PR and CI/Unity QA before merge. Never grant general remote shell or unconstrained repository pushes to an AI prompt; add narrowly scoped new operations with tests when a capability is missing.

## One-time owner settings (only if future authentication actually fails)

- GitHub Settings → your repository → Settings → Secrets and variables → Actions: confirm **AARIS_CODESPACE_TOKEN** exists. Do not disclose its value or recreate it if existing Codespace jobs work. If missing/expired, make a dedicated, limited, expiring owner token with the required Codespaces permissions and use GitHub's secret UI or an authenticated local GitHub CLI to put it under that name. Codespaces SSH may have additional account requirements; validate via one read-only queued job.
- The **GITHUB_TOKEN is built in**. Do not manually generate or paste a separate token for routine private main reads. Ensure the on-demand workflow has permissions: contents:read, and the LFS writer has contents:write separately. Repository Settings → Actions → General may also restrict Actions PR creation, even when the token can push a branch.
- If a third-party AI needs unattended independent GitHub access beyond its existing connector, install a **GitHub App only on this repository** with the minimum required permissions (Contents: read/write as necessary, Pull requests: write if PR creation is needed, Actions: read only if run logs needed). Store its private key in GitHub Actions Secrets, not the game repo. Use short-lived installation tokens minted per job. Do not use a permanent "all scopes" PAT to grant "anything anywhere" access.
- No AI agent can obtain someone else's GitHub credential merely by reading instructions. A user must authorize each new integration; if it isn't connected, it cannot operate this private repo.

## Failure handling

- **GitHub repo read fails**: check job's GITHUB_TOKEN presence, contents:read, GITHUB_REPOSITORY, Actions checkout and pinned ref; do not ask user to send a PAT in chat.
- **Codespace cannot start/SSH**: check AARIS_CODESPACE_TOKEN permissions, account quota, Codespace lifecycle and SSHD. Do not retry destructive Commands or leak token.
- **Git LFS push fails**: use the verified uploader workflow and investigate permissions / protected refs / LFS budget. Keep scratch source and pending journal, report UNSAVED until remote receipt exists.
- **Original scene, prefabs or settings differ from main**: preserve those files; use semantic diff, owner checks and explicit PR. A verified shader material does not imply full scene sync.
- **Another AI is unauthorized**: connect its own GitHub integration or install an appropriate GitHub App. Do not distribute a shared account credential.

**References:** Docs/AI_CODESPACE_ON_DEMAND.md (older operational examples), Docs/UNITY_BATCHED_AUTOSYNC.md, .github/workflows/ai-codespace-on-demand.yml (job queue), .github/workflows/unity-batched-github-upload.yml (privileged LFS), Tools/World/ai_master_github_auth.py (ephemeral read transport).

Official security guidance: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github and https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
