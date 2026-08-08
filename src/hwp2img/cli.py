import os
import tempfile
from pathlib import Path

from hwp2img import hwp_to_pdf, output, pdf_to_images, stitch
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


def main(argv: list[str]) -> int:
    if not argv:
        _show_error("변환할 한글 문서 파일을 이 프로그램 위로 끌어다 놓아 주세요.")
        return 1

    for hwp_path in argv:
        output_dir = os.path.dirname(os.path.abspath(hwp_path))
        try:
            process_file(hwp_path, output_dir, hwp_to_pdf.create_hwp)
        except Hwp2ImgError as exc:
            _show_error(exc.user_message)
            return 1
        except Exception as exc:
            log_path = _log_error(exc)
            _show_error(f"예상하지 못한 문제가 생겼어요.\n\n자세한 내용은 이 파일에 저장했어요:\n{log_path}")
            return 1
    return 0


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
