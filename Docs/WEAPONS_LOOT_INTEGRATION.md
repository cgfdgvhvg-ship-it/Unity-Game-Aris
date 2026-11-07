# Aaris 2×2km local weapon + loot architecture

## Installed binary weapon assets

Five CC0 Pichuliru East pack rigged FBXs are committed locally in
`Assets/Resources/AarisWeapons/Models/`; no live download URL is used
by the game. Download hashes and rights are documented in
`Docs/WEAPON_ASSETS_LICENSE_AND_SOURCE.md`. Models are **game-ready
flat-shaded, not yet photorealistic**; URP appearance/hand grip requires
a genuine Unity Editor visual check.

## Data-driven magazine, recoil and scope rules

These Aaris numbers are balancing defaults, NOT values copied from
Free Fire/PUBG. Change `Assets/Resources/AarisWeapons/weapon_catalog.json`
rather than creating a new combat script for each gun.

| Aaris class | RPM | Mode | Magazine | Damage | ADS FOV |
| --- | ---: | --- | ---: | ---: | ---: |
| Compact SMG | 780 | Automatic | 36 | 20 | 47° |
| Tactical AR | 660 | Automatic | 30 | 33 | 40° |
| Battle Rifle | 520 | Automatic | 25 | 42 | 38° |
| Bolt Sniper | 48 | Single-press | 5 | 112 | 14° |
| Pump Shotgun | 85 | Single-press; 8 pellets | 6 | 11 per pellet | 48° |

There are two carried gun slots. The existing Fire button keeps punching
until a gun is collected, then the single `AarisEquippedGun` class
handles a properly timed shot, magazine consumption, reloading, spread,
muzzle-to-target line of sight and limited camera recoil.

The five movement/combat buttons remain unchanged. Three compact
**weapon utility** controls appear only after pickup:
`ADS`, `SWAP` and `RELOAD`; they share the existing EventSystem.
For keyboard review: Q=swap, R=reload, right-mouse=ADS.
The player's third-person motor remains sole camera/FOV and collision owner.

## Three-tier match loot

1. **Buildings:** From the actual 59 authored map buildings, the offline
   baker chooses 156 potential room-floor coordinates from likely
   residential structures. Each match samples candidates with a 72%
   probability, but spawns only where **both physical floor and roof
   are verified**, clearance above the floor is available, and a player
   can approach the item. Unusable solid meshes are skipped rather
   than pretending they are accessible rooms.
2. **Native trees:** Four Terrain tiles currently report about 7,508
   native TreeInstances. At most 12 per tile are sampled at boot,
   with at most 72 attempts per tile and >=32m spacing between
   candidates. Actual item locations are offset 2–9m from sampled
   trunks; floor/overlap and terrain/water checks happen near player.
   Other trees receive no gun.
3. **Open world:** 358 spatially distributed, jittered 100m grid
   candidates outside the authored building AABBs. Each match samples
   at 32%, all across the 2km map. Ground, water and wall clearance
   remain mandatory; no guaranteed gun in every cell.

Match loot uses a local xorshift seed and cached candidate list, so
returning to an area does not reroll its drops. A collected pickup
stays collected. Rendered pickup objects only stream within **42m**
of the player, with **40 active maximum**, **6 newly created maximum
per refresh**, and disappear visually past 69m (but retain their
per-match plan). Surrounding native world colliders are already enabled
out to 55m by the existing `AarisNearbyColliders` system.

**No full 2km physics scan, no per-frame tree-instance copies, no terrain
or building edits, no fake gun cubes, no network asset dependency.**

## Quality and trust boundaries

- These systems are for local gameplay; online multiplayer needs a
  server-side authoritative loot seed, pickup ownership arbitration,
  hit validation, ammunition and shot reconciliation.
- Current raycast hit-scan is an abstract game mechanic, not a full
  ballistic/penetration/ricochet model.
- Accessible interiors and tree loot need true **Unity Play mode**
  checks against the actual TerrainCollider/MeshCollider geometry.
- There is no claim of actual 60 FPS or working reload/humanoid visual
  attachment before Play-mode/Android testing.
- Only source+binary integrity is verified in license-free GitHub Actions.
- The intended future Editor check is
  `Aaris.MapReview.Editor.AarisWeaponImportValidation.Run` under a
  legitimately licensed Unity Editor 6000.3.26f1.

## Rebuild/provenance verification

```sh
python Tools/Weapons/bake_loot.py
python Tools/Validation/check_weapon_loot.py
```

The 514 baked indoor/grid candidates are reproducible from the
existing `Docs/MAP_LAYOUT.json`; the optional bounded tree sampling
runs at the start of the match, not at build time.

This feature is reviewed in PR #94 and does not alter native scene,
terrain, houses or Git LFS map assets.
