/*
 * win32_surface.c - C11 Win32 hardware-level desktop observation and
 * fail-closed policy-gated input surface with portable non-Windows stub.
 */
#include "win32_surface.h"

#include <ctype.h>
#include <stdio.h>
#include <string.h>

#ifdef _WIN32
#  ifndef WIN32_LEAN_AND_MEAN
#    define WIN32_LEAN_AND_MEAN
#  endif
#  include <windows.h>
#endif

static const char *const kExcludedTitlePatterns[] = {
    "captcha", "recaptcha", "hcaptcha", "turnstile", "uac",
    "user account control", "credential", "sign in", "password",
    "chrome://inspect", "oauth", "security prompt", "verify you are human"
};

static int ws_contains_ci(const char *hay, const char *needle) {
    size_t hlen, nlen;
    if (hay == NULL || needle == NULL || needle[0] == '\0') { return 0; }
    hlen = strlen(hay);
    nlen = strlen(needle);
    if (nlen > hlen) { return 0; }
    for (size_t i = 0; i + nlen <= hlen; ++i) {
        size_t j = 0;
        while (j < nlen && tolower((unsigned char)hay[i + j]) == tolower((unsigned char)needle[j])) { ++j; }
        if (j == nlen) { return 1; }
    }
    return 0;
}

static int32_t ws_fail(WsDispatchResult *res, int32_t code, const char *msg) {
    res->status_code = code;
    res->executed = 0;
    (void)snprintf(res->reason, sizeof(res->reason), "%s", msg);
    return code;
}

WS_API int32_t ws_is_excluded_title(const char *title) {
    size_t n = sizeof(kExcludedTitlePatterns) / sizeof(kExcludedTitlePatterns[0]);
    if (title == NULL || title[0] == '\0') { return 0; }
    for (size_t i = 0; i < n; ++i) {
        if (ws_contains_ci(title, kExcludedTitlePatterns[i])) { return 1; }
    }
    return 0;
}

WS_API uint64_t ws_hash_frame_fnv1a64(const uint8_t *data, size_t len) {
    uint64_t h = UINT64_C(14695981039346656037);
    if (data == NULL) { return h; }
    for (size_t i = 0; i < len; ++i) {
        h ^= (uint64_t)data[i];
        h *= UINT64_C(1099511628211);
    }
    return h;
}

#ifdef _WIN32

static void ws_read_hwnd_title(HWND hwnd, char *buf, size_t cap) {
    wchar_t wbuf[WS_TITLE_CAP];
    int wlen;
    if (buf == NULL || cap == 0U) { return; }
    buf[0] = '\0';
    if (hwnd == NULL || !IsWindow(hwnd)) { return; }
    wlen = GetWindowTextW(hwnd, wbuf, (int)(sizeof(wbuf) / sizeof(wbuf[0])));
    if (wlen > 0) {
        (void)WideCharToMultiByte(CP_UTF8, 0, wbuf, wlen, buf, (int)(cap - 1U), NULL, NULL);
        buf[cap - 1U] = '\0';
    }
}

static WsRect ws_read_hwnd_rect(HWND hwnd) {
    RECT rc;
    WsRect out = {0, 0, 0, 0};
    if (hwnd != NULL && IsWindow(hwnd) && GetWindowRect(hwnd, &rc)) {
        out.left = (int32_t)rc.left;
        out.top = (int32_t)rc.top;
        out.right = (int32_t)rc.right;
        out.bottom = (int32_t)rc.bottom;
    }
    return out;
}

static BOOL CALLBACK ws_enum_windows_cb(HWND hwnd, LPARAM lparam) {
    WsDesktopObs *obs = (WsDesktopObs *)(uintptr_t)lparam;
    DWORD pid = 0;
    char title[WS_TITLE_CAP];
    WsWindowInfo *slot;
    if (obs == NULL || obs->window_count >= WS_MAX_WINDOWS) { return FALSE; }
    if (!IsWindowVisible(hwnd)) { return TRUE; }
    ws_read_hwnd_title(hwnd, title, sizeof(title));
    if (title[0] == '\0') { return TRUE; }
    (void)GetWindowThreadProcessId(hwnd, &pid);
    slot = &obs->windows[obs->window_count++];
    slot->hwnd = (uint64_t)(uintptr_t)hwnd;
    slot->pid = (uint32_t)pid;
    slot->visible = 1;
    slot->bounds = ws_read_hwnd_rect(hwnd);
    (void)snprintf(slot->title, sizeof(slot->title), "%s", title);
    return TRUE;
}

static uint64_t ws_capture_downsampled_hash(uint32_t w, uint32_t h, uint32_t *sw, uint32_t *sh) {
    HWND desktop = GetDesktopWindow();
    HDC src = GetDC(desktop);
    uint8_t pixels[64U * 36U * 4U];
    *sw = 64U;
    *sh = 36U;
    memset(pixels, 0, sizeof(pixels));
    if (src != NULL && w > 0U && h > 0U) {
        HDC mem = CreateCompatibleDC(src);
        HBITMAP bm = (mem != NULL) ? CreateCompatibleBitmap(src, 64, 36) : NULL;
        if (mem != NULL && bm != NULL) {
            HGDIOBJ old = SelectObject(mem, bm);
            (void)SetStretchBltMode(mem, HALFTONE);
            if (StretchBlt(mem, 0, 0, 64, 36, src, 0, 0, (int)w, (int)h, SRCCOPY)) {
                BITMAPINFO bmi;
                memset(&bmi, 0, sizeof(bmi));
                bmi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
                bmi.bmiHeader.biWidth = 64;
                bmi.bmiHeader.biHeight = -36;
                bmi.bmiHeader.biPlanes = 1;
                bmi.bmiHeader.biBitCount = 32;
                bmi.bmiHeader.biCompression = BI_RGB;
                (void)GetDIBits(mem, bm, 0, 36U, pixels, &bmi, DIB_RGB_COLORS);
            }
            if (old != NULL) { (void)SelectObject(mem, old); }
        }
        if (bm != NULL) { DeleteObject(bm); }
        if (mem != NULL) { DeleteDC(mem); }
        ReleaseDC(desktop, src);
    }
    return ws_hash_frame_fnv1a64(pixels, sizeof(pixels));
}

static int32_t ws_dispatch_live_win32(const WsInputRequest *req, WsDispatchResult *out_res) {
    HWND target = (HWND)(uintptr_t)req->target_hwnd;
    INPUT inputs[2];
    UINT count = 0, sent = 0;
    int sw = GetSystemMetrics(SM_CXSCREEN), sh = GetSystemMetrics(SM_CYSCREEN);
    if (target == NULL || !IsWindow(target)) {
        return ws_fail(out_res, WS_ERR_DISPATCH_FAILED, "target hwnd is not a live window");
    }
    memset(inputs, 0, sizeof(inputs));
    if (req->action_kind == WS_INPUT_FOCUS) {
        if (!SetForegroundWindow(target)) {
            return ws_fail(out_res, WS_ERR_DISPATCH_FAILED, "SetForegroundWindow refused by OS foreground lock");
        }
        out_res->status_code = WS_OK;
        out_res->executed = 1;
        out_res->events_sent = 1U;
        (void)snprintf(out_res->reason, sizeof(out_res->reason), "%s", "focus dispatched to allowlisted window");
        return WS_OK;
    }
    if (req->action_kind == WS_INPUT_MOVE || req->action_kind == WS_INPUT_LEFT_CLICK) {
        LONG nx = (sw > 1) ? (LONG)(((int64_t)req->x * 65535LL) / (int64_t)(sw - 1)) : 0;
        LONG ny = (sh > 1) ? (LONG)(((int64_t)req->y * 65535LL) / (int64_t)(sh - 1)) : 0;
        inputs[0].type = INPUT_MOUSE;
        inputs[0].mi.dx = nx;
        inputs[0].mi.dy = ny;
        inputs[0].mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE;
        count = 1U;
        if (req->action_kind == WS_INPUT_LEFT_CLICK) {
            inputs[0].mi.dwFlags |= MOUSEEVENTF_LEFTDOWN;
            inputs[1].type = INPUT_MOUSE;
            inputs[1].mi.dx = nx;
            inputs[1].mi.dy = ny;
            inputs[1].mi.dwFlags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP;
            count = 2U;
        }
    } else if (req->action_kind == WS_INPUT_KEY_TAP) {
        inputs[0].type = INPUT_KEYBOARD;
        inputs[0].ki.wVk = (WORD)req->vk_code;
        inputs[1].type = INPUT_KEYBOARD;
        inputs[1].ki.wVk = (WORD)req->vk_code;
        inputs[1].ki.dwFlags = KEYEVENTF_KEYUP;
        count = 2U;
    } else {
        return ws_fail(out_res, WS_ERR_INVALID_ARG, "unsupported action_kind");
    }
    sent = SendInput(count, inputs, (int)sizeof(INPUT));
    out_res->events_sent = (uint32_t)sent;
    if (sent != count) {
        return ws_fail(out_res, WS_ERR_DISPATCH_FAILED, "SendInput did not deliver all requested events");
    }
    out_res->status_code = WS_OK;
    out_res->executed = 1;
    (void)snprintf(out_res->reason, sizeof(out_res->reason), "%s", "authorized input dispatched via SendInput");
    return WS_OK;
}

#endif /* _WIN32 */

WS_API int32_t ws_observe_desktop(WsDesktopObs *out_obs) {
    if (out_obs == NULL) { return WS_ERR_INVALID_ARG; }
    memset(out_obs, 0, sizeof(*out_obs));
    out_obs->abi_version = WS_ABI_VERSION;
#ifdef _WIN32
    {
        HWND fg = GetForegroundWindow();
        out_obs->is_windows_live = 1;
        out_obs->screen_width = (uint32_t)GetSystemMetrics(SM_CXSCREEN);
        out_obs->screen_height = (uint32_t)GetSystemMetrics(SM_CYSCREEN);
        out_obs->active_hwnd = (uint64_t)(uintptr_t)fg;
        ws_read_hwnd_title(fg, out_obs->active_title, sizeof(out_obs->active_title));
        out_obs->active_bounds = ws_read_hwnd_rect(fg);
        (void)EnumWindows(ws_enum_windows_cb, (LPARAM)(uintptr_t)out_obs);
        out_obs->frame_hash_fnv1a64 = ws_capture_downsampled_hash(
            out_obs->screen_width, out_obs->screen_height, &out_obs->sample_width, &out_obs->sample_height
        );
    }
#else
    {
        static const uint8_t kSeed[] = "accountable-surface:portable-stub:v1";
        out_obs->is_windows_live = 0;
        out_obs->screen_width = 1920U;
        out_obs->screen_height = 1080U;
        out_obs->sample_width = 64U;
        out_obs->sample_height = 36U;
        out_obs->frame_hash_fnv1a64 = ws_hash_frame_fnv1a64(kSeed, sizeof(kSeed) - 1U);
        (void)snprintf(out_obs->active_title, sizeof(out_obs->active_title), "%s", "portable-stub");
        out_obs->active_bounds.right = 1920;
        out_obs->active_bounds.bottom = 1080;
    }
#endif
    return WS_OK;
}

WS_API int32_t ws_plan_and_dispatch_input(const WsInputRequest *req, WsDispatchResult *out_res) {
    char effective_title[WS_TITLE_CAP];
    if (req == NULL || out_res == NULL) { return WS_ERR_INVALID_ARG; }
    memset(out_res, 0, sizeof(*out_res));
    out_res->dry_run = (req->dry_run != 0) ? 1 : 0;
    if (req->grant_verified != 1) {
        return ws_fail(out_res, WS_REFUSED_NO_GRANT, "fail-closed refusal: grant_verified must be 1");
    }
    (void)snprintf(effective_title, sizeof(effective_title), "%s", req->target_title);
#ifdef _WIN32
    if (req->target_hwnd != 0ULL) {
        char live[WS_TITLE_CAP];
        ws_read_hwnd_title((HWND)(uintptr_t)req->target_hwnd, live, sizeof(live));
        if (live[0] != '\0') {
            if (ws_is_excluded_title(live)) {
                return ws_fail(out_res, WS_REFUSED_EXCLUDED_WINDOW, "fail-closed refusal: live window matches hard exclusion");
            }
            (void)snprintf(effective_title, sizeof(effective_title), "%s", live);
        }
    }
#endif
    if (ws_is_excluded_title(effective_title) || ws_is_excluded_title(req->target_title) ||
        ws_is_excluded_title(req->allowlist_title)) {
        return ws_fail(out_res, WS_REFUSED_EXCLUDED_WINDOW, "fail-closed refusal: target matches hard-excluded auth/CAPTCHA/UAC window");
    }
    if (req->allowlist_title[0] == '\0' || !ws_contains_ci(effective_title, req->allowlist_title)) {
        return ws_fail(out_res, WS_REFUSED_TARGET_NOT_ALLOWLISTED, "fail-closed refusal: target window title is not allowlisted");
    }
    if (!(req->allowed_bounds.right > req->allowed_bounds.left && req->allowed_bounds.bottom > req->allowed_bounds.top)) {
        return ws_fail(out_res, WS_REFUSED_OUT_OF_BOUNDS, "fail-closed refusal: allowed_bounds rectangle is empty");
    }
    if ((req->action_kind == WS_INPUT_MOVE || req->action_kind == WS_INPUT_LEFT_CLICK) &&
        !(req->x >= req->allowed_bounds.left && req->x < req->allowed_bounds.right &&
          req->y >= req->allowed_bounds.top && req->y < req->allowed_bounds.bottom)) {
        return ws_fail(out_res, WS_REFUSED_OUT_OF_BOUNDS, "fail-closed refusal: input coordinates outside allowed_bounds");
    }
    if (req->dry_run != 0) {
        out_res->status_code = WS_DRY_RUN_PLANNED;
        (void)snprintf(out_res->reason, sizeof(out_res->reason), "%s", "authorized dry-run plan verified; zero OS input sent");
        return WS_DRY_RUN_PLANNED;
    }
#ifdef _WIN32
    return ws_dispatch_live_win32(req, out_res);
#else
    return ws_fail(out_res, WS_ERR_DISPATCH_FAILED, "live Win32 SendInput unavailable on non-Windows portable stub");
#endif
}
