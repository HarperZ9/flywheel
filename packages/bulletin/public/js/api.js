/**
 * Where the board is, and how this page talks to it.
 *
 * The origin is resolved once, at load, from ?board= or from data-board on the
 * html element. Everything else in the face goes through read(), so there is a
 * single place where a request to the board is made and a single place where a
 * failure is turned into an error a human can read.
 *
 * No function here sends a signed request, and none can: the page holds no key.
 */

const params = new URLSearchParams(location.search);

/** The board origin, without a trailing slash. Empty when nothing configured one. */
export const BOARD = (params.get("board") || document.documentElement.dataset.board || "").replace(/\/$/, "");

/** The query parameters the page starts in, so the caller can restore a view from a link. */
export const START = {
    room: params.get("room"),
    q: params.get("q"),
    thread: params.get("thread"),
};

export async function read(path) {
    const response = await fetch(BOARD + path, { headers: { accept: "application/json" } });
    const body = await response.json().catch(() => null);
    if (!response.ok) {
        // The board answers a failure with RFC 9457 problem details, so the
        // detail line is written for whoever is reading it. Fall back to the
        // status only when there is nothing to quote.
        const detail = body?.detail || body?.error || `${path} returned ${response.status}`;
        throw new Error(detail);
    }
    return body;
}

export function stamp(seconds) {
    const date = new Date(seconds * 1000);
    return `${date.toISOString().replace("T", " ").slice(0, 16)}Z`;
}

/**
 * Keep the address bar in step with the view.
 *
 * A search or an open thread is a place, so it gets a URL that reopens it. The
 * history entry is replaced rather than pushed for the feed, which is where the
 * page starts, and pushed for anything the reader navigated to on purpose.
 */
export function setLocation(view, push) {
    const next = new URLSearchParams();
    if (view.room) {
        next.set("room", view.room);
    }
    if (view.q) {
        next.set("q", view.q);
    }
    if (view.thread) {
        next.set("thread", view.thread);
    }
    if (params.has("board")) {
        next.set("board", params.get("board"));
    }
    const text = next.toString();
    const url = text.length === 0 ? location.pathname : `${location.pathname}?${text}`;
    if (push) {
        history.pushState(view, "", url);
    } else {
        history.replaceState(view, "", url);
    }
}
