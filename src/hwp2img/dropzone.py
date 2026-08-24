"""인자 없이 실행됐을 때 뜨는 드롭존 창.

지금까지 argv 가 비면 "이 프로그램 위로 끌어다 놓아 주세요" 안내창을 띄우고 끝났다 —
어머니가 아이콘을 더블클릭하면 아무것도 못 하는 막다른 길이었다. 그 자리를 이 창이 대신한다.
**아이콘 위에 파일을 떨어뜨리는 기존 경로는 그대로다**(argv 가 있으면 이 모듈은 아예 안 불린다).

## 왜 tkinter 인가

tkinter 는 표준 라이브러리이고 PyInstaller 가 **내장 훅**으로 tcl/tk 를 수집한다.
`tkinterdnd2` 처럼 외장 Tcl 확장 바이너리를 들고 오는 라이브러리는, 수집에 실패해도
**개발 PC 에서는 되고 어머니 PC 에서만 터진다** — 이 레포가 이미 두 번 겪은 실패다.
드롭 수용은 tkinter 가 못 하므로 `dnd.py` 가 `ctypes` 로 OS 기본 DLL 만 써서 붙인다.

## 왜 변환을 스레드로 돌리나

`watchdog.run_process_file` 은 최대 `DEFAULT_TIMEOUT_SECONDS`(30초) 동안 **블로킹**한다.
드롭 핸들러에서 그걸 그냥 부르면 메시지 루프가 그동안 멈춰 창이 "응답 없음" 이 되고,
"바꾸는 중이에요…" 라고 써 두려던 그 글자조차 그려지지 않는다(크로스모델 리뷰 지적).
그래서 변환은 워커 스레드에서 돌리고, **UI 갱신은 반드시 메인 스레드로 되돌린다.**

## 왜 Tk 없이 테스트되나

이 Mac 에는 `_tkinter` 가 없다(3.11·3.14 둘 다 실측). 그래서 판정과 상태 전이는
`DropZoneController` 에 모으고 view 를 주입받는다 — 이 레포가 Windows 전용 함수에
이미 쓰는 방식이다. `import tkinter` 도 그래서 함수 안에 있다(모듈 최상위면 Mac 에서
테스트 수집이 통째로 깨진다).
"""

import threading
from pathlib import Path

from hwp2img import dnd, messages
from hwp2img.cli import SUPPORTED_EXTENSIONS
from hwp2img.errors import Hwp2ImgError, UnsupportedFileError

IDLE = "idle"
PROCESSING = "processing"

ACCEPT = "accept"
REJECT = "reject"

WINDOW_TITLE = "한글 사진으로 바꾸기"


def classify_drop(paths) -> tuple[str, str]:
    """떨어진 경로들을 보고 변환할지 거절할지 정한다.

    거절이면 두 번째 값이 **어머니에게 그대로 보여줄 문구**다. 문구는 인자 드롭 경로와
    공유한다(`messages.py`) — 같은 상황에서 두 경로가 다른 말을 하면 그 자체가 혼란이다.
    """
    if not paths:
        return REJECT, messages.PROMPT
    if len(paths) > 1:
        return REJECT, messages.TOO_MANY_FILES
    path = paths[0]
    if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
        return REJECT, UnsupportedFileError(path).user_message
    return ACCEPT, path


def _spawn_thread(job) -> None:
    threading.Thread(target=job, daemon=True).start()


class DropZoneController:
    """창의 상태 머신. Tk 를 모른다 — view 는 주입받는다.

    view 규약: `set_status(text)` · `is_alive() -> bool` · `schedule(fn)`.
    `schedule` 은 **메인 스레드에서** fn 을 실행해야 한다.
    """

    def __init__(self, view, convert, spawn=None, describe_error=None):
        self._view = view
        self._convert = convert
        self._spawn = spawn or _spawn_thread
        self._describe_error = describe_error or (lambda exc: messages.UNEXPECTED)
        self._state = IDLE

    @property
    def state(self) -> str:
        return self._state

    def handle_paths(self, paths) -> None:
        """드롭과 '파일 고르기' 버튼이 함께 쓰는 진입점."""
        if self._state == PROCESSING:
            # 변환 중 추가 드롭은 받지 않는다. 받아 주면 한글 COM 을 동시에 두 번
            # 띄우게 되는데, 그건 이 프로그램이 한 번도 검증한 적 없는 상태다.
            self._view.set_status(messages.BUSY)
            return

        verdict, payload = classify_drop(paths)
        if verdict != ACCEPT:
            self._view.set_status(payload)
            return

        self._state = PROCESSING
        self._view.set_status(messages.CONVERTING)
        self._spawn(lambda: self._work(payload))

    def _work(self, hwp_path: str) -> None:
        """워커 스레드에서 돈다. **여기서 예외가 새어나가면 아무도 못 본다.**"""
        try:
            out_path = self._convert(hwp_path)
        except Hwp2ImgError as exc:
            self._finish(exc.user_message)
        except Exception as exc:
            self._finish(self._describe_error(exc))
        else:
            self._finish(messages.done(out_path))

    def can_close(self) -> bool:
        """변환 중이면 창을 닫지 못하게 한다.

        지금 닫으면 워커 스레드(daemon)와 `watchdog` 이 띄운 자식 프로세스가 어중간하게
        남는데, `--noconsole` 이라 어머니 눈에는 아무 흔적도 안 보인다. `watchdog` 이
        30초 안에 무조건 끝내므로 기다리는 시간은 유한하다 — 그동안 막는 편이 안전하다.
        """
        if self._state == PROCESSING:
            self._view.set_status(messages.BUSY)
            return False
        return True

    def _finish(self, message: str) -> None:
        """워커 스레드에서 불린다. **여기서 `IDLE` 로 되돌리면 안 된다.**

        `schedule` 은 다음 메인 루프 틱에 실행된다. 여기서 상태를 먼저 IDLE 로 찍으면
        그 사이에 들어온 드롭이 받아들여지고, 뒤늦게 도착한 **이전 결과가 새 변환의
        "바꾸는 중…" 을 덮어쓴다** — 어머니가 아직 변환 중인데 "다 됐어요" 를 본다
        (cursor diff 리뷰 지적). 상태와 화면은 같은 틱에 같이 바뀌어야 한다.
        """
        if not self._view.is_alive():
            self._state = IDLE  # 그릴 화면이 없다. 상태만 되돌린다
            return
        try:
            self._view.schedule(lambda: self._apply(message))
        except Exception:
            # 변환이 끝나는 순간 어머니가 창을 닫으면 메인 루프가 이미 없을 수 있다.
            # 여기서도 되돌려야 창이 살아남은 경우에 영구히 막히지 않는다.
            self._state = IDLE

    def _apply(self, message: str) -> None:
        """메인 스레드에서 불린다 — 상태와 화면이 여기서 함께 바뀐다."""
        self._state = IDLE
        # is_alive 검사와 실제 갱신 사이에 창이 닫힐 수 있어 한 번 더 본다.
        if not self._view.is_alive():
            return
        self._view.set_status(message)


class _TkView:
    """`DropZoneController` 가 요구하는 view 규약의 Tk 구현."""

    def __init__(self, root, label):
        self._root = root
        self._label = label

    def set_status(self, text: str) -> None:
        self._label.config(text=text)

    def is_alive(self) -> bool:
        try:
            return bool(self._root.winfo_exists())
        except Exception:
            return False

    def schedule(self, fn) -> None:
        self._root.after(0, fn)


def launch(convert, describe_error=None, drop_hook=None) -> int:
    """드롭존 창을 띄우고 닫힐 때까지 돈다. 정상 종료면 0."""
    root, _controller, hooks = _build_window(convert, describe_error, drop_hook)
    try:
        root.mainloop()
    finally:
        for hook, _hwnd in hooks:
            hook.detach()
    return 0


def _build_window(convert, describe_error=None, drop_hook=None):
    """창을 만들고 배선까지 끝낸 뒤 `(root, controller, hooks)` 을 돌려준다.

    `mainloop()` 을 여기서 안 부르는 건 **테스트 때문이다.** 예전에는 `launch()` 하나가
    창 생성부터 메인 루프까지 다 했는데, 그러면 본문 전체가 어떤 테스트도 안 지나서
    위젯 인자 오타 하나가 어머니 PC 까지 그대로 간다 — `--noconsole` 이라 거기서는
    에러 메시지조차 안 보인다.
    """
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry("520x340")
    root.configure(bg="#f4f1ea")
    root.minsize(420, 280)

    frame = tk.Frame(root, bg="#ffffff", highlightbackground="#c8b89a", highlightthickness=3)
    frame.pack(fill="both", expand=True, padx=22, pady=(22, 12))

    label = tk.Label(
        frame,
        text=f"{messages.PROMPT}\n\n{messages.HINT}",
        font=("맑은 고딕", 16),
        bg="#ffffff",
        fg="#2b2b2b",
        justify="center",
        wraplength=420,
    )
    label.pack(expand=True, padx=16, pady=16)

    view = _TkView(root, label)
    controller = DropZoneController(view, convert, describe_error=describe_error)

    def browse():
        chosen = filedialog.askopenfilename(
            title=WINDOW_TITLE,
            filetypes=[("한글 문서", "*.hwp *.hwpx")],
        )
        if chosen:
            controller.handle_paths([chosen])

    tk.Button(
        root,
        text=messages.BROWSE_BUTTON,
        font=("맑은 고딕", 12),
        command=browse,
        relief="flat",
        bg="#3d5a80",
        fg="#ffffff",
        activebackground="#2c4463",
        activeforeground="#ffffff",
        padx=14,
        pady=8,
        cursor="hand2",
    ).pack(pady=(0, 22))

    def on_close():
        if controller.can_close():
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    def on_dropped(paths):
        """`WM_DROPFILES` 콜백 **스택 안에서** 불린다.

        그 자리에서 Tk 위젯을 만지면 Tcl 이 Windows 메시지 처리 도중 재진입한다
        (cursor diff 리뷰 지적). 반드시 메인 루프로 넘긴 뒤에 만진다.
        """
        try:
            root.after(0, lambda: controller.handle_paths(paths))
        except Exception:
            pass

    # 창이 실제로 만들어진 뒤에야 핸들이 생긴다.
    root.update_idletasks()

    hooks = []
    if drop_hook is not None:
        hooks.append((drop_hook, root.winfo_id()))
    else:
        # ★Tk 의 클라이언트 창과 프레임 창 중 **어느 쪽이 드롭을 받는지 Windows 에서
        # 확인한 적이 없다.** 개발자가 그 PC 에서 반복 시도할 수 없으므로, 서로 다르면
        # 둘 다 건다. 둘 다 실패해도 "파일 고르기" 버튼으로 변환은 그대로 된다.
        for hwnd in _drop_target_handles(root):
            hooks.append((dnd.create_drop_hook(), hwnd))

    for hook, hwnd in hooks:
        hook.attach(hwnd, on_dropped)

    return root, controller, hooks


def _drop_target_handles(root) -> list[int]:
    """드롭을 받을 후보 창 핸들. 중복은 뺀다."""
    handles = []
    try:
        handles.append(root.winfo_id())
    except Exception:
        pass
    try:
        frame = int(root.wm_frame(), 16)
        if frame and frame not in handles:
            handles.append(frame)
    except Exception:
        pass
    return handles
