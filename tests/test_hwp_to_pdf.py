import sys
import types

import pytest

from hwp2img.errors import HwpAutomationError, HwpNotInstalledError
from hwp2img.hwp_to_pdf import convert, create_hwp


class FakeHwp:
    def __init__(
        self,
        open_result=True,
        save_result=True,
        write_file=True,
        quit_raises=False,
        open_raises=False,
        save_raises=False,
    ):
        self.calls = []
        self._open_result = open_result
        self._save_result = save_result
        self._write_file = write_file
        self._quit_raises = quit_raises
        self._open_raises = open_raises
        self._save_raises = save_raises

    def open(self, filename):
        self.calls.append(("open", filename))
        if self._open_raises:
            raise RuntimeError("0x80040154 암호로 보호된 문서입니다")
        return self._open_result

    def save_as(self, path, format="HWP"):
        self.calls.append(("save_as", path, format))
        if self._save_raises:
            raise RuntimeError("디스크 쓰기 실패")
        # 진짜 한글은 save_as 가 True 면 파일을 만든다. convert() 의 사후 검사가
        # 의미를 가지려면 fake 도 그 계약을 지켜야 한다.
        if self._save_result and self._write_file:
            with open(path, "wb") as f:
                f.write(b"fake-pdf-bytes")
        return self._save_result

    def quit(self, save=False):
        self.calls.append(("quit", save))
        if self._quit_raises:
            raise RuntimeError("COM 객체가 이미 죽어 있음")


def test_convert_happy_path_opens_saves_and_quits(tmp_path):
    hwp = FakeHwp()
    pdf_path = str(tmp_path / "출력.pdf")

    convert(hwp, "문서.hwp", pdf_path)

    assert hwp.calls == [
        ("open", "문서.hwp"),
        ("save_as", pdf_path, "PDF"),
        ("quit", False),
    ]


def test_convert_raises_when_open_fails_but_still_quits(tmp_path):
    hwp = FakeHwp(open_result=False)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", str(tmp_path / "출력.pdf"))

    assert ("quit", False) in hwp.calls


def test_convert_raises_when_save_fails_but_still_quits(tmp_path):
    hwp = FakeHwp(save_result=False)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", str(tmp_path / "출력.pdf"))

    assert ("quit", False) in hwp.calls


def test_convert_raises_when_save_as_reports_success_but_writes_nothing(tmp_path):
    """COM 자동화는 True 를 돌려주고도 파일을 안 만들 수 있다 — 그러면 사용자는
    '성공했다'는 안내를 받고 빈손이 된다."""
    hwp = FakeHwp(write_file=False)
    pdf_path = str(tmp_path / "출력.pdf")

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", pdf_path)


def test_convert_raises_when_pdf_is_empty(tmp_path):
    pdf_path = tmp_path / "출력.pdf"
    pdf_path.write_bytes(b"")
    hwp = FakeHwp(write_file=False)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", str(pdf_path))


def test_convert_absorbs_quit_failure_when_conversion_succeeded(tmp_path):
    """quit 이 던진 예외가 성공한 변환을 실패로 뒤바꾸면 안 된다."""
    hwp = FakeHwp(quit_raises=True)
    pdf_path = str(tmp_path / "출력.pdf")

    convert(hwp, "문서.hwp", pdf_path)  # 예외가 새어 나오면 이 줄에서 실패한다

    assert ("quit", False) in hwp.calls


def test_convert_reports_the_real_error_when_quit_also_fails(tmp_path):
    """open 실패가 진짜 원인인데 quit 예외가 그걸 덮어쓰면 원인을 못 찾는다."""
    hwp = FakeHwp(open_result=False, quit_raises=True)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", str(tmp_path / "출력.pdf"))


def test_convert_raises_hwp_automation_error_when_open_itself_raises(tmp_path):
    """False 반환뿐 아니라 open() 자체가 예외를 던지는 경우도 있다 —
    암호 걸린 문서·파일 잠김 등은 COM 이 bool 이 아니라 예외로 실패를 알린다.
    이걸 못 잡으면 예외가 main() 의 일반 캐치올까지 새어나가 '예상하지 못한 문제'라는
    막연한 안내로 가버린다."""
    hwp = FakeHwp(open_raises=True)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", str(tmp_path / "출력.pdf"))

    assert ("quit", False) in hwp.calls


def test_convert_raises_hwp_automation_error_when_save_as_itself_raises(tmp_path):
    hwp = FakeHwp(save_raises=True)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", str(tmp_path / "출력.pdf"))

    assert ("quit", False) in hwp.calls


def test_create_hwp_forces_a_fresh_hangul_instance(monkeypatch):
    """new=True 가 빠지면 pyhwpx 가 이미 떠 있는 한글에 붙어서, 사용자가 열어둔
    미저장 문서를 우리가 숨기고 quit(save=False) 로 날려버린다."""
    captured = {}

    class FakeHwpCom:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_pyhwpx = types.ModuleType("pyhwpx")
    fake_pyhwpx.Hwp = FakeHwpCom
    monkeypatch.setitem(sys.modules, "pyhwpx", fake_pyhwpx)

    create_hwp()

    assert captured["new"] is True
    assert captured["visible"] is False


def test_create_hwp_raises_hwp_not_installed_when_com_creation_fails(monkeypatch):
    class ExplodingHwp:
        def __init__(self, **kwargs):
            raise OSError("0x80040154 클래스가 등록되어 있지 않습니다")

    fake_pyhwpx = types.ModuleType("pyhwpx")
    fake_pyhwpx.Hwp = ExplodingHwp
    monkeypatch.setitem(sys.modules, "pyhwpx", fake_pyhwpx)

    with pytest.raises(HwpNotInstalledError):
        create_hwp()
