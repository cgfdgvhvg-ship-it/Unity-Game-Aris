// Aaris Turbo Broker. No public command submission endpoint.
// Only owner-authorized Cloudflare Durable Object SQL API may enqueue commands.
const REPO = "sundamunda289-art/Unity-Game-Aris";
const REPO_ID = "1443109769";
const ACTOR_ID = "353065137";
const WORKFLOW = REPO + "/.github/workflows/aaris-turbo-bootstrap.yml@refs/heads/main";
const AUDIENCE = "aaris-turbo-bootstrap-v1";
const json = (value, status = 200) => new Response(JSON.stringify(value), {
  status, headers: {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"}
});
function decodeB64(s) {
  const b = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(b, c => c.charCodeAt(0));
}
function parseJWTPart(s) {
  return JSON.parse(new TextDecoder().decode(decodeB64(s)));
}
async function verifyActionsJWT(token) {
  const parts = token.split(".");
  if (parts.length !== 3) throw Error("token_parts");
  const header = parseJWTPart(parts[0]), claims = parseJWTPart(parts[1]);
  const now = Math.floor(Date.now() / 1000);
  if (header.alg !== "RS256" || !header.kid ||
      claims.iss !== "https://token.actions.githubusercontent.com" ||
      claims.aud !== AUDIENCE ||
      String(claims.repository_id) !== REPO_ID ||
      String(claims.actor_id) !== ACTOR_ID ||
      claims.repository !== REPO ||
      claims.ref !== "refs/heads/main" ||
      claims.workflow_ref !== WORKFLOW ||
      !["issue_comment", "workflow_dispatch"].includes(claims.event_name) ||
      !Number.isFinite(claims.exp) || claims.exp <= now || claims.exp > now + 1800 ||
      !Number.isFinite(claims.iat) || claims.iat > now + 60) {
    throw Error("claims");
  }
  const discovery = await fetch("https://token.actions.githubusercontent.com/.well-known/openid-configuration");
  if (!discovery.ok) throw Error("issuer_discovery");
  const config = await discovery.json();
  if (!config.jwks_uri || !config.jwks_uri.startsWith("https://token.actions.githubusercontent.com/")) throw Error("issuer_jwks");
  const keyResponse = await fetch(config.jwks_uri);
  if (!keyResponse.ok) throw Error("jwks");
  const jwks = await keyResponse.json();
  const jwk = (jwks.keys || []).find(k => k.kid === header.kid && k.kty === "RSA");
  if (!jwk) throw Error("unknown_kid");
  const key = await crypto.subtle.importKey("jwk", jwk, {name: "RSASSA-PKCS1-v1_5", hash: "SHA-256"}, false, ["verify"]);
  const message = new TextEncoder().encode(parts[0] + "." + parts[1]);
  if (!await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, decodeB64(parts[2]), message)) throw Error("signature");
  return claims;
}
function validMachine(name) {
  return typeof name === "string" && /^[a-zA-Z0-9][a-zA-Z0-9-]{2,119}$/.test(name);
}
async function sha256(s) {
  const bytes = new TextEncoder().encode(s);
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    b => b.toString(16).padStart(2, "0")).join("");
}
export class TurboMachine {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    const sql = ctx.storage.sql;
    sql.exec("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)");
    sql.exec("CREATE TABLE IF NOT EXISTS machines (name TEXT PRIMARY KEY, last_seen INTEGER NOT NULL, stage TEXT NOT NULL)");
    sql.exec("CREATE TABLE IF NOT EXISTS commands (id TEXT PRIMARY KEY, argv_json TEXT NOT NULL, cwd TEXT NOT NULL DEFAULT '/workspaces', max_seconds INTEGER NOT NULL DEFAULT 120, expires_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'queued', created_at INTEGER NOT NULL DEFAULT (unixepoch()), started_at INTEGER, finished_at INTEGER, exit_code INTEGER, error TEXT)");
    sql.exec("CREATE TABLE IF NOT EXISTS chunks (command_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, ts INTEGER NOT NULL DEFAULT (unixepoch()), PRIMARY KEY (command_id, seq))");
    sql.exec("CREATE INDEX IF NOT EXISTS chunks_command ON chunks (command_id, seq)");
  }
  async fetch(req) {
    const path = new URL(req.url).pathname;
    if (path === "/internal/grant" && req.method === "POST") {
      const data = await req.json();
      if (typeof data.token !== "string" || data.token.length !== 64) return json({error:"token"}, 400);
      this.ctx.storage.sql.exec("INSERT INTO config(key,value) VALUES('token_sha256',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", await sha256(data.token));
      this.ctx.storage.sql.exec("INSERT INTO config(key,value) VALUES('last_seen',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", String(Math.floor(Date.now()/1000)));
      this.ctx.storage.sql.exec("INSERT INTO config(key,value) VALUES('token_expires',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", String(Math.floor(Date.now()/1000)+7*86400));
      return json({ok:true});
    }
    if (path === "/internal/register" && req.method === "POST") {
      const data = await req.json();
      if (!validMachine(data.name)) return json({error:"name"}, 400);
      this.ctx.storage.sql.exec("INSERT INTO machines(name,last_seen,stage) VALUES(?,unixepoch(),?) ON CONFLICT(name) DO UPDATE SET last_seen=unixepoch(),stage=excluded.stage", data.name, data.stage === "connected" ? "connected" : "bootstrapped");
      return json({ok:true});
    }
    if (!path.startsWith("/agent/") || req.method !== "POST") return json({error:"not_found"},404);
    const token = (req.headers.get("authorization") || "").replace(/^Bearer /, "");
    const hashes = Array.from(this.ctx.storage.sql.exec("SELECT value FROM config WHERE key='token_sha256'"));
    const expires = Array.from(this.ctx.storage.sql.exec("SELECT value FROM config WHERE key='token_expires'"));
    if (!hashes.length || !expires.length || Number(expires[0].value) <= Math.floor(Date.now()/1000) ||
        token.length !== 64 || await sha256(token) !== hashes[0].value) return json({error:"unauthorized"},401);
    const sql = this.ctx.storage.sql;
    if (path === "/agent/ping") {
      const now = Math.floor(Date.now()/1000);
      sql.exec("INSERT INTO config(key,value) VALUES('last_seen',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",String(now));
      // Keep authenticated output privately for one day. Remove old image chunks,
      // completed jobs and expired abandoned queue items; never prune running jobs.
      const last = Array.from(sql.exec("SELECT value FROM config WHERE key='last_cleanup'"));
      if (!last.length || now - Number(last[0].value) >= 3600) {
        const stale = "(status IN ('completed','failed') AND COALESCE(finished_at,created_at) < unixepoch()-86400) OR (status='queued' AND expires_at < unixepoch()-86400)";
        sql.exec("DELETE FROM chunks WHERE command_id IN (SELECT id FROM commands WHERE " + stale + ")");
        sql.exec("DELETE FROM commands WHERE " + stale);
        sql.exec("INSERT INTO config(key,value) VALUES('last_cleanup',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",String(now));
      }
      return json({ok:true});
    }
    if (path === "/agent/next") {
      sql.exec("UPDATE commands SET status='failed',error='agent_lease_expired',finished_at=unixepoch() WHERE status='running' AND started_at + max_seconds + 90 < unixepoch()");
      const active = Array.from(sql.exec("SELECT COUNT(*) AS n FROM commands WHERE status='running'"));
      if (active[0].n >= 2) return json({job:null});
      const rows = Array.from(sql.exec("UPDATE commands SET status='running', started_at=unixepoch() WHERE id=(SELECT id FROM commands WHERE status='queued' AND expires_at>unixepoch() ORDER BY created_at,id LIMIT 1) RETURNING id,argv_json,cwd,max_seconds"));
      return json({job:rows[0]||null});
    }
    if (path === "/agent/chunk") {
      const d=await req.json();
      if(typeof d.id!=="string"||d.id.length>128||!Number.isSafeInteger(d.seq)||d.seq<0||
          !["stdout","stderr"].includes(d.kind)||typeof d.text!=="string"||d.text.length>8192) return json({error:"chunk"},400);
      const found=Array.from(sql.exec("SELECT 1 FROM commands WHERE id=? AND status='running'",d.id));
      if(!found.length) return json({error:"not_running"},409);
      sql.exec("INSERT OR IGNORE INTO chunks(command_id,seq,kind,text) VALUES(?,?,?,?)",d.id,d.seq,d.kind,d.text);
      return json({ok:true});
    }
    if (path === "/agent/done") {
      const d=await req.json();
      if (typeof d.id !=="string" || d.id.length>128 || !Number.isInteger(d.exit_code) || d.exit_code< -255 || d.exit_code>255) return json({error:"done"},400);
      sql.exec("UPDATE commands SET status=?,exit_code=?,finished_at=unixepoch(),error=? WHERE id=? AND status='running'",
        d.exit_code===0?"completed":"failed",d.exit_code,
        typeof d.error==="string"?d.error.slice(0,100):"",d.id);
      return json({ok:true});
    }
    return json({error:"not_found"},404);
  }
}
export default {
  async fetch(request, env) {
    const u = new URL(request.url);
    if (u.pathname === "/health" && request.method==="GET") {
      const operation = request.headers.get("x-aaris-op");
      if (!operation) return json({service:"aaris-turbo",version:2,status:"ready"});
      const machine = request.headers.get("x-aaris-machine");
      const credential = request.headers.get("x-aaris-token");
      const encoded = request.headers.get("x-aaris-payload") || "";
      if (!["ping","next","chunk","done"].includes(operation) ||
          !validMachine(machine) || !/^[0-9a-f]{64}$/.test(credential || "") ||
          encoded.length > 11000 || !/^[A-Za-z0-9_-]*$/.test(encoded)) return json({error:"unauthorized"},401);
      let payload;
      try {
        payload=encoded ? JSON.parse(new TextDecoder().decode(decodeB64(encoded))) : {};
        if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw Error("not_object");
      } catch (_) { return json({error:"bad_payload"},400); }
      const stub=env.MACHINES.get(env.MACHINES.idFromName("machine:"+machine));
      const response=await stub.fetch("https://internal/agent/"+operation,
        {method:"POST",headers:{"authorization":"Bearer "+credential,"content-type":"application/json"},
          body:JSON.stringify(payload)});
      if (operation === "ping" && response.ok) {
        const registry = env.MACHINES.get(env.MACHINES.idFromName("registry"));
        await registry.fetch("https://internal/internal/register",{
          method:"POST",body:JSON.stringify({name:machine,stage:"connected"})});
      }
      return response;
    }
    if (u.pathname === "/bootstrap" && request.method==="POST") {
      try {
        const bearer = (request.headers.get("authorization")||"").replace(/^Bearer /, "");
        await verifyActionsJWT(bearer);
        const b = await request.json();
        if (!validMachine(b.machine)) return json({error:"bad_machine"},400);
        const token = Array.from(crypto.getRandomValues(new Uint8Array(32)), v=>v.toString(16).padStart(2,"0")).join("");
        const stub = env.MACHINES.get(env.MACHINES.idFromName("machine:"+b.machine));
        const response = await stub.fetch("https://internal/internal/grant",{method:"POST",body:JSON.stringify({token})});
        if (!response.ok) return json({error:"grant_failed"},503);
        const registry = env.MACHINES.get(env.MACHINES.idFromName("registry"));
        await registry.fetch("https://internal/internal/register",{method:"POST",body:JSON.stringify({name:b.machine,stage:"bootstrapped"})});
        return json({machine:b.machine,token,endpoint:u.origin+"/agent/"+encodeURIComponent(b.machine),expires_at:Math.floor(Date.now()/1000)+7*86400});
      } catch (_) { return json({error:"unauthorized"},401); }
    }
    const match=u.pathname.match(/^\/agent\/([A-Za-z0-9-]{3,120})\/(ping|next|chunk|done)$/);
    if(!match || request.method!=="POST") return json({error:"not_found"},404);
    const stub=env.MACHINES.get(env.MACHINES.idFromName("machine:"+match[1]));
    const response = await stub.fetch(new Request("https://internal/agent/"+match[2],request));
    if (match[2] === "ping" && response.ok) {
      const registry = env.MACHINES.get(env.MACHINES.idFromName("registry"));
      await registry.fetch("https://internal/internal/register", {method:"POST",
        body:JSON.stringify({name:match[1],stage:"connected"})});
    }
    return response;
  }
};
