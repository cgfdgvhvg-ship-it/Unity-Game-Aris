#!/usr/bin/env python3
"""Local camera-intent API for Cloudflare email-protected Unity desktop sessions.

The server binds only to 127.0.0.1. Cloudflare's --allowed-mail must be active.
No authentication tokens are accepted or stored here; no arbitrary shell commands.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import math
import os
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "ci-live-control"
STATE.mkdir(parents=True, exist_ok=True)

HTML = """<!doctype html><html lang="en"><meta name="viewport"
content="width=device-width, initial-scale=1"><title>Aaris Unity Live</title>
<style>body{background:#0a1b26;color:#edf9ff;font-family:system-ui;margin:12px}
button,input{font-size:16px;padding:9px;margin:3px;max-width:115px}
button{background:#0e8573;color:white;border:0;border-radius:6px}
label{display:inline-block}iframe{width:100%;height:68vh;border:1px solid #477;
border-radius:8px}small{color:#b7d4dd}#result{white-space:pre-wrap}</style>
<h2>Aaris Unity live camera</h2><small>Real editor if licensed; temporary GitHub runner session.
Camera coordinates in Unity metres. Access limited to approved email via Cloudflare.</small>
<div><label>X <input id="x" type="number" value="-420"></label>
<label>Y <input id="y" type="number" value="22"></label>
<label>Z <input id="z" type="number" value="-210"></label>
<label>Yaw <input id="yaw" type="number" value="0"></label>
<label>Pitch <input id="pitch" type="number" value="20"></label>
<label>Distance <input id="distance" type="number" value="22"></label>
<button onclick="go()">Move + photograph</button></div>
<p id="result">Opening session...</p>
<iframe src="/vnc/vnc.html?autoconnect=true&resize=remote&path=vnc/websockify"></iframe>
<p><a style="color:#6fead7" href="/api/photo" target="_blank">Latest genuine Unity PNG</a></p>
<script>
async function go(){let data={};for(let k of ['x','y','z','yaw','pitch','distance'])
data[k]=Number(document.getElementById(k).value);
try{let r=await fetch('/api/camera',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify(data)});document.getElementById('result').textContent=JSON.stringify(await r.json());}
catch(e){document.getElementById('result').textContent=String(e);}}
async function status(){try{let r=await fetch('/api/status');
document.getElementById('result').textContent=JSON.stringify(await r.json());}catch(e){}}
setInterval(status,7000);status();
</script></html>"""

def validate(data):
    allowed = {"x": (-1000, 1000), "y": (-500, 4000),
               "z": (-1000, 1000), "yaw": (-360, 360),
               "pitch": (-85, 85), "distance": (2, 1000)}
    if not isinstance(data, dict) or any(k not in allowed for k in data):
        raise ValueError("Unknown camera field")
    clean = {}
    for key, (lo, hi) in allowed.items():
        val = data.get(key)
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not lo <= val <= hi:
            raise ValueError("Invalid camera " + key)
        clean[key] = float(val)
    clean["nonce"] = int(time.time_ns() % 9000000000000000)
    return clean

class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, mimetype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", mimetype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data: blob:; connect-src 'self' wss:; frame-src 'self'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self.send(200, HTML, "text/html; charset=utf-8")
        if path == "/api/status":
            status = STATE / "status.json"
            data = json.loads(status.read_text()) if status.exists() else {"state": "Waiting for Unity Editor camera bridge"}
            return self.send(200, data)
        if path == "/api/photo":
            photo = STATE / "latest.png"
            if not photo.exists():
                return self.send(404, {"error": "Unity has not captured a real image yet"})
            return self.send(200, photo.read_bytes(), "image/png")
        return self.send(404, {"error": "Unknown endpoint"})

    def do_POST(self):
        if self.path != "/api/camera":
            return self.send(404, {"error": "Unknown endpoint"})
        if self.headers.get("Content-Type","").split(";")[0] != "application/json":
            return self.send(415, {"error": "Only JSON camera intents accepted"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 2048:
                raise ValueError("Camera payload too large/empty")
            request = validate(json.loads(self.rfile.read(length)))
            tmp = STATE / "camera.tmp"
            tmp.write_text(json.dumps(request))
            os.replace(tmp, STATE / "camera.json")
            return self.send(202, {"queued": True, "nonce": request["nonce"]})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return self.send(400, {"error": str(exc)})

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
