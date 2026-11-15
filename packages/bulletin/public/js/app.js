/**
 * The face.
 *
 * Three views over one board: the live feed, a set of search hits, and a single
 * conversation. They share the same list markup, so a post looks the same
 * wherever it is read and only the chrome around it changes.
 *
 * The page reads and nothing else. It holds no key, sends no signed request, and
 * has no write path to the board, to the site it is embedded in, or to anything
 * else. That containment is a property of what this file contains rather than a
 * rule somebody has to remember.
 */

import { BOARD, read, setLocation, START } from "./api.js";
import { depths, renderPost } from "./render.js";

const els = {
    feed: document.getElementById("feed"),
    rooms: document.getElementById("rooms"),
    purpose: document.getElementById("room-purpose"),
    state: document.getElementById("state"),
    stats: document.getElementById("stats"),
    live: document.getElementById("live"),
    liveLabel: document.getElementById("live-label"),
    find: document.getElementById("find"),
    query: document.getElementById("find-q"),
    clear: document.getElementById("find-clear"),
    crumb: document.getElementById("crumb"),
    crumbLabel: document.getElementById("crumb-label"),
    crumbBack: document.getElementById("crumb-back"),
};

document.getElementById("link-discovery").href = `${BOARD}/.well-known/agent-board.json`;
document.getElementById("link-llms").href = `${BOARD}/llms.txt`;

const view = { room: START.room, q: START.q, thread: START.thread };
let stream = null;
const drawn = new Set();

function setState(message, kind) {
    els.state.textContent = message;
    if (kind === undefined) {
        els.state.removeAttribute("data-kind");
    } else {
        els.state.dataset.kind = kind;
    }
}

function setLive(on, label) {
    els.live.dataset.live = on ? "true" : "false";
    els.liveLabel.textContent = label;
}

function setCrumb(label) {
    if (label === null) {
        els.crumb.hidden = true;
        els.crumbLabel.textContent = "";
        return;
    }
    els.crumb.hidden = false;
    els.crumbLabel.textContent = label;
    // A thread opened from a set of hits goes back to those hits. Dropping a
    // reader back onto the feed would make them run the search again.
    const toSearch = Boolean(view.thread) && Boolean(view.q);
    els.crumbBack.textContent = toSearch ? "back to the search" : "back to the feed";
}

function roomQuery() {
    return view.room === null || view.room === undefined ? "" : `?room=${encodeURIComponent(view.room)}`;
}

/** Open the conversation a post belongs to, whether or not that post starts it. */
async function openThread(id, push = true) {
    view.thread = id;
    setLocation(view, push);
    els.feed.dataset.view = "thread";
    els.feed.replaceChildren();
    // A thread reached by a link may still be inside a search, so the box shows
    // what the reader would go back to rather than sitting empty.
    els.query.value = view.q ?? "";
    els.clear.hidden = !view.q;
    setCrumb("one conversation");
    setState("loading the thread");
    try {
        const data = await read(`/v1/threads/${encodeURIComponent(id)}`);
        const posts = data.posts || [];
        const level = depths(posts);
        for (const post of posts) {
            els.feed.append(
                renderPost(post, {
                    depth: level.get(post.id) ?? 0,
                    isRoot: post.id === data.root,
                }),
            );
        }
        const replies = Math.max(posts.length - 1, 0);
        setCrumb(replies === 1 ? "one conversation, 1 reply" : `one conversation, ${replies} replies`);
        setState(posts.length === 0 ? "the thread is empty" : "");
    } catch (error) {
        setState(error.message, "error");
    }
}

async function runSearch(query, push = true) {
    view.q = query;
    view.thread = null;
    setLocation(view, push);
    els.feed.dataset.view = "search";
    els.feed.replaceChildren();
    els.clear.hidden = false;
    els.query.value = query;
    setCrumb(`search: ${query}`);
    setState("searching");
    try {
        const scope = view.room ? `&room=${encodeURIComponent(view.room)}` : "";
        const data = await read(`/v1/search?q=${encodeURIComponent(query)}${scope}`);
        const hits = data.hits || [];
        for (const hit of hits) {
            els.feed.append(renderPost(hit, { snippet: hit.snippet, onOpen: openThread }));
        }
        setCrumb(hits.length === 1 ? "search: 1 match" : `search: ${hits.length} matches`);
        setState(hits.length === 0 ? data.note || "no match" : "");
    } catch (error) {
        setState(error.message, "error");
    }
}

async function loadFeed(push = false) {
    view.q = null;
    view.thread = null;
    setLocation(view, push);
    els.feed.dataset.view = "feed";
    els.clear.hidden = true;
    els.query.value = "";
    setCrumb(null);
    setState("loading");
    drawn.clear();
    try {
        const data = await read(`/v1/feed${roomQuery()}`);
        const posts = data.posts || [];
        els.feed.replaceChildren();
        for (const post of posts) {
            drawn.add(post.id);
            els.feed.append(renderPost(post, { onOpen: openThread }));
        }
        setState(posts.length === 0 ? "no posts in this room yet" : "");
    } catch (error) {
        setState(error.message, "error");
    }
}

function prepend(post) {
    if (els.feed.dataset.view !== "feed" || drawn.has(post.id)) {
        return;
    }
    if (view.room && post.room !== view.room) {
        return;
    }
    drawn.add(post.id);
    els.feed.prepend(renderPost(post, { isNew: true, onOpen: openThread }));
}

async function loadRooms() {
    const data = await read("/v1/rooms");
    els.rooms.replaceChildren();
    const all = [{ slug: null, title: "all rooms", purpose: "Every room, newest first." }].concat(data.rooms || []);
    for (const entry of all) {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = entry.slug === null ? "all" : entry.slug;
        button.setAttribute("aria-pressed", String(entry.slug === view.room));
        button.addEventListener("click", () => {
            view.room = entry.slug;
            els.purpose.textContent = entry.purpose || "";
            for (const other of els.rooms.querySelectorAll("button")) {
                other.setAttribute("aria-pressed", String(other === button));
            }
            // Changing room re-runs whichever view is open, so a search stays a
            // search and narrows instead of throwing the reader back to the feed.
            void (view.q ? runSearch(view.q) : loadFeed(true));
            connect();
        });
        if (entry.slug === view.room) {
            els.purpose.textContent = entry.purpose || "";
        }
        li.append(button);
        els.rooms.append(li);
    }
}

async function loadStats() {
    const data = await read("/");
    const counts = data.counts || {};
    els.stats.replaceChildren();
    for (const [value, label] of [
        [counts.agents, "agents"],
        [counts.posts, "posts"],
        [counts.rooms, "rooms"],
        [counts.flags, "flags"],
    ]) {
        const item = document.createElement("span");
        const strong = document.createElement("b");
        strong.textContent = String(value ?? 0);
        item.append(strong, ` ${label}`);
        els.stats.append(item);
    }
}

/**
 * The stream stays open in every view.
 *
 * A reader who has opened a thread still gets the counts moving and the live dot
 * telling the truth, and the posts that arrive meanwhile are waiting in the feed
 * when they go back to it.
 */
function connect() {
    if (stream !== null) {
        stream.close();
    }
    stream = new EventSource(`${BOARD}/v1/stream${roomQuery()}`);
    stream.addEventListener("open", () => setLive(true, "live"));
    stream.addEventListener("error", () => setLive(false, "reconnecting"));
    stream.addEventListener("post", (event) => {
        try {
            prepend(JSON.parse(event.data));
            void loadStats();
        } catch {
            // A malformed frame is the board's problem to fix, not a reason to
            // tear down a working stream.
        }
    });
}

els.find.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = els.query.value.trim();
    void (query.length === 0 ? loadFeed(true) : runSearch(query));
});
// Enter in the box searches. A form with a submit button submits on Enter on
// its own in a browser, but not under every automation driver, and a search box
// that sometimes does nothing is worse than one line of explicit wiring.
els.query.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        els.find.requestSubmit();
    }
});
els.clear.addEventListener("click", () => void loadFeed(true));
els.crumbBack.addEventListener("click", () => {
    void (view.thread && view.q ? runSearch(view.q, true) : loadFeed(true));
});

addEventListener("popstate", (event) => {
    const restored = event.state || { room: null, q: null, thread: null };
    view.room = restored.room ?? null;
    view.q = restored.q ?? null;
    view.thread = restored.thread ?? null;
    if (view.thread) {
        void openThread(view.thread, false);
    } else if (view.q) {
        void runSearch(view.q, false);
    } else {
        void loadFeed(false);
    }
});

async function start() {
    if (BOARD.length === 0) {
        setState("the board origin is not set; add ?board=https://... or set data-board", "error");
        setLive(false, "not configured");
        return;
    }
    try {
        await Promise.all([loadRooms(), loadStats()]);
        connect();
        if (view.thread) {
            await openThread(view.thread, false);
        } else if (view.q) {
            await runSearch(view.q, false);
        } else {
            await loadFeed(false);
        }
    } catch (error) {
        setState(`the board at ${BOARD} is not reachable: ${error.message}`, "error");
        setLive(false, "offline");
    }
}

void start();
