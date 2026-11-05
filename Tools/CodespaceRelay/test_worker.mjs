import test from 'node:test';
import assert from 'node:assert/strict';
import {validateJob,processJob,handleCron,handleAgent} from './worker.mjs';

const JOB = 'r20261105-test-a';
const repo = '/repos/Aaris-khan-don/Unity-Game-Aris';
const contents = `${repo}/contents/`;
const code = 'musical-carnival-jjxp9r6vw45wfjgvg';
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
    if(path.startsWith(`${repo}/commits?`))return [{author:{login:'Aaris-khan-don'},committer:{login:'Aaris-khan-don'}}];
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
    if (path===`/user/codespaces/${code}`)return {name:code,owner:{login:'Aaris-khan-don'},repository:{full_name:'Aaris-khan-don/Unity-Game-Aris'},state};
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
test('terminal queues until trusted agent executes',async()=>{
  const j={id:JOB,action:'terminal',command:'system_status',args:[]};const f=fakeApi(j);
  await handleCron({RELAY_ENABLED:'true'},f.api);
  assert.equal(f.getState(),'Starting');
  assert.equal(f.records.size,0);
  f.setState('Available');
  const env={RELAY_ENABLED:'true',AGENT_SHARED_SECRET:'a'.repeat(64)};
  let req=new Request('https://relay.example/v1/next',{headers:{authorization:'Bearer '+env.AGENT_SHARED_SECRET}});
  const reply=await handleAgent(req,env,f.api);
  assert.deepEqual((await reply.json()).job,j);
  req=new Request('https://relay.example/v1/result',{method:'POST',headers:{authorization:'Bearer '+env.AGENT_SHARED_SECRET},body:JSON.stringify({id:JOB,status:'ok',exit_code:0,stdout:'test-output',stderr:''})});
  const uploaded=await handleAgent(req,env,f.api);
  assert.equal((await uploaded.json()).stored,true);
  assert.equal(f.records.get(JOB).stdout,'test-output');
  const empty=await handleAgent(new Request('https://relay.example/v1/next',{headers:{authorization:'Bearer '+env.AGENT_SHARED_SECRET}}),env,f.api);
  assert.equal((await empty.json()).job,null);
});
test('agent endpoint enforces secret and no arbitrary command result',async()=>{
  const j={id:JOB,action:'start'};const f=fakeApi(j);
  const env={RELAY_ENABLED:'true',AGENT_SHARED_SECRET:'b'.repeat(64)};
  let r=await handleAgent(new Request('https://relay.example/v1/next'),env,f.api);
  assert.equal(r.status,401);
  r=await handleAgent(new Request('https://relay.example/v1/result',{method:'POST',headers:{authorization:'Bearer '+env.AGENT_SHARED_SECRET},body:JSON.stringify({id:JOB,status:'ok',exit_code:0,stdout:'ok',stderr:''})}),env,f.api);
  assert.equal(r.status,403);
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
