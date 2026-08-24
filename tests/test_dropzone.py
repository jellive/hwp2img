"""드롭존 창의 **판정과 상태 전이**를 Tk 없이 검증한다.

실제 Tk 창은 이 Mac 에서 띄울 수 없을 수도 있다(`_tkinter` 부재). 그래서
`DropZoneController` 는 view 를 주입받고, 여기서는 가짜 view 를 넣는다.

★이 파일의 제일 중요한 계약: **메인 스레드가 아닌 곳에서는 view 를 만지지 않는다.**
실기기에서 앱이 드롭하는 순간 죽은 원인이 그것이었다(tkinter 는 스레드 안전하지 않다).
`ExplodingView` 를 쓰는 테스트들이 그 계약을 고정한다.
"""

import pytest

from hwp2img import dropzone, messages
from hwp2img.errors import HwpTimeoutError, UnsupportedFileError


class FakeView:
    def __init__(self, alive=True):
        self.statuses = []
        self._alive = alive

    def set_status(self, text):
        self.statuses.append(text)

    def is_alive(self):
        return self._alive

    def close(self):
        self._alive = False

    @property
    def last(self):
        return self.statuses[-1] if self.statuses else None


class ExplodingView:
    """건드리기만 해도 터진다 — '이 자리에서 view 를 만지면 안 된다' 를 고정하는 데 쓴다."""

    def set_status(self, text):
        raise AssertionError("메인 스레드가 아닌 곳에서 view.set_status 를 불렀다")

    def is_alive(self):
        raise AssertionError("메인 스레드가 아닌 곳에서 view.is_alive 를 불렀다")


def _sync_spawn(fn):
    """워커 스레드 대신 그 자리에서 실행한다."""
    fn()


def _controller(convert, view=None, spawn=_sync_spawn, describe_error=None):
    return dropzone.DropZoneController(
        view=view if view is not None else FakeView(),
        convert=convert,
        spawn=spawn,
        describe_error=describe_error,
    )


# --- 경로 판정 -------------------------------------------------------------


@pytest.mark.parametrize("name", ["a.hwp", "a.HWP", "b.hwpx", "b.HwpX"])
def test_classify_accepts_hwp_regardless_of_case(name):
    verdict, payload = dropzone.classify_drop([f"C:/x/{name}"])
    assert verdict == dropzone.ACCEPT
    assert payload == f"C:/x/{name}"


def test_classify_keeps_spaces_in_the_path():
    """실기기에서 죽은 파일 이름에 띄어쓰기가 있었다 — 경로를 훼손하지 않는지 고정한다."""
    dropped = r"C:\Users\m\공문 최종 (수정).hwp"
    assert dropzone.classify_drop([dropped]) == (dropzone.ACCEPT, dropped)


def test_classify_rejects_multiple_files_with_the_same_wording_as_the_argv_branch():
    assert dropzone.classify_drop(["a.hwp", "b.hwp"]) == (dropzone.REJECT, messages.TOO_MANY_FILES)


def test_classify_rejects_unsupported_extension_with_the_existing_error_wording():
    verdict, payload = dropzone.classify_drop(["보고서.pdf"])
    assert verdict == dropzone.REJECT
    assert payload == UnsupportedFileError("보고서.pdf").user_message


def test_classify_rejects_empty_drop():
    assert dropzone.classify_drop([])[0] == dropzone.REJECT


# --- ★스레드 경계: 여기서는 view 를 만지면 안 된다 --------------------------


def test_offering_a_drop_never_touches_the_view():
    """`offer_paths` 는 **Win32 WndProc 콜백 안에서** 불린다. 거기서 Tk 를 만지면
    Tcl 이 메시지 처리 도중 재진입한다."""
    c = _controller(lambda p: "out.png", view=ExplodingView())
    c.offer_paths([r"C:\a b.hwp"])  # 터지면 여기서 실패한다
    assert c.state == dropzone.IDLE  # 아직 처리 안 됐다 — poll 이 해야 한다


def test_the_worker_never_touches_the_view():
    """변환은 워커 스레드에서 돈다. **여기서 Tk 를 만져서 실기기 앱이 죽었다.**"""
    c = dropzone.DropZoneController(
        view=ExplodingView(), convert=lambda p: "out.png", spawn=_sync_spawn
    )
    c._work(r"C:\a b.hwp")  # 워커가 하는 일 전부. 터지면 실패한다


def test_the_worker_never_touches_the_view_on_failure():
    def boom(_path):
        raise HwpTimeoutError("stuck")

    c = dropzone.DropZoneController(view=ExplodingView(), convert=boom, spawn=_sync_spawn)
    c._work(r"C:\a b.hwp")


def test_offering_a_notice_never_touches_the_view():
    c = _controller(lambda p: "out.png", view=ExplodingView())
    c.offer_notice(messages.DROP_FAILED)


# --- poll 이 실제로 반영한다 -------------------------------------------------


def test_polling_turns_an_offered_drop_into_a_conversion():
    view = FakeView()
    converted = []
    c = _controller(lambda p: (converted.append(p), "C:/x/a_변환.png")[1], view=view)

    c.offer_paths([r"C:\공문 최종.hwp"])
    assert converted == []  # 아직

    c.poll()
    assert converted == [r"C:\공문 최종.hwp"]
    c.poll()  # 결과 반영
    assert c.state == dropzone.IDLE
    assert "a_변환.png" in view.last


def test_polling_reports_a_failure_and_returns_to_idle():
    view = FakeView()

    def boom(_path):
        raise HwpTimeoutError("stuck")

    c = _controller(boom, view=view)
    c.handle_paths([r"C:\a.hwp"])
    assert c.state == dropzone.PROCESSING  # 아직 화면에 안 그려졌다

    c.poll()
    assert c.state == dropzone.IDLE
    assert view.last == HwpTimeoutError("stuck").user_message


def test_polling_uses_the_injected_describer_for_unexpected_errors():
    view = FakeView()

    def boom(_path):
        raise ValueError("nope")

    c = _controller(boom, view=view, describe_error=lambda exc: f"로그: {exc}")
    c.handle_paths([r"C:\a.hwp"])
    c.poll()
    assert view.last == "로그: nope"
    assert c.state == dropzone.IDLE


def test_a_notice_does_not_end_the_conversion():
    """드롭 실패 안내는 상태를 안 건드린다 — 변환 중이면 변환 중인 채로 둔다."""
    view = FakeView()
    pending = []
    c = _controller(lambda p: "out.png", view=view, spawn=pending.append)

    c.handle_paths([r"C:\a.hwp"])
    assert c.state == dropzone.PROCESSING
    c.offer_notice(messages.DROP_FAILED)
    c.poll()
    assert view.last == messages.DROP_FAILED
    assert c.state == dropzone.PROCESSING, "안내가 변환 상태를 끝내 버렸다"


def test_results_are_applied_before_new_drops_are_accepted():
    """순서를 바꾸면 방금 시작한 변환의 '바꾸는 중…' 을 직전 결과가 덮어쓴다."""
    view = FakeView()
    c = _controller(lambda p: "먼저.png", view=view)

    c.handle_paths([r"C:\first.hwp"])  # 결과가 outbox 에 쌓인다
    c.offer_paths([r"C:\second.hwp"])  # 새 드롭이 inbox 에 쌓인다
    c.poll()

    assert view.statuses[-1] == messages.CONVERTING, "결과가 새 변환 안내를 덮어썼다"


# --- 상태 전이 -------------------------------------------------------------


def test_drop_while_processing_is_rejected_and_does_not_start_a_second_conversion():
    view = FakeView()
    started = []
    pending = []
    c = _controller(lambda p: (started.append(p), "out.png")[1], view=view, spawn=pending.append)

    c.handle_paths([r"C:\a.hwp"])
    assert c.state == dropzone.PROCESSING

    c.handle_paths([r"C:\b.hwp"])
    assert view.last == messages.BUSY

    for job in pending:
        job()
    c.poll()
    assert started == [r"C:\a.hwp"]
    assert c.state == dropzone.IDLE


def test_reject_does_not_enter_processing():
    view = FakeView()
    c = _controller(lambda p: pytest.fail("변환이 시작되면 안 된다"), view=view)
    c.handle_paths(["보고서.pdf"])
    assert c.state == dropzone.IDLE


# --- 창이 닫힌 뒤 -----------------------------------------------------------


def test_nothing_is_written_to_a_window_that_was_closed():
    view = FakeView()
    c = _controller(lambda p: "out.png", view=view)
    c.handle_paths([r"C:\a.hwp"])
    view.close()
    before = len(view.statuses)

    c.poll()

    assert len(view.statuses) == before  # 죽은 창을 갱신하지 않았다
    assert c.state == dropzone.IDLE  # 상태는 되돌아온다


# --- 변환 중 창 닫기 --------------------------------------------------------


def test_closing_is_refused_while_a_conversion_is_running():
    view = FakeView()
    pending = []
    c = _controller(lambda p: "out.png", view=view, spawn=pending.append)

    c.handle_paths([r"C:\a.hwp"])
    assert c.can_close() is False
    assert view.last == messages.BUSY

    for job in pending:
        job()
    c.poll()
    assert c.can_close() is True


def test_closing_is_allowed_when_idle():
    assert _controller(lambda p: "out.png").can_close() is True
