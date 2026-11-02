using UnityEngine;

namespace Aaris.MapReview
{
    /// <summary>Standalone map review camera, with keyboard/mouse and multi-touch controls.</summary>
    [DisallowMultipleComponent, RequireComponent(typeof(Camera))]
    public sealed class AarisMapExplorer : MonoBehaviour
    {
        [SerializeField, Min(1f)] private float moveSpeed = 45f;
        [SerializeField, Min(1f)] private float fastMultiplier = 4f;
        [SerializeField] private float mouseLookSensitivity = 0.15f;
        [SerializeField] private float touchLookSensitivity = 0.10f;
        [SerializeField] private float terrainClearance = 2.5f;
        [SerializeField] private float mapBoundary = 980f;
        [SerializeField] private float maximumAltitude = 1800f;
        [SerializeField] private bool showHelp = true;
        private Vector3 homePosition;
        private Quaternion homeRotation;
        private float yaw, pitch;
        private Vector3 lastMouse;
        private int lookFinger = -1;
        private bool fast, previousSimulateMouse;
        private Rect forward, backward, left, right, rise, descend, zoomIn, zoomOut, home, overview, speed, help;
        private float uiScale;
        private GUIStyle buttonStyle, textStyle, panelStyle;

        private void Awake()
        {
            homePosition = transform.position;
            homeRotation = transform.rotation;
            ReadAngles();
            lastMouse = Input.mousePosition;
            previousSimulateMouse = Input.simulateMouseWithTouches;
            Input.simulateMouseWithTouches = false;
        }

        private void OnDestroy() { Input.simulateMouseWithTouches = previousSimulateMouse; }
        private void OnApplicationFocus(bool focus) { lookFinger = -1; lastMouse = Input.mousePosition; }
        private void ReadAngles()
        {
            yaw = transform.eulerAngles.y;
            pitch = Mathf.DeltaAngle(0f, transform.eulerAngles.x);
        }
        private Vector3 ForwardOnGround => Quaternion.Euler(0f, yaw, 0f) * Vector3.forward;
        private Vector3 RightOnGround => Quaternion.Euler(0f, yaw, 0f) * Vector3.right;

        private void Layout()
        {
            uiScale = Mathf.Clamp(Mathf.Min(Screen.width / 960f, Screen.height / 540f), 0.5f, 3f);
            Rect safe = Screen.safeArea;
            float x = safe.xMin / uiScale + 14f;
            float y = (Screen.height - safe.yMin) / uiScale - 14f;
            float end = safe.xMax / uiScale - 14f;
            float top = (Screen.height - safe.yMax) / uiScale + 12f;
            const float b = 58f, gap = 6f;
            forward = new Rect(x + b + gap, y - 2 * b - gap, b, b);
            backward = new Rect(x + b + gap, y - b, b, b);
            left = new Rect(x, y - b, b, b);
            right = new Rect(x + 2 * (b + gap), y - b, b, b);
            rise = new Rect(end - b, y - 2 * b - gap, b, b);
            descend = new Rect(end - b, y - b, b, b);
            zoomIn = new Rect(end - 2 * b - gap, y - 2 * b - gap, b, b);
            zoomOut = new Rect(end - 2 * b - gap, y - b, b, b);
            home = new Rect(x, top, 86f, 38f);
            overview = new Rect(x + 92f, top, 100f, 38f);
            speed = new Rect(x + 198f, top, 100f, 38f);
            help = new Rect(end - 66f, top, 66f, 38f);
        }
        private Vector2 ScreenToGUI(Vector2 p) => new Vector2(p.x / uiScale, (Screen.height - p.y) / uiScale);
        private bool OverControls(Vector2 screen)
        {
            Vector2 p = ScreenToGUI(screen);
            return forward.Contains(p) || backward.Contains(p) || left.Contains(p) || right.Contains(p)
                || rise.Contains(p) || descend.Contains(p) || zoomIn.Contains(p) || zoomOut.Contains(p)
                || home.Contains(p) || overview.Contains(p) || speed.Contains(p) || help.Contains(p);
        }
        private void ActivateButton(Vector2 screen)
        {
            Vector2 p = ScreenToGUI(screen);
            if (home.Contains(p)) ResetView();
            else if (overview.Contains(p)) Overview();
            else if (speed.Contains(p)) fast = !fast;
            else if (help.Contains(p)) showHelp = !showHelp;
        }
        private void ReadHeldButton(Vector2 screen, ref Vector3 movement, ref float zoom)
        {
            Vector2 p = ScreenToGUI(screen);
            if (forward.Contains(p)) movement += ForwardOnGround;
            if (backward.Contains(p)) movement -= ForwardOnGround;
            if (right.Contains(p)) movement += RightOnGround;
            if (left.Contains(p)) movement -= RightOnGround;
            if (rise.Contains(p)) movement += Vector3.up;
            if (descend.Contains(p)) movement -= Vector3.up;
            if (zoomIn.Contains(p)) zoom += 1f;
            if (zoomOut.Contains(p)) zoom -= 1f;
        }
        private void Look(Vector2 delta, float sensitivity)
        {
            yaw += delta.x * sensitivity;
            pitch = Mathf.Clamp(pitch - delta.y * sensitivity, -85f, 85f);
            transform.rotation = Quaternion.Euler(pitch, yaw, 0f);
        }
        private void Update()
        {
            Layout();
            float dt = Mathf.Min(Time.unscaledDeltaTime, 0.05f);
            Vector3 movement = Vector3.zero;
            float zoom = 0f;
            if (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow)) movement += ForwardOnGround;
            if (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow)) movement -= ForwardOnGround;
            if (Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow)) movement += RightOnGround;
            if (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow)) movement -= RightOnGround;
            if (Input.GetKey(KeyCode.E)) movement += Vector3.up;
            if (Input.GetKey(KeyCode.Q)) movement -= Vector3.up;
            if (Input.GetKeyDown(KeyCode.F)) ResetView();
            if (Input.GetKeyDown(KeyCode.O)) Overview();
            if (Input.GetKeyDown(KeyCode.H)) showHelp = !showHelp;

            bool pinching = false;
            if (Input.touchCount >= 2)
            {
                Touch a = Input.GetTouch(0), b = Input.GetTouch(1);
                if (!OverControls(a.position) && !OverControls(b.position)
                    && a.phase != TouchPhase.Began && b.phase != TouchPhase.Began
                    && a.phase != TouchPhase.Ended && b.phase != TouchPhase.Ended
                    && a.phase != TouchPhase.Canceled && b.phase != TouchPhase.Canceled)
                {
                    float before = ((a.position - a.deltaPosition) - (b.position - b.deltaPosition)).magnitude;
                    float change = Vector2.Distance(a.position, b.position) - before;
                    Dolly(change / Mathf.Max(Screen.width, 1) * 250f);
                    pinching = true;
                    lookFinger = -1;
                }
            }
            for (int i = 0; i < Input.touchCount; i++)
            {
                Touch t = Input.GetTouch(i);
                if (t.phase == TouchPhase.Ended || t.phase == TouchPhase.Canceled)
                {
                    if (lookFinger == t.fingerId) lookFinger = -1;
                    continue;
                }
                if (t.phase == TouchPhase.Began) ActivateButton(t.position);
                if (!pinching && lookFinger == t.fingerId)
                {
                    if (t.phase == TouchPhase.Moved) Look(t.deltaPosition / uiScale, touchLookSensitivity);
                    continue;
                }
                if (OverControls(t.position)) ReadHeldButton(t.position, ref movement, ref zoom);
                else if (!pinching)
                {
                    if (lookFinger == -1) lookFinger = t.fingerId;
                    if (lookFinger == t.fingerId && t.phase == TouchPhase.Moved)
                        Look(t.deltaPosition / uiScale, touchLookSensitivity);
                }
            }
            if (Input.touchCount == 0)
            {
                lookFinger = -1;
                Vector3 mouse = Input.mousePosition;
                Vector2 delta = mouse - lastMouse;
                if (Input.GetMouseButton(1) && !OverControls(mouse)) Look(delta, mouseLookSensitivity);
                if (Input.GetMouseButton(2) && !OverControls(mouse))
                    transform.position += (-RightOnGround * delta.x - ForwardOnGround * delta.y) * Mathf.Max(0.05f, GroundDistance() * 0.0015f);
                if (Input.GetMouseButtonDown(0)) ActivateButton(mouse);
                if (Input.GetMouseButton(0)) ReadHeldButton(mouse, ref movement, ref zoom);
                if (!OverControls(mouse)) Dolly(Input.mouseScrollDelta.y * 3f);
                lastMouse = mouse;
            }
            float multiplier = fast || Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift) ? fastMultiplier : 1f;
            transform.position += Vector3.ClampMagnitude(movement, 1f) * (moveSpeed * multiplier * dt);
            if (zoom != 0f) Dolly(zoom * dt * 5f);
            ConstrainPosition();
        }
        private float GroundHeight(Vector3 p)
        {
            float ground = -38.07552f;
            foreach (Terrain t in Terrain.activeTerrains)
            {
                if (t.terrainData == null) continue;
                Vector3 origin = t.transform.position, size = t.terrainData.size;
                if (p.x >= origin.x && p.x <= origin.x + size.x && p.z >= origin.z && p.z <= origin.z + size.z)
                    ground = Mathf.Max(ground, t.SampleHeight(p) + origin.y);
            }
            return ground;
        }
        private float GroundDistance() => Mathf.Max(5f, transform.position.y - GroundHeight(transform.position));
        private void Dolly(float steps)
        {
            transform.position += transform.forward * (steps * Mathf.Clamp(GroundDistance() * 0.075f, 2f, 70f));
        }
        private void ConstrainPosition()
        {
            Vector3 p = transform.position;
            p.x = Mathf.Clamp(p.x, -mapBoundary, mapBoundary);
            p.z = Mathf.Clamp(p.z, -mapBoundary, mapBoundary);
            p.y = Mathf.Clamp(p.y, GroundHeight(p) + terrainClearance, maximumAltitude);
            transform.position = p;
        }
        public void ResetView()
        {
            transform.SetPositionAndRotation(homePosition, homeRotation);
            ReadAngles(); lookFinger = -1;
        }
        public void Overview()
        {
            transform.SetPositionAndRotation(new Vector3(0f, 1780f, 0f), Quaternion.Euler(89f, 0f, 0f));
            ReadAngles(); lookFinger = -1;
        }
        private void OnGUI()
        {
            Layout();
            Matrix4x4 old = GUI.matrix;
            GUI.matrix = Matrix4x4.Scale(new Vector3(uiScale, uiScale, 1f));
            if (buttonStyle == null)
            {
                buttonStyle = new GUIStyle(GUI.skin.button) { fontSize = 17, alignment = TextAnchor.MiddleCenter };
                textStyle = new GUIStyle(GUI.skin.label) { fontSize = 14, wordWrap = true };
                panelStyle = new GUIStyle(GUI.skin.box);
            }
            GUI.Box(forward, "Fwd", buttonStyle); GUI.Box(backward, "Back", buttonStyle);
            GUI.Box(left, "Left", buttonStyle); GUI.Box(right, "Right", buttonStyle);
            GUI.Box(rise, "Up", buttonStyle); GUI.Box(descend, "Down", buttonStyle);
            GUI.Box(zoomIn, "+", buttonStyle); GUI.Box(zoomOut, "-", buttonStyle);
            GUI.Box(home, "Home", buttonStyle);
            GUI.Box(overview, "Overview", buttonStyle);
            GUI.Box(speed, fast ? "Speed: 4x" : "Speed: 1x", buttonStyle);
            GUI.Box(help, "Help", buttonStyle);
            if (showHelp)
            {
                float width = Mathf.Min(600f, Screen.width / uiScale - 32f);
                Rect panel = new Rect(home.x, home.yMax + 8f, width, 58f);
                GUI.Box(panel, "", panelStyle);
                GUI.Label(new Rect(panel.x + 10f, panel.y + 5f, panel.width - 20f, panel.height - 10f),
                    Application.isMobilePlatform
                    ? "Hold arrows to move. Drag empty space to look. Pinch or + / - to zoom. Up / Down change height."
                    : "WASD / arrows: move | Q / E: height | Shift: fast | Right-drag: look | Middle-drag: pan | Wheel: zoom | F: home | O: overview", textStyle);
            }
            GUI.matrix = old;
        }
    }
}
