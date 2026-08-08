import pytest
from PIL import Image

from hwp2img.output import save_result, copy_to_clipboard, open_in_explorer


def test_save_result_writes_png_named_after_source(tmp_path):
    image = Image.new("RGB", (10, 10), color="white")
    output_dir = tmp_path / "변환된사진"

    out_path = save_result(image, "/원본/공문_2026.hwp", str(output_dir))

    assert out_path == str(output_dir / "공문_2026_변환.png")
    assert (output_dir / "공문_2026_변환.png").exists()


def test_save_result_creates_output_dir_if_missing(tmp_path):
    image = Image.new("RGB", (10, 10), color="white")
    output_dir = tmp_path / "does" / "not" / "exist"

    save_result(image, "doc.hwp", str(output_dir))

    assert output_dir.is_dir()


class FakeClipboard:
    CF_DIB = 8

    def __init__(self, raise_on_set=False):
        self.calls = []
        self._raise_on_set = raise_on_set

    def OpenClipboard(self):
        self.calls.append("open")

    def EmptyClipboard(self):
        self.calls.append("empty")

    def SetClipboardData(self, fmt, data):
        self.calls.append(("set", fmt, data))
        if self._raise_on_set:
            raise RuntimeError("boom")

    def CloseClipboard(self):
        self.calls.append("close")


def test_copy_to_clipboard_strips_bmp_header_and_uses_cf_dib():
    image = Image.new("RGB", (10, 10), color="blue")
    fake = FakeClipboard()

    copy_to_clipboard(image, clipboard_module=fake)

    assert fake.calls[0] == "open"
    assert fake.calls[1] == "empty"
    set_call = fake.calls[2]
    assert set_call[0] == "set"
    assert set_call[1] == FakeClipboard.CF_DIB
    assert not set_call[2].startswith(b"BM")  # BMP 파일 헤더(14바이트)가 제거됐어야 함
    assert fake.calls[3] == "close"


def test_copy_to_clipboard_closes_even_if_set_fails():
    image = Image.new("RGB", (10, 10), color="blue")
    fake = FakeClipboard(raise_on_set=True)

    with pytest.raises(RuntimeError):
        copy_to_clipboard(image, clipboard_module=fake)

    assert fake.calls[-1] == "close"


def test_open_in_explorer_selects_the_file():
    calls = []

    open_in_explorer(
        "C:\\Users\\mom\\Desktop\\변환된사진\\문서_변환.png",
        runner=lambda args: calls.append(args),
    )

    assert calls == [["explorer", "/select,C:\\Users\\mom\\Desktop\\변환된사진\\문서_변환.png"]]
