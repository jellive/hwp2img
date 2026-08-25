"""탐색기 우클릭 메뉴 등록의 불변식.

여기 테스트는 전부 **주입한 가짜 레지스트리**로 돈다. 그래서 이 파일이 초록인 것은
"레지스트리에 실제로 써진다"의 증거가 **아니다** — 진짜 `winreg` 경계는
`test_shell_menu_windows.py` 가 Windows 에서만 본다. 이번 주에 가짜 `shell32` 뒤에서
테스트 95개가 초록인 채로 드래그앤드롭이 완전히 깨져 있었던 것과 같은 함정이다.
"""

import pytest

from hwp2img import shell_menu
from hwp2img.shell_menu import (
    CLASSES,
    DISPLAY_NAME,
    EXTENSIONS,
    PROG_ID,
    command_line,
    desired_entries,
    ensure_registered,
    unregister,
)

EXE = r"C:\Users\m\Desktop\hwp2img.exe"


class FakeRegistry:
    """키 경로 → {값 이름: 값}. 값 이름 "" 은 기본값이다."""

    def __init__(self, initial=None):
        self.keys = dict(initial or {})
        self.writes = []
        self.deleted = []
        self.deleted_values = []

    def read(self, key_path, value_name):
        return self.keys.get(key_path, {}).get(value_name)

    def write(self, key_path, value_name, value):
        self.keys.setdefault(key_path, {})[value_name] = value
        self.writes.append((key_path, value_name, value))

    def delete(self, key_path):
        self.keys.pop(key_path, None)
        self.deleted.append(key_path)

    def delete_value(self, key_path, value_name):
        self.keys.get(key_path, {}).pop(value_name, None)
        self.deleted_values.append((key_path, value_name))


# --- 불변식 1: `%1` 은 반드시 인용된다 -----------------------------------------
#
# 인용이 빠지면 공백 든 파일명이 argv 여러 개로 쪼개져 들어오고, `cli.main` 은 그걸
# 병합하지 않고 `TOO_MANY_FILES` 로 거부한다(`cli.py` 의 `len(argv) > 1` 분기).
# 즉 **공백 든 파일만 조용히 실패**한다 — 어머니 입장에선 "어떤 문서는 되고 어떤 건 안 됨".


def test_the_command_quotes_the_file_argument():
    assert command_line(EXE) == f'"{EXE}" "%1"'


def test_the_command_quotes_an_exe_path_that_has_spaces():
    exe = r"C:\Program Files\한글 사진으로 바꾸기\hwp2img.exe"

    assert command_line(exe) == f'"{exe}" "%1"'


def test_every_command_entry_passes_exactly_one_quoted_argument():
    commands = [v for _, _, v in desired_entries(EXE) if "%1" in v]

    assert commands, "명령 항목이 하나도 없다"
    for command in commands:
        assert command.count("%1") == 1
        assert '"%1"' in command


# --- 불변식 2: 확장자 키의 기본값을 절대 안 쓴다 --------------------------------
#
# `HKCU\Software\Classes\.hwp` 의 기본값을 쓰면 한글 문서의 파일 연결을 가로챈다.
# 그러면 어머니가 .hwp 를 더블클릭해도 한글이 안 뜬다 — 되돌리기 전까지 문서를 못 연다.


def test_no_entry_touches_the_default_value_of_an_extension_key():
    for key_path, value_name, _ in desired_entries(EXE):
        for ext in EXTENSIONS:
            assert not (key_path == rf"{CLASSES}\{ext}" and value_name == "")


def test_the_extension_is_only_touched_under_open_with_progids():
    for ext in EXTENSIONS:
        # `.hwp` 는 `.hwpx` 의 접두사라 단순 startswith 로는 둘이 섞인다.
        key = rf"{CLASSES}\{ext}"
        touched = [
            k for k, _, _ in desired_entries(EXE) if k == key or k.startswith(key + "\\")
        ]

        assert touched == [rf"{key}\OpenWithProgids"]


# --- 불변식 3: HKLM 을 안 건드린다 ---------------------------------------------


def test_every_key_lives_under_the_per_user_classes_root():
    for key_path, _, _ in desired_entries(EXE):
        assert key_path.startswith(CLASSES + "\\")


# --- 두 경로를 다 건다 ---------------------------------------------------------
#
# Win11 축약 메뉴는 평범한 shell verb 를 "더 많은 옵션 표시" 아래로 숨긴다.
# 상단 경로는 "프로그램에서 열기"(= OpenWithProgids) 하나뿐이라 둘 다 등록한다.


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_the_windows11_top_level_route_is_registered(ext):
    entries = desired_entries(EXE)

    assert (rf"{CLASSES}\{ext}\OpenWithProgids", PROG_ID, "") in entries
    assert (rf"{CLASSES}\{PROG_ID}\shell\open\command", "", command_line(EXE)) in entries


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_the_legacy_more_options_route_is_registered(ext):
    entries = desired_entries(EXE)
    verb = rf"{CLASSES}\SystemFileAssociations\{ext}\shell\{shell_menu.VERB}"

    assert (verb, "", DISPLAY_NAME) in entries
    assert (rf"{verb}\command", "", command_line(EXE)) in entries


def test_the_menu_label_is_what_the_mother_sees():
    labels = [v for k, name, v in desired_entries(EXE) if name == "" and "%1" not in v]

    assert labels, "표시 이름 항목이 하나도 없다"
    assert set(labels) == {DISPLAY_NAME}


# --- 등록 동작 -----------------------------------------------------------------


def test_registering_writes_every_entry():
    registry = FakeRegistry()

    assert ensure_registered(exe=EXE, reader=registry.read, writer=registry.write) is True
    assert registry.writes == desired_entries(EXE)


def test_registering_again_with_the_same_exe_writes_nothing():
    registry = FakeRegistry()
    ensure_registered(exe=EXE, reader=registry.read, writer=registry.write)
    registry.writes.clear()

    assert ensure_registered(exe=EXE, reader=registry.read, writer=registry.write) is True
    assert registry.writes == []


# --- 불변식 4: exe 가 움직이면 스스로 고친다 -----------------------------------
#
# 바탕화면 exe 는 이름변경·이동·새 버전 덮어쓰기로 경로가 쉽게 바뀐다(크로스모델 지적).
# 설치 프로그램이 아직 없으니 매 실행 시 자가 치유로 푼다.


def test_a_moved_exe_is_registered_again_at_the_new_path():
    registry = FakeRegistry()
    ensure_registered(exe=EXE, reader=registry.read, writer=registry.write)
    registry.writes.clear()
    moved = r"D:\프로그램\hwp2img.exe"

    ensure_registered(exe=moved, reader=registry.read, writer=registry.write)

    assert registry.writes == desired_entries(moved)
    assert registry.read(rf"{CLASSES}\{PROG_ID}\shell\open\command", "") == command_line(moved)


# --- 불변식 5: 등록 실패가 변환을 막지 않는다 ----------------------------------


def test_a_registry_failure_is_swallowed():
    def explode(*_args):
        raise OSError("액세스가 거부되었습니다")

    assert ensure_registered(exe=EXE, reader=lambda *_: None, writer=explode) is False


def test_a_read_failure_is_swallowed():
    def explode(*_args):
        raise OSError("액세스가 거부되었습니다")

    assert ensure_registered(exe=EXE, reader=explode, writer=lambda *_: None) is False


# --- 얼리지 않은 환경에서는 아무것도 등록하지 않는다 ---------------------------
#
# 개발 PC 에서 테스트를 돌리는 것만으로 내 레지스트리가 바뀌면 안 된다. 그리고 dev 에서는
# 가리킬 exe 자체가 없다 — python 인터프리터를 메뉴에 박으면 어머니 PC 에서 못 쓴다.


def test_nothing_is_registered_when_there_is_no_frozen_exe(monkeypatch):
    monkeypatch.setattr(shell_menu, "current_exe", lambda: None)
    registry = FakeRegistry()

    assert ensure_registered(reader=registry.read, writer=registry.write) is False
    assert registry.writes == []


def test_current_exe_is_none_unless_the_app_is_frozen(monkeypatch):
    monkeypatch.delattr(shell_menu.sys, "frozen", raising=False)

    assert shell_menu.current_exe() is None


def test_current_exe_is_the_running_exe_when_frozen(monkeypatch):
    monkeypatch.setattr(shell_menu.sys, "frozen", True, raising=False)
    monkeypatch.setattr(shell_menu.sys, "executable", EXE, raising=False)

    assert shell_menu.current_exe() == EXE


# --- 롤백 ---------------------------------------------------------------------


def test_unregister_removes_every_thing_we_wrote():
    """등록한 것이 하나도 안 남아야 한다 — 키로 지웠든 값으로 지웠든."""
    registry = FakeRegistry()
    ensure_registered(exe=EXE, reader=registry.read, writer=registry.write)

    unregister(deleter=registry.delete, value_deleter=registry.delete_value)

    for key_path, value_name, _ in desired_entries(EXE):
        assert registry.read(key_path, value_name) is None


def test_unregister_deletes_children_before_their_parents():
    registry = FakeRegistry()

    unregister(deleter=registry.delete, value_deleter=registry.delete_value)

    for index, key_path in enumerate(registry.deleted):
        for later in registry.deleted[index + 1 :]:
            assert not later.startswith(key_path + "\\"), (
                f"{later} 를 부모 {key_path} 보다 나중에 지운다 — winreg.DeleteKey 는 "
                "하위 키가 있는 키를 못 지운다"
            )


def test_unregister_never_raises():
    def explode(*_args):
        raise OSError("액세스가 거부되었습니다")

    assert unregister(deleter=explode, value_deleter=lambda *_: None) is False
    assert unregister(deleter=lambda *_: None, value_deleter=explode) is False


# --- cursor diff 리뷰가 잡은 결함 2건의 재현 테스트 ----------------------------


def test_unregister_never_deletes_the_shared_open_with_key():
    """`OpenWithProgids` 는 **공유 키**다 — 한글·다른 뷰어의 ProgID 가 같이 들어 있다.

    키를 통째로 지우면 우리 것만이 아니라 그 앱들의 "프로그램에서 열기" 항목까지 날아간다.
    우리 값 하나만 지워야 한다.
    """
    registry = FakeRegistry()
    shared = rf"{CLASSES}\.hwp\OpenWithProgids"
    registry.write(shared, "Hwp.Document", "")  # 다른 앱이 이미 넣어 둔 값
    ensure_registered(exe=EXE, reader=registry.read, writer=registry.write)

    unregister(deleter=registry.delete, value_deleter=registry.delete_value)

    assert shared not in registry.deleted, "공유 키를 통째로 지웠다"
    assert (shared, PROG_ID) in registry.deleted_values
    assert registry.read(shared, "Hwp.Document") == "", "다른 앱의 항목이 사라졌다"


def test_unregister_still_removes_our_own_keys_entirely():
    registry = FakeRegistry()
    ensure_registered(exe=EXE, reader=registry.read, writer=registry.write)

    unregister(deleter=registry.delete, value_deleter=registry.delete_value)

    assert rf"{CLASSES}\{PROG_ID}\shell\open\command" in registry.deleted
    assert rf"{CLASSES}\SystemFileAssociations\.hwp\shell\{shell_menu.VERB}" in registry.deleted


def test_a_half_written_registration_is_finished_on_the_next_run():
    """등록 도중 터지면 다음 실행이 마저 채워야 한다.

    명령 키는 **두 번째**로 써진다. 그 뒤 항목에서 실패하면 명령 키는 이미 맞는 값이라,
    "명령 키만" 보고 조기 반환하면 메뉴 절반이 빠진 상태가 **영구히 고착**된다.
    """
    registry = FakeRegistry()
    calls = []

    def flaky(key_path, value_name, value):
        calls.append(key_path)
        if len(calls) > 2:
            raise OSError("여기서 터진다")
        registry.write(key_path, value_name, value)

    ensure_registered(exe=EXE, reader=registry.read, writer=flaky)
    assert registry.read(rf"{CLASSES}\{PROG_ID}\shell\open\command", "") == command_line(EXE)
    assert registry.read(rf"{CLASSES}\.hwp\OpenWithProgids", PROG_ID) is None

    ensure_registered(exe=EXE, reader=registry.read, writer=registry.write)

    for key_path, value_name, value in desired_entries(EXE):
        assert registry.read(key_path, value_name) == value


@pytest.mark.parametrize("ext", EXTENSIONS)
def test_unregister_never_deletes_the_extension_key_itself(ext):
    """확장자 키(`.hwp`)는 우리가 만든 것이 아닐 수 있다 — 지우면 한글 연결이 날아간다.

    이 불변식은 Windows 전용 테스트에만 있었는데, 그러면 macOS 개발 중에 보호를 지워도
    아무 테스트도 안 깨진다(변이 검사로 실제로 빠져나갔다). 여기서도 건다.
    """
    registry = FakeRegistry()
    ensure_registered(exe=EXE, reader=registry.read, writer=registry.write)

    unregister(deleter=registry.delete, value_deleter=registry.delete_value)

    assert rf"{CLASSES}\{ext}" not in registry.deleted
    assert rf"{CLASSES}\SystemFileAssociations\{ext}" not in registry.deleted
    assert CLASSES not in registry.deleted
