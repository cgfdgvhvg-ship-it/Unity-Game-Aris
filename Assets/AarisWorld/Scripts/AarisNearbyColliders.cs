using UnityEngine;

namespace Aaris.MapReview
{
    // Keep exact authored shapes. Terrain height/tree collisions and the player are never gated.
    [DisallowMultipleComponent, DefaultExecutionOrder(-250)]
    public sealed class AarisNearbyColliders : MonoBehaviour
    {
        [SerializeField] private Transform target;
        [SerializeField] private Collider[] obstacles;
        [SerializeField] private float activationDistance = 55;
        private Bounds[] worldBounds;
        private Vector3 lastPosition;
        private float nextCheck;

        private void Awake()
        {
            if (target == null || obstacles == null) { enabled = false; return; }
            worldBounds = new Bounds[obstacles.Length];
            for (int i = 0; i < obstacles.Length; i++)
            {
                Collider c = obstacles[i];
                if (c == null) continue;
                // Collider.bounds is empty while disabled. Read only local bounds metadata;
                // never temporarily enable/cook every distant building just to cache bounds.
                Bounds local;
                if (c is MeshCollider mc && mc.sharedMesh != null) local = mc.sharedMesh.bounds;
                else if (c is BoxCollider box) local = new Bounds(box.center, box.size);
                else { c.enabled = true; worldBounds[i] = c.bounds; continue; }
                Matrix4x4 m = c.transform.localToWorldMatrix;
                Vector3 e = local.extents;
                Vector3 x = m.MultiplyVector(new Vector3(e.x, 0, 0));
                Vector3 y = m.MultiplyVector(new Vector3(0, e.y, 0));
                Vector3 z = m.MultiplyVector(new Vector3(0, 0, e.z));
                Vector3 worldSize = 2 * new Vector3(Mathf.Abs(x.x) + Mathf.Abs(y.x) + Mathf.Abs(z.x),
                    Mathf.Abs(x.y) + Mathf.Abs(y.y) + Mathf.Abs(z.y), Mathf.Abs(x.z) + Mathf.Abs(y.z) + Mathf.Abs(z.z));
                worldBounds[i] = new Bounds(m.MultiplyPoint3x4(local.center), worldSize);
            }
            RefreshNow();
        }
        private void Update()
        {
            if (target == null) return;
            if ((target.position - lastPosition).sqrMagnitude >= 4 || Time.unscaledTime >= nextCheck) RefreshNow();
        }
        public void RefreshNow()
        {
            if (target == null || worldBounds == null) return;
            lastPosition = target.position;
            nextCheck = Time.unscaledTime + .25f;
            float limit = activationDistance * activationDistance;
            for (int i = 0; i < obstacles.Length; i++)
            {
                Collider c = obstacles[i];
                if (c == null) continue;
                // XZ distance supports long piers and elevated towers without early deactivation.
                Vector3 q = worldBounds[i].ClosestPoint(lastPosition);
                float dx = q.x - lastPosition.x, dz = q.z - lastPosition.z;
                bool wanted = dx * dx + dz * dz <= limit;
                if (c.enabled != wanted) c.enabled = wanted;
            }
            // A teleported CharacterController/camera must see the newly enabled shapes immediately.
            Physics.SyncTransforms();
        }
        private void OnDisable()
        {
            if (obstacles == null) return;
            foreach (Collider c in obstacles) if (c != null) c.enabled = true;
        }
    }
}
