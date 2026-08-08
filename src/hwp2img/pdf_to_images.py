import pymupdf
from PIL import Image


def render_pages(pdf_path: str, dpi: int = 200) -> list[Image.Image]:
    doc = pymupdf.open(pdf_path)
    try:
        return [page.get_pixmap(dpi=dpi).pil_image() for page in doc]
    finally:
        doc.close()
