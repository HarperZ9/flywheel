"""Universal, native, no-shim capture of the composited output.

Every renderer -- D3D11, D3D12, Vulkan, OpenGL, Metal, software -- composites to
the display. Capturing THERE is agnostic to all of them by construction: the
membrane never imports a graphics API, never tracks a D3D version, and needs no
producer-side shim. It asks the OS for the pixels the OS already has.

One dispatch, three native backends, each via the OS's own API through `ctypes`
(standard library -- no third-party package):
  * Windows  -- GDI (BitBlt + GetDIBits)
  * macOS    -- CoreGraphics (CGDisplayCreateImageForRect)
  * Linux/X11 -- Xlib (XGetImage)

Validation honesty (the discipline EMET keeps): the Windows backend is validated
live in the author's environment. The macOS and Linux backends are implemented to
the documented OS APIs and are re-derivable, but are validated on their own
platforms -- not by the author here. On any platform without its backend,
capture_available() is False and callers degrade; nothing crashes.

Cost note: each grab captures, converts, and PNG-encodes. Keep it cheap the way
the continuity loop expects -- capture a REGION, sample at a cadence
(ResourceBudget.min_interval_s), and let the change-proportional loop skip the
expensive decode/perceptual-hash on unchanged frames.
"""

from __future__ import annotations

import sys
from typing import Iterator

from .capture import Frame, FrameDescriptor
from .pngencode import bgra_to_rgb, encode_png


class CaptureUnavailable(Exception):
    """Native capture is not available here (unsupported platform or OS error)."""


# ---------------------------------------------------------------------------
# Platform dispatch
# ---------------------------------------------------------------------------


def _platform_backend():
    p = sys.platform
    if p == "win32":
        return _win_grab
    if p == "darwin":
        return _mac_grab
    if p.startswith("linux"):
        return _x11_grab
    return None


def capture_available() -> bool:
    """True iff a native capture backend can run on this platform right now."""
    try:
        p = sys.platform
        if p == "win32":
            import ctypes
            return hasattr(ctypes, "windll")
        if p == "darwin":
            return _mac_libs() is not None
        if p.startswith("linux"):
            return _x11_lib() is not None
    except Exception:
        return False
    return False


def grab_raw(region: tuple[int, int, int, int] | None = None) -> tuple[bytes, int, int]:
    """Capture the composited output as RAW, top-down, tight-row BGRA bytes.

    This is the cheap grab -- capture only, no colour conversion and no PNG
    encode.  The high-rate fast path hashes these bytes directly for identity and
    perceives them straight (RawFrameOrgan); the per-frame zlib encode that
    grab_png pays is never incurred.  region = (x, y, w, h); None = full primary
    display.  Raises CaptureUnavailable on an unsupported platform or OS failure.
    """
    backend = _platform_backend()
    if backend is None or not capture_available():
        raise CaptureUnavailable(f"no native capture backend for platform {sys.platform!r}")
    if region is not None:
        _, _, w, h = region
        if w <= 0 or h <= 0:
            raise CaptureUnavailable("non-positive capture dimensions")
    return backend(region)  # (bgra, w, h)


def grab_png(region: tuple[int, int, int, int] | None = None) -> tuple[bytes, int, int]:
    """Capture the composited output and return (png_bytes, width, height).

    region = (x, y, w, h); None = the full primary display. Raises
    CaptureUnavailable on an unsupported platform or any OS-level failure.
    """
    bgra, w, h = grab_raw(region)
    return encode_png(w, h, bgra_to_rgb(bgra, w, h), channels=3), w, h


def _depad(raw: bytes, width: int, height: int, bytes_per_row: int) -> bytes:
    """Strip row padding to a tight width*4 BGRA buffer."""
    rowbytes = width * 4
    if bytes_per_row == rowbytes:
        return raw[: rowbytes * height]
    tight = bytearray(rowbytes * height)
    for r in range(height):
        tight[r * rowbytes : (r + 1) * rowbytes] = raw[r * bytes_per_row : r * bytes_per_row + rowbytes]
    return bytes(tight)


# ---------------------------------------------------------------------------
# Windows -- GDI  (validated live)
# ---------------------------------------------------------------------------

_SRCCOPY = 0x00CC0020


def _win_grab(region):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.BitBlt.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
    ]
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
    ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    if region is None:
        x = y = 0
        w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    else:
        x, y, w, h = region

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise CaptureUnavailable("GetDC failed")
    mem_dc = bmp = old_bmp = None
    try:
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bmp = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
        if not mem_dc or not bmp:
            raise CaptureUnavailable("could not allocate device context / bitmap")
        # Keep the DC's default bitmap so we can restore it before deleting ours:
        # DeleteObject silently fails on a bitmap still selected into a DC, which
        # would leak the HBITMAP and its w*h*4 backing memory on every grab.
        old_bmp = gdi32.SelectObject(mem_dc, bmp)
        if not gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, x, y, _SRCCOPY):
            raise CaptureUnavailable("BitBlt failed")
        bmih = BITMAPINFOHEADER()
        bmih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmih.biWidth = w
        bmih.biHeight = -h  # top-down
        bmih.biPlanes = 1
        bmih.biBitCount = 32
        bmih.biCompression = 0  # BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        if gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(bmih), 0) == 0:
            raise CaptureUnavailable("GetDIBits returned 0 scanlines")
        return bytes(buf), w, h  # BGRA, top-down, tight rows
    finally:
        if mem_dc and old_bmp:
            gdi32.SelectObject(mem_dc, old_bmp)  # deselect ours before deleting it
        if bmp:
            gdi32.DeleteObject(bmp)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)


# ---------------------------------------------------------------------------
# macOS -- CoreGraphics
# ---------------------------------------------------------------------------

_mac_cache = None


def _mac_libs():
    global _mac_cache
    if _mac_cache is None:
        import ctypes
        try:
            cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            _mac_cache = (cg, cf)
        except OSError:
            _mac_cache = False
    return _mac_cache or None


def _mac_grab(region):
    import ctypes

    libs = _mac_libs()
    if libs is None:
        raise CaptureUnavailable("CoreGraphics not available")
    cg, cf = libs

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    class CGSize(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

    class CGRect(ctypes.Structure):
        _fields_ = [("origin", CGPoint), ("size", CGSize)]

    cg.CGMainDisplayID.restype = ctypes.c_uint32
    cg.CGDisplayPixelsWide.restype = ctypes.c_size_t
    cg.CGDisplayPixelsWide.argtypes = [ctypes.c_uint32]
    cg.CGDisplayPixelsHigh.restype = ctypes.c_size_t
    cg.CGDisplayPixelsHigh.argtypes = [ctypes.c_uint32]
    cg.CGDisplayCreateImageForRect.restype = ctypes.c_void_p
    cg.CGDisplayCreateImageForRect.argtypes = [ctypes.c_uint32, CGRect]
    for fn in ("CGImageGetWidth", "CGImageGetHeight", "CGImageGetBytesPerRow",
               "CGImageGetDataProvider", "CGImageRelease"):
        getattr(cg, fn).argtypes = [ctypes.c_void_p]
    cg.CGImageGetWidth.restype = ctypes.c_size_t
    cg.CGImageGetHeight.restype = ctypes.c_size_t
    cg.CGImageGetBytesPerRow.restype = ctypes.c_size_t
    cg.CGImageGetDataProvider.restype = ctypes.c_void_p
    cg.CGDataProviderCopyData.restype = ctypes.c_void_p
    cg.CGDataProviderCopyData.argtypes = [ctypes.c_void_p]
    cf.CFDataGetLength.restype = ctypes.c_long
    cf.CFDataGetLength.argtypes = [ctypes.c_void_p]
    cf.CFDataGetBytePtr.restype = ctypes.c_void_p
    cf.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    did = cg.CGMainDisplayID()
    if region is None:
        x = y = 0.0
        w = int(cg.CGDisplayPixelsWide(did))
        h = int(cg.CGDisplayPixelsHigh(did))
    else:
        x, y, w, h = region
    rect = CGRect(CGPoint(float(x), float(y)), CGSize(float(w), float(h)))
    img = cg.CGDisplayCreateImageForRect(did, rect)
    if not img:
        raise CaptureUnavailable("CGDisplayCreateImageForRect returned null")
    try:
        aw = int(cg.CGImageGetWidth(img))
        ah = int(cg.CGImageGetHeight(img))
        bpr = int(cg.CGImageGetBytesPerRow(img))
        provider = cg.CGImageGetDataProvider(img)
        data = cg.CGDataProviderCopyData(provider)
        if not data:
            raise CaptureUnavailable("CGDataProviderCopyData returned null")
        try:
            length = cf.CFDataGetLength(data)
            ptr = cf.CFDataGetBytePtr(data)
            raw = ctypes.string_at(ptr, length)
        finally:
            cf.CFRelease(data)
        # CoreGraphics display image is 32bpp little-endian (BGRA byte order).
        return _depad(raw, aw, ah, bpr), aw, ah
    finally:
        cg.CGImageRelease(img)


# ---------------------------------------------------------------------------
# Linux / X11 -- Xlib
# ---------------------------------------------------------------------------

_x11_cache = None


def _x11_lib():
    global _x11_cache
    if _x11_cache is None:
        import ctypes
        for name in ("libX11.so.6", "libX11.so"):
            try:
                _x11_cache = ctypes.CDLL(name)
                break
            except OSError:
                continue
        else:
            _x11_cache = False
    return _x11_cache or None


def _x11_grab(region):
    import ctypes

    xlib = _x11_lib()
    if xlib is None:
        raise CaptureUnavailable("libX11 not available")

    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XDefaultScreen.restype = ctypes.c_int
    xlib.XDefaultScreen.argtypes = [ctypes.c_void_p]
    xlib.XDisplayWidth.restype = ctypes.c_int
    xlib.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xlib.XDisplayHeight.restype = ctypes.c_int
    xlib.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xlib.XGetImage.restype = ctypes.c_void_p
    xlib.XGetImage.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int,
    ]
    xlib.XDestroyImage.argtypes = [ctypes.c_void_p]

    class XImage(ctypes.Structure):
        _fields_ = [
            ("width", ctypes.c_int), ("height", ctypes.c_int), ("xoffset", ctypes.c_int),
            ("format", ctypes.c_int), ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
            ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int),
            ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int),
            ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
            ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong),
            ("blue_mask", ctypes.c_ulong),
        ]

    dpy = xlib.XOpenDisplay(None)
    if not dpy:
        raise CaptureUnavailable("XOpenDisplay failed (no X11 display)")
    try:
        root = xlib.XDefaultRootWindow(dpy)
        if region is None:
            scr = xlib.XDefaultScreen(dpy)
            x = y = 0
            w = xlib.XDisplayWidth(dpy, scr)
            h = xlib.XDisplayHeight(dpy, scr)
        else:
            x, y, w, h = region
        zpixmap = 2
        all_planes = (1 << 64) - 1  # AllPlanes (~0 unsigned long)
        ximg_p = xlib.XGetImage(dpy, root, x, y, w, h, all_planes, zpixmap)
        if not ximg_p:
            raise CaptureUnavailable("XGetImage returned null")
        try:
            ximg = ctypes.cast(ximg_p, ctypes.POINTER(XImage)).contents
            if ximg.bits_per_pixel != 32:
                raise CaptureUnavailable(f"unsupported X11 bits_per_pixel {ximg.bits_per_pixel}")
            bpl = ximg.bytes_per_line
            raw = ctypes.string_at(ximg.data, bpl * h)
        finally:
            xlib.XDestroyImage(ximg_p)
        # X11 ZPixmap 32bpp little-endian: byte order B,G,R,X -- treat as BGRA.
        return _depad(raw, w, h, bpl), w, h
    finally:
        xlib.XCloseDisplay(dpy)


# ---------------------------------------------------------------------------
# CaptureSource
# ---------------------------------------------------------------------------


class ScreenCaptureSource:
    """A native CaptureSource: yields PNG frames of the composited output.

    Infinite by design (always-on); bound it with run_continuity(max_frames=...)
    and pace it with ResourceBudget.min_interval_s.  Encodes each grab to PNG, so
    every frame is directly witnessable on disk; for high-rate perception where
    that encode is wasted work, use RawScreenCaptureSource instead.
    """

    def __init__(self, region: tuple[int, int, int, int] | None = None,
                 source_id: str = "screen"):
        self.region = region
        self.source_id = source_id

    def frames(self) -> Iterator[Frame]:
        index = 0
        while True:
            png, w, h = grab_png(self.region)
            yield Frame(
                descriptor=FrameDescriptor(
                    source_id=self.source_id, frame_index=index,
                    width=w, height=h, pixel_format="png",
                ),
                payload=png,
            )
            index += 1


class RawScreenCaptureSource:
    """A native CaptureSource yielding RAW BGRA frames -- the high-rate fast path.

    No per-frame PNG encode: each frame carries the raw BGRA bytes plus geometry
    in its descriptor.  The continuity loop hashes those bytes for identity every
    tick (cheap) and only a real change pays the perceptual hash, computed
    directly from the raw pixels (RawFrameOrgan) -- no encode and no decode, ever.

    Infinite by design; bound with run_continuity(max_frames=...) and pace with
    ResourceBudget.min_interval_s.  The continuity loop selects RawFrameOrgan
    automatically for these raw frames, so no organ needs to be passed.
    """

    def __init__(self, region: tuple[int, int, int, int] | None = None,
                 source_id: str = "screen-raw"):
        self.region = region
        self.source_id = source_id

    def frames(self) -> Iterator[Frame]:
        index = 0
        while True:
            bgra, w, h = grab_raw(self.region)
            yield Frame(
                descriptor=FrameDescriptor(
                    source_id=self.source_id, frame_index=index,
                    width=w, height=h, pixel_format="bgra",
                ),
                payload=bgra,
            )
            index += 1
