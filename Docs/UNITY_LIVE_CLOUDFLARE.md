# Aaris Unity cloud live desktop (phone / GitHub Actions)

## Overview

The on-demand workflow .github/workflows/aaris-live-unity.yml starts a
GitHub-hosted Linux desktop (Xvfb + Openbox + x11vnc + noVNC), a local camera
control HTTP API, and a temporary Cloudflare Quick Tunnel. The URL is HTTPS,
changes on each run, and only works while the runner is alive.

Quick Tunnel email authentication restricts access using the --allowed-mail
flag and the approved UNITY_EMAIL GitHub Secret. The visitor receives an email
one-time PIN to unlock the desktop. Avoid publishing VNC without this gate.
The link alone does not grant access. Anyone controlling the allowed mailbox
can authenticate, so secure that email account.

## Start on phone
1. Ensure your UNITY_EMAIL Secret contains the mailbox that receives PINs.
2. Open https://github.com/sundamunda289-art/Unity-Game-Aris/actions/workflows/aaris-live-unity.yml
3. Tap Run workflow (main) and choose 15, 45 or 90 minutes.
4. Read the live-desktop job's "Start Cloudflare email-protected temporary
   tunnel" step log. It prints the temporary HTTPS URL and job summary.
5. Open the URL, authenticate with the email PIN, and use the web desktop.
6. Camera controls accept position X/Y/Z, yaw, pitch and distance. The Python
   API writes a bounded camera request locally. The Editor C# bridge updates
   Unity Scene view and renders the frame into ci-live-control/latest.png,
   downloadable from the live page if the real Unity Editor is running.
7. The last actual PNG is uploaded to the workflow's Actions artifact.

## Licensing / authentication

UNITY_LICENSE is OPTIONAL for starting the Linux desktop, but a valid
authorized ULF is needed for Unity Editor rendering. The existing Python
workflow remains fully independent of Unity activation.

Unity 6000.3 Personal activation normally requires Unity Hub; merely saving
UNITY_EMAIL and UNITY_PASSWORD does not give an ephemeral machine a perpetual
Personal seat. Manual ALF/ULF activation of Personal is unsupported in recent
Unity docs. Do not spoof Machine IDs, publish cookies, or auto-click approval
prompts. No secret contents are uploaded to GitHub Releases.

## Important boundaries

- GitHub-hosted runners have a finite lifetime. This is an on-demand desktop,
  NOT permanently running compute. Next session gets a new Quick Tunnel URL.
- Cloudflare Quick Tunnels are development only, have no uptime guarantee,
  and do not require a Cloudflare account, domain or configured Access app.
  A stable private hostname needs a named Tunnel, domain and Access policy.
- Camera intent API binds 127.0.0.1, accepts only bounded numeric inputs,
  and does not provide arbitrary remote shell access.
- Assets, Library cache and checkpoint strategies are separate from this
  session. Source-of-truth stays in Git. ci-live-control and logs are ignored.
- The phone can see the actual desktop during an authorized running session;
  ChatGPT does not itself have a continuous stream of that live page. The AI
  can inspect screenshot artifacts from GitHub when they exist.

Official documents:
https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
https://docs.unity.com/en-us/engine/6000.3/manual/get-started/install-and-upgrade/licenses-and-activation/manual-license-activation/manual-activation-cmd-mac

## ChatGPT-accessible, free camera command relay

Persistent read-only Cloudflare Worker hub:
https://aaris-unity-live-hub.aaris-game-control-6f9c.workers.dev

The hub's code is Tools/CI/cloudflare_live_hub.mjs. It uses no KV,
R2, paid resource or stored credential. It reads the public issue camera
channel and available screenshot links. Cloudflare Workers Free requests
are limited to 100,000/day; the hub caches GitHub lookups for 45 seconds.

Authorised camera command channel:
https://github.com/sundamunda289-art/Unity-Game-Aris/issues/77

Only comments authored by sundamunda289-art with the format
CAMERA x y z yaw pitch distance are accepted, e.g.
CAMERA -420 22 -210 0 20 22

While the on-demand Actions desktop is running, Python polls this issue
every four seconds. The runner announces its temporary, email-PIN-protected
Tunnel URL in a GitHub comment. After an authorized licensed Unity Editor
processes a camera request, the Python bridge uploads a real 1280x720
screenshot to the live-photos GitHub Release and replies with its link.
The read-only Worker displays that link.

A connected GitHub app can post issue commands and fetch screenshot links.
This is near-real-time discrete frame inspection, NOT a continuously streamed
video channel into ChatGPT. The phone can watch the actual noVNC live desktop
during a running session.

If Unity has not activated on that machine, no true Unity screenshot is
created. The desktop and Cloudflare hub cannot activate Unity by themselves.
Do not put passwords, license tokens, OAuth cookies or any private values
in public issue comments or public release assets.
