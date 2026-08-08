import pytest

from hwp2img.errors import HwpAutomationError
from hwp2img.hwp_to_pdf import convert


class FakeHwp:
    def __init__(self, open_result=True, save_result=True):
        self.calls = []
        self._open_result = open_result
        self._save_result = save_result

    def open(self, filename):
        self.calls.append(("open", filename))
        return self._open_result

    def save_as(self, path, format="HWP"):
        self.calls.append(("save_as", path, format))
        return self._save_result

    def quit(self, save=False):
        self.calls.append(("quit", save))


def test_convert_happy_path_opens_saves_and_quits():
    hwp = FakeHwp()

    convert(hwp, "문서.hwp", "출력.pdf")

    assert hwp.calls == [
        ("open", "문서.hwp"),
        ("save_as", "출력.pdf", "PDF"),
        ("quit", False),
    ]


def test_convert_raises_when_open_fails_but_still_quits():
    hwp = FakeHwp(open_result=False)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", "출력.pdf")

    assert ("quit", False) in hwp.calls


def test_convert_raises_when_save_fails_but_still_quits():
    hwp = FakeHwp(save_result=False)

    with pytest.raises(HwpAutomationError):
        convert(hwp, "문서.hwp", "출력.pdf")

    assert ("quit", False) in hwp.calls
