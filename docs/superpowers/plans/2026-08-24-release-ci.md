# CI / GitHub Release — 계획 + 레인 지적 처리 원장 (2026-08-24)

## 무엇을 만드나

태그를 밀면 GitHub Actions 가 Windows 에서 exe 를 빌드해 **Release 에 첨부**한다.
어머니에게는 링크 하나만 주면 된다. 덤으로 **`windows-latest` 에서 pytest 가 돈다** —
이 프로젝트가 한 번도 못 가진 검증 표면이다(개발은 Mac, 실행은 Windows 전용).

## 착수 전 레인 (블라인드 + 레드팀)

| 레인 | 받은 것 | 결과 |
|---|---|---|
| `agy` — **블라인드** | 목표·제약·완료 조건만 (`DRAFT-v0` 안 줌) | 독립 설계안 |
| `codex` — **레드팀** | `DRAFT-v0` 전문 | `VERDICT: REVISE` |

### ★두 레인이 추측한 것을 내가 실측으로 확정했다

둘 다 "한글 없는 러너에서 `--collect-all pyhwpx` 가 실패할 **수도** 있다" 고만 했다.
휠을 직접 받아 뜯어 확인했다 (`pip download pyhwpx --no-deps`, 1.7.2):

```
pyhwpx/core.py
  60| try:
  61|     shutil.rmtree(...gen_py)
  62| except FileNotFoundError: pass
  66| win32.gencache.EnsureModule("{7D2B6F3C-1D95-4E0C-BF5A-5EE564186FBC}", 0, 1, 0)   ← try 밖
```

**모듈 최상위에서, try 없이** 한글 타입 라이브러리를 요구한다. `--collect-all` 은 패키지를
실제로 import 해서 분석하므로 **러너에서 죽을 공산이 크다.** 이 사실이 설계를 정했다.
(같은 확인에서 `FilePathCheckerModule.dll` · `fonts.json` 이 패키지 안에 있다는 것과,
pyhwpx 가 numpy·pandas·pyperclip 을 최상위에서 import 한다는 것도 확인했다.)

### 채택한 지적

| # | 출처 | 지적 | 처리 |
|---|---|---|---|
| 1 | codex | 워크플로 `permissions` 가 없다. 기본 토큰이 read-only 면 릴리즈 생성이 죽는다 | **채택.** release=`contents: write`, test=`contents: read` |
| 2 | codex | 태그가 테스트 성공을 기다리지 않는다 — 테스트가 깨진 커밋의 exe 가 공개될 수 있다 | **채택.** 한 잡 안에서 pytest → 빌드 → 릴리즈 순서. 릴리즈 생성은 **맨 마지막 한 스텝** |
| 3 | codex | `v*` 가 너무 넓다. 태그와 `pyproject` version 이 어긋난 채 배포된다 | **채택.** 대조해서 다르면 멈춘다 |
| 4 | codex | 서명 안 된 exe + SmartScreen/MOTW → 안내 없으면 어머니가 거기서 멈춘다 | **채택.** 릴리즈 노트·README 에 "[추가 정보] → [실행]" 을 어머니 눈높이로 |
| 5 | codex | 플랫폼 마커가 러너에서 어떻게 풀리는지 기록이 없다 | **채택.** `pip freeze` 를 릴리즈 노트에 접어 넣는다 |
| 6 | **cursor** (diff) | **`workflow_dispatch` 는 항상 죽는다** — 수동 실행 시 `GITHUB_REF_NAME` 이 태그가 아니라 브랜치명이라 버전 대조가 무조건 실패 | **채택.** `workflow_dispatch` 를 뺐다. 릴리즈는 태그에서만 |
| 7 | **cursor** | `--hidden-import` 도 같은 import 부작용으로 죽을 수 있다 — 프로브가 형태를 맞혀도 빌드가 죽으면 소용없다 | **채택 — 설계를 바꿨다.** 프로브+분기를 버리고 **빌드 자체를 두 번 시도**한다(collect-all → 실패 시 no-import 형태 → 둘 다 실패면 잡 실패) |
| 8 | **cursor** | 5MB 하한으로는 **dll 누락을 못 잡는다.** 불완전 번들도 통과한다 | **채택 — 이번 라운드 최고 수확.** 빌드 결과물에서 `FilePathCheckerModule` 문자열을 직접 찾는다. 없으면 릴리즈를 안 만든다. **이 레포가 실제로 겪은 실패다**(커밋 `25376ab`) |
| 9 | cursor | 자산이 둘이면 두 번째 업로드 실패 시 "릴리즈는 있는데 자산이 반쪽" 이 남는다 | **채택.** 자산을 exe 하나로 줄였다(`pip freeze` 는 노트 본문으로) |

### 반박한 지적

| 출처 | 지적 | 반박 근거 |
|---|---|---|
| codex | **한글이 설치된 자체 호스팅 Windows 러너**로 COM 까지 CI 검증 | **안 받는다.** 전용 PC 상시 가동 + 한컴 라이선스 + 러너 보안 관리 비용이 개인 도구 하나에 과하다. 실기기 검증은 Jell 이 어머니 PC 에 깔 때 어차피 일어난다 |
| codex | **Authenticode 코드 서명** | **범위 밖.** 인증서가 유료다. 대신 SmartScreen 안내를 어머니 눈높이로 적었다(채택 #4) |
| codex | 태그 빌드는 private artifact 로만 두고, **수동 승인 환경**을 거쳐 릴리즈 | **안 받는다.** 사용자가 한 명인 개인 도구에 GitHub Environment 승인 절차는 의례다. 승인할 사람과 실기기 검증할 사람이 같은 한 명이다 |
| codex | requirements 를 **hash 고정**해 재현성 확보 | **부분만.** 전체 hash pinning 은 이 규모에 과하다. 대신 **무엇이 실제로 들어갔는지**를 `pip freeze` 로 릴리즈마다 남긴다 — 재현 대신 **기록**을 택했다 |
| cursor | fallback 이 `--collect-all` 과 **동등하지 않다** | **사실은 맞다 — 그래서 안 고치는 게 아니라 다르게 막았다.** 동등성을 코드로 증명할 방법이 없어서, 대신 ①dll 존재를 실제로 검사하고 ②어느 형태로 빌드했는지를 릴리즈 노트에 박아 실기기 확인 항목으로 넘긴다 |
| codex | `windows-latest` 이미지 드리프트로 같은 태그가 다른 exe 를 낸다 | **수용하고 명시.** Python 만 3.11 로 고정했다. 이미지 고정은 GitHub 의 이미지 폐기 주기를 따라다녀야 해서 비용이 더 크다 |

## 검증한 것 (Mac 에서 할 수 있는 만큼)

- 두 워크플로 **YAML 파싱 OK**
- **모든 `run:` 블록을 `bash -n` 으로 문법 검사** — 5개 전부 통과
- 결과물 검사 스텝(크기·SHA256·유니코드 복사)을 더미 파일로 **드라이런** — 통과
- 버전 대조 스니펫(`tomllib`)을 로컬에서 실행 — `0.2.0` 정상 추출

**못 하는 것:** 워크플로가 실제로 도는지는 밀어 봐야 안다. 그게 다음 단계다.

## 게이트

- **GATE A** — `test.yml` 이 `windows-latest` 에서 통과하나 (**push 하면 바로 답이 나온다**)
- **GATE B** — 태그를 밀면 릴리즈에 exe 가 붙나 · 어느 빌드 형태로 됐나
- **GATE C** — 그 exe 가 어머니 PC 에서 실제로 도나 (**여전히 실기기 전용**)
