using UnityEngine;

namespace Aaris.MapReview
{
    /// <summary>
    /// One physics authority per vehicle, driven by four input intents.
    /// Real WheelColliders supply traction, suspension, braking and steering;
    /// never write Rigidbody.linearVelocity to fake acceleration.
    /// </summary>
    [DisallowMultipleComponent, RequireComponent(typeof(Rigidbody))]
    [DefaultExecutionOrder(-40)]
    public sealed class AarisVehicleMotor : MonoBehaviour
    {
        private const float WheelRadius = 0.39f;
        private readonly WheelCollider[] wheels = new WheelCollider[4];
        private Rigidbody body;
        private AarisVehicleSession driver;
        private float forward, steering, smoothSteer;
        private float topSpeed;
        private float brakeTorque = 3200f;
        private float lastDriven;
        public string VehicleId { get; private set; }
        public bool IsOccupied => driver != null;
        public bool CanPark => !IsOccupied && body != null &&
            body.linearVelocity.sqrMagnitude < 0.7f &&
            body.angularVelocity.sqrMagnitude < .25f;
        public float SpeedMetresPerSecond => body != null
            ? Vector3.Dot(body.linearVelocity, transform.forward) : 0f;

        public void Configure(string id, float maxSpeedMetres, float kilograms)
        {
            VehicleId = id;
            topSpeed = Mathf.Clamp(maxSpeedMetres, 16f, 28f);
            body = GetComponent<Rigidbody>();
            body.mass = Mathf.Clamp(kilograms, 850f, 2300f);
            body.interpolation = RigidbodyInterpolation.Interpolate;
            body.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            body.linearDamping = .12f;
            body.angularDamping = .65f;
            body.maxAngularVelocity = 3f;
            // A low but plausible COM improves stability; it does not
            // guarantee that a flipped car will right itself.
            body.centerOfMass = new Vector3(0f, -.27f, 0f);
            var shell = GetComponent<BoxCollider>();
            if (shell == null) shell = gameObject.AddComponent<BoxCollider>();
            shell.center = new Vector3(0f, .52f, 0f);
            shell.size = new Vector3(1.85f, 1.03f, 3.85f);
            CreateWheel(0, -.84f, 1.38f);
            CreateWheel(1, .84f, 1.38f);
            CreateWheel(2, -.84f, -1.38f);
            CreateWheel(3, .84f, -1.38f);
        }

        private void CreateWheel(int index, float x, float z)
        {
            var anchor = new GameObject("PhysicsWheel_" + index);
            anchor.transform.SetParent(transform, false);
            anchor.transform.localPosition = new Vector3(x, -.10f, z);
            var wheel = anchor.AddComponent<WheelCollider>();
            wheel.radius = WheelRadius;
            wheel.mass = 24f;
            wheel.suspensionDistance = .24f;
            wheel.wheelDampingRate = .32f;
            wheel.suspensionSpring = new JointSpring
            {
                spring = 32000f, damper = 4200f, targetPosition = .5f
            };
            WheelFrictionCurve forwardGrip = wheel.forwardFriction;
            forwardGrip.extremumSlip = .36f;
            forwardGrip.extremumValue = 1.2f;
            forwardGrip.asymptoteSlip = .83f;
            forwardGrip.asymptoteValue = .83f;
            forwardGrip.stiffness = 1.15f;
            wheel.forwardFriction = forwardGrip;
            WheelFrictionCurve sideGrip = wheel.sidewaysFriction;
            sideGrip.extremumSlip = .28f;
            sideGrip.extremumValue = 1.2f;
            sideGrip.asymptoteSlip = .7f;
            sideGrip.asymptoteValue = .85f;
            sideGrip.stiffness = 1.35f;
            wheel.sidewaysFriction = sideGrip;
            wheels[index] = wheel;
        }

        public bool TryTakeDriver(AarisVehicleSession session)
        {
            if (session == null || IsOccupied || body == null ||
                body.linearVelocity.magnitude > 2f) return false;
            driver = session;
            forward = steering = smoothSteer = 0f;
            lastDriven = Time.time;
            return true;
        }

        public void SetInput(float forwardAxis, float steerAxis)
        {
            if (driver == null) return;
            forward = Mathf.Clamp(forwardAxis, -1f, 1f);
            steering = Mathf.Clamp(steerAxis, -1f, 1f);
            lastDriven = Time.time;
        }

        public void ReleaseDriver(AarisVehicleSession session)
        {
            if (session != driver) return;
            driver = null;
            forward = steering = 0f;
            for (int i = 0; i < wheels.Length; i++)
                if (wheels[i] != null)
                {
                    wheels[i].motorTorque = 0f;
                    wheels[i].brakeTorque = 420f;
                }
        }

        private void FixedUpdate()
        {
            if (body == null || wheels[0] == null) return;
            float speed = SpeedMetresPerSecond;
            float speedAbs = Mathf.Abs(speed);
            float throttle = driver != null ? forward : 0f;
            float turn = driver != null ? steering : 0f;

            // Four progressive torque bands are speed-derived, not arbitrary
            // teleporting 9/16/22/28 m/s velocities after an input timer.
            float torque = speedAbs < 7f ? 1500f : speedAbs < 14f ? 1180f :
                speedAbs < 21f ? 850f : 580f;
            float drive = 0f, brake = 0f;
            if (throttle > .08f)
            {
                if (speed < -1f) brake = brakeTorque * throttle;
                else if (speed < topSpeed) drive = torque * throttle;
            }
            else if (throttle < -.08f)
            {
                if (speed > 1f) brake = brakeTorque * -throttle;
                else if (speed > -7f) drive = -torque * .48f * -throttle;
            }
            else
            {
                // Realistic rolling drag; touching neither arrow coasts
                // rather than stopping instantly in mid-air.
                brake = driver == null ? 600f : 155f;
            }
            // Downhill speed control: apply brake instead of directly
            // overwriting velocity, which would ignore collision impulses.
            if (speed > topSpeed + .6f || speed < -8f)
                brake = Mathf.Max(brake, 1100f);
            for (int i = 0; i < wheels.Length; i++)
            {
                wheels[i].motorTorque = i >= 2 ? drive * .5f : 0f;
                wheels[i].brakeTorque = brake;
            }
            // Gradually reduce steering angle at speed so 100km/h inputs
            // cannot instantaneously rotate a multi-ton vehicle by 70°/s.
            float maxAngle = Mathf.Lerp(32f, 10f, Mathf.InverseLerp(0f, 24f, speedAbs));
            float target = turn * maxAngle;
            smoothSteer = Mathf.MoveTowards(smoothSteer, target, 125f * Time.fixedDeltaTime);
            wheels[0].steerAngle = wheels[1].steerAngle = smoothSteer;

            // Mild aero downforce supports handling but cannot defeat walls.
            if (speedAbs > 6f)
                body.AddForce(-transform.up * Mathf.Min(18000f, 20f * speedAbs * speedAbs),
                    ForceMode.Force);
        }

        private void OnDisable()
        {
            forward = steering = 0f;
        }
    }
}
