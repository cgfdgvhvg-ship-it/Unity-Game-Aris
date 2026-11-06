import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{validateJob,processJob,handleCron,handleAgent} from './worker.mjs';

const JOB = 'r20261105-test-a';
const repo = '/repos/sundamunda289-art/Unity-Game-Aris';
const contents = `${repo}/contents/`;
const code = 'redesigned-space-train-gxp5jwvq94wg2wvw6';
function encode(json){return btoa(JSON.stringify(json))}
function fakeApi(job,initial='Shutdown') {
  const list=[{type:'file',name:job.id+'.json'}];
  const records=new Map();
  let state=initial;
  const calls=[];
  async function api(path,opts={}) {
    const method=opts.method||'GET';calls.push(method+' '+path);
    if(path.startsWith(contents+'.aaris/relay-jobs?'))return list;
    if(path.startsWith(contents+'.aaris/relay-jobs/'+job.id+'.json'))return {type:'file',encoding:'base64',size:100,content:encode(job)};
    if(path.startsWith(`${repo}/commits?`))return [{author:{login:'sundamunda289-art'},committer:{login:'sundamunda289-art'}}];
    if(path.startsWith(contents+'.aaris/relay-results/')) {
      const key=path.match(/(r[a-z0-9-]+)\.json/)[1];
      if(method==='PUT') {
        assert(!records.has(key));
        records.set(key, JSON.parse(atob(opts.body.content)));
        return {commit:{sha:'abcdef'}};
      }
      const out=records.get(key);
      return out ? {type:'file',encoding:'base64',size:100,content:encode(out)} : null;
    }
    if (path===`/user/codespaces/${code}`)return {name:code,owner:{login:'sundamunda289-art'},repository:{full_name:'sundamunda289-art/Unity-Game-Aris'},state};
    if (path===`/user/codespaces/${code}/start`) {state='Starting';return {state};}
    if (path===`/user/codespaces/${code}/stop`) {state='ShuttingDown';return {state};}
    throw Error('unexpected '+path);
  }
  return {api,calls,records,setState:v=>{state=v},getState:()=>state};
}

test('unsupported arbitrary shell and malformed jobs rejected',()=>{
  assert.throws(()=>validateJob({id:JOB,action:'terminal',command:'bash',args:['rm -rf /']}, JOB+'.json'));
  assert.throws(()=>validateJob({id:JOB,action:'terminal',command:'unity_recover',args:['x']}, JOB+'.json'));
  assert.throws(()=>validateJob({id:JOB,action:'stop',extra:true}, JOB+'.json'));
});
test('start requests lifecycle and creates truthful receipt',async()=>{
  const j={id:JOB,action:'start'}; const f=fakeApi(j);
  assert.deepEqual(await handleCron({RELAY_ENABLED:'true'},f.api),{status:'polled',scanned:1,handled:1});
  assert(f.calls.some(x=>x===`POST /user/codespaces/${code}/start`));
  assert.equal(f.records.get(j.id).status,'start_requested');
  assert.equal(f.records.get(j.id).state_before,'Shutdown');
  await handleCron({RELAY_ENABLED:'true'},f.api);
  assert.equal(f.calls.filter(x=>x.includes('/start')).length,1);
});
test('stop on ShuttingDown never sends duplicate stop request',async()=>{
  const j={id:JOB,action:'stop'};const f=fakeApi(j,'ShuttingDown');
  await handleCron({RELAY_ENABLED:'true'},f.api);
  assert.equal(f.calls.filter(x=>x.endsWith('/stop')).length,0);
  assert.equal(f.records.get(j.id).status,'already_stopped_or_stopping');
});
test('Cloudflare never starts Codespace for terminal commands',async()=>{
  const j={id:JOB,action:'terminal',command:'system_status',args:[]};
  const f=fakeApi(j);
  await handleCron({RELAY_ENABLED:'true'},f.api);
  assert.equal(f.getState(),'Shutdown');
  assert.equal(f.records.size,0);
  assert.equal(f.calls.some(x=>x.includes('/user/codespaces/')),false);
  const response=await handleAgent(new Request('https://relay.example/v1/next'),{},f.api);
  assert.equal(response.status,410);
});

test('start waits during ShuttingDown then safely retries after Shutdown',async()=>{
  const job={id:JOB,action:'start'};const f=fakeApi(job,'ShuttingDown');
  await handleCron({RELAY_ENABLED:'true'},f.api);
  assert.equal(f.records.size,0);
  assert.equal(f.calls.filter(x=>x.includes('/start')).length,0);
  f.setState('Shutdown');
  await handleCron({RELAY_ENABLED:'true'},f.api);
  assert.equal(f.records.get(JOB).status,'start_requested');
  assert.equal(f.calls.filter(x=>x.includes('/start')).length,1);
});
test('disabled relay cannot act on Codespace',async()=>{
  const job={id:JOB,action:'stop'};const f=fakeApi(job,'Available');
  assert.deepEqual(await handleCron({RELAY_ENABLED:'false'},f.api),{status:'disabled'});
  assert.equal(f.calls.length,0);
});

test('camera focus schema rejects arbitrary shell and unsafe coordinates',()=>{
  const id='r20261105-cameratest-01';
  const safe={id,action:'terminal',command:'unity_camera_focus',args:[102.307,-10.849,62.974]};
  assert.equal(validateJob(safe,id+'.json').command,'unity_camera_focus');
  for(const args of [[1,2],['x',2,3],[NaN,0,0],[Infinity,1,2],[20001,0,0]]) {
    assert.throws(()=>validateJob({...safe,args},id+'.json'));
  }
});

test('live view redirects only to GitHub owner-authenticated Codespace private port',async()=>{
  const response=await worker.fetch(new Request('https://example.workers.dev/live'),{RELAY_ENABLED:'true'});
  assert.equal(response.status,302);
  assert.equal(response.headers.get('location'),
    'https://redesigned-space-train-gxp5jwvq94wg2wvw6-6080.app.github.dev/vnc.html?autoconnect=true&resize=scale');
  assert.equal(response.headers.get('cache-control'),'no-store');
  assert.equal(response.headers.get('referrer-policy'),'no-referrer');
});
