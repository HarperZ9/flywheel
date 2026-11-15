/**
 * Proof-of-work worker.
 *
 * Registration proof of work is a tight hashing loop. At the board's target it
 * runs long enough to stall a frame, so it belongs off the main thread. The
 * page posts {challenge, thumbprint, bits}; this answers {ok, solution} or
 * {ok:false, error}. It shares the one solver in sign.js, so the worker and the
 * page never drift on how a solution is formed.
 */

import { solveProofOfWork } from "./sign.js";

self.onmessage = async (event) => {
    const { challenge, thumbprint, bits } = event.data;
    try {
        const solution = await solveProofOfWork(challenge, thumbprint, bits);
        self.postMessage({ ok: true, solution });
    } catch (error) {
        self.postMessage({ ok: false, error: error instanceof Error ? error.message : String(error) });
    }
};
