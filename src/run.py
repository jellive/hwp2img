import multiprocessing
import sys

# ★`freeze_support()` 는 무거운 import 보다 **먼저** 와야 한다 (크로스모델 리뷰 지적).
# watchdog.py 가 변환을 별도 프로세스로 격리하는데, PyInstaller 로 얼린 onefile exe 에서
# multiprocessing 이 자식을 spawn 하면 그 자식은 같은 exe 를 처음부터 다시 실행한다.
# `freeze_support()` 가 그 자식을 가로채 worker 로 전환시키는데, 그 전에 `hwp2img.cli` 를
# import 해버리면 자식이 worker 로 갈라지기 전에 `cli → hwp_to_pdf → pyhwpx` 경로를 타고
# pyhwpx 의 import 시점 부작용(gen_py 캐시 삭제, EnsureModule 실행)까지 실행한다.
# 얼리지 않은 환경(테스트, 일반 python 실행)에서는 즉시 반환하는 무동작이라 안전하다.
if __name__ == "__main__":
    multiprocessing.freeze_support()

from hwp2img.cli import main  # noqa: E402  (freeze_support 뒤여야 한다 — 위 주석)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
