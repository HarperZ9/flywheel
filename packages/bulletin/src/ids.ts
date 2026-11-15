/**
 * Sortable identifiers.
 *
 * Post ids sort as plain strings, so the feed pages by id rather than by
 * offset. The post write path may raise the numeric prefix above wall-clock
 * time to keep IDs monotonic when several posts land in one clock tick.
 */

import { encodeBase64Url } from "./bytes.ts";

const MILLIS_WIDTH = 13;

export function newId(nowMillis: number): string {
    const stamp = String(nowMillis).padStart(MILLIS_WIDTH, "0");
    const random = new Uint8Array(6);
    crypto.getRandomValues(random);
    return `${stamp}-${encodeBase64Url(random)}`;
}

/** Logical millis prefix back out of an id. `created_at` remains the wall clock. */
export function idMillis(id: string): number | null {
    const stamp = Number(id.slice(0, MILLIS_WIDTH));
    return Number.isInteger(stamp) ? stamp : null;
}

export function randomToken(bytes = 24): string {
    const buffer = new Uint8Array(bytes);
    crypto.getRandomValues(buffer);
    return encodeBase64Url(buffer);
}
