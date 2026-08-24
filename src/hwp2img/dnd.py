"""탐색기에서 창 안으로 파일을 끌어다 놓는 것(`WM_DROPFILES`)을 받는다.

**pywin32 가 아니라 `ctypes` 로 `shell32`/`user32` 를 직접 부른다.** 이 둘은 모든
Windows 에 있는 OS 기본 DLL 이라 PyInstaller 가 무엇을 수집하든 무관하다. pywin32 는
이미 requirements 에 있지만 "의존성에 있다" 와 "얼린 exe 에 그 하위 모듈과 DLL 이
들어간다" 는 별개다(크로스모델 리뷰 지적) — 이 레포는 정확히 그 장르로 두 번 데었다
(`--collect-all pyhwpx` 누락, 보안승인모듈 등록 실패).

★**여기가 실패해도 앱은 계속 쓸 수 있어야 한다.** 관리자 권한 차이(UIPI)로 드롭이
아예 차단되는 환경이 있고, 그건 개발 PC 에서 재현되지 않는다. 그래서 `attach()` 는
예외를 밖으로 내보내지 않고 `False` 를 돌려주며, 창은 "파일 고르기" 버튼으로 변환을
끝까지 마칠 수 있게 만들어져 있다(`dropzone.py`).
"""

import ctypes

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4

# Windows 롱패스 여유. `DragQueryFileW` 가 잘라 쓰므로 넉넉해도 손해가 없다.
_PATH_BUFFER_CHARS = 32768

_DRAGQUERY_COUNT = 0xFFFFFFFF

# ★★Win32 함수에는 **반드시** argtypes 를 박는다. 이걸 빼먹어서 실기기에서 드롭이
#   통째로 안 먹었다(2026-08-24). Windows 러너 실측:
#
#     hdrop = 0x264596e0088   ← **42비트**. c_int 에 안 들어간다
#     argtypes 없이 호출 → ctypes.ArgumentError: argument 1: OverflowError: int too long to convert
#     argtypes 주고 호출 → count=1, path='C:\Users\m\공문.hwp'   ✅
#
#   Mac 에서는 같은 상황이 조용히 32비트로 **잘리기만** 해서 증상이 다르게 보인다 —
#   그래서 로컬 재현만으로는 메커니즘을 오해한다.
#   그리고 그 예외는 `_dispatch` 의 `except` 에 먹혀서 **화면상 아무 일도 안 일어난다.**
HDROP = ctypes.c_void_p
_DRAGQUERY_ARGTYPES = [HDROP, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]


def configure(shell32):
    """`shell32` 의 프로토타입을 64비트 안전하게 박는다. 설정한 객체를 그대로 돌려준다."""
    shell32.DragQueryFileW.argtypes = _DRAGQUERY_ARGTYPES
    shell32.DragQueryFileW.restype = ctypes.c_uint
    shell32.DragFinish.argtypes = [HDROP]
    shell32.DragFinish.restype = None
    shell32.DragAcceptFiles.argtypes = [HDROP, ctypes.c_bool]
    shell32.DragAcceptFiles.restype = None
    return shell32


_configured_shell32 = None


def _shell32():
    """프로토타입을 박은 shell32. 한 번만 설정한다."""
    global _configured_shell32
    if _configured_shell32 is None:
        _configured_shell32 = configure(ctypes.windll.shell32)
    return _configured_shell32


def extract_dropped_paths(hdrop, shell32=None) -> list[str]:
    """`WM_DROPFILES` 의 hDrop 핸들에서 떨어진 파일 경로를 **전부** 뽑는다.

    탐색기에서 여러 개를 선택해 떨어뜨리면 **한 메시지에 여러 경로가 온다.** 첫 개만
    읽으면 나머지가 조용히 사라지므로 개수를 먼저 물어보고 전부 읽는다. 판정(한 개만
    받는다)은 `dropzone.classify_drop` 이 하고, 여기서는 사실만 전달한다.

    `DragFinish` 는 **반드시** 부른다 — 빼먹으면 드롭할 때마다 셸 메모리가 샌다.
    """
    if shell32 is None:
        shell32 = _shell32()

    try:
        count = shell32.DragQueryFileW(hdrop, _DRAGQUERY_COUNT, None, 0)
        paths = []
        for index in range(count):
            buffer = ctypes.create_unicode_buffer(_PATH_BUFFER_CHARS)
            shell32.DragQueryFileW(hdrop, index, buffer, _PATH_BUFFER_CHARS)
            paths.append(buffer.value)
        return paths
    finally:
        shell32.DragFinish(hdrop)


class NullDropHook:
    """Windows 가 아닌 곳(개발 Mac)과 테스트용 — 아무것도 하지 않는다."""

    def attach(self, hwnd, on_files, on_error=None) -> bool:
        return False

    def detach(self) -> None:
        pass


class Win32DropHook:
    """창의 WndProc 을 가로채 `WM_DROPFILES` 만 먼저 처리한다.

    ★`self._proc` 참조를 반드시 붙들고 있어야 한다. ctypes 콜백 객체가 GC 되면
    Windows 는 해제된 메모리를 함수 포인터로 부르게 된다.
    """

    def __init__(self):
        self._hwnd = None
        self._old_proc = None
        self._proc = None
        self._on_files = None

    def attach(self, hwnd, on_files, on_error=None) -> bool:
        """`on_error(exc)` 를 주면 드롭 처리 중 난 예외를 알려 준다.

        예외를 밖으로 내보낼 수는 없다 — WndProc 안에서 터지면 Windows 가 거기서 죽는다.
        그런데 **조용히 삼키면 어머니 눈에는 드롭이 그냥 무반응으로 보인다.** 실제로
        그것 때문에 실기기 왕복을 한 번 했다. 삼키되, 알릴 수는 있게 둔다.
        """
        try:
            user32 = ctypes.windll.user32
            _shell32().DragAcceptFiles(hwnd, True)

            old_proc = [0]

            wndproc_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_size_t,
                ctypes.c_ssize_t,
            )

            def _dispatch(handle, message, wparam, lparam):
                if message == WM_DROPFILES:
                    try:
                        on_files(extract_dropped_paths(wparam))
                    except Exception as exc:
                        # 드롭 처리가 터져도 창은 살아 있어야 한다. 여기서 예외가
                        # 새어나가면 Windows 가 우리 WndProc 안에서 죽는다.
                        # 단 **조용히 죽지는 않는다** — 알릴 수단이 있으면 알린다.
                        if on_error is not None:
                            try:
                                on_error(exc)
                            except Exception:
                                pass
                    return 0
                # ★`set_long()` 이 돌아오는 순간부터 메시지가 여기로 들어온다. 예전에는
                #   `self._old_proc` 을 그 **뒤에** 대입해서, 그 사이에 온 메시지가
                #   `None` 을 원래 프로시저로 넘겼다. 원래 것을 아직 모르면 기본 처리로 보낸다.
                previous = old_proc[0]
                if not previous:
                    return user32.DefWindowProcW(handle, message, wparam, lparam)
                return user32.CallWindowProcW(previous, handle, message, wparam, lparam)

            proc = wndproc_type(_dispatch)

            # 64비트에서 argtypes/restype 을 안 주면 포인터가 32비트로 잘려 들어간다.
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            set_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            user32.CallWindowProcW.restype = ctypes.c_ssize_t
            user32.CallWindowProcW.argtypes = [
                ctypes.c_ssize_t,
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_size_t,
                ctypes.c_ssize_t,
            ]
            user32.DefWindowProcW.restype = ctypes.c_ssize_t
            user32.DefWindowProcW.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_size_t,
                ctypes.c_ssize_t,
            ]

            old = set_long(hwnd, GWLP_WNDPROC, ctypes.cast(proc, ctypes.c_void_p).value)
            if not old:
                return False
            old_proc[0] = old

            self._hwnd = hwnd
            self._old_proc = old
            self._proc = proc
            self._on_files = on_files
            return True
        except Exception:
            # 드롭을 못 걸었을 뿐이다 — 파일 고르기 버튼으로 변환은 그대로 된다.
            return False

    def detach(self) -> None:
        try:
            if self._hwnd is not None and self._old_proc is not None:
                user32 = ctypes.windll.user32
                set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
                set_long(self._hwnd, GWLP_WNDPROC, self._old_proc)
        except Exception:
            pass
        finally:
            self._hwnd = None
            self._old_proc = None
            self._proc = None


def create_drop_hook(platform_name=None):
    """플랫폼에 맞는 훅을 준다. Windows 가 아니면 아무것도 안 하는 훅이다."""
    if platform_name is None:
        import sys

        platform_name = sys.platform
    return Win32DropHook() if platform_name == "win32" else NullDropHook()
