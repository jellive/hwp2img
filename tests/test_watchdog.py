import multiprocessing
import os
import time

import pymupdf
import pytest

from hwp2img import cli, watchdog
from hwp2img.errors import Hwp2ImgError, HwpAutomationError, HwpTimeoutError, UnsupportedFileError

# 프로덕션(Windows)은 spawn 만 가능하고 run_process_file() 의 기본값도 spawn 이다.
# 여기서는 fork 를 명시적으로 주입해 Mac 에서도 진짜 OS 프로세스로 격리/타임아웃/강제종료
# 메커니즘 자체를 검증한다 — spawn 고유의 이슈(PyInstaller freeze_support 등)는 이걸로
# 검증되지 않는다. 그건 Windows 실기기 체크리스트 항목이다.
FORK_CTX = multiprocessing.get_context("fork")


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


@pytest.fixture(autouse=True)
def _stub_windows_only_side_effects(monkeypatch):
    """clipboard/explorer 는 Windows 전용 실호출이라 Mac 에서 실행되는 자식 프로세스
    안에서는 항상 실패한다. fork 는 부모의 monkeypatch 상태를 그대로 물려받으므로
    여기서 한 번만 스텁하면 모든 테스트의 자식 프로세스에도 적용된다."""
    monkeypatch.setattr(cli.output, "copy_to_clipboard", lambda image: None)
    monkeypatch.setattr(cli.output, "open_in_explorer", lambda path: None)


def test_run_process_file_returns_out_path_on_success(tmp_path):
    hwp_path = tmp_path / "공문.hwp"
    hwp_path.write_text("dummy")
    output_dir = tmp_path / "out"

    out_path = watchdog.run_process_file(
        str(hwp_path),
        str(output_dir),
        lambda: FakeHwpWritesRealPdf(page_count=1),
        timeout=5,
        ctx=FORK_CTX,
    )

    assert out_path == str(output_dir / "공문_변환.png")
    assert (output_dir / "공문_변환.png").exists()


def test_run_process_file_raises_timeout_error_without_actually_waiting_for_the_hang(tmp_path):
    hwp_path = tmp_path / "암호걸림.hwp"
    hwp_path.write_text("dummy")

    start = time.monotonic()
    with pytest.raises(HwpTimeoutError):
        watchdog.run_process_file(
            str(hwp_path), str(tmp_path / "out"), HangingHwp, timeout=0.5, ctx=FORK_CTX
        )
    elapsed = time.monotonic() - start

    # HangingHwp 는 30초를 잔다 — timeout 근처에서 끝나야 watchdog 이 실제로 죽인 것이다.
    assert elapsed < 5





def test_run_process_file_propagates_hwp2img_error_with_its_user_message(tmp_path):
    txt_path = tmp_path / "메모.txt"
    txt_path.write_text("hwp 가 아닌 파일")

    with pytest.raises(UnsupportedFileError) as exc_info:
        watchdog.run_process_file(
            str(txt_path),
            str(tmp_path / "out"),
            lambda: FakeHwpWritesRealPdf(),
            timeout=5,
            ctx=FORK_CTX,
        )

    assert exc_info.value.user_message == "한글 문서 파일(.hwp, .hwpx)만 변환할 수 있어요."


def test_run_process_file_propagates_unexpected_errors_without_disguising_them(tmp_path):
    """예상 못한 예외를 조용히 HwpAutomationError 로 바꿔버리면 main() 의 로그 경로가
    아니라 '손상되지 않았는지 확인해 주세요' 안내로 가버려 실제 원인이 사라진다."""
    hwp_path = tmp_path / "공문.hwp"
    hwp_path.write_text("dummy")

    def boom():
        raise ValueError("전혀 예상 못한 내부 오류")

    with pytest.raises(RuntimeError) as exc_info:
        watchdog.run_process_file(
            str(hwp_path), str(tmp_path / "out"), boom, timeout=5, ctx=FORK_CTX
        )

    assert not isinstance(exc_info.value, Hwp2ImgError)
    assert "전혀 예상 못한 내부 오류" in str(exc_info.value)


def test_drain_until_terminal_picks_up_a_result_that_had_not_flushed_yet():
    """`multiprocessing.Queue.put()` 은 백그라운드 스레드가 파이프에 쓴다 — 자식이 죽은
    것으로 보이는 시점에도 결과가 아직 안 올라왔을 수 있어서, 한 번 더 읽어야 성공한
    변환을 실패로 오판하지 않는다."""
    queue = FORK_CTX.Queue()
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
            str(tmp_path / "공문.hwp"), str(tmp_path / "out"), CrashingHwp, timeout=5, ctx=FORK_CTX
        )
