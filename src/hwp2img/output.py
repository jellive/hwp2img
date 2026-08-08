import io
import os
import subprocess
from pathlib import Path

from PIL import Image


def save_result(image: Image.Image, source_hwp_path: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    stem = Path(source_hwp_path).stem
    out_path = os.path.join(output_dir, f"{stem}_변환.png")
    image.save(out_path, "PNG")
    return out_path


def copy_to_clipboard(image: Image.Image, clipboard_module=None) -> None:
    if clipboard_module is None:
        import win32clipboard

        clipboard_module = win32clipboard

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "BMP")
    data = buffer.getvalue()[14:]  # BMP 파일 헤더(14바이트)는 CF_DIB 에 포함되지 않는다
    buffer.close()

    clipboard_module.OpenClipboard()
    try:
        clipboard_module.EmptyClipboard()
        clipboard_module.SetClipboardData(clipboard_module.CF_DIB, data)
    finally:
        clipboard_module.CloseClipboard()


def open_in_explorer(path: str, runner=subprocess.run) -> None:
    runner(["explorer", f"/select,{path}"])
