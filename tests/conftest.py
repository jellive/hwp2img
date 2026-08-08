import pymupdf
import pytest


@pytest.fixture
def make_pdf(tmp_path):
    """factory fixture: make_pdf(page_count) -> 그 페이지 수만큼 빈 페이지가 있는 PDF 경로"""

    def _make(page_count: int, width: int = 200, height: int = 300) -> str:
        path = tmp_path / f"sample_{page_count}page.pdf"
        doc = pymupdf.open()
        for i in range(page_count):
            page = doc.new_page(width=width, height=height)
            page.insert_text((10, 10), f"page {i + 1}")
        doc.save(str(path))
        doc.close()
        return str(path)

    return _make
