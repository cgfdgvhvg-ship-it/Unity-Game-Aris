# Aaris AI Codespaces control (mobile-first)

Canonical repo: `sundamunda289-art/Unity-Game-Aris`. This system is separate from the existing GitHub Actions Unity desktop and MAP protocol. Reference scripts: `.github/workflows/aaris-codespaces-control.yml`, `Tools/Codespaces/controller.sh`, `Tools/Codespaces/remote.sh`, `.devcontainer/`.

## One-time Termux login / change Codespace account

Open Termux and run this lightweight setup. No giant Unity Git LFS clone is needed on your phone:

```bash
pkg install -y gh curl jq
curl -fsSL https://raw.githubusercontent.com/sundamunda289-art/Unity-Game-Aris/main/Tools/Codespaces/termux_switch.sh -o "$HOME/aaris-switch.sh"
bash "$HOME/aaris-switch.sh"
```

This downloads only the reviewed switch script. It performs official GitHub device/browser login for the main repo owner (once) and the Codespace account, saves them in isolated private local CLI profiles, and rotates only the `CODESPACE_PAT` GitHub Actions Secret. Do not paste tokens, passwords, ULFs or OAuth links into public issues.

Repeat the same Termux script to change the account used for Codespaces. The account must be permitted to use Codespaces on this repo under GitHub's billing/quota policies. The repository does not need to be transferred.

## ChatGPT commands via GitHub connector

As repo owner `sundamunda289-art`, post exactly one of these strings to [GitHub Issue #77](https://github.com/sundamunda289-art/Unity-Game-Aris/issues/77):

```text
CS MACHINES
CS INFO
CS START
CS STATUS
CS SYNC
CS LFS
CS LFS REPORT
CS CHANGES
CS INSTALL
CS EDITOR
CS LICENSE
CS SHOT
CS TEST
CS STOP
```

- `CS MACHINES` reads available machine IDs, CPU cores and RAM. `CS INFO` reports the existing Codespace's actual machine name, state and configured idle timeout without using SSH. Choose machine first.
- `CS START` creates/starts the selected account's Codespace. If no machine was selected in the workflow form, it picks an available machine with at least 4 CPUs and 16 GiB RAM. A specific machine can be specified in Actions > Run workflow.
- `CS STATUS` reports CPU, memory, free storage, Editor process and screen status from the Codespace terminal.
- `CS SYNC` updates to main and downloads Git LFS assets; refuses dirty worktrees and non-fast-forward overwrites. `CS LFS` attempts to hydrate large assets using the large /tmp disk and reports safe error categories. `CS CHANGES` lists tracked modified project filenames read-only when sync is blocked, without reading their contents.
- `CS INSTALL` installs official Unity Hub and Unity Editor 6000.3.26f1 only once per Codespace. It can use significant disk/bandwidth.
- `CS EDITOR` starts Xvfb :99 and attempts to launch the Editor. It does not prove Unity license activation.
- `CS LICENSE` reports preliminary installation state; official Unity Hub entitlement must be checked in the destination Codespace.
- `CS SHOT` captures a PNG only when an Editor process and nonblank display are detected. Inspect the actual pixels before claiming the scene rendered.
- `CS TEST` runs approved project tests; `CS STOP` stops the Codespace.

## Returning results to ChatGPT

The workflow responds under the issuing comment with a bounded, credential-safe status and a link to its GitHub Actions run. That run uploads a unique `aaris-codespace-RUN_ID` artifact (2-day retention) containing `result.json`, `terminal.txt`, and an optional `screen.png`. Thus, results do not collide across commands or bloat Git history. GitHub connector access may allow the assistant to retrieve the artifact. If it cannot decode the ZIP image directly, download and attach the image to the conversation. Screenshots are not published to a public Release, because sign-in dialogs can include private data.

## Workspace and licensing

`/workspaces/Unity-Game-Aris` holds the project; `/tmp/aaris-unity-runtime/editors` holds the Editor installation; `/tmp/aaris-codespaces` holds transient logs and screenshots. An existing Codespace preserves files while stopped but processes terminate; the next task restarts the display and Editor as needed. A new Codespace repeats scripted setup, not manual software provisioning. Unity Editor and Library cache use the large ephemeral /tmp volume, so installation/import may need to run again after Codespace restart if the temporary disk is cleared.

**Unity Personal:** legitimate activation requires Unity Hub sign-in; the same Codespace may retain authorized state across stop/start, but another account's new Codespace can require another approval. Do not clone hardware IDs, GitHub-publish license files or transfer login cookies between devices. Licensing and successful scene render are separate verification steps.

## Security and testing

The workflow processes issue commands **only** from the exact owner account on Issue #77. The remote bridge accepts an allowlist of task identifiers, not arbitrary shell or `eval`. Static tests execute on pushes/PRs without Codespace credentials. Live machine creation, Unity installation and licensing cannot be claimed tested until a real authenticated Codespace session runs.

Relevant official guidance: [GitHub CLI](https://cli.github.com/manual/gh_codespace), [Codespaces lifecycle](https://docs.github.com/en/codespaces/about-codespaces/understanding-the-codespace-lifecycle), [Unity Hub Linux](https://docs.unity.com/en-us/hub/install-hub-linux), [Unity Personal licenses](https://docs.unity.com/en-us/hub/manage-license).


### 2026-11-07 CLI + LFS diagnostics
`CS INSTALL` uses the current, official Unity CLI instead of deprecated Unity Hub headless CLI. The installer and Editor live in the larger temporary filesystem; installer logs remain private in the Codespace. `CS LFS REPORT` enumerates hydrated/pointer counts and classifies the last LFS failure without exposing credentials. A missing remote LFS object must be recovered from authentic matching bytes, never fabricated or replaced by a placeholder. Check Unity license and native scene separately after installation.

### Fast restart (persistent install)
After the one-time Editor installation succeeds on the current Codespace, \`CS START\` and \`CS EDITOR\` reuse \`~/.local/share/aaris-unity-editors/6000.3.26f1\`; no Editor re-download on normal stop/start. On first install, portable Unity CLI \`--download-directory\` and \`--resume\` use persistent storage. Leave Unity Library/import cache on /tmp because persistent free storage is limited. For a different account's new Codespace, software is reinstalled automatically; enable GitHub Codespaces prebuilds in repository settings if the account quota/plan permits (prebuild storage consumes quota).

### One-time phone Unity Personal sign-in

Post `CS AUTH` as the owner to Issue #77 after setting CODESPACE_PAT. GitHub Actions holds a PRIVATE SSH stream to the Codespace while `unity auth login` runs. Its actual unity.com browser URL is intercepted by `auth_bridge.py` and sent ONLY to a Cloudflare Workers KV namespace `aaris-unity-approval-private`, key `run-<GITHUB_RUN_ID>`. No URL, token or account email is written into public GitHub Issues, workflow logs or artifacts. Signed GitHub OIDC pins owner ID, repository ID, branch, and specific approved workflow; Cloudflare KV entry expires after 480 seconds. ChatGPT retrieves the URL using connected Cloudflare and sends it in this private chat.

User opens official Unity link on phone, signs into Unity account via Google/Gmail if configured, and taps Allow. Then the Codespace executes `unity auth status`, `unity license activate --personal --accept-eula`, and `unity license status`. A successful browser page alone is NOT proof of a license. If Unity Personal requires Unity Hub, report that status instead of claiming activation. Same Codespace may preserve authorized login, but new machines may require re-approval. Never copy login tokens/license files into GitHub.

### Private OAuth relay troubleshooting
`CS PROBE` verifies the exact GitHub Actions OIDC claim comparisons and Cloudflare Worker `/probe` without starting Unity or exposing secrets. It outputs only booleans and HTTP status codes, never a token. Run it before asking for phone authorization if `CS AUTH` reports `UNITY_PRIVATE_APPROVAL_RELAY_FAILED`.


### Direct phone-only Unity Allow, no Cloudflare

The simpler recommended method uses Tools/Codespaces/termux_unity_allow.sh on the owner's Android Termux. Download the script from the repository main branch using curl, then run it with bash. It reuses the existing authenticated Codespace GitHub CLI profile under ~/.config/aaris-ai/codespace-gh. It selects the existing Codespace and streams the reviewed mobile_license.py over SSH. The phone immediately opens the genuine session-specific Unity login link with termux-open-url (and prints a fallback link privately on the phone). Sign in through the official Unity-owned page using the associated Google/Gmail account and tap Allow. Keep the Termux session alive. The Codespace then attempts the official Unity Personal activation and verifies the license; Hub fallback may be required. No Cloudflare, email PIN, ULF file, or GitHub public OAuth logs are involved. A generic static Unity login URL cannot authorize a specific remote CLI session. The old CS AUTH Cloudflare method remains optional, not required for this phone method.


### Secure fallback if workers.dev is blocked
If a provider network policy blocks the private Cloudflare Workers relay even at `/health`, `CS AUTH` uses **RSA-3072 OAEP-SHA256** encryption locally on GitHub Actions and posts only ciphertext to the owner control Issue #77, prefixed `AARIS_UNITY_ENCRYPTED_APPROVAL_V1`. The genuine Unity URL and credentials are never posted publicly. ChatGPT must decrypt with the matching private key held separately from GitHub, verify the SHA-256 digest and unity.com domain, and deliver the short-lived URL ONLY in private chat. The current public key is session-specific; future turns must rotate keys if the corresponding private key is unavailable. Never post the decryption key or an unencrypted approval URL in the Issue. If no matching private key is available, do not claim the URL can be recovered. The corresponding private key is not stored in the repo or on Codespaces.

On a Codespace where the Unity CLI binary is missing, `CS AUTH` installs the official CLI first (no large Unity Editor download required), then performs browser sign-in. Unity CLI Linux installs are normally in `~/.local/bin/unity`; `UNITY_CLI_HOME` is used to persist CLI authentication state separately. Genuine Unity license status still must be verified after user approval.

Unity CLI and the re-usable Editor now use the Codespace user's writable home directory, because the /workspaces root can reject writes. The original Unity project stays under /workspaces/Unity-Game-Aris. /tmp is only for transient caches and downloads.

If Codespaces SSH has a misleading `$HOME` environment variable, mobile Unity authentication chooses the passwd database home of the effective SSH user and checks write permissions before storing OAuth session data. Only if every persistent candidate rejects writes does it use an owner-only `/tmp/aaris-unity-home-<uid>` directory; in that case the authentication session may not survive stop/restart. The public issue receives only `UNITY_STATE_HOME_PERSISTENT` or `UNITY_STATE_HOME_TEMPORARY`, never absolute paths or session credentials.

When Unity CLI installer returns UNSUPPORTED_GLIBC, run `CS STATUS` to report the *actual* Codespace OS ID, OS version, glibc version, and Docker readiness. The current devcontainer definition requests Ubuntu 22.04 (glibc >=2.34), but an existing Codespace can still run its older image until explicitly rebuilt. Do not upgrade glibc in-place, impersonate hardware or overwrite map/LFS assets. Preserve source changes before an owner-approved Codespace rebuild.

### Ubuntu repair for inherited Alpine Codespace
Owner-only `CS REBUILD` verifies the existing Codespace has `/workspaces/Unity-Game-Aris/.devcontainer/devcontainer.json` requesting the official Ubuntu 22.04 base, checks that the Git working directory exists, then calls GitHub's supported `gh codespace rebuild -c` (non-full). GitHub guarantees existing `/workspaces` files and unsaved edits are preserved over this devcontainer rebuild. Data and programs outside `/workspaces` (including `/tmp`, global packages and prior home auth) are **not** preserved. Never use git clean/reset/force push as part of a rebuild. Afterward run `CS STATUS` and verify `os_id=ubuntu` and `glibc>=2.34` before Unity CLI or Editor installation. If rebuilding fails, do not delete the Codespace; inspect the rebuild log through GitHub Codespaces.

### Post-rebuild recovery diagnostics
`CS LOGS` uses the official `gh codespace logs -c` interface to inspect Codespace startup and devcontainer build outcomes without requiring SSH. The worker emits only fixed classifications (Ubuntu/Alpine image, image pull, package installation, post-create/post-start, SSH or network failures). It never uploads or prints raw logs, OAuth tokens or account data. Use `CS INFO`, `CS LOGS`, then `CS STATUS` after rebuild; do not claim the Editor is available until SSH and a genuine Editor launch both succeed.

### Fresh Ubuntu fallback when old Codespace SSH is inaccessible
Owner-only command `CS FRESH` creates a *second* Codespace with display name `aaris-ai-unity`, branch `main`, explicit `.devcontainer/devcontainer.json` (Ubuntu 22.04), machine `standardLinux32gb` (4 CPUs/16 GB), and 240-minute idle timeout. It refuses to create a duplicate with the same display name. The original Codespace and `/workspaces` are **not deleted, rebuilt, reset or overwritten**; uncommitted edits remain there, and the fresh Codespace checks out GitHub main independently. Creating a second Codespace consumes Codespaces compute and storage quota; stop the unused old Codespace manually after verifying that the new one is functional. `CS START`/`CS STATUS` will select the new `aaris-ai-unity` Codespace when present. LFS hydration must be verified again on the new clone.

### SSH reliability after Ubuntu Codespace recreation
The custom Ubuntu 22.04 devcontainer explicitly includes GitHub's documented `ghcr.io/devcontainers/features/sshd:1` Feature. GitHub CLI `gh codespace ssh` requires a running SSH server in custom images; installing `openssh-server` without starting it is not sufficient. This feature applies when creating a new Codespace or rebuilding a container with the updated devcontainer configuration. Do not remove or reset existing map and LFS worktrees to apply it.

### Select fresh SSH-ready Ubuntu Codespace
After the official `ghcr.io/devcontainers/features/sshd:1` configuration is merged, the repository owner can post `CS FRESH SSH` to Issue #77. It creates `aaris-ai-unity-ssh` with 4 CPUs, 16GB RAM, an explicit Ubuntu 22.04 devcontainer, and 240-minute idle timeout. The existing Alpine and earlier Ubuntu Codespaces and their `/workspaces` data are preserved. Only the earlier nonfunctional fresh machine is stopped to avoid concurrent CPU use; it is never deleted. Once created, subsequent `CS STATUS`, `CS AUTH` and `CS LFS` select the SSH-ready machine. This creates additional Codespaces storage usage until old ones are manually deleted.

### Native Unity main-scene photo and Play Mode verification (without desktop screenshots)

The new owner-only Issue #77 commands are `CS SCENE RENDER` and `CS SCENE PLAY`. They invoke reviewed `Tools/Codespaces/scene_probe.sh` on the existing Codespace using the GitHub Actions controller. The GUI Editor must be closed first: request `CS CLOSE EDITOR`, check `CS EDITOR PROCESS`, and only use `CS EDITOR RECOVER` when zero visible Unity windows are detected. Then issue `CS SYNC`, `CS SCENE RENDER` and, **only if render passes**, `CS SCENE PLAY`.

Unlike `CS SHOT`, the render operation calls the actual licensed Unity 6000.3.26f1 Editor in batch mode with Xvfb/Mesa **graphics enabled**, opens the canonical native scene and four TerrainData tiles, positions a disposable orthographic map camera at (0,1600,0) and writes a true 1600x1600 `map-overview.png`. The separate Play Mode operation opens the same scene, enters Play Mode, requires 60 or more frames, checks player/camera/vehicle manager/four tiles and zero recorded runtime errors, and writes `play-frame.png`. No saved scene or Git LFS asset is edited by either operation.

Download actual PNG plus `render-report.json` / `play-report.json` from the respective `aaris-codespace-RUN_ID` Actions artifact. Do not interpret a green workflow, a nonblank Linux desktop, a zero-error static scan, or a license status without a native-render report as proof that the map works. The Unity batch Editor must have authorized licensing; the command reports failure instead of bypassing activation or producing simulated images. Raw Editor logs stay private in the Codespace. If an Editor is already running, the probe refuses the project lock rather than launching a second instance.


### Take photos at any map coordinate

Issue #77 owner command: `CS PHOTO X Z` or `CS PHOTO X Z YAW PITCH DISTANCE`.
For example, `CS PHOTO -420 -210` (automatic elevation and useful viewing angle) or `CS PHOTO 350 220 90 35 85`. X and Z are 2km world metres, yaw is direction in degrees, pitch is angle above horizontal, distance in metres; coordinates must fall inside the saved [-1000,+1000] bounds.

The command uses native Unity Editor `EditorSceneManager.OpenScene` and a transient URP camera. It finds the real TerrainData elevation, raises the camera over terrain along the line of sight, and saves `photo-detail.png` plus a wider `photo-context.png` alongside `photo-report.json` in the same owner GitHub Actions artifact. No noVNC input, Linux desktop capture or synthetic image is involved. Use another `CS PHOTO` with a different yaw or distance to inspect the object from the other side. Only the owner can issue the command; `photo_request.py` rejects invalid coordinates, NaN, shell injection and unauthorized parameter shapes.

For a fresh or hung Codespace editor, first use `CS EDITOR PROCESS`, the protected graceful shutdown/recovery process, and `CS SYNC` before `CS PHOTO`. A photo does not validate vehicle collision or gameplay; `CS SCENE PLAY` is a separate smoke test. Do not claim this setup is verified until a real Unity camera PNG has been inspected and the JSON report marks passed.
