/**
 * The shapes a signature check works with, and the one error it throws.
 *
 * These live apart from both the parser and the verifier so neither has to
 * import the other to name a type, which keeps the module graph a tree.
 */

export const WEB_BOT_AUTH_TAG = "web-bot-auth";

export interface SignatureMember {
    label: string;
    covered: string[];
    params: Map<string, string | number | boolean>;
    /** The received parameter text, reused verbatim as the @signature-params value. */
    raw: string;
}

export interface SignedRequest {
    method: string;
    url: string;
    headers: Headers;
}

export class SignatureError extends Error {
    readonly status: number;
    readonly hint: string;
    /**
     * The stable code a client branches on. It defaults to the common case so
     * most throw sites stay one line each, and the few failures a client must
     * tell apart set it explicitly.
     */
    readonly code: string;

    constructor(message: string, hint: string, status = 401, code = "signature_invalid") {
        super(message);
        this.name = "SignatureError";
        this.status = status;
        this.hint = hint;
        this.code = code;
    }
}
