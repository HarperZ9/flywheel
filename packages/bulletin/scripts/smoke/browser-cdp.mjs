import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:net";
import { setTimeout as delay } from "node:timers/promises";
const CDP_COMMAND_TIMEOUT_MS = 10_000;
const CHROME_LAUNCH_TIMEOUT_MS = 30_000;
const CHROME_EXIT_TIMEOUT_MS = 2_500;
const STDERR_LIMIT = 4096;
export class Cdp {
    constructor(socket, options = {}) {
        this.socket = socket;
        this.nextId = 1;
        this.pending = new Map();
        this.listeners = new Map();
        this.commandTimeoutMs = options.commandTimeoutMs ?? CDP_COMMAND_TIMEOUT_MS;
        socket.addEventListener("message", (event) => this.message(event.data));
        socket.addEventListener("close", () => this.rejectPending(new Error("CDP socket closed")));
        socket.addEventListener("error", () => this.rejectPending(new Error("CDP socket error")));
    }
    message(raw) {
        const text = typeof raw === "string" ? raw : Buffer.from(raw).toString("utf8");
        const payload = JSON.parse(text);
        if (payload.id !== undefined) {
            const pending = this.pending.get(payload.id);
            if (pending === undefined) return;
            this.pending.delete(payload.id);
            clearTimeout(pending.timer);
            if (payload.error) pending.reject(new Error(payload.error.message));
            else pending.resolve(payload.result ?? {});
            return;
        }
        for (const listener of this.listeners.get(payload.method) ?? []) listener(payload.params ?? {});
    }
    on(method, listener) {
        const listeners = this.listeners.get(method) ?? new Set();
        listeners.add(listener);
        this.listeners.set(method, listeners);
        return () => listeners.delete(listener);
    }
    send(method, params = {}, timeoutMs = this.commandTimeoutMs) {
        const id = this.nextId;
        this.nextId += 1;
        const message = JSON.stringify({ id, method, params });
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.pending.delete(id);
                reject(new Error(`timed out waiting for CDP ${method}`));
            }, timeoutMs);
            timer.unref?.();
            this.pending.set(id, { resolve, reject, timer });
            try {
                this.socket.send(message);
            } catch (error) {
                clearTimeout(timer);
                this.pending.delete(id);
                reject(error);
            }
        });
    }
    rejectPending(error) {
        for (const [id, pending] of this.pending) {
            clearTimeout(pending.timer);
            pending.reject(error);
            this.pending.delete(id);
        }
    }
    pendingCount() {
        return this.pending.size;
    }
    close() {
        this.rejectPending(new Error("CDP socket closed"));
        this.socket.close();
    }
}
function defaultChrome() {
    return process.env.CHROME_PATH || process.env.BROWSER || "chrome";
}
async function freePort() {
    const server = createServer();
    await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolve);
    });
    const address = server.address();
    await new Promise((resolve) => server.close(resolve));
    return address.port;
}
function withTimer(promise, timeoutMs, message, onTimeout) {
    let timer;
    const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => {
            onTimeout?.();
            reject(new Error(message));
        }, timeoutMs);
        timer.unref?.();
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}
export async function fetchJsonWithDeadline(url, timeoutMs, label, init = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    timer.unref?.();
    let response;
    try {
        response = await fetch(url, { ...init, signal: controller.signal });
    } catch (error) {
        if (controller.signal.aborted) throw new Error(`timed out fetching ${label}`);
        throw error;
    } finally {
        clearTimeout(timer);
    }
    if (!response.ok) throw new Error(`${label} returned ${response.status}`);
    return withTimer(response.json(), timeoutMs, `timed out reading ${label} body`, () => response.body?.cancel().catch(() => {}));
}
async function waitForJson(url, timeoutMs, child, stderr, state) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
        if (state.error !== null) throw new Error(`Chrome launch failed: ${state.error.message}`);
        if (child.exitCode !== null || child.signalCode !== null) throw chromeExitError("Chrome exited before opening DevTools", stderr, child);
        try {
            const remaining = Math.max(1, Math.min(750, deadline - Date.now()));
            return await fetchJsonWithDeadline(url, remaining, "Chrome DevTools");
        } catch {
            await delay(100);
        }
    }
    throw chromeExitError(`Chrome did not open DevTools at ${url}`, stderr, child);
}
function chromeExitError(prefix, stderr, child) {
    const detail = stderr.text.trim();
    const status = child.exitCode !== null ? `exit ${child.exitCode}` : child.signalCode ? `signal ${child.signalCode}` : "still running";
    const suffix = detail === "" ? "" : `; stderr${stderr.truncated ? " tail" : ""}: ${detail}`;
    return new Error(`${prefix} (${status})${suffix}`);
}
async function openSocket(url, timeoutMs, commandTimeoutMs) {
    const socket = new WebSocket(url);
    await withTimer(new Promise((resolve, reject) => {
        socket.addEventListener("open", resolve, { once: true });
        socket.addEventListener("error", () => reject(new Error(`could not open ${url}`)), { once: true });
    }), timeoutMs, `timed out opening ${url}`, () => socket.close());
    return new Cdp(socket, { commandTimeoutMs });
}
async function openPage(port, options) {
    const endpoint = `http://127.0.0.1:${port}/json/new?${encodeURIComponent("about:blank")}`;
    const tab = await fetchJsonWithDeadline(endpoint, options.commandTimeoutMs, "Chrome new tab", { method: "PUT" });
    if (typeof tab.webSocketDebuggerUrl !== "string") throw new Error("Chrome did not return a page websocket");
    return openSocket(tab.webSocketDebuggerUrl, options.commandTimeoutMs, options.commandTimeoutMs);
}
function waitForEvent(page, method, timeoutMs) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
            off();
            reject(new Error(`timed out waiting for ${method}`));
        }, timeoutMs);
        timer.unref?.();
        const off = page.on(method, (params) => {
            clearTimeout(timer);
            off();
            resolve(params);
        });
    });
}
function collectStderr(child, limit) {
    const stderr = { text: "", truncated: false };
    child.stderr?.setEncoding("utf8");
    child.stderr?.on("data", (chunk) => {
        stderr.text += chunk;
        if (stderr.text.length > limit) {
            stderr.text = stderr.text.slice(-limit);
            stderr.truncated = true;
        }
    });
    return stderr;
}
export function chromeLaunchArgs(port, profile, options = {}) {
    const noSandbox = (options.env ?? process.env).BULLETIN_CHROME_NO_SANDBOX === "1";
    const args = [
        "--headless=new",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-gpu",
        "--disable-sync",
        "--no-default-browser-check",
        "--no-first-run",
        "--remote-debugging-address=127.0.0.1",
        `--remote-debugging-port=${port}`,
        `--user-data-dir=${profile}`,
        "about:blank",
    ];
    if (noSandbox) args.splice(1, 0, "--no-sandbox");
    return args;
}
function spawnChrome(port, profile, chrome, stderrLimit) {
    const child = spawn(chrome, chromeLaunchArgs(port, profile), { stdio: ["ignore", "ignore", "pipe"], windowsHide: true });
    const state = { error: null };
    child.once("error", (error) => { state.error = error; });
    return { child, stderr: collectStderr(child, stderrLimit), state };
}
async function waitForExit(child, timeoutMs) {
    if (child.exitCode !== null || child.signalCode !== null) return true;
    return withTimer(new Promise((resolve) => child.once("exit", () => resolve(true))), timeoutMs, "exit wait elapsed")
        .catch(() => false);
}
async function cleanupBrowser(page, child, profile, options) {
    const errors = [];
    let browserCloseError = null;
    if (page !== null) {
        try { await page.send("Browser.close", {}, 1_500); }
        catch (error) { browserCloseError = error; }
        page.close();
    }
    if (child !== null && !(await waitForExit(child, options.exitTimeoutMs))) {
        if (browserCloseError !== null) errors.push(`Browser.close failed: ${browserCloseError.message}`);
        child.kill();
        if (!(await waitForExit(child, options.exitTimeoutMs))) {
            child.kill("SIGKILL");
            if (!(await waitForExit(child, options.exitTimeoutMs))) errors.push("Chrome did not exit after kill");
        }
    }
    for (let attempt = 0; attempt < 5; attempt += 1) {
        try {
            await rm(profile, { recursive: true, force: true });
            return errors.length === 0 ? null : new Error(errors.join("; "));
        } catch (error) {
            if (attempt === 4) errors.push(`could not remove profile ${profile}: ${error.message}`);
            else await delay(100);
        }
    }
    return new Error(errors.join("; "));
}
export async function withBrowserPage(action, options = {}) {
    const runtime = {
        chrome: options.chrome ?? defaultChrome(),
        commandTimeoutMs: options.commandTimeoutMs ?? CDP_COMMAND_TIMEOUT_MS,
        exitTimeoutMs: options.exitTimeoutMs ?? CHROME_EXIT_TIMEOUT_MS,
        launchTimeoutMs: options.launchTimeoutMs ?? CHROME_LAUNCH_TIMEOUT_MS,
        stderrLimit: options.stderrLimit ?? STDERR_LIMIT,
        tmpRoot: options.tmpRoot ?? tmpdir(),
    };
    const port = await freePort();
    const profile = await mkdtemp(join(runtime.tmpRoot, "bulletin-chrome-"));
    let child = null;
    let page = null;
    let result;
    let thrown = null;
    try {
        const launched = spawnChrome(port, profile, runtime.chrome, runtime.stderrLimit);
        child = launched.child;
        await waitForJson(`http://127.0.0.1:${port}/json/version`, runtime.launchTimeoutMs, child, launched.stderr, launched.state);
        page = await openPage(port, runtime);
        result = await action(page);
    } catch (error) {
        thrown = error;
    }
    const cleanupError = await cleanupBrowser(page, child, profile, runtime);
    if (thrown !== null) {
        if (cleanupError !== null) thrown.message += `; cleanup failure: ${cleanupError.message}`;
        throw thrown;
    }
    if (cleanupError !== null) throw new Error(`Chrome cleanup failed: ${cleanupError.message}`);
    return result;
}
export async function navigateAndEvaluate(page, url, expression, timeoutMs = 20_000) {
    const requests = [];
    const responses = [];
    const consoleMessages = [];
    const pageErrors = [];
    page.on("Network.requestWillBeSent", (event) => requests.push({ url: event.request?.url ?? "", type: event.type ?? "" }));
    page.on("Network.responseReceived", (event) => responses.push({ url: event.response?.url ?? "", status: event.response?.status ?? 0 }));
    page.on("Runtime.consoleAPICalled", (event) => consoleMessages.push(event.args?.map((arg) => arg.value ?? arg.description ?? "").join(" ") ?? ""));
    page.on("Runtime.exceptionThrown", (event) => pageErrors.push(event.exceptionDetails?.text ?? "runtime exception"));
    await Promise.all([page.send("Network.enable"), page.send("Page.enable"), page.send("Runtime.enable")]);
    const loaded = waitForEvent(page, "Page.loadEventFired", timeoutMs);
    try {
        await page.send("Page.navigate", { url }, timeoutMs);
        await loaded;
    } catch (error) {
        loaded.catch(() => {});
        throw error;
    }
    const result = await page.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, timeout: timeoutMs }, timeoutMs);
    if (result.exceptionDetails !== undefined) throw new Error(result.exceptionDetails.text ?? "browser evaluation failed");
    const location = await page.send("Runtime.evaluate", { expression: "location.href", returnByValue: true }, timeoutMs);
    return { value: result.result?.value, requests, responses, consoleMessages, pageErrors, finalUrl: location.result?.value };
}
