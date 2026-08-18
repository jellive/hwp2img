class Hwp2ImgError(Exception):
    user_message = "변환 중 문제가 생겼어요."


class UnsupportedFileError(Hwp2ImgError):
    def __init__(self, path: str):
        super().__init__(f"unsupported file: {path}")
        self.user_message = "한글 문서 파일(.hwp, .hwpx)만 변환할 수 있어요."


class HwpNotInstalledError(Hwp2ImgError):
    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.user_message = "한컴오피스 한글을 찾을 수 없어요. 컴퓨터에 한글이 설치되어 있는지 확인해 주세요."


class HwpAutomationError(Hwp2ImgError):
    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.user_message = "한글 문서를 여는 중 문제가 생겼어요. 파일이 손상되지 않았는지 확인해 주세요."


class HwpTimeoutError(Hwp2ImgError):
    def __init__(self, detail: str = ""):
        super().__init__(detail)
        self.user_message = "이 파일은 변환할 수 없어요. 암호가 걸려 있거나 문서에 문제가 있을 수 있어요."
