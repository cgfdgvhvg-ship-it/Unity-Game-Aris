# Android 0.3.0: memory and saved battle-royale props

The reported 10–15 second Android exit has not been reproduced or attributed
to a particular fault. These are memory/physics hardening changes, not a
claim that the native/device crash is fixed. Test this version on the affected
4 GB or lower RAM phone before treating it as stable.

## Preserved appearance

All four TerrainData binaries keep their exact SHA-256 values. Existing height
grids, paint-map pixels, trees, rocks, buildings, close meshes, texture sources,
LOD thresholds, sky, water, sun, HDR, render scale, shadow settings and global
mipmap limit are retained. The original 13 districts, 59 model placements and
45 empty vehicle markers remain. Some original source rocks have no collider;
this change does not invent collision geometry for those vendor prototypes.

The Android review never paints terrain during play. Its eight 2048-square
RGBA paint maps contain 178,956,960 bytes (170.67 MiB) of CPU image data in
addition to their GPU images. `AarisMobileRuntime` uploads the unchanged
existing mip chains, one map per initial frame, then discards those CPU copies
with `Apply(false, true)`. No pixel arrays, mip recalculation, texture resizing
or terrain clones are created. This is eligible CPU memory, not a measured
device saving or total-process RAM estimate. It can cause short initial upload
hitches and must be verified on the phone. Editor assets remain readable;
runtime terrain painting/CPU alphamap reads must not be added without revisiting
this policy. The terrain height data used for walking is not released.

Repeated home instances and their reusable prefabs no longer request static
batch geometry duplication. Meshes/materials remain shared and the existing
SRP Batcher remains enabled. Draw-call/CPU tradeoffs still need profiling.
The exact authored static building/prop colliders activate within 55 m of the
player's XZ distance to their full world AABB, refreshed after 2 m travel or
0.25 s. Large piers and tower height are accounted for. HOME refreshes the
window synchronously after teleport. Terrain, native tree and player colliders
stay enabled. There are no replacement collision approximations for existing
buildings. Distant building colliders start disabled; bounds metadata can be
read without temporarily enabling/cooking all of them. Future vehicles,
projectiles or multiple players will need a multi-target collision policy.

Android uses explicit OpenGLES3 plus ETC2 instead of an automatic API choice.
This removes one source of driver variability; it does not establish a Vulkan
driver fault. Quality, color space, texture resolution and lighting are not
lowered. The frame target is 60, with a 30/60 button for frame pacing. A target
is not measured FPS and high frame rates cannot be guaranteed on every phone.

## Saved additions

`Docs/MOBILE_REVIEW_REPORT.json` records every exact transform and source.
There are four 12 m climbable lookout decks at Freight District, Southern
Airfield, Northern Ridge Town and Valley Settlement. Four switchback stair
flights have 1.7 m width, 0.167 m visible risers, 26.565-degree continuous
collision ramps, open stairwells and edge rails. Decks use existing flat pads;
terrain and roads are not moved. Unity walking/camera verification is pending.

Six original static wreck props decorate district margins. They are not
downloaded vehicle models, have no Rigidbody/vehicle scripts, and leave all
future drivable vehicle markers clear. New lookout and wreck meshes are
original project geometry. Twenty-four additional rock props use Poly Haven
Rock 09 by Jenelle van Heerden. Shared Rusty Metal 02 textures are by Rob
Tuytel. Both Poly Haven sources are CC0. Existing vendor terrain assets retain
their original Unity Asset Store licence. New sources:

- https://polyhaven.com/a/rock_09
- https://polyhaven.com/a/rusty_metal_02
- https://polyhaven.com/license

All additions share three saved LOD meshes per type and shared materials.
They are ordinary AI-readable Unity mesh/prefab/material assets, not runtime
GLB imports, map generation, new lights, particle effects or new render passes.
New 1K mobile prop textures retain their downloaded source resolution. They
do not replace or downscale any existing texture.

## Capture the next run

The REPORT button copies the latest local diagnostic JSON to the clipboard.
Paste it into the support chat after testing. It includes the device/GPU/API,
Unity allocations, Android PSS, texture-memory estimates, frame average/p95,
low-memory warning count, released paint-copy bytes and last managed error.
Unity allocations alone do not represent whole-process memory. Sampling is
every three seconds; it allocates no per-frame telemetry objects and triggers
no forced GC. Low-memory notifications request a cooldown-limited cleanup of
unused assets without lowering graphics. The OS may terminate an app without
first delivering a low-memory callback; native crashes and GPU/OS kills still
require Android logcat. Logs stay local in `AarisDiagnostics/current.jsonl`
and `previous.jsonl`, bounded to approximately 256 KiB each. Nothing is uploaded.

Saved-file checks: `python Tools/Validation/check_mobile_review.py --native`
(omit `--native` for a pointer-only checkout). Use Unity 6000.3.26f1 to import,
compile, render and build; run on the affected phone, walk into dense forest,
cross all seams, climb all towers, use HOME, pause/resume and compare memory
before/after. Repeat for several minutes. No device pass or FPS gain is claimed.

Optional maintainer reproduction: run `Tools/MapBuild/mobile_review.py` last,
after other map authoring, in a complete LFS checkout with its Python dependencies.
Normal Unity builds open the already saved scene and need no generation method.

## Spatial cells and actual asset streaming

Static building/prop physics is indexed in 250 m spatial cells. A long object
is indexed in every cell its world bounds touch; negative world coordinates
and cell-border crossings are supported. The active window queries only nearby
cells, reuses lists/stamps and activates the same exact collider set as a full
map scan. This reduces candidate-search work as props grow. It does not unload
TerrainData, meshes or textures: all four native terrain tiles remain resident.

A future full terrain streaming migration needs independently loadable chunk
assets, asynchronous preload before travel, an unload delay to prevent thrashing,
and a distant representation so the island skyline never disappears. Source
height sample spacing, painted texture layers, world-space UVs, shared edge
normals and collision continuity must survive the bake. It requires Unity
export and device testing, and is not claimed as implemented here. Merely
disabling a GameObject does not release strongly referenced assets. Lowering
paint maps to 512, forcing four layers, replacing the terrain shader, increasing
Pixel Error, removing distant shadows or adding fog to hide missing detail are
not applied to this version. No fixed FPS uplift or percentage RAM saving is
asserted.
