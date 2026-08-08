import struct

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
    # 스트립된 데이터가 유효한 BITMAPINFOHEADER(biSize=40)로 시작하는지 확인 —
    # 14바이트를 정확히 제거했는지 검증(13/15바이트 스트립도 startswith(b"BM") 검사만으론 통과함)
    assert struct.unpack_from("<I", set_call[2], 0)[0] == 40
    assert fake.calls[3] == "close"


def test_copy_to_clipboard_closes_even_if_set_fails():
    image = Image.new("RGB", (10, 10), color="blue")
    fake = FakeClipboard(raise_on_set=True)

    with pytest.raises(RuntimeError):
        copy_to_clipboard(image, clipboard_module=fake)

    assert fake.calls[-1] == "close"


def test_open_in_explorer_opens_the_containing_folder():
    """리스트 형태(`["explorer", f"/select,{path}"]`)는 subprocess 의 list2cmdline 이
    `/select` 까지 통째로 인용해버려 깨진다(실측) — 문자열 명령 형태로만 정확히 동작한다."""
    calls = []

    open_in_explorer(
        "C:\\Users\\mom\\Desktop\\변환된사진\\문서_변환.png",
        runner=lambda cmd: calls.append(cmd),
    )

    assert calls == ['explorer /select,"C:\\Users\\mom\\Desktop\\변환된사진\\문서_변환.png"']


def test_open_in_explorer_handles_paths_with_spaces():
    """공백이 든 한글 파일명은 흔하다. 두 가지 형태가 실측으로 깨졌었다:
    리스트 형태는 `/select` 까지 인용 안에 갇히고, `f'/select,"{path}"'` 형태는
    안쪽 따옴표가 이스케이프된다. 문자열 명령 형태만 정확한 명령을 만든다 —
    `"select" in cmd` 같은 부분 검사로는 이 인용 버그를 못 잡으므로 전체 문자열을 비교한다."""
    calls = []

    open_in_explorer(
        "C:\\Users\\mom\\Desktop\\어린이집 안내문 (3월)_변환.png",
        runner=lambda cmd: calls.append(cmd),
    )

    assert calls == ['explorer /select,"C:\\Users\\mom\\Desktop\\어린이집 안내문 (3월)_변환.png"']
