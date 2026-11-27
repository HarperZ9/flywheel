/*
 * test_win32_surface.c - Standalone C11 self-test proving read-only desktop
 * observation, deterministic frame-diff hashing, and 4/4 planted fail-closed
 * refusal controls.
 */
#include "win32_surface.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int g_failures = 0;

static void check_true(int cond, const char *label) {
    if (!cond) {
        fprintf(stderr, "[FAIL] %s\n", label);
        ++g_failures;
    } else {
        printf("[PASS] %s\n", label);
    }
}

static WsInputRequest make_base_req(void) {
    WsInputRequest req;
    memset(&req, 0, sizeof(req));
    req.target_hwnd = 0ULL;
    req.action_kind = WS_INPUT_LEFT_CLICK;
    req.x = 120;
    req.y = 80;
    req.vk_code = 0U;
    req.grant_verified = 1;
    req.dry_run = 1;
    (void)snprintf(req.target_title, sizeof(req.target_title), "%s", "Accountable Workspace - Notes");
    (void)snprintf(req.allowlist_title, sizeof(req.allowlist_title), "%s", "Accountable Workspace");
    req.allowed_bounds.left = 0;
    req.allowed_bounds.top = 0;
    req.allowed_bounds.right = 800;
    req.allowed_bounds.bottom = 600;
    return req;
}

static void test_readonly_observation(void) {
    WsDesktopObs obs;
    int32_t rc = ws_observe_desktop(&obs);
    check_true(rc == WS_OK, "observe_desktop returns WS_OK");
    check_true(obs.abi_version == WS_ABI_VERSION, "observe_desktop reports ABI v1");
    check_true(obs.sample_width == 64U && obs.sample_height == 36U, "observe_desktop reports 64x36 sample");
    check_true(obs.frame_hash_fnv1a64 != 0ULL, "observe_desktop produces non-zero FNV-1a frame hash");
    check_true(obs.window_count <= WS_MAX_WINDOWS, "observe_desktop respects WS_MAX_WINDOWS cap");
}

static void test_deterministic_frame_diff_hash(void) {
    const uint8_t hello[] = {'h', 'e', 'l', 'l', 'o'};
    uint8_t frame_a[64];
    uint8_t frame_b[64];
    uint64_t h_hello = ws_hash_frame_fnv1a64(hello, sizeof(hello));
    uint64_t h_a1;
    uint64_t h_a2;
    uint64_t h_b;

    check_true(h_hello == UINT64_C(0xa430d84680aabd0b), "FNV-1a64 matches canonical test vector for 'hello'");
    for (size_t i = 0; i < sizeof(frame_a); ++i) {
        frame_a[i] = (uint8_t)(i * 3U + 7U);
        frame_b[i] = frame_a[i];
    }
    frame_b[31] ^= 0x01U;
    h_a1 = ws_hash_frame_fnv1a64(frame_a, sizeof(frame_a));
    h_a2 = ws_hash_frame_fnv1a64(frame_a, sizeof(frame_a));
    h_b = ws_hash_frame_fnv1a64(frame_b, sizeof(frame_b));
    check_true(h_a1 == h_a2, "identical framebuffer produces bit-identical hash");
    check_true(h_a1 != h_b, "1-bit framebuffer change produces distinct dirty-region hash");
}

static void test_planted_fail_closed_controls(void) {
    static const char *const kExcludedSamples[] = {
        "Sign in - Account Portal",
        "Cloudflare Turnstile Challenge",
        "reCAPTCHA verification",
        "User Account Control (UAC)",
        "Windows Credential Manager",
        "Enter Password to Unlock",
        "chrome://inspect/#devices"
    };
    WsInputRequest req;
    WsDispatchResult res;
    int32_t rc;

    /* Control 1: Missing grant -> WS_REFUSED_NO_GRANT */
    req = make_base_req();
    req.grant_verified = 0;
    rc = ws_plan_and_dispatch_input(&req, &res);
    check_true(rc == WS_REFUSED_NO_GRANT && res.executed == 0 && res.events_sent == 0U,
               "control 1: missing grant refused fail-closed");

    /* Control 2: Hard-excluded security/auth/CAPTCHA/UAC titles -> WS_REFUSED_EXCLUDED_WINDOW */
    for (size_t i = 0; i < sizeof(kExcludedSamples) / sizeof(kExcludedSamples[0]); ++i) {
        req = make_base_req();
        (void)snprintf(req.target_title, sizeof(req.target_title), "%s", kExcludedSamples[i]);
        (void)snprintf(req.allowlist_title, sizeof(req.allowlist_title), "%s", kExcludedSamples[i]);
        check_true(ws_is_excluded_title(kExcludedSamples[i]) == 1, "excluded title detector catches sample");
        rc = ws_plan_and_dispatch_input(&req, &res);
        check_true(rc == WS_REFUSED_EXCLUDED_WINDOW && res.executed == 0 && res.events_sent == 0U,
                   "control 2: hard-excluded window refused fail-closed");
    }

    /* Control 3: Non-allowlisted window title -> WS_REFUSED_TARGET_NOT_ALLOWLISTED */
    req = make_base_req();
    (void)snprintf(req.target_title, sizeof(req.target_title), "%s", "Unrelated Browser Tab");
    rc = ws_plan_and_dispatch_input(&req, &res);
    check_true(rc == WS_REFUSED_TARGET_NOT_ALLOWLISTED && res.executed == 0 && res.events_sent == 0U,
               "control 3: non-allowlisted target refused fail-closed");

    /* Control 4: Out-of-bounds coordinates -> WS_REFUSED_OUT_OF_BOUNDS */
    req = make_base_req();
    req.x = 1200;
    req.y = 900;
    rc = ws_plan_and_dispatch_input(&req, &res);
    check_true(rc == WS_REFUSED_OUT_OF_BOUNDS && res.executed == 0 && res.events_sent == 0U,
               "control 4: out-of-bounds click refused fail-closed");

    /* Positive dry-run control: allowlisted + granted + in-bounds -> WS_DRY_RUN_PLANNED */
    req = make_base_req();
    rc = ws_plan_and_dispatch_input(&req, &res);
    check_true(rc == WS_DRY_RUN_PLANNED && res.executed == 0 && res.dry_run == 1 && res.events_sent == 0U,
               "authorized dry-run plan accepted with zero OS input injected");
}

int main(void) {
    test_readonly_observation();
    test_deterministic_frame_diff_hash();
    test_planted_fail_closed_controls();
    if (g_failures != 0) {
        fprintf(stderr, "win32_surface self-test FAILED (%d failures)\n", g_failures);
        return 1;
    }
    printf("win32_surface self-test PASSED (0 failures)\n");
    return 0;
}
