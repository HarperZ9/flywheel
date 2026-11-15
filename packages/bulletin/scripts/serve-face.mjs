/**
 * A static server for the face, for local checking only.
 *
 * wrangler serves the board and this serves the page that reads it, from a
 * different origin, which is the arrangement the deployed board is in. It sets
 * the module MIME type because a browser refuses to run a module script served
 * as anything else, and that refusal is silent apart from one console line.
 *
 * Path segments are filtered rather than normalised, so there is no traversal to
 * get wrong: a request can only name files that are already under public/.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../public/", import.meta.url));
const PORT = Number(process.argv[2] || 8080);
const TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
};

function target(requestUrl) {
    const parts = decodeURIComponent(new URL(requestUrl, "http://x").pathname)
        .split("/")
        .filter((part) => part.length > 0 && part !== "." && part !== "..");
    return join(ROOT, ...(parts.length === 0 ? ["index.html"] : parts));
}

createServer(async (request, response) => {
    const file = target(request.url);
    try {
        const body = await readFile(file);
        response.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
        response.end(body);
    } catch {
        response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
        response.end("not found\n");
    }
}).listen(PORT, "127.0.0.1", () => console.log(`face on http://127.0.0.1:${PORT}`));
