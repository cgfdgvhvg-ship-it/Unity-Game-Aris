using System;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace Aaris.MapReview
{
    /// <summary>
    /// Presentation-only adapter. The saved AarisThirdPersonPlayer continues to own
    /// input, camera, physics and terrain traversal. Imported characters never add
    /// another collider, rigidbody or movement controller.
    /// </summary>
    [DisallowMultipleComponent, RequireComponent(typeof(CharacterController))]
    [DefaultExecutionOrder(200)]
    public sealed class AarisCharacterVisual : MonoBehaviour
    {
        private const string PrimaryModel = "AarisCharacters/Primary/Player";
        private const string FallbackModel = "AarisCharacters/Kenney/characterMedium";
        private const string KenneyClips = "AarisCharacters/Kenney/";
        private const string PrimaryClips = "AarisCharacters/Primary/Animations/";
        private const float TargetHeightMetres = 1.78f;

        [SerializeField, Range(-180f, 180f)] private float modelYawOffset;
        [SerializeField, Range(0.1f, 0.8f)] private float blendResponseSeconds = 0.2f;
        [SerializeField] private float fullRunSpeed = 6.5f;
        [SerializeField, Range(0f, 8f)] private float sprintForwardLeanDegrees = 4f;
        [SerializeField, Range(0f, 0.12f)] private float landingCompressionMetres = 0.055f;

        private CharacterController controller;
        private GameObject visual;
        private MeshRenderer[] placeholderRenderers;
        private Animator animator;
        private Material runtimeSkin;
        private PlayableGraph graph;
        private AnimationMixerPlayable mixer;
        private bool graphReady;
        private float runBlend;
        private float airborneBlend;
        private float walkRunBlend;
        private AnimationClipPlayable idlePlayable, walkPlayable, runPlayable, jumpPlayable,
            fallPlayable, crouchPlayable, crouchWalkPlayable, jumpStartPlayable,
            jumpLandPlayable, punchPlayable, shootPlayable;
        private AnimationClip crouchClip, crouchWalkClip, punchClip, shootClip;
        private int lastVisualAttackSequence;
        private float seenTakeoff = -10f, seenTouchdown = -10f;
        private AarisBattleActions actions;
        private AarisThirdPersonPlayer playerMotor;
        private Transform punchArm;
        private Vector3 restingLocalPosition;
        private Quaternion restingLocalRotation;
        private float crouchBlend, proneBlend;
        private AnimationClip idleClip, walkClip, runClip;
        private float locomotionPhase;
        private bool primaryLoaded;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void AttachToExistingPlayer()
        {
            // Preserve the checked-in scene and player prefab, including all original
            // camera references and controller tuning. No scene editor drag-and-drop.
            var player = FindFirstObjectByType<AarisThirdPersonPlayer>();
            if (player != null && player.GetComponent<AarisCharacterVisual>() == null)
                player.gameObject.AddComponent<AarisCharacterVisual>();
        }

        private void Awake()
        {
            controller = GetComponent<CharacterController>();
        }

        private void Start()
        {
            var source = Resources.Load<GameObject>(PrimaryModel);
            primaryLoaded = source != null;
            if (source == null)
                source = Resources.Load<GameObject>(FallbackModel);
            if (source == null)
            {
                Debug.LogWarning("Aaris: no imported 3D character yet. Existing humanoid remains visible. Install the CC0 character pack.");
                enabled = false;
                return;
            }

            visual = Instantiate(source, transform, false);
            visual.name = "AarisRiggedCharacterVisual";
            visual.transform.localPosition = Vector3.zero;
            visual.transform.localRotation = Quaternion.Euler(0f, modelYawOffset, 0f);
            SetLayerRecursively(visual.transform, gameObject.layer);

            animator = visual.GetComponentInChildren<Animator>(true);
            if (animator == null)
                animator = visual.AddComponent<Animator>();

            if (animator.avatar == null)
            {
                Avatar[] avatars = Resources.LoadAll<Avatar>(
                    source.name == "Player" ? PrimaryModel : FallbackModel);
                for (int i = 0; i < avatars.Length; i++)
                {
                    if (avatars[i] != null && avatars[i].isValid && avatars[i].isHuman)
                    {
                        animator.avatar = avatars[i];
                        break;
                    }
                }
            }
            if (animator.avatar == null || !animator.avatar.isValid || !animator.avatar.isHuman)
            {
                Debug.LogWarning("Aaris: imported model has no valid Humanoid Avatar; keeping the original player visible.");
                Destroy(visual);
                visual = null;
                enabled = false;
                return;
            }

            if (!FitVisualToController())
            {
                Debug.LogWarning("Aaris: imported character has no usable render bounds; keeping original model.");
                Destroy(visual);
                visual = null;
                enabled = false;
                return;
            }

            // Only hide the OLD primitive mesh renderers. Do not touch collisions,
            // virtual camera, Transform hierarchy, UI or existing controller.
            placeholderRenderers = GetComponentsInChildren<MeshRenderer>(true);
            for (int i = 0; i < placeholderRenderers.Length; i++)
                if (placeholderRenderers[i] != null &&
                    !placeholderRenderers[i].transform.IsChildOf(visual.transform))
                    placeholderRenderers[i].enabled = false;

            TryApplySkin();
            actions = GetComponent<AarisBattleActions>();
            playerMotor = GetComponent<AarisThirdPersonPlayer>();
            restingLocalPosition = visual.transform.localPosition;
            restingLocalRotation = visual.transform.localRotation;
            punchArm = animator.GetBoneTransform(HumanBodyBones.RightUpperArm);
            animator.applyRootMotion = false;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            SetupAnimations();
            Debug.Log(graphReady
                ? "Aaris: rigged player + humanoid idle/run/jump animation mixer ready."
                : "Aaris: rigged player ready; compatible animation clips not yet imported.");
        }

        private bool FitVisualToController()
        {
            var renderers = visual.GetComponentsInChildren<Renderer>(true);
            Bounds combined = new Bounds();
            bool hasBounds = false;
            foreach (var renderer in renderers)
            {
                if (renderer == null) continue;
                if (!hasBounds) { combined = renderer.bounds; hasBounds = true; }
                else combined.Encapsulate(renderer.bounds);
            }
            if (!hasBounds || combined.size.y < 0.01f || combined.size.y > 1000f)
                return false;

            float scale = Mathf.Clamp(TargetHeightMetres / combined.size.y, 0.01f, 100f);
            visual.transform.localScale = Vector3.one * scale;
            // FBX pivots vary between packages. Align the bottom of the mesh with
            // the CharacterController's ground point, without moving the collider.
            Physics.SyncTransforms();
            combined = new Bounds();
            hasBounds = false;
            foreach (var renderer in renderers)
            {
                if (renderer == null) continue;
                if (!hasBounds) { combined = renderer.bounds; hasBounds = true; }
                else combined.Encapsulate(renderer.bounds);
            }
            if (hasBounds)
                visual.transform.position += Vector3.up * (transform.position.y - combined.min.y);
            return true;
        }

        private void TryApplySkin()
        {
            // Never recolor an external high-fidelity Player.fbx by force.
            if (Resources.Load<GameObject>(PrimaryModel) != null) return;
            var skins = Resources.LoadAll<Texture2D>(KenneyClips);
            Texture2D chosen = null;
            int bestScore = int.MinValue;
            foreach (var tex in skins)
            {
                if (tex == null) continue;
                string n = tex.name.ToLowerInvariant();
                int score = (n.Contains("human") ? 8 : 0)
                    + (n.Contains("male") ? 3 : 0)
                    + (n.Contains("casual") ? 2 : 0)
                    - (n.Contains("zombie") ? 20 : 0);
                if (score > bestScore) { chosen = tex; bestScore = score; }
            }
            if (chosen == null || bestScore < 0) return;
            Shader shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) shader = Shader.Find("Standard");
            if (shader == null) return;
            runtimeSkin = new Material(shader) { name = "AarisKenneyRuntimeSkin" };
            if (runtimeSkin.HasProperty("_BaseMap")) runtimeSkin.SetTexture("_BaseMap", chosen);
            else runtimeSkin.mainTexture = chosen;
            foreach (var skinned in visual.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                skinned.sharedMaterial = runtimeSkin;
        }

        private static void SetLayerRecursively(Transform t, int layer)
        {
            t.gameObject.layer = layer;
            for (int i = 0; i < t.childCount; i++)
                SetLayerRecursively(t.GetChild(i), layer);
        }

        private AnimationClip FindClip(string name, string preferred)
        {
            // Unity imports each local FBX as an AnimationClip subasset.
            string location = primaryLoaded ? PrimaryClips + name : KenneyClips + name;
            var clips = Resources.LoadAll<AnimationClip>(location);
            AnimationClip fallback = null;
            foreach (var clip in clips)
            {
                if (clip == null || clip.legacy || clip.length < 0.02f) continue;
                string label = clip.name.ToLowerInvariant();
                if (label.Contains("preview") || label.Contains("pose")) continue;
                if (label.Contains(preferred)) return clip;
                if (fallback == null) fallback = clip;
            }
            return fallback;
        }

        private void SetupAnimations()
        {
            idleClip = FindClip("idle", "idle");
            walkClip = FindClip("walk", "walk") ?? FindClip("run", "run");
            runClip = FindClip("run", "run");
            // Each FBX has one reviewed humanoid motion: never use the
            // Jump_Land clip for takeoff or airborne looping.
            AnimationClip jump = FindClip("jump", "jump");
            AnimationClip jumpStart = FindClip("jump_start", "jump") ?? jump;
            AnimationClip jumpLand = FindClip("jump_land", "jump") ?? jump;
            AnimationClip fall = FindClip("fall", "fall");
            crouchClip = FindClip("crouch", "crouch") ?? idleClip;
            crouchWalkClip = FindClip("crouch_walk", "crouch") ?? crouchClip;
            punchClip = FindClip("punch", "punch");
            shootClip = FindClip("shoot", "shoot");
            if (punchClip == null) punchClip = idleClip;
            if (shootClip == null) shootClip = idleClip;
            if (idleClip == null || walkClip == null || runClip == null)
                return;
            if (jump == null) jump = idleClip;
            if (fall == null) fall = jump;

            graph = PlayableGraph.Create("AarisHumanoidLocomotion");
            graph.SetTimeUpdateMode(DirectorUpdateMode.GameTime);
            mixer = AnimationMixerPlayable.Create(graph, 11);
            idlePlayable = AnimationClipPlayable.Create(graph, idleClip);
            walkPlayable = AnimationClipPlayable.Create(graph, walkClip);
            runPlayable = AnimationClipPlayable.Create(graph, runClip);
            jumpPlayable = AnimationClipPlayable.Create(graph, jump);
            fallPlayable = AnimationClipPlayable.Create(graph, fall);
            crouchPlayable = AnimationClipPlayable.Create(graph, crouchClip);
            crouchWalkPlayable = AnimationClipPlayable.Create(graph, crouchWalkClip);
            jumpStartPlayable = AnimationClipPlayable.Create(graph, jumpStart);
            jumpLandPlayable = AnimationClipPlayable.Create(graph, jumpLand);
            punchPlayable = AnimationClipPlayable.Create(graph, punchClip);
            shootPlayable = AnimationClipPlayable.Create(graph, shootClip);
            // Keep one-shot clips short enough to react promptly to attacks
            // without blending over multiple shots in the same hold.
            punchPlayable.SetSpeed(Mathf.Clamp(punchClip.length / 0.42f, 0.7f, 3.5f));
            shootPlayable.SetSpeed(Mathf.Clamp(shootClip.length / 0.2f, 0.7f, 4.0f));
            jumpLandPlayable.SetSpeed(Mathf.Clamp(jumpLand.length / 0.3f, 0.7f, 3.0f));
            idlePlayable.SetApplyFootIK(true);
            walkPlayable.SetApplyFootIK(true);
            runPlayable.SetApplyFootIK(true);
            crouchWalkPlayable.SetApplyFootIK(true);
            var inputs = new[]
            {
                idlePlayable, walkPlayable, runPlayable,
                jumpPlayable, fallPlayable, crouchPlayable,
                crouchWalkPlayable, jumpStartPlayable, jumpLandPlayable,
                punchPlayable, shootPlayable
            };
            for (int i = 0; i < inputs.Length; i++)
            {
                graph.Connect(inputs[i], 0, mixer, i);
                mixer.SetInputWeight(i, i == 0 ? 1f : 0f);
            }
            var output = AnimationPlayableOutput.Create(graph, "AarisHumanoidOutput", animator);
            output.SetSourcePlayable(mixer);
            graphReady = true;
            graph.Play();
        }

        private static void LoopPlayable(AnimationClipPlayable playable, AnimationClip clip, double cycle)
        {
            if (clip == null || clip.length < 0.02f) return;
            double seconds = cycle * clip.length;
            playable.SetTime(seconds - Math.Floor(seconds / clip.length) * clip.length);
        }

        private void LateUpdate()
        {
            if (visual == null || controller == null) return;
            if (actions == null) actions = GetComponent<AarisBattleActions>();

            float dt = Mathf.Min(Time.deltaTime, 0.05f);
            float alpha = 1f - Mathf.Exp(-dt / Mathf.Max(0.04f, blendResponseSeconds));
            bool crouching = actions != null &&
                actions.Stance == AarisBattleActions.PlayerStance.Crouching;
            bool prone = actions != null &&
                actions.Stance == AarisBattleActions.PlayerStance.Prone;
            crouchBlend = Mathf.Lerp(crouchBlend, crouching ? 1f : 0f, alpha);
            proneBlend = Mathf.Lerp(proneBlend, prone ? 1f : 0f, alpha);

            // The source CC0 pack contains a crouch clip, not a full prone
            // crawl clip. Tilt/ground-align the mesh as a visual fallback;
            // the actual prone collision capsule is authoritative.
            // Runtime animator owns limb poses; this shallow, visual-only
            // secondary motion adds sprint anticipation and soft landing.
            // It never moves the physical CharacterController.
            Vector3 velocityNow = controller.velocity;
            float planar = new Vector2(velocityNow.x, velocityNow.z).magnitude;
            float leaning = Mathf.InverseLerp(4.2f, fullRunSpeed, planar) *
                sprintForwardLeanDegrees * (1f - proneBlend);
            Quaternion upright = restingLocalRotation * Quaternion.Euler(leaning, 0f, 0f);
            Quaternion proneRotation = restingLocalRotation * Quaternion.Euler(80f, 0f, 0f);
            visual.transform.localRotation = Quaternion.Slerp(upright, proneRotation, proneBlend);

            float landingAge = playerMotor != null
                ? Time.unscaledTime - playerMotor.LastLandingTime
                : 10f;
            float landingDip = landingAge >= 0f && landingAge <= 0.2f
                ? Mathf.Sin(Mathf.PI * landingAge / 0.2f) * landingCompressionMetres
                : 0f;
            visual.transform.localPosition = restingLocalPosition +
                new Vector3(0f, proneBlend * 0.36f - landingDip, proneBlend * 0.14f);

            if (graphReady)
            {
                Vector3 velocity = controller.velocity;
                float horizontal = new Vector2(velocity.x, velocity.z).magnitude;
                float movementTarget = Mathf.Clamp01(horizontal / 1.2f);
                float sprintTarget = Mathf.InverseLerp(3.4f,
                    Mathf.Max(3.5f, fullRunSpeed), horizontal);
                float airTarget = controller.isGrounded ? 0f : 1f;
                runBlend = Mathf.Lerp(runBlend, movementTarget, alpha);
                walkRunBlend = Mathf.Lerp(walkRunBlend, sprintTarget, alpha);
                airborneBlend = Mathf.Lerp(airborneBlend, airTarget, alpha);

                // Exclusive stance base, phase-specific airborne/landing
                // transitions, and reactive one-shot combat weights. Every
                // mixer input participates in a weight sum of approximately 1.
                float pose = Mathf.Clamp01(crouchBlend + proneBlend);
                float crouchMotion = Mathf.Clamp01(horizontal / 1.2f) *
                    crouchBlend * (1f - proneBlend);
                float crouchRest = pose - crouchMotion;
                float grounded = (1f - airborneBlend) * (1f - pose);
                float jumping = velocity.y >= -0.6f ? 1f : 0f;

                float takeoffAge = playerMotor != null
                    ? Time.unscaledTime - playerMotor.LastJumpStartedTime : 10f;
                float touchdownAge = playerMotor != null
                    ? Time.unscaledTime - playerMotor.LastLandingTime : 10f;
                float startWeight = airborneBlend > 0.02f && takeoffAge >= 0f &&
                    takeoffAge < 0.23f
                    ? Mathf.Clamp01((0.23f - takeoffAge) / 0.14f) : 0f;
                float landWeight = controller.isGrounded && touchdownAge >= 0f &&
                    touchdownAge < 0.28f
                    ? Mathf.Clamp01((0.28f - touchdownAge) / 0.18f) : 0f;
                float lastPunchAge = actions != null ? Time.time - actions.LastPunchTime : 10f;
                float lastShootAge = actions != null ? Time.time - actions.LastShootTime : 10f;
                float punchWeight = lastPunchAge >= 0f && lastPunchAge < 0.43f
                    ? Mathf.Clamp01((0.43f - lastPunchAge) / 0.12f) : 0f;
                float shootWeight = lastShootAge >= 0f && lastShootAge < 0.2f
                    ? Mathf.Clamp01((0.2f - lastShootAge) / 0.07f) : 0f;

                // Jumps/landings win over combat, which wins over locomotion.
                float primary = Mathf.Max(startWeight, landWeight);
                punchWeight *= 1f - primary;
                shootWeight *= 1f - primary;
                if (shootWeight > 0f) punchWeight = 0f;
                float baseWeight = 1f - Mathf.Clamp01(primary + punchWeight + shootWeight);
                mixer.SetInputWeight(0, baseWeight * grounded * (1f - runBlend));
                mixer.SetInputWeight(1, baseWeight * grounded * runBlend * (1f - walkRunBlend));
                mixer.SetInputWeight(2, baseWeight * grounded * runBlend * walkRunBlend);
                mixer.SetInputWeight(3, baseWeight * airborneBlend * jumping * (1f - pose));
                mixer.SetInputWeight(4, baseWeight * airborneBlend * (1f - jumping) * (1f - pose));
                mixer.SetInputWeight(5, baseWeight * crouchRest);
                mixer.SetInputWeight(6, baseWeight * crouchMotion);
                mixer.SetInputWeight(7, startWeight);
                mixer.SetInputWeight(8, landWeight);
                mixer.SetInputWeight(9, punchWeight);
                mixer.SetInputWeight(10, shootWeight);

                if (playerMotor != null && takeoffAge >= 0f &&
                    playerMotor.LastJumpStartedTime != seenTakeoff)
                {
                    seenTakeoff = playerMotor.LastJumpStartedTime;
                    jumpStartPlayable.SetTime(0d);
                }
                if (playerMotor != null && touchdownAge >= 0f &&
                    playerMotor.LastLandingTime != seenTouchdown)
                {
                    seenTouchdown = playerMotor.LastLandingTime;
                    jumpLandPlayable.SetTime(0d);
                }
                if (actions != null && actions.AttackSequence != lastVisualAttackSequence)
                {
                    lastVisualAttackSequence = actions.AttackSequence;
                    punchPlayable.SetTime(0d);
                    shootPlayable.SetTime(0d);
                }

                locomotionPhase += horizontal * dt / 1.75f;
                if (locomotionPhase > 1000f) locomotionPhase -= 1000f;
                LoopPlayable(idlePlayable, idleClip, Time.timeAsDouble / Math.Max(0.02, idleClip.length));
                LoopPlayable(walkPlayable, walkClip, locomotionPhase);
                LoopPlayable(runPlayable, runClip, locomotionPhase);
                LoopPlayable(crouchWalkPlayable, crouchWalkClip, locomotionPhase);

            }

            // In-place upper-arm punch pulse. Only the animation skeleton is
            // affected; hit registration lives in AarisBattleActions.
            if (punchArm != null && actions != null && punchClip == idleClip)
            {
                float t = (Time.time - actions.LastPunchTime) / 0.36f;
                if (t >= 0f && t <= 1f)
                    punchArm.localRotation *= Quaternion.Euler(
                        -72f * Mathf.Sin(t * Mathf.PI), 0f, 0f);
            }
        }

        private void OnDestroy()
        {
            if (graph.IsValid()) graph.Destroy();
            if (runtimeSkin != null) Destroy(runtimeSkin);
            if (placeholderRenderers != null)
                foreach (var renderer in placeholderRenderers)
                    if (renderer != null) renderer.enabled = true;
        }
    }
}
