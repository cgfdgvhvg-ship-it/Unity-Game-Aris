# Aaris Unity CI agent instructions

Repository: sundamunda289-art/Unity-Game-Aris; branch: main. Public repository: NEVER commit or release passwords, tokens, Unity license files, Hub state, private content or secrets.

## Canonical world
Unity 6000.3.26f1, URP 17.3.0. Native source scene: Assets/TerrainDemoScene_URP/Scenes/TerrainDemoScene.unity; 2km by 2km world on four real TerrainData tiles. See Docs/MAP_LAYOUT.json, README.md, the existing AarisExplorerBuild.cs and Tools/Validation before edits. Many assets are Git LFS tracked: a pointer is NOT a valid Unity scene. A Release checkpoint does not replace permanent Git history.

## GitHub Actions only; no Codespaces
- Primary workflow: .github/workflows/aaris-unity-photographer.yml. Main branch pushes trigger it. workflow_dispatch accepts intent=all, houses, roads, tiles or sky.
- Unity executes Aaris.MapReview.Editor.AarisCICapture.Capture. It opens the checked-in native scene and captures genuine HD PNGs. No -nographics; Xvfb plus Mesa and a real graphics device required.
- Photos and photo-audit.json are uploaded to Actions artifacts and live-photos Release. Black/white/flat images are diagnosed; no success claim for unverified visuals.
- Cache release tags: engine-cache for the compatible Library, project-checkpoint for changed project assets. Archives are SHA-256 verified and individual assets are kept under 2 GiB.
- Never publish credentials, license folders or the Git working database. Library is an expendable import cache, not a source-of-truth snapshot.
- Jobs are ephemeral and limited to 6h maximum. Periodic saves plus if: always() are best-effort; hard termination/cancellation can bypass final cleanup. Persist final project changes in Git.
- CI cannot be a permanently reachable interactive Unity Editor screen. It can automate Editor operations with intent commands; no exposed VNC server or Codespace needed.
- Reproducible cold starts depend on Docker image availability, license, LFS access, disk, cache and network; 1-2 minutes is not guaranteed.
- Do not overwrite real terrain, mesh, scene, prefab, material or .meta files just to make screenshots pass. Capture errors require investigation.
- Test Python checkpoint with: python Tools/CI/session_store.py selftest. Treat Unity activation as a separate required dependency; only use configured GitHub Secrets, never print them.
