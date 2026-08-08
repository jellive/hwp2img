# hwp2img

어머니가 받은 한글(.hwp) 문서를 카카오톡으로 바로 보낼 수 있는 이미지로 바꿔주는 프로그램.

## 사용법 (어머니용)

1. 바탕화면의 "한글 사진으로 바꾸기" 아이콘 위로 변환하고 싶은 .hwp 파일을 끌어다 놓는다.
2. 잠시 기다리면 "변환된사진" 폴더가 자동으로 열린다.
3. 그 폴더의 사진을 카카오톡에 첨부해서 보내거나, 카카오톡 채팅창에 Ctrl+V 로 바로 붙여넣는다.

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
    pyinstaller --onefile --noconsole --name "한글사진으로바꾸기" src/run.py

결과물: `dist/한글사진으로바꾸기.exe`

## 최초 1회 배포 체크리스트

- [ ] 위 명령으로 만든 .exe 를 어머니 PC 바탕화면에 복사
- [ ] 실제 hwp 문서 하나로 드래그앤드롭 테스트 — 보안 팝업이 뜨는지 확인
      (pyhwpx 가 `Hwp(register_module=True)` 기본값으로 자동 등록하므로 이론상 안 떠야 함 — 실제로 확인할 것)
- [ ] "변환된사진" 폴더가 자동으로 열리는지, 결과 이미지가 원본과 비교해 읽을 수 있는 품질인지 확인
- [ ] 카카오톡에 Ctrl+V 로 붙여넣기가 실제로 되는지 확인
