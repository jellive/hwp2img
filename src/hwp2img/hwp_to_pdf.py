import os

from hwp2img.errors import HwpAutomationError, HwpNotInstalledError
from hwp2img.security import ensure_security_module


def convert(hwp, hwp_path: str, pdf_path: str) -> None:
    try:
        # open()/save_as() 는 실패를 bool False 로도, 예외로도 알릴 수 있다(암호 걸린 문서,
        # 파일 잠김, 권한 등은 COM 이 예외를 던진다) — 둘 다 같은 HwpAutomationError 로 모아야
        # main() 의 일반 캐치올("예상하지 못한 문제가...")이 아니라 이미 있는 구체적인
        # 한국어 안내로 간다.
        try:
            opened = hwp.open(hwp_path)
        except Exception as exc:
            raise HwpAutomationError(f"open() raised for {hwp_path}: {exc}") from exc
        if not opened:
            raise HwpAutomationError(f"failed to open {hwp_path}")

        try:
            saved = hwp.save_as(pdf_path, format="PDF")
        except Exception as exc:
            raise HwpAutomationError(f"save_as() raised for {pdf_path}: {exc}") from exc
        if not saved:
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
    (계획 문서 Task 9 참고).

    보안승인모듈은 우리가 먼저 등록한다. pyhwpx 도 `register_module=True` 기본값으로
    같은 일을 하지만 그 구현이 `pip` 실행에 의존해서 얼린 exe 에서는 항상 실패한다
    (자세한 내용은 security.py). 등록에 실패해도 변환은 그대로 시도한다 —
    최악의 경우 한글 보안 팝업이 한 번 뜰 뿐이다.

    `new=True` 는 필수다 — 기본값(new=False)이면 pyhwpx 가 이미 실행 중인 한글 COM 인스턴스에
    붙어버려서, 사용자가 열어둔 문서를 우리가 숨기고(visible=False) 마지막에 quit(save=False) 로
    날려버린다. 항상 별도 프로세스를 새로 띄운다.
    """
    ensure_security_module()

    try:
        from pyhwpx import Hwp
    except ImportError as exc:
        raise HwpNotInstalledError("pyhwpx not available") from exc

    try:
        return Hwp(new=True, visible=False)
    except Exception as exc:
        raise HwpNotInstalledError(str(exc)) from exc
