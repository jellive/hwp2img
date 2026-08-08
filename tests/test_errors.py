from hwp2img.errors import Hwp2ImgError, UnsupportedFileError, HwpNotInstalledError, HwpAutomationError


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
