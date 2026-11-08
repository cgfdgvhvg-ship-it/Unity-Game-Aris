# Codespaces fast start: reproducible Unity 6000.3 Editor + LFS

Repository: `sundamunda289-art/Unity-Game-Aris`, branch `main`.
Unity Editor: **6000.3.26f1** (changeset `de8167e7440c`).
All operations preserve the native Unity scene, Git LFS assets, and pre-existing changes. Do not run `git clean`, `git reset --hard`, or overwrite a Unity licence to recover a Codespace.

## How the stored fast-start logic works

The checked-in `.devcontainer/devcontainer.json` configures:

1. `onCreateCommand: bash .devcontainer/prebuild.sh`: installs Ubuntu packages, `git-lfs`, the official SSH server feature, tries an LFS pull, and runs the verified Unity CLI **fresh** installer (using explicit EULA/yes, no blind `--resume`). The Editor is stored in the Codespace user's persistent `~/.local/share/aaris-unity-editors/6000.3.26f1` directory. The command is idempotent.
2. `postCreateCommand: bash .devcontainer/finalize.sh`: starts the virtual display, checks all LFS-tracked paths for missing files or unexpanded pointers, downloads only if required, and checks the Editor binary. A prebuilt machine should reuse the already installed assets.
3. `postStartCommand: bash .devcontainer/start_screen.sh`: starts Xvfb/Fluxbox when the Codespace resumes. This does **not** automatically activate a Unity licence or prove the actual Editor is rendering.

`Tools/Codespaces/verify_lfs.py` is a read-only count-based checker. It never prints asset file contents or private CLI authentication data. Codespaces prebuild images must NOT contain `.ulf`, Unity Hub login state, access tokens, cookies, GitHub PATs, credentials, machine IDs, or OAuth sessions. They are never created by the prebuild script.

## Enable the actual GitHub Prebuild once

1. Visit [Codespaces settings](https://github.com/sundamunda289-art/Unity-Game-Aris/settings/codespaces) as a repository admin.
2. Select **Set up prebuild**. Choose **main** and **.devcontainer/devcontainer.json**.
3. Prefer **On configuration change** or a moderate scheduled cadence to limit storage and Actions usage. Start with **one retained version** and the region you actually use, subject to GitHub's available controls.
4. Click **Create** and confirm the GitHub-managed prebuild finishes successfully. Before creating a new Codespace, check that the machine selection shows **Prebuild ready**.
5. Create a new Codespace using the same branch, devcontainer and a machine size that supports the prebuild (the current target is 4 CPU / 16 GB).

GitHub executes `onCreateCommand` when producing its prebuild snapshot, but **not** `postCreateCommand` at that stage. Without a configured/ready prebuild, a brand new Codespace still has to download and install Unity Editor and LFS on its own. Prebuilds use storage and Actions quotas; they are **not guaranteed free or seconds-fast**, and a full Unity project import can still require time and an authorized licence.

## Verify a Codespace, without claiming false success

Owner-authorized commands can be posted on [Issue #77](https://github.com/sundamunda289-art/Unity-Game-Aris/issues/77) through ChatGPT's connected GitHub account:

```text
CS STATUS
CS LFS REPORT
CS LICENSE
CS DEPS
CS EDITOR
CS EDITOR DIAG
CS SHOT
CS ACCEPT TERMS
CS SAFE MODE
CS COMPILE REPORT
```

`CS STATUS` must show `editor_installed=yes`. `CS LFS REPORT` must show `lfs_unhydrated_pointer_count=0`. `CS LICENSE` searches the effective SSH user's CLI home and reports whether the **license status command** succeeds. `CS EDITOR` can only prove that an Editor process started. `CS SHOT` is only a virtual-desktop capture and needs visual inspection; it is not proof that the map is rendered. If the Editor quits after launch because its Linux shared libraries are absent, run `CS DEPS` once; it only installs a fixed set of Ubuntu 22.04 GUI/OpenGL packages and never changes the Unity map or license. This same package step is included in new prebuilds. Then retry `CS EDITOR`. If the Editor still quits, run `CS EDITOR DIAG`: it classifies local launch failures without publishing raw Editor logs. A genuine Unity-rendered scene screenshot and successful scene load are separate acceptance tests.

## Accept Unity Editor Software Terms (explicit user approval only)

The Editor can show a `Unity Editor Software Terms` checkbox dialog on first launch. With the user's **explicit approval for the terms displayed in the current session**, the authorized repo owner can post `CS ACCEPT TERMS` to Issue #77. The one-shot remote script locates exactly one visible window with that title, checks the dialog geometry, selects the agreement checkbox and presses **Accept and Continue**. A follow-up `CS SHOT` is required to inspect what opened. If the title/geometry is different, it fails closed without clicking. It never runs in a prebuild or at Codespace startup. A new version of the Terms needs fresh permission.

## One-time mobile Unity account authorization

Run the existing reviewed `Tools/Codespaces/termux_unity_allow.sh` in Android Termux. It selects the SSH-ready Codespace and opens the **session-specific official Unity login URL** privately on the phone. The user must approve via Google/Unity and may need Unity Hub for Personal activation. No static link can silently approve a new session. Do **not** put login URLs or licence files in this public repository, GitHub Actions artifacts, GitHub Issues or prebuild snapshots.

## Recovery logic

- Missing CLI/Editor: `CS INSTALL` (same idempotent installer) and then `CS STATUS`.
- Missing LFS objects: `CS LFS` followed by `CS LFS REPORT`; never force reset map assets.
- Codespace offline: `CS START`, then `CS STATUS`. Use `CS FRESH SSH` only when a new machine is needed; it consumes additional quota and leaves older workspaces intact.
- License inactive: use approved phone login on the **same Codespace** and verify again. A new machine must not inherit a different machine's license or OAuth tokens.

Official docs: https://docs.github.com/en/codespaces/prebuilding-your-codespaces/configuring-prebuilds

## Recovery when Unity reports compilation errors

When the screenshot displays **Enter Safe Mode?**, the owner may issue `CS SAFE MODE`. The one-shot command checks the exact visible dialog and clicks **Enter Safe Mode**, not Ignore or Quit. This does not delete any assets or change C# source files.

Then issue `CS COMPILE REPORT` to obtain bounded compiler errors from the current Codespace's Unity Editor log in the Actions artifact. It reports paths only under `Assets/`, `Packages/` or `Library/PackageCache/`, C# error codes, and sanitized messages. It does not publish the raw Unity log. Repair C# source in a reviewed PR, then recompile; never reset the LFS project to fix compiler errors.
