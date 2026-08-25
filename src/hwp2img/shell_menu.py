"""탐색기 우클릭 메뉴 등록 (Windows 전용, `HKCU` 만 쓴다 — 관리자 권한이 필요 없다).

어머니는 파일을 **찾은 다음 바탕화면 아이콘까지 끌어다 놔야** 했다. 창 두 개를 동시에
띄우고 좌표를 맞추는 조작이라 이 흐름에서 유일하게 손 기술이 필요한 자리였고, 이번 주
실기기 결함 2건이 전부 그 축에서 나왔다. 우클릭은 그 조작을 없앤다.

## Win11 이 경로를 둘로 만든다

평범한 shell verb 는 Windows 11 축약 메뉴에서 **무조건 "더 많은 옵션 표시" 아래**로 간다.
상단에 뜨려면 `IExplorerCommand` + app identity(sparse package) + 코드 서명이 필요한데
우리한테는 없다. 그래서 상단 경로는 **"프로그램에서 열기" 서브메뉴** 하나뿐이고, 거기
등록하는 정식 키가 `OpenWithProgids` 다(Microsoft: "OpenWithProgids 가 OpenWithList 보다
선호된다. OpenWithList 는 XP 이전 레거시 전용이다").

값 3개 더 쓰는 비용이라 **둘 다 건다.** 이 프로젝트에서 제일 비싼 것은 어머니 PC 왕복이고,
어느 쪽이 실제로 보이는지는 여기서 잴 수 없다.

## 확장자 키의 기본값은 절대 건드리지 않는다

`HKCU\\Software\\Classes\\.hwp` 의 기본값을 쓰면 한글 문서의 파일 연결을 가로챈다. 그러면
어머니가 .hwp 를 더블클릭해도 한글이 안 뜬다. 우리가 만드는 것은 그 아래 `OpenWithProgids`
하위 키뿐이고, 기본값이 비어 있으면 `HKCR` 병합 뷰에서 한글의 연결이 그대로 보인다.
"""

import sys

PROG_ID = "hwp2img.convert"
DISPLAY_NAME = "한글 사진으로 바꾸기"
EXTENSIONS = (".hwp", ".hwpx")
VERB = "hwp2img"

# 사용자별 클래스 루트. HKLM 은 쓰지 않는다 — 관리자 권한이 필요하고 어머니는 그걸 못 한다.
CLASSES = r"Software\Classes"


def command_line(exe: str) -> str:
    """탐색기가 실행할 명령.

    `%1` 의 인용을 빼지 마라. 빼면 공백 든 파일명이 argv 여러 개로 쪼개져 들어오고,
    `cli.main` 은 그걸 병합하지 않고 "한 번에 한 개씩" 안내로 거부한다. 즉 **공백 든
    파일만 조용히 실패**한다 — 어머니 입장에서는 "어떤 문서는 되고 어떤 건 안 됨"이 되어
    재현 정보 없이 지원해야 한다.
    """
    return f'"{exe}" "%1"'


def desired_entries(exe: str) -> list[tuple[str, str, str]]:
    """`(키 경로, 값 이름, 값)` 목록. 값 이름 `""` 은 그 키의 기본값이다. 전부 `REG_SZ`.

    순서가 곧 쓰는 순서다. 부모 키가 먼저 와야 `CreateKey` 가 중간 키를 만들며 내려간다.
    """
    command = command_line(exe)
    entries: list[tuple[str, str, str]] = [
        (rf"{CLASSES}\{PROG_ID}", "", DISPLAY_NAME),
        (rf"{CLASSES}\{PROG_ID}\shell\open\command", "", command),
    ]

    for ext in EXTENSIONS:
        # Win11 상단 경로 — "프로그램에서 열기" 서브메뉴.
        # 값이 빈 문자열인 것은 Microsoft 문서 그대로다(REG_NONE 또는 빈 REG_SZ).
        entries.append((rf"{CLASSES}\{ext}\OpenWithProgids", PROG_ID, ""))

        # 레거시 경로 — "더 많은 옵션 표시" 아래.
        verb = rf"{CLASSES}\SystemFileAssociations\{ext}\shell\{VERB}"
        entries.append((verb, "", DISPLAY_NAME))
        entries.append((rf"{verb}\command", "", command))

    return entries


def current_exe() -> str | None:
    """메뉴가 가리켜야 할 exe. 얼린 빌드가 아니면 `None`.

    개발 환경에서는 가리킬 exe 가 없다 — python 인터프리터 경로를 메뉴에 박으면 어머니 PC
    에서 아무것도 안 된다. 그리고 테스트를 돌리는 것만으로 내 레지스트리가 바뀌면 안 된다.

    `abspath` 를 씌우지 마라. 얼린 빌드의 `sys.executable` 은 이미 절대경로이고, 혹시라도
    아니라면 `abspath` 는 **탐색기가 준 cwd 기준으로** 풀어서 그럴듯하게 틀린 경로를 만든다.
    그 경로가 그대로 레지스트리에 박히면 메뉴는 보이는데 아무것도 안 되는 상태가 된다.
    """
    if not getattr(sys, "frozen", False):
        return None
    return sys.executable


def ensure_registered(exe: str | None = None, reader=None, writer=None) -> bool:
    """우클릭 메뉴를 등록한다. 이미 지금 exe 로 등록돼 있으면 아무것도 안 쓰고 True.

    이 함수는 **절대 예외를 던지지 않는다** — 메뉴 등록에 실패해도 변환은 되어야 한다.
    `security.ensure_security_module` 과 같은 규율이다.

    exe 경로가 바뀌면(이름변경·이동·다른 폴더의 새 버전) 전부 다시 쓴다. 설치 프로그램이
    아직 없어서 등록을 유지해 줄 주체가 없으므로, 실행할 때마다 스스로 고친다.
    """
    if reader is None:
        reader = _read_registry
    if writer is None:
        writer = _write_registry

    try:
        if exe is None:
            exe = current_exe()
        if not exe:
            return False

        entries = desired_entries(exe)

        # **전 항목**을 대조한다. 명령 키 하나만 보면 안 된다 — 그건 두 번째로 써지므로,
        # 그 뒤 항목에서 등록이 터지면 다음 실행이 "명령 키가 맞네" 하고 조기 반환해서
        # 메뉴 절반이 빠진 상태가 영구히 고착된다(cursor diff 리뷰 지적).
        if all(reader(key, name) == value for key, name, value in entries):
            return True

        for key_path, value_name, value in entries:
            writer(key_path, value_name, value)
        return True
    except Exception:
        return False


def unregister(deleter=None, value_deleter=None) -> bool:
    """등록한 것을 지운다 — 롤백 경로.

    **공유 키에서는 값만 지운다.** `.hwp\\OpenWithProgids` 에는 한글·다른 뷰어의 ProgID 가
    같이 들어 있다. 키를 통째로 지우면 그 앱들의 "프로그램에서 열기" 항목까지 날아간다
    (cursor diff 리뷰 지적 — 롤백이 등록보다 더 큰 사고를 내는 모양이었다).

    우리가 통째로 만든 키(`hwp2img.convert\\…`, `…\\shell\\hwp2img\\…`)만 키째로 지우고,
    확장자 키(`.hwp`) 자체는 건드리지 않는다. `winreg.DeleteKey` 는 하위 키가 있는 키를
    못 지우므로 깊은 것부터 지운다.
    """
    if deleter is None:
        deleter = _delete_registry_key
    if value_deleter is None:
        value_deleter = _delete_registry_value

    try:
        for key_path, value_name, _ in desired_entries("x"):
            if value_name:
                value_deleter(key_path, value_name)
        for key_path in _keys_deepest_first():
            deleter(key_path)
        return True
    except Exception:
        return False


def _keys_deepest_first() -> list[str]:
    keys = {key_path for key_path, _, _ in desired_entries("x")}

    # 중간 키(`…\shell\open`, `…\shell`)도 우리가 만든 것이라 같이 지운다.
    for key_path in list(keys):
        parts = key_path.split("\\")
        for depth in range(len(CLASSES.split("\\")) + 1, len(parts)):
            keys.add("\\".join(parts[:depth]))

    ours = [k for k in keys if _is_ours(k)]
    return sorted(ours, key=lambda k: k.count("\\"), reverse=True)


def _is_ours(key_path: str) -> bool:
    """우리가 통째로 만들지 않은 키를 롤백의 **키 삭제** 대상에서 뺀다.

    `OpenWithProgids` 는 여러 앱이 값을 나눠 갖는 공유 키다 — 여기서는 값만 지운다.
    """
    if key_path == CLASSES or key_path == rf"{CLASSES}\SystemFileAssociations":
        return False
    if key_path.endswith(r"\OpenWithProgids"):
        return False
    for ext in EXTENSIONS:
        if key_path in (rf"{CLASSES}\{ext}", rf"{CLASSES}\SystemFileAssociations\{ext}"):
            return False
    return True


def _read_registry(key_path: str, value_name: str) -> str | None:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
    except OSError:
        return None
    try:
        value, _kind = winreg.QueryValueEx(key, value_name)
        return value
    except OSError:
        return None
    finally:
        winreg.CloseKey(key)


def _write_registry(key_path: str, value_name: str, value: str) -> None:
    import winreg

    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, value)
    finally:
        winreg.CloseKey(key)


def _delete_registry_key(key_path: str) -> None:
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except OSError:
        # 없는 키를 지우는 것은 롤백에서 정상이다.
        pass


def _delete_registry_value(key_path: str, value_name: str) -> None:
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
    except OSError:
        return
    try:
        winreg.DeleteValue(key, value_name)
    except OSError:
        # 없는 값을 지우는 것은 롤백에서 정상이다.
        pass
    finally:
        winreg.CloseKey(key)
