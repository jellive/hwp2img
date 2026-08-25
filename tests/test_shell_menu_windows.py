"""진짜 `winreg` 로 도는 우클릭 메뉴 등록 테스트 (Windows 에서만).

`test_shell_menu.py` 는 가짜 레지스트리로 돈다. **그래서 그 파일이 초록인 것은 레지스트리에
실제로 써진다는 증거가 아니다** — 이번 주에 가짜 `shell32` 뒤에서 테스트 95개가 초록인 채
드래그앤드롭이 완전히 깨져 있었다(ctypes `argtypes` 미선언). 파이썬 가짜가 경계를 대신하면
그 경계는 검증 안 된 것이다. 여기서 그 경계를 실제로 넘는다.

**폭발 반경 0:** `shell_menu.CLASSES` 를 테스트 전용 하위 트리로 바꿔치기해서, 진짜 winreg
호출을 그대로 쓰되 어머니의 실제 파일 연결(`HKCU\\Software\\Classes\\.hwp`)은 건드리지 않는다.
"""

import os

import pytest

from hwp2img import shell_menu
from hwp2img.shell_menu import (
    EXTENSIONS,
    PROG_ID,
    command_line,
    desired_entries,
    ensure_registered,
    unregister,
)

winreg = pytest.importorskip("winreg", reason="Windows 에서만 도는 테스트다")

EXE = r"C:\Users\m\Desktop\hwp2img.exe"
MOVED_EXE = r"C:\Program Files\한글 사진으로 바꾸기\hwp2img.exe"


def _delete_tree(path: str) -> None:
    """하위 키까지 통째로 지운다 — `winreg.DeleteKey` 는 자식이 있으면 못 지운다."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ)
    except OSError:
        return
    children = []
    try:
        index = 0
        while True:
            try:
                children.append(winreg.EnumKey(key, index))
            except OSError:
                break
            index += 1
    finally:
        winreg.CloseKey(key)

    for child in children:
        _delete_tree(f"{path}\\{child}")
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        pass


@pytest.fixture
def sandbox(monkeypatch):
    """진짜 레지스트리에 쓰되, 실제 파일 연결과 겹치지 않는 하위 트리로 보낸다."""
    root = rf"Software\hwp2img_test_{os.getpid()}"
    monkeypatch.setattr(shell_menu, "CLASSES", rf"{root}\Classes")
    _delete_tree(root)
    yield root
    _delete_tree(root)


def _read(key_path: str, value_name: str):
    return shell_menu._read_registry(key_path, value_name)


# --- 경계가 실제로 넘어가는가 -------------------------------------------------


def test_a_real_registration_round_trips_the_exact_command(sandbox):
    assert ensure_registered(exe=EXE) is True

    command_key = rf"{shell_menu.CLASSES}\{PROG_ID}\shell\open\command"
    assert _read(command_key, "") == command_line(EXE)


def test_a_real_write_creates_every_intermediate_key(sandbox):
    # `…\shell\open\command` 는 세 단계 아래다. CreateKeyEx 가 중간 키를 만들어야 한다.
    ensure_registered(exe=EXE)

    for depth_key in (
        rf"{shell_menu.CLASSES}\{PROG_ID}",
        rf"{shell_menu.CLASSES}\{PROG_ID}\shell",
        rf"{shell_menu.CLASSES}\{PROG_ID}\shell\open",
        rf"{shell_menu.CLASSES}\{PROG_ID}\shell\open\command",
    ):
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, depth_key, 0, winreg.KEY_READ))


def test_a_spaced_exe_path_survives_the_real_round_trip(sandbox):
    ensure_registered(exe=MOVED_EXE)

    command = _read(rf"{shell_menu.CLASSES}\{PROG_ID}\shell\open\command", "")
    assert command == f'"{MOVED_EXE}" "%1"'
    assert '"%1"' in command


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_the_open_with_entry_really_lands_under_the_extension(sandbox, ext):
    ensure_registered(exe=EXE)

    assert _read(rf"{shell_menu.CLASSES}\{ext}\OpenWithProgids", PROG_ID) == ""


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_the_legacy_verb_really_lands_under_system_file_associations(sandbox, ext):
    ensure_registered(exe=EXE)

    verb = rf"{shell_menu.CLASSES}\SystemFileAssociations\{ext}\shell\{shell_menu.VERB}"
    assert _read(verb, "") == shell_menu.DISPLAY_NAME
    assert _read(rf"{verb}\command", "") == command_line(EXE)


# --- 어머니의 파일 연결을 가로채지 않는다 (실레지스트리로 확인) ----------------
#
# 이 검사가 이 파일에서 제일 중요하다. 확장자 키의 기본값을 쓰면 .hwp 더블클릭이
# 한글이 아니라 우리 프로그램으로 가서, 어머니가 문서를 아예 못 연다.


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_the_extension_default_value_is_still_untouched_after_registering(sandbox, ext):
    ensure_registered(exe=EXE)

    assert _read(rf"{shell_menu.CLASSES}\{ext}", "") is None


# --- exe 가 움직이면 실제로 다시 써지는가 -------------------------------------


def test_moving_the_exe_really_rewrites_the_command(sandbox):
    ensure_registered(exe=EXE)

    ensure_registered(exe=MOVED_EXE)

    assert _read(rf"{shell_menu.CLASSES}\{PROG_ID}\shell\open\command", "") == command_line(
        MOVED_EXE
    )
    verb_command = rf"{shell_menu.CLASSES}\SystemFileAssociations\.hwp\shell\{shell_menu.VERB}\command"
    assert _read(verb_command, "") == command_line(MOVED_EXE)


def test_registering_the_same_exe_twice_is_a_no_op_against_the_real_registry(sandbox):
    ensure_registered(exe=EXE)
    writes = []

    ensure_registered(exe=EXE, writer=lambda *args: writes.append(args))

    assert writes == []


# --- 롤백 (고위험 변경이라 증거가 필요하다) ------------------------------------


def test_a_real_unregister_removes_everything_we_wrote(sandbox):
    ensure_registered(exe=EXE)

    assert unregister() is True

    for key_path, value_name, _ in desired_entries(EXE):
        assert _read(key_path, value_name) is None


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_unregister_leaves_the_extension_key_itself_alone(sandbox, ext):
    # 확장자 키는 우리가 만든 것이 아닐 수 있다. 지우면 한글의 연결까지 날아간다.
    ensure_registered(exe=EXE)
    unregister()

    winreg.CloseKey(
        winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, rf"{shell_menu.CLASSES}\{ext}", 0, winreg.KEY_READ
        )
    )


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_a_real_unregister_keeps_another_apps_open_with_entry(sandbox, ext):
    """`OpenWithProgids` 는 공유 키다 — 롤백이 남의 항목까지 지우면 안 된다.

    진짜 `winreg.DeleteValue` 경로를 탄다. 키를 통째로 지우던 시절에는 여기서
    `Hwp.Document` 가 같이 사라졌다.
    """
    shared = rf"{shell_menu.CLASSES}\{ext}\OpenWithProgids"
    ensure_registered(exe=EXE)
    shell_menu._write_registry(shared, "Hwp.Document", "")

    assert unregister() is True

    assert _read(shared, PROG_ID) is None
    assert _read(shared, "Hwp.Document") == ""
