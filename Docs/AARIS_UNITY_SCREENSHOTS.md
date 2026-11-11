# Unity Editor screenshots via GitHub Actions

The active Codespace hosts the **real Unity Editor**; an Actions runner only captures
its visible window and packages the resulting JPEG as an artifact. It does not
launch a second Editor, build an APK, alter native scenes, or replace Cloudflare
Turbo. Prefer the private Cloudflare GUI bridge for ordinary real-time inspection.

## Owner-only request

Comment on the existing Issue #77 using exactly:

```text
AARIS SCREENSHOT aaris-ai-ubuntu-minimal-4qr6v94w9rwvhjgp6
```

Or manually run the **Aaris Unity Screenshot (Codespace)** workflow from the
Actions tab, entering the exact name of the active Codespace. When rotating to
a new Codespace, use its **new exact name**.

The dedicated workflow only accepts comments on Issue #77 made by GitHub
account ID 353065137 (sundamunda289-art). It uses the repository's existing
`CODESPACE_PAT` Actions secret to connect to that account's running Codespace.
A missing secret or offline/inaccessible Codespace produces an explicit error.
Never paste a PAT into issue comments or chat.

The runner selects the **visible Unity Editor window** via X11, captures a JPEG
without the full desktop, checks its MIME type and uploads it using
`actions/upload-artifact@v4`. The image bytes are **never printed in public
Actions logs or GitHub Issues**.

Open the latest matching Actions run and download the
`AarisUnityScreenshot-<run_id>` artifact ZIP. Retention is **1 day**; it is
not a perpetual link. The user can share that JPEG in ChatGPT if needed.
Because this repository is public, avoid leaving credentials, personal
information, or other sensitive material visible within Unity.

This is a screenshot of the current GUI, not proof of device FPS or a successful
Play Mode session. The workflow does not turn on Play Mode or modify assets.
If Unity is not open on `:99` or the Codespace SSH permission is insufficient,
the capture fails safely and does not synthesize a screenshot.

## Safe fallback

Use `python3 ~/.local/share/aaris-turbo/gui.py look --fast` through the
authenticated Cloudflare Durable Object queue and read the completed screenshot
chunks privately. The existing bridge returns a grid overlay for interaction.
Do not publish these private screen chunks as source, comments or public logs.
