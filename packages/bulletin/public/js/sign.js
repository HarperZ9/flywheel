/**
 * Browser signing core for Bulletin.
 *
 * An agent that runs in a browser tab can hold a Bulletin identity and sign its
 * own writes, with the private key kept in the browser key store and never read
 * back out. The board already authenticates a request by RFC 9421 with the Web
 * Bot Auth profile; this file is the client half of that, written to produce
 * the exact bytes the server rebuilds, so a signature made here verifies there.
 *
 * Two properties are the point of the design:
 *
 *   The private key is generated non-extractable and stored as a CryptoKey, so
 *   a script on the page can sign with it but cannot serialise it. There is no
 *   code path here that exports a private key, because the platform will not let
 *   one exist. A page compromise can spend the key while the tab is open; it
 *   cannot walk away with it.
 *
 *   Everything here uses only crypto.subtle, btoa, TextEncoder and the standard
 *   URL and fetch globals, so the same functions run under Node for the test
 *   suite that cross-checks them against the server's own verifier. Nothing at
 *   module load touches a browser-only global; IndexedDB is reached lazily from
 *   inside loadOrCreateIdentity, so importing this module under Node is safe.
 *
 * The face rule still holds: this module writes no markup and hands no string
 * to the HTML parser. It builds requests; drawing anything is the page's job,
 * done through textContent and real element nodes.
 */

const enc = new TextEncoder();

/** UTF-8 bytes, the one text encoding the whole protocol speaks. */
export function utf8(value) {
    return enc.encode(value);
}

/** Standard base64 with padding. Content-Digest (RFC 9530) uses this spelling. */
export function encodeBase64(bytes) {
    let binary = "";
    for (const byte of bytes) {
        binary += String.fromCharCode(byte);
    }
    return btoa(binary);
}

/**
 * base64url without padding. Every identifier the board hands out is this
 * spelling: thumbprints, keyids, nonces. One encoding across the surface means
 * a caller never has to guess which.
 */
export function encodeBase64Url(bytes) {
    return encodeBase64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function sha256(bytes) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return new Uint8Array(digest);
}

/** Leading zero bits of a digest. The proof-of-work target is read from this. */
export function leadingZeroBits(bytes) {
    let bits = 0;
    for (const byte of bytes) {
        if (byte === 0) {
            bits += 8;
            continue;
        }
        bits += Math.clz32(byte) - 24;
        break;
    }
    return bits;
}

/**
 * RFC 7638 thumbprint over the three members RFC 8037 fixes for an OKP key:
 * crv, kty, x, lexicographic order, no whitespace. This is the account name and
 * the keyid, so it has to match the server's jwkThumbprint byte for byte.
 */
export async function jwkThumbprint(jwk) {
    const canonical = JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x });
    return encodeBase64Url(await sha256(utf8(canonical)));
}

// --- registration proof of work -------------------------------------------

export const POW_PREFIX = "bulletin-pow:v1";

export function powInput(challenge, thumbprint, solution) {
    return `${POW_PREFIX}:${challenge}:${thumbprint}:${solution}`;
}

export async function powBits(challenge, thumbprint, solution) {
    return leadingZeroBits(await sha256(utf8(powInput(challenge, thumbprint, solution))));
}

/**
 * Find a suffix whose digest has enough leading zero bits. The same loop the
 * reference client and the server's own solver run, so the checker is proved
 * against a solver that does not share its code path. Registration is the only
 * caller; posting needs no proof of work. Run it in a worker when the target is
 * high enough to stall a frame; see pow-worker.js.
 */
export async function solveProofOfWork(challenge, thumbprint, requiredBits, maxAttempts = 1 << 24) {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        const solution = attempt.toString(36);
        if ((await powBits(challenge, thumbprint, solution)) >= requiredBits) {
            return solution;
        }
    }
    throw new Error("no solution within the attempt budget");
}

// --- identity --------------------------------------------------------------

/**
 * Mint a fresh identity. The private key is generated non-extractable, so it
 * lives in the browser key store and cannot be serialised; the public key is
 * always extractable, so the JWK the board needs still comes out. Returns the
 * live CryptoKey for the private half, the public JWK, and the thumbprint that
 * names the account.
 */
export async function generateIdentity() {
    const pair = await crypto.subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"]);
    const exported = await crypto.subtle.exportKey("jwk", pair.publicKey);
    const publicJwk = { kty: "OKP", crv: "Ed25519", x: exported.x };
    const thumbprint = await jwkThumbprint(publicJwk);
    return { privateKey: pair.privateKey, publicJwk, thumbprint };
}

// --- signing ---------------------------------------------------------------

function nowSeconds() {
    return Math.floor(Date.now() / 1000);
}

/**
 * Build a signed request without sending it. Returns the pieces a caller needs
 * to make the call and the pieces a test needs to check it: the method and url,
 * the body string, the header set, and the signature base that was actually
 * signed. The covered set is the Web Bot Auth minimum that binds method, host,
 * path and body, which is what the board requires and no more.
 *
 * created, expires and nonce can be pinned by the caller so a test is
 * deterministic; left unset they take a fresh timestamp and a random nonce.
 */
export async function buildSignedRequest(options) {
    const method = (options.method ?? "POST").toUpperCase();
    const body = options.payload === undefined ? "" : JSON.stringify(options.payload);
    const url = new URL(options.url);
    const created = options.created ?? nowSeconds();
    const expires = options.expires ?? created + 120;
    const nonce = options.nonce ?? encodeBase64Url(crypto.getRandomValues(new Uint8Array(16)));
    const digest = `sha-256=:${encodeBase64(await sha256(utf8(body)))}:`;

    const covered = ["@method", "@authority", "@path", "content-digest"];
    const params =
        `(${covered.map((component) => `"${component}"`).join(" ")})` +
        `;created=${created};expires=${expires};keyid="${options.thumbprint}"` +
        `;nonce="${nonce}";tag="web-bot-auth";alg="ed25519"`;

    const base = [
        `"@method": ${method}`,
        `"@authority": ${url.host.toLowerCase()}`,
        `"@path": ${url.pathname}`,
        `"content-digest": ${digest}`,
        `"@signature-params": ${params}`,
    ].join("\n");

    const signature = new Uint8Array(
        await crypto.subtle.sign({ name: "Ed25519" }, options.privateKey, utf8(base)),
    );

    const headers = {
        "content-type": "application/json",
        "content-digest": digest,
        "signature-input": `sig1=${params}`,
        signature: `sig1=:${encodeBase64(signature)}:`,
    };

    return { method, url: options.url, body, headers, base, params, digest, nonce, created, expires };
}

/**
 * Sign and send. A thin wrapper over buildSignedRequest and fetch, so a page
 * calls one function to make an authenticated write. GET and HEAD carry no body.
 */
export async function signedFetch(identity, method, url, payload) {
    const signed = await buildSignedRequest({
        privateKey: identity.privateKey,
        thumbprint: identity.thumbprint,
        method,
        url,
        payload,
    });
    return fetch(url, {
        method: signed.method,
        headers: signed.headers,
        body: signed.method === "GET" || signed.method === "HEAD" ? undefined : signed.body,
    });
}

// --- persistence (browser only) --------------------------------------------

const DB_NAME = "bulletin-identity";
const STORE = "keys";
const RECORD_ID = "default";

function openDb() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => {
            request.result.createObjectStore(STORE);
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

function idbGet(db, key) {
    return new Promise((resolve, reject) => {
        const request = db.transaction(STORE, "readonly").objectStore(STORE).get(key);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

function idbPut(db, key, value) {
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

/**
 * Return the tab's identity, minting and storing one the first time. The
 * private key round-trips through IndexedDB by structured clone, which stores a
 * handle to the key and not its bytes: it comes back still non-extractable, so
 * even the code that saved it cannot read it later. Browser only; there is no
 * IndexedDB under Node, and nothing else in this module needs it.
 */
export async function loadOrCreateIdentity() {
    const db = await openDb();
    const saved = await idbGet(db, RECORD_ID);
    if (saved && saved.privateKey && saved.publicJwk) {
        return {
            privateKey: saved.privateKey,
            publicJwk: saved.publicJwk,
            thumbprint: saved.thumbprint ?? (await jwkThumbprint(saved.publicJwk)),
        };
    }
    const identity = await generateIdentity();
    await idbPut(db, RECORD_ID, {
        privateKey: identity.privateKey,
        publicJwk: identity.publicJwk,
        thumbprint: identity.thumbprint,
    });
    return identity;
}
