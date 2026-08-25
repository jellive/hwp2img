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


---

# 추가분 — 드롭존 창 (2026-08-24)

인자 없이 실행했을 때(아이콘 더블클릭) 뜨는 **드롭존 창**이 추가됐다. 설계 근거와
크로스모델 레인이 무엇을 잡았는지는 `docs/superpowers/plans/2026-08-24-dropzone.md`.

**기존 "아이콘 위에 드롭" 경로는 손대지 않았다** — argv 가 있으면 `cli.main` 이 창 코드
근처에도 안 간다(`_launch_dropzone` 은 argv 가 빌 때만 불리고, `tkinter` 는 그 안에서
import 된다). 즉 이 변경으로 **기존 경로가 새로 깨질 자리는 없다.**

## Mac 에서 끝난 것

- 테스트 **95개 통과** (기존 56 + 신규 39). 변이 검사 **22종을 전부 잡는다**
  (책임 코드를 부수면 해당 테스트가 실제로 FAIL 한다 — 통과만으로는 증거가 아니라서 확인했다)
- 판정·상태 전이·경로 추출은 전부 Mac 에서 검증됨
- ★**진짜 Tk 창으로 `_build_window` 전체를 돌려 봤다** (`tests/test_dropzone_window.py`).
  위젯 생성·`WM_DELETE_WINDOW` 가로채기·`root.after` 마샬링·파일 고르기 버튼·`_TkView`·
  `launch()` 의 메인 루프와 정리 경로까지 실제로 실행된다. **위젯 인자 오타를 실제로 잡는 것**을
  변이 검사로 확인했다(`justify`→`justfy`, `text`→`txt` 둘 다 FAIL 남).
  → Windows 에서 "창이 아예 안 뜬다" 가 나온다면 원인은 **Tk 배선이 아니라 패키징**이다.

## Windows 에서 **반드시** 확인해야 하는 것 (전부 미검증)

1. **더블클릭 → 창이 뜨는가.** Tk 배선 자체는 Mac 에서 실제 창으로 확인됐으므로, 여기서
   안 뜨면 **PyInstaller 가 tcl/tk 를 수집했는지**부터 본다(내장 훅이 하게 돼 있다).
   창 띄우기가 통째로 터지면 `_launch_dropzone` 이 잡아 로그 + 안내창을 낸다 —
   즉 **무음 종료는 아니어야 한다.** 무음이면 그 예외 처리 앞단에서 죽은 것이다.
   ★Tk 버전이 다르다: Mac 검증은 **Tk 9.0**, Windows 파이썬 3.11 은 **8.6** 이다.
2. **창 안으로 드롭이 먹는가.** `dnd.Win32DropHook` 이 `root.winfo_id()` 에 후킹하는데,
   Tk 는 클라이언트 창과 프레임 창이 갈린다. 드롭이 안 오면 **`root.wm_frame()` 의 핸들
   (16진 문자열 → `int(..., 16)`)로 바꿔서** 다시 시도해 볼 것. 이게 첫 번째 의심 지점이다.
3. **드롭이 끝내 안 되면** — 버튼 폴백이 있으니 앱은 못 쓰게 되지 않는다. 그 상태로도 배포 가능하다.
   (`attach()` 는 실패해도 예외를 안 던지고 `False` 만 돌려준다. 그게 의도다.)
4. **연속 2~3회 변환 후 작업관리자에서 `Hwp.exe` 개수를 볼 것.** `watchdog.py` docstring 이
   "자식이 띄운 한글이 백그라운드에 남을 수 있다" 고 적어 뒀는데, 지금까지는 1회 변환 후 앱이
   즉시 종료돼서 문제가 안 됐다. **창이 상주하면 이게 처음으로 문제가 될 수 있는 축이다.**
   쌓이면 그때 `watchdog.py` 의 핸들 기반 종료를 Windows 에서 작성·검증해 넣는다.
5. 변환 중 창을 닫아 보기 — 프로세스가 남지 않고 깨끗이 끝나는지.

## 별건 (이번 변경과 무관 — 손대지 않았다)

`.venv` 가 **Python 3.14.6** 인데 `.python-version` 과 이 문서는 **3.11 이 유일하게 검증된
조합**이라고 못박고 있다. Mac 개발 환경의 드리프트다. Windows 에서는 위 "0. 시작 전에" 절대로
3.11 을 쓸 것.


---

# 추가분 — CI / GitHub Release (2026-08-24)

`.github/workflows/` 가 생겼다. 설계 근거와 레인 지적 처리는
`docs/superpowers/plans/2026-08-24-release-ci.md`.

## 이걸로 **처음** 생기는 것

**`windows-latest` 러너에서 pytest 가 돈다.** 이 프로젝트는 지금까지 Windows 에서
테스트를 단 한 번도 돌려본 적이 없다 — 개발이 Mac 이고 실행은 Windows 전용이라 그 간극이
통째로 미검증이었다. main push / PR 마다 이제 그 표면이 열린다.

**단 러너에는 한컴오피스가 없다.** 그래서 COM 경계 바깥만 돈다. 아래는 여전히 실기기 전용이다:
실제 .hwp → PDF 변환 · 보안승인모듈 레지스트리 등록 · 얼린 exe 의 실행 · 드롭 후킹.

## ✅ CI 결과 — **Windows·macOS 양쪽 초록** (2026-08-24, 4차 실행)

`test.yml` 이 `windows-latest` · `macos-latest` 에서 **95개 전부 통과**한다.
이 프로젝트가 Windows 에서 테스트를 통과한 것은 이번이 처음이다.

**특히 Tk 스모크 테스트 10개가 Windows 에서 실제로 돈다** — 창 생성·위젯·
`WM_DELETE_WINDOW` 가로채기·`root.after` 마샬링·파일 고르기 버튼이 Windows Tk 에서
동작한다는 뜻이다. 즉 실기기에서 창이 안 뜨면 원인은 **Tk 배선이 아니라 PyInstaller 패키징**이다.

**여전히 열린 것:** 실제 .hwp → PDF 변환(한글 COM) · 보안승인모듈 등록 · 얼린 exe 실행 ·
탐색기에서 창으로 드롭. 러너에 한컴오피스가 없어서 CI 가 못 본다.

## v0.3.0 — 탐색기 우클릭 메뉴 (2026-08-25)

Jell 결정: 어머니가 **파일을 끌고 가지 않아도 되게** 한다. 어머니 PC 는 **Windows 11**.

**Win11 이 설계를 갈랐다 (웹 확인):** 평범한 shell verb 는 Win11 축약 메뉴에서 **무조건
"더 많은 옵션 표시" 아래**로 간다. 상단에 뜨려면 `IExplorerCommand` + app identity(sparse
package) + **코드 서명**이 필요한데 우리한테 없다. 상단 경로는 **"프로그램에서 열기"
서브메뉴** 하나뿐이고 그 정식 키가 `OpenWithProgids` 다. **두 경로를 다 등록했다** —
레지스트리 값 3개 더 쓰는 비용이고, 이 프로젝트에서 제일 비싼 것은 어머니 PC 왕복이다.

⚠️ **정직하게: Win11 에선 "우클릭 한 번"이 아니라 3클릭이다.** 줄어드는 것은 클릭 수가 아니라
**드래그라는 손 기술**과 창 두 개를 동시에 띄우는 일이다.

전부 `HKCU\Software\Classes` 라 **관리자 권한이 필요 없다.** 설치 프로그램도 없다 —
`cli.main()` 이 매 실행마다 자가 등록·자가 치유한다(exe 를 옮기거나 새 버전으로 바꿔도 따라온다).

**CI 가 실제로 보는 것:** `tests/test_shell_menu_windows.py` 가 **진짜 `winreg`** 로
테스트 전용 하위 트리(`Software\hwp2img_test_<pid>\Classes`)에 쓰고 읽고 지운다.
가짜 레지스트리만 썼으면 그 경계는 검증 안 된 것이다 — v0.2.1 의 `argtypes` 결함이
가짜 `shell32` 뒤에서 테스트 95개를 초록으로 유지한 채 숨어 있었던 것과 같은 함정이다.

**🔴 CI 가 못 보는 것 (실기기 전용 게이트):**
- 메뉴가 **탐색기에 실제로 보이는가.** 레지스트리에 값이 있는 것과 메뉴에 뜨는 것은 다르다.
- Win11 에서 **[프로그램에서 열기]** 안에 뜨는가, **[더 많은 옵션 표시]** 안에 뜨는가.
  → 어느 쪽인지 확인해서 README 의 안내 순서를 그쪽으로 맞출 것.
- 우클릭으로 넘어온 `"%1"` 인용이 **띄어쓰기 든 파일명**에서 실제로 한 덩어리로 오는가.
  (틀리면 `cli.main` 의 `len(argv) > 1` 분기가 "한 번에 한 개씩" 으로 거부한다 —
  **공백 든 파일만 조용히 실패**해서 재현 정보 없이 지원해야 하는 최악의 모양이 된다)
- .hwp **더블클릭이 여전히 한글로 가는가.** 확장자 키의 기본값은 안 건드리지만 실기기 확인 필요.

**롤백:** `python -c "from hwp2img import shell_menu; shell_menu.unregister()"` — 또는
`HKCU\Software\Classes` 에서 `hwp2img.convert`, `.hwp\OpenWithProgids\hwp2img.convert`,
`SystemFileAssociations\.hwp(x)\shell\hwp2img` 를 지운다. 확장자 키 자체는 지우지 않는다.

### CI 를 붙여서 잡은 결함 (4라운드)

| # | 무엇 | 어디서만 보였나 |
|---|---|---|
| 1 | `test_watchdog.py` 가 **`fork`** 컨텍스트를 썼다 — 프로덕션은 `spawn` 인데. Windows 엔 `fork` 가 없어 **수집조차 안 됐다** | Windows(수집 에러) + macOS 러너(Abort trap) |
| 2 | `watchdog._kill()` 을 지워도 타임아웃 테스트가 통과했다 — **자식이 정말 죽었는지 아무도 안 봤다** | 변이 검사 |
| 3 | Tk 테스트가 **워커를 두고 창을 부숴** 프로세스를 죽였다. Tcl 패닉은 `abort()` 라 try/except 로 못 잡고, **나중에** 터져서 엉뚱한 테스트가 죽은 것처럼 보였다 | 양쪽 러너 |
| 4 | `write_text()` 에 encoding 미지정 → 러너 로케일이 **cp1252** 라 한글에서 죽었다 | Windows 만 |
| 5 | **Tk root 를 반복 생성/파괴하면 불안정하다** — Windows 4번째 생성에서 `init.tcl` 을 못 찾았다. **가끔만** 그래서 더 나쁘다(직전 실행은 10개 다 통과) | Windows(간헐) + macOS 로컬(세그폴트) |

## ✅ 첫 CI 가 즉시 잡은 것 (2026-08-24)

**`tests/test_watchdog.py` 가 `fork` 컨텍스트를 쓰고 있었다.** 프로덕션은 `spawn` 을 쓰는데도.

- **Windows**: `ValueError: cannot find context for 'fork'` — 이 파일이 **수집조차 안 됐다.**
  하필 watchdog 이 Windows 전용 로직인데 그 테스트가 Windows 에서 한 번도 안 돌고 있었다.
- **macOS 러너**: pymupdf/PIL 이 올라온 프로세스에서 `fork` → `Abort trap: 6`.
  (Mac 로컬에서는 우연히 통과했다.)

→ `spawn` 으로 바꿨다. 이제 **배포되는 것과 같은 메커니즘**을 잰다.
같이 발견: `_kill()` 을 통째로 지워도 타임아웃 테스트가 통과했다 — 예외만 보고 **자식이
정말 죽었는지는 아무도 안 봤다.** 죽은 것을 확인하는 단언을 넣었다(변이 검사로 확인).

**이게 CI 를 붙인 값어치다.** 첫 실행에서 바로 나왔다.

## 릴리즈 실측 (v0.2.0, 2026-08-24) — 예측이 맞았고, 결과는 다르게 나왔다

**`--collect-all pyhwpx` 는 죽지 않았다. 경고만 냈다:**

```
485 WARNING: Failed to collect submodules for 'pyhwpx' because importing 'pyhwpx' raised:
    pywintypes.com_error: (-2147319779, 'Library not registered.', None, None)
```

즉 `core.py:66` 의 `EnsureModule` 이 한글 부재로 실패한다는 예측은 **정확히 맞았는데**,
PyInstaller 가 그걸 치명적으로 취급하지 않고 넘어갔다. 그래서 빌드 형태는 `collect-all`
(손으로 빌드하던 것과 같은 명령)로 기록됐고, 2차 폴백은 안 탔다.

🔴 **그렇다고 손으로 빌드한 것과 같다는 뜻은 아니다.** `collect_all` 이 돌려주는 세 가지
(datas · binaries · hiddenimports) 중 **hiddenimports 수집이 실패**했다. dll·데이터는
들어갔고(빌드 검사에서 `FilePathCheckerModule` 문자열 확인됨) 서브모듈은 정적 분석으로
따라왔을 가능성이 높지만, **한글이 깔린 PC 에서 빌드한 것과 구성이 같다고 단정할 수 없다.**
→ 실기기에서 **변환을 한 번 끝까지** 돌려 봐야 확정된다.

**자산 이름은 ASCII 여야 한다.** 첫 시도에서 `한글-사진으로-바꾸기.exe` 로 올렸더니
릴리즈에 **`-.-.exe`** 로 게시됐다 — 한글이 통째로 하이픈이 됐다. `hwp2img.exe` 로 올리고
이름 바꾸는 안내를 릴리즈 노트에 두는 쪽으로 되돌렸다(README 가 원래 그렇게 지시했다).

## 🔴 첫 CI 결과에서 **반드시** 확인할 것

1. **`windows-latest` 에서 pytest 95개가 통과하나.** 특히 `tests/test_dropzone_window.py`
   (진짜 Tk 창) — GitHub 러너가 대화형 데스크톱 세션이 아니라 Tk 생성이 다를 수 있다.
   실패하면 그 자체가 정보다. **디스플레이 문제면 skip 으로 빠지고, 아니면 빨갛게 뜬다** —
   그 테스트가 그렇게 갈라 놓았다.
2. **`pyhwpx 를 import 할 수 있나` 스텝의 결과.** 이게 이 설계의 최대 미지수다.
   `pyhwpx/core.py:66` 이 **import 시점에** `win32.gencache.EnsureModule("{7D2B6F3C-…}", 0, 1, 0)`
   을 try 없이 부르는데(휠 실측), 그 GUID 는 한글 타입 라이브러리다. 러너에 한글이 없으니
   여기서 죽을 공산이 크다.
   - 죽으면 → 빌드가 `--collect-all` 대신 `--hidden-import + --add-data` 형태로 간다.
     **그 exe 는 지금까지 손으로 만들던 것과 빌드 형태가 다르다.** 실기기에서 특히
     **보안 팝업이 뜨는지**(= `FilePathCheckerModule.dll` 이 제대로 들어갔는지)를 봐야 한다.
   - 안 죽으면 → README 의 그 명령 그대로다.
   - **어느 쪽으로 빌드했는지는 릴리즈 노트에 적힌다.**

## 알려진 한계 (고치지 않기로 한 것)

- **코드 서명 없음** → SmartScreen 경고. 인증서가 유료라 범위 밖이다. 대신 릴리즈 노트와
  README 에 "[추가 정보] → [실행]" 을 어머니 눈높이로 적어 뒀다.
- **`windows-latest` 이미지 드리프트** → 같은 태그를 다시 빌드하면 다른 exe 가 나올 수 있다.
  Python 만 3.11 로 고정했다. 무엇이 들어갔는지는 자산의 `installed-packages.txt` 로 남긴다.
- **자체 호스팅 러너(한글 설치)로 COM 까지 CI 검증** → 안 한다. 전용 PC·한컴 라이선스·러너
  보안 관리 비용이 개인 도구 하나에 비해 과하다.


---

# 드롭이 무반응이던 원인 (v0.2.1, 2026-08-24)

실기기 보고: **파일 고르기 버튼은 되는데 창 안으로 드래그앤드롭이 안 먹는다.**
→ 폴백 버튼을 넣어 둔 것이 여기서 값을 했다. 앱을 못 쓰게 되지는 않았다.

## 원인 — Windows 러너에 계측을 넣어 경계마다 실측했다

```
hwnd=0x601e0                 (19비트 — 문제없음)
old_wndproc=0x7ffb989873a0   ← 서브클래싱은 성공했다
hdrop=0x264596e0088          ← 42비트. c_int 에 안 들어간다
dispatch 호출됨? True         ← WM_DROPFILES 는 정상 도착했다
wparam == hdrop ? True        ← 핸들 값도 온전히 도착했다
exception=ArgumentError: argument 1: OverflowError: int too long to convert
[argtypes 준 경우]   count=1  path='C:\Users\m\공문.hwp'   ✅
[argtypes 없는 경우] 터짐
```

메시지도 핸들도 멀쩡했다. **`shell32` 를 `argtypes` 없이 부르는 순간 ctypes 가 던졌고,**
그 예외를 `_dispatch` 의 `except` 가 삼켜서 **화면상 아무 일도 안 일어났다.**

⚠️ **Mac 에서는 같은 상황이 조용히 32비트로 잘리기만 한다** — 증상이 달라서 로컬 재현만으로는
메커니즘을 오해한다. 실제로 내가 처음 세운 가설이 그래서 틀렸다(경로 0개가 될 거라고 봤는데,
실제로는 예외였다). **Windows 러너에서 계측한 것이 결론을 냈다.**

## 무엇이 이 결함을 놓쳤나

`tests/test_dnd.py` 가 **순수 파이썬 가짜(`FakeShell32`)** 를 썼다. 그래서 ctypes 경계를
한 번도 안 지났고, 드롭이 통째로 안 되는데 테스트 95개가 전부 초록이었다.
**가짜로 대체한 경계는 테스트되지 않는다** — 이 레포에서 두 번째로 밟은 형태다
(첫 번째는 시크릿 게이트가 `.env` 없는 레포에서 공허하게 통과한 것).

## 지금 그 자리를 무엇이 지키나

- `tests/test_dnd_windows.py` — **진짜 `HDROP` 을 `GlobalAlloc` 으로 만들어 실제 창에
  `WM_DROPFILES` 를 보낸다.** Windows CI 에서 돈다. 수정 전 RED, 수정 후 GREEN 을 확인했다.
- `tests/test_dnd.py` — 실측된 42비트 핸들(`0x264596E0088`)을 **진짜 `CFUNCTYPE` 마샬링**으로
  왕복시킨다. 플랫폼 무관이라 Mac 에서도 돈다. `HDROP` 을 `c_int` 로 되돌리면 깨진다.

## 같이 고친 것

- **WndProc 경쟁** — `set_long()` 이 돌아오는 순간부터 메시지가 들어오는데 `self._old_proc` 은
  그 뒤에 대입돼서, 그 사이 메시지가 `None` 을 원래 프로시저로 넘기고 있었다.
- **조용한 실패를 없앴다** — 드롭 처리가 터지면 창이 "끌어다 놓기가 잘 안 됐어요.
  아래 '파일 고르기' 버튼을 눌러 주세요" 를 띄운다. 예외를 WndProc 밖으로 낼 수는 없지만,
  **조용히 삼키면 무반응으로 보인다.** 그것 때문에 실기기 왕복을 한 번 했다.


---

# 드롭하면 앱이 죽던 원인 (v0.2.2, 2026-08-24)

v0.2.1 실기기 보고: **창은 뜨는데 파일을 끌어다 놓으면 앱이 죽는다.**

## 먼저 배제한 것

- **exe 파일 이름** — 스모크 워크플로(`.github/workflows/smoke.yml`)로 ASCII / 한글+공백 /
  한글 / ASCII+공백 **네 조합 모두 정상 실행** 확인. 게다가 Jell 은 `hwp2img.exe` 그대로 썼다.
- **PyInstaller 부트로더** — 창이 뜨므로 실행 자체는 된다.

## 원인 — 워커 스레드가 Tk 를 만졌다

전체 배선을 진짜 `WM_DROPFILES` 로 치는 테스트를 Windows CI 에 넣자 즉시 재현됐다:

```
test_the_whole_dropzone_survives_a_real_drop
AssertionError: assert 'processing' == 'idle'
```

창은 살고 변환도 호출되는데 **결과가 화면으로 영영 안 돌아왔다.**
`DropZoneController._finish` 가 **워커 스레드에서** `root.winfo_exists()` 와 `root.after()` 를
직접 불렀기 때문이다. **tkinter 는 스레드 안전하지 않다.**
CI Tk 에서는 콜백이 조용히 안 도는 것으로, 실기기에서는 **Tcl 패닉 → 프로세스 사망**으로 나타났다.

★**버튼 경로에서 안 드러난 이유**: 저장·클립보드·탐색기는 전부 **자식 프로세스**가 한다.
그래서 창 글자만 안 바뀌고 사용자는 성공으로 본다 — **잠복해 있었을 뿐 늘 틀린 코드였다.**

## 지금 구조

**어느 스레드에서도 Tk 를 만지지 않는다.**

```
WndProc 콜백 ──> controller.offer_paths()  ──┐
워커 스레드   ──> controller._outbox.put()  ──┤   (둘 다 큐에 넣기만 한다)
                                              │
메인 루프 ── root.after(100ms) ── pump() ── controller.poll() ──> view.set_status()
```

- `offer_paths` / `_work` 는 view 를 **건드리지 않는다.** `ExplodingView`(건드리면 터지는 가짜)로
  그 계약을 테스트가 고정한다 — 되돌리면 변이 검사가 잡는다.
- `_finish`/`_apply`/`schedule` 기계장치를 통째로 없앴다. 부품이 줄었다.
- WndProc 콜백이 Tcl 을 아예 안 건드리므로 **재진입 걱정도 같이 사라졌다.**
- `pump` 는 `launch()` 가 아니라 `_build_window()` 에 있다 — 배선 쪽에 없으면
  `_build_window` 로 만든 창은 큐가 영원히 안 비워진다(테스트가 잡았다).

## 지금 그 자리를 무엇이 지키나

- `tests/test_dnd_windows.py::test_the_whole_dropzone_survives_a_real_drop` —
  **띄어쓰기와 괄호가 든 파일명**(`공문 최종 (수정).hwp`)으로 진짜 드롭 메시지를 보내
  변환 호출과 창 생존을 확인한다. Windows CI 108 passed.
- `tests/test_dropzone.py` 의 `ExplodingView` 계열 — 스레드 경계 계약.

## 🔴 아직 안 본 것

CI 의 드롭 테스트는 `convert` 를 가짜로 준다. 즉 **창이 떠 있는 상태에서 실제 한글 COM 변환**
(= `watchdog` 이 얼린 exe 안에서 자식 프로세스를 spawn 하는 것)은 여전히 실기기 전용이다.
드롭까지 되고 변환에서 문제가 생기면 그 조합이 범인이다.
