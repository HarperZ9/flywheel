import { ROOM, localResponses, sha256Base64Url, textHash } from "./media-cross-surface-checks.mjs";

export function mediaCrossReport({ base, face, objects }) {
    return {
        schema: "bulletin.same-media-cross-surface/v4",
        base,
        face: face.receipt,
        objects: objects.map((item) => reportObject(item, base, face.origin)),
        fixtures: objects.map((item) => ({
            name: item.fixture.name,
            media_type: item.fixture.mediaType,
            kind: item.fixture.kind,
            bytes: item.fixture.bytes.byteLength,
            sha256: sha256Base64Url(item.fixture.bytes),
            source: item.fixture.source,
        })),
    };
}

function reportObject(item, base, faceOrigin) {
    const expected = item.expected;
    return {
        room: ROOM,
        fixture: expected.fixture,
        kind: expected.kind,
        media_type: expected.mediaType,
        post_id: expected.postId,
        media_id: expected.mediaId,
        media_url: expected.mediaUrl,
        bytes: expected.bytes,
        body_sha256: textHash(expected.body),
        alt_sha256: textHash(expected.alt),
        checks: { http_post: item.httpPostFailures, mcp_feed: item.mcpFailures, browser_dom: item.browserCheck.domFailures, browser_network: item.browserCheck.networkFailures, browser_remote: item.browserCheck.remoteFailures, browser_local: item.browserCheck.localFailures, invalid_media_control: item.invalidMediaControl.caught ? [] : item.invalidMediaControl.domFailures, hidden_player_control: item.hiddenPlayerControl === null || item.hiddenPlayerControl.caught ? [] : item.hiddenPlayerControl.domFailures },
        http_range: pickRangeEvidence(item.httpRange),
        browser: { final_url: item.browserCheck.browser.finalUrl, request_count: item.browserCheck.browser.requests.length, expected_media_requested: item.browserCheck.browser.requests.some((request) => request.url === expected.mediaUrl), media: pickMediaEvidence(item.browserCheck.browser.value), local_responses: localResponses(item.browserCheck.browser.responses, [base, faceOrigin]), console_messages: item.browserCheck.browser.consoleMessages, page_errors: item.browserCheck.browser.pageErrors },
        controls: { invalid_media_decode: item.invalidMediaControl, hidden_player: item.hiddenPlayerControl },
    };
}

function pickRangeEvidence(range) {
    return { status: range?.status ?? 0, content_range: range?.contentRange ?? "", body_length: range?.bodyLength ?? 0, body_sha256: range?.bodySha256 ?? "", first_eight_match: range?.firstEightMatch === true };
}
function pickMediaEvidence(snapshot) {
    return { tag: snapshot?.mediaTag ?? "", current_src: snapshot?.currentSrc ?? "", natural_width: snapshot?.naturalWidth ?? 0, natural_height: snapshot?.naturalHeight ?? 0, ready_state: snapshot?.readyState ?? 0, duration: snapshot?.duration ?? 0, video_width: snapshot?.videoWidth ?? 0, video_height: snapshot?.videoHeight ?? 0, controls: snapshot?.controls === true, autoplay: snapshot?.autoplay === true, plays_inline: snapshot?.playsInline === true, complete: snapshot?.complete === true, decoded: snapshot?.decoded === true, decode_error: snapshot?.decodeError ?? "", control_visible: snapshot?.controlVisible === true, control_pointer_interactive: snapshot?.controlPointerInteractive === true, control_covered: snapshot?.controlCovered === true, control_clipped: snapshot?.controlClipped === true, control_rect: snapshot?.controlRect ?? null, playback_method: snapshot?.playbackMethod ?? "", playback_native_control: snapshot?.playbackNativeControl === true, playback_started: snapshot?.playbackStarted === true, playback_start_time: snapshot?.playbackStartTime ?? 0, playback_end_time: snapshot?.playbackEndTime ?? 0, playback_max_time: snapshot?.playbackMaxTime ?? 0, playback_paused: snapshot?.playbackPaused === true, playback_ended: snapshot?.playbackEnded === true, playback_error: snapshot?.playbackError ?? "", playback_reason: snapshot?.playbackReason ?? "" };
}
