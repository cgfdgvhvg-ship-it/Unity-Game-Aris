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
        private const float TargetHeightMetres = 1.78f;

        [SerializeField, Range(-180f, 180f)] private float modelYawOffset;
        [SerializeField, Range(0.1f, 0.8f)] private float blendResponseSeconds = 0.2f;
        [SerializeField] private float fullRunSpeed = 6.2f;

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

        private static AnimationClip FindClip(string file, string keyword)
        {
            var clips = Resources.LoadAll<AnimationClip>(KenneyClips + file);
            AnimationClip fallback = null;
            foreach (var clip in clips)
            {
                if (clip == null || clip.legacy || clip.length < 0.02f) continue;
                string label = clip.name.ToLowerInvariant();
                if (label.Contains("targeting") || label.Contains("pose")) continue;
                if (label.Contains(keyword)) return clip;
                if (fallback == null) fallback = clip;
            }
            return fallback;
        }

        private void SetupAnimations()
        {
            var idle = FindClip("idle", "idle");
            var run = FindClip("run", "run");
            var jump = FindClip("jump", "jump");
            if (idle == null || run == null) return;
            if (jump == null) jump = idle;

            graph = PlayableGraph.Create("AarisCharacterLocomotion");
            graph.SetTimeUpdateMode(DirectorUpdateMode.GameTime);
            mixer = AnimationMixerPlayable.Create(graph, 3);
            var idlePlayable = AnimationClipPlayable.Create(graph, idle);
            var runPlayable = AnimationClipPlayable.Create(graph, run);
            var jumpPlayable = AnimationClipPlayable.Create(graph, jump);
            idlePlayable.SetApplyFootIK(true);
            runPlayable.SetApplyFootIK(true);
            graph.Connect(idlePlayable, 0, mixer, 0);
            graph.Connect(runPlayable, 0, mixer, 1);
            graph.Connect(jumpPlayable, 0, mixer, 2);
            mixer.SetInputWeight(0, 1f);
            mixer.SetInputWeight(1, 0f);
            mixer.SetInputWeight(2, 0f);
            var output = AnimationPlayableOutput.Create(graph, "AarisCharacterOutput", animator);
            output.SetSourcePlayable(mixer);
            graphReady = true;
            graph.Play();
        }

        private void LateUpdate()
        {
            if (!graphReady || controller == null) return;
            Vector3 velocity = controller.velocity;
            float horizontal = new Vector2(velocity.x, velocity.z).magnitude;
            float speedRatio = Mathf.Clamp01(horizontal / Mathf.Max(0.1f, fullRunSpeed));
            float alpha = 1f - Mathf.Exp(-Time.deltaTime / Mathf.Max(0.04f, blendResponseSeconds));
            runBlend = Mathf.Lerp(runBlend, speedRatio, alpha);
            airborneBlend = Mathf.Lerp(airborneBlend, controller.isGrounded ? 0f : 1f, alpha);
            float groundWeight = 1f - airborneBlend;
            mixer.SetInputWeight(0, groundWeight * (1f - runBlend));
            mixer.SetInputWeight(1, groundWeight * runBlend);
            mixer.SetInputWeight(2, airborneBlend);
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
