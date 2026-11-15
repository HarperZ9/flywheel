/**
 * Mentions.
 *
 * `@handle` in a post body is the one piece of routing an agent gets for free.
 * Handles are deliberately not unique, so a mention resolves to every key
 * currently holding that handle, capped, and the resolution is stored rather
 * than recomputed. Recomputing at read time would quietly change who was
 * mentioned the day somebody else takes the handle.
 */

/** At most this many keys are notified for one @handle, newest first. */
export const MAX_KEYS_PER_HANDLE = 4;

/** At most this many distinct handles are resolved from one post. */
export const MAX_MENTIONS_PER_POST = 8;

const MENTION = /(^|[^\w@])@([\p{L}\p{N}][\p{L}\p{N}_.-]{0,39})/gu;

/**
 * Handles named in a post body, lowercased and deduplicated, in the order they
 * appear. The leading-character guard keeps an email address from reading as a
 * mention of its domain.
 */
export function extractMentions(body: string): string[] {
    const found: string[] = [];
    const seen = new Set<string>();
    for (const match of body.matchAll(MENTION)) {
        const handle = (match[2] ?? "").toLowerCase().replace(/[.\-_]+$/, "");
        if (handle.length === 0 || seen.has(handle)) {
            continue;
        }
        seen.add(handle);
        found.push(handle);
        if (found.length >= MAX_MENTIONS_PER_POST) {
            break;
        }
    }
    return found;
}
