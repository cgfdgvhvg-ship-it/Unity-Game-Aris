using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Aaris.MapReview
{
    /// <summary>
    /// Exactly five transparent mobile action buttons, laid out in safe-area
    /// coordinates. Input and presentation are decoupled from movement/physics.
    /// Created once at scene load; no prefab, Inspector setup or online images.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class AarisBattleHUD : MonoBehaviour
    {
        internal enum Action { Fire, Jump, Crouch, Prone, Sprint }

        private static AarisBattleHUD instance;
        private readonly List<AarisHudButton> buttons = new List<AarisHudButton>(5);
        private AarisBattleActions actions;
        private AarisThirdPersonPlayer player;
        private RectTransform safeRoot;
        private Vector2 previousScreen;
        private Rect previousSafeArea;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Boot()
        {
            var existing = FindFirstObjectByType<AarisThirdPersonPlayer>();
            if (existing == null || FindFirstObjectByType<AarisBattleHUD>() != null) return;

            var state = existing.GetComponent<AarisBattleActions>();
            if (state == null) state = existing.gameObject.AddComponent<AarisBattleActions>();

            var hudObject = new GameObject("Aaris Mobile Battle HUD");
            var hud = hudObject.AddComponent<AarisBattleHUD>();
            hud.Build(existing, state);
        }

        private static void CreateEventSystemIfMissing()
        {
            if (FindFirstObjectByType<EventSystem>() != null) return;
            var es = new GameObject("Aaris UI Event System");
            es.AddComponent<EventSystem>();
            // The saved project explicitly uses Unity's classic Input Manager.
            es.AddComponent<StandaloneInputModule>();
        }

        private void Build(AarisThirdPersonPlayer motor, AarisBattleActions state)
        {
            if (instance != null && instance != this) { Destroy(gameObject); return; }
            instance = this;
            actions = state;
            player = motor;
            CreateEventSystemIfMissing();

            var canvasObj = new GameObject("Mobile Battle Canvas", typeof(RectTransform),
                typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            canvasObj.transform.SetParent(transform, false);
            var canvas = canvasObj.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 180;
            var scaler = canvasObj.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(960f, 540f);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.matchWidthOrHeight = 0.5f;

            var safeAreaObject = new GameObject("Safe Area", typeof(RectTransform));
            safeAreaObject.transform.SetParent(canvasObj.transform, false);
            safeRoot = safeAreaObject.GetComponent<RectTransform>();
            safeRoot.offsetMin = Vector2.zero;
            safeRoot.offsetMax = Vector2.zero;

            // Positions are local to the display cutout-safe rectangle. The
            // reference style uses a left sprint and right clustered actions.
            Add(Action.Sprint, new Vector2(0f, 0.68f), new Vector2(225f, 0f), 112f);
            Add(Action.Fire, new Vector2(1f, 0.49f), new Vector2(-253f, 0f), 132f);
            Add(Action.Jump, new Vector2(1f, 0.49f), new Vector2(-83f, 0f), 108f);
            Add(Action.Crouch, new Vector2(1f, 0.14f), new Vector2(-87f, 0f), 112f);
            Add(Action.Prone, new Vector2(1f, 0.12f), new Vector2(-227f, 0f), 106f);

            UpdateSafeArea(true);
            Debug.Log("Aaris HUD: five original offline action buttons enabled: Fire/Punch, Jump, Crouch, Prone, Sprint.");
        }

        private void Add(Action action, Vector2 anchor, Vector2 offset, float diameter)
        {
            var item = new GameObject("HUD " + action, typeof(RectTransform),
                typeof(Image), typeof(AarisHudButton));
            item.transform.SetParent(safeRoot, false);
            var rect = item.GetComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = anchor;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = offset;
            rect.sizeDelta = new Vector2(diameter, diameter);

            var background = item.GetComponent<Image>();
            background.sprite = AarisHudGlyphs.Ring;
            background.type = Image.Type.Simple;
            background.preserveAspect = true;
            background.raycastTarget = true;

            var iconObj = new GameObject("White " + action + " Silhouette",
                typeof(RectTransform), typeof(Image));
            iconObj.transform.SetParent(item.transform, false);
            var iconRect = iconObj.GetComponent<RectTransform>();
            iconRect.anchorMin = Vector2.zero;
            iconRect.anchorMax = Vector2.one;
            iconRect.offsetMin = new Vector2(diameter * 0.23f, diameter * 0.23f);
            iconRect.offsetMax = new Vector2(-diameter * 0.23f, -diameter * 0.23f);
            var icon = iconObj.GetComponent<Image>();
            icon.sprite = AarisHudGlyphs.Get((AarisHudGlyphs.Glyph)action);
            icon.preserveAspect = true;
            icon.raycastTarget = false;
            icon.color = new Color(1f, 1f, 1f, 0.97f);

            var button = item.GetComponent<AarisHudButton>();
            button.Configure(this, action, background);
            buttons.Add(button);
        }

        private void UpdateSafeArea(bool force)
        {
            var safe = Screen.safeArea;
            var resolution = new Vector2(Screen.width, Screen.height);
            if (!force && previousScreen == resolution && previousSafeArea == safe) return;
            previousScreen = resolution;
            previousSafeArea = safe;
            if (Screen.width <= 0 || Screen.height <= 0) return;
            safeRoot.anchorMin = new Vector2(safe.xMin / Screen.width, safe.yMin / Screen.height);
            safeRoot.anchorMax = new Vector2(safe.xMax / Screen.width, safe.yMax / Screen.height);
            safeRoot.offsetMin = safeRoot.offsetMax = Vector2.zero;
        }

        private void LateUpdate()
        {
            UpdateSafeArea(false);
            foreach (var button in buttons)
            {
                bool selected = button.Kind == Action.Sprint && player != null && player.IsAutoSprinting ||
                    button.Kind == Action.Fire && actions != null && actions.FireHeld ||
                    button.Kind == Action.Crouch && actions != null &&
                        actions.Stance == AarisBattleActions.PlayerStance.Crouching ||
                    button.Kind == Action.Prone && actions != null &&
                        actions.Stance == AarisBattleActions.PlayerStance.Prone;
                button.SetSelected(selected);
            }
        }

        internal void Down(Action action)
        {
            if (actions == null || player == null) return;
            switch (action)
            {
                case Action.Fire: actions.SetFireHeld(true); break;
                case Action.Jump: player.RequestJump(); break;
                case Action.Crouch: actions.ToggleCrouch(); player.CancelAutoSprint(); break;
                case Action.Prone: actions.ToggleProne(); player.CancelAutoSprint(); break;
                case Action.Sprint: player.ToggleAutoSprint(); break;
            }
        }

        internal void Up(Action action)
        {
            if (action == Action.Fire && actions != null) actions.SetFireHeld(false);
        }

        /// <summary>Use on touch BEGAN to keep HUD fingers out of the camera joystick.</summary>
        public static bool CapturesScreenPosition(Vector2 screenPosition)
        {
            if (instance == null || !instance.isActiveAndEnabled) return false;
            foreach (var b in instance.buttons)
                if (b != null && b.IsWithin(screenPosition)) return true;
            return false;
        }

        private void OnApplicationPause(bool paused)
        {
            if (paused && actions != null) actions.SetFireHeld(false);
        }

        private void OnDisable()
        {
            if (actions != null) actions.SetFireHeld(false);
            if (instance == this) instance = null;
        }
    }

    /// <summary>
    /// Touch lifecycle is tracked per pointer. Hold-fire is released by either
    /// pointer up, a disabled button, scene unload or application pause.
    /// </summary>
    internal sealed class AarisHudButton : MonoBehaviour,
        IPointerDownHandler, IPointerUpHandler, ICancelHandler
    {
        private AarisBattleHUD owner;
        private AarisBattleHUD.Action kind;
        private Image background;
        private RectTransform bounds;
        private int activePointer = int.MinValue;
        private static readonly Color Normal = Color.white;
        private static readonly Color Selected = new Color(0.57f, 0.83f, 1f, 1f);

        internal AarisBattleHUD.Action Kind => kind;

        internal void Configure(AarisBattleHUD controller, AarisBattleHUD.Action action, Image image)
        {
            owner = controller;
            kind = action;
            background = image;
            bounds = transform as RectTransform;
        }

        internal bool IsWithin(Vector2 point) =>
            bounds != null && RectTransformUtility.RectangleContainsScreenPoint(bounds, point, null);

        internal void SetSelected(bool selected)
        {
            if (background != null) background.color = selected ? Selected : Normal;
        }

        public void OnPointerDown(PointerEventData eventData)
        {
            if (owner == null || activePointer != int.MinValue) return;
            activePointer = eventData.pointerId;
            owner.Down(kind);
        }

        public void OnPointerUp(PointerEventData eventData)
        {
            if (owner == null || activePointer != eventData.pointerId) return;
            activePointer = int.MinValue;
            owner.Up(kind);
        }

        public void OnCancel(BaseEventData eventData)
        {
            Release();
        }

        private void Release()
        {
            if (activePointer == int.MinValue) return;
            activePointer = int.MinValue;
            if (owner != null) owner.Up(kind);
        }

        private void OnDisable() => Release();
    }
}
