/**
 * Aaris Codespace relay: GitHub Actions-free lifecycle and bounded command queue.
 * Deploy as a Cloudflare Worker with a Cron Trigger. Never place tokens in git.
 * No arbitrary shell, no repository checkout or source edits.
 */
const REPO = 'Aaris-khan-don/Unity-Game-Aris';
const OWNER = 'Aaris-khan-don';
const BRANCH = 'ai/codespace-jobs';
const CODESPACE = 'musical-carnival-jjxp9r6vw45wfjgvg';
const JOBS = '.aaris/relay-jobs';
const RESULTS = '.aaris/relay-results';
const ID = /^r[a-z0-9][a-z0-9-]{5,51}$/;
const COMMANDS = new Set(['system_status', 'desktop_live_start', 'desktop_live_status',
  'unity_virtual_start', 'unity_virtual_status', 'unity_camera_focus', 'unity_status', 'unity_recover',
  'unity_gallery_start', 'unity_gallery_diagnose', 'unity_gallery_partial_export',
  'unity_frame_check']);
const GALLERY_ID = /^[a-z][a-z0-9-]{3,55}$/;

export function validateJob(input, file) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw Error('invalid job');
  const keys = Object.keys(input).sort().join(',');
  const job = input;
  if (!ID.test(job.id) || file !== `${job.id}.json`) throw Error('invalid job identity');
  if (!['start', 'stop', 'status', 'terminal'].includes(job.action)) throw Error('unsupported action');
  if (job.action !== 'terminal') {
    if (keys !== 'action,id') throw Error('lifecycle job must have only action and id');
  } else {
    if (keys !== 'action,args,command,id') throw Error('invalid terminal schema');
    if (!COMMANDS.has(job.command) || !Array.isArray(job.args)) throw Error('unsupported command');
    const needsArg = ['unity_gallery_diagnose','unity_gallery_partial_export','unity_frame_check'].includes(job.command);
    const camera = job.command === 'unity_camera_focus';
    if (job.args.length !== (camera ? 3 : needsArg ? 1 : 0)) throw Error('bad command argument count');
    if (needsArg && (typeof job.args[0] !== 'string' || !GALLERY_ID.test(job.args[0]))) {
      throw Error('unsafe gallery/frame identifier');
    }
    if (camera && job.args.some(n => typeof n !== 'number' || !Number.isFinite(n) || Math.abs(n)>20000)) {
      throw Error('invalid camera coordinates');
    }
  }
  return job;
}

function encode64(s) {
  const bytes = new TextEncoder().encode(s);
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}
function decode64(s) {
  const bytes = Uint8Array.from(atob(s.replace(/\s/g, '')), c => c.charCodeAt(0));
  return new TextDecoder('utf-8', {fatal:true}).decode(bytes);
}
function safePath(s) { return s.split('/').map(encodeURIComponent).join('/'); }
function equalToken(received, expected) {
  if (!expected || typeof received !== 'string') return false;
  const a = new TextEncoder().encode(received), b = new TextEncoder().encode(expected);
  let diff = a.length ^ b.length;
  for (let i=0; i<Math.max(a.length, b.length);i++) diff |= (a[i] || 0) ^ (b[i] || 0);
  return diff === 0;
}

export function makeGitHubApi(env, transport = fetch) {
  if (!env.GITHUB_CONTROL_TOKEN) throw Error('GitHub secret not configured');
  return async function api(path, opts={}) {
    const method = opts.method || 'GET';
    const response = await transport(`https://api.github.com${path}`, {
      method,
      headers: {
        'Authorization': `Bearer ${env.GITHUB_CONTROL_TOKEN}`,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'aaris-codespace-relay/1',
        ...(opts.body ? {'Content-Type':'application/json'} : {})
      },
      ...(opts.body ? {body:JSON.stringify(opts.body)} : {})
    });
    if (response.status === 404 && method === 'GET') return null;
    if (!response.ok) throw Error(`GitHub ${method} ${path.split('?')[0]} HTTP ${response.status}`);
    return response.status === 204 ? {} : response.json();
  };
}
function contentsPath(path) {
  return `/repos/${REPO}/contents/${safePath(path)}`;
}
async function getContent(api, path) {
  const obj=await api(`${contentsPath(path)}?ref=${encodeURIComponent(BRANCH)}`);
  if (!obj || obj.type !== 'file' || obj.encoding !== 'base64' || typeof obj.content !== 'string') return null;
  if (obj.size > 18000) throw Error('oversized repository entry');
  return JSON.parse(decode64(obj.content));
}
async function getJobs(api) {
  const files = await api(`${contentsPath(JOBS)}?ref=${encodeURIComponent(BRANCH)}`);
  if (!files) return [];
  if (!Array.isArray(files) || files.length > 900) throw Error('queue listing invalid or too long');
  return files.filter(x=>x.type === 'file' && ID.test(x.name.replace(/\.json$/,'')) && x.name.endsWith('.json'))
    .map(x=>x.name).sort();
}
async function pendingResult(api, id) {
  return await getContent(api, `${RESULTS}/${id}.json`);
}
async function loadAuthorizedJob(api, filename) {
  const path = `${JOBS}/${filename}`;
  const job = validateJob(await getContent(api, path), filename);
  const commits = await api(`/repos/${REPO}/commits?sha=${encodeURIComponent(BRANCH)}&path=${encodeURIComponent(path)}&per_page=1`);
  const c = Array.isArray(commits) ? commits[0] : null;
  if (!c || !(c.author?.login?.toLowerCase() === OWNER.toLowerCase() ||
               c.committer?.login?.toLowerCase() === OWNER.toLowerCase())) {
    throw Error('Job commit is not from the authorized repository owner');
  }
  return job;
}
async function publishResult(api, job, result) {
  const content = JSON.stringify({schema:1, id:job.id, action:job.action,
    recorded_utc:new Date().toISOString(), ...result},null,2);
  if (content.length > 16000) throw Error('result oversized');
  await api(contentsPath(`${RESULTS}/${job.id}.json`), {method:'PUT',body:{
    branch:BRANCH,
    message:`Codespace relay result ${job.id}`,
    content:encode64(content)
  }});
}
async function codespace(api) {
  const info=await api(`/user/codespaces/${encodeURIComponent(CODESPACE)}`);
  if (info?.name !== CODESPACE || info?.repository?.full_name !== REPO ||
      info?.owner?.login?.toLowerCase() !== OWNER.toLowerCase()) {
    throw Error('Codespace identity mismatch: refusing lifecycle action');
  }
  return info;
}

export async function processJob(api, job) {
  const info=await codespace(api);
  const state=info.state;
  if (job.action === 'status') return {status:'observed', state, source:'cloudflare-scheduled-worker'};
  if (job.action === 'stop') {
    if (['Shutdown','ShuttingDown'].includes(state)) return {status:'already_stopped_or_stopping',state_before:state};
    if (!['Available','Running'].includes(state)) return null; // safe retry next Cron
    await api(`/user/codespaces/${encodeURIComponent(CODESPACE)}/stop`, {method:'POST'});
    return {status:'stop_requested',state_before:state};
  }
  if (job.action === 'start' || job.action === 'terminal') {
    if (['ShuttingDown','Starting','Rebuilding','RebuildPending'].includes(state)) return null;
    if (['Shutdown','Stopped'].includes(state)) {
      await api(`/user/codespaces/${encodeURIComponent(CODESPACE)}/start`, {method:'POST'});
      if (job.action==='start') return {status:'start_requested',state_before:state};
      return null; // terminal request waits for the in-Codespace agent
    }
    if (!['Available','Running'].includes(state)) throw Error(`Cannot wake Codespace in state ${state}`);
    return job.action === 'start' ? {status:'already_running',state_before:state} : null;
  }
  throw Error('unhandled action');
}

export async function handleCron(env, api=makeGitHubApi(env)) {
  if (env.RELAY_ENABLED !== 'true') return {status:'disabled'};
  const files=await getJobs(api);
  let handled=0;
  for (const file of files) {
    if (handled>=8) break;
    const id=file.slice(0,-5);
    if (await pendingResult(api,id)) continue;
    handled++;
    let job;
    try {
      job = await loadAuthorizedJob(api,file);
      const result = await processJob(api,job);
      if (result) await publishResult(api,job,result);
    } catch (err) {
      // A transient API/server failure must remain retryable; do not create
      // permanent errors for 409, 429, 5xx or GitHub API unavailability.
      if (/HTTP (409|429|5\d\d)/.test(String(err))) continue;
      if (job) await publishResult(api,job,{
        status:'error',error:String(err.message||err).slice(0,300)});
    }
  }
  return {status:'polled',scanned:files.length,handled};
}

function json(data, status=200) {
  return new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json','cache-control':'no-store'}});
}
export async function handleAgent(request,env,api=makeGitHubApi(env)) {
  if (env.RELAY_ENABLED !== 'true') return json({error:'relay not enabled'},503);
  const u=new URL(request.url);
  if (!equalToken(request.headers.get('authorization')?.replace(/^Bearer /,''),env.AGENT_SHARED_SECRET)) {
    return json({error:'unauthorized'},401);
  }
  if (request.method==='GET' && u.pathname==='/v1/next') {
    for (const file of await getJobs(api)) {
      const id=file.slice(0,-5);
      if (await pendingResult(api,id)) continue;
      const job=await loadAuthorizedJob(api,file);
      if (job.action==='terminal') return json({job});
    }
    return json({job:null});
  }
  if (request.method==='POST' && u.pathname==='/v1/result') {
    if (Number(request.headers.get('content-length')||0)>18000) return json({error:'too large'},413);
    const body=await request.text();
    if (body.length>18000) return json({error:'too large'},413);
    let data;
    try { data=JSON.parse(body); } catch { return json({error:'bad JSON'},400); }
    if (!data || !ID.test(data.id) || !['ok','error'].includes(data.status) ||
      !Number.isInteger(data.exit_code) || ![-1,0,1,2,3,124,127].includes(data.exit_code) ||
      typeof data.stdout!=='string' || data.stdout.length>9000 ||
      typeof data.stderr!=='string' || data.stderr.length>3000) {
      return json({error:'bad result'},400);
    }
    if (await pendingResult(api,data.id)) return json({error:'already recorded'},409);
    const job=await loadAuthorizedJob(api,`${data.id}.json`);
    if (job.action!=='terminal') return json({error:'not a terminal request'},403);
    await publishResult(api,job,{source:'codespace-agent',status:data.status,
      command:job.command,exit_code:data.exit_code,stdout:data.stdout,stderr:data.stderr});
    return json({stored:true,id:data.id});
  }
  return json({error:'unknown route'},404);
}

export default {
  async scheduled(_event, env, ctx) { ctx.waitUntil(handleCron(env)); },
  async fetch(request, env) {
    if (new URL(request.url).pathname==='/health') return json({service:'aaris-codespace-relay',version:1});
    const pathname = new URL(request.url).pathname;
    if (pathname === '/live') {
      // GitHub's PRIVATE forwarded port enforces owner sign-in; Cloudflare does
      // not proxy video or make the Codespace desktop publicly reachable.
      const target = `https://${CODESPACE}-6080.app.github.dev/vnc.html?autoconnect=true&resize=scale`;
      return new Response(null, {status:302,headers:{location:target,'cache-control':'no-store','referrer-policy':'no-referrer'}});
    }
    if (pathname === '/live-info') return json({mode:'github-private-forwarded-port',port:6080,needs_codespace_online:true,needs_novnc_server:true,requires_github_owner_login:true,redirect_path:'/live'});
    return handleAgent(request,env);
  }
};
