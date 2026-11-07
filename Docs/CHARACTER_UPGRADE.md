# Aaris male humanoid character upgrade — offline source of truth

## Status
The saved native 2 km Unity scene and its original player prefab remain untouched.
The existing player physics/controller/camera/mobile joystick are preserved.
The new `AarisCharacterVisual.cs` is a visual rig adapter with an eleven-input
Unity Playables mixer for **Idle / Walk / Sprint / Jump Start / Jump Loop /
Jump Land / Crouch Idle / Crouch Walk / Punch Jab / Pistol Shoot** and
falling fallback. It runs from
local `Resources` assets; there are no runtime character CDN or external URL
requests. The previous primitive body is retained as a visible fallback until
the imported humanoid passes Unity validation.

## Ownership / licensing
- Male body: **Quaternius**, Universal Base Characters free Standard pack,
  Superhero Male, CC0-1.0, https://quaternius.com/packs/universalbasecharacters.html
- Motions: **Quaternius**, Universal Animation Library free Standard pack,
  CC0-1.0, https://quaternius.com/packs/universalanimationlibrary.html
- Reviewed texture-preserving GLB redistribution:
  https://github.com/Seyamalam/blood-league-kickoff/blob/main/docs/ASSET_CREDITS.md
- Exact source commit: `aa02a4e6d8337a0604d2da131bcbbeb1f01badf0`.
  SHA-256 and git blob SHAs are hardcoded in `Tools/Character/vendor_quaternius.py`.
- Full CC0 license files and audit manifest are stored with the actual assets.
  This is a **stylized high-quality starting rig**, not an official
  PUBG/BGMI/Free Fire character or a claim of identical proprietary systems.

## Permanent local files

```text
Assets/Resources/AarisCharacters/Primary/
  Player.fbx
  Animations/{idle,walk,run,jump,crouch}.fbx
  Animations/{jump_start,jump_land,crouch_walk,punch,shoot}.fbx
  Animations/clip-sources.json        # exact source action provenance
  Textures/*.png
  LICENSE-BASE-CHARACTERS.txt
  LICENSE-ANIMATIONS.txt
  asset-source.json
  *.meta (stable GUIDs; also for directories)
```

`.fbx` and texture PNG bytes are committed through Git LFS. Re-running the game
does not require access to the original websites; an LFS pointer alone is not
a complete asset, so Git LFS hydration must be verified.

## One-time acquisition, not runtime downloads
`.github/workflows/aaris-character-vendor.yml` runs on the feature branch
without a Unity license. It installs Blender, verifies pinned CC0 GLBs, converts
the character and motion clips into Unity-readable native FBX files, generates
meta GUIDs, tracks binaries in LFS and commits actual files to the branch.

Equivalent local setup:
```sh
sudo apt-get install blender python3-numpy git-lfs
python3 Tools/Character/vendor_quaternius.py --selftest
python3 Tools/Character/vendor_quaternius.py
python3 Tools/Character/write_unity_meta.py
git lfs install
git lfs track 'Assets/Resources/AarisCharacters/Primary/*.fbx'
git lfs track 'Assets/Resources/AarisCharacters/Primary/Animations/*.fbx'
git lfs track 'Assets/Resources/AarisCharacters/Primary/Textures/*.png'
git add .gitattributes Assets/Resources
git commit -m 'Vendor CC0 male player and animations locally'
git push
```

## Gameplay integration
- The original `AarisThirdPersonPlayer.cs` controls move/sprint, buffered
  jump, slopes/terrain elevation, water exclusion, collision and camera.
- `AarisCharacterVisual.cs` automatically loads the local Player.fbx and
  assigns its valid Humanoid Avatar. The body is scaled to the authoritative
  1.78 m capsule; old primitive MeshRenderers alone are hidden, not deleted.
- Imported motion is in-place (`Animator.applyRootMotion=false`) so the
  collision controller remains the gameplay authority.
- The Playables mixer uses explicit source-correct takeoff, airborne and
  landing clips; crouch/walk variants and one-shot punch/shoot clips; it
  interpolates using real player velocity and grounded state. Takeoff,
  landing and attacks reset clip time on events, rather than playing a
  random animation from the source pack. A prone pose is still a visual
  fallback because the verified 43-animation library has no crawl/prone clip.
- `AarisCharacterImport.cs` supplies deterministic Unity Humanoid FBX imports.

## Test gates before merging
1. Offline installer passes checksum selftests and CC0 license audit.
2. Actual FBX, PNG, license, and Unity .meta files are committed and hydrate
   through Git LFS (do not merely commit an external download link).
3. In Unity 6000.3.26f1: run
   `Aaris.MapReview.Editor.AarisCharacterImport.Validate` in batchmode or the
   **Aaris > Validate Vendored Male Character** menu.
4. Open the actual terrain scene; check model, texture, humanoid retarget,
   feet on uneven terrain, walking/running/jumping, camera, obstacle collision.
5. Capture genuine Unity screenshot/video evidence and verify mobile FPS.
   A green Python/Blender GitHub Actions run alone **cannot prove** the game
   rendered or the Unity Editor was successfully licensed.

No native terrain, road, house, map scene or vehicle LFS objects are edited
by this branch until a reviewed scene change is explicitly required.

## Verified input animation source upgrade (2026-11-07)
The pinned Quaternius GLB contains **43 source motions**; a separate
SHA-256-verified audit found Jump_Start, Jump_Loop, Jump_Land,
Crouch_Fwd_Loop, Punch_Jab and Pistol_Shoot. The original first import
accidentally bound `Jump_Land` as `jump.fbx`. This was corrected by
explicit source selectors; all 10 animation FBXs plus 1 character model
are now persisted in Git LFS. The CI verifier reports **11 hydrated FBX
objects, 20 unique Unity .meta GUIDs and both CC0 licenses**.

Source audit workflow: `.github/workflows/aaris-motion-audit.yml`.
Import verification: `Aaris.MapReview.Editor.AarisCharacterImport.Validate`.
**Actual Unity Editor humanoid retarget and screenshot QA remain pending.**
