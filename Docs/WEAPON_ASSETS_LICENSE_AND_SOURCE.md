# Offline gun model source, redistribution and quality limits

Five rigged FBX firearm models are vendored from **Pichuliru, CC0 Flat Guns East** (2022). Original source: https://opengameart.org/content/cc0-flat-guns-east ; upstream curated copy: https://github.com/petroulacl/fps-asset-kit . OpenGameArt explicitly marks the artist's 10-model East pack **CC0 1.0** and includes FBX/GLB/OBJ/Blend. Keep this record when redistributing the game.

Source tree pinned to `petroulacl/fps-asset-kit@a19b7458a593598211c95ec46ef4eb4b6d1f94d7`. Each file is independently verified using Git's canonical blob SHA-1 (not a truncated filename checksum):

| Unity local FBX | Original source filename | Git blob SHA-1 |
| --- | --- | --- |
| SMG.fbx | SMG_Compact_East.Rig.fbx | 2fadbba99ac6d3373b8f6b04786374c42c54394f |
| AssaultRifle.fbx | Rifle_Assault_East.Rig.fbx | 8f2109f415755ad0af8aaa1d911ddfea7c2064cd |
| BattleRifle.fbx | Rifle_Battle_East.RIg.fbx | 24f2bfee4166e2208cb070b3de273f0989fafc9d |
| Sniper.fbx | Sniper_Rifle_East.Rig.fbx | a743e79ea184966021aba937d30cb6876e2cbaba |
| Shotgun.fbx | Shotgun_Pump_East.RIg.fbx | 3590c4b06c378037190edd870ca0c24fdaf5ae8a |

The binary FBX files must be **committed to this game repository**; a deleted upstream link cannot break a shipped APK. The GitHub Actions file `.github/workflows/aaris-weapon-vendor.yml` retrieves only these five pinned assets once. No actual game ever downloads weapons from that link.

**Honest visual limitation:** These are original CC0 **flat-shaded/rigged** firearm shapes, not PUBG's copyrighted meshes or photogrammetric/PBR weapons. They give production-safe silhouettes, real model geometry and an extensible material interface, but cannot be called photorealistic until Unity import, custom URP materials/textures and device visual QA confirm that result. No external SFX or trademarked skins have been copied.

The Unity model poses/hand orientations must be inspected in Editor before declaring the feature ready. The initial offline catalog uses balanced *Aaris-specific* parameters, not copied proprietary game values.

All firearm art remains 3D visual decoration only, never alters collision, projectile physics, buildings, terrain or the 2km player controller.
