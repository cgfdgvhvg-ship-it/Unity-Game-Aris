using System;
using System.Collections.Generic;
using UnityEngine;

namespace Aaris.MapReview
{
    [Serializable]
    internal sealed class AarisLootCandidate
    {
        public string kind, origin;
        public float x, y, z;
        public int slot;
    }

    [Serializable]
    internal sealed class AarisLootDocument
    {
        public int schema, sizeMetres;
        public AarisLootCandidate[] candidates;
    }

    /// <summary>
    /// Author-baked points + match-seeded, weighted loot. Only nearby areas
    /// become actual GameObjects, AFTER AarisNearbyColliders has enabled local
    /// building floors and walls. This avoids a 2x2km physics scan on boot.
    /// </summary>
    [DisallowMultipleComponent, DefaultExecutionOrder(-80)]
    public sealed class AarisWeaponLootWorld : MonoBehaviour
    {
        private const float ActivationMetres = 42f; // below the 55m collider streaming radius
        private const float ReleaseMetres = 69f;
        private const int MaximumActiveLoot = 40;
        private const float SeaLevel = -38.07552f;

        private readonly List<AarisWeaponPickup> active = new List<AarisWeaponPickup>(32);
        private readonly RaycastHit[] pickupObstructions = new RaycastHit[24];
        private AarisLootCandidate[] candidates;
        private AarisWeaponSpec[] choices;
        private bool[] consumed;
        private AarisWeaponInventory inventory;
        private Transform player;
        private float nextRefresh;
        private uint rng, matchSeed;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Boot()
        {
            var motor = FindFirstObjectByType<AarisThirdPersonPlayer>();
            if (motor == null || FindFirstObjectByType<AarisWeaponLootWorld>() != null) return;
            var inventory = motor.GetComponent<AarisWeaponInventory>();
            if (inventory == null) inventory = motor.gameObject.AddComponent<AarisWeaponInventory>();
            var root = new GameObject("Aaris Match Weapon Loot (offline, streamed)");
            var world = root.AddComponent<AarisWeaponLootWorld>();
            world.player = motor.transform;
            world.inventory = inventory;
            world.Initialize();
        }

        private void Initialize()
        {
            if (!AarisWeaponCatalog.TryLoad())
            {
                enabled = false;
                return;
            }
            TextAsset text = Resources.Load<TextAsset>("AarisWeapons/loot_candidates");
            if (text == null)
            {
                Debug.LogError("Aaris: no embedded offline authored loot locations.");
                enabled = false;
                return;
            }
            AarisLootDocument doc;
            try { doc = JsonUtility.FromJson<AarisLootDocument>(text.text); }
            catch (Exception e)
            {
                Debug.LogError("Aaris: invalid loot JSON: " + e.Message);
                enabled = false;
                return;
            }
            if (doc == null || doc.schema != 1 || doc.sizeMetres != 2000 ||
                doc.candidates == null || doc.candidates.Length < 50)
            {
                Debug.LogError("Aaris: loot candidates do not describe the 2km map.");
                enabled = false;
                return;
            }
            // Different each match; deterministic once seed is chosen. A
            // future authoritative server can provide this seed to clients.
            matchSeed = unchecked((uint)DateTime.UtcNow.Ticks) ^
                unchecked((uint)Environment.TickCount) ^ 0x59371FA3u;
            rng = matchSeed;

            // 4 tiles hold around 7,500 native trees. Sample just a few
            // distributed tree cover nodes ONCE at match boot, never every
            // frame and never one loot item for every vegetation instance.
            var allCandidates = new List<AarisLootCandidate>(doc.candidates);
            AppendNativeTreeCover(allCandidates);
            candidates = allCandidates.ToArray();
            consumed = new bool[candidates.Length];
            choices = new AarisWeaponSpec[candidates.Length];
            int selected = 0;
            for (int i = 0; i < candidates.Length; i++)
            {
                var c = candidates[i];
                // Apply the probability to ALL sectors. An early cap on
                // sorted candidates unfairly stocked the west side first
                // and left the east half of the 2km map with no outdoor loot.
                // Memory is bounded by 514 authored slots; instantiated
                // GameObjects are separately capped at MaximumActiveLoot.
                if (!WithinMap(c)) continue;
                bool indoor = c.kind == "indoor";
                float chance = indoor ? 0.72f :
                    c.kind == "tree" ? 0.75f : 0.32f;
                if (AarisWeaponRandom.Next01(ref rng) > chance) continue;
                var spec = AarisWeaponCatalog.Select(ref rng, indoor);
                if (spec == null) continue;
                choices[i] = spec;
                selected++;
            }
            Debug.Log("Aaris: match seed " + matchSeed + ", planned " + selected +
                " offline pickups (actual ground/collision validated near player).");
        }

        private void AppendNativeTreeCover(List<AarisLootCandidate> result)
        {
            foreach (var terrain in Terrain.activeTerrains)
            {
                if (terrain == null || terrain.terrainData == null) continue;
                var data = terrain.terrainData;
                // TreeInstance[] is requested ONCE per tile, not once per
                // update. The saved map currently contains ~7.5k instances
                // in total. Keep the sample budget fixed for mobile memory.
                TreeInstance[] trees = data.treeInstances;
                if (trees == null || trees.Length == 0) continue;
                int accepted = 0, attempts = 0;
                Vector3 origin = terrain.transform.position;
                Vector3 size = data.size;
                while (accepted < 12 && attempts++ < 72)
                {
                    int idx = (int)(AarisWeaponRandom.Next(ref rng) % (uint)trees.Length);
                    Vector3 tree = origin + Vector3.Scale(trees[idx].position, size);
                    float angle = AarisWeaponRandom.Next01(ref rng) * Mathf.PI * 2f;
                    float distance = 2f + AarisWeaponRandom.Next01(ref rng) * 7f;
                    float x = tree.x + Mathf.Cos(angle) * distance;
                    float z = tree.z + Mathf.Sin(angle) * distance;
                    if (x < -955f || x > 955f || z < -955f || z > 955f) continue;
                    bool nearExistingTreeCandidate = false;
                    foreach (var c in result)
                    {
                        if (c.kind != "tree") continue;
                        float dx = c.x - x, dz = c.z - z;
                        if (dx * dx + dz * dz < 32f * 32f)
                        {
                            nearExistingTreeCandidate = true;
                            break;
                        }
                    }
                    if (nearExistingTreeCandidate) continue;
                    result.Add(new AarisLootCandidate
                    {
                        kind = "tree", x = x, y = 0f, z = z,
                        origin = "native Terrain tree", slot = idx
                    });
                    accepted++;
                }
            }
        }

        private static bool WithinMap(AarisLootCandidate c) =>
            c != null && c.x >= -957f && c.x <= 957f &&
            c.z >= -957f && c.z <= 957f;

        private static Terrain TerrainAt(float x, float z)
        {
            foreach (var t in Terrain.activeTerrains)
            {
                if (t == null || t.terrainData == null) continue;
                Vector3 p = t.transform.position;
                Vector3 s = t.terrainData.size;
                if (x >= p.x && x <= p.x + s.x && z >= p.z && z <= p.z + s.z)
                    return t;
            }
            return null;
        }

        private bool TryResolve(AarisLootCandidate c, out Vector3 spot)
        {
            spot = default(Vector3);
            var terrain = TerrainAt(c.x, c.z);
            if (terrain == null) return false;
            bool indoor = c.kind == "indoor";
            // For outdoor positions use the native Terrain surface, NOT
            // the first arbitrary roof encountered from the sky.
            float expectedGround = indoor ? c.y :
                terrain.transform.position.y + terrain.SampleHeight(new Vector3(c.x, 0f, c.z));
            if (expectedGround <= SeaLevel + 0.7f) return false;
            Vector3 start = new Vector3(c.x, expectedGround + 1.9f, c.z);
            if (!Physics.Raycast(start, Vector3.down, out RaycastHit floor, 3.3f,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                return false;
            if (floor.normal.y < (indoor ? 0.966f : 0.970f)) return false;
            if (Mathf.Abs(floor.point.y - expectedGround) > 0.85f) return false;

            if (indoor)
            {
                // AABB alone NEVER proves that an area has an interior.
                // Require a physical ceiling and a flat solid support.
                Vector3 above = floor.point + Vector3.up * 0.78f;
                if (!Physics.Raycast(above, Vector3.up, out RaycastHit roof, 15f,
                    Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                    return false;
                if (roof.collider is TerrainCollider) return false;
                if (roof.distance < 1.05f) return false; // unusably low roof
            }
            else if (!(floor.collider is TerrainCollider))
            {
                // An outdoor loot entry must never turn into roof loot.
                return false;
            }

            Vector3 center = floor.point + Vector3.up * 0.43f;
            if (Physics.CheckCapsule(center + Vector3.down * .05f,
                center + Vector3.up * .25f, .19f,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore))
                return false; // no inside-wall or furniture placement

            spot = floor.point + Vector3.up * .13f;
            return true;
        }

        private bool CanReachPickup(AarisWeaponPickup pickup)
        {
            // Range is not enough: a weapon behind a solid wall must not be
            // collected through that wall. Ignore only the player's own
            // colliders, not all colliders on the player layer.
            Vector3 eye = player.position + Vector3.up * .95f;
            Vector3 target = pickup.transform.position + Vector3.up * .24f;
            Vector3 toTarget = target - eye;
            float distance = toTarget.magnitude;
            if (distance <= 0.001f) return true;
            int hits = Physics.RaycastNonAlloc(new Ray(eye, toTarget / distance),
                pickupObstructions, distance,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
            if (hits >= pickupObstructions.Length) return false;
            for (int i = 0; i < hits; i++)
            {
                var collider = pickupObstructions[i].collider;
                if (collider == null || collider.transform.IsChildOf(player)) continue;
                return false;
            }
            return true;
        }

        private void Update()
        {
            if (player == null || inventory == null || candidates == null) return;
            if (Time.unscaledTime < nextRefresh) return;
            nextRefresh = Time.unscaledTime + .33f;
            var playerPosition = player.position;
            float releaseSquared = ReleaseMetres * ReleaseMetres;

            for (int i = active.Count - 1; i >= 0; i--)
            {
                var pickup = active[i];
                if (pickup == null)
                {
                    active.RemoveAt(i);
                    continue;
                }
                float d2 = (pickup.transform.position - playerPosition).sqrMagnitude;
                if (d2 < 2.15f * 2.15f && inventory.HasCapacity &&
                    CanReachPickup(pickup))
                {
                    if (inventory.TryPickup(pickup.Spec,
                        matchSeed ^ (uint)(pickup.CandidateIndex + 1)))
                    {
                        consumed[pickup.CandidateIndex] = true;
                        active.RemoveAt(i);
                        Destroy(pickup.gameObject);
                        continue;
                    }
                }
                if (d2 > releaseSquared)
                {
                    active.RemoveAt(i);
                    Destroy(pickup.gameObject);
                }
            }

            if (active.Count >= MaximumActiveLoot) return;
            float loadSquared = ActivationMetres * ActivationMetres;
            int built = 0;
            for (int i = 0; i < candidates.Length && active.Count < MaximumActiveLoot; i++)
            {
                if (choices[i] == null || consumed[i] || IsCurrentlyActive(i)) continue;
                var c = candidates[i];
                float dx = c.x - playerPosition.x, dz = c.z - playerPosition.z;
                if (dx * dx + dz * dz >= loadSquared) continue;
                if (built >= 6) break; // avoid 1-frame mass imports
                if (!TryResolve(c, out Vector3 spot)) continue;
                var root = new GameObject("Loot " + choices[i].displayName + " #" + i);
                root.transform.SetParent(transform, false);
                root.transform.position = spot;
                var pickup = root.AddComponent<AarisWeaponPickup>();
                pickup.Initialize(choices[i], i);
                if (!pickup.enabled) { Destroy(root); continue; }
                active.Add(pickup);
                built++;
            }
        }

        private bool IsCurrentlyActive(int candidateIndex)
        {
            foreach (var item in active)
                if (item != null && item.CandidateIndex == candidateIndex) return true;
            return false;
        }
    }
}
