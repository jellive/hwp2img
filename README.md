# hwp2img

어머니가 받은 한글(.hwp) 문서를 카카오톡으로 바로 보낼 수 있는 이미지로 바꿔주는 프로그램.

Windows 머신에서 이어서 작업한다면 **[docs/WINDOWS-HANDOFF.md](docs/WINDOWS-HANDOFF.md)를
먼저 읽어라** — 지금 뭐가 끝났고 뭐가 안 끝났는지, 다음에 뭐부터 확인해야 하는지 정리돼 있다.

## 사용법 (어머니용)

1. 바탕화면의 "한글 사진으로 바꾸기" 아이콘 위로 변환하고 싶은 .hwp 파일을 끌어다 놓는다.
2. 잠시 기다리면 원본 파일이 있던 바로 그 폴더가 자동으로 열리고, 방금 만들어진 사진이 선택된 채로 보인다.
3. 카카오톡 채팅창에 Ctrl+V 로 바로 붙여넣거나, 열린 폴더에서 선택된 그 사진을 첨부해서 보낸다.
   (다른 프로그램이 클립보드를 쓰고 있어서 복사가 안 됐을 때는 안내창이 뜬다 — 그때는 열린 폴더에서 사진을 직접 골라 보낸다.)

## 개발 환경 설정 (Mac/Windows 공통 — 순수 로직 테스트)

    python3 -m venv .venv
    source .venv/bin/activate  # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    pytest

`pyhwpx`/`pywin32`는 Windows 전용이라 Mac에서는 설치되지 않는다(`requirements.txt`의 플랫폼 마커).
`hwp_to_pdf.py`/`output.py`의 Windows 전용 함수는 의존성 주입으로 테스트되므로 Mac에서도 전체
테스트 스위트가 통과해야 한다.

## Windows 실기기 빌드 (반드시 Windows + 한컴오피스 설치 환경에서)

    pip install -r requirements.txt
    pip install pyinstaller
    pyinstaller --onefile --noconsole --collect-all pyhwpx --name "hwp2img" src/run.py

결과물: `dist/hwp2img.exe`

- `--collect-all pyhwpx` — pyhwpx 는 보안승인모듈 `FilePathCheckerModule.dll` 과 폰트 데이터를
  패키지 안에 들고 있는데, 이건 import 분석만으로는 잡히지 않아서 명시적으로 수집해야 한다.
  빠뜨리면 개발 PC 에서는 되고 어머니 PC 에서만 보안 팝업/실행 실패가 난다.
  이 dll 을 레지스트리에 등록하는 건 `hwp2img/security.py` 가 직접 한다 — pyhwpx 의 자동
  등록은 `pip` 실행에 의존해서 얼린 exe 에서 항상 실패한다(계획 문서 Task 9 참고).
- `--name` 은 ASCII 로 둔다 — 비-ASCII 이름으로 직접 빌드하면 일부 Windows 환경에서
  PyInstaller 부트로더가 실패한 전례가 있다. 한글 이름이 필요하면 빌드한 뒤
  `dist/hwp2img.exe` 를 가리키는 바탕화면 바로가기를 "한글 사진으로 바꾸기" 로 만들어 준다
  (또는 .exe 를 그 이름으로 복사한다).

## 최초 1회 배포 체크리스트

- [ ] 위 명령으로 만든 .exe 를 어머니 PC 바탕화면에 복사하고, "한글 사진으로 바꾸기" 라는
      이름의 바로가기를 만들어 준다
- [ ] 실제 hwp 문서 하나로 드래그앤드롭 테스트 — 보안 팝업이 뜨는지 확인
      (pyhwpx 가 `Hwp(register_module=True)` 기본값으로 자동 등록하므로 이론상 안 떠야 함 — 실제로 확인할 것)
- [ ] 변환된 사진이 원본 .hwp 파일과 같은 폴더에 생기고, 탐색기가 그 사진을 선택한 채로 열리는지 확인
      (결과 이미지가 원본과 비교해 읽을 수 있는 품질인지도 함께 확인)
- [ ] 카카오톡에 Ctrl+V 로 붙여넣기가 실제로 되는지 확인
