import multiprocessing
import os
import time

import pymupdf
import pytest

from hwp2img import cli, watchdog
from hwp2img.errors import Hwp2ImgError, HwpAutomationError, HwpTimeoutError, UnsupportedFileError

# ★프로덕션이 실제로 쓰는 **spawn** 으로 잰다.
#
# 예전에는 여기서 `fork` 를 주입했다. Mac 에서 빠르고, 자식이 부모의 monkeypatch 를
# 그대로 물려받아 편해서였다. 그런데 CI 를 붙이자마자 양쪽에서 깨졌다(2026-08-24 실측):
#   · Windows — `fork` 컨텍스트가 **없다.** `ValueError: cannot find context for 'fork'`
#     로 이 파일이 **수집조차 안 됐다.** 하필 watchdog 이 Windows 전용 로직인데
#     그 테스트가 Windows 에서 한 번도 안 돌고 있었다.
#   · macOS 러너 — pymupdf/PIL 이 올라온 프로세스에서 `fork` 하니 `Abort trap: 6`.
#
# 즉 이 테스트는 **앱이 절대 쓰지 않는 경로**를 재고 있었다. spawn 으로 바꾸면
# 두 플랫폼에서 다 돌고, 무엇보다 배포되는 것과 같은 메커니즘을 잰다.
# (spawn 고유의 PyInstaller freeze_support 이슈는 여전히 실기기 항목이다.)
SPAWN_CTX = multiprocessing.get_context("spawn")


class FakeHwpWritesRealPdf:
    """save_as 호출 시 실제로 읽을 수 있는 PDF 를 만들어 이후 파이프라인이 진짜로
    동작하는지까지 확인할 수 있게 한다. test_cli.py 의 동명 Fake 와 동일한 계약."""

    def __init__(self, page_count=1):
        self.page_count = page_count

    def open(self, filename):
        return True

    def save_as(self, path, format="HWP"):
        doc = pymupdf.open()
        for i in range(self.page_count):
            page = doc.new_page(width=200, height=300)
            page.insert_text((10, 10), f"page {i + 1}")
        doc.save(path)
        doc.close()
        return True

    def quit(self, save=False):
        pass


class HangingHwp:
    """암호 걸린 hwp 를 열 때 COM 이 안 보이는 모달에서 응답 없이 멈추는 상황을 흉내낸다."""

    def open(self, filename):
        time.sleep(30)
        return True

    def save_as(self, path, format="HWP"):
        return True

    def quit(self, save=False):
        pass


class CrashingHwp:
    """자식 프로세스가 결과를 큐에 보내기도 전에 통째로 죽는(진짜 크래시) 상황을 흉내낸다."""

    def open(self, filename):
        os._exit(1)


def _stub_windows_only_side_effects_in_child() -> None:
    """**자식 프로세스 안에서** clipboard/explorer 를 스텁한다.

    spawn 자식은 부모를 새로 import 하므로 부모의 monkeypatch 를 물려받지 않는다
    (fork 였을 때는 물려받아서 부모에서 한 번만 하면 됐다). 이 둘은 Windows 실호출이라
    Mac·CI 러너에서 반드시 실패하고, 그 실패 안내 경로인 `cli._show_notice` 는
    `ctypes.windll` 이라 비-Windows 에서 **또** 터진다 — 자식이 통째로 죽는다.
    """
    cli.output.copy_to_clipboard = lambda image: None
    cli.output.open_in_explorer = lambda path: None


class RecordingCtx:
    """생성된 자식 프로세스를 붙들어 둔다 — **정말 죽였는지** 보기 위해서다.

    이게 없으면 `watchdog._kill()` 을 통째로 지워도 타임아웃 테스트가 그대로 통과한다
    (변이 검사로 확인). `HwpTimeoutError` 는 그래도 나고 시간도 그대로라서다. 그러면
    멈춘 한글을 붙든 자식이 백그라운드에 남는데 — 그걸 죽이는 것이 이 모듈의 존재 이유다.
    """

    def __init__(self, inner):
        self._inner = inner
        self.processes = []

    def Queue(self, *args, **kwargs):
        return self._inner.Queue(*args, **kwargs)

    def Process(self, *args, **kwargs):
        process = self._inner.Process(*args, **kwargs)
        self.processes.append(process)
        return process


# spawn 은 팩토리를 pickle 로 넘긴다 — 람다·지역함수는 못 넘긴다. 모듈 최상위여야 한다.
def make_working_hwp():
    _stub_windows_only_side_effects_in_child()
    return FakeHwpWritesRealPdf(page_count=1)


def make_hanging_hwp():
    return HangingHwp()


def make_crashing_hwp():
    return CrashingHwp()


def raise_unexpected_error():
    raise ValueError("전혀 예상 못한 내부 오류")


def test_run_process_file_returns_out_path_on_success(tmp_path):
    hwp_path = tmp_path / "공문.hwp"
    hwp_path.write_text("dummy")
    output_dir = tmp_path / "out"

    out_path = watchdog.run_process_file(
        str(hwp_path),
        str(output_dir),
        make_working_hwp,
        timeout=5,
        ctx=SPAWN_CTX,
    )

    assert out_path == str(output_dir / "공문_변환.png")
    assert (output_dir / "공문_변환.png").exists()


def test_run_process_file_raises_timeout_error_without_actually_waiting_for_the_hang(tmp_path):
    hwp_path = tmp_path / "암호걸림.hwp"
    hwp_path.write_text("dummy")

    ctx = RecordingCtx(SPAWN_CTX)
    start = time.monotonic()
    with pytest.raises(HwpTimeoutError):
        watchdog.run_process_file(
            str(hwp_path), str(tmp_path / "out"), make_hanging_hwp, timeout=0.5, ctx=ctx
        )
    elapsed = time.monotonic() - start

    # HangingHwp 는 30초를 잔다 — timeout 근처에서 끝나야 watchdog 이 실제로 죽인 것이다.
    assert elapsed < 5

    # ★그리고 자식이 **정말로** 죽어 있어야 한다. 예외가 났다는 것만으로는 증거가 아니다 —
    #   멈춘 한글을 붙든 자식이 백그라운드에 남으면 고치려던 증상이 그대로다.
    assert ctx.processes, "자식 프로세스가 만들어지지 않았다"
    assert not ctx.processes[0].is_alive(), "타임아웃인데 자식이 살아 있다 — 안 죽였다"





def test_run_process_file_propagates_hwp2img_error_with_its_user_message(tmp_path):
    txt_path = tmp_path / "메모.txt"
    txt_path.write_text("hwp 가 아닌 파일")

    with pytest.raises(UnsupportedFileError) as exc_info:
        watchdog.run_process_file(
            str(txt_path),
            str(tmp_path / "out"),
            make_working_hwp,
            timeout=5,
            ctx=SPAWN_CTX,
        )

    assert exc_info.value.user_message == "한글 문서 파일(.hwp, .hwpx)만 변환할 수 있어요."


def test_run_process_file_propagates_unexpected_errors_without_disguising_them(tmp_path):
    """예상 못한 예외를 조용히 HwpAutomationError 로 바꿔버리면 main() 의 로그 경로가
    아니라 '손상되지 않았는지 확인해 주세요' 안내로 가버려 실제 원인이 사라진다."""
    hwp_path = tmp_path / "공문.hwp"
    hwp_path.write_text("dummy")

    with pytest.raises(RuntimeError) as exc_info:
        watchdog.run_process_file(
            str(hwp_path), str(tmp_path / "out"), raise_unexpected_error, timeout=5, ctx=SPAWN_CTX
        )

    assert not isinstance(exc_info.value, Hwp2ImgError)
    assert "전혀 예상 못한 내부 오류" in str(exc_info.value)


def test_drain_until_terminal_picks_up_a_result_that_had_not_flushed_yet():
    """`multiprocessing.Queue.put()` 은 백그라운드 스레드가 파이프에 쓴다 — 자식이 죽은
    것으로 보이는 시점에도 결과가 아직 안 올라왔을 수 있어서, 한 번 더 읽어야 성공한
    변환을 실패로 오판하지 않는다."""
    queue = SPAWN_CTX.Queue()
    queue.put(("ok", "/some/path.png"))
    time.sleep(0.1)

    assert watchdog._drain_until_terminal(queue, per_message_timeout=1.0) == (
        "ok",
        "/some/path.png",
    )


def test_drain_until_terminal_treats_a_broken_pipe_as_no_result():
    """크로스모델 리뷰 지적: Windows spawn 에서 자식을 강제 종료하면 파이프가 끊겨
    EOFError/BrokenPipeError 가 난다. 이게 새어나가면 사용자에게 안내창을 띄우는 경로
    자체가 막히므로 '결과 없음'(None)으로 삼켜야 한다."""

    class BrokenQueue:
        def get(self, timeout=None):
            raise EOFError("pipe closed")

    assert watchdog._drain_until_terminal(BrokenQueue(), per_message_timeout=0.1) is None


def test_run_process_file_raises_automation_error_when_child_exits_without_a_result(tmp_path):
    with pytest.raises(HwpAutomationError):
        watchdog.run_process_file(
            str(tmp_path / "공문.hwp"), str(tmp_path / "out"), make_crashing_hwp, timeout=5, ctx=SPAWN_CTX
        )
