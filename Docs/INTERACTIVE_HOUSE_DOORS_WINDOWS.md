# Aaris offline interactive doors and breakable windows

## Scope and existing source constraints
The 59 original town buildings and original exported building prefabs contain a combined nonconvex LOD0 MeshCollider, so pasting a decorative moving door on top would **not** create an opening. The original Unity scene, old meshes, materials, LFS terrain and GUIDs must not be damaged by an unverified automatic mesh cutter.

Four explicitly marked additional settlement sites (ARX_18, ARX_19, ARX_20, ARX_21) instead instantiate a small modular URP house with physical **gaps in its wall geometry**. The other 17 additive sites, five watchtowers, and all original 59 town buildings are unchanged.

## Game behaviour
* A panel at the actual doorway hinges open toward the exterior when the player comes within 2.8 m. Rotation is framerate-independent at up to 230 degrees per second.
* Automatic closing waits 1.5 seconds after the player moves away and checks for occupants, vehicle bodies and other colliders in the doorway. Static closed doors do not perform expensive overlap scans every frame.
* Each modular house has one 85-HP door and three 15-HP glass panes. Bullets and grenades use the existing `IAarisDamageable` offline pipeline. The panel's own collider is disabled only after destruction. Glass panes leave the intended window hole open. Door destruction leaves a traversable door hole.
* Max three wood or four glass decorative fragments per break, with collisions off and destruction at 1.1 s. No persistent debris objects, third-party assets, networking, downloads, or runtime-generated high-poly meshes.
* Modular house wall/roof/door trim can reuse the already imported URP source prefab's local authored material textures; fall back to shared instanced URP-Lit materials. Four houses use existing approved map coordinates and original footprint dimensions.

## Validation and limitations
`python3 Tools/Validation/test_settlement_expansion.py` audits geometry cutouts, site distribution, finite bounds, no tree/road/building overlap, collider behaviour and reuse of the existing gun damage hook. CI also checks C# syntax. **This does not replace native Unity Play Mode.**

Before declaring it released, use licensed Unity 6000.3.26f1 in an isolated PR-ref worktree to prove the four modular homes actually spawn, photograph an open and closed door, shoot a glass pane and a door, confirm player can walk through their openings, measure player collisions, and record zero runtime errors. Do not use photos of an older `main` commit as proof. Keep PR in draft until these real checks complete.

Future full-home support requires safely splitting each original model's door/window geometry from its fused wall mesh and authoring accurate wall colliders; it cannot be solved by animation alone.
