"""탐색기 → 창 드롭(WM_DROPFILES) 훅.

실제 후킹은 Windows 에서만 되지만, **경로 추출**은 shell32 를 주입해 여기서 검증한다.
레드팀이 "복수 선택 드롭은 한 메시지에 여러 경로가 온다" 고 지적했고, 그 경계가
실제로 존재한다는 것을 이 테스트가 고정한다.
"""

import ctypes

from hwp2img import dnd


class FakeShell32:
    """DragQueryFileW 의 실제 규약을 흉내낸다.

    - (hdrop, 0xFFFFFFFF, None, 0) → 파일 개수
    - (hdrop, i, buf, size)        → buf 에 i 번째 경로를 쓰고 길이를 돌려준다
    """

    def __init__(self, paths):
        self.paths = paths
        self.finished = []

    def DragQueryFileW(self, hdrop, index, buf, size):
        if index == 0xFFFFFFFF:
            return len(self.paths)
        buf.value = self.paths[index]
        return len(self.paths[index])

    def DragFinish(self, hdrop):
        self.finished.append(hdrop)


def test_extracts_a_single_dropped_path():
    shell32 = FakeShell32([r"C:\Users\m\문서.hwp"])
    assert dnd.extract_dropped_paths(1234, shell32) == [r"C:\Users\m\문서.hwp"]


def test_extracts_every_path_when_several_files_arrive_in_one_message():
    shell32 = FakeShell32(["a.hwp", "b.hwp", "c.hwp"])
    assert dnd.extract_dropped_paths(1234, shell32) == ["a.hwp", "b.hwp", "c.hwp"]


def test_releases_the_drop_handle_even_when_there_are_no_paths():
    """DragFinish 를 빼먹으면 드롭할 때마다 셸 메모리가 샌다."""
    shell32 = FakeShell32([])
    assert dnd.extract_dropped_paths(1234, shell32) == []
    assert shell32.finished == [1234]


def test_releases_the_drop_handle_after_a_successful_extraction():
    shell32 = FakeShell32(["a.hwp"])
    dnd.extract_dropped_paths(1234, shell32)
    assert shell32.finished == [1234]


def test_non_windows_gets_a_hook_that_does_nothing_instead_of_crashing():
    hook = dnd.create_drop_hook(platform_name="darwin")
    assert hook.attach(hwnd=1, on_files=lambda paths: None) is False
    hook.detach()  # 예외가 나면 안 된다


def test_windows_gets_the_real_hook():
    hook = dnd.create_drop_hook(platform_name="win32")
    assert isinstance(hook, dnd.Win32DropHook)


# --- 64비트 핸들이 프로토타입을 통과하나 (실기기 결함의 재발 방지) --------------


class FakeDll:
    """`argtypes`/`restype` 를 대입할 수 있는 가짜 DLL. 진짜 ctypes 와 같은 모양이다."""

    class _Func:
        def __init__(self):
            self.argtypes = None
            self.restype = "미설정"

        def __call__(self, *args):
            return 0

    def __init__(self):
        self.DragQueryFileW = self._Func()
        self.DragFinish = self._Func()
        self.DragAcceptFiles = self._Func()


def test_configure_declares_a_pointer_sized_handle_for_every_shell32_call():
    """실기기 결함 재발 방지. `HDROP` 을 `c_int` 로 두면 42비트 핸들에서 죽는다."""
    dll = dnd.configure(FakeDll())

    assert dll.DragQueryFileW.argtypes[0] is dnd.HDROP
    assert dll.DragFinish.argtypes == [dnd.HDROP]
    assert dll.DragAcceptFiles.argtypes[0] is dnd.HDROP
    assert dnd.HDROP is ctypes.c_void_p, "핸들은 포인터 크기여야 한다"
    # restype 도 반드시 정한다 — 기본값 c_int 는 개수를 잘못 읽을 수 있다
    assert dll.DragQueryFileW.restype is ctypes.c_uint


def test_a_real_42bit_handle_survives_our_declared_prototype():
    """**진짜 ctypes 마샬링**으로 왕복시킨다 — 가짜 객체로는 이 결함을 못 잡는다.

    0x264596e0088 은 Windows 러너에서 실제로 관측된 HDROP 이다(42비트).
    `argtypes` 를 `c_int` 로 되돌리면 이 테스트가 깨진다.
    """
    measured_hdrop = 0x264596E0088
    assert measured_hdrop.bit_length() == 42

    seen = {}

    prototype = ctypes.CFUNCTYPE(ctypes.c_uint, *dnd._DRAGQUERY_ARGTYPES)

    def impl(hdrop, index, buffer, size):
        seen["hdrop"] = hdrop
        seen["index"] = index
        return 0

    callback = prototype(impl)
    callback(measured_hdrop, 0xFFFFFFFF, None, 0)

    assert seen["hdrop"] == measured_hdrop, "핸들이 마샬링에서 변형됐다"
    assert seen["index"] == 0xFFFFFFFF, "개수 요청 상수가 변형됐다"


def test_the_old_prototype_would_have_mangled_that_handle():
    """왜 고쳤는지를 고정한다 — 예전 형태(c_int)에서는 같은 값이 살아남지 못한다."""
    measured_hdrop = 0x264596E0088
    seen = {}

    prototype = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_int, ctypes.c_uint,
                                 ctypes.c_wchar_p, ctypes.c_uint)

    def impl(hdrop, index, buffer, size):
        seen["hdrop"] = hdrop
        return 0

    callback = prototype(impl)
    try:
        callback(measured_hdrop, 0, None, 0)
    except (ctypes.ArgumentError, OverflowError):
        return  # Windows 는 여기서 던진다 — 그게 실기기에서 본 것이다
    assert seen["hdrop"] != measured_hdrop, "c_int 인데 42비트가 온전히 통과했다?"


def test_the_default_path_goes_through_the_configured_shell32(monkeypatch):
    """기본 경로가 **설정 안 된** raw DLL 을 쓰면 실기기에서 그대로 다시 죽는다.

    Mac 에서는 `ctypes.windll` 이 없어 진짜 기본 경로를 못 지나므로, 최소한
    `_shell32()`(= argtypes 를 박아 둔 것)를 거치는지는 여기서 고정한다.
    """
    fake = FakeShell32([r"C:\a.hwp"])
    used = []
    monkeypatch.setattr(dnd, "_shell32", lambda: (used.append(True), fake)[1])

    assert dnd.extract_dropped_paths(0x264596E0088) == [r"C:\a.hwp"]
    assert used == [True], "_shell32() 를 안 거치고 raw DLL 을 썼다"
