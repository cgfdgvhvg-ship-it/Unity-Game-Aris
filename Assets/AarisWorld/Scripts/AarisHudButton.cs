using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Aaris.MapReview
{
    /// <summary>
    /// Touch lifecycle is tracked per pointer. Hold-fire is released by either
    /// pointer up, a disabled button, scene unload or application pause.
    /// </summary>
    public sealed class AarisHudButton : MonoBehaviour,
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
