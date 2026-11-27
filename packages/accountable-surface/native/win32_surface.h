/*
 * win32_surface.h - C11 hardware-level desktop observation and fail-closed
 * policy-gated input surface for accountable-surface.
 *
 * Hard exclusions compiled into the native membrane:
 *   - Zero CAPTCHA/Turnstile/reCAPTCHA interaction
 *   - Zero anti-bot stealth or browser-debugger hooks
 *   - Zero credential, password, OAuth, or UAC bypass
 *   - Fail-closed refusal unless grant_verified == 1 and target is allowlisted
 */
#ifndef ACCOUNTABLE_SURFACE_WIN32_SURFACE_H
#define ACCOUNTABLE_SURFACE_WIN32_SURFACE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32) && defined(WS_BUILD_DLL)
#  define WS_API __declspec(dllexport)
#else
#  define WS_API
#endif

#define WS_ABI_VERSION 1U
#define WS_MAX_WINDOWS 32U
#define WS_TITLE_CAP 256U
#define WS_REASON_CAP 256U

enum WsStatusCode {
    WS_OK = 0,
    WS_DRY_RUN_PLANNED = 1,
    WS_ERR_INVALID_ARG = -1,
    WS_REFUSED_NO_GRANT = -2,
    WS_REFUSED_EXCLUDED_WINDOW = -3,
    WS_REFUSED_TARGET_NOT_ALLOWLISTED = -4,
    WS_REFUSED_OUT_OF_BOUNDS = -5,
    WS_ERR_CAPTURE_FAILED = -6,
    WS_ERR_DISPATCH_FAILED = -7
};

enum WsInputActionKind {
    WS_INPUT_FOCUS = 1,
    WS_INPUT_MOVE = 2,
    WS_INPUT_LEFT_CLICK = 3,
    WS_INPUT_KEY_TAP = 4
};

typedef struct WsRect {
    int32_t left;
    int32_t top;
    int32_t right;
    int32_t bottom;
} WsRect;

typedef struct WsWindowInfo {
    uint64_t hwnd;
    uint32_t pid;
    int32_t visible;
    WsRect bounds;
    char title[WS_TITLE_CAP];
} WsWindowInfo;

typedef struct WsDesktopObs {
    uint32_t abi_version;
    int32_t is_windows_live;
    uint32_t screen_width;
    uint32_t screen_height;
    uint64_t frame_hash_fnv1a64;
    uint32_t sample_width;
    uint32_t sample_height;
    uint64_t active_hwnd;
    char active_title[WS_TITLE_CAP];
    WsRect active_bounds;
    uint32_t window_count;
    WsWindowInfo windows[WS_MAX_WINDOWS];
} WsDesktopObs;

typedef struct WsInputRequest {
    uint64_t target_hwnd;
    int32_t action_kind;
    int32_t x;
    int32_t y;
    uint32_t vk_code;
    int32_t grant_verified;
    int32_t dry_run;
    char target_title[WS_TITLE_CAP];
    char allowlist_title[WS_TITLE_CAP];
    WsRect allowed_bounds;
} WsInputRequest;

typedef struct WsDispatchResult {
    int32_t status_code;
    int32_t executed;
    int32_t dry_run;
    uint32_t events_sent;
    char reason[WS_REASON_CAP];
} WsDispatchResult;

/* Returns 1 if title matches any hard-excluded auth/CAPTCHA/UAC pattern, else 0. */
WS_API int32_t ws_is_excluded_title(const char *title);

/* Deterministic 64-bit FNV-1a hash over raw framebuffer or observation bytes. */
WS_API uint64_t ws_hash_frame_fnv1a64(const uint8_t *data, size_t len);

/* Read-only desktop inventory + downsampled framebuffer hash (zero mutation). */
WS_API int32_t ws_observe_desktop(WsDesktopObs *out_obs);

/* Fail-closed policy gate and dry-run/authorized input dispatcher. */
WS_API int32_t ws_plan_and_dispatch_input(
    const WsInputRequest *req,
    WsDispatchResult *out_res
);

#ifdef __cplusplus
}
#endif

#endif /* ACCOUNTABLE_SURFACE_WIN32_SURFACE_H */
