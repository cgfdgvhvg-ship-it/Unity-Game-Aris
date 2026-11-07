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
