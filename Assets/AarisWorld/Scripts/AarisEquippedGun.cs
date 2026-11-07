using UnityEngine;

namespace Aaris.MapReview
{
    /// <summary>
    /// Optional equipment component: add to a future gun prefab and call
    /// AarisBattleActions.Equip(gun). Unarmed characters never require it.
    /// Pure local hit-scan; server validation is required for online multiplayer.
    /// </summary>
    public sealed class AarisEquippedGun : MonoBehaviour
    {
        [SerializeField, Min(0.05f)] private float secondsBetweenShots = 0.15f;
        [SerializeField, Min(1f)] private float maxRangeMetres = 180f;
        [SerializeField, Min(0f)] private float damage = 18f;
        private readonly RaycastHit[] hits = new RaycastHit[24];

        public float SecondsBetweenShots => secondsBetweenShots;

        /// <summary>
        /// Report the nearest external hit (not only a hit on another layer).
        /// Players and enemies can share the Player layer; only objects
        /// parented beneath the *shooting actor* are excluded. The nonalloc
        /// buffer fails closed when saturated, instead of picking a random
        /// farther object in a forest or crowded battle.
        /// </summary>
        private bool TryFirstOtherHit(Ray ray, float range, Transform owner,
            out RaycastHit closest, out bool saturated)
        {
            closest = default(RaycastHit);
            int count = Physics.RaycastNonAlloc(ray, hits, range,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
            saturated = count >= hits.Length;
            if (saturated) return false;
            int best = -1;
            float distance = float.PositiveInfinity;
            for (int i = 0; i < count; i++)
            {
                Collider collider = hits[i].collider;
                if (collider == null || collider.transform.IsChildOf(owner)) continue;
                if (hits[i].distance >= distance) continue;
                distance = hits[i].distance;
                best = i;
            }
            if (best < 0) return false;
            closest = hits[best];
            return true;
        }

        private static bool SameDamageTarget(Collider a, Collider b)
        {
            if (a == null || b == null) return false;
            if (a == b) return true;
            if (a.attachedRigidbody != null && a.attachedRigidbody == b.attachedRigidbody)
                return true;
            return a.transform.IsChildOf(b.transform) ||
                b.transform.IsChildOf(a.transform);
        }

        public bool TryFire(Camera camera, GameObject owner)
        {
            if (camera == null || owner == null) return false;
            Ray cameraRay = camera.ViewportPointToRay(new Vector3(0.5f, 0.5f, 0f));
            bool hasTarget = TryFirstOtherHit(cameraRay, maxRangeMetres,
                owner.transform, out RaycastHit target, out bool saturated);
            if (saturated) return false;

            Vector3 destination = hasTarget ? target.point : cameraRay.GetPoint(maxRangeMetres);
            // Crosshair uses camera aim but the physical muzzle must also
            // see the target; never hit somebody behind a nearby solid wall.
            Vector3 muzzle = owner.transform.position +
                Vector3.up * 1.3f + owner.transform.forward * 0.24f;
            Vector3 segment = destination - muzzle;
            float length = segment.magnitude;
            if (length > 0.025f)
            {
                bool hasMuzzleHit = TryFirstOtherHit(
                    new Ray(muzzle, segment / length), length,
                    owner.transform, out RaycastHit muzzleHit, out saturated);
                if (saturated) return false;
                if (hasMuzzleHit &&
                    (!hasTarget || !SameDamageTarget(target.collider, muzzleHit.collider)))
                    return true; // Bullet stopped by intervening cover.
            }
            if (hasTarget) ApplyDamage(target.collider, damage, owner);
            return true;
        }

        internal static void ApplyDamage(Collider collider, float amount, GameObject attacker)
        {
            if (collider == null) return;
            for (Transform node = collider.transform; node != null; node = node.parent)
            {
                // Interface is intentionally decoupled from health components.
                foreach (var component in node.GetComponents<MonoBehaviour>())
                {
                    if (component is IAarisDamageable damageable)
                    {
                        damageable.ApplyDamage(amount, attacker);
                        return;
                    }
                }
            }
        }
    }

    public interface IAarisDamageable
    {
        void ApplyDamage(float amount, GameObject attacker);
    }
}
