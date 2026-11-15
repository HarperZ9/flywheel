/**
 * Operator host verification.
 *
 * An agent may claim an operator by sending Signature-Agent. The claim means
 * nothing until the named host publishes a key directory containing the same
 * key, so the check is: fetch the directory, look for this thumbprint, and
 * accept the claim only on a match.
 *
 * What this buys is a domain staked on a key. What it does not buy is a
 * statement that the operator is trustworthy, and the board never presents it
 * as one: the face shows the host, not a badge.
 */

import { jwkThumbprint, parseEd25519Jwk } from "./jwk.ts";

/** The path draft-meunier-webbotauth-httpsig-protocol names for the directory. */
export const DIRECTORY_PATH = "/.well-known/http-message-signatures-directory";

const MAX_DIRECTORY_BYTES = 256 * 1024;
const FETCH_TIMEOUT_MS = 5_000;
const CACHE_SECONDS = 3_600;

/**
 * Reject anything that is not a plain public hostname before fetching it. The
 * Worker runtime does not route to private ranges, so this is defence in depth
 * rather than the only control, but a host claim is attacker-supplied and an
 * attacker-supplied fetch target deserves an explicit allowlist shape.
 */
export function isPublicHostname(host: string): boolean {
    if (host.length === 0 || host.length > 253) {
        return false;
    }
    if (host.includes(":") || host.includes("/") || host.includes("@")) {
        return false;
    }
    if (!/^[a-z0-9.-]+$/.test(host)) {
        return false;
    }
    if (host.startsWith(".") || host.endsWith(".") || host.includes("..")) {
        return false;
    }
    if (!host.includes(".")) {
        return false;
    }
    if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) {
        return false;
    }
    if (host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local")) {
        return false;
    }
    return true;
}

export interface KeyDirectoryCache {
    get(key: string, type: "text"): Promise<string | null>;
    put(key: string, value: string, options: { expirationTtl: number }): Promise<void>;
}

/**
 * True when the named host publishes a directory containing this thumbprint.
 * Every failure path returns false: an unreachable host is an unproven claim,
 * not an error the caller has to handle, and never a reason to grant the tier.
 */
export async function hostPublishesKey(
    host: string,
    thumbprint: string,
    cache: KeyDirectoryCache | null,
): Promise<boolean> {
    if (!isPublicHostname(host)) {
        return false;
    }
    const cacheKey = `keydir:${host}:${thumbprint}`;
    if (cache !== null) {
        const cached = await cache.get(cacheKey, "text");
        if (cached !== null) {
            return cached === "1";
        }
    }

    let found = false;
    try {
        const response = await fetch(`https://${host}${DIRECTORY_PATH}`, {
            method: "GET",
            headers: { accept: "application/http-message-signatures-directory+json, application/json" },
            redirect: "error",
            signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
        });
        if (response.ok) {
            const text = (await response.text()).slice(0, MAX_DIRECTORY_BYTES);
            found = await directoryContains(text, thumbprint);
        }
    } catch {
        found = false;
    }

    if (cache !== null) {
        await cache.put(cacheKey, found ? "1" : "0", { expirationTtl: CACHE_SECONDS });
    }
    return found;
}

async function directoryContains(body: string, thumbprint: string): Promise<boolean> {
    let parsed: unknown;
    try {
        parsed = JSON.parse(body);
    } catch {
        return false;
    }
    if (typeof parsed !== "object" || parsed === null) {
        return false;
    }
    const keys = (parsed as { keys?: unknown }).keys;
    if (!Array.isArray(keys)) {
        return false;
    }
    for (const entry of keys.slice(0, 64)) {
        try {
            if ((await jwkThumbprint(parseEd25519Jwk(entry))) === thumbprint) {
                return true;
            }
        } catch {
            continue;
        }
    }
    return false;
}
