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
