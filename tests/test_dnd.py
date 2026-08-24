"""탐색기 → 창 드롭(WM_DROPFILES) 훅.

실제 후킹은 Windows 에서만 되지만, **경로 추출**은 shell32 를 주입해 여기서 검증한다.
레드팀이 "복수 선택 드롭은 한 메시지에 여러 경로가 온다" 고 지적했고, 그 경계가
실제로 존재한다는 것을 이 테스트가 고정한다.
"""

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
