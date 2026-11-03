# Android low-RAM emergency render scale — proposed, source-only

This is a **stacked change on draft PR #19**, not a replacement for its authored house/SpeedTree meshes, importer metadata or source-collider fixes. The four native TerrainData files, original materials, source prefabs, their GUID/fileID mappings, all camera far planes and Terrain tree visibility distances are **untouched by this patch**.

## Behavior

`AarisMobileRuntime` already has Android-only RAM-class profiles (reported RAM <= 3584 MB) and three 180-frame p95 frame-time quality states. This patch adds one extra, *opt-out* URP pixel-fill fallback. On devices outside that RAM class and in the Unity Editor, it does not run.

| State | 2-GB class (<= 2304 MB) | 3-GB class (2305–3584 MB) |
| --- | --- | --- |
| Normal / one-step pressure relief | Existing authored URP render scale | Existing authored URP render scale |
| Sustained pressure level 2 | At most 0.90, never higher than authored scale | At most 0.94, never higher than authored scale |
| Recovered quality level 0–1 | Restore exact originally loaded render scale | Restore exact originally loaded render scale |
| Runtime component destroyed | Restore original URP render scale | Restore original URP render scale |

Quality moves to pressure level 2 only after the existing startup warm-up, full 180-frame observation window, repeated p95 threshold crossings, and a cooldown. The game's 30/60-FPS switch resets this observation window; an intentional 30-FPS cap does not count as a 60-FPS stall. Disable the serialized `allowEmergencyRenderScale` boolean to compare A/B. Only when the active URP asset exists can this feature run. `renderScale` and `emergencyRenderScaleActive` are included in the local JSONL report.

This preserves distant **object visibility** but does not magically preserve **pixel resolution**: fine leaves, distant fences and text can appear softer at the fallback value. GPU pixel cost falls with render area, but the improvement is not guaranteed on CPU-bound scenes and may vary by device, driver and thermal state. The system is deliberately conservative to prioritize image clarity.

## Acceptance gates before merge

1. Import and compile in **Unity 6000.3.26f1 / URP 17.3.0**; ensure the configured URP asset permits the runtime render-scale setter. A source check is **not** a compilation.
2. Compare the same player route at original scale vs. fallback on real 2 GB and 3 GB Android phones: record p95 frame time, GPU frame time, Android PSS, streaming use, memory warnings, temperature and screenshot details of trees, rock edges, windows, rooflines and distant scenery.
3. Verify 60->30->60 frame-target switches do not create false pressure changes and that the profile restores on component unload. The report captures *Unity* frame-time and memory estimates; logcat/Profiler remain necessary for native faults.
4. Reject the fallback or adjust thresholds if the clarity loss exceeds the measured performance gain. Keep draft until actual device results and Unity import/physics capture are reviewed.

No new third-party geometry/model was downloaded. Saved door/window clearance and room accessibility still require continuous CharacterController and visual tests; this code does not change those assets.
