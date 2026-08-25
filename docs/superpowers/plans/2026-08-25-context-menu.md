# 탐색기 우클릭 메뉴 — 실행 계획

Jell 결정 2026-08-25: **우클릭부터 만든다. 어머니 PC 는 Windows 11.**

## Win11 이 설계를 바꾼다 (웹 확인 2026-08-25)

평범한 shell verb 는 Win11 축약 메뉴에서 **무조건 "더 많은 옵션 표시" 아래**로 간다.
상단에 뜨려면 `IExplorerCommand` + app identity(sparse package) + **코드 서명**이 필요한데
우리한테 없다. 그래서 **상단 경로는 "프로그램에서 열기" 서브메뉴** 하나뿐이고, 거기 등록하는
정식 키가 `OpenWithProgids` 다 (MS: *"OpenWithProgids 가 OpenWithList 보다 선호된다.
OpenWithList 는 XP 이전 레거시 전용이다"*).

**두 경로를 다 건다.** 값 3개 더 쓰는 비용이고, 이 프로젝트에서 제일 비싼 것은 어머니 PC 왕복이다.

| 경로 | 어머니가 하는 것 | 어디에 등록 |
|---|---|---|
| Win11 상단 | 우클릭 → 프로그램에서 열기 → 한글 사진으로 바꾸기 | `.hwp\OpenWithProgids` + ProgID |
| 레거시 | 우클릭 → 더 많은 옵션 표시 → 한글 사진으로 바꾸기 | `SystemFileAssociations\.hwp\shell\hwp2img` |

⚠️ **정직하게: Win11 에선 "우클릭 한 번"이 아니라 3클릭이다.** 줄어드는 것은 클릭 수가 아니라
**드래그라는 손 기술**과 창 두 개를 동시에 띄우는 일이다. 오늘 실기기 결함 2건이 전부 그 축이었다.

## 등록 내용 — 전부 `HKCU\Software\Classes` (관리자 권한 0)

```
hwp2img.convert                                    (기본값) = "한글 사진으로 바꾸기"
hwp2img.convert\shell\open\command                 (기본값) = "<exe>" "%1"
.hwp\OpenWithProgids                               hwp2img.convert = REG_NONE
.hwpx\OpenWithProgids                              hwp2img.convert = REG_NONE
SystemFileAssociations\.hwp\shell\hwp2img          (기본값) = "한글 사진으로 바꾸기"
SystemFileAssociations\.hwp\shell\hwp2img\command  (기본값) = "<exe>" "%1"
SystemFileAssociations\.hwpx\shell\hwp2img         (기본값) = "한글 사진으로 바꾸기"
SystemFileAssociations\.hwpx\shell\hwp2img\command (기본값) = "<exe>" "%1"
```

## 지켜야 할 불변식 (테스트로 고정한다)

1. **`%1` 은 반드시 인용된다** (`"<exe>" "%1"`). 인용이 빠지면 argv 가 쪼개져 들어오고
   `cli.py:52-54` 가 `TOO_MANY_FILES` 로 거부한다 → **공백 든 파일만 조용히 실패**한다.
   이번 주에 Jell 이 실제로 의심했던 그 증상이다 (codex C3, cursor 보강).
2. **`.hwp`/`.hwpx` 의 기본값을 쓰지 않는다.** 쓰면 한글 파일 연결을 가로채 어머니가
   문서를 못 연다. `OpenWithProgids` 하위 키만 만든다.
3. **HKLM 을 안 건드린다.** 전부 HKCU.
4. **exe 경로가 바뀌면 재등록한다** (codex C4 — 바탕화면 exe 는 이름변경·이동으로 경로가 깨진다).
   설치 프로그램이 아직 없으니 **매 실행 시 자가 치유**로 푼다.
5. **등록 실패가 변환을 막지 않는다.** `security.ensure_security_module` 과 같은 규율.

## 순환 조건 (codex C2) — 이 배포에서는 이미 풀려 있다
"등록하려면 먼저 한 번 실행해야 한다"가 맞지만, 어머니는 **이미 바탕화면 아이콘으로 쓰고 있다.**
새 exe 를 받고 평소대로 한 번 변환하면 그때 메뉴가 생긴다. 설치 프로그램은 필요 없다.

## 검증
- 단위: 주입한 가짜 레지스트리로 위 불변식 1~5
- **Windows CI: 진짜 `winreg`** 로 샌드박스 베이스(`Software\hwp2img_test_<pid>\Classes`)에
  써 보고 읽어 확인한 뒤 지운다. **가짜만 쓰면 그 경계는 검증 안 된 것**이라는 게 이번 주
  드래그앤드롭에서 배운 것이다(가짜 `shell32` 뒤에서 95개 테스트가 초록인 채 완전히 깨져 있었다).
- **CI 가 못 하는 것:** 탐색기 메뉴에 실제로 보이는가. 어머니 PC(또는 Windows 장비)에서만.

## 롤백
`unregister()` 로 우리가 만든 키를 전부 지운다. 지운 뒤 남은 값이 0인지 테스트로 확인한다.

---

## 구현 후 diff 검토 — cursor (유예 중이라 codex 아님)

**`VERDICT: REVISE`.** 실제 결함 2건. 둘 다 실행이 바뀌는 것이라 고쳤다.

| # | 지적 | 처리 |
|---|---|---|
| D1 | **롤백이 `OpenWithProgids` 키를 통째로 지운다.** 그 키는 한글·다른 뷰어가 값을 나눠 갖는 **공유 키**라, 우리 값만이 아니라 그 앱들의 "프로그램에서 열기" 항목까지 날아간다 | **채택 · 고침.** 값만 지우고(`DeleteValue`) 공유 키는 안 지운다. 재현 테스트 2개(가짜·진짜 winreg) |
| D2 | **조기 반환이 명령 키 하나만 본다.** 명령 키는 **두 번째로** 써지므로 그 뒤 항목에서 등록이 터지면, 다음 실행이 "명령 키 맞네" 하고 반환해 **메뉴 절반이 빠진 상태가 영구 고착**된다 | **채택 · 고침.** 전 항목을 대조한다. 재현 테스트 1개 |
| D3 | `OpenWithProgids` 를 `REG_SZ ""` 로 쓰는데 MS 권장은 `REG_NONE` | **반박.** MS 문서 원문이 *"value type of either REG_NONE or REG_SZ and an empty string as the data value"* — 둘 다 명시적으로 허용이다 |
| D4 | HKCU 에 `.hwp` 키 자체가 (기본값 없이) 생길 수 있고, 병합 후 실제 더블클릭은 CI 로 증명 안 된다 | **채택 — 결함이 아니라 열린 게이트.** 이미 실기기 게이트로 적혀 있다 |
| D5 | 탐색기가 실제로 `"%1"` 을 어떻게 argv 로 넘기는지는 E2E 미검증 | **채택 — 열린 게이트.** README 체크리스트에 띄어쓰기 파일명 항목으로 박았다 |
| D6 | `watchdog` 자식은 `process_file` 만 타므로 등록을 안 한다 (`freeze_support` 실기기 검증은 기존 미완 항목) | **확인함 — 결함 아님** |

**변이 검사:** 등록 10종 + 롤백 4종 = **14/14 잡힘.**
그중 하나는 처음에 **빠져나갔다** — `_is_ours` 의 확장자 키 보호를 지워도 macOS 에서
아무 테스트도 안 깨졌다(그 불변식이 Windows 전용 파일에만 있었다). 가짜 쪽에 같은
검사를 추가해 닫았다. **변이 검사를 안 돌렸으면 그 구멍은 그대로 남았다.**
