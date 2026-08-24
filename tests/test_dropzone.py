"""드롭존 창의 **판정과 상태 전이**를 Tk 없이 검증한다.

실제 Tk 창은 이 Mac 에서 띄울 수 없다 — `_tkinter` 가 없다(3.11·3.14 둘 다 실측).
그래서 `DropZoneController` 는 view 를 주입받고, 여기서는 가짜 view 를 넣는다.
이 레포가 Windows 전용 함수(`output.copy_to_clipboard` 등)에 이미 쓰는 방식과 같다.
"""

import pytest

from hwp2img import dropzone, messages
from hwp2img.errors import HwpTimeoutError, UnsupportedFileError


class FakeView:
    """schedule() 을 즉시 실행하는 가짜 메인 스레드."""

    def __init__(self, alive=True):
        self.statuses = []
        self._alive = alive
        self.scheduled = 0

    def set_status(self, text):
        self.statuses.append(text)

    def is_alive(self):
        return self._alive

    def schedule(self, fn):
        self.scheduled += 1
        fn()

    def close(self):
        self._alive = False

    @property
    def last(self):
        return self.statuses[-1] if self.statuses else None


def _sync_spawn(fn):
    """워커 스레드 대신 그 자리에서 실행한다."""
    fn()


def _controller(convert, view=None, spawn=_sync_spawn, describe_error=None):
    return dropzone.DropZoneController(
        view=view or FakeView(),
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


def test_classify_rejects_multiple_files_with_the_same_wording_as_the_argv_branch():
    verdict, payload = dropzone.classify_drop(["a.hwp", "b.hwp"])
    assert verdict == dropzone.REJECT
    assert payload == messages.TOO_MANY_FILES


def test_classify_rejects_unsupported_extension_with_the_existing_error_wording():
    verdict, payload = dropzone.classify_drop(["보고서.pdf"])
    assert verdict == dropzone.REJECT
    assert payload == UnsupportedFileError("보고서.pdf").user_message


def test_classify_rejects_empty_drop():
    verdict, _ = dropzone.classify_drop([])
    assert verdict == dropzone.REJECT


# --- 상태 전이 -------------------------------------------------------------


def test_successful_conversion_returns_to_idle():
    view = FakeView()
    c = _controller(lambda p: "C:/x/a_변환.png", view=view)

    c.handle_paths(["C:/x/a.hwp"])

    assert c.state == dropzone.IDLE
    assert messages.CONVERTING in view.statuses
    assert "a_변환.png" in view.last


def test_conversion_failure_also_returns_to_idle_so_the_next_drop_still_works():
    """레드팀 지적: '변환 중…' 에 갇히면 이후 드롭이 영구히 막힌다."""
    view = FakeView()

    def boom(_path):
        raise HwpTimeoutError("stuck")

    c = _controller(boom, view=view)
    c.handle_paths(["C:/x/a.hwp"])

    assert c.state == dropzone.IDLE
    assert view.last == HwpTimeoutError("stuck").user_message

    # 그리고 실제로 다음 드롭이 받아들여진다
    calls = []
    c._convert = lambda p: (calls.append(p), "out.png")[1]
    c.handle_paths(["C:/x/b.hwp"])
    assert calls == ["C:/x/b.hwp"]


def test_unexpected_exception_uses_the_injected_describer():
    view = FakeView()

    def boom(_path):
        raise ValueError("nope")

    c = _controller(boom, view=view, describe_error=lambda exc: f"로그: {exc}")
    c.handle_paths(["C:/x/a.hwp"])

    assert c.state == dropzone.IDLE
    assert view.last == "로그: nope"


def test_drop_while_processing_is_rejected_and_does_not_start_a_second_conversion():
    view = FakeView()
    started = []

    def convert(path):
        started.append(path)
        return "out.png"

    # 첫 변환이 아직 안 끝난 상태를 만든다 — spawn 이 즉시 실행하지 않는다.
    pending = []
    c = _controller(convert, view=view, spawn=pending.append)

    c.handle_paths(["C:/x/a.hwp"])
    assert c.state == dropzone.PROCESSING

    c.handle_paths(["C:/x/b.hwp"])
    assert view.last == messages.BUSY

    for job in pending:
        job()
    assert started == ["C:/x/a.hwp"]
    assert c.state == dropzone.IDLE


def test_reject_does_not_enter_processing():
    view = FakeView()
    c = _controller(lambda p: pytest.fail("변환이 시작되면 안 된다"), view=view)

    c.handle_paths(["보고서.pdf"])

    assert c.state == dropzone.IDLE


# --- 창이 닫히는 경쟁 (레드팀 지적 #6) --------------------------------------


def test_result_is_not_written_to_a_window_that_was_already_closed():
    view = FakeView()
    pending = []
    c = _controller(lambda p: "out.png", view=view, spawn=pending.append)

    c.handle_paths(["C:/x/a.hwp"])
    view.close()  # 변환이 도는 동안 어머니가 창을 닫았다
    before = len(view.statuses)
    view.scheduled = 0
    for job in pending:
        job()

    assert len(view.statuses) == before  # 죽은 창을 갱신하지 않았다
    # 죽은 메인 루프에 일감을 **넣지도** 않는다. 이걸 안 보면 _apply 쪽 가드 하나가
    # 두 가드를 다 덮어 버려서 이 테스트가 무뎌진다(변이 검사에서 실제로 그랬다).
    assert view.scheduled == 0
    assert c.state == dropzone.IDLE


def test_result_is_not_written_when_the_window_dies_between_the_two_guards():
    """is_alive 검사와 실제 갱신 사이에 창이 닫히는 경쟁 — _apply 쪽 가드를 고정한다."""

    class DiesOnSchedule(FakeView):
        def schedule(self, fn):
            self.scheduled += 1
            self._alive = False  # after() 로 넘긴 직후 창이 닫혔다
            fn()

    view = DiesOnSchedule()
    c = _controller(lambda p: "out.png", view=view)
    c.handle_paths(["C:/x/a.hwp"])

    assert view.scheduled == 1
    assert view.statuses == [messages.CONVERTING]  # 결과는 안 쓰였다
    assert c.state == dropzone.IDLE


def test_worker_never_raises_into_the_thread_even_if_the_view_blows_up():
    """워커 스레드에서 새어나간 예외는 아무도 못 본다 — 안에서 삼킨다."""

    class ExplodingView(FakeView):
        def schedule(self, fn):
            raise RuntimeError("main loop is gone")

    c = _controller(lambda p: "out.png", view=ExplodingView())
    c.handle_paths(["C:/x/a.hwp"])  # 예외가 나가면 이 줄에서 실패한다
    assert c.state == dropzone.IDLE


# --- 워커 ↔ 메인 스레드 경계 (cursor diff 리뷰 지적) ------------------------


class DeferredView(FakeView):
    """`root.after(0, …)` 처럼 **나중에** 실행되는 스케줄러."""

    def __init__(self):
        super().__init__()
        self.queue = []

    def schedule(self, fn):
        self.scheduled += 1
        self.queue.append(fn)

    def flush(self):
        jobs, self.queue = self.queue, []
        for job in jobs:
            job()


def test_stays_processing_until_the_main_thread_actually_applies_the_result():
    """워커가 `_state=IDLE` 을 먼저 찍으면, 결과가 화면에 그려지기 전에 다음 드롭이
    받아들여진다. 그러면 늦게 도착한 이전 결과가 새 변환의 '바꾸는 중…' 을 덮어써서
    어머니가 **아직 변환 중인데 '다 됐어요' 를 보게 된다.**"""
    view = DeferredView()
    c = _controller(lambda p: "out.png", view=view)

    c.handle_paths(["C:/x/a.hwp"])  # 워커는 즉시 돌고 _finish 까지 갔다
    assert view.scheduled == 1
    assert c.state == dropzone.PROCESSING  # 아직 화면에 안 그려졌다

    c.handle_paths(["C:/x/b.hwp"])  # 이 틈에 들어온 드롭
    assert view.last == messages.BUSY

    view.flush()
    assert c.state == dropzone.IDLE
    assert "out.png" in view.last


def test_state_returns_to_idle_even_when_the_window_died_before_scheduling():
    view = FakeView()
    pending = []
    c = _controller(lambda p: "out.png", view=view, spawn=pending.append)
    c.handle_paths(["C:/x/a.hwp"])
    view.close()
    for job in pending:
        job()
    assert c.state == dropzone.IDLE  # 안 그러면 창이 살아나도 영구히 막힌다


def test_state_returns_to_idle_when_scheduling_itself_blows_up():
    class ExplodingView(FakeView):
        def schedule(self, fn):
            raise RuntimeError("main loop is gone")

    c = _controller(lambda p: "out.png", view=ExplodingView())
    c.handle_paths(["C:/x/a.hwp"])
    assert c.state == dropzone.IDLE


# --- 변환 중 창 닫기 --------------------------------------------------------


def test_closing_is_refused_while_a_conversion_is_running():
    """변환 중에 창을 닫으면 워커 스레드(daemon)와 watchdog 자식 프로세스가 어중간하게
    남는다. `--noconsole` 이라 어머니 눈에는 아무것도 안 보인다. watchdog 이 30초 안에
    무조건 끝내므로, 그동안 닫기를 막는 편이 안전하다."""
    view = DeferredView()
    c = _controller(lambda p: "out.png", view=view)

    c.handle_paths(["C:/x/a.hwp"])
    assert c.can_close() is False
    assert view.last == messages.BUSY

    view.flush()
    assert c.can_close() is True


def test_closing_is_allowed_when_idle():
    c = _controller(lambda p: "out.png")
    assert c.can_close() is True
