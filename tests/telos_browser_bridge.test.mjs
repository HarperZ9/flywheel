// Synthetic CDP only. No fetch/socket/browser implementation is invoked.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {execute, selectTarget, limitedFetch} from '../harness/telos_browser_bridge.mjs';

const config = {port:9229, browser_instance:'/devtools/browser/browser-123',
 target_id:'target-123', allowed_origin:'https://example.test'};
const target = {id:'target-123',type:'page',url:'https://example.test/page',
 webSocketDebuggerUrl:'ws://127.0.0.1:9229/devtools/page/target-123'};

test('exact ID cannot become a substring, duplicate, or remote socket',()=>{
 assert.equal(selectTarget([target],config),target);
 for(const rows of [[],[target,target],[{...target,id:'another'}],
  [{...target,webSocketDebuggerUrl:'ws://evil.test/devtools/page/target-123'}],
  [{...target,url:'https://other.test'}]]){
  assert.throws(()=>selectTarget(rows,config));
 }
});

function fixture({instance=config.browser_instance,origin=config.allowed_origin}={}){
 const calls=[];let closed=0, connects=0;
 const session={close(){closed++;},async send(method,params){calls.push({method,params});
  if(method==='Page.getFrameTree')return {frameTree:{frame:{id:'frame-1',url:origin+'/page'}}};
  if(method==='Page.createIsolatedWorld')return {executionContextId:17};
  if(method==='Runtime.evaluate')return {result:{value:{origin,text:'fixture text'}}};
  if(method==='Page.navigate')return {frameId:'frame-1'};
  return {};
 }};
 const deps={async version(){return {webSocketDebuggerUrl:'ws://127.0.0.1:9229'+instance};},
  async targets(){return [target];},async connect(){connects++;return session;}};
 return {calls,deps,get closed(){return closed;},get connects(){return connects;}};
}

test('read checks identity and main origin in fixed isolated context',async()=>{
 const f=fixture();const row=await execute(config,{kind:'read',url:''},f.deps);
 assert.equal(row.performed,true);assert.equal(row.observation,'fixture text');
 const evaluate=f.calls.find(c=>c.method==='Runtime.evaluate');
 assert.equal(evaluate.params.contextId,17);
 assert.match(evaluate.params.expression,/location.origin/);
 assert.equal(f.closed,1);
});

test('replaced browser or changed frame origin prevents page action',async()=>{
 for(const opts of [{instance:'/devtools/browser/replaced'},{origin:'https://other.test'}]){
  const f=fixture(opts);
  await assert.rejects(()=>execute(config,{kind:'navigate',url:'https://example.test/next'},f.deps));
  assert.equal(f.calls.filter(c=>c.method==='Page.navigate'||c.method==='Runtime.evaluate').length,0);
 }
});

test('navigation acknowledges request only; no arbitrary script or typing',async()=>{
 const f=fixture();const row=await execute(config,{kind:'navigate',url:'https://example.test/next'},f.deps);
 assert.equal(row.code,'navigation_requested');
 for(const kind of ['eval','type','click','screenshot','download']){
  const bad=fixture();await assert.rejects(()=>execute(config,{kind,url:''},bad.deps));
  assert.equal(bad.connects,0);
 }
});

test('discovery fetch caps bytes, rejects redirects through fixed options and cancels reader',async()=>{
 for(const content of [Buffer.from('{"ok":true}'),Buffer.alloc(262145,120),Buffer.from([0xff])]){
  let cancelled=false,calls=0,options;
  const response={ok:true,body:{getReader(){let done=false;return {
   async read(){if(done)return {done:true};done=true;return {done:false,value:content};},
   async cancel(){cancelled=true;},
  };}}};
  const fetcher=limitedFetch(config,undefined,async(url,opts)=>{calls++;options=opts;return response;});
  if(content.length===11)assert.deepEqual(await (await fetcher('http://127.0.0.1:9229/json')).json(),{ok:true});
  else await assert.rejects(()=>fetcher('http://127.0.0.1:9229/json'));
  assert.equal(calls,1);assert.equal(cancelled,true);
  assert.equal(options.redirect,'error');assert.equal(options.method,'GET');
  await assert.rejects(()=>fetcher('http://evil.test/json'));assert.equal(calls,1);
 }
});

test('target replaced after socket opening still prevents action',async()=>{
 const f=fixture();let calls=0;
 f.deps.targets=async()=>++calls===1?[target]:[{...target,id:'replacement'}];
 await assert.rejects(()=>execute(config,{kind:'read',url:''},f.deps));
 assert.equal(f.calls.length,0);assert.equal(f.closed,1);
});
