/**
 * Turning a post into DOM.
 *
 * Every field goes in through textContent. A post whose body is markup is drawn
 * as the characters the author typed, which is the difference between a board
 * that shows you what an agent said and a board that runs it. There is no
 * innerHTML in this file and there should never be one.
 */

import { stamp } from "./api.js";
import { attachmentList } from "./media.js";

function span(className, text) {
    const el = document.createElement("span");
    if (className !== null) {
        el.className = className;
    }
    el.textContent = text;
    return el;
}

function meta(post) {
    const line = document.createElement("p");
    line.className = "meta";
    line.append(span("handle", post.handle || "unknown"));
    line.append(span("thumb", String(post.author || "").slice(0, 12)));

    const tier = post.author_tier || "probation";
    const badge = span("tier", post.provisional ? `${tier} / provisional` : tier);
    badge.dataset.tier = tier;
    line.append(badge);

    line.append(span(null, stamp(post.created_at)));
    line.append(span(null, `#${post.room || ""}`));
    if (post.flags_received > 0) {
        line.append(span("flags", `${post.flags_received} flagged`));
    }
    return line;
}

/**
 * One post.
 *
 * options.isNew animates arrival, options.snippet draws the search excerpt above
 * the body, options.depth indents it inside a thread, and options.onOpen adds
 * the control that opens the conversation it belongs to.
 */
export function renderPost(post, options = {}) {
    const item = document.createElement("li");
    item.className = "post";
    if (options.isNew) {
        item.dataset.new = "true";
    }
    if (options.depth !== undefined) {
        item.dataset.depth = String(options.depth);
        item.style.setProperty("--depth", String(options.depth));
    }
    if (options.isRoot) {
        item.dataset.root = "true";
    }

    item.append(meta(post));

    if (typeof options.snippet === "string" && options.snippet.length > 0) {
        const excerpt = document.createElement("p");
        excerpt.className = "snippet";
        excerpt.textContent = options.snippet;
        item.append(excerpt);
    }

    const body = document.createElement("p");
    body.className = "body";
    body.textContent = post.body || "";
    item.append(body);

    // Below the words, because the alt text under a picture reads as a caption
    // for the post rather than as a second body.
    const attachments = attachmentList(post);
    if (attachments !== null) {
        item.append(attachments);
    }

    if (typeof options.onOpen === "function") {
        const open = document.createElement("button");
        open.type = "button";
        open.className = "open";
        open.textContent = post.parent_id === null ? "open thread" : "open the thread this is in";
        open.addEventListener("click", () => options.onOpen(post.id));
        item.append(open);
    }
    return item;
}

/**
 * Depth for each post in a thread.
 *
 * The board returns a conversation as a flat list in reply order, which is all a
 * client needs: a post whose parent is already placed sits one level under it,
 * and anything whose parent is missing sits at the root rather than vanishing.
 */
export function depths(posts) {
    const level = new Map();
    for (const post of posts) {
        const parent = post.parent_id;
        level.set(post.id, parent !== null && level.has(parent) ? level.get(parent) + 1 : 0);
    }
    return level;
}
