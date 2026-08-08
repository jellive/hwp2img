import os

from hwp2img.errors import HwpAutomationError, HwpNotInstalledError


def convert(hwp, hwp_path: str, pdf_path: str) -> None:
    try:
        if not hwp.open(hwp_path):
            raise HwpAutomationError(f"failed to open {hwp_path}")
        if not hwp.save_as(pdf_path, format="PDF"):
            raise HwpAutomationError(f"failed to save {pdf_path} as PDF")
    finally:
        # quit 실패가 진짜 원인(open/save 실패)을 덮어써서 원인을 가리지 않게 삼킨다.
        try:
            hwp.quit(save=False)
        except Exception:
            pass

    # COM 자동화는 성공을 반환하고도 파일을 안 만드는 경우가 있어 결과물을 직접 확인한다.
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
        raise HwpAutomationError(f"{pdf_path} was not created or is empty")


def create_hwp():
    """실제 한글 COM 객체를 생성한다.
    Windows + 한컴오피스가 있어야 동작하므로 이 함수 자체는 원격 세션에서 수동으로 검증한다
    (계획 문서 Task 9 참고). pyhwpx 는 Hwp(register_module=True) 기본값으로 보안승인모듈을
    자동 등록하므로 여기서 레지스트리를 직접 건드리지 않는다.

    `new=True` 는 필수다 — 기본값(new=False)이면 pyhwpx 가 이미 실행 중인 한글 COM 인스턴스에
    붙어버려서, 사용자가 열어둔 문서를 우리가 숨기고(visible=False) 마지막에 quit(save=False) 로
    날려버린다. 항상 별도 프로세스를 새로 띄운다.
    """
    try:
        from pyhwpx import Hwp
    except ImportError as exc:
        raise HwpNotInstalledError("pyhwpx not available") from exc

    try:
        return Hwp(new=True, visible=False)
    except Exception as exc:
        raise HwpNotInstalledError(str(exc)) from exc
