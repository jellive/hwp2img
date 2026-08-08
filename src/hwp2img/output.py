import os
from pathlib import Path

from PIL import Image


def save_result(image: Image.Image, source_hwp_path: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    stem = Path(source_hwp_path).stem
    out_path = os.path.join(output_dir, f"{stem}_변환.png")
    image.save(out_path, "PNG")
    return out_path
