import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { lstat, readFile, realpath } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { extname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BACKEND_PUBLIC = fileURLToPath(new URL("../../public/", import.meta.url));
const BACKEND_ASSETS = Object.freeze(["index.html", "board.css", "js/api.js", "js/app.js", "js/media.js", "js/render.js"]);
const BACKEND_ASSET_SET = new Set(BACKEND_ASSETS);

export const PORTFOLIO_ASSETS = Object.freeze([
    "bulletin.html",
    "favicon.svg",
    "brand/aperture-mark-96.webp",
    "system/doc.css",
    "system/reading.css",
    "system/nav.css",
    "system/export.css",
    "system/print.css",
    "system/routes.js",
    "system/nav.js",
    "system/export.js",
    "system/theme-entry.js",
    "system/theme.js",
    "system/theme.css",
    "system/fonts/hanken-grotesk.woff2",
    "system/fonts/conso-regular.woff2",
    "system/fonts/conso-semibold.woff2",
    "system/fonts/conso-bold.woff2",
    "system/fonts/conso-regular.woff",
    "system/fonts/conso-semibold.woff",
    "system/fonts/conso-bold.woff",
    "system/bulletin-board.js",
    "system/bulletin-work.js",
    "system/bulletin/compose.js",
    "system/bulletin/sign.js",
    "system/bulletin/pow-worker.js",
    "system/tokens.css",
    "system/plate.css",
    "system/notebook-sheet.css",
    "system/notebook-diagram.css",
    "system/page-components.css",
    "system/fonts/conso-medium.woff2",
    "system/fonts/conso-medium.woff",
    "system/fonts/conso-regularitalic.woff2",
    "system/fonts/conso-regularitalic.woff",
    "system/fonts/accession/variable/AccessionText[INKS,wght].woff2",
    "system/fonts/accession/variable/AccessionText-Italic[INKS,wght].woff2",
    "system/fonts/accession/variable/AccessionDisplay[wght].woff2",
    "system/fonts/accession/variable/AccessionMono[wght].woff2",
]);
const PORTFOLIO_ASSET_SET = new Set(PORTFOLIO_ASSETS);

function contentType(filePath) {
    switch (extname(filePath).toLowerCase()) {
        case ".html": return "text/html; charset=utf-8";
        case ".css": return "text/css; charset=utf-8";
        case ".js": return "text/javascript; charset=utf-8";
        case ".json": return "application/json; charset=utf-8";
        case ".svg": return "image/svg+xml";
        case ".png": return "image/png";
        case ".webp": return "image/webp";
        case ".woff2": return "font/woff2";
        case ".woff": return "font/woff";
        default: return "application/octet-stream";
    }
}

function inside(root, candidate) {
    const rel = relative(root, candidate);
    return rel === "" || (rel.length > 0 && !rel.startsWith("..") && !isAbsolute(rel));
}

function escapeAttribute(value) {
    return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function escapeHtml(value) {
    return escapeAttribute(value).replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function portfolioHtmlWithLocalBoard(html, boardOrigin) {
    const escaped = escapeAttribute(boardOrigin);
    const pattern = /(<div\b(?=[^>]*\bid="board")(?=[^>]*\bdata-board=")[^>]*\bdata-board=")[^"]*(")/;
    const rewritten = html.replace(pattern, `$1${escaped}$2`);
    if (rewritten === html) throw new Error("portfolio bulletin.html has no board data-board attribute to override");
    return rewritten;
}

async function fileRoot(root) {
    const lexicalRoot = resolve(root);
    return { root: lexicalRoot, realRoot: await realpath(lexicalRoot) };
}

async function rejectSymlinkParts(root, relPath, label) {
    let current = root;
    for (const part of relPath.split("/")) {
        current = resolve(current, part);
        if ((await lstat(current)).isSymbolicLink()) throw new Error(`refusing symlinked ${label} ${relPath}`);
    }
}

async function safeFile(rootInfo, relPath, label) {
    const lexical = resolve(rootInfo.root, relPath);
    if (!inside(rootInfo.root, lexical)) throw new Error(`refusing ${label} outside root ${relPath}`);
    await rejectSymlinkParts(rootInfo.root, relPath, label);
    const real = await realpath(lexical);
    if (!inside(rootInfo.realRoot, real)) throw new Error(`refusing ${label} outside real root ${relPath}`);
    return real;
}

async function sha256File(path) {
    return createHash("sha256").update(await readFile(path)).digest("hex");
}

async function receiptFor(rootInfo, relPath, label) {
    const path = await safeFile(rootInfo, relPath, label);
    return { path: relPath, sha256: await sha256File(path) };
}

function gitHead(root) {
    const result = spawnSync("git", ["-C", root, "rev-parse", "HEAD"], { encoding: "utf8", windowsHide: true });
    return result.status === 0 ? result.stdout.trim() : null;
}

function gitStatus(root) {
    const result = spawnSync("git", ["-C", root, "status", "--short"], { encoding: "utf8", windowsHide: true });
    return result.status === 0 ? result.stdout.trim() : null;
}

async function optionalReceipt(rootInfo, relPath) {
    try {
        return await receiptFor(rootInfo, relPath, "portfolio receipt");
    } catch {
        return null;
    }
}

async function portfolioReceipt(rootInfo) {
    return {
        kind: "portfolio",
        root: rootInfo.root,
        real_root: rootInfo.realRoot,
        head: gitHead(rootInfo.root),
        status_short: gitStatus(rootInfo.root),
        source_receipt: await optionalReceipt(rootInfo, "source-receipt.json"),
        assets: await Promise.all(PORTFOLIO_ASSETS.map((asset) => receiptFor(rootInfo, asset, "portfolio asset"))),
    };
}

function requestedAsset(requestUrl) {
    let leaf = "";
    try {
        const url = new URL(requestUrl ?? "/", "http://127.0.0.1");
        leaf = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "bulletin.html";
    } catch {
        return { status: 400, body: "bad request\n" };
    }
    const normalized = leaf.replace(/\/+/g, "/");
    const parts = normalized.split("/");
    if (normalized.includes("\0") || normalized.includes("\\") || parts.some((part) => part === "" || part === "." || part === "..")) {
        return { status: 403, body: "forbidden\n" };
    }
    return PORTFOLIO_ASSET_SET.has(normalized) ? { asset: normalized } : { status: 404, body: "not found\n" };
}

async function startServer(rootInfo, boardOrigin) {
    const server = createServer(async (request, response) => {
        try {
            const target = requestedAsset(request.url);
            if (target.asset === undefined) {
                response.writeHead(target.status, { "content-type": "text/plain; charset=utf-8" }).end(target.body);
                return;
            }
            const path = await safeFile(rootInfo, target.asset, "portfolio asset");
            const body = target.asset === "bulletin.html"
                ? portfolioHtmlWithLocalBoard(await readFile(path, "utf8"), boardOrigin)
                : await readFile(path);
            response.writeHead(200, { "content-type": contentType(target.asset), "cache-control": "no-store" });
            response.end(body);
        } catch (error) {
            const forbidden = error instanceof Error && error.message.startsWith("refusing ");
            response.writeHead(forbidden ? 403 : 404, { "content-type": "text/plain; charset=utf-8" }).end(forbidden ? "forbidden\n" : "not found\n");
        }
    });
    await new Promise((resolveListen, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolveListen);
    });
    return server;
}

export async function startBackendFace() {
    const rootInfo = await fileRoot(BACKEND_PUBLIC);
    const server = await startBackendServer(rootInfo);
    const address = server.address();
    return { kind: "backend", origin: `http://127.0.0.1:${address.port}`, path: "/", receipt: await backendFaceReceipt(rootInfo), close: () => new Promise((resolveClose) => server.close(resolveClose)) };
}

function backendAsset(requestUrl) {
    const url = new URL(requestUrl ?? "/", "http://127.0.0.1");
    const leaf = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html";
    if (leaf === "favicon.ico" || leaf.startsWith("system/fonts/")) return { empty: true };
    return BACKEND_ASSET_SET.has(leaf) ? { asset: leaf } : { status: 404, body: "not found\n" };
}

async function startBackendServer(rootInfo) {
    const server = createServer(async (request, response) => {
        try {
            const target = backendAsset(request.url);
            if (target.empty) return response.writeHead(204, { "cache-control": "no-store" }).end();
            if (target.asset === undefined) return response.writeHead(target.status, { "content-type": "text/plain; charset=utf-8" }).end(target.body);
            const path = await safeFile(rootInfo, target.asset, "backend asset");
            response.writeHead(200, { "content-type": contentType(target.asset), "cache-control": "no-store" }).end(await readFile(path));
        } catch {
            response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("not found\n");
        }
    });
    await new Promise((resolveListen, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolveListen);
    });
    return server;
}

export async function startPortfolioFace(faceRoot, boardOrigin) {
    const rootInfo = await fileRoot(faceRoot);
    const receipt = await portfolioReceipt(rootInfo);
    const server = await startServer(rootInfo, boardOrigin);
    const address = server.address();
    return { kind: "portfolio", origin: `http://127.0.0.1:${address.port}`, path: "/bulletin.html", receipt, close: () => new Promise((resolveClose) => server.close(resolveClose)) };
}

function mediaTag(expected, attrs = "") {
    const src = `/v1/media/${escapeAttribute(expected.mediaId)}`;
    const extra = attrs === "" ? "" : ` ${attrs}`;
    if (expected.kind === "audio") return `<audio class="media"${extra} controls preload="none" src="${src}"></audio>`;
    if (expected.kind === "video") return `<video class="media"${extra} controls playsinline preload="metadata" src="${src}"></video>`;
    return `<img class="media"${extra} src="${src}" alt="${escapeAttribute(expected.alt)}">`;
}

function controlHtml(expected, attrs = "") {
    return `<div id="board"><article data-post-id="${escapeAttribute(expected.postId)}"><p class="post-body">${escapeHtml(expected.body)}</p><figure data-media-id="${escapeAttribute(expected.mediaId)}">${mediaTag(expected, attrs)}<figcaption class="post-attachment-caption">${escapeHtml(expected.alt)}</figcaption></figure></article></div>`;
}

async function startSyntheticMediaFace(expected, bytes, path, attrs = "") {
    const server = createServer((request, response) => {
        const url = new URL(request.url ?? "/", "http://127.0.0.1");
        if (url.pathname === `/v1/media/${expected.mediaId}`) return response.writeHead(200, { "content-type": expected.mediaType, "cache-control": "no-store" }).end(bytes);
        if (url.pathname === "/favicon.ico") return response.writeHead(204, { "cache-control": "no-store" }).end();
        if (url.pathname === path) return response.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" }).end(controlHtml(expected, attrs));
        response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("not found\n");
    });
    await new Promise((resolveListen, reject) => {
        server.once("error", reject);
        server.listen(0, "127.0.0.1", resolveListen);
    });
    const address = server.address();
    return { kind: "portfolio", origin: `http://127.0.0.1:${address.port}`, path, close: () => new Promise((resolveClose) => server.close(resolveClose)) };
}

export function startInvalidMediaFace(expected) {
    return startSyntheticMediaFace(expected, Buffer.from("this is not a valid media fixture"), "/invalid-image-control.html");
}

export function startHiddenMediaFace(expected, bytes) {
    return startSyntheticMediaFace(expected, bytes, "/hidden-media-control.html", 'data-hidden-control="true" style="display:none"');
}

export const startInvalidImageFace = startInvalidMediaFace;

export async function backendFaceReceipt(rootInfo = null) {
    rootInfo ??= await fileRoot(BACKEND_PUBLIC);
    return {
        kind: "backend",
        root: rootInfo.root,
        real_root: rootInfo.realRoot,
        assets: await Promise.all(BACKEND_ASSETS.map((asset) => receiptFor(rootInfo, asset, "backend asset"))),
    };
}




