// Aaris Unity private approval relay. Public endpoints never return an OAuth URL.
// A signed, precisely scoped GitHub Actions OIDC token is required to publish.
const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "https://aaris-unity-approval-relay.aaris-game-control-6f9c.workers.dev/publish";
const JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks";
const REPOSITORY = "sundamunda289-art/Unity-Game-Aris";
const REPOSITORY_ID = "1443109769";
const ACTOR_ID = "353065137";
const APPROVED_WORKFLOWS = new Set([
  REPOSITORY + "/.github/workflows/aaris-live-unity.yml@refs/heads/main",
  REPOSITORY + "/.github/workflows/aaris-codespaces-control.yml@refs/heads/main",
]);
const TTL_SECONDS = 480;

function decodeBase64Url(value) {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]+$/.test(value)) throw Error("invalid jwt");
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), ch => ch.charCodeAt(0));
}
function parseJwtJson(value) {
  return JSON.parse(new TextDecoder().decode(decodeBase64Url(value)));
}
function validUnityUrl(link) {
  if (typeof link !== "string" || link.length > 4000) return false;
  try {
    const uri = new URL(link);
    const h = uri.hostname.toLowerCase();
    const approved = ["unity.com", "unity3d.com"].some(d => h === d || h.endsWith("." + d));
    return approved && uri.protocol === "https:" && !uri.username && !uri.password;
  } catch (_) {
    return false;
  }
}
async function verifyGithubOidc(token) {
  if (typeof token !== "string" || token.length > 16000 || token.length < 100) throw Error("bad token");
  const chunks = token.split(".");
  if (chunks.length !== 3) throw Error("malformed token");
  const header = parseJwtJson(chunks[0]);
  const claims = parseJwtJson(chunks[1]);
  if (header.alg !== "RS256" || typeof header.kid !== "string" || header.kid.length > 200) throw Error("invalid algorithm");
  const now = Math.floor(Date.now() / 1000);
  if (claims.iss !== ISSUER || claims.aud !== AUDIENCE) throw Error("invalid issuer/audience");
  if (![claims.iat, claims.exp].every(Number.isFinite)
      || claims.iat > now + 60 || claims.exp <= now - 10
      || claims.exp - claims.iat > 900 || claims.iat < now - 900) throw Error("invalid token lifetime");
  if (String(claims.repository_id) !== REPOSITORY_ID
      || claims.repository !== REPOSITORY
      || String(claims.actor_id) !== ACTOR_ID
      || claims.ref !== "refs/heads/main"
      || !APPROVED_WORKFLOWS.has(claims.workflow_ref)
      || !["issue_comment", "workflow_dispatch"].includes(claims.event_name)
      || !/^[0-9]{6,18}$/.test(String(claims.run_id || ""))) {
    throw Error("unauthorized GitHub workflow");
  }
  const response = await fetch(JWKS_URL, {cf: {cacheTtl: 300, cacheEverything: true}});
  if (!response.ok) throw Error("OIDC verifier unavailable");
  const keys = await response.json();
  const publicJwk = keys.keys?.find(k => k.kid === header.kid && k.kty === "RSA" && (!k.alg || k.alg === "RS256"));
  if (!publicJwk) throw Error("unrecognized signing key");
  const pub = await crypto.subtle.importKey("jwk", publicJwk, {name: "RSASSA-PKCS1-v1_5", hash: "SHA-256"}, false, ["verify"]);
  const encoded = new TextEncoder().encode(chunks[0] + "." + chunks[1]);
  const verified = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", pub, decodeBase64Url(chunks[2]), encoded);
  if (!verified) throw Error("invalid token signature");
  return claims;
}
function response(status, content) {
  return new Response(JSON.stringify(content), {status, headers: {
    "Content-Type": "application/json", "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  }});
}
export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    if (request.method === "GET" && path === "/health") return response(200, {healthy: true, private_link_retrieval: "Cloudflare account API only"});
    if (request.method !== "POST" || !["/publish", "/probe"].includes(path)) return response(404, {error:"not_found"});
    // No GET API for the stored URL. Only the account's KV admin API can read it.
    const header = request.headers.get("Authorization") || "";
    if (!header.startsWith("Bearer ")) return response(401, {error: "authentication_required"});
    if (Number(request.headers.get("Content-Length") || "0") > 5200) return response(413, {error:"payload_too_large"});
    let claims;
    try { claims = await verifyGithubOidc(header.slice(7)); }
    catch (_) { return response(403, {error: "github_workflow_identity_rejected"}); }
    if (path === "/probe") return response(200, {accepted:true,run_id:String(claims.run_id)});
    let body;
    try { body = await request.json(); } catch (_) { return response(400, {error:"bad_json"}); }
    if (!body || typeof body !== "object" || String(body.run_id) !== String(claims.run_id)
        || !validUnityUrl(body.auth_url)) return response(400, {error:"bad_approval_request"});
    try {
      await env.APPROVALS.put("run-" + claims.run_id, JSON.stringify({
        run_id: String(claims.run_id),
        auth_url: body.auth_url,
        saved_at: Date.now(),
        expires_at: Date.now() + TTL_SECONDS * 1000
      }), {expirationTtl: TTL_SECONDS});
    } catch (_) {
      return response(503, {error:"private_storage_unavailable"});
    }
    return response(202, {accepted: true, run_id: String(claims.run_id), expires_in_seconds: TTL_SECONDS});
  }
};
