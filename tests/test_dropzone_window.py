"""**진짜 Tk 창**으로 `_build_window` 를 돌려 보는 스모크 테스트.

나머지 드롭존 테스트는 view 를 주입해 상태 전이만 본다. 그것만으로는 **창을 만드는 코드
자체가 한 줄도 실행되지 않는다** — 위젯 인자 오타나 없는 옵션 하나가 그대로 배포까지 간다.
`--noconsole` 로 얼린 exe 라 어머니 PC 에서는 그게 "아이콘만 반짝이고 끝" 으로 보이고,
그 PC 에서는 디버그할 수도 없다. 그래서 여기서 실제로 띄워 본다.

★**Tk 를 못 띄우는 환경인지는 모듈 진입 때 한 번만 잰다.** 처음엔 fixture 안에서
`except TclError: skip` 으로 처리했는데, **그게 위젯 인자 오타(`TclError`)까지 같이
삼켰다** — 변이 검사에서 `justify` 를 `justfy` 로 바꿔도 skip 이 돼서 초록으로 보였다.
잡으려던 바로 그 결함을 못 잡는 테스트였다.

★**이게 Windows 검증을 대신하지는 않는다.** 여기서 도는 것은 Tk 배선뿐이다.
Win32 드롭 후킹(`dnd.Win32DropHook`)·PyInstaller 패키징·`--noconsole` 동작은 여전히
Windows 실기기에서만 확인된다. Tk 버전도 다르다(Mac 9.0 / Windows 파이썬 3.11 은 8.6).
"""

import threading
import time

import pytest

from hwp2img import dropzone, messages

tk = pytest.importorskip("tkinter", reason="이 파이썬에 _tkinter 가 없다")


# 디스플레이가 없어서 못 띄우는 것과, 코드가 틀려서 못 띄우는 것을 **가른다.**
# 앞엣것만 skip 이다. `TclError` 를 통째로 skip 하면 위젯 인자 오타까지 같이 삼켜서
# 잡으려던 결함이 초록으로 보인다(변이 검사가 실제로 그걸 잡았다).
# ★모듈 진입 때 Tk root 를 미리 하나 띄워 보는 방식은 쓰지 않는다 — pymupdf/PIL 이
#   로드된 pytest 프로세스에서 root 를 만들었다 부수고 다시 만들면 macOS Tk 가
#   `update_idletasks` 에서 세그폴트했다(실측). 프로세스당 root 하나로 간다.
_DISPLAY_FAILURE_HINTS = ("no display name", "couldn't connect", "DISPLAY", "can't find a usable")


class RecordingHook:
    def __init__(self):
        self.attached = []
        self.detached = 0

    def attach(self, hwnd, on_files):
        self.attached.append((hwnd, on_files))
        return True

    def detach(self):
        self.detached += 1


def _build(convert=None, hook=None):
    """창을 만들고 곧바로 감춘다 — 테스트가 화면을 점거하지 않게.

    여기서는 `TclError` 를 잡지 않는다(모듈 상단 주석 참고).
    """
    hook = hook or RecordingHook()
    try:
        root, controller, hooks = dropzone._build_window(
            convert=convert or (lambda path: f"{path}_변환.png"),
            drop_hook=hook,
        )
    except tk.TclError as exc:
        if any(hint in str(exc) for hint in _DISPLAY_FAILURE_HINTS):
            pytest.skip(f"이 환경에서는 Tk 창을 띄울 수 없다: {exc}")
        raise  # 위젯 인자 오류 같은 진짜 결함은 통과시키지 않는다
    root.withdraw()
    return root, controller, hooks


@pytest.fixture
def window():
    root, controller, hooks = _build()
    try:
        yield root, controller, hooks
    finally:
        if root.winfo_exists():
            root.destroy()


def _settle(root, controller, timeout=5.0):
    """워커가 결과를 메인 루프에 넘기고 IDLE 로 돌아올 때까지 이벤트를 돌린다.

    ★**살아 있는 워커를 두고 `root.destroy()` 하면 프로세스가 통째로 죽는다.** 그 워커가
    파괴된 Tk 를 만지는 순간 Tcl 이 패닉하는데, 그건 파이썬 예외가 아니라 `abort()` 라
    try/except 로 못 잡는다. CI 실측(2026-08-24): Windows `0x80000003` ·
    macOS `Abort trap: 6`. 게다가 **나중에** 터져서 엉뚱한 테스트가 죽은 것처럼 보였다.

    실앱은 `can_close()` 가 변환 중 닫기를 막아 이 상황 자체를 안 만든다 — 이 테스트가
    그 보호를 일부러 우회했기 때문에 생기는 일이다.
    """
    deadline = time.monotonic() + timeout
    while controller.state == dropzone.PROCESSING and time.monotonic() < deadline:
        if _window_is_open(root):
            root.update()
        time.sleep(0.01)
    return controller.state


def _window_is_open(root) -> bool:
    """루트를 파괴하면 Tcl 인터프리터째 사라져 `winfo` 호출 자체가 던진다.
    `_TkView.is_alive()` 가 같은 이유로 같은 모양을 하고 있다."""
    try:
        return bool(root.winfo_exists())
    except tk.TclError:
        return False


def _widgets(parent):
    found = [parent]
    for child in parent.winfo_children():
        found.extend(_widgets(child))
    return found


def _texts(root):
    return [w.cget("text") for w in _widgets(root) if "text" in w.keys()]


# --- 창이 실제로 만들어지나 -------------------------------------------------


def test_the_window_actually_builds_with_the_prompt_visible(window):
    root, _controller, _hooks = window
    assert root.title() == dropzone.WINDOW_TITLE
    texts = _texts(root)
    assert any(messages.PROMPT in t for t in texts)
    assert any(messages.BROWSE_BUTTON in t for t in texts)


def test_drop_target_handles_parses_the_frame_handle_without_blowing_up():
    """`wm_frame()` 은 '0x…' 문자열이라 파싱이 필요하다. 클라이언트 핸들과 같으면
    중복을 뺀다 — 안 그러면 같은 창을 두 번 서브클래싱한다."""
    root, _controller, _hooks = _build()
    try:
        handles = dropzone._drop_target_handles(root)
        assert handles, "후보 핸들이 하나도 없다"
        assert all(isinstance(h, int) and h != 0 for h in handles)
        assert len(handles) == len(set(handles)), "중복이 안 걸러졌다"
        assert root.winfo_id() in handles
    finally:
        root.destroy()


def test_the_drop_hook_is_attached_to_a_real_window_handle(window):
    _root, _controller, hooks = window
    assert len(hooks) == 1
    hook, hwnd = hooks[0]
    assert hook.attached, "attach 가 안 불렸다"
    assert isinstance(hwnd, int) and hwnd != 0


# --- 배선이 실제로 도나 -----------------------------------------------------


def test_status_text_really_changes_through_the_tk_view(window):
    """`_TkView.set_status` 가 진짜 위젯에 먹히는지 — 가짜 view 로는 못 보는 부분."""
    root, controller, _hooks = window
    controller.handle_paths(["보고서.pdf"])  # 거절 경로라 스레드가 안 뜬다
    root.update()
    assert any("한글 문서 파일" in t for t in _texts(root))


def test_a_drop_from_the_hook_is_marshalled_onto_the_main_loop(window):
    """드롭 콜백은 `WM_DROPFILES` 스택 안에서 불린다 — 그 자리에서 Tk 를 만지면
    Tcl 이 재진입한다. `root.after` 로 넘어가는지 실제 메인 루프로 확인한다."""
    root, _controller, hooks = window
    on_dropped = hooks[0][0].attached[0][1]

    on_dropped(["a.hwp", "b.hwp"])  # 두 개 → 거절 경로 (변환 안 뜬다)
    assert not any(messages.TOO_MANY_FILES in t for t in _texts(root)), "즉시 실행됐다 — 마샬링 안 됨"

    root.update()  # 여기서 after(0) 이 돈다
    assert any(messages.TOO_MANY_FILES in t for t in _texts(root))


# --- 닫기 가로채기 ----------------------------------------------------------


def _click_the_close_box(root):
    """창의 X 버튼을 누른 것과 같다 — 등록된 WM_DELETE_WINDOW 핸들러를 실제로 부른다.

    `root.protocol("WM_DELETE_WINDOW")` 는 **등록을 안 해도** Tk 기본값(`…destroy`)을
    돌려준다. 그래서 반환값이 참인지 보는 것만으로는 등록 여부를 못 가른다 — 변이 검사가
    그걸 잡았다. 부르고 나서 창이 어떻게 됐는지로 판정한다.
    """
    root.tk.call(root.protocol("WM_DELETE_WINDOW"))


def test_closing_while_converting_keeps_the_window_alive():
    """변환 중 창을 닫으면 워커(daemon)와 watchdog 자식이 --noconsole 뒤에 남는다."""
    gate = threading.Event()
    root, controller, _hooks = _build(convert=lambda path: (gate.wait(5), "out.png")[1])
    try:
        controller.handle_paths(["C:/x/a.hwp"])
        assert controller.state == dropzone.PROCESSING

        _click_the_close_box(root)
        assert _window_is_open(root), "변환 중인데 창이 닫혔다"
        root.update()
        assert any(messages.BUSY in t for t in _texts(root))
    finally:
        gate.set()
        assert _settle(root, controller) == dropzone.IDLE, "워커가 안 끝났다 — 지금 창을 부수면 프로세스가 죽는다"
        if _window_is_open(root):
            root.destroy()


def test_closing_while_idle_really_closes_the_window():
    root, controller, _hooks = _build()
    assert controller.state == dropzone.IDLE
    _click_the_close_box(root)
    assert not _window_is_open(root), "닫혀야 하는데 안 닫혔다"


# --- 파일 고르기 버튼 (드롭이 막힌 환경의 폴백) ------------------------------


def test_the_browse_button_feeds_the_chosen_file_into_the_same_path(window, monkeypatch):
    from tkinter import filedialog

    root, controller, _hooks = window
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **kw: "고른파일.pdf")

    buttons = [w for w in _widgets(root) if isinstance(w, tk.Button)]
    assert len(buttons) == 1
    buttons[0].invoke()
    root.update()

    assert any("한글 문서 파일" in t for t in _texts(root))  # 같은 판정 경로를 탔다
    assert controller.state == dropzone.IDLE


def test_cancelling_the_browse_dialog_does_nothing(window, monkeypatch):
    from tkinter import filedialog

    root, controller, _hooks = window
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **kw: "")

    before = _texts(root)
    [w for w in _widgets(root) if isinstance(w, tk.Button)][0].invoke()
    root.update()

    assert _texts(root) == before
    assert controller.state == dropzone.IDLE


# --- launch() 의 나머지 절반 ------------------------------------------------


def test_launch_runs_the_main_loop_and_detaches_the_hook_on_the_way_out(monkeypatch):
    hook = RecordingHook()
    built = _build(hook=hook)
    root = built[0]
    root.after(10, root.destroy)  # 메인 루프가 실제로 돌아야 이게 실행된다
    monkeypatch.setattr(dropzone, "_build_window", lambda *a, **k: built)

    assert dropzone.launch(convert=lambda p: "out.png") == 0
    assert hook.detached == 1
