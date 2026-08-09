"""한글 오토메이션 보안승인모듈(FilePathCheckerModule.dll) 등록.

한글은 오토메이션이 파일을 열고 저장할 때 사용자에게 승인 팝업을 띄운다.
보안승인모듈을 레지스트리에 등록해 두면 이 팝업이 생략된다.

pyhwpx 도 `Hwp(register_module=True)` 로 같은 일을 하려 하지만, 그 구현은 dll 위치를
찾으려고 `pip show pyhwpx` 를 서브프로세스로 부른다. PyInstaller 로 얼린 exe 에는 pip 가
없어서 그 호출이 실패하고, 실패를 삼킨 뒤 초기화되지 않은 지역변수를 읽어
`UnboundLocalError` 로 죽는다("RegisterModule 액션을 실행할 수 없음"). 그러면 그 다음의
`RegisterModule()` 호출까지 통째로 건너뛰어 결국 어머니 PC 에서 보안 팝업이 뜬다.
개발 PC 에서는 pip 가 있어 우연히 넘어가므로 배포 후에야 드러난다.

그래서 dll 경로를 우리가 직접 찾아 레지스트리에 적어 둔다. 값이 이미 올바르게 있으면
pyhwpx 의 `check_registry_key()` 가 True 를 돌려주어 문제의 코드 경로 자체를 타지 않는다.

onefile exe 에서는 등록되는 경로가 실행할 때마다 새로 풀리는 임시 폴더(`_MEIxxxxx`)
안이라, 프로그램이 끝나면 그 값은 없는 경로를 가리키게 된다. 한글이 dll 을 읽는 시점은
프로그램이 돌고 있는 동안이라 동작에는 문제가 없고, 다음 실행 때 아래 `exists` 검사가
실패해 새 경로로 다시 쓴다.
"""

import os
import sys

DLL_NAME = "FilePathCheckerModule.dll"
VALUE_NAME = "FilePathCheckerModule"

# 한글 버전에 따라 키가 다르다. pyhwpx 의 check_registry_key 도 이 순서로 확인한다.
REGISTRY_PATHS = (
    r"Software\HNC\HwpAutomation\Modules",
    r"Software\Hnc\HwpUserAction\Modules",
)


def candidate_dirs() -> list[str]:
    """보안모듈 dll 이 있을 만한 폴더를 우선순위대로 돌려준다."""
    dirs = []

    # PyInstaller onefile 이 압축을 푸는 임시 폴더. --collect-all pyhwpx 로 빌드하면
    # dll 이 그 아래 pyhwpx/ 에 들어간다.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(os.path.join(meipass, "pyhwpx"))
        dirs.append(meipass)

    # exe 와 같은 폴더에 dll 을 손으로 놔둔 경우
    if sys.argv and sys.argv[0]:
        dirs.append(os.path.dirname(os.path.abspath(sys.argv[0])))

    # 개발 환경: 설치된 pyhwpx 패키지 안
    try:
        import pyhwpx

        dirs.append(os.path.dirname(os.path.abspath(pyhwpx.__file__)))
    except Exception:
        pass

    return dirs


def find_security_dll(dirs=None, exists=None) -> str | None:
    if dirs is None:
        dirs = candidate_dirs()
    if exists is None:
        exists = os.path.exists

    for directory in dirs:
        if not directory:
            continue
        path = os.path.join(directory, DLL_NAME)
        if exists(path):
            return path
    return None


def ensure_security_module(dll_path=None, reader=None, writer=None, exists=None) -> bool:
    """보안승인모듈을 레지스트리에 등록한다. 등록되어 있으면 True.

    이 함수는 절대 예외를 던지지 않는다 — 등록에 실패해도 변환은 시도해야 한다.
    최악의 경우 사용자에게 한글 보안 팝업이 뜰 뿐이고, 그건 변환 실패보다 낫다.
    """
    if exists is None:
        exists = os.path.exists
    if reader is None:
        reader = _read_registry
    if writer is None:
        writer = _write_registry

    try:
        current = reader()
        if current and exists(current):
            return True

        path = dll_path or find_security_dll(exists=exists)
        if not path:
            return False

        writer(path)
        return True
    except Exception:
        return False


def _read_registry() -> str | None:
    import winreg

    for path in REGISTRY_PATHS:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ)
        except OSError:
            continue
        try:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            if value:
                return value
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)
    return None


def _write_registry(dll_path: str) -> None:
    """이미 있는 키에 먼저 쓰고, 둘 다 없으면 첫 번째 키를 만들어 쓴다.

    한글 버전마다 쓰는 키가 달라서, 없는 키를 새로 만들어 넣는 것보다
    그 PC 에 실제로 존재하는 키에 넣는 편이 맞을 확률이 높다.
    """
    import winreg

    for path in REGISTRY_PATHS:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_WRITE)
        except OSError:
            continue
        try:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, dll_path)
            return
        finally:
            winreg.CloseKey(key)

    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_PATHS[0], 0, winreg.KEY_WRITE)
    try:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, dll_path)
    finally:
        winreg.CloseKey(key)
