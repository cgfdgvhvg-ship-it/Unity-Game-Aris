# Aaris humanoid character upgrade (2026-11-07)

## Source and status

The saved 2 km Unity scene and original `Assets/AarisWorld/Player/AarisPlayer.prefab` are intentionally unchanged.
The old player uses primitive-body renderers with manual sine-wave arm/leg motions.
`AarisCharacterVisual` automatically attaches to the existing `AarisThirdPersonPlayer` at runtime, prefers a rigged **Primary/Player.fbx**, and falls back to a verified, free **Kenney Animated Characters Retro** source when imported. If no compatible Humanoid model exists, the saved player remains visible and controllable. The package bytes are **not yet checked in** by this PR: installation must run before a genuine visual upgrade can be asserted.

High-detail recommended source: Quaternius **Universal Base Characters** (CC0), free Standard kit, FBX or glTF; approx. 13k triangles per base. Pair with Quaternius Universal Animation Library (CC0) for detailed locomotion/combat. Some Standard downloads use itch.io's interactive download page, so there is no invented automated URL. Add a selected Unity-compatible Humanoid FBX as `Assets/Resources/AarisCharacters/Primary/Player.fbx`, along with its legally acquired textures. Unity must import it once (GUI or batchmode). The existing adapter will use it automatically, including any Kenney fallback animation FBXs that are installed and compatible with its humanoid avatar.

Links:
- https://quaternius.com/packs/universalbasecharacters.html
- https://quaternius.com/packs/universalanimationlibrary.html
- https://kenney.nl/assets/animated-characters-retro
- https://kenney.nl/knowledge-base/game-assets-3d/importing-characters-and-animations

## One-command verified starter asset acquisition (no Unity license needed)

```bash
python3 Tools/Character/install_kenney.py --selftest
python3 Tools/Character/install_kenney.py
```

The installer uses Kenney's public 2022 Animated Characters Retro ZIP, checks its reviewed
SHA-256, rejects ZIP path traversal/oversized assets, selects `characterMedium.fbx`
plus `idle.fbx`, `run.fbx`, `jump.fbx` and PNG skins, and writes only
`Assets/Resources/AarisCharacters/Kenney/`. Archive revisions fail closed unless a
human has reviewed the changed pack and explicitly passes `--allow-updated-source`.
Alternatively use `--archive /path/to/official.zip`.

The source pack is **CC0-1.0**, including commercial reuse, but Kenney's art is a
stylized low-poly starter, NOT BGMI/Free Fire photorealism. Quaternius is the
preferred more detailed visual replacement. Do not substitute unlicensed
commercial-game character rips.

## Unity import (automatic; no drag-and-drop)

`Assets/AarisWorld/Editor/AarisHumanoidImport.cs` marks the acquired Kenney
model as Humanoid, sets imported animation FBXs to use its avatar when
available and enables locomotion looping. If Unity imports the animation
before `characterMedium.fbx`, reimport animation files after the main model
has imported; inspect avatar validation in Unity logs.

`AarisCharacterVisual.cs` uses the imported model as **presentation only**.
The original `CharacterController`, input, slope limits, Camera collision,
safe spawn and terrain traversal stay unchanged. On successful model import
it hides old primitive-body mesh renderers without deleting scene objects,
and blends Idle/Run/Jump using the **Playables API**. The imported clip is
in-place; root motion is disabled to avoid fighting the saved controller.
On missing assets or invalid avatars it visibly falls back to the existing
player instead of spawning an invisible character.

The primary FBX must be imported with a *valid Humanoid Avatar*, correct
forward orientation, and compatible textures; models cannot be made to
animate correctly merely by renaming them. For Quaternius animations,
retarget the licensed humanoid clips in Unity's importer; the adapter can
be extended with an animation-source configuration after inspecting the
actual asset file names.

## Review gates before merge

1. `python3 Tools/Character/install_kenney.py --selftest` passes.
2. Source asset ZIP hash, FBX filenames, the CC0 license, Unity-generated .meta
   files and Git/LFS hydration are reviewed. Commit the binary FBXs and PNGs,
   not only the installer.
3. Import under Unity 6000.3.26f1; check compiler errors, humanoid Avatar
   validity, actual animation clip names, and Unity console logs.
4. Verify original 1.78 m player controller, multi-touch joystick, camera,
   terrain slopes, steps, jumping, collision and no duplicate player.
5. Capture actual third-person and side-view Unity screenshots of idle,
   run and jump before claiming the new character visually works.
6. Profile mobile GPU/CPU cost and skinned mesh memory before shipping.

No Unity license bypass, background render, screenshot or passed runtime build
is claimed by these source-only changes.
