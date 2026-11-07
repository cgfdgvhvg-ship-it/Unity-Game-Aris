using UnityEngine;

namespace Aaris.MapReview
{
    /// <summary>
    /// Player intent/state; DOES NOT move the CharacterController.
    /// AarisThirdPersonPlayer remains the sole physics/terrain authority.
    /// A weapon slot is optional: empty hands make Fire invoke a melee punch.
    /// </summary>
    [DisallowMultipleComponent, RequireComponent(typeof(AarisThirdPersonPlayer))]
    [RequireComponent(typeof(CharacterController))]
    [DefaultExecutionOrder(-120)]
    public sealed class AarisBattleActions : MonoBehaviour
    {
        public enum PlayerStance { Standing, Crouching, Prone }

        [SerializeField, Min(0.56f)] private float crouchHeight = 1.14f;
        [SerializeField, Min(0.56f)] private float proneHeight = 0.62f;
        [SerializeField, Min(0.3f)] private float punchReach = 1.45f;
        [SerializeField, Min(0.1f)] private float punchInterval = 0.56f;
        [SerializeField, Min(0f)] private float punchDamage = 20f;
        [SerializeField] private AarisEquippedGun equippedGun;

        private CharacterController capsule;
        private AarisThirdPersonPlayer motor;
        private Vector3 standingCenter;
        private float standingHeight, standingStepOffset, nextAttack;
        private readonly Collider[] nearHits = new Collider[32];
        private PlayerStance stance;
        private bool fireHeld;
        private int attackSequence;
        private float lastPunchTime = -10f;

        public PlayerStance Stance => stance;
        public bool FireHeld => fireHeld;
        public bool IsArmed => equippedGun != null && equippedGun.isActiveAndEnabled;
        public float CameraEyeHeight => stance == PlayerStance.Prone ? 0.54f
            : stance == PlayerStance.Crouching ? 0.94f : 1.45f;
        public int AttackSequence => attackSequence;
        public float LastPunchTime => lastPunchTime;

        private void Awake()
        {
            capsule = GetComponent<CharacterController>();
            motor = GetComponent<AarisThirdPersonPlayer>();
            standingCenter = capsule.center;
            standingHeight = capsule.height;
            standingStepOffset = capsule.stepOffset;
            stance = PlayerStance.Standing;
        }

        public void Equip(AarisEquippedGun gun)
        {
            equippedGun = gun;
            nextAttack = 0f;
        }

        public void SetFireHeld(bool held)
        {
            fireHeld = held;
            if (held && motor != null) motor.CancelAutoSprint();
        }

        public bool ToggleCrouch() =>
            TrySetStance(stance == PlayerStance.Crouching
                ? PlayerStance.Standing : PlayerStance.Crouching);

        public bool ToggleProne() =>
            TrySetStance(stance == PlayerStance.Prone
                ? PlayerStance.Standing : PlayerStance.Prone);

        public bool TryStand() => TrySetStance(PlayerStance.Standing);

        public bool TrySetStance(PlayerStance target)
        {
            if (target == stance) return true;
            float height = target == PlayerStance.Standing ? standingHeight :
                target == PlayerStance.Crouching ? crouchHeight : proneHeight;
            // CharacterController cannot be shorter than its diameter.
            height = Mathf.Max(height, capsule.radius * 2f + 0.015f);
            if (height > capsule.height && !HasRoomAbove(height)) return false;

            float floorRelative = standingCenter.y - standingHeight * 0.5f;
            capsule.height = height;
            capsule.center = new Vector3(standingCenter.x, floorRelative + height * 0.5f, standingCenter.z);
            capsule.stepOffset = Mathf.Min(standingStepOffset, Mathf.Max(0.08f, height * 0.3f));
            stance = target;
            return true;
        }

        private bool HasRoomAbove(float proposedHeight)
        {
            float floor = standingCenter.y - standingHeight * 0.5f;
            float radius = Mathf.Max(0.05f, capsule.radius - capsule.skinWidth * 0.5f);
            Vector3 low = transform.TransformPoint(new Vector3(standingCenter.x, floor + radius, standingCenter.z));
            Vector3 high = transform.TransformPoint(new Vector3(
                standingCenter.x, floor + proposedHeight - radius, standingCenter.z));
            // The project reserves layer 8 for the player; do not hit its own limb meshes.
            int mask = Physics.DefaultRaycastLayers & ~(1 << gameObject.layer);
            int count = Physics.OverlapCapsuleNonAlloc(low, high, radius, nearHits, mask,
                QueryTriggerInteraction.Ignore);
            if (count == nearHits.Length) return false; // Fail closed on buffer overflow.
            for (int i = 0; i < count; i++)
                if (nearHits[i] != null && !nearHits[i].transform.IsChildOf(transform))
                    return false;
            return true;
        }

        private void Update()
        {
            if (!fireHeld || Time.time < nextAttack) return;
            if (IsArmed)
            {
                if (equippedGun.TryFire(motor.AimCamera, gameObject))
                {
                    attackSequence++;
                    nextAttack = Time.time + equippedGun.SecondsBetweenShots;
                }
                else nextAttack = Time.time + 0.04f;
                return;
            }

            nextAttack = Time.time + punchInterval;
            lastPunchTime = Time.time;
            attackSequence++;
            Punch();
        }

        private void Punch()
        {
            Vector3 origin = transform.position + Vector3.up *
                (stance == PlayerStance.Prone ? 0.4f : stance == PlayerStance.Crouching ? 0.73f : 1.15f);
            Vector3 center = origin + transform.forward * (punchReach * 0.58f);
            int mask = Physics.DefaultRaycastLayers & ~(1 << gameObject.layer);
            int count = Physics.OverlapSphereNonAlloc(center, 0.48f, nearHits, mask,
                QueryTriggerInteraction.Ignore);
            int best = -1;
            float distance = float.MaxValue;
            for (int i = 0; i < count; i++)
            {
                var collider = nearHits[i];
                if (collider == null || collider.transform.IsChildOf(transform)) continue;
                Vector3 nearest = collider.ClosestPoint(origin);
                Vector3 delta = nearest - origin;
                if (delta.sqrMagnitude > punchReach * punchReach ||
                    Vector3.Dot(transform.forward, delta) < 0.1f) continue;
                if (delta.sqrMagnitude < distance)
                {
                    distance = delta.sqrMagnitude;
                    best = i;
                }
            }
            if (best >= 0) AarisEquippedGun.ApplyDamage(nearHits[best], punchDamage, gameObject);
        }

        private void OnDisable() => fireHeld = false;
        private void OnApplicationPause(bool paused)
        {
            if (paused) fireHeld = false;
        }
    }

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
