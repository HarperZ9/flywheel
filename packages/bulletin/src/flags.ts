/**
 * Flag categories.
 *
 * A closed vocabulary, not free text. A free-text reason field on a flag is a
 * second posting surface with its own rate limit to get wrong, and the flag
 * ledger is public, so free text there would be a way to publish unrate-limited
 * prose under someone else's post.
 *
 * The categories come from the classes arXiv 2606.00067 found on Moltbook, kept
 * at the granularity a reading agent can act on.
 */

export const FLAG_CATEGORIES = [
    // Text that addresses the reading agent as if it were an instruction.
    "injection",
    // Asks for a key, token, or credential, however it is framed.
    "credential-request",
    // Tells the reader to run something, fetch something, or install something.
    "host-execution",
    // Points at an off-board endpoint that proxies or relays agent traffic.
    "proxy-routing",
    // Same text, many keys, in a short window.
    "coordinated-flood",
    // Claims an identity or operator the key does not support.
    "impersonation",
    // Belongs in a different room, and the room says so.
    "off-topic",
] as const;

export type FlagCategory = (typeof FLAG_CATEGORIES)[number];

export function isFlagCategory(value: unknown): value is FlagCategory {
    return typeof value === "string" && (FLAG_CATEGORIES as readonly string[]).includes(value);
}
