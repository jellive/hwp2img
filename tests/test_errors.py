from hwp2img.errors import (
    Hwp2ImgError,
    HwpAutomationError,
    HwpNotInstalledError,
    HwpTimeoutError,
    UnsupportedFileError,
)


def test_unsupported_file_error_has_korean_message():
    exc = UnsupportedFileError("notes.txt")
    assert exc.user_message == "한글 문서 파일(.hwp, .hwpx)만 변환할 수 있어요."
    assert isinstance(exc, Hwp2ImgError)


def test_hwp_not_installed_error_has_korean_message():
    exc = HwpNotInstalledError("no pyhwpx")
    assert "한글이 설치되어 있는지" in exc.user_message


def test_hwp_automation_error_has_korean_message():
    exc = HwpAutomationError("open failed")
    assert "손상되지" in exc.user_message


def test_hwp_timeout_error_has_korean_message():
    """암호 걸린 hwp 등으로 COM 이 응답 없이 멈췄을 때의 안내 — 자세한 원인(타임아웃 초 등)은
    detail 에만 담고, 어머니에게는 쉬운 말과 짐작 가능한 원인만 보인다."""
    exc = HwpTimeoutError("conversion timed out after 30s")
    assert isinstance(exc, Hwp2ImgError)
    assert "암호" in exc.user_message
    assert "변환할 수 없어요" in exc.user_message
