"""임시 계측 — 드롭 경로의 각 경계에서 무슨 값이 오가는지 실제 Windows 에서 찍는다.

원인이 확정되면 이 파일은 지운다. 추측을 쌓는 대신 경계마다 실측하려고 둔 것이다.
"""

import ctypes
import sys
import traceback

import pytest

from hwp2img import dnd

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Win32 전용 계측")

tk = pytest.importorskip("tkinter")

WM_DROPFILES = 0x0233


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", ctypes.c_uint32),
        ("pt", _POINT),
        ("fNC", ctypes.c_int),
        ("fWide", ctypes.c_int),
    ]


def _make_hdrop(paths):
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    blob = ("".join(p + "\0" for p in paths) + "\0").encode("utf-16-le")
    header_size = ctypes.sizeof(_DROPFILES)
    handle = kernel32.GlobalAlloc(0x0042, header_size + len(blob))
    address = kernel32.GlobalLock(handle)
    try:
        header = _DROPFILES.from_address(address)
        header.pFiles = header_size
        header.fWide = 1
        ctypes.memmove(address + header_size, blob, len(blob))
    finally:
        kernel32.GlobalUnlock(handle)
    return handle


def test_probe_every_boundary_of_the_drop_path():
    facts = []
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    hwnd = root.winfo_id()
    facts.append(f"hwnd={hwnd:#x} (bit_length={hwnd.bit_length()})")

    seen = {}

    # dnd 의 진짜 dispatch 를 흉내내되, 각 단계를 기록한다.
    wndproc_type = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
    )
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    old_holder = {}

    def _dispatch(handle, message, wparam, lparam):
        if message == WM_DROPFILES:
            seen["called"] = True
            seen["wparam"] = wparam
            try:
                seen["paths"] = dnd.extract_dropped_paths(wparam)
            except BaseException as exc:  # noqa: BLE001 — 무엇이 나오는지가 알고 싶은 것
                seen["exc"] = f"{type(exc).__name__}: {exc}"
                seen["tb"] = traceback.format_exc()[-400:]
            return 0
        return user32.CallWindowProcW(old_holder.get("old", 0), handle, message, wparam, lparam)

    proc = wndproc_type(_dispatch)
    shell32.DragAcceptFiles.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    shell32.DragAcceptFiles(hwnd, True)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    set_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [
        ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
    ]
    old_holder["old"] = set_long(hwnd, -4, ctypes.cast(proc, ctypes.c_void_p).value)
    facts.append(f"old_wndproc={old_holder['old']:#x}")

    hdrop = _make_hdrop([r"C:\Users\m\공문.hwp"])
    facts.append(f"hdrop={hdrop:#x} (bit_length={int(hdrop).bit_length()})")

    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW(hwnd, WM_DROPFILES, hdrop, 0)

    facts.append(f"dispatch 호출됨? {seen.get('called', False)}")
    facts.append(f"wparam 도착값={seen.get('wparam', 'N/A') if not isinstance(seen.get('wparam'), int) else hex(seen['wparam'])}")
    facts.append(f"wparam == hdrop ? {seen.get('wparam') == hdrop}")
    facts.append(f"paths={seen.get('paths', 'N/A')}")
    facts.append(f"exception={seen.get('exc', '없음')}")
    facts.append(f"tb={seen.get('tb', '')}")

    # argtypes 를 준 shell32 로 같은 hdrop 을 직접 읽어 본다 (핸들 자체가 유효한지)
    try:
        s2 = ctypes.WinDLL("shell32")
        s2.DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
        s2.DragQueryFileW.restype = ctypes.c_uint
        hdrop2 = _make_hdrop([r"C:\Users\m\공문.hwp"])
        cnt = s2.DragQueryFileW(hdrop2, 0xFFFFFFFF, None, 0)
        buf = ctypes.create_unicode_buffer(32768)
        s2.DragQueryFileW(hdrop2, 0, buf, 32768)
        facts.append(f"[argtypes 준 경우] count={cnt} path={buf.value!r}")
    except BaseException as exc:  # noqa: BLE001
        facts.append(f"[argtypes 준 경우] 터짐 {type(exc).__name__}: {exc}")

    # argtypes 없이 같은 것을 해 본다
    try:
        s3 = ctypes.WinDLL("shell32")
        hdrop3 = _make_hdrop([r"C:\Users\m\공문.hwp"])
        cnt3 = s3.DragQueryFileW(hdrop3, 0xFFFFFFFF, None, 0)
        facts.append(f"[argtypes 없는 경우] count={cnt3}")
    except BaseException as exc:  # noqa: BLE001
        facts.append(f"[argtypes 없는 경우] 터짐 {type(exc).__name__}: {exc}")

    set_long(hwnd, -4, old_holder["old"])
    root.destroy()

    raise AssertionError("=== 계측 결과 ===\n" + "\n".join(facts))
