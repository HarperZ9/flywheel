import assert from "node:assert/strict";
import { mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { browserSnapshotFailures, projectionFailures, rangeReadFailures } from "../scripts/smoke/media-cross-surface-checks.mjs";
import { startHiddenMediaFace } from "../scripts/smoke/face-server.mjs";
import { deterministicMediaFixtures, prepareFixtureBrowserOptions } from "../scripts/smoke/media-fixtures.mjs";

function expected(kind: "image" | "audio" | "video") {
    const mediaId = kind[0]!.repeat(43);
    const mediaType = kind === "audio" ? "audio/wav" : kind === "video" ? "video/webm" : "image/png";
    return { postId: `post-${kind}`, body: `body-${kind}`, alt: `alt-${kind}`, mediaId, mediaUrl: `http://127.0.0.1:8787/v1/media/${mediaId}`, mediaType, kind, bytes: 128 };
}

function postFor(want: ReturnType<typeof expected>) {
    return {
        id: want.postId,
        body: want.body,
        content_is_untrusted: true,
        attachments: [{ media_id: want.mediaId, alt: want.alt, media_type: want.mediaType, kind: want.kind, bytes: want.bytes, url: `/v1/media/${want.mediaId}` }],
    };
}

function mediaSnapshot(want: ReturnType<typeof expected>, overrides = {}) {
    return {
        found: true,
        bodyText: want.body,
        captionText: want.alt,
        mediaAlt: want.kind === "image" ? want.alt : "",
        mediaSrc: want.mediaUrl,
        currentSrc: want.mediaUrl,
        mediaId: want.mediaId,
        mediaTag: want.kind.toUpperCase(),
        complete: want.kind === "image",
        decoded: true,
        naturalWidth: want.kind === "image" ? 4 : 0,
        naturalHeight: want.kind === "image" ? 4 : 0,
        controls: want.kind !== "image",
        autoplay: false,
        playsInline: want.kind === "video",
        readyState: want.kind === "image" ? undefined : 2,
        duration: want.kind === "image" ? undefined : 1.25,
        videoWidth: want.kind === "video" ? 16 : 0,
        videoHeight: want.kind === "video" ? 16 : 0,
        playbackMethod: want.kind === "image" ? "" : "native-keyboard-space",
        playbackNativeControl: want.kind !== "image",
        controlVisible: want.kind !== "image",
        controlPointerInteractive: want.kind !== "image",
        controlCovered: false,
        controlClipped: false,
        controlRect: want.kind === "image" ? undefined : { x: 8, y: 8, width: 220, height: 36 },
        playbackStarted: want.kind !== "image",
        playbackStartTime: 0,
        playbackEndTime: want.kind === "image" ? 0 : 0.2,
        playbackMaxTime: want.kind === "image" ? 0 : 0.2,
        playbackPaused: want.kind !== "image",
        playbackEnded: false,
        playbackError: "",
        injectedNodes: [],
        eventAttributes: [],
        bodyAnchors: [],
        sentinelLinks: [],
        ...overrides,
    };
}

test("same-object projection uses expected media kind and type", () => {
    const audio = expected("audio");
    assert.deepEqual(projectionFailures(postFor(audio), audio), []);
    assert.ok(projectionFailures(postFor(audio), { ...audio, mediaType: "video/webm" }).includes("media type mismatch"));
});

test("HTTP range evidence rejects empty or wrong bytes behind matching headers", () => {
    const fixture = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 99, 100]);
    const good = { status: 206, contentRange: "bytes 0-7/10", bytes: fixture.slice(0, 8) };
    assert.deepEqual(rangeReadFailures(good, fixture), []);
    assert.ok(rangeReadFailures({ ...good, bytes: new Uint8Array(8) }, fixture).includes("media range body bytes mismatch"));
    assert.ok(rangeReadFailures({ ...good, bytes: new Uint8Array() }, fixture).includes("media range body length mismatch"));
});

test("browser DOM evidence accepts loaded audio and video controls from the exact board URL", () => {
    const audio = expected("audio");
    const video = expected("video");
    assert.deepEqual(browserSnapshotFailures({ expected: audio, snapshot: mediaSnapshot(audio) }), []);
    assert.deepEqual(browserSnapshotFailures({ expected: video, snapshot: mediaSnapshot(video) }), []);
});

test("browser DOM evidence rejects broken playable media", () => {
    const video = expected("video");
    const failures = browserSnapshotFailures({ expected: video, snapshot: mediaSnapshot(video, { readyState: 0, duration: Number.NaN }) });
    assert.ok(failures.includes("browser video did not load/decode"));
});

test("browser DOM evidence rejects playable media without native-control playback", () => {
    const audio = expected("audio");
    const failures = browserSnapshotFailures({
        expected: audio,
        snapshot: mediaSnapshot(audio, { playbackMethod: "document-click-handler", playbackNativeControl: false }),
    });
    assert.ok(failures.includes("browser audio did not play through native controls"));
});

test("browser DOM evidence rejects hidden playable media even if playback advances", () => {
    const audio = expected("audio");
    const failures = browserSnapshotFailures({
        expected: audio,
        snapshot: mediaSnapshot(audio, { controlVisible: false, controlRect: { x: 0, y: 0, width: 0, height: 0 } }),
    });
    assert.ok(failures.includes("browser audio controls are not visibly reachable"));
});

test("browser DOM evidence rejects playable media without playback progress", () => {
    const audio = expected("audio");
    const failures = browserSnapshotFailures({
        expected: audio,
        snapshot: mediaSnapshot(audio, { playbackStarted: false, playbackEndTime: 0, playbackMaxTime: 0 }),
    });
    assert.ok(failures.includes("browser audio did not play through native controls"));
    assert.ok(failures.includes("browser audio currentTime did not advance"));
});

test("browser DOM evidence rejects sub-second playable media", () => {
    const video = expected("video");
    const failures = browserSnapshotFailures({ expected: video, snapshot: mediaSnapshot(video, { duration: 0.25 }) });
    assert.ok(failures.includes("browser video duration is under one second"));
});

test("deterministic smoke fixtures include original PNG and WAV media", () => {
    const fixtures = deterministicMediaFixtures();
    assert.deepEqual(fixtures.map((fixture) => fixture.name), ["png", "wav"]);
    assert.equal(fixtures[0]!.mediaType, "image/png");
    assert.equal(fixtures[1]!.mediaType, "audio/wav");
    assert.ok(fixtures.every((fixture) => fixture.bytes.byteLength >= 32));
    assert.equal(wavDurationSeconds(fixtures[1]!.bytes), 1.25);
});

test("hidden media control face serves owned bytes behind a hidden player", async (t) => {
    const want = expected("audio");
    const bytes = new Uint8Array([82, 73, 70, 70, 1, 2, 3, 4]);
    const face = await startHiddenMediaFace(want, bytes);
    t.after(() => face.close());
    const html = await fetch(`${face.origin}${face.path}`).then((response) => response.text());
    const mediaBody = await fetch(`${face.origin}/v1/media/${want.mediaId}`).then((response) => response.arrayBuffer());
    const media = new Uint8Array(mediaBody as ArrayBuffer);
    assert.match(html, /data-hidden-control="true"/);
    assert.deepEqual(media, bytes);
});

test("fixture generation creates the requested browser profile root", async (t) => {
    const parent = await mkdtemp(join(tmpdir(), "bulletin-media-fixtures-"));
    const tmpRoot = join(parent, "missing-log-dir");
    t.after(() => rm(parent, { recursive: true, force: true }));
    const options = await prepareFixtureBrowserOptions({ tmpRoot });
    assert.equal(options.tmpRoot, tmpRoot);
    assert.equal((await stat(tmpRoot)).isDirectory(), true);
});

function wavDurationSeconds(bytes: Uint8Array) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const sampleRate = view.getUint32(24, true);
    const dataBytes = view.getUint32(40, true);
    return dataBytes / 2 / sampleRate;
}
