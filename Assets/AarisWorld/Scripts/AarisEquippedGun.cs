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

        public bool TryFire(Camera camera, GameObject owner)
        {
            if (camera == null || owner == null) return false;
            Ray ray = camera.ViewportPointToRay(new Vector3(0.5f, 0.5f, 0f));
            int mask = Physics.DefaultRaycastLayers & ~(1 << owner.layer);
            int count = Physics.RaycastNonAlloc(ray, hits, maxRangeMetres, mask,
                QueryTriggerInteraction.Ignore);
            int bestIndex = -1;
            float bestDistance = float.PositiveInfinity;
            for (int i = 0; i < count; i++)
            {
                if (hits[i].collider == null || hits[i].collider.transform.IsChildOf(owner.transform))
                    continue;
                if (hits[i].distance < bestDistance)
                {
                    bestDistance = hits[i].distance;
                    bestIndex = i;
                }
            }
            if (bestIndex >= 0) ApplyDamage(hits[bestIndex].collider, damage, owner);
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
