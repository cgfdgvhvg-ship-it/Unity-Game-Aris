# Natural proportions for existing native Unity trees

The user requested trees that look less thin, with slightly thicker trunks and a fuller silhouette. **Original local Unity SpeedTree prefabs are retained**—there is no download or hotlinked model.

## Rebalanced tree silhouettes

| Original prefab | Root horizontal X/Z | Root vertical Y | Horizontal growth | Vertical growth |
| --- | ---: | ---: | ---: | ---: |
| Conifer | 1.15 | 1.035 | +15% | +3.5% |
| Pine_A | 1.13 | 1.035 | +13% | +3.5% |
| Pine_B | 1.16 | 1.035 | +16% | +3.5% |
| Pine_C | 1.13 | 1.035 | +13% | +3.5% |
| Pine_D | 1.14 | 1.04 | +14% | +4% |
| Cypress | 1.61 (previously 1.50) | 1.525 (previously 1.50) | +7.3% | +1.7% |

The change targets the **prefab root Transform only**. The same transform scales its trunk, native BoxCollider and all four existing near/far LODs together. It **does not claim** to separately edit trunk bark mesh vertices or add leaves; that would require asset-specific mesh reauthoring.

The original 1,100 added forest tree positions, six SpeedTree source assets, colors/materials, 4 native LFS TerrainData tiles, and native scene remain untouched in this PR. Original authored tree positions retain a minimum 13 m clearance from road edges, so the modest X/Z enlargement does not deliberately move trees onto roads.

## Verification and merge gate

Run `python3 Tools/Validation/test_tree_proportions.py` to check six prefab root scales, preserved four LOD meshes, BoxColliders, 1,100 placement coordinate references, and road clearance.

**This must be visually inspected in actual Unity 6000.3.26f1 (URP), including native Terrain tree rendering**. Unity Terrain may interpret TreePrototype prefab scale differently than ordinary GameObjects; confirm it affects native tree instances before merging. Test near the roads and compare trunk width, canopy proportions, physics collisions, draw calls and LOD popping from before/after images. If there is no native tree change, switch to a carefully verified TreeInstance.widthScale edit and serialize via Git LFS rather than claiming this prefab edit worked.

Do not reset the existing licensed Codespace's locally changed files. Use a separate `/tmp` worktree for any Unity validation and preserve all original source/Git LFS data.
