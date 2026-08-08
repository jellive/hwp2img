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
    output.copy_to_clipboard(image)
    output.open_in_explorer(out_path)
    return out_path


def main(argv: list[str]) -> int:
    if not argv:
        _show_error("변환할 한글 문서 파일을 이 프로그램 위로 끌어다 놓아 주세요.")
        return 1

    output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "변환된사진")
    for hwp_path in argv:
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
    import traceback

    log_path = os.path.join(os.path.expanduser("~"), "Desktop", "hwp2img_오류.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")
    return log_path


def _show_error(message: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, message, "한글 사진으로 바꾸기", 0x10)
