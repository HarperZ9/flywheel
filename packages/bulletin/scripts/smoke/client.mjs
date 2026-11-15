/**
 * The signing client the smoke test drives the board with.
 *
 * It is deliberately written from the specification rather than from the board
 * own code: nothing here is imported from src/. If the two ever disagree about
 * what a signature base looks like, the run fails, which is the whole point.
 */

import { webcrypto as crypto } from "node:crypto";

const args = Object.fromEntries(
    process.argv.slice(2).reduce((acc, v, i, a) => (v.startsWith("--") ? [...acc, [v.slice(2), a[i + 1]]] : acc), []),
);
const BASE = (args.base ?? "http://127.0.0.1:8787").replace(/\/$/, "");
const enc = new TextEncoder();

let passed = 0;
const failures = [];
function check(name, condition, detail) {
    if (condition) {
        passed += 1;
        console.log(`  ok   ${name}`);
    } else {
        failures.push(name);
        console.log(`  FAIL ${name}${detail === undefined ? "" : ` -- ${detail}`}`);
    }
}

const b64 = (b) => Buffer.from(b).toString("base64");
const b64url = (b) => Buffer.from(b).toString("base64url");
const sha256 = async (b) => new Uint8Array(await crypto.subtle.digest("SHA-256", b));

function leadingZeroBits(bytes) {
    let n = 0;
    for (const byte of bytes) {
        if (byte === 0) {
            n += 8;
            continue;
        }
        return n + Math.clz32(byte) - 24;
    }
    return n;
}

/** A key and its thumbprint, with no account behind it yet. */
async function makeKey() {
    const pair = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
    const pub = await crypto.subtle.exportKey("jwk", pair.publicKey);
    const jwk = { kty: "OKP", crv: "Ed25519", x: pub.x };
    const thumbprint = b64url(await sha256(enc.encode(JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x }))));
    return { privateKey: pair.privateKey, jwk, thumbprint };
}

/**
 * A fresh challenge, solved for one thumbprint. Registration and rotation both
 * pay this, and rotation pays it for the key arriving rather than the key
 * asking, so the thumbprint is a parameter.
 */
async function solveChallenge(thumbprint) {
    const challenge = await (await fetch(`${BASE}/v1/challenge`)).json();
    const prefix = `bulletin-pow:v1:${challenge.challenge}:${thumbprint}:`;
    for (let i = 0; ; i += 1) {
        const solution = i.toString(36);
        if (leadingZeroBits(await sha256(enc.encode(prefix + solution))) >= challenge.bits) {
            return { challenge: challenge.challenge, solution };
        }
    }
}

async function makeAgent(handle) {
    const agent = await makeKey();
    const paid = await solveChallenge(agent.thumbprint);
    const registered = await send(agent, "POST", "/v1/agents", {
        public_jwk: agent.jwk,
        handle,
        challenge: paid.challenge,
        solution: paid.solution,
    });
    if (registered.status !== 201) throw new Error(`registration failed: ${JSON.stringify(registered.body)}`);
    return agent;
}

async function build(agent, method, path, payload) {
    // An upload signs the file itself, so the digest has to cover the raw bytes
    // rather than a JSON spelling of them.
    const raw = payload instanceof Uint8Array;
    const body = raw ? payload : payload === undefined ? "" : JSON.stringify(payload);
    const url = new URL(BASE + path);
    const created = Math.floor(Date.now() / 1000);
    const nonce = b64url(crypto.getRandomValues(new Uint8Array(16)));
    const digest = `sha-256=:${b64(await sha256(raw ? body : enc.encode(body)))}:`;
    const params =
        "(\"@method\" \"@authority\" \"@path\" \"@query\" \"content-digest\")" +
        `;created=${created};expires=${created + 120};keyid="${agent.thumbprint}"` +
        `;nonce="${nonce}";tag="web-bot-auth";alg="ed25519"`;
    const base = [
        `"@method": ${method}`,
        `"@authority": ${url.host.toLowerCase()}`,
        `"@path": ${url.pathname}`,
        `"@query": ${url.search === "" ? "?" : url.search}`,
        `"content-digest": ${digest}`,
        `"@signature-params": ${params}`,
    ].join("\n");
    const sig = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, agent.privateKey, enc.encode(base)));
    const init = {
        method,
        headers: {
            "content-digest": digest,
            "signature-input": `sig1=${params}`,
            signature: `sig1=:${b64(sig)}:`,
        },
    };
    // A signed GET covers the digest of an empty body. fetch refuses to attach
    // a body to a GET at all, so the header goes out on its own.
    if (method !== "GET") {
        init.headers["content-type"] = raw ? "application/octet-stream" : "application/json";
        init.body = body;
    }
    return { url, init };
}

async function send(agent, method, path, payload) {
    const { url, init } = await build(agent, method, path, payload);
    const response = await fetch(url, init);
    return { status: response.status, body: await response.json().catch(() => null) };
}

export function summary() {
    console.log(`\n${passed} passed, ${failures.length} failed`);
    if (failures.length > 0) {
        console.log(failures.map((f) => `  - ${f}`).join("\n"));
        process.exit(1);
    }
}

export { BASE, build, check, makeAgent, makeKey, send, solveChallenge };
