"""COM 자동화가 멈췄을 때를 대비한 프로세스 격리 + 타임아웃 감시.

암호 걸린 hwp 나 문서 복구 프롬프트가 뜨는 hwp 를 열면, 한글 COM 이 (`visible=False`라
안 보이는) 모달을 띄운 채 응답 없이 멈출 수 있다. COM 은 STA apartment 규칙을 따르므로
이 대기는 같은 프로세스 안의 스레드 타임아웃으로는 취소할 수 없다 — 그래서 변환 전체를
별도 프로세스에서 돌리고, 여기서 정해진 시간 안에 안 끝나면 그 프로세스와 프로세스가
새로 띄운 한글 COM 서버(Hwp.exe)만 강제 종료한다.

★**Hwp.exe 는 죽이지 않는다. 우리가 만든 파이썬 자식 프로세스만 죽인다.** (Jell 결정 2026-08-18)

이 프로그램의 제1 제약은 "어머니가 열어둔 한글 문서를 절대 죽이지 않는다" 이다.
처음 구현은 자식을 띄우기 직전/직후의 Hwp.exe PID 스냅샷을 비교해 "새로 생긴 것" 만
죽였는데, 크로스모델 리뷰(codex)가 **그 차집합은 소유권 증명이 아니라는 것**을 지적했다:

- 변환 중에 어머니가 한글을 직접 실행하면 그 PID 가 "새로 생긴 것" 에 들어온다
- 변환기를 실수로 두 번 띄우면 서로의 한글을 새 PID 로 기록한다
- Windows 는 종료된 프로세스의 PID 를 재사용하므로, 기록해 둔 PID 를 나중에 죽이면
  그 사이 그 번호를 물려받은 무관한 프로세스를 죽인다

소유권을 진짜로 증명하려면 COM 객체의 윈도우 핸들에서 `GetWindowThreadProcessId` 로
PID 를 얻고 `OpenProcess` 핸들을 쥔 채 그 핸들로 종료해야 하는데, 전부 Windows 전용
API 라 **개발 환경(macOS)에서는 작성도 검증도 할 수 없다.** 검증 못 하는 코드가 어머니
문서를 저장 없이 날릴 수 있는 자리라, 그 경로를 통째로 뺐다.

결과: 타임아웃 시 자식 파이썬 프로세스만 종료한다. 그 자식이 띄운 한글은 백그라운드에
남을 수 있다(메모리를 먹지만 재부팅으로 정리되고, 무엇보다 **어머니 문서는 안전하다**).
원래 고치려던 증상 — "암호 걸린 hwp 를 드롭하면 앱이 영원히 멈추고 아무 메시지도 없다" —
는 자식만 죽여도 해결된다. 소유권이 확실한 것만 죽인다.

Windows 실기기에서 고아 Hwp.exe 가 실제로 문제가 되면, 그때 위 핸들 기반 방식을
Windows 에서 작성하고 검증해서 다시 넣는다.
"""

import multiprocessing
import time
import traceback
from queue import Empty as _QueueEmpty

from hwp2img.errors import (
    Hwp2ImgError,
    HwpAutomationError,
    HwpNotInstalledError,
    HwpTimeoutError,
    UnsupportedFileError,
)

# 실측 변환은 4~6초(Task 9 러너북). 큰 문서 여유분을 감안해 30초로 잡았다 —
# Windows 실기기에서 대용량 문서 기준으로 재확인할 것.
DEFAULT_TIMEOUT_SECONDS = 30

_POLL_INTERVAL_SECONDS = 0.2

_ERROR_TYPES = {
    "UnsupportedFileError": UnsupportedFileError,
    "HwpNotInstalledError": HwpNotInstalledError,
    "HwpAutomationError": HwpAutomationError,
    "HwpTimeoutError": HwpTimeoutError,
}


def run_process_file(
    hwp_path: str,
    output_dir: str,
    hwp_factory,
    dpi: int = 200,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ctx=None,
) -> str:
    """`cli.process_file` 을 별도 프로세스에서 돌리고 시간 안에 끝나는지 감시한다.

    성공하면 결과 이미지 경로를 그대로 돌려준다. 변환 실패는 원래 예외 타입을 그대로
    다시 던진다(사용자 안내 문구 보존). 타임아웃이면 **자식 프로세스만** 강제 종료한 뒤
    `HwpTimeoutError` 를 던진다 — 한글(Hwp.exe)은 건드리지 않는다(모듈 docstring 참고).
    """
    ctx = ctx or multiprocessing.get_context("spawn")

    queue = ctx.Queue()
    process = ctx.Process(
        target=_child_main,
        args=(hwp_path, output_dir, hwp_factory, dpi, queue),
    )
    process.start()

    deadline = time.monotonic() + timeout
    result = None

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            message = queue.get(timeout=min(remaining, _POLL_INTERVAL_SECONDS))
        except _QueueEmpty:
            if not process.is_alive():
                break
            continue
        except (EOFError, BrokenPipeError, OSError):
            # Windows spawn 에서 자식을 강제 종료하면 named pipe 가 끊겨 여기서
            # EOFError/BrokenPipeError 가 난다(크로스모델 리뷰 지적). 이걸 안 잡으면
            # 무한 대기를 막으려던 부모가 도리어 예외로 죽어 사용자에게 아무 안내도
            # 못 준다. 파이프가 끊긴 건 "결과 없음" 으로 취급하고 아래 정리 경로로 간다.
            break
        result = message
        break

    if result is None:
        # multiprocessing.Queue.put() 은 백그라운드 스레드로 flush 되므로, 프로세스가
        # 이미 죽은 것으로 보여도(타임아웃이든 크래시든) 결과 메시지가 아직 파이프에
        # 안 올라왔을 수 있다.
        result = _drain_until_terminal(queue, per_message_timeout=1.0)

    if result is None:
        was_alive = process.is_alive()
        _kill(process)
        if was_alive:
            raise HwpTimeoutError(f"conversion timed out after {timeout}s for {hwp_path}")
        raise HwpAutomationError(
            f"child process exited without a result (exitcode={process.exitcode}) for {hwp_path}"
        )

    process.join(timeout=5)
    if process.is_alive():
        _kill(process)

    if result[0] == "ok":
        return result[1]

    _, type_name, user_message, detail = result
    exc_cls = _ERROR_TYPES.get(type_name)
    if exc_cls is not None:
        exc = exc_cls(detail or "")
        if user_message:
            exc.user_message = user_message
        raise exc
    # 알려진 Hwp2ImgError 유형이 아니다 — 친절한 안내로 덮어써서 진짜 원인을 감추지 않고,
    # main() 의 일반 예외 경로(트레이스백 로그 + 로그 경로 안내)로 그대로 흘려보낸다.
    raise RuntimeError(detail or "unexpected error in isolated conversion")


def _drain_until_terminal(queue, per_message_timeout: float):
    """큐에 아직 flush 되지 않은 최종 메시지(ok/error)가 있으면 읽어 온다."""
    try:
        return queue.get(timeout=per_message_timeout)
    except (_QueueEmpty, EOFError, BrokenPipeError, OSError):
        # 파이프가 끊긴 경우도 "결과 없음" 이다 — 위 루프와 같은 이유로 여기서 예외가
        # 새어나가면 안내창을 띄우는 경로 자체가 막힌다.
        return None


def _kill(process) -> None:
    """자식 프로세스를 강제 종료한다.

    한글(Hwp.exe)은 여기서 죽이지 않는다 — 소유권을 증명할 수 없어서다(모듈 docstring).
    예외는 절대 새어나가게 하지 않는다: 여기서 죽으면 호출부가 사용자에게 안내창을
    띄우기 전에 터진다.
    """
    try:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
    except Exception:
        pass


def _child_main(hwp_path, output_dir, hwp_factory, dpi, queue) -> None:
    """별도 프로세스에서 실행된다 — spawn 방식에서 pickle 로 넘기려면 반드시 모듈
    최상위 함수여야 한다.

    `hwp2img.cli` 를 여기서(함수 안에서) import 하는 건 게으름이 아니라 순환 임포트를
    피하기 위해서다 — `cli.py` 가 `_run_conversion()` 에서 이 모듈을 import 하므로,
    이 모듈이 최상위에서 `cli` 를 import 하면 서로를 부르는 순환이 생긴다.
    """
    from hwp2img.cli import process_file

    try:
        out_path = process_file(hwp_path, output_dir, hwp_factory, dpi)
        queue.put(("ok", out_path))
    except Hwp2ImgError as exc:
        queue.put(("error", type(exc).__name__, exc.user_message, str(exc)))
    except Exception:
        queue.put(("error", "Exception", None, traceback.format_exc()))
