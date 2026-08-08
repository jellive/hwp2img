import os
import tempfile

import pymupdf
import pytest
from PIL import Image

from hwp2img import cli, pdf_to_images
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


def test_process_file_produces_stitched_png_with_correct_height(tmp_path, monkeypatch, make_pdf):
    """페이지가 실제로 다 이어붙었는지 높이로 확인한다 — 예전 검사는 stitch 를
    `pages[0]` 으로 바꿔 2페이지째를 통째로 버려도 초록이었다."""
    clipboard_calls = []
    explorer_calls = []
    monkeypatch.setattr(cli.output, "copy_to_clipboard", lambda image: clipboard_calls.append(image))
    monkeypatch.setattr(cli.output, "open_in_explorer", lambda path: explorer_calls.append(path))

    # 기대 높이를 하드코딩하지 않고 같은 렌더 경로로 실측한다(dpi 가 바뀌어도 따라간다).
    single_page_pdf = make_pdf(page_count=1, width=200, height=300)
    single_height = pdf_to_images.render_pages(single_page_pdf)[0].height

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

    with Image.open(out_path) as result_image:
        assert result_image.height == single_height * 2


def test_process_file_keeps_the_saved_png_when_clipboard_and_explorer_fail(tmp_path, monkeypatch):
    """클립보드를 다른 앱이 잡고 있는 건 Windows 에서 흔하다. 그것 때문에 이미 저장된
    이미지가 없는 것처럼 보이면 안 된다."""

    def boom(*args, **kwargs):
        raise RuntimeError("clipboard is held by another application")

    monkeypatch.setattr(cli.output, "copy_to_clipboard", boom)
    monkeypatch.setattr(cli.output, "open_in_explorer", boom)
    monkeypatch.setattr(cli, "_show_notice", lambda msg: None)

    hwp_path = tmp_path / "공문.hwp"
    hwp_path.write_text("dummy")
    output_dir = tmp_path / "out"

    out_path = cli.process_file(
        str(hwp_path), str(output_dir), lambda: FakeHwpWritesRealPdf(page_count=1)
    )

    assert out_path == str(output_dir / "공문_변환.png")
    assert os.path.exists(out_path)


def test_process_file_shows_notice_when_clipboard_copy_fails(tmp_path, monkeypatch):
    """복사 실패를 조용히 넘기면 어머니가 Ctrl+V 로 직전 클립보드 내용(사적인 캡처 등)을
    그대로 전송할 수 있다 — 그래서 이때만은 조용히 넘어가지 않고 알린다."""

    def boom(*args, **kwargs):
        raise RuntimeError("clipboard is held by another application")

    notices = []
    monkeypatch.setattr(cli.output, "copy_to_clipboard", boom)
    monkeypatch.setattr(cli.output, "open_in_explorer", lambda path: None)
    monkeypatch.setattr(cli, "_show_notice", lambda msg: notices.append(msg))

    hwp_path = tmp_path / "공문.hwp"
    hwp_path.write_text("dummy")
    output_dir = tmp_path / "out"

    out_path = cli.process_file(
        str(hwp_path), str(output_dir), lambda: FakeHwpWritesRealPdf(page_count=1)
    )

    assert out_path == str(output_dir / "공문_변환.png")
    assert os.path.exists(out_path)
    assert len(notices) == 1
    assert "저장했어요" in notices[0]


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


def test_main_logs_traceback_and_hides_raw_exception_on_unexpected_error(monkeypatch, tmp_path):
    fake_home = tmp_path / "fake_home"
    (fake_home / "Desktop").mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(fake_home))

    messages = []
    monkeypatch.setattr(cli, "_show_error", lambda msg: messages.append(msg))

    raw_detail = "0x80040154 CoCreateInstance failed: 클래스가 등록되어 있지 않습니다"

    def failing_process_file(*args, **kwargs):
        raise RuntimeError(raw_detail)

    monkeypatch.setattr(cli, "process_file", failing_process_file)

    result = cli.main(["whatever.hwp"])

    assert result == 1

    log_path = fake_home / "Desktop" / "hwp2img_오류.log"
    assert log_path.exists()
    assert raw_detail in log_path.read_text(encoding="utf-8")

    assert len(messages) == 1
    assert raw_detail not in messages[0]
    assert str(log_path) in messages[0]


def test_main_uses_the_source_files_own_directory_as_output_dir(monkeypatch, tmp_path):
    """바탕화면 고정 경로는 OneDrive 동기화 환경에서 유령 폴더를 만든다 — 원본 파일 옆에
    저장하면 어머니가 방금 파일을 끌어온 바로 그 폴더에 결과가 남는다."""
    captured = {}

    def fake_process_file(hwp_path, output_dir, hwp_factory, dpi=200):
        captured["output_dir"] = output_dir
        return "ignored"

    monkeypatch.setattr(cli, "process_file", fake_process_file)

    hwp_dir = tmp_path / "문서함"
    hwp_dir.mkdir()
    hwp_path = hwp_dir / "공문.hwp"
    hwp_path.write_text("dummy")

    result = cli.main([str(hwp_path)])

    assert captured["output_dir"] == str(hwp_dir)
    assert result == 0


def test_log_error_falls_back_to_tempdir_when_desktop_is_unavailable(monkeypatch, tmp_path):
    """OneDrive 폴더 리디렉션 등으로 바탕화면이 없을 수 있다. 마지막 방어선인
    _log_error 가 거기서 죽으면 --noconsole 빌드에선 아무 안내도 안 남는다."""
    desktop = tmp_path / "Desktop"
    fallback = tmp_path / "fallback_tmp"
    fallback.mkdir()

    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(fallback))

    real_makedirs = os.makedirs

    def desktop_is_missing(path, *args, **kwargs):
        if path == str(desktop):
            raise OSError("바탕화면 폴더가 없습니다")
        return real_makedirs(path, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", desktop_is_missing)

    log_path = cli._log_error(RuntimeError("0x80040154 클래스가 등록되어 있지 않습니다"))

    assert log_path == str(fallback / "hwp2img_오류.log")
    contents = (fallback / "hwp2img_오류.log").read_text(encoding="utf-8")
    # except 블록 밖에서 불렀으므로, 넘겨준 exc 를 직접 포맷하지 않으면 이 문자열은 안 남는다.
    assert "0x80040154" in contents


def test_log_error_returns_sentinel_when_every_location_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "also_unwritable"))

    def nothing_is_writable(path, *args, **kwargs):
        raise OSError("읽기 전용 파일 시스템")

    monkeypatch.setattr(os, "makedirs", nothing_is_writable)

    assert cli._log_error(RuntimeError("boom")) == "(로그 파일을 만들 수 없었어요)"


def test_main_still_shows_a_message_when_logging_cannot_write_anywhere(monkeypatch, tmp_path):
    """로그를 못 남기더라도 사용자에게는 뭐라도 보여야 한다."""
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "also_unwritable"))
    monkeypatch.setattr(os, "makedirs", _raise_oserror)

    messages = []
    monkeypatch.setattr(cli, "_show_error", lambda msg: messages.append(msg))
    monkeypatch.setattr(cli, "process_file", _raise_runtime_error)

    result = cli.main(["whatever.hwp"])

    assert result == 1
    assert len(messages) == 1
    assert "(로그 파일을 만들 수 없었어요)" in messages[0]


def _raise_oserror(*args, **kwargs):
    raise OSError("읽기 전용 파일 시스템")


def _raise_runtime_error(*args, **kwargs):
    raise RuntimeError("무슨 일이 났는지 사용자에게 그대로 보여주면 안 되는 내용")
