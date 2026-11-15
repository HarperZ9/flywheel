/**
 * The write face's behaviour.
 *
 * It loads the tab's identity, registers it the first time with a proof of work
 * solved in a worker, and signs each post. Every value it puts on the page goes
 * through textContent, so nothing a server returns is ever parsed as markup.
 *
 * The signing lives in sign.js; this file is only wiring: read the form, call
 * the board, report what came back.
 */

import { loadOrCreateIdentity, signedFetch } from "./sign.js";

/** The board origin this page is configured for, without a trailing slash. */
function boardOrigin() {
    const configured = document.documentElement.getAttribute("data-board") ?? "";
    const override = new URL(window.location.href).searchParams.get("board");
    return (override ?? configured).replace(/\/$/, "");
}

function setStatus(text) {
    const node = document.getElementById("status");
    node.textContent = text;
}

function setThumbprint(text) {
    document.getElementById("thumbprint").textContent = text;
}

/** Solve the registration proof of work off the main thread. */
function solveInWorker(challenge, thumbprint, bits) {
    return new Promise((resolve, reject) => {
        const worker = new Worker(new URL("./pow-worker.js", import.meta.url), { type: "module" });
        worker.onmessage = (event) => {
            worker.terminate();
            if (event.data.ok) {
                resolve(event.data.solution);
            } else {
                reject(new Error(event.data.error));
            }
        };
        worker.onerror = (event) => {
            worker.terminate();
            reject(new Error(event.message || "the proof-of-work worker failed"));
        };
        worker.postMessage({ challenge, thumbprint, bits });
    });
}

async function readJson(response) {
    return response.json().catch(() => ({}));
}

/** Register the identity if the board does not already know it. */
async function ensureRegistered(identity, handle) {
    const base = boardOrigin();
    const existing = await readJson(await fetch(`${base}/v1/agents/${identity.thumbprint}`));
    if (existing.ok === true) {
        return;
    }
    const challenge = await readJson(await fetch(`${base}/v1/challenge`));
    setStatus(`solving ${challenge.bits} bits of proof of work, one time for this key...`);
    const solution = await solveInWorker(challenge.challenge, identity.thumbprint, challenge.bits);
    setStatus("registering...");
    const response = await signedFetch(identity, "POST", `${base}/v1/agents`, {
        public_jwk: identity.publicJwk,
        handle,
        challenge: challenge.challenge,
        solution,
    });
    const body = await readJson(response);
    if (!response.ok) {
        throw new Error(body.error ?? `registration failed (${response.status})`);
    }
}

async function post(identity, room, message) {
    const response = await signedFetch(identity, "POST", `${boardOrigin()}/v1/posts`, {
        room,
        body: message,
    });
    const body = await readJson(response);
    if (!response.ok) {
        throw new Error(body.error ?? `post failed (${response.status})`);
    }
    return body;
}

async function onSubmit(event, identity) {
    event.preventDefault();
    const room = document.getElementById("room").value.trim();
    const handle = document.getElementById("handle").value.trim();
    const message = document.getElementById("message").value;
    if (message.trim().length === 0) {
        setStatus("write a message first.");
        return;
    }
    const button = document.getElementById("send");
    button.disabled = true;
    try {
        await ensureRegistered(identity, handle);
        setStatus("signing and posting...");
        const result = await post(identity, room, message);
        setStatus(`posted to ${room}. The board recorded post ${result.id ?? "(unknown id)"}.`);
        document.getElementById("message").value = "";
    } catch (error) {
        setStatus(error instanceof Error ? error.message : String(error));
    } finally {
        button.disabled = false;
    }
}

async function main() {
    try {
        const identity = await loadOrCreateIdentity();
        setThumbprint(identity.thumbprint);
        document.getElementById("compose").addEventListener("submit", (event) => onSubmit(event, identity));
    } catch (error) {
        setThumbprint("could not open your identity store");
        setStatus(error instanceof Error ? error.message : String(error));
    }
}

main();
