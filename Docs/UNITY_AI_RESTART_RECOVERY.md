# Unity Codespace restart recovery — durable state without noVNC

## What is and is not persistent

The original project is **/workspaces/Unity-Game-Aris** and its Git LFS
source has been independently verified 764/764 present. GitHub Codespaces
officially retains /workspaces when stopped and restarted. Running Unity
processes and the separate /tmp scratch project are NOT retained. GitHub
explicitly states that /tmp is cleared on **Codespace stop**, even though
it is sometimes retained across a container rebuild.

Sources:
- https://docs.github.com/en/codespaces/developing-in-a-codespace/persisting-environment-variables-and-temporary-files
- https://docs.github.com/en/codespaces/about-codespaces/understanding-the-codespace-lifecycle

A smaller JSON checkpoint alone CANNOT preserve 10+ GiB of imported
Unity Library; we do not claim an instant exact resume. Unity rebuilds
its generated Library cache from the existing Assets/Packages/ProjectSettings
if the scratch was lost. Never delete or overwrite the ORIGINAL Library.

## Small persistent checkpoint (saves key state only)

New AI entrypoint:
`python3 Tools/World/unity_session_checkpoint.py` (read-only JSON)
`python3 Tools/World/unity_session_checkpoint.py --checkpoint` (writes
ONE small atomic JSON file, after confirming scratch scene exists).

Persistent destination:
`/workspaces/.aaris-world-bridge/ondemand/unity-session-checkpoint.json`

Contains exact scene name, Unity version, source hashes for
ProjectVersion, Packages manifest, Scene and Scene .meta; timestamp,
whether scratch Scene was loaded, and warning if TerrainData scratch
bytes differ from protected original. It never stores Unity tokens,
account information, untracked files, screenshots, full Library, or
binary Unity assets. All source checking is read-only.

## Recovery decision table

| Situation on next AI job | Safe automated response |
| --- | --- |
| Existing Unity process is running on identical scratch project | Reuse process; do not launch duplicate |
| Unity stopped but compatible scratch Library remains | Launch normal Unity Editor on private Xvfb :12 and reuse existing import |
| Scratch /tmp cleared on Codespace stop | Recreate copy from ORIGINAL unchanged Assets/Packages/ProjectSettings on /tmp; full Unity import required |
| Original core changed since scratch was imported | Refuse stale scratch reuse; report conflict for safe review |
| Unity executable missing, original disk <250 MiB, scratch disk <20 GiB | Refuse launch; report exact blocker |
| Old scratch has pending/unpromoted edits | Do NOT replay mutating actions automatically or overwrite owner source |
| Dedicated Codespace branch job starts stopped Codespace | Existing GitHub Actions owner queue wakes Codespace by its exact name and runs recovery over SSH |

The planned `unity_session_recover` job runs this decision
tree. It does NOT depend on noVNC or a phone screen. It must not
automatically activate a Unity license, accept terms, commit/push core
assets, reset Git, copy scratch TerrainData back, or revive a dead PID.

This recovery runs when an **authorized AI job is sent**. Simply opening
a Codespace web tab does not itself guarantee an AI job is scheduled:
automatic on-start hooks would require a separately tested devcontainer
change/rebuild and may risk the existing 36 dirty/untracked paths.

## Last verified real session

The real GUI Unity Editor 6000.3.26f1 opened
`Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity` on private
Xvfb and read 4 Terrain components, 7,508 tree instances, 84 Prefabs,
256 Materials. It saved and independently read back a reversible tree
move and scale, then generated a real camera JPEG. A byte-level
comparison found scratch TerrainData serialized differently even
after undo, while its .meta and main Scene matched. Hence no
unsupervised scratch-to-original promotion.

See `Docs/UNITY_AI_NO_VNC_VERIFIED_20261105.md` and
`Docs/CODESPACE_OVERLAY_RECOVERY.md` for exact run IDs.

## Future improvement required for true instant resume

Obtain more persistent capacity or an authenticated external Unity
Library cache built/verified from an immutable source fingerprint.
Restore the cache with checksum/compatibility checks into a stable
persistent project location before launching Editor. Do NOT use Git
LFS as a cache for generated `Library`; keep LFS for versioned
game assets. Until that service is available, /tmp recovery requires
a fresh import and cannot promise last process memory/UI state.
