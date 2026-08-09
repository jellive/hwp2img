import os

from hwp2img import security
from hwp2img.security import DLL_NAME, ensure_security_module, find_security_dll


def test_find_security_dll_returns_first_directory_that_has_it():
    found = find_security_dll(
        dirs=["/없는곳", "/있는곳", "/또있는곳"],
        exists=lambda p: p in (
            os.path.join("/있는곳", DLL_NAME),
            os.path.join("/또있는곳", DLL_NAME),
        ),
    )

    assert found == os.path.join("/있는곳", DLL_NAME)


def test_find_security_dll_returns_none_when_nowhere():
    assert find_security_dll(dirs=["/없는곳"], exists=lambda p: False) is None


def test_ensure_security_module_writes_found_dll_path():
    written = []

    ok = ensure_security_module(
        reader=lambda: None,
        writer=written.append,
        exists=lambda p: p == os.path.join("/패키지", DLL_NAME),
        dll_path=None,
    )

    # dll_path 를 안 줬으므로 candidate_dirs() 를 탐색한다. 그 경로에는 dll 이 없으니
    # 등록할 것도 없어야 한다 — 없는 dll 을 레지스트리에 적으면 한글이 조용히 무시한다.
    assert ok is False
    assert written == []


def test_ensure_security_module_writes_explicit_dll_path():
    written = []

    ok = ensure_security_module(
        dll_path=r"C:\앱\FilePathCheckerModule.dll",
        reader=lambda: None,
        writer=written.append,
        exists=lambda p: False,
    )

    assert ok is True
    assert written == [r"C:\앱\FilePathCheckerModule.dll"]


def test_ensure_security_module_skips_write_when_already_registered():
    written = []

    ok = ensure_security_module(
        reader=lambda: r"C:\기존\FilePathCheckerModule.dll",
        writer=written.append,
        exists=lambda p: p == r"C:\기존\FilePathCheckerModule.dll",
    )

    assert ok is True
    assert written == []


def test_ensure_security_module_rewrites_when_registered_path_is_gone():
    """예전에 등록된 경로가 지워졌으면(가상환경 삭제 등) 다시 써야 한다."""
    written = []

    ok = ensure_security_module(
        dll_path=r"C:\새경로\FilePathCheckerModule.dll",
        reader=lambda: r"C:\지워진곳\FilePathCheckerModule.dll",
        writer=written.append,
        exists=lambda p: False,
    )

    assert ok is True
    assert written == [r"C:\새경로\FilePathCheckerModule.dll"]


def test_ensure_security_module_never_raises_when_registry_write_fails():
    """레지스트리 쓰기가 막혀도(정책, 권한) 변환 자체는 계속돼야 한다."""

    def exploding_writer(path):
        raise PermissionError("레지스트리 쓰기 거부")

    ok = ensure_security_module(
        dll_path=r"C:\앱\FilePathCheckerModule.dll",
        reader=lambda: None,
        writer=exploding_writer,
        exists=lambda p: False,
    )

    assert ok is False


def test_ensure_security_module_never_raises_when_registry_read_fails():
    def exploding_reader():
        raise OSError("레지스트리 읽기 실패")

    assert (
        ensure_security_module(
            dll_path=r"C:\앱\FilePathCheckerModule.dll",
            reader=exploding_reader,
            writer=lambda p: None,
            exists=lambda p: False,
        )
        is False
    )


def test_candidate_dirs_prefers_pyinstaller_bundle(monkeypatch):
    """얼린 exe 안에서는 번들에 들어온 dll 을 먼저 봐야 한다 —
    개발 PC 의 pyhwpx 경로는 어머니 PC 에 존재하지 않는다."""
    monkeypatch.setattr(security.sys, "_MEIPASS", r"C:\Temp\_MEI123", raising=False)

    dirs = security.candidate_dirs()

    assert dirs[0] == os.path.join(r"C:\Temp\_MEI123", "pyhwpx")
    assert dirs[1] == r"C:\Temp\_MEI123"
