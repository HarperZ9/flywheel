/**
 * Drawing an attachment.
 *
 * The URL is built here from the media id rather than taken from the `url`
 * field the board sends alongside it. The id has one shape and it is checked
 * against that shape, so a field carrying something else cannot point this page
 * at another origin. As in render.js, every string goes in through textContent
 * or through an attribute, and there is no innerHTML in this file.
 *
 * Alt text is not decoration. It is what the author signed, and it is the only
 * description of a file a reader who cannot open it will ever get, so it is
 * drawn under the object as well as attached to it.
 */

import { BOARD } from "./api.js";

const MEDIA_ID = /^[0-9A-Za-z_-]{43}$/;

function mediaUrl(id) {
    return typeof id === "string" && MEDIA_ID.test(id) ? `${BOARD}/v1/media/${id}` : null;
}

function caption(text) {
    const line = document.createElement("p");
    line.className = "alt";
    line.textContent = text;
    return line;
}

function image(url, attachment) {
    const el = document.createElement("img");
    el.className = "media";
    el.src = url;
    el.alt = attachment.alt || "";
    el.loading = "lazy";
    el.decoding = "async";
    // The board reads both out of the file's own header. Setting them reserves
    // the space before the bytes arrive, so the feed does not jump under a
    // reader who is already partway down it.
    if (attachment.width && attachment.height) {
        el.width = attachment.width;
        el.height = attachment.height;
    }
    return el;
}

function player(tag, url, preload) {
    const el = document.createElement(tag);
    el.className = "media";
    el.controls = true;
    el.preload = preload;
    el.src = url;
    if (tag === "video") {
        el.playsInline = true;
    }
    return el;
}

/** A file whose kind this page has no player for. The reader decides. */
function link(url, attachment) {
    const el = document.createElement("a");
    el.className = "media-link";
    el.href = url;
    el.rel = "noopener noreferrer";
    el.textContent = attachment.alt || attachment.media_type || "attachment";
    return el;
}

function object(url, attachment) {
    switch (attachment.kind) {
        case "image":
            return image(url, attachment);
        case "audio":
            return player("audio", url, "none");
        case "video":
            return player("video", url, "metadata");
        default:
            return link(url, attachment);
    }
}

/**
 * A withheld object keeps its place in the list. Removing the row would leave
 * the post's content hash underivable and leave a reader with no way to tell
 * that something was there.
 */
function withheldItem(attachment) {
    const item = document.createElement("li");
    item.className = "attachment";
    item.dataset.withheld = "true";
    item.append(caption(attachment.alt || "an attachment"));
    const note = document.createElement("p");
    note.className = "withheld";
    note.textContent = "withheld by the operator; the record is at /v1/moderation";
    item.append(note);
    return item;
}

function attachmentItem(attachment) {
    const url = mediaUrl(attachment.media_id);
    if (attachment.withheld === true || url === null) {
        return withheldItem(attachment);
    }
    const item = document.createElement("li");
    item.className = "attachment";
    item.dataset.kind = attachment.kind || "file";
    item.append(object(url, attachment));
    item.append(caption(attachment.alt || ""));
    return item;
}

/** The list for one post, or null when the post carries nothing. */
export function attachmentList(post) {
    const attachments = Array.isArray(post.attachments) ? post.attachments : [];
    if (attachments.length === 0) {
        return null;
    }
    const list = document.createElement("ul");
    list.className = "attachments";
    for (const attachment of attachments) {
        list.append(attachmentItem(attachment));
    }
    return list;
}
