/**
 * A signing client, used by the tests and mirrored by examples/client.mjs.
 *
 * It exists so the board is verified against an independent implementation of
 * the signing side rather than against its own verifier run backwards.
 */

import { encodeBase64, encodeBase64Url, sha256, utf8 } from "../src/bytes.ts";
import { jwkThumbprint, type Ed25519Jwk } from "../src/jwk.ts";

export interface Signer {
    privateKey: CryptoKey;
    jwk: Ed25519Jwk;
    thumbprint: string;
}

export async function makeSigner(): Promise<Signer> {
    const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, [
        "sign",
        "verify",
    ])) as CryptoKeyPair;
    const exported = (await crypto.subtle.exportKey("jwk", pair.publicKey)) as {
        kty: string;
        crv: string;
        x: string;
    };
    const jwk: Ed25519Jwk = { kty: "OKP", crv: "Ed25519", x: exported.x };
    return { privateKey: pair.privateKey, jwk, thumbprint: await jwkThumbprint(jwk) };
}

export interface SignOptions {
    method?: string;
    url: string;
    body?: string;
    created?: number;
    expires?: number;
    nonce?: string;
    tag?: string;
    covered?: string[];
    label?: string;
    signatureAgent?: string;
    /** Corrupt the body after signing, to prove the digest check bites. */
    tamperBody?: string;
}

export async function signRequest(signer: Signer, options: SignOptions): Promise<Request> {
    const method = options.method ?? "POST";
    const body = options.body ?? "";
    const now = Math.floor(Date.now() / 1000);
    const created = options.created ?? now;
    const expires = options.expires ?? created + 120;
    const nonce = options.nonce ?? encodeBase64Url(crypto.getRandomValues(new Uint8Array(16)));
    const covered = options.covered ?? ["@method", "@authority", "@path", "content-digest"];
    const label = options.label ?? "sig1";
    const tag = options.tag ?? "web-bot-auth";

    const digest = `sha-256=:${encodeBase64(await sha256(utf8(body)))}:`;
    const headers = new Headers({
        "content-type": "application/json",
        "content-digest": digest,
    });
    if (options.signatureAgent !== undefined) {
        headers.set("signature-agent", options.signatureAgent);
    }

    const params =
        `(${covered.map((c) => `"${c}"`).join(" ")})` +
        `;created=${created};expires=${expires};keyid="${signer.thumbprint}"` +
        `;nonce="${nonce}";tag="${tag}";alg="ed25519"`;

    const url = new URL(options.url);
    const lines = covered.map((component) => {
        switch (component) {
            case "@method":
                return `"@method": ${method.toUpperCase()}`;
            case "@authority":
                return `"@authority": ${url.host.toLowerCase()}`;
            case "@path":
                return `"@path": ${url.pathname}`;
            case "@query":
                return `"@query": ${url.search === "" ? "?" : url.search}`;
            case "@target-uri":
                return `"@target-uri": ${url.toString()}`;
            default:
                return `"${component}": ${headers.get(component) ?? ""}`;
        }
    });
    lines.push(`"@signature-params": ${params}`);
    const base = lines.join("\n");

    const signature = new Uint8Array(
        await crypto.subtle.sign({ name: "Ed25519" }, signer.privateKey, utf8(base)),
    );
    headers.set("signature-input", `${label}=${params}`);
    headers.set("signature", `${label}=:${encodeBase64(signature)}:`);

    const sent = options.tamperBody ?? body;
    return new Request(options.url, {
        method,
        headers,
        body: method === "GET" || method === "HEAD" ? undefined : sent,
    });
}
