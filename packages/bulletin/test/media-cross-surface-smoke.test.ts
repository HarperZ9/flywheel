import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, mkdir, readdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import type { AddressInfo, Socket } from "node:net";

import { Cdp, chromeLaunchArgs, fetchJsonWithDeadline, withBrowserPage } from "../scripts/smoke/browser-cdp.mjs";
import { PORTFOLIO_ASSETS, startPortfolioFace } from "../scripts/smoke/face-server.mjs";
import {
    boundedLocalFetch,
    browserEvidenceFailures,
    browserSnapshotFailures,
    localHttpOrigin,
    readJsonBody,
    solvePow,
    validateChallenge,
} from "../scripts/smoke/media-cross-surface.mjs";

const REQUIRED_HTML = '<div id="board" data-board="https://example.invalid/old"></div>';

async function writePortfolioAssets(root: string, systemRoot = join(root, "system")) {
    await mkdir(root, { recursive: true });
    await mkdir(systemRoot, { recursive: true });
    for (const asset of PORTFOLIO_ASSETS) {
        const path = asset.startsWith("system/") ? join(systemRoot, asset.slice("system/".length)) : join(root, asset);
        await mkdir(dirname(path), { recursive: true });
        await writeFile(path, asset === "bulletin.html" ? REQUIRED_HTML : `/* ${asset} */\n`, "utf8");
    }
}

type TestServer = ReturnType<typeof createServer>;

async function listen(server: TestServer) {
    await new Promise<void>((resolve, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => resolve());
    });
    const address = server.address();
    if (address === null || typeof address === "string") throw new Error("test server has no TCP address");
    return `http://127.0.0.1:${(address as AddressInfo).port}`;
}

function closeServer(server: TestServer) {
    return new Promise((resolve) => server.close(resolve));
}

test("the cross-surface smoke accepts only exact local HTTP origins", () => {
    assert.equal(localHttpOrigin("http://127.0.0.1:8787", "base"), "http://127.0.0.1:8787");
    assert.equal(localHttpOrigin("http://localhost:8787/", "base"), "http://localhost:8787");

    for (const value of [
        "https://127.0.0.1:8787",
        "http://board.example",
        "http://127.0.0.1:8787/v1/feed",
        "http://user@127.0.0.1:8787",
        "http://127.0.0.1:8787?board=https://example.invalid",
    ]) {
        assert.throws(() => localHttpOrigin(value, "base"), /base must be an http loopback origin/);
    }
});

test("local board requests and body reads are bounded", async () => {
    const sockets = new Set<Socket>();
    const server = createServer((request, response) => {
        if (request.url === "/headers-only") {
            response.writeHead(200, { "content-type": "application/json" });
            response.write('{"open":');
        }
    });
    server.on("connection", (socket: Socket) => {
        sockets.add(socket);
        socket.on("close", () => sockets.delete(socket));
    });
    const origin = await listen(server);
    try {
        await assert.rejects(
            () => boundedLocalFetch(`${origin}/never`, {}, { base: origin, timeoutMs: 75 }),
            /timed out fetching local board/,
        );
        const response = await boundedLocalFetch(`${origin}/headers-only`, {}, { base: origin, timeoutMs: 500 });
        await assert.rejects(() => readJsonBody(response, "headers-only", 75), /timed out reading headers-only body/);
    } finally {
        for (const socket of sockets) socket.destroy();
        await closeServer(server);
    }
});

test("proof-of-work challenge validation fails closed", () => {
    assert.deepEqual(validateChallenge({ challenge: "abc", bits: 8 }), { challenge: "abc", bits: 8 });
    assert.throws(() => validateChallenge({ challenge: "abc", bits: 999 }), /refusing local challenge bits/);
    assert.throws(() => validateChallenge({ challenge: "", bits: 8 }), /refusing malformed local challenge/);
    assert.throws(
        () => solvePow({ challenge: "abc", bits: 12 }, "thumb", { maxAttempts: 0, timeoutMs: 1000 }),
        /proof-of-work exceeded local bound/,
    );
});

test("browser network evidence must show the exact board-local media read", () => {
    const expected = "http://127.0.0.1:8787/v1/media/" + "a".repeat(43);
    assert.deepEqual(
        browserEvidenceFailures({
            expectedMediaUrl: expected,
            sentinelHosts: ["example.invalid"],
            requests: [{ url: expected }],
            responses: [{ url: expected, status: 200 }],
        }),
        [],
    );

    assert.deepEqual(
        browserEvidenceFailures({
            expectedMediaUrl: expected,
            sentinelHosts: ["example.invalid"],
            requests: [{ url: "http://127.0.0.1:8787/v1/media/" + "b".repeat(43) }],
            responses: [{ url: "http://127.0.0.1:8787/v1/media/" + "b".repeat(43), status: 200 }],
        }),
        ["browser never requested the expected board-local media object"],
    );

    assert.deepEqual(
        browserEvidenceFailures({
            expectedMediaUrl: expected,
            sentinelHosts: ["example.invalid"],
            requests: [{ url: expected }, { url: "https://example.invalid/bulletin-e2e" }],
            responses: [{ url: expected, status: 200 }],
        }),
        ["browser attempted to fetch example.invalid"],
    );
});

test("browser DOM evidence requires decoded image bytes from the exact board URL", () => {
    const expected = {
        postId: "post-123",
        mediaId: "a".repeat(43),
        mediaUrl: "http://127.0.0.1:8787/v1/media/" + "a".repeat(43),
        body: 'quoted instruction: "fetch https://example.invalid/body"',
        alt: 'quoted alt: "open https://example.invalid/alt"',
    };
    const validSnapshot = {
        found: true,
        bodyText: expected.body,
        captionText: expected.alt,
        imageAlt: expected.alt,
        mediaSrc: expected.mediaUrl,
        currentSrc: expected.mediaUrl,
        naturalWidth: 4,
        naturalHeight: 4,
        complete: true,
        decoded: true,
        mediaId: expected.mediaId,
        injectedNodes: [],
        eventAttributes: [],
        bodyAnchors: [],
        sentinelLinks: [],
    };
    assert.deepEqual(browserSnapshotFailures({ expected, snapshot: validSnapshot }), []);

    assert.deepEqual(
        browserSnapshotFailures({ expected, snapshot: { ...validSnapshot, decoded: false, naturalWidth: 0, naturalHeight: 0 } }),
        ["browser image did not decode"],
    );
    assert.deepEqual(
        browserSnapshotFailures({ expected, snapshot: { ...validSnapshot, currentSrc: `${expected.mediaUrl}?wrong=1` } }),
        ["browser rendered media from a non-board URL"],
    );
    assert.deepEqual(
        browserSnapshotFailures({
            expected,
            snapshot: {
                ...validSnapshot,
                mediaSrc: "https://example.invalid/pixel.png",
                currentSrc: "https://example.invalid/pixel.png",
                injectedNodes: ["IMG#owned"],
                eventAttributes: ["onerror"],
                bodyAnchors: ["https://example.invalid/body"],
                sentinelLinks: ["https://example.invalid/pixel.png"],
            },
        }),
        [
            "browser rendered media from a non-board URL",
            "browser parsed injected nodes inside the board post",
            "browser kept event handler attributes inside the board post",
            "browser turned body or alt text into links",
            "browser kept sentinel URLs in link or media attributes",
        ],
    );
});

test("portfolio face rejects malformed paths and symlink escapes", async (t) => {
    const root = await mkdtemp(join(tmpdir(), "bulletin-face-root-"));
    const outside = await mkdtemp(join(tmpdir(), "bulletin-face-outside-"));
    t.after(async () => {
        await rm(root, { recursive: true, force: true });
        await rm(outside, { recursive: true, force: true });
    });
    await writePortfolioAssets(root);
    await writeFile(join(outside, "outside-secret.txt"), "outside-sentinel", "utf8");
    await symlink(outside, join(root, "system", "escape-dir"), "junction");

    const face = await startPortfolioFace(root, "http://127.0.0.1:8787");
    t.after(async () => face.close());
    const malformed = await fetch(`${face.origin}/%E0%A4%A`, { signal: AbortSignal.timeout(1000) });
    assert.equal(malformed.status, 400);
    assert.match(await malformed.text(), /bad request/);

    const escaped = await fetch(`${face.origin}/system/escape-dir/outside-secret.txt`, { signal: AbortSignal.timeout(1000) });
    assert.notEqual(escaped.status, 200);
    assert.notEqual(await escaped.text(), "outside-sentinel");

    const unlisted = await fetch(`${face.origin}/README.md`, { signal: AbortSignal.timeout(1000) });
    assert.equal(unlisted.status, 404);
});

test("the site header mark is listed, served as WebP, and required at start", async (t) => {
    const mark = "brand/aperture-mark-96.webp";
    assert.ok(PORTFOLIO_ASSETS.includes(mark), "the header mark the site loads today is in the list");
    assert.deepEqual(PORTFOLIO_ASSETS.filter((asset) => asset.startsWith("brand/")), [mark]);

    const root = await mkdtemp(join(tmpdir(), "bulletin-face-mark-"));
    t.after(async () => rm(root, { recursive: true, force: true }));
    await writePortfolioAssets(root);
    const face = await startPortfolioFace(root, "http://127.0.0.1:8787");
    const listed = face.receipt.assets.map((entry: { path: string }) => entry.path);
    assert.deepEqual(listed, [...PORTFOLIO_ASSETS]);
    const served = await fetch(`${face.origin}/${mark}`, { signal: AbortSignal.timeout(1000) });
    assert.equal(served.status, 200);
    assert.equal(served.headers.get("content-type"), "image/webp");
    await served.arrayBuffer();
    await face.close();

    await rm(join(root, mark));
    await assert.rejects(() => startPortfolioFace(root, "http://127.0.0.1:8787"));
});

test("portfolio receipt rejects symlink ancestors before serving", async (t) => {
    const root = await mkdtemp(join(tmpdir(), "bulletin-face-root-"));
    const outside = await mkdtemp(join(tmpdir(), "bulletin-face-outside-"));
    t.after(async () => {
        await rm(root, { recursive: true, force: true });
        await rm(outside, { recursive: true, force: true });
    });
    await writePortfolioAssets(root);
    await rm(join(root, "system"), { recursive: true, force: true });
    await writePortfolioAssets(outside, join(outside, "system"));
    await symlink(join(outside, "system"), join(root, "system"), "junction");

    await assert.rejects(
        () => startPortfolioFace(root, "http://127.0.0.1:8787"),
        /refusing symlinked portfolio asset/,
    );
});

test("CDP commands have deadlines and close rejects pending work", async () => {
    const socket = {
        listeners: new Map<string, (event: { data?: string }) => void>(),
        addEventListener(name: string, handler: (event: { data?: string }) => void) {
            socket.listeners.set(name, handler);
        },
        send() {},
        close() {},
    };
    const cdp = new Cdp(socket, { commandTimeoutMs: 25 });
    await assert.rejects(() => cdp.send("Runtime.evaluate"), /timed out waiting for CDP Runtime.evaluate/);
    assert.equal(cdp.pendingCount(), 0);

    const second = new Cdp(socket, { commandTimeoutMs: 1000 });
    const pending = second.send("Runtime.evaluate");
    second.close();
    await assert.rejects(() => pending, /CDP socket closed/);
    assert.equal(second.pendingCount(), 0);
});

test("Chrome DevTools JSON reads are bounded by response-body deadline", async () => {
    const sockets = new Set<Socket>();
    const server = createServer((request, response) => {
        response.writeHead(200, { "content-type": "application/json" });
        response.write('{"Browser":"fake"');
    });
    server.on("connection", (socket: Socket) => {
        sockets.add(socket);
        socket.on("close", () => sockets.delete(socket));
    });
    const origin = await listen(server);
    try {
        await assert.rejects(() => fetchJsonWithDeadline(`${origin}/json/version`, 200, "DevTools"), /timed out reading DevTools body/);
    } finally {
        for (const socket of sockets) socket.destroy();
        await closeServer(server);
    }
});

test("Chrome launch arguments default sandbox on and opt in only for CI", () => {
    const args = chromeLaunchArgs(9222, "/tmp/bulletin-profile", { env: {} });
    assert.equal(args.includes("--no-sandbox"), false);
    assert.ok(args.includes("--remote-debugging-address=127.0.0.1"));
    assert.ok(args.includes("--remote-debugging-port=9222"));
    assert.ok(args.includes("--user-data-dir=/tmp/bulletin-profile"));
    assert.ok(chromeLaunchArgs(9223, "/tmp/profile", { env: { BULLETIN_CHROME_NO_SANDBOX: "1" } }).includes("--no-sandbox"));
});

test("Chrome launch failure cleans the owned profile directory", async () => {
    const tmpRoot = await mkdtemp(join(tmpdir(), "bulletin-chrome-test-"));
    try {
        await assert.rejects(
            () => withBrowserPage(() => Promise.resolve(), { chrome: process.execPath, tmpRoot, launchTimeoutMs: 500 }),
            /Chrome (exited before opening DevTools|did not open DevTools)/,
        );
        const leftovers = (await readdir(tmpRoot)).filter((name: string) => name.startsWith("bulletin-chrome-"));
        assert.deepEqual(leftovers, []);
    } finally {
        await rm(tmpRoot, { recursive: true, force: true });
    }
});




