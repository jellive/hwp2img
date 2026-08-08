import pymupdf
import pytest
from PIL import Image

from hwp2img import cli
from hwp2img.errors import UnsupportedFileError


class FakeHwpWritesRealPdf:
    """save_as 호출 시 실제로 읽을 수 있는 PDF 를 만들어 이후 파이프라인(렌더링)이
    진짜로 동작하는지까지 확인할 수 있게 한다."""

    def __init__(self, page_count=1):
        self.page_count = page_count
        self.calls = []

    def open(self, filename):
        self.calls.append(("open", filename))
        return True

    def save_as(self, path, format="HWP"):
        doc = pymupdf.open()
        for i in range(self.page_count):
            page = doc.new_page(width=200, height=300)
            page.insert_text((10, 10), f"page {i + 1}")
        doc.save(path)
        doc.close()
        self.calls.append(("save_as", path, format))
        return True

    def quit(self, save=False):
        self.calls.append(("quit", save))


def test_process_file_rejects_unsupported_extension(tmp_path):
    def factory():
        raise AssertionError("hwp_factory should not be called for unsupported files")

    with pytest.raises(UnsupportedFileError):
        cli.process_file(str(tmp_path / "notes.txt"), str(tmp_path / "out"), factory)


def test_process_file_produces_stitched_png(tmp_path, monkeypatch):
    clipboard_calls = []
    explorer_calls = []
    monkeypatch.setattr(cli.output, "copy_to_clipboard", lambda image: clipboard_calls.append(image))
    monkeypatch.setattr(cli.output, "open_in_explorer", lambda path: explorer_calls.append(path))

    hwp_path = tmp_path / "공문.hwp"
    hwp_path.write_text("dummy")  # 내용은 FakeHwp 가 무시하므로 존재만 하면 됨
    output_dir = tmp_path / "out"

    out_path = cli.process_file(
        str(hwp_path), str(output_dir), lambda: FakeHwpWritesRealPdf(page_count=2)
    )

    assert out_path == str(output_dir / "공문_변환.png")
    assert (output_dir / "공문_변환.png").exists()
    assert len(clipboard_calls) == 1
    assert explorer_calls == [out_path]


def test_main_shows_error_and_returns_1_when_no_files(monkeypatch):
    messages = []
    monkeypatch.setattr(cli, "_show_error", lambda msg: messages.append(msg))

    result = cli.main([])

    assert result == 1
    assert messages


def test_main_shows_user_message_on_hwp2img_error(monkeypatch):
    messages = []
    monkeypatch.setattr(cli, "_show_error", lambda msg: messages.append(msg))

    def failing_process_file(*args, **kwargs):
        raise UnsupportedFileError("bad.txt")

    monkeypatch.setattr(cli, "process_file", failing_process_file)

    result = cli.main(["bad.txt"])

    assert result == 1
    assert messages == ["한글 문서 파일(.hwp, .hwpx)만 변환할 수 있어요."]
