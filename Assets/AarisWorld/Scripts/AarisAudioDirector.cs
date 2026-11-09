using System;
using System.Collections.Generic;
using UnityEngine;

namespace Aaris.MapReview
{
    /// <summary>
    /// Small, offline, event-aware 3D mixer for the saved player.
    /// Uses the EXISTING movement, drop, combat and vehicle authorities.
    /// Missing clips are silent; no downloads, Update-time Resources.Load,
    /// duplicate controllers, networking or per-shot GameObject allocations.
    /// </summary>
    [DisallowMultipleComponent, DefaultExecutionOrder(900)]
    public sealed class AarisAudioDirector : MonoBehaviour
    {
        private const int VoiceCount = 12;
        private static AarisAudioDirector instance;
        private static readonly string[] Keys =
        {
            "plane_engine_loop", "jump_whoosh", "wind_rush_loop",
            "parachute_open", "parachute_land", "step_dirt", "step_road",
            "step_water", "jump_start", "land_thud", "smg_shot",
            "ar_shot", "battle_rifle_shot", "sniper_shot", "shotgun_shot",
            "bolt_reload", "shell_drop", "bullet_impact", "punch_hit",
            "grenade_pin", "grenade_throw", "grenade_bounce", "grenade_boom",
            "car_start", "car_engine_loop", "tire_skid", "car_crash"
        };
        private readonly Dictionary<string, AudioClip> clips = new Dictionary<string, AudioClip>(32);
        private readonly AudioSource[] voices = new AudioSource[VoiceCount];
        private AarisThirdPersonPlayer player;
        private AarisBattleActions combat;
        private AarisVehicleSession vehicle;
        private AarisOfflineDrop drop;
        private CharacterController capsule;
        private AudioSource planeLoop, windLoop, engineLoop;
        private AarisOfflineDrop.DropPhase lastDropPhase;
        private bool hasDropPhase, wasDriving;
        private float previousY, previousJump = -10f, previousLand = -10f;
        private float stepDistance, lastSkidAt = -10f, lastCrashAt = -10f;
        private int nextVoice;
        private Vector3 previousPosition;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            var savedPlayer = FindFirstObjectByType<AarisThirdPersonPlayer>();
            if (savedPlayer != null && savedPlayer.GetComponent<AarisAudioDirector>() == null)
                savedPlayer.gameObject.AddComponent<AarisAudioDirector>();
        }

        private static AudioSource MakeSource(Transform parent, string name)
        {
            var obj = new GameObject(name);
            obj.transform.SetParent(parent, false);
            var source = obj.AddComponent<AudioSource>();
            source.playOnAwake = false;
            source.spatialBlend = 1f;
            source.rolloffMode = AudioRolloffMode.Logarithmic;
            source.minDistance = 1.5f;
            source.maxDistance = 65f;
            source.dopplerLevel = 0f;
            source.priority = 180;
            return source;
        }

        private void Awake()
        {
            if (instance != null && instance != this) { enabled = false; return; }
            instance = this;
            player = GetComponent<AarisThirdPersonPlayer>();
            combat = GetComponent<AarisBattleActions>();
            vehicle = GetComponent<AarisVehicleSession>();
            drop = GetComponent<AarisOfflineDrop>();
            capsule = GetComponent<CharacterController>();
            foreach (string key in Keys)
                clips[key] = Resources.Load<AudioClip>("SFX/" + key);
            for (int i = 0; i < voices.Length; i++)
                voices[i] = MakeSource(transform, "Aaris SFX Voice " + i);
            planeLoop = MakeSource(transform, "Plane Engine Loop");
            windLoop = MakeSource(transform, "Drop Wind Loop");
            engineLoop = MakeSource(transform, "Vehicle Engine Loop");
            planeLoop.loop = windLoop.loop = engineLoop.loop = true;
            previousY = transform.position.y;
            previousPosition = transform.position;
        }

        private AudioClip GetClip(string name)
        {
            return clips.TryGetValue(name, out AudioClip value) ? value : null;
        }

        private void OneShot(string name, Vector3 point, float volume = 1f, float pitch = 1f)
        {
            AudioClip clip = GetClip(name);
            if (clip == null) return;
            AudioSource voice = voices[nextVoice];
            nextVoice = (nextVoice + 1) % voices.Length;
            if (voice.isPlaying) voice.Stop();
            voice.transform.position = point;
            voice.pitch = Mathf.Clamp(pitch, 0.75f, 1.3f);
            voice.PlayOneShot(clip, Mathf.Clamp01(volume));
        }

        /// <summary>Only successful weapon shots call this, never a held Fire button.</summary>
        public static void GunShot(string category, string id, Vector3 position)
        {
            if (instance == null) return;
            string sound = category == "SMG" ? "smg_shot" :
                category == "Sniper" ? "sniper_shot" :
                category == "Shotgun" ? "shotgun_shot" :
                id == "BattleRifle" ? "battle_rifle_shot" : "ar_shot";
            instance.OneShot(sound, position, 0.85f, UnityEngine.Random.Range(0.97f, 1.035f));
        }

        public static void BulletImpact(Vector3 position)
        {
            if (instance != null) instance.OneShot("bullet_impact", position, 0.36f);
        }

        public static void Punch(Vector3 position)
        {
            if (instance != null) instance.OneShot("punch_hit", position, 0.65f);
        }

        public static void GrenadeThrow(Vector3 position)
        {
            if (instance == null) return;
            instance.OneShot("grenade_pin", position, 0.5f);
            instance.OneShot("grenade_throw", position, 0.65f);
        }

        public static void GrenadeBounce(Vector3 position, float speed)
        {
            if (instance != null && speed > 1.3f)
                instance.OneShot("grenade_bounce", position, Mathf.Clamp01(speed / 12f) * 0.65f);
        }

        public static void GrenadeExplosion(Vector3 position)
        {
            if (instance != null) instance.OneShot("grenade_boom", position, 1f);
        }

        public static void VehicleCrash(Vector3 position, float relativeSpeed)
        {
            if (instance == null || relativeSpeed < 4f ||
                Time.time - instance.lastCrashAt < 0.5f) return;
            instance.lastCrashAt = Time.time;
            instance.OneShot("car_crash", position, Mathf.Clamp01(relativeSpeed / 17f));
        }

        private static void BeginLoop(AudioSource source, AudioClip clip)
        {
            if (clip == null || source.clip == clip && source.isPlaying) return;
            source.clip = clip;
            source.volume = 0f;
            source.Play();
        }

        private static void AdjustLoop(AudioSource source, float volume, float pitch, float dt)
        {
            if (source == null || source.clip == null) return;
            source.volume = Mathf.MoveTowards(source.volume, volume, dt * 1.6f);
            source.pitch = Mathf.MoveTowards(source.pitch, pitch, dt * 1.8f);
            if (source.volume <= 0.001f && volume <= 0f && source.isPlaying)
                source.Stop();
        }

        private void LateUpdate()
        {
            float dt = Mathf.Clamp(Time.deltaTime, 0f, 0.15f);
            Vector3 pos = transform.position;
            float fallSpeed = dt > 0.001f
                ? Mathf.Clamp((previousY - pos.y) / dt, 0f, 65f) : 0f;
            previousY = pos.y;
            if (drop == null) drop = GetComponent<AarisOfflineDrop>();
            bool airborneDrop = drop != null && drop.enabled && !drop.HasLanded;
            bool driving = vehicle != null && vehicle.IsDriving;

            TickDrop(airborneDrop, fallSpeed, pos, dt);
            TickVehicle(driving, pos, dt);

            if (!airborneDrop && !driving && player != null && player.enabled)
                TickFootsteps(pos);
            else stepDistance = 0f;

            previousPosition = pos;
        }

        private void TickDrop(bool activeDrop, float fallSpeed, Vector3 pos, float dt)
        {
            if (!activeDrop)
            {
                AdjustLoop(planeLoop, 0f, 1f, dt);
                AdjustLoop(windLoop, 0f, 1f, dt);
                hasDropPhase = false;
                return;
            }
            var phase = drop.Phase;
            if (!hasDropPhase || phase != lastDropPhase)
            {
                if (phase == AarisOfflineDrop.DropPhase.InPlane)
                    BeginLoop(planeLoop, GetClip("plane_engine_loop"));
                else if (phase == AarisOfflineDrop.DropPhase.Freefall)
                {
                    OneShot("jump_whoosh", pos, 0.8f);
                    BeginLoop(windLoop, GetClip("wind_rush_loop"));
                }
                else if (phase == AarisOfflineDrop.DropPhase.Opening)
                    OneShot("parachute_open", pos, 0.9f);
                lastDropPhase = phase;
                hasDropPhase = true;
            }
            planeLoop.transform.position = pos;
            windLoop.transform.position = pos;
            float planeVol = phase == AarisOfflineDrop.DropPhase.InPlane ? 0.65f : 0f;
            float windVol = phase == AarisOfflineDrop.DropPhase.Freefall
                ? Mathf.Lerp(0.35f, 0.85f, fallSpeed / 54f) : 0.18f;
            float windPitch = phase == AarisOfflineDrop.DropPhase.Freefall
                ? Mathf.Lerp(0.9f, 1.25f, fallSpeed / 54f) : 0.85f;
            AdjustLoop(planeLoop, planeVol, 1f, dt);
            AdjustLoop(windLoop, windVol, windPitch, dt);
        }

        private void TickVehicle(bool driving, Vector3 pos, float dt)
        {
            var car = driving ? vehicle.DrivenCar : null;
            if (car == null)
            {
                if (wasDriving) wasDriving = false;
                AdjustLoop(engineLoop, 0f, 0.85f, dt);
                return;
            }
            if (!wasDriving)
            {
                OneShot("car_start", car.transform.position, 0.8f);
                BeginLoop(engineLoop, GetClip("car_engine_loop"));
                wasDriving = true;
            }
            float speed = Mathf.Abs(car.SpeedMetresPerSecond);
            float normalized = Mathf.Clamp01(speed /
                Mathf.Max(1f, car.TopSpeedMetresPerSecond));
            // Four smooth synthesized gear bands. Audio only: real physics
            // still owns RPM, WheelColliders, traction and torque.
            float gearPhase = Mathf.Repeat(normalized * 4f, 1f);
            float targetPitch = Mathf.Clamp(0.84f + normalized * 0.62f +
                gearPhase * 0.31f + Mathf.Abs(car.ThrottleInput) * 0.09f,
                0.8f, 2f);
            engineLoop.transform.position = car.transform.position;
            AdjustLoop(engineLoop, Mathf.Lerp(0.4f, 0.85f, normalized), targetPitch, dt);
            bool hardBrake = speed > 9f &&
                (car.ThrottleInput < -0.8f || car.LateralSlipMetresPerSecond > 3.5f);
            if (hardBrake && Time.time - lastSkidAt >= 0.95f)
            {
                lastSkidAt = Time.time;
                OneShot("tire_skid", car.transform.position, 0.56f);
            }
        }

        private void TickFootsteps(Vector3 pos)
        {
            if (capsule == null || !capsule.enabled) return;
            if (player.LastJumpStartedTime > previousJump &&
                Time.time - player.LastJumpStartedTime < 0.3f)
            {
                previousJump = player.LastJumpStartedTime;
                OneShot("jump_start", pos, 0.58f);
            }
            if (player.LastLandingTime > previousLand &&
                Time.time - player.LastLandingTime < 0.3f)
            {
                previousLand = player.LastLandingTime;
                OneShot("land_thud", pos, 0.72f);
            }
            if (!capsule.isGrounded) { stepDistance = 0f; return; }
            Vector3 delta = pos - previousPosition;
            delta.y = 0f;
            float moved = delta.magnitude;
            if (moved > 1.5f) { stepDistance = 0f; return; }
            if (moved < 0.008f) return;
            float speed = moved / Mathf.Max(Time.deltaTime, 0.001f);
            if (speed < 0.4f) return;
            float stride = combat != null && combat.Stance == AarisBattleActions.PlayerStance.Prone
                ? 0.65f : combat != null && combat.Stance == AarisBattleActions.PlayerStance.Crouching
                ? 0.92f : speed > 5.4f ? 1.65f : 1.25f;
            stepDistance += moved;
            if (stepDistance < stride) return;
            stepDistance %= stride;
            string surface = "step_dirt";
            if (Physics.Raycast(pos + Vector3.up * 0.4f, Vector3.down,
                    out RaycastHit hit, 2.0f, Physics.DefaultRaycastLayers,
                    QueryTriggerInteraction.Ignore))
            {
                string label = hit.collider.name.ToLowerInvariant();
                if (label.Contains("water") || label.Contains("river") ||
                    label.Contains("stream")) surface = "step_water";
                else if (label.Contains("road") || label.Contains("asphalt") ||
                    label.Contains("concrete") || label.Contains("floor") ||
                    label.Contains("bridge")) surface = "step_road";
            }
            OneShot(surface, pos, speed > 5.4f ? 0.61f : 0.48f,
                UnityEngine.Random.Range(0.92f, 1.08f));
        }

        private void OnDestroy()
        {
            if (instance == this) instance = null;
        }
    }
}
