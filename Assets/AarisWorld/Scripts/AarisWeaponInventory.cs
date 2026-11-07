using UnityEngine;

namespace Aaris.MapReview
{
    /// <summary>
    /// Two weapon slots + empty-hand fallback. Equipped weapons are self-
    /// contained instances; switching does not reset remaining ammunition.
    /// This is a local prototype, not a network replicated inventory.
    /// </summary>
    [DisallowMultipleComponent, RequireComponent(typeof(AarisBattleActions))]
    public sealed class AarisWeaponInventory : MonoBehaviour
    {
        private readonly AarisEquippedGun[] slots = new AarisEquippedGun[2];
        private readonly Transform[] weaponModels = new Transform[2];
        private AarisBattleActions combat;
        private AarisThirdPersonPlayer motor;
        private int selected = -1;
        private bool aiming;
        private Transform hand;

        public AarisEquippedGun Current =>
            selected >= 0 && selected < slots.Length ? slots[selected] : null;
        public bool Aiming => aiming;
        public int SelectedSlot => selected;

        private void Awake()
        {
            combat = GetComponent<AarisBattleActions>();
            motor = GetComponent<AarisThirdPersonPlayer>();
        }

        public bool HasCapacity => slots[0] == null || slots[1] == null;

        public bool TryPickup(AarisWeaponSpec spec, uint seed)
        {
            if (spec == null || !spec.Valid || !HasCapacity) return false;
            int at = slots[0] == null ? 0 : 1;
            GameObject prefab = Resources.Load<GameObject>(spec.modelResource);
            if (prefab == null) return false; // never show a fake gun cube
            var root = new GameObject("Aaris Weapon Slot " + (at + 1) + " " + spec.id);
            root.transform.SetParent(transform, false);
            var equipped = root.AddComponent<AarisEquippedGun>();
            equipped.Configure(spec, seed);
            var visible = Instantiate(prefab, root.transform);
            visible.name = spec.displayName + " Model";
            // All gun geometry is purely cosmetic: no extra collisions or
            // physics motors grafted onto the humanoid.
            foreach (var c in visible.GetComponentsInChildren<Collider>(true)) c.enabled = false;
            var view = visible.transform;
            var renderer = view.GetComponentInChildren<Renderer>();
            if (renderer != null && renderer.bounds.size.sqrMagnitude > 0.0001f)
            {
                var bounds = renderer.bounds.size;
                float longest = Mathf.Max(bounds.x, bounds.y, bounds.z);
                view.localScale = Vector3.one * Mathf.Clamp(0.86f / longest, 0.001f, 10f);
            }
            view.localPosition = spec.handOffset;
            view.localRotation = Quaternion.Euler(spec.handRotation);
            view.localScale *= spec.handScale;
            slots[at] = equipped;
            weaponModels[at] = root.transform;
            root.SetActive(false);
            if (selected < 0) EquipSlot(at);
            Debug.Log("Aaris loot: acquired " + spec.displayName);
            return true;
        }

        public void EquipSlot(int slot)
        {
            if (slot < 0 || slot >= slots.Length || slots[slot] == null) return;
            if (combat != null) combat.SetFireHeld(false);
            selected = slot;
            ToggleAim(false);
            for (int i = 0; i < slots.Length; i++)
                if (slots[i] != null) slots[i].gameObject.SetActive(i == slot);
            combat.Equip(slots[selected]);
            AttachModelToHand(slot);
        }

        public void CycleWeapon()
        {
            if (selected < 0) return;
            int other = 1 - selected;
            if (slots[other] != null) EquipSlot(other);
        }

        public bool Reload() => Current != null && Current.BeginReload();

        public void ToggleAim()
        {
            if (Current == null) { ToggleAim(false); return; }
            ToggleAim(!aiming);
        }

        private void ToggleAim(bool value)
        {
            aiming = value && Current != null;
            if (motor != null)
                motor.SetWeaponAimFov(aiming ? Current.ScopeFov : -1f);
        }

        private void AttachModelToHand(int index)
        {
            if (weaponModels[index] == null) return;
            if (hand == null)
            {
                var animators = GetComponentsInChildren<Animator>(true);
                foreach (var animator in animators)
                    if (animator != null && animator.avatar != null && animator.avatar.isHuman)
                    {
                        hand = animator.GetBoneTransform(HumanBodyBones.RightHand);
                        if (hand != null) break;
                    }
            }
            Transform socket = hand != null ? hand : transform;
            weaponModels[index].SetParent(socket, false);
            if (hand == null)
                weaponModels[index].localPosition = new Vector3(.29f, 1.1f, .3f);
            else
                weaponModels[index].localPosition = Current.Spec.handOffset;
            weaponModels[index].localRotation = Quaternion.Euler(Current.Spec.handRotation);
        }

        private void LateUpdate()
        {
            // The Humanoid is created at scene start, potentially after
            // the first loot pickup. Bind the actual right hand once ready.
            if (Current != null && hand == null) AttachModelToHand(selected);
        }

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.Q)) CycleWeapon();
            if (Input.GetKeyDown(KeyCode.R)) Reload();
            if (Input.GetMouseButtonDown(1)) ToggleAim();
        }

        private void OnDisable()
        {
            ToggleAim(false);
            if (combat != null) combat.SetFireHeld(false);
        }
    }
}
