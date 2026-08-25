import os
import tempfile
from pathlib import Path

from hwp2img import hwp_to_pdf, messages, output, pdf_to_images, shell_menu, stitch, watchdog
from hwp2img.errors import Hwp2ImgError, UnsupportedFileError

SUPPORTED_EXTENSIONS = {".hwp", ".hwpx"}


def process_file(hwp_path: str, output_dir: str, hwp_factory, dpi: int = 200) -> str:
    if Path(hwp_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(hwp_path)

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "converted.pdf")
        hwp = hwp_factory()
        hwp_to_pdf.convert(hwp, hwp_path, pdf_path)
        pages = pdf_to_images.render_pages(pdf_path, dpi=dpi)

    image = stitch.stitch_vertical(pages)
    out_path = output.save_result(image, hwp_path, output_dir)

    # 저장된 PNG 가 본체다. 클립보드는 다른 앱이 잡고 있으면 흔히 실패하고 탐색기도 마찬가지라,
    # 이 둘의 실패로 이미 성공한 변환 결과를 버리지 않는다.
    try:
        output.copy_to_clipboard(image)
    except Exception:
        # 조용히 넘어가면 어머니가 Ctrl+V 로 직전 클립보드 내용(사적인 캡처 등)을
        # 그대로 전송할 수 있다. 저장은 이미 됐으니 안내한다 — 단, 실제 경로를 직접
        # 적어야 한다. "열린 폴더에서"라고만 하면 바로 다음의 탐색기 오픈까지 실패했을 때
        # 어디서도 찾을 수 없는 안내가 된다(탐색기 성공 여부와 무관하게 유효해야 함).
        _show_notice(f"사진은 저장했어요.\n\n복사가 안 돼서 붙여넣기는 안 될 거예요.\n여기서 찾아 보내주세요:\n{out_path}")
    try:
        output.open_in_explorer(out_path)
    except Exception:
        pass
    return out_path


def main(argv: list[str], launcher=None) -> int:
    # 탐색기 우클릭 메뉴를 자가 등록·자가 치유한다. 설치 프로그램이 없어서 등록을 유지해 줄
    # 주체가 없고, 바탕화면 exe 는 이름변경·이동·새 버전으로 경로가 쉽게 바뀐다.
    #
    # `watchdog` 이 띄우는 자식은 여기 안 온다 — `run.py` 의 `freeze_support()` 가 자식을
    # worker 로 가로채므로 `main()` 은 부모에서만 돈다.
    #
    # 등록 실패는 변환을 막지 않는다. `ensure_registered` 는 예외를 안 던지지만, 그건 그
    # 함수의 약속이지 이 자리의 보장이 아니다 — 여기서도 막는다.
    try:
        shell_menu.ensure_registered()
    except Exception:
        pass

    if not argv:
        # 아이콘을 더블클릭한 경우다. 예전에는 "이 프로그램 위로 끌어다 놓아 주세요"
        # 안내창만 띄우고 끝나는 막다른 길이었다 — 이제 드롭존 창을 띄운다.
        # 아이콘 위 드롭(argv 있음)은 아래 경로 그대로이고, 창은 뜨지 않는다.
        return (launcher or _launch_dropzone)()

    # 여러 파일 동시 드래그(배치 처리)는 설계상 스코프 아웃이다(스펙 문서 "스코프 아웃" 절).
    # 예전에는 argv 를 그냥 순회하다 첫 파일 실패에서 조용히 멈췄는데, 어머니가 실수로
    # 여러 개를 집어 드롭하면 나머지가 안내도 없이 사라지는 셈이었다 — 아예 시작하지 않고
    # 안내한다. 문구는 드롭존 창과 공유한다(`messages.py`).
    if len(argv) > 1:
        _show_error(messages.TOO_MANY_FILES)
        return 1

    try:
        _convert_one(argv[0])
    except Hwp2ImgError as exc:
        _show_error(exc.user_message)
        return 1
    except Exception as exc:
        _show_error(_describe_unexpected(exc))
        return 1
    return 0


def _convert_one(hwp_path: str) -> str:
    """결과는 늘 원본 .hwp 가 있던 폴더에 만든다 — 두 진입점이 같이 쓴다."""
    return _run_conversion(hwp_path, os.path.dirname(os.path.abspath(hwp_path)))


def _describe_unexpected(exc: Exception) -> str:
    """예외 전문은 로그로만 보내고, 어머니에게는 로그 경로만 알린다."""
    return f"{messages.UNEXPECTED}\n\n자세한 내용은 이 파일에 저장했어요:\n{_log_error(exc)}"


def _launch_dropzone() -> int:
    """`dropzone` 은 여기서(함수 안에서) import 한다.

    `dropzone` 이 이 모듈을 최상위에서 import 하므로 여기서도 최상위로 하면 순환이 된다.
    그리고 argv 가 있는 경로 — 즉 지금까지 검증해 온 경로 — 는 tkinter 근처를 아예
    건드리지 않게 된다. `run.py` 가 import 순서를 조심하는 것과 같은 이유다.
    """
    from hwp2img import dropzone

    try:
        return dropzone.launch(convert=_convert_one, describe_error=_describe_unexpected)
    except Exception as exc:
        # 창을 띄우는 것 자체가 실패할 수 있다 — 얼린 exe 에 tcl/tk 가 안 들어갔거나,
        # tkinter import 가 깨졌거나. `--noconsole` 이라 이걸 안 잡으면 어머니는
        # **아무 메시지도 없이** 아이콘만 반짝이는 것을 본다.
        _show_error(_describe_unexpected(exc))
        return 1


def _run_conversion(hwp_path: str, output_dir: str) -> str:
    """실제 변환 경로 — watchdog 을 거쳐 별도 프로세스에서 실행한다.

    암호 걸린 문서 등으로 한글 COM 이 응답 없이 멈춰도, 이 프로세스(자식이 아니라
    지금 이 프로세스) 는 계속 살아 있어야 어머니에게 안내창을 띄울 수 있다.
    """
    return watchdog.run_process_file(hwp_path, output_dir, hwp_to_pdf.create_hwp)


def _log_error(exc: Exception) -> str:
    """예외 전문을 로그 파일에 적고 그 경로를 돌려준다.

    사용자에게 남는 마지막 안내 수단이라 이 함수는 절대 예외를 던지지 않는다 —
    바탕화면이 없을 수 있고(OneDrive 폴더 리디렉션) 그러면 --noconsole 빌드에서
    아무 메시지도 못 본 채 조용히 죽는다. 바탕화면 → 임시 폴더 순으로 시도한다.
    """
    import traceback
    from datetime import datetime

    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    entry = f"\n=== {datetime.now().isoformat()} ===\n{detail}"

    for base in (os.path.join(os.path.expanduser("~"), "Desktop"), tempfile.gettempdir()):
        log_path = os.path.join(base, "hwp2img_오류.log")
        try:
            os.makedirs(base, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
            return log_path
        except OSError:
            continue
    return "(로그 파일을 만들 수 없었어요)"


def _show_error(message: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, message, "한글 사진으로 바꾸기", 0x10)


def _show_notice(message: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, message, "한글 사진으로 바꾸기", 0x40)
