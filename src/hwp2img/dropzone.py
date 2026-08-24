"""인자 없이 실행됐을 때 뜨는 드롭존 창.

지금까지 argv 가 비면 "이 프로그램 위로 끌어다 놓아 주세요" 안내창을 띄우고 끝났다 —
어머니가 아이콘을 더블클릭하면 아무것도 못 하는 막다른 길이었다. 그 자리를 이 창이 대신한다.
**아이콘 위에 파일을 떨어뜨리는 기존 경로는 그대로다**(argv 가 있으면 이 모듈은 아예 안 불린다).

## 왜 tkinter 인가

tkinter 는 표준 라이브러리이고 PyInstaller 가 **내장 훅**으로 tcl/tk 를 수집한다.
`tkinterdnd2` 처럼 외장 Tcl 확장 바이너리를 들고 오는 라이브러리는, 수집에 실패해도
**개발 PC 에서는 되고 어머니 PC 에서만 터진다** — 이 레포가 이미 두 번 겪은 실패다.
드롭 수용은 tkinter 가 못 하므로 `dnd.py` 가 `ctypes` 로 OS 기본 DLL 만 써서 붙인다.

## ★Tk 는 **메인 스레드에서만** 만진다

`watchdog.run_process_file` 이 최대 30초 블로킹하므로 변환은 워커 스레드에서 돈다.
예전에는 그 워커가 끝나면서 `root.winfo_exists()` 와 `root.after()` 를 **직접** 불렀는데,
**tkinter 는 스레드 안전하지 않다.** 실기기에서는 그게 Tcl 패닉 → 프로세스 사망이었고
(어머니 PC 에서 드롭하는 순간 앱이 죽었다), CI 에서는 조용히 콜백이 안 도는 것으로 나타났다.
버튼 경로에서 안 드러난 이유는 저장·클립보드·탐색기를 **자식 프로세스**가 하기 때문이다 —
창 글자만 안 바뀌고 사용자는 성공으로 본다.

지금은 **어느 스레드에서도 Tk 를 만지지 않는다.** 드롭도 변환 결과도 큐에 넣고,
메인 루프가 `poll()` 로 가져가 화면을 바꾼다. 큐는 스레드 안전하고 Tcl 과 무관하다.
덕분에 WndProc 콜백도 Tcl 을 아예 안 건드린다(재진입 걱정도 같이 사라진다).

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

import queue
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

    view 규약: `set_status(text)` · `is_alive() -> bool`.
    ★**`set_status` 는 메인 스레드에서만 불린다** — `poll()` 안에서만 부르기 때문이다.
    """

    #: 메인 루프가 큐를 확인하는 주기(ms). 사람이 못 느낄 만큼 짧고, 놀고 있을 때
    #: CPU 를 안 쓸 만큼 길다.
    POLL_INTERVAL_MS = 100

    def __init__(self, view, convert, spawn=None, describe_error=None):
        self._view = view
        self._convert = convert
        self._spawn = spawn or _spawn_thread
        self._describe_error = describe_error or (lambda exc: messages.UNEXPECTED)
        self._state = IDLE
        self._inbox = queue.Queue()  # 드롭된 경로 (WndProc 에서 들어온다)
        self._outbox = queue.Queue()  # (문구, 변환이 끝났나) (워커에서 들어온다)

    @property
    def state(self) -> str:
        return self._state

    # --- 아무 스레드에서나 불러도 되는 것 (Tk 를 안 만진다) -------------------

    def offer_paths(self, paths) -> None:
        """드롭된 경로를 접수만 한다. **Win32 WndProc 콜백 안에서 불린다.**

        여기서 Tk 를 만지면 Tcl 이 메시지 처리 도중 재진입한다. 큐에 넣기만 하고
        실제 처리는 `poll()` 이 메인 스레드에서 한다.
        """
        self._inbox.put(list(paths))

    def offer_notice(self, message: str) -> None:
        """상태만 알린다 — 변환 상태는 안 건드린다."""
        self._outbox.put((message, False))

    # --- 메인 스레드 전용 ---------------------------------------------------

    def poll(self) -> bool:
        """메인 루프가 주기적으로 부른다. 큐를 비우고 화면을 갱신한다.

        결과를 먼저 반영하고 그다음 새 드롭을 받는다 — 순서를 바꾸면 방금 시작한
        변환의 "바꾸는 중…" 을 직전 결과가 덮어쓴다.
        """
        did_something = False

        while True:
            try:
                message, finished = self._outbox.get_nowait()
            except queue.Empty:
                break
            if finished:
                self._state = IDLE
            self._set_status(message)
            did_something = True

        while True:
            try:
                paths = self._inbox.get_nowait()
            except queue.Empty:
                break
            self.handle_paths(paths)
            did_something = True

        return did_something

    def handle_paths(self, paths) -> None:
        """드롭과 '파일 고르기' 버튼이 함께 쓰는 진입점. **메인 스레드에서만.**"""
        if self._state == PROCESSING:
            # 변환 중 추가 드롭은 받지 않는다. 받아 주면 한글 COM 을 동시에 두 번
            # 띄우게 되는데, 그건 이 프로그램이 한 번도 검증한 적 없는 상태다.
            self._set_status(messages.BUSY)
            return

        verdict, payload = classify_drop(paths)
        if verdict != ACCEPT:
            self._set_status(payload)
            return

        self._state = PROCESSING
        self._set_status(messages.CONVERTING)
        self._spawn(lambda: self._work(payload))

    def can_close(self) -> bool:
        """변환 중이면 창을 닫지 못하게 한다.

        지금 닫으면 워커 스레드(daemon)와 `watchdog` 이 띄운 자식 프로세스가 어중간하게
        남는데, `--noconsole` 이라 어머니 눈에는 아무 흔적도 안 보인다. `watchdog` 이
        30초 안에 무조건 끝내므로 기다리는 시간은 유한하다 — 그동안 막는 편이 안전하다.
        """
        if self._state == PROCESSING:
            self._set_status(messages.BUSY)
            return False
        return True

    def _set_status(self, message: str) -> None:
        if self._view.is_alive():
            self._view.set_status(message)

    # --- 워커 스레드 전용 (Tk 를 절대 만지지 않는다) -------------------------

    def _work(self, hwp_path: str) -> None:
        """워커 스레드에서 돈다. **여기서 예외가 새어나가면 아무도 못 본다.**

        ★view 를 건드리지 않는다. 결과는 큐에만 넣는다 — tkinter 는 스레드 안전하지 않고,
        예전에 여기서 `root.after()` 를 부르다 실기기에서 프로세스가 죽었다.
        """
        try:
            out_path = self._convert(hwp_path)
        except Hwp2ImgError as exc:
            self._outbox.put((exc.user_message, True))
        except Exception as exc:
            self._outbox.put((self._describe_error(exc), True))
        else:
            self._outbox.put((messages.done(out_path), True))


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


def launch(convert, describe_error=None, drop_hook=None) -> int:
    """드롭존 창을 띄우고 닫힐 때까지 돈다. 정상 종료면 0."""
    root, _controller, hooks = _build_window(convert, describe_error, drop_hook)
    try:
        root.mainloop()
    finally:
        for hook, _hwnd in hooks:
            hook.detach()
    return 0


def _build_window(convert, describe_error=None, drop_hook=None, root=None):
    """창을 만들고 배선까지 끝낸 뒤 `(root, controller, hooks)` 을 돌려준다.

    `mainloop()` 을 여기서 안 부르는 건 **테스트 때문이다.** 예전에는 `launch()` 하나가
    창 생성부터 메인 루프까지 다 했는데, 그러면 본문 전체가 어떤 테스트도 안 지나서
    위젯 인자 오타 하나가 어머니 PC 까지 그대로 간다 — `--noconsole` 이라 거기서는
    에러 메시지조차 안 보인다.
    """
    import tkinter as tk
    from tkinter import filedialog

    # `root` 는 테스트가 창을 주입하기 위한 자리다. 실행 경로는 항상 None 으로 들어온다.
    # Tk 는 root 를 만들었다 부수기를 반복하면 불안정하다 — macOS 는 세그폴트했고
    # Windows 러너는 4번째 생성에서 `Can't find a usable init.tcl` 이 났다(둘 다 실측).
    # 그래서 스모크 테스트는 root 하나를 두고 Toplevel 을 주입한다.
    if root is None:
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

    # ★`WM_DROPFILES` 콜백은 Tcl 을 **아예 안 만진다.** 큐에 넣기만 하고
    #   실제 처리는 아래 `pump()` 가 메인 루프에서 한다.
    on_dropped = controller.offer_paths

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

    def on_drop_error(_exc):
        """드롭 처리가 터졌다. **조용히 넘어가면 무반응으로 보인다** — 버튼을 가리킨다."""
        controller.offer_notice(messages.DROP_FAILED)

    for hook, hwnd in hooks:
        hook.attach(hwnd, on_dropped, on_error=on_drop_error)

    # ★펌프는 **배선의 일부**다. `launch()` 쪽에 두면 `_build_window` 로 만든 창은
    #   큐가 영원히 안 비워진다 — 드롭해도 아무 일이 안 일어난다.
    def pump():
        """메인 루프가 큐를 비운다. 다른 스레드가 Tk 를 만지지 않게 하는 유일한 통로다."""
        controller.poll()
        if view.is_alive():
            root.after(DropZoneController.POLL_INTERVAL_MS, pump)

    root.after(DropZoneController.POLL_INTERVAL_MS, pump)

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
