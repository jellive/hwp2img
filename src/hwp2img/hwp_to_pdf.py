from hwp2img.errors import HwpAutomationError, HwpNotInstalledError


def convert(hwp, hwp_path: str, pdf_path: str) -> None:
    try:
        if not hwp.open(hwp_path):
            raise HwpAutomationError(f"failed to open {hwp_path}")
        if not hwp.save_as(pdf_path, format="PDF"):
            raise HwpAutomationError(f"failed to save {pdf_path} as PDF")
    finally:
        hwp.quit(save=False)


def create_hwp():
    """실제 한글 COM 객체를 생성한다.
    Windows + 한컴오피스가 있어야 동작하므로 이 함수 자체는 원격 세션에서 수동으로 검증한다
    (계획 문서 Task 9 참고). pyhwpx 는 Hwp(register_module=True) 기본값으로 보안승인모듈을
    자동 등록하므로 여기서 레지스트리를 직접 건드리지 않는다.
    """
    try:
        from pyhwpx import Hwp
    except ImportError as exc:
        raise HwpNotInstalledError("pyhwpx not available") from exc

    try:
        return Hwp(visible=False)
    except Exception as exc:
        raise HwpNotInstalledError(str(exc)) from exc
