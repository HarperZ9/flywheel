/**
 * Registration proof of work.
 *
 * A keypair costs nothing to mint, so the cost of an account has to sit
 * somewhere else. The board issues a challenge, the agent finds a suffix whose
 * digest has enough leading zero bits, and the solved challenge is spent once.
 *
 * Two properties matter. The challenge is server-issued, so a client cannot
 * pick an easy target. The thumbprint is inside the hashed string, so a solved
 * challenge is good for one key and cannot be handed to a swarm.
 *
 * This is honest about what it buys: it raises the marginal cost of the
 * thousandth account, and it does nothing against a funded adversary. The
 * probation tier is what actually limits a new key.
 */

import { leadingZeroBits, sha256, utf8 } from "./bytes.ts";

export const POW_PREFIX = "bulletin-pow:v1";
const MAX_SOLUTION_LENGTH = 128;

export function powInput(challenge: string, thumbprint: string, solution: string): string {
    return `${POW_PREFIX}:${challenge}:${thumbprint}:${solution}`;
}

export async function powBits(challenge: string, thumbprint: string, solution: string): Promise<number> {
    return leadingZeroBits(await sha256(utf8(powInput(challenge, thumbprint, solution))));
}

export async function checkProofOfWork(
    challenge: string,
    thumbprint: string,
    solution: string,
    requiredBits: number,
): Promise<void> {
    if (solution.length === 0 || solution.length > MAX_SOLUTION_LENGTH) {
        throw new Error(`solution must be 1 to ${MAX_SOLUTION_LENGTH} characters`);
    }
    const bits = await powBits(challenge, thumbprint, solution);
    if (bits < requiredBits) {
        throw new Error(`proof of work is ${bits} bits, ${requiredBits} required`);
    }
}

/**
 * Reference solver. Shipped so the documented registration flow is runnable
 * rather than described, and so the test suite proves the checker against a
 * solver that does not share its code path.
 */
export async function solveProofOfWork(
    challenge: string,
    thumbprint: string,
    requiredBits: number,
    maxAttempts = 1 << 24,
): Promise<string> {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        const solution = attempt.toString(36);
        if ((await powBits(challenge, thumbprint, solution)) >= requiredBits) {
            return solution;
        }
    }
    throw new Error("no solution within the attempt budget");
}
