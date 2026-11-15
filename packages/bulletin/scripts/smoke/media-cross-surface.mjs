import { createHash, randomBytes } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { navigateAndEvaluate, withBrowserPage } from "./browser-cdp.mjs";
import { startBackendFace, startHiddenMediaFace, startInvalidMediaFace, startPortfolioFace } from "./face-server.mjs";
import { mediaCrossReport } from "./media-cross-surface-report.mjs";
import { mediaSmokeFixtures } from "./media-fixtures.mjs";
import { BASE, build, check, makeKey, summary } from "./client.mjs";
import { ROOM, browserEvidenceFailures, browserSnapshotFailures, expectedObject, localHttpOrigin, localResponseFailures, projectionFailures, rangeReadFailures, remoteRequestFailures, sha256Base64Url, smokeExpression } from "./media-cross-surface-checks.mjs";
export { browserEvidenceFailures, browserSnapshotFailures, localHttpOrigin };
const REQUEST_TIMEOUT_MS = 8_000;
const BODY_TIMEOUT_MS = 8_000;
const POW_MAX_BITS = 20;
const POW_MAX_ATTEMPTS = 5_000_000;
const POW_TIMEOUT_MS = 10_000;
function parseOptions(args) {
    const value = (name) => { const index = args.indexOf(name); return index === -1 ? undefined : args[index + 1]; };
    return { backendFace: args.includes("--backend-face"), chrome: value("--chrome"), faceRoot: value("--face-root"), logDir: value("--log-dir") };
}
function cancelBody(response) {
    try { response.body?.cancel().catch(() => {}); } catch { /* Body may already be locked by json()/arrayBuffer(). */ }
}
function withDeadline(promise, timeoutMs, message, onTimeout) {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => { onTimeout?.(); reject(new Error(message)); }, timeoutMs);
        timer.unref?.();
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
async function fetchWithDeadline(url, init, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    timer.unref?.();
    try {
        return await fetch(url, { ...init, signal: controller.signal });
    } catch (error) {
        if (controller.signal.aborted) throw new Error(`timed out fetching local board ${url.pathname}`);
        throw error;
    } finally {
        clearTimeout(timer);
    }
}
export async function boundedLocalFetch(pathOrUrl, init = {}, options = {}) {
    const base = localHttpOrigin(options.base ?? BASE, "base");
    const url = pathOrUrl instanceof URL ? pathOrUrl : new URL(String(pathOrUrl), base);
    if (url.origin !== base) throw new Error(`refusing non-local board request to ${url.origin}`);
    const response = await fetchWithDeadline(url, { ...init, redirect: "manual" }, options.timeoutMs ?? REQUEST_TIMEOUT_MS);
    if (response.status >= 300 && response.status < 400) throw new Error(`refusing redirect from local board ${url.pathname}`);
    return response;
}
export function readJsonBody(response, label, timeoutMs = BODY_TIMEOUT_MS) {
    return withDeadline(response.json(), timeoutMs, `timed out reading ${label} body`, () => cancelBody(response));
}
export function readBytesBody(response, label, timeoutMs = BODY_TIMEOUT_MS) {
    return withDeadline(response.arrayBuffer(), timeoutMs, `timed out reading ${label} body`, () => cancelBody(response));
}
async function optionalJson(response, label) {
    try { return await readJsonBody(response, label); }
    catch (error) {
        if (error instanceof Error && error.message.startsWith("timed out ")) throw error;
        return null;
    }
}
async function json(path) {
    const response = await boundedLocalFetch(path);
    return { status: response.status, body: await optionalJson(response, path), headers: response.headers };
}
async function mcpCall(payload) {
    const response = await boundedLocalFetch("/mcp", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
    return { status: response.status, body: await optionalJson(response, "MCP") };
}
async function signed(agent, method, path, payload) {
    const request = await build(agent, method, path, payload);
    const response = await boundedLocalFetch(request.url, request.init);
    return { status: response.status, body: await optionalJson(response, path) };
}
async function makeLocalAgent(handle) {
    const agent = await makeKey();
    const paid = await solveLocalChallenge(agent.thumbprint);
    const registered = await signed(agent, "POST", "/v1/agents", { public_jwk: agent.jwk, handle, challenge: paid.challenge, solution: paid.solution });
    if (registered.status !== 201) throw new Error("local registration failed");
    return agent;
}
export function validateChallenge(raw) {
    if (raw === null || typeof raw !== "object" || typeof raw.challenge !== "string" || raw.challenge.length < 1 || raw.challenge.length > 128) {
        throw new Error("refusing malformed local challenge");
    }
    if (!Number.isInteger(raw.bits) || raw.bits < 0 || raw.bits > POW_MAX_BITS) {
        throw new Error(`refusing local challenge bits above ${POW_MAX_BITS}`);
    }
    return { challenge: raw.challenge, bits: raw.bits };
}
export function solvePow(rawChallenge, thumbprint, options = {}) {
    const challenge = validateChallenge(rawChallenge);
    const maxAttempts = options.maxAttempts ?? POW_MAX_ATTEMPTS;
    const timeoutMs = options.timeoutMs ?? POW_TIMEOUT_MS;
    if (!Number.isInteger(maxAttempts) || maxAttempts < 1) throw new Error("proof-of-work exceeded local bound before solving");
    const deadline = Date.now() + timeoutMs;
    const prefix = `bulletin-pow:v1:${challenge.challenge}:${thumbprint}:`;
    for (let i = 0; i < maxAttempts; i += 1) {
        if ((i & 2047) === 0 && Date.now() > deadline) throw new Error("proof-of-work exceeded local bound before solving");
        const solution = i.toString(36);
        if (leadingZeroBits(createHash("sha256").update(prefix + solution).digest()) >= challenge.bits) return { challenge: challenge.challenge, solution };
    }
    throw new Error("proof-of-work exceeded local bound before solving");
}
async function solveLocalChallenge(thumbprint) {
    const response = await boundedLocalFetch("/v1/challenge");
    return solvePow(await readJsonBody(response, "challenge"), thumbprint);
}
function leadingZeroBits(bytes) {
    let n = 0;
    for (const byte of bytes) {
        if (byte === 0) { n += 8; continue; }
        return n + Math.clz32(byte) - 24;
    }
    return n;
}
async function startFace(options, base) {
    if (options.faceRoot !== undefined) return startPortfolioFace(options.faceRoot, base);
    if (options.backendFace) return startBackendFace();
    throw new Error("pass --face-root <portfolio repo> for the website check, or --backend-face for the backend face fallback");
}
async function writeReport(logDir, report) {
    if (logDir === undefined) return null;
    const dir = resolve(logDir);
    await mkdir(dir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const path = resolve(dir, `same-media-cross-surface-report-${stamp}.json`);
    await writeFile(path, JSON.stringify(report, null, 2) + "\n", "utf8");
    return path;
}
function checkProjection(label, post, expected) {
    const failures = projectionFailures(post, expected);
    check(label, failures.length === 0, failures.join(", "));
    return failures;
}
function label(expected, text) {
    return expected.fixture === "png" ? text : `${expected.fixture} ${text}`;
}
async function checkHttp(expected, fixture) {
    const post = await json(`/v1/posts/${expected.postId}`);
    const postFailures = checkProjection(label(expected, "HTTP post read carries the same media object"), post.body?.post, expected);
    const feed = await json(`/v1/feed?room=${ROOM}&limit=20`);
    const feedPost = (feed.body?.posts ?? []).find((item) => item.id === expected.postId);
    checkProjection(label(expected, "HTTP feed read finds the same post"), feedPost, expected);
    const media = await boundedLocalFetch(expected.mediaUrl);
    check(label(expected, "HTTP media read serves the same object"), media.status === 200, `got ${media.status}`);
    check(label(expected, `HTTP media read serves ${expected.mediaType}`), media.headers.get("content-type") === expected.mediaType);
    const bytes = new Uint8Array(await readBytesBody(media, "media"));
    check(label(expected, "HTTP media content address re-derives"), sha256Base64Url(bytes) === expected.mediaId);
    const ranged = await boundedLocalFetch(expected.mediaUrl, { headers: { range: "bytes=0-7" } });
    const rangeBytes = new Uint8Array(await readBytesBody(ranged, "media range"));
    const range = { status: ranged.status, contentRange: ranged.headers.get("content-range"), bytes: rangeBytes, bodyLength: rangeBytes.byteLength, bodySha256: sha256Base64Url(rangeBytes), firstEightMatch: false };
    const rangeFailures = rangeReadFailures(range, fixture.bytes);
    range.firstEightMatch = rangeFailures.length === 0;
    check(label(expected, "HTTP media range read carries the first 8 bytes"), rangeFailures.length === 0, rangeFailures.join(", "));
    const rangeHeader = `bytes 0-7/${fixture.bytes.byteLength}`;
    const wrong = rangeReadFailures({ status: 206, contentRange: rangeHeader, bytes: new Uint8Array(8) }, fixture.bytes);
    const empty = rangeReadFailures({ status: 206, contentRange: rangeHeader, bytes: new Uint8Array() }, fixture.bytes);
    check(label(expected, "false-success control catches wrong media range body"), wrong.includes("media range body bytes mismatch"));
    check(label(expected, "false-success control catches empty media range body"), empty.includes("media range body length mismatch"));
    return { failures: postFailures.concat(rangeFailures), range };
}
async function checkMcp(expected) {
    const mcp = await mcpCall({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "board_feed", arguments: { room: ROOM, limit: 20 } } });
    const feed = mcp.body?.result?.structuredContent;
    const post = (feed?.posts ?? []).find((item) => item.id === expected.postId);
    const failures = checkProjection(label(expected, "MCP board_feed reads the same post and media"), post, expected);
    check("MCP feed repeats the untrusted marker", feed?.content_is_untrusted === true);
    const wrong = projectionFailures(post, { ...expected, mediaId: "b".repeat(43) });
    check(label(expected, "false-success control catches a wrong MCP media id"), wrong.includes("media id mismatch"));
    return failures;
}
async function runBrowser(face, options, expected, base) {
    if (options.logDir !== undefined) await mkdir(resolve(options.logDir), { recursive: true });
    const pageUrl = face.kind === "portfolio" ? `${face.origin}${face.path}` : `${face.origin}${face.path}?board=${encodeURIComponent(base)}&room=${ROOM}`;
    return withBrowserPage(async (page) => {
        const result = await navigateAndEvaluate(page, pageUrl, smokeExpression(face.kind, expected), 25_000);
        Object.assign(result.value, await nativeControlPlayback(page, expected));
        return result;
    }, { chrome: options.chrome, tmpRoot: options.logDir ?? tmpdir() });
}
async function nativeControlPlayback(page, expected) {
    if (expected.kind === "image") return {};
    const setup = await page.send("Runtime.evaluate", { expression: nativeControlSetupExpression(expected.mediaUrl), returnByValue: true }, 5_000);
    const state = setup.result?.value ?? {};
    if (state.ready !== true) return { playbackError: state.error ?? "playable media not found", playbackMethod: "native-keyboard-space", playbackNativeControl: false };
    await page.send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32, nativeVirtualKeyCode: 32 }, 5_000);
    await page.send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32, nativeVirtualKeyCode: 32 }, 5_000);
    const result = await page.send("Runtime.evaluate", { expression: playbackResultExpression(expected.mediaUrl, state.playbackStartTime ?? 0), awaitPromise: true, returnByValue: true }, 7_000);
    return { ...state, ...(result.result?.value ?? { playbackError: "playback check returned no value" }) };
}
function nativeControlSetupExpression(mediaUrl) {
    const url = JSON.stringify(mediaUrl);
    return `(() => { const media = Array.from(document.querySelectorAll("audio,video")).find((element) => element.currentSrc === ${url} || element.src === ${url}); if (!media) return { ready: false, error: "missing playable media" }; media.scrollIntoView({ block: "center", inline: "center" }); try { media.pause(); media.currentTime = 0; } catch {} media.focus({ preventScroll: true }); const rect = media.getBoundingClientRect(); const style = getComputedStyle(media); const rawX = rect.left + rect.width / 2; const rawY = rect.top + rect.height / 2; const x = Math.max(1, Math.min(window.innerWidth - 1, rawX)); const y = Math.max(1, Math.min(window.innerHeight - 1, rawY)); const hit = document.elementFromPoint(x, y); const visible = rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || "1") > 0; return { ready: true, playbackMethod: "native-keyboard-space", playbackNativeControl: document.activeElement === media, focused: document.activeElement === media, controlVisible: visible, controlPointerInteractive: style.pointerEvents !== "none", controlCovered: visible && hit !== media && !media.contains(hit), controlClipped: rawX < 0 || rawY < 0 || rawX >= window.innerWidth || rawY >= window.innerHeight, controlRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }, playbackStartTime: media.currentTime || 0 }; })()`;
}
function playbackResultExpression(mediaUrl, startTime) {
    const url = JSON.stringify(mediaUrl);
    return `new Promise((resolve) => { const media = Array.from(document.querySelectorAll("audio,video")).find((element) => element.currentSrc === ${url} || element.src === ${url}); if (!media) return resolve({ playbackError: "missing playable media" }); let max = media.currentTime || 0; const start = ${JSON.stringify(startTime)}; const done = (reason) => { clearInterval(timer); clearTimeout(deadline); max = Math.max(max, media.currentTime || 0); if (!media.paused && !media.ended) media.pause(); const error = media.error ? media.error.message || "media error" : ""; resolve({ playbackStarted: !media.paused || media.ended || max > start, playbackEndTime: media.currentTime || 0, playbackMaxTime: max, playbackPaused: media.paused === true, playbackEnded: media.ended === true, playbackError: error, playbackReason: reason }); }; const timer = setInterval(() => { max = Math.max(max, media.currentTime || 0); if (max - start >= 0.08 || media.ended) done("progress"); }, 50); const deadline = setTimeout(() => done("timeout"), 5_000); })`;
}
async function checkBrowser(face, options, expected, base) {
    const browser = await runBrowser(face, options, expected, base);
    const domFailures = browserSnapshotFailures({ expected, snapshot: browser.value ?? {} });
    const networkFailures = browserEvidenceFailures({ expectedMediaUrl: expected.mediaUrl, sentinelHosts: ["example.invalid"], requests: browser.requests, responses: browser.responses });
    const remoteFailures = remoteRequestFailures(browser.requests, [base, face.origin]);
    const localFailures = localResponseFailures(browser.responses, [base, face.origin]);
    check(label(expected, `${face.kind} browser face renders the exact post/media`), domFailures.length === 0, domFailures.join(", "));
    check(label(expected, "browser requested the board-local media and no sentinel host"), networkFailures.length === 0, networkFailures.join(", "));
    check(label(expected, "browser stayed inside local face and board origins"), remoteFailures.length === 0, remoteFailures.join(", "));
    check(label(expected, "browser local face and board responses succeeded"), localFailures.length === 0, localFailures.join(", "));
    const wrong = browserSnapshotFailures({ expected: { ...expected, mediaId: "c".repeat(43), mediaUrl: `${base}/v1/media/${"c".repeat(43)}` }, snapshot: browser.value ?? {} });
    check(label(expected, "false-success control catches a wrong browser media id"), wrong.includes("browser rendered a different media id"));
    return { browser, domFailures, networkFailures, remoteFailures, localFailures };
}
async function checkInvalidMediaControl(options, source) {
    const expected = { postId: `invalid-${source.fixture}-control`, mediaId: "d".repeat(43), mediaUrl: "", body: `invalid ${source.kind} negative control`, alt: `invalid ${source.kind} negative control`, mediaType: source.mediaType, kind: source.kind, fixture: source.fixture };
    const face = await startInvalidMediaFace(expected);
    expected.mediaUrl = `${face.origin}/v1/media/${expected.mediaId}`;
    try {
        const browser = await runBrowser(face, options, expected, face.origin);
        const domFailures = browserSnapshotFailures({ expected, snapshot: browser.value ?? {} });
        const networkFailures = browserEvidenceFailures({ expectedMediaUrl: expected.mediaUrl, sentinelHosts: ["example.invalid"], requests: browser.requests, responses: browser.responses });
        const remoteFailures = remoteRequestFailures(browser.requests, [face.origin]);
        const localFailures = localResponseFailures(browser.responses, [face.origin]);
        const wanted = `browser ${source.kind} ${source.kind === "image" ? "did not decode" : "did not load/decode"}`;
        check(label(source, "invalid media control keeps network preconditions passing"), networkFailures.length === 0, networkFailures.join(", "));
        check(label(source, "false-success control catches broken browser media"), domFailures.includes(wanted), domFailures.join(", "));
        check(label(source, "invalid media control stayed inside loopback origin"), remoteFailures.length === 0, remoteFailures.join(", "));
        check(label(source, "invalid media control local responses succeeded"), localFailures.length === 0, localFailures.join(", "));
        return { caught: domFailures.includes(wanted), expected_failure: wanted, domFailures, networkFailures, remoteFailures, localFailures, snapshot: browser.value };
    } finally {
        await face.close();
    }
}
async function checkHiddenPlayerControl(options, source, fixture) {
    if (source.kind === "image") return null;
    const expected = { ...source };
    const face = await startHiddenMediaFace(expected, fixture.bytes);
    expected.mediaUrl = `${face.origin}/v1/media/${expected.mediaId}`;
    try {
        const browser = await runBrowser(face, options, expected, face.origin);
        const domFailures = browserSnapshotFailures({ expected, snapshot: browser.value ?? {} });
        const networkFailures = browserEvidenceFailures({ expectedMediaUrl: expected.mediaUrl, sentinelHosts: ["example.invalid"], requests: browser.requests, responses: browser.responses });
        const remoteFailures = remoteRequestFailures(browser.requests, [face.origin]);
        const localFailures = localResponseFailures(browser.responses, [face.origin]);
        const wanted = `browser ${source.kind} controls are not visibly reachable`;
        check(label(source, "false-success control catches hidden native media controls"), domFailures.includes(wanted), domFailures.join(", "));
        check(label(source, "hidden media control kept network preconditions passing"), networkFailures.length === 0, networkFailures.join(", "));
        check(label(source, "hidden media control stayed inside loopback origin"), remoteFailures.length === 0, remoteFailures.join(", "));
        check(label(source, "hidden media control local responses succeeded"), localFailures.length === 0, localFailures.join(", "));
        return { caught: domFailures.includes(wanted), expected_failure: wanted, domFailures, networkFailures, remoteFailures, localFailures, snapshot: browser.value };
    } finally { await face.close(); }
}
async function createSameMediaObject(base, fixture) {
    const nonce = randomBytes(8).toString("hex");
    const expected = expectedObject(base, nonce, sha256Base64Url(fixture.bytes), fixture.bytes.byteLength, fixture);
    const agent = await makeLocalAgent(`smoke-same-media-${nonce}`);
    const uploaded = await signed(agent, "POST", "/v1/media", fixture.bytes);
    const uploadLabel = expected.fixture === "png" ? "signed HTTP upload accepts the generated PNG" : `signed HTTP upload accepts generated ${fixture.mediaType}`;
    const idLabel = expected.fixture === "png" ? "uploaded id is the hash of the generated PNG" : `uploaded id is the hash of generated ${fixture.mediaType}`;
    check(label(expected, uploadLabel), uploaded.status === 201, `got ${uploaded.status}`);
    check(label(expected, idLabel), uploaded.body?.media?.id === expected.mediaId);
    const posted = await signed(agent, "POST", "/v1/posts", { room: ROOM, body: expected.body, attachments: [{ media_id: expected.mediaId, alt: expected.alt }] });
    expected.postId = posted.body?.post?.id;
    check(label(expected, "signed HTTP post accepts the uploaded media id"), posted.status === 201, `got ${posted.status}`);
    check(label(expected, "signed HTTP post returned a post id"), typeof expected.postId === "string");
    return expected;
}
export async function mediaCrossSurfaceChecks(options = parseOptions(process.argv.slice(2))) {
    const base = localHttpOrigin(BASE, "base");
    const face = await startFace(options, base);
    console.log(`same-media smoke: ${base}`);
    let reportPath = null;
    try {
        const discovery = await json("/.well-known/agent-board.json");
        check("local board discovery answers", discovery.status === 200, `got ${discovery.status}`);
        check("local board has media enabled", discovery.body?.media?.enabled === true, "media.enabled is not true");
        const fixtures = await mediaSmokeFixtures({ chrome: options.chrome, tmpRoot: options.logDir ?? tmpdir() });
        const objects = [];
        for (const fixture of fixtures) {
            const expected = await createSameMediaObject(base, fixture);
            const httpCheck = await checkHttp(expected, fixture);
            const mcpFailures = await checkMcp(expected);
            const browserCheck = await checkBrowser(face, options, expected, base);
            const invalidMediaControl = await checkInvalidMediaControl(options, expected);
            const hiddenPlayerControl = await checkHiddenPlayerControl(options, expected, fixture);
            objects.push({ expected, httpPostFailures: httpCheck.failures, httpRange: httpCheck.range, mcpFailures, browserCheck, invalidMediaControl, hiddenPlayerControl, fixture });
        }
        reportPath = await writeReport(options.logDir, mediaCrossReport({ base, face, objects }));
    } finally {
        await face.close();
    }
    if (reportPath !== null) console.log(`private report: ${reportPath}`);
}
function isMain() { return process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href; }
if (isMain()) { try { await mediaCrossSurfaceChecks(); summary(); } catch (error) { console.error(error instanceof Error ? error.message : String(error)); process.exit(1); } }
