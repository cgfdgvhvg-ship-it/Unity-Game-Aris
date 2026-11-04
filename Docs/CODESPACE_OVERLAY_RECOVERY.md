# Codespace OverlayFS, RAM, and Unity Recovery — verified November 4, 2026

## Scope and current state

- Repository: `Aaris-khan-don/Unity-Game-Aris`
- Existing Codespace: `musical-carnival-jjxp9r6vw45wfjgvg`
- Project: `/workspaces/Unity-Game-Aris`
- Native Unity Editor 6000.3.26f1: `/home/codespace/Unity/Hub/Editor/6000.3.26f1/Editor/Unity`
- Open Scene intended: `Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity`
- The native Unity process was verified in **T (stopped)** state at PID 40121, with **0.585 GiB persistent free disk**. Its partial `Library` remains intact.
- All 764 LFS assets were previously hash-verified (3,932,660,996 bytes); avoid redundant Git LFS downloads. The **current** `.git/lfs/objects` is only **8.3 MiB**, not 3–5 GiB of duplicates.
- Preserve all 15 intentionally modified tracked and 3 untracked project files, including unsaved/locally created bridge assets. No forced `git clean`, `git reset`, `Library` deletion or scene regenerate.

## Measured mounts and RAM: do not mistake memory availability for tmpfs capacity

Reference: [real Codespace filesystem probe](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41870345402).

| Path/device | Verified mount | Total | Free at probe | Restart-safe? |
| --- | --- | ---: | ---: | --- |
| `/dev/shm` | tmpfs | 0.062 GiB / 64 MiB | 0.062 GiB | No |
| `/workspaces` | ext4 /dev/loop4 | 31.326 GiB | 0.585 GiB | Persistent Codespace data |
| `/home/codespace/Unity` | overlay root | 31.326 GiB reported | 0.585 GiB reported | Home/container-layer lifecycle must not be assumed persistent across rebuild |
| `/tmp` | separate ext4 /dev/sda1 | 117.556 GiB | 101.626 GiB | **No:** temporary scratch, not durable across stop/rebuild |

RAM: 15.619 GiB total, 11.441 GiB available, 0 swap, Unity process RSS approximately 1.99 GiB. Unity `PackageManager` is approximately 4.805 GiB. Therefore a 3.5–4 GiB `mv ... /dev/shm` **cannot work**, even though there is more RAM available, and a symlink to `/tmp` or `/dev/shm` would break when temporary content disappears. Do not perform either move against an active/paused Editor.

## What can actually reclaim space

**Do not confuse visible file sizes with reclaimable disk blocks.** The root filesystem is OverlayFS. Its read-only lower layers cannot be removed by ordinary `rm -rf` inside this container; deleting a lower-layer file records a whiteout in the writable layer without shrinking the lower image. A rebuild from a reviewed leaner image is required to exclude preinstalled runtimes. Treat installed software under `/opt`, `/usr`, `/usr/local` as *not approved for deletion* without an upper-layer audit and package dependency review.

Read-only system audit: [41866479417](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41866479417) and [41867472392](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41867472392):

- `/opt/conda` about 1.30 GiB, `/opt/conda/pkgs` about 694 MiB; deleting installed package stores is risky and could save **0 bytes** when sourced from lower layers.
- `/usr/local/share/nvm` about 0.52 GiB. Codespace uses an active Node.js executable; do not delete its runtime.
- `/usr/local/go` about 0.28 GiB; `/usr/share/dotnet` about 0.79 GiB; size alone does not establish safe reclaimable bytes.
- The download-archive-only cleanup audit found **zero** qualifying Conda `.conda`/`.tar.bz2` and APT `.deb` archives. [41868003328](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41868003328).
- Previously safe, measured disposable caches already reclaimed 235.7 MiB. Do not delete Unity `Data/Resources/PackageManager` (built-in shaders/render packages).

## Safe recovery sequence for another AI

1. Read `AGENTS.md` and use the reviewed, owner-only `ai/codespace-jobs` Actions queue. Send exactly **one** job at a time. On the current main branch, `layered_storage_probe` is a read-only, no-args operation. Wait for its completed Action and matching job ID before making capacity claims.
2. Verify actual free space with `df`, mount type and persistent `Library`; check current Unity PID state instead of assuming prior PID survived a Codespace stop. Never resume an interrupted Import solely because the process exists.
3. Require at least 4 GiB **persistent** free disk before `unity_resume_paused` on the verified existing process; fresh first import needs a larger budget (the guarded controller uses 8 GiB). Higher capacity is only a *guardrail*, not a promise of import completion.
4. To remove **base-image** tools, prepare and separately review a *lean devcontainer base image* that installs only required Unity Editor dependencies, Git LFS, SSH, VS Code server, Xvfb/Openbox/x11vnc/websockify, Python 3, and necessary build tooling. Do not run a rebuild automatically. First back up intentionally dirty project files, untracked files, metadata and important config to verified persistent/remote storage, and document how Unity Editor 6000.3.26f1 will be installed and licensed again. Changing the underlying image can remove home-layer Unity installation.
5. After a tested new environment and sufficient persistent capacity, restore project unchanged; reuse import cache only when backed up compatibly, compile C#, open exact TerrainDemoScene, inspect a tree, perform reversible Move/Scale via Unity and read back the saved core asset. Capture screenshot to one-day artifact (not the Git history). Do **not** claim these last steps have happened already.

## Out-of-bounds operations

- `sudo rm -rf /opt /usr/local /usr/lib` or deleting package manager directories on OverlayFS as an assumed free-space fix.
- `git lfs prune --force`, wholesale deletion of `.git/lfs/objects`, or modifying tracked LFS content.
- Relocating the live Editor `PackageManager`, `Assets`, `Library`, project metadata or Git data to a volatile filesystem by `mv` plus a symlink.
- Calling a Codespace restart/rebuild a "resume" of a stopped POSIX process. On restart, RAM/process state is gone even though the persistent project data remains.

## Big-tech-style operating principle

Run **inventory → classify ownership/layer → dependency check → reversible dry-run → explicit guardrails → only verified cleanup → measure actual `df` delta → native Unity smoke test**. Treat protected geometry, package dependencies and restart recovery as hard invariants rather than optimizing solely for recovered bytes. `layered_storage_probe` implements the read-only first part of this sequence.
