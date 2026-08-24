# Windows 세션 인수인계

이 문서는 Mac에서 여기까지 진행한 뒤, **Windows의 맨몸 Claude Code**(스킬·플러그인 없음,
프롬프트만 있음)로 이어서 작업할 때 읽는 문서다. 다른 건 몰라도 이것만은 지키고 시작할 것:

> **`docs/superpowers/plans/2026-08-08-hwp2img.md`가 "REQUIRED SUB-SKILL:
> superpowers:subagent-driven-development" 라고 적어놓은 줄은 무시해라.** 그건 Mac
> 세션에 깔린 플러그인 이름이고, 여기엔 없다. 그 문서는 여전히 **가장 정확한 작업 기록**이니
> 내용은 그대로 신뢰하되, "이 스킬을 불러라" 같은 지시문만 읽고 넘겨라.

## 지금 상태 (한 줄 요약)

**코드는 완성됐다. 남은 건 전부 Windows 실행 검증이다.** Mac에서는 이 이상 구현할 게 없다 —
TODO·스텁 0건, 테스트 56개 전부 통과, 커버리지 92%(나머지 8%는 구조적으로 Mac에서 못 도는
Windows 전용 코드). Task 1-8(변환 파이프라인 전체)은 끝났고 실제 문서로 한 번 확인도 됐다.
**Task 9(실기기 검증)가 미완**이고, 그 안에서도 특히 최근에 추가된 `watchdog.py`(타임아웃·
프로세스 격리)는 **Windows에서 단 한 번도 안 돌려봤다.**

## 0. 시작 전에 — 환경 설정

```bash
git clone https://github.com/jellive/hwp2img.git
cd hwp2img
```

**Python은 3.11.x를 써라.** `.python-version`이 그렇게 박혀 있다 — 실제로 검증된 조합이
Windows 11 Pro + 한컴오피스 한글 9.0.0.562 + **Python 3.11**이었고(2026-08-09 실측),
`pyhwpx`/`pywin32`가 그보다 새 Python에서도 되는지는 아무도 확인한 적이 없다. `pyproject.toml`의
`requires-python = ">=3.11"`은 하한선만 걸어놔서 최신 Python을 그냥 깔면 조용히 더 넓은
버전을 쓰게 된다 — 굳이 그 변수를 새로 만들지 마라.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

**`56 passed`가 안 나오면 그 자리에서 멈춰라.** 그 밑에서 뭘 더 하든 신뢰할 수 없다. 이 56개는
Mac에서도 통과하던 것들이라, Windows에서 실패한다면 그 자체가 환경 차이를 알려주는 신호다.

## 1. 지금 당장 해야 하는 것 — 순서대로

원본은 `docs/superpowers/plans/2026-08-08-hwp2img.md:905-984`(Task 9 전문)이다. 여기 있는 건
그걸 실행 순서로 다시 정리한 것 — **차이가 보이면 원본을 믿어라.**

### 1-1. 빌드부터

```powershell
pip install pyinstaller
pyinstaller --onefile --noconsole --collect-all pyhwpx --name "hwp2img" src/run.py
```

결과물: `dist/hwp2img.exe`. **`--collect-all pyhwpx`를 빼지 마라** — 이게 없으면 개발 PC에서는
되는데 어머니 PC에서만 보안 팝업/실행 실패가 난다(README.md:31-33). `--name`도 ASCII로 유지
— 비-ASCII 이름으로 직접 빌드했다가 PyInstaller 부트로더가 실패한 전례가 있다(README.md:36-37).
한글 이름 바로가기는 exe를 가리키는 바탕화면 바로가기로 따로 만든다.

### 1-2. `watchdog.py` 5개 항목 — 이게 제일 중요하다

**이 프로그램의 제1 제약은 "어머니가 열어둔 한글 문서를 절대 죽이지 않는다"다.** 이걸
Windows에서 확인 안 하고 넘어가면 안 된다. `src/hwp2img/watchdog.py:1-32`의 독스트링을
먼저 읽어라 — 왜 "새로 생긴 PID를 죽인다"는 처음 구현을 버렸는지(PID 재사용 문제로 어머니의
멀쩡한 한글을 죽일 수 있어서) 설명돼 있다. codex 크로스모델 리뷰 2회로 BLOCKER 1건 + HIGH
1건 + MEDIUM 2건을 잡아 고쳤고 코드 자체는 통과했지만, **Windows 실행으로는 한 번도 검증
안 됐다.**

1. **한글을 이미 띄운 상태에서, 별도로 암호 걸린(또는 무한정 멈추는) hwp를 변환기에 드롭.**
   타임아웃 뒤에도 먼저 띄운 한글 창·문서가 그대로 살아있는지 **작업 관리자에서 PID를 직접
   비교**해서 확인해라. 이게 이 기능 전체의 하드 제약이다 — 여기서 실패하면 나머지 항목은
   의미 없다.
2. **실제 암호 걸린 hwp로 변환 시도.** `DEFAULT_TIMEOUT_SECONDS`(30초, `watchdog.py`에서
   찾을 수 있다) 안에 안내창("이 파일은 변환할 수 없어요...")이 뜨는지, 그 사이 나머지 OS는
   정상 동작하는지. (Mac에서 이 한글 버전으로는 암호 문서를 만들 방법이 없어서 이거 하나가
   Task 9 전체에서 유일하게 아직 아무도 시도 못 해본 케이스다.)
3. **타임아웃 후 작업 관리자에서 `Hwp.exe`가 실제로 사라지는지.** 좀비로 안 남는지.
4. **`multiprocessing.freeze_support()`가 onefile exe에서 실제로 자식 프로세스 spawn을
   가능하게 하는지.** codex 2차 리뷰는 "최신 PyInstaller는 spawn worker가 이미 풀린
   `_MEIxxxx`를 재사용한다"고 확인했지만 이 exe로 직접 검증한 적은 없다. 자식이 `python.exe`를
   새로 찾으려다 실패하는 형태의 에러가 없는지 볼 것.
5. **페이지 많은 문서 기준 30초가 충분한지.** 정상 변환인데 타임아웃으로 오판되면 그것도
   실패다. 30초에 근접하면 `watchdog.py`의 `DEFAULT_TIMEOUT_SECONDS`를 올려라.

**이 5개가 전부 끝나기 전에는 어머니 PC에 절대 올리지 마라.** (Jell 결정, 2026-08-18)

### 1-3. 그 다음 — README의 "최초 1회 배포 체크리스트"

`watchdog.py` 5개 항목까지 끝난 뒤에만 진행. `README.md:41-49`에 그대로 있다 — 실제 hwp로
드래그앤드롭, 보안 팝업 안 뜨는지, 결과 사진이 원본 폴더에 선택된 채로 열리는지, 카카오톡에
Ctrl+V 되는지.

## 2. 알아둘 것 — 건드리지 말아야 할 부분

- **`output.py`의 `open_in_explorer`가 문자열 커맨드를 쓰는 이유.** argv 리스트로 바꾸고 싶은
  유혹이 들 수 있는데, 이미 두 번 시도해서 둘 다 실패한 자리다 — `subprocess`의
  `list2cmdline`이 `/select` 플래그 자체를 다시 따옴표로 감싸서 깨진다. 지금 문자열 형태가
  유일하게 동작하는 형태다. "리팩터링"하지 마라.
- **`Hwp.exe`를 PID로 강제 종료하는 코드를 다시 넣지 마라.** 위 1-2절에서 설명한 그 이유 —
  PID 재사용 때문에 어머니의 멀쩡한 한글을 죽일 수 있다. 고아 프로세스가 실제로 문제가
  되면(재부팅 없이 메모리를 계속 먹는 게 확인되면), `watchdog.py:30-31`이 이미 정답을 적어놨다
  — 윈도우 핸들에서 `GetWindowThreadProcessId`로 PID를 얻고 `OpenProcess` 핸들을 쥔 채
  그 핸들로 종료하는 것. PID 스냅샷 비교가 아니라.
- **손상된 hwp가 에러 없이 "성공"으로 처리되는 것**은 알려진 상태다(치명적이진 않고, 알아볼
  수 없는 PNG가 나올 뿐). 고칠 거면 먼저 물어봐라 — 지금은 의도적으로 남겨둔 것이다.
- **자동 업데이트·배치(여러 파일 동시) 변환·GUI 설정 화면·macOS/Linux 지원**은 전부 스코프
  아웃이다(`docs/superpowers/specs/2026-08-08-hwp2img-design.md`). 필요해 보여도 먼저
  Jell한테 물어봐라 — 어머니 한 명이 쓰는 프로그램이라 "있으면 좋은 것"의 기준이 보통과 다르다.

## 3. 도구가 없을 때 검증하는 법

여기엔 codex·cursor 같은 교차검증 레인도, `superpowers:test-driven-development` 같은
강제 워크플로도 없다. 대신 이렇게 해라:

1. **코드를 고치기 전에 `pytest`를 돌려서 56개 통과를 기준선으로 잡아라.**
2. **고친 뒤 다시 `pytest`.** 실패한 테스트가 있으면 그걸 고치기 전엔 다음으로 안 넘어간다.
3. **Windows 전용 코드(COM·클립보드·레지스트리·watchdog)를 고쳤다면, 유닛 테스트 통과만으로
   끝났다고 하지 마라.** 이 프로젝트의 유닛 테스트는 전부 페이크 객체로 Windows API를
   흉내낸 것뿐이다(`tests/`의 `FakeHwp`, `FakeClipboard`, 페이크 `winreg` 등) — 진짜 검증은
   위 1절의 실기기 체크리스트뿐이다.
4. **자기 diff를 직접 한 번 더 읽어라.** 여긴 두 번째 모델이 리뷰해줄 수 없으니, 최소한
   "이 변경이 왜 필요했는지"를 한 문장으로 설명 못 하면 되돌려라.
5. 다 끝나면 이 저장소 관례대로 커밋한다 — `docs/superpowers/plans/2026-08-08-hwp2img.md`에
   실행 기록을 남기는 방식(위 Task 9 절의 "실행 기록: 2026-08-09..." 같은 형태)을 그대로
   따라가면 다음 사람(또는 다음 Mac 세션)이 뭐가 확인됐는지 바로 안다.

## 4. Mac 세션에 다시 알려주고 싶으면

지금은 두 세션이 실시간으로 안 이어져 있다. 결과는 (a) 위 3-5번처럼 plan 문서에 실행 기록으로
남기고 git commit/push 해두거나, (b) 다음에 Mac Claude Code 세션을 열 때 직접 말해주면 된다.
둘 다 안 하면 다음 Mac 세션은 이 문서가 쓰인 시점(2026-08-24)에서 아무것도 안 바뀐 걸로 안다.
