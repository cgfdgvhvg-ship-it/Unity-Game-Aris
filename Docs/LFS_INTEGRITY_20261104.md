# Unity map: complete Git LFS integrity check — 2026-11-04

## Verified result

- Codespace project: `/workspaces/Unity-Game-Aris`.
- **All 764 LFS assets present, hydrated and byte-for-byte SHA-256 verified** against their Git LFS OIDs on the checked-out map-core branch.
- Checked-out Git HEAD was identical on all 11 batches: `8225f4346df94ca5e2a2edb671976a49866d04bf`.
- **764 / 764 SHA-256 matches; 0 mismatches; 0 missing; 0 LFS pointers; 0 unreadable; 0 oversized/deferred; 0 file-changed-during-hash.**
- Verified file bytes: **3,932,660,996 decimal bytes (3.933 GB, 3.663 GiB)**. Matches the earlier local LFS inventory byte count.
- No Git LFS fetch/pull or checkout required for these files. Avoid redundant multi-GB downloads onto the small Codespace disk.
- Git LFS file extensions at this checkout: `.asset`, `.png`, `.tif`, `.fbx`, `.exr`, `.tiff`, etc. Do not infer from extensions that ordinary-Git `.mat`, `.prefab`, or `.unity` files are Git LFS pointers.
- The known **15 modified tracked and 3 untracked files remain intentional saved core-authoring work**; they are **not** approved for deletion, reset or overwrite. They are separate from the 764 exact LFS hashes. Their Unity re-import behavior has *not* yet been independently verified in the graphical Editor.

## Evidence (11 full SHA-256 verification jobs)

Every job returned `ok:true`, `exit_code:0`, the same `head_sha` above, and the exact next cursor.

| File cursor [start, end) | Matches | Bytes hashed | Actions run |
|---|---:|---:|---|
| 0–145 | 145 | 464,965,786 | [41837307762](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41837307762) |
| 145–290 | 145 | 75,841,265 | [41837430791](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41837430791) |
| 290–435 | 145 | 17,937,588 | [41837571970](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41837571970) |
| 435–515 | 80 | 498,124,150 | [41837708584](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41837708584) |
| 515–610 | 95 | 471,749,031 | [41837854990](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41837854990) |
| 610–651 | 41 | 501,268,305 | [41837995298](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41837995298) |
| 651–689 | 38 | 503,149,784 | [41838155284](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41838155284) |
| 689–719 | 30 | 390,151,689 | [41838305877](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41838305877) |
| 719–730 | 11 | 480,046,629 | [41838425894](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41838425894) |
| 730–750 | 20 | 503,123,843 | [41838557434](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41838557434) |
| 750–764 | 14 | 26,302,926 | [41838676033](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41838676033) |
| **Total** | **764** | **3,932,660,996** | **all succeeded** |

## Disk cleanup carried out before verification

- Removed only re-downloadable Copilot package and npm cache directories.
- Real disk recovered: **235.7 MiB**. Free disk improved **3.392 GiB → 3.623 GiB** at that verified point.
- Original [cache cleanup run](https://github.com/Aaris-khan-don/Unity-Game-Aris/actions/runs/41834537871) reported `git_worktree_unchanged:true`.
- Preserved the already-installed Unity Editor 6000.3.26f1 (8.2 GiB installed), saved map assets and all dirty source files. No Unity project `Library` had been imported at the time of storage inventory.

## What this check does *not* prove

- Intentional modified foliage/mesh/LOD asset files need separate saved-asset/Unity Editor validation. An LFS hash mismatch against a modified file is not inherently an error; **never revert core edits to force a match**.
- Exact equality of clean LFS files does not prove scene physics, visual quality, build parity, materials or gameplay performance.
- A large Unity project import may exceed the remaining ~3.6 GiB disk. Verify real free space first; do not re-download the complete LFS dataset into `.git/lfs/objects` without a sufficient disk budget.

## AI protocol for future audits

Read `AGENTS.md` and `Docs/AI_CODESPACE_ON_DEMAND.md`. Use the owner-authorized GitHub Actions `lfs_verify_chunk` job on `ai/codespace-jobs` starting with numeric cursor `0`. Follow `next_cursor` until `all_done:true`, verify identical `head_sha` and sum categories. **Do not post jobs to legacy Issue #37**. No per-file download was needed at the time of this report.
