# Full Unity Editor in a lean Codespace image + safe Git LFS synchronization

## Status: optional, NOT deployed

The new optional configuration is at .devcontainer/aaris-unity-image/devcontainer.json
with its Dockerfile. This is a build recipe, **not an installed or tested image**.
It has NOT rebuilt or modified the existing dirty Codespace
musical-carnival-jjxp9r6vw45wfjgvg or resumed Unity PID 40121.

The recipe installs the entire official Linux Unity **6000.3.26f1** Editor
during image construction, not after the Codespace starts, so its files
can be part of the base-image layer instead of the live writable layer.
It keeps the exact Unity Engine/Shader/PackageManager components. It does
NOT downgrade or alter URP 17.3.0, VFX Graph 17.3.0, original Terrain,
Assets, .mat, .prefab, .unity or .meta. A slim developer image reduces
unrelated language toolchains, not game graphical quality.

The Editor installer is the official Unity Linux release:
https://unity.com/releases/editor/whats-new/6000.3.26f1
Changeset de8167e7440c. It does not include additional Android
Build Support, SDK, NDK or JDK modules; these should be packaged in
the image too before attempting APK builds. Do not bake a Unity account,
license, GitHub secret or the project into the Docker image.

A Docker image can require substantial image-building space; a smaller
base does not guarantee that the existing 32-GiB persistent disk grows.
Test this recipe only on a separate Codespace first. Validate full Editor
startup, C# compilation, actual terrain scene, UI/C# bridge, screenshot,
disk accounting and Android module needs BEFORE any move of the original
worktree. Changing the container image can discard the old Unity Editor
and credentials installed outside /workspaces; preserve dirty files first.

## Read-only first: targeted Git LFS helper

AI entry point:

    python3 Tools/World/unity_lfs_preflight.py

The command prints machine-readable JSON showing the pinned Unity version,
whether the Editor binary exists, all three core file paths, LFS files
present/missing/as pointers, modified files protected from overwrite,
and available persistent disk. It does not launch Unity or download anything.
Existing hydrated LFS source files are never fetched again.

Explicitly gated repair on a future machine with sufficient free storage:

    python3 Tools/World/unity_lfs_preflight.py --hydrate-missing

Only at least 8 GiB persistent free space, maximum 12 missing clean
files, maximum 512 MiB combined source size, exact matching HEAD LFS
pointer hashes, and enough remaining headroom permits a fetch. It
requests only these missing paths and checks their SHA-256 on checkout.
It will NOT run on the current 0.585-GiB-free environment. This
preflight checks presence, not the complete SHA-256 of already-present
assets; refer to Docs/LFS_INTEGRITY_20261104.md for the previous
764/764 full hash audit.

Git LFS belongs to GAME DATA, not the multi-GiB Unity Editor program.
Never put Editor binaries into the game's LFS history as a supposed cache.
Do not run git reset, git clean, full git lfs pull, LFS prune --force,
or delete Unity Library.

## Restart-safe AI workflow

1. Keep the original project in /workspaces/Unity-Game-Aris and preserve
   intentionally changed and untracked core files.
2. In the future, explicitly select the optional new devcontainer
   configuration ONLY for a separate Codespace/backup-verified migration.
3. Check editor executable, source version and headroom using preflight.
4. Reuse existing hydrated LFS; if missing and safe, explicitly hydrate
   only the missing clean assets.
5. Start the Editor only with the persistent disk guard and appropriate
   licensing. Load exact original TerrainDemoScene; verify Unity APIs can
   inspect, edit, save and read back an object, and capture a real image.
6. Keep source, metadata and Library persistent. Never symlink the main
   Editor into volatile /tmp or the measured 64-MiB /dev/shm.
