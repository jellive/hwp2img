"""**진짜 Windows 에서** 드롭 경로 전체를 왕복시키는 통합 테스트.

`tests/test_dnd.py` 는 `FakeShell32`(순수 파이썬)를 쓴다. 그래서 **ctypes 경계를 한 번도
안 지난다** — 실기기에서 드롭이 통째로 안 먹는데 그 테스트 95개는 전부 초록이었다.
여기서는 실제 `HDROP` 을 만들어 실제 창에 `WM_DROPFILES` 를 보낸다.

★재현하려는 결함(실측 2026-08-24): `argtypes` 를 안 주면 ctypes 가 인자를 **32비트로 자른다.**
  보냄 0x1A2B3C4D5 → C 쪽 도착 0x5D4C3B2B.
  `HDROP` 은 64비트 힙 핸들이라 잘린 채로 `DragQueryFileW` 에 들어가고, 그러면 개수가 0이 되고,
  경로가 0개가 되고, `classify_drop([])` 이 상태를 원래 안내문으로 되돌린다 —
  **어머니 눈에는 아무 일도 안 일어난 것처럼 보인다.**
"""

import ctypes
import sys

import pytest

from hwp2img import dnd

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="진짜 Win32 드롭 경로 테스트")

tk = pytest.importorskip("tkinter")

WM_DROPFILES = 0x0233
GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _DROPFILES(ctypes.Structure):
    """셸이 `WM_DROPFILES` 로 넘기는 메모리 블록의 헤더."""

    _fields_ = [
        ("pFiles", ctypes.c_uint32),  # 파일 목록이 시작하는 오프셋
        ("pt", _POINT),
        ("fNC", ctypes.c_int),
        ("fWide", ctypes.c_int),  # 유니코드면 참
    ]


def _make_hdrop(paths):
    """탐색기가 만드는 것과 같은 모양의 진짜 HDROP 을 만든다."""
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    blob = "".join(p + "\0" for p in paths) + "\0"
    blob_bytes = blob.encode("utf-16-le")
    header_size = ctypes.sizeof(_DROPFILES)

    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, header_size + len(blob_bytes))
    assert handle, "GlobalAlloc 실패"
    address = kernel32.GlobalLock(handle)
    assert address, "GlobalLock 실패"
    try:
        header = _DROPFILES.from_address(address)
        header.pFiles = header_size
        header.fWide = 1
        ctypes.memmove(address + header_size, blob_bytes, len(blob_bytes))
    finally:
        kernel32.GlobalUnlock(handle)
    return handle


def _pump_until(root, done, timeout=10.0):
    """메인 루프를 돌려 `_build_window` 이 건 pump 가 큐를 비우게 한다."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if done():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture(scope="module")
def tk_root():
    """이 모듈 전체가 쓰는 **단 하나의** Tk root.

    전에는 테스트마다 `tk.Tk()` 를 새로 만들고 부쉈다. Tk 는 그걸 반복하면 불안정하다 —
    Windows 러너에서 `Can't find a usable init.tcl` 로 죽었다(2026-08-25 실측, 같은 코드가
    직전 런에서는 통과했으므로 **간헐**이다). `test_dropzone_window.py` 는 이미 같은 이유로
    이 패턴으로 고쳐져 있었는데 이 파일만 옛 패턴이 남아 있었다.

    간헐 실패를 두면 다음의 **진짜** 실패가 "또 그거겠지"로 묻힌다. 그게 진짜 비용이다.
    """
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk 를 띄울 수 없다: {exc}")
    root.withdraw()
    yield root
    try:
        if root.winfo_exists():
            root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def window(tk_root):
    """테스트 하나가 쓰는 창. root 가 아니라 Toplevel 이다."""
    top = tk.Toplevel(tk_root)
    top.withdraw()
    top.update_idletasks()
    yield top
    try:
        if top.winfo_exists():
            top.destroy()
    except tk.TclError:
        pass


def test_attach_actually_succeeds_on_a_real_tk_window(window):
    """`attach()` 는 실패를 조용히 삼키고 False 만 돌려준다 — 정말 걸렸는지 확인한다."""
    hook = dnd.Win32DropHook()
    try:
        assert hook.attach(window.winfo_id(), lambda paths: None) is True
    finally:
        hook.detach()


def test_a_real_wm_dropfiles_delivers_the_exact_path(window):
    """탐색기가 보내는 것과 같은 메시지를 보내고, 경로가 **그대로** 도착하는지 본다.

    이게 실기기에서 깨져 있던 바로 그 경로다.
    """
    received = []
    hook = dnd.Win32DropHook()
    hwnd = window.winfo_id()
    assert hook.attach(hwnd, received.append) is True
    try:
        user32 = ctypes.windll.user32
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        hdrop = _make_hdrop([r"C:\Users\m\공문.hwp"])
        user32.SendMessageW(hwnd, WM_DROPFILES, hdrop, 0)
    finally:
        hook.detach()

    assert received == [[r"C:\Users\m\공문.hwp"]]


def test_several_dropped_files_all_arrive(window):
    received = []
    hook = dnd.Win32DropHook()
    hwnd = window.winfo_id()
    assert hook.attach(hwnd, received.append) is True
    try:
        user32 = ctypes.windll.user32
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        ]
        hdrop = _make_hdrop([r"C:\a.hwp", r"C:\b.hwp", r"C:\c.hwp"])
        user32.SendMessageW(hwnd, WM_DROPFILES, hdrop, 0)
    finally:
        hook.detach()

    assert received == [[r"C:\a.hwp", r"C:\b.hwp", r"C:\c.hwp"]]


def test_other_messages_still_reach_the_original_window_procedure(window):
    """서브클래싱이 `WM_DROPFILES` 말고는 원래 창 프로시저로 넘겨야 한다.
    안 그러면 창이 그려지지도, 닫히지도 않는다."""
    hook = dnd.Win32DropHook()
    hwnd = window.winfo_id()
    assert hook.attach(hwnd, lambda paths: None) is True
    try:
        window.title("드롭훅 붙은 뒤")
        window.update()  # 메시지가 정상 처리돼야 여기서 안 멈춘다
        assert window.winfo_exists()
    finally:
        hook.detach()
    window.update()
    assert window.winfo_exists()


# --- 드롭존 **전체 배선** (실기기에서 죽은 자리) ------------------------------


def test_the_whole_dropzone_survives_a_real_drop(tk_root):
    """지금까지의 테스트는 드롭 콜백이 `list.append` 였다 — **Tk 를 안 만진다.**

    실기기는 창이 뜨고 나서 **드롭하는 순간 죽었다.** 그 경로는 여기부터다:
    WndProc 콜백 → `root.after` → 컨트롤러 → 워커 스레드 → 결과를 다시 메인 루프로.
    파일명에 **띄어쓰기와 괄호**를 넣는다 — 실기기에서 죽은 파일이 그런 이름이었다.
    """
    from hwp2img import dropzone

    dropped = r"C:\Users\m\공문 최종 (수정).hwp"
    converted = []

    root, controller, hooks = dropzone._build_window(
        convert=lambda path: (converted.append(path), path + "_변환.png")[1],
        drop_hook=None,  # ★진짜 Win32DropHook 을 쓴다
        root=tk.Toplevel(tk_root),
    )
    try:
        root.withdraw()
        root.update()
        assert hooks, "훅이 하나도 안 붙었다"

        user32 = ctypes.windll.user32
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
        ]
        user32.SendMessageW(root.winfo_id(), WM_DROPFILES, _make_hdrop([dropped]), 0)

        # 창이 아직 살아 있어야 한다 — 실기기에서는 여기서 죽었다
        assert root.winfo_exists(), "드롭 직후 창이 사라졌다"

        # 드롭은 이제 **큐에 들어간다** — 메인 루프의 pump 가 가져가야 변환이 시작된다.
        # 그래서 state 로만 기다리면 아직 IDLE 이라 루프가 즉시 빠진다.
        _pump_until(root, lambda: converted and controller.state == dropzone.IDLE)

        assert root.winfo_exists(), "변환이 끝난 뒤 창이 사라졌다"
        assert converted == [dropped], f"변환에 안 넘어갔다: {converted}"
        assert controller.state == dropzone.IDLE
    finally:
        for hook, _hwnd in hooks:
            hook.detach()
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass


def test_a_drop_still_works_when_the_window_is_the_only_hook_target(tk_root):
    """`_drop_target_handles` 가 후보를 두 개 돌려주면 같은 창에 훅이 둘 붙는다.
    그 상태에서도 드롭이 한 번만 처리돼야 한다(두 번 변환하면 안 된다)."""
    from hwp2img import dropzone

    calls = []
    root, controller, hooks = dropzone._build_window(
        convert=lambda path: (calls.append(path), "out.png")[1],
        drop_hook=None,
        root=tk.Toplevel(tk_root),
    )
    try:
        root.withdraw()
        root.update()
        user32 = ctypes.windll.user32
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
        ]
        user32.SendMessageW(root.winfo_id(), WM_DROPFILES, _make_hdrop([r"C:\a b.hwp"]), 0)

        _pump_until(root, lambda: calls and controller.state == dropzone.IDLE)
        # 훅이 둘 붙어도 변환은 한 번만 — 두 번 돌면 한글 COM 이 동시에 두 개 뜬다
        assert calls == [r"C:\a b.hwp"], f"변환 호출이 {len(calls)}번이다"
    finally:
        for hook, _hwnd in hooks:
            hook.detach()
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass
