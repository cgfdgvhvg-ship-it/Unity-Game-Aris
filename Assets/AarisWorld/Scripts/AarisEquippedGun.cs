using UnityEngine;

namespace Aaris.MapReview
{
    /// <summary>
    /// One implementation for all locally configured weapon types.
    /// Emits camera-aligned hit scans, checks line of sight from the stance
    /// muzzle and applies damage only via the game-side IAarisDamageable hook.
    /// Single-player prototype; online sessions need server authority.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class AarisEquippedGun : MonoBehaviour
    {
        private readonly RaycastHit[] rayHits = new RaycastHit[48];
        private AarisWeaponSpec spec;
        private int magazine, reserve;
        private float reloadUntil, nextFire;
        private uint spreadSeed;
        private bool reloading;
        public bool Configured => spec != null;
        public bool Automatic => spec != null && spec.automatic;
        public float SecondsBetweenShots => spec != null ? spec.ShotInterval : 1f;
        public int Magazine { get { RefreshReload(); return magazine; } }
        public int Reserve { get { RefreshReload(); return reserve; } }
        public bool Reloading { get { RefreshReload(); return reloading; } }
        public string DisplayName => spec != null ? spec.displayName : "Unarmed";
        public float ScopeFov => spec != null ? spec.adsFov : 60f;
        public string ModelResource => spec != null ? spec.modelResource : null;
        public AarisWeaponSpec Spec => spec;

        public void Configure(AarisWeaponSpec weapon, uint matchSeed)
        {
            if (weapon == null || !weapon.Valid)
            {
                Debug.LogError("Aaris: invalid weapon configured.");
                enabled = false;
                return;
            }
            spec = weapon;
            magazine = spec.magazineSize;
            reserve = spec.reserveAmmo;
            spreadSeed = matchSeed ^ 0x7F4A7C15u;
            nextFire = 0f;
            reloading = false;
        }

        private void Update() => RefreshReload();

        // Even an unequipped weapon must complete its reload on schedule.
        // Unity stops calling Update on inactive inventory slot GameObjects.
        public void RefreshReload()
        {
            if (!reloading || spec == null || Time.time < reloadUntil) return;
            int transfer = Mathf.Min(spec.magazineSize - magazine, reserve);
            magazine += transfer;
            reserve -= transfer;
            reloading = false;
        }

        public bool BeginReload()
        {
            RefreshReload();
            if (spec == null || reloading || magazine >= spec.magazineSize || reserve == 0)
                return false;
            reloadUntil = Time.time + spec.reloadSeconds;
            reloading = true;
            return true;
        }

        private bool FirstExternalHit(Ray ray, float range, Transform owner,
            out RaycastHit nearest, out bool saturated)
        {
            nearest = default(RaycastHit);
            int count = Physics.RaycastNonAlloc(ray, rayHits, range,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
            saturated = count >= rayHits.Length;
            if (saturated) return false;
            float minDistance = float.PositiveInfinity;
            bool found = false;
            for (int i = 0; i < count; i++)
            {
                Collider collider = rayHits[i].collider;
                if (collider == null || collider.transform.IsChildOf(owner)) continue;
                if (rayHits[i].distance >= minDistance) continue;
                minDistance = rayHits[i].distance;
                nearest = rayHits[i];
                found = true;
            }
            return found;
        }

        private static bool SameTarget(Collider a, Collider b)
        {
            if (a == null || b == null) return false;
            if (a == b) return true;
            if (a.attachedRigidbody != null && a.attachedRigidbody == b.attachedRigidbody)
                return true;
            return a.transform.IsChildOf(b.transform) || b.transform.IsChildOf(a.transform);
        }

        public bool TryFire(Camera camera, GameObject owner)
        {
            RefreshReload();
            if (spec == null || camera == null || owner == null || reloading ||
                Time.time < nextFire) return false;
            if (magazine <= 0)
            {
                BeginReload();
                return false;
            }
            // Consume exactly one cartridge per trigger event, including
            // multi-pellet shotguns; reload and cooldown live in weapon state.
            magazine--;
            nextFire = Time.time + spec.ShotInterval;
            AarisBattleActions actions = owner.GetComponent<AarisBattleActions>();
            float muzzleHeight = actions != null
                ? Mathf.Max(0.28f, actions.CameraEyeHeight - 0.15f) : 1.3f;
            Vector3 muzzle = owner.transform.position + Vector3.up * muzzleHeight +
                owner.transform.forward * 0.24f;

            for (int pellet = 0; pellet < spec.pellets; pellet++)
            {
                Vector2 spread = new Vector2(AarisWeaponRandom.Next01(ref spreadSeed) * 2f - 1f,
                    AarisWeaponRandom.Next01(ref spreadSeed) * 2f - 1f);
                spread = Vector2.ClampMagnitude(spread, 1f) * spec.spreadDegrees;
                Vector3 look = Quaternion.AngleAxis(spread.x, camera.transform.up) *
                    Quaternion.AngleAxis(-spread.y, camera.transform.right) * camera.transform.forward;
                Ray aim = new Ray(camera.transform.position, look);
                bool targetFound = FirstExternalHit(aim, spec.rangeMetres,
                    owner.transform, out RaycastHit target, out bool saturated);
                if (saturated) continue; // fail closed on crowded physics
                Vector3 destination = targetFound ? target.point : aim.GetPoint(spec.rangeMetres);
                Vector3 path = destination - muzzle;
                float distance = path.magnitude;
                if (distance > 0.025f)
                {
                    bool muzzleHitFound = FirstExternalHit(
                        new Ray(muzzle, path / distance), distance,
                        owner.transform, out RaycastHit muzzleHit, out saturated);
                    if (saturated) continue;
                    if (muzzleHitFound &&
                        (!targetFound || !SameTarget(target.collider, muzzleHit.collider)))
                        continue;
                }
                if (targetFound) ApplyDamage(target.collider, spec.damage, owner);
            }
            var motor = owner.GetComponent<AarisThirdPersonPlayer>();
            if (motor != null) motor.ApplyWeaponRecoil(spec.recoilPitchDegrees,
                (AarisWeaponRandom.Next01(ref spreadSeed) - 0.5f) *
                spec.recoilPitchDegrees * 0.4f);
            if (magazine == 0) BeginReload();
            return true;
        }

        internal static void ApplyDamage(Collider collider, float amount, GameObject attacker)
        {
            if (collider == null) return;
            for (Transform node = collider.transform; node != null; node = node.parent)
            {
                foreach (var component in node.GetComponents<MonoBehaviour>())
                    if (component is IAarisDamageable damageable)
                    {
                        damageable.ApplyDamage(amount, attacker);
                        return;
                    }
            }
        }
    }

    public interface IAarisDamageable
    {
        void ApplyDamage(float amount, GameObject attacker);
    }
}
