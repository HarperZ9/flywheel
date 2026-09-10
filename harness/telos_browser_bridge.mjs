// Restricted operations over Telos's existing CDP client, never its launcher.
import {open} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const MAX_BYTES = 262144, TEXT_BYTES = 16384, RESULT_BYTES = 32768;
const SUPPORTED_CDP_SHA256 = 'd2d43363842b3f84e4f4562c6f7d74c1ff0d98054c456c172d9a0e70db9b1413';
const fail = () => {throw new Error('browser_preflight_refused');};
function origin(value) {
  if (typeof value !== 'string' || value.length > 2048 || /[\x00-\x20\x7f-\uffff\\]/.test(value)) fail();
  const url = new URL(value);
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password) fail();
  return url.origin;
}
function identity(config) {
  if (!Number.isInteger(config.port) || config.port < 1 || config.port > 65535
      || !/^[A-Za-z0-9_-]{1,128}$/.test(config.target_id)
      || !/^\/devtools\/browser\/[A-Za-z0-9_-]{1,128}$/.test(config.browser_instance)
      || origin(config.allowed_origin) !== config.allowed_origin) fail();
}
function checkVersion(version, config) {
  if (version?.webSocketDebuggerUrl !== `ws://127.0.0.1:${config.port}${config.browser_instance}`) fail();
}
export function selectTarget(targets, config) {
  identity(config);
  if (!Array.isArray(targets)) fail();
  const hits = targets.filter(t=>t?.id === config.target_id);
  if (hits.length !== 1) fail();
  const target = hits[0];
  if (target.type !== 'page' || origin(target.url) !== config.allowed_origin
      || target.webSocketDebuggerUrl !== `ws://127.0.0.1:${config.port}/devtools/page/${config.target_id}`) fail();
  return target;
}

export async function execute(config, action, deps, progress = ()=>{}) {
  identity(config);
  if (!action || !['read','navigate'].includes(action.kind)) fail();
  if (action.kind === 'navigate' && origin(action.url) !== config.allowed_origin) fail();
  if (action.kind === 'read' && action.url !== '') fail();
  checkVersion(await deps.version(), config);
  const target = selectTarget(await deps.targets(), config);
  const session = await deps.connect(target.webSocketDebuggerUrl);
  try {
    // Reobserve after opening the exact socket, before an operation is sent.
    checkVersion(await deps.version(), config);
    selectTarget(await deps.targets(), config);
    const tree = await session.send('Page.getFrameTree');
    const frame = tree?.frameTree?.frame;
    if (typeof frame?.id !== 'string' || origin(frame.url) !== config.allowed_origin) fail();
    if (action.kind === 'navigate') {
      progress();
      const result = await session.send('Page.navigate', {url:action.url});
      if (result?.errorText || result?.isDownload || result?.frameId !== frame.id) fail();
      return {ok:true, performed:true, code:'navigation_requested'};
    }
    const world = await session.send('Page.createIsolatedWorld', {
      frameId:frame.id, worldName:'flywheel-bounded-read', grantUniveralAccess:false,
    });
    if (!Number.isInteger(world?.executionContextId)) fail();
    const expected = JSON.stringify(config.allowed_origin);
    // This fixed expression is the only evaluation surface. No caller code.
    const expression = `(()=>{if(location.origin!==${expected})return null;`
      + `const text=(document.body?.innerText||'').slice(0,${TEXT_BYTES});`
      + `return location.origin===${expected}?{origin:location.origin,text}:null})()`;
    progress();
    const result = await session.send('Runtime.evaluate', {
      expression, contextId:world.executionContextId, returnByValue:true, awaitPromise:false,
    });
    const value = result?.result?.value;
    if (result?.exceptionDetails || value?.origin !== config.allowed_origin
        || typeof value?.text !== 'string') fail();
    const bytes = Buffer.from(value.text, 'utf8');
    if (bytes.length > TEXT_BYTES) fail();
    return {ok:true, performed:true, code:'read', observation:value.text};
  } finally { session.close(); }
}

export function limitedFetch(config, signal, fetchImpl = fetch) {
  const base = `http://127.0.0.1:${config.port}`;
  return async (url) => {
    if (![base+'/json', base+'/json/version'].includes(url)) fail();
    const response = await fetchImpl(url, {method:'GET', redirect:'error', signal});
    if (!response.ok || !response.body) fail();
    const reader = response.body.getReader();
    let size = 0; const chunks = [];
    try {
      while (true) {
        const {done,value} = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_BYTES) fail();
        chunks.push(Buffer.from(value));
      }
    } finally { await reader.cancel().catch(()=>{}); }
    const value = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));
    return {ok:true, json:async()=>value};
  };
}

function socketFactory(sockets, WebSocketImpl = WebSocket) {
  return url => {
    const socket = new WebSocketImpl(url); sockets.add(socket);
    // Preserve Telos correlation while bounding accepted messages. Native
    // WebSocket may allocate a frame before this check; no heap-bound claim.
    const proxy = {
      set onopen(fn) {socket.onopen=fn;}, set onerror(fn) {socket.onerror=fn;},
      set onmessage(fn) {socket.onmessage=e=>{
        if (typeof e.data !== 'string' || Buffer.byteLength(e.data,'utf8') > MAX_BYTES) {
          socket.close(); return;
        }
        fn(e);
      };},
      send(payload) {socket.send(payload);}, close() {socket.close();},
    };
    return proxy;
  };
}

async function main() {
  let started = false, timer; const sockets = new Set();
  try {
    const chunks = []; let size = 0;
    for await (const chunk of process.stdin) {
      size += chunk.length; if (size > 16384) fail(); chunks.push(chunk);
    }
    const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (request.schema !== 'flywheel.telos-browser-request/v1'
        || !Number.isInteger(request.timeout_ms) || request.timeout_ms < 1
        || request.timeout_ms > 9000) fail();
    const {config,action} = request; identity(config);
    timer = setTimeout(()=>process.exit(2),request.timeout_ms);
    const signal = AbortSignal.timeout(request.timeout_ms);
    const file = await open(config.cdp_module,'r');
    const buffer = Buffer.alloc(MAX_BYTES+1); let sizeRead;
    try { ({bytesRead:sizeRead} = await file.read(buffer,0,buffer.length,0)); }
    finally { await file.close(); }
    const bytes = buffer.subarray(0,sizeRead);
    if (sizeRead > MAX_BYTES || createHash('sha256').update(bytes).digest('hex') !== config.cdp_sha256) fail();
    const source = new TextDecoder('utf-8',{fatal:true}).decode(bytes).replaceAll('\r\n','\n');
    if (createHash('sha256').update(source).digest('hex') !== SUPPORTED_CDP_SHA256) fail();
    const cdp = await import(pathToFileURL(config.cdp_module).href);
    const bounded = limitedFetch(config,signal);
    const row = await execute(config,action,{
      version:()=>cdp.debuggerVersion(config.port,bounded),
      targets:()=>cdp.listTargets(config.port,bounded),
      connect:url=>cdp.CdpSession.connect(url,socketFactory(sockets)),
    },()=>{started=true;});
    const out = JSON.stringify(row);
    if (Buffer.byteLength(out,'utf8') > RESULT_BYTES) fail();
    process.stdout.write(out+'\n');
  } catch {
    if (started) process.exitCode = 2;
    else process.stdout.write(JSON.stringify({ok:false,performed:false,code:'preflight_refused'})+'\n');
  } finally {
    clearTimeout(timer);
    for (const socket of sockets) {try {socket.close();} catch {}}
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
