from __future__ import annotations

import ctypes
import os
import logging
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

import cv2
import mss
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "강화.log"

ENHANCE_IMAGE_DIR = Path(r"C:\Users\Jongseo Won\Desktop\auto\images\enhance")

PRE_ENHANCE1_IMAGE = ENHANCE_IMAGE_DIR / "pre_enhance1.png"
PRE_ENHANCE2_IMAGE = ENHANCE_IMAGE_DIR / "pre_enhance2.png"
ENHANCE1_IMAGE = ENHANCE_IMAGE_DIR / "enhance1.png"
ENHANCE2_IMAGE = ENHANCE_IMAGE_DIR / "enhance2.png"

THRESHOLD = 0.82
SCAN_INTERVAL_SECONDS = 0.12
CLICK_COOLDOWN_SECONDS = 0.35
CLICK_HOLD_SECONDS = 0.08
CURSOR_SETTLE_SECONDS = 0.25
POST_CLICK_DELAY_SECONDS = 0.15
PRE_CLICK_DELAY_SECONDS = 0.0
VK_ESCAPE = 0x1B
MOUSE_CLICK_LOCK = threading.Lock()


class MouseInput(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class InputUnion(ctypes.Union):
    _fields_ = (("mi", MouseInput),)


class Input(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = (
        ("type", wintypes.DWORD),
        ("data", InputUnion),
    )


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def ensure_admin() -> bool:
    if ctypes.windll.shell32.IsUserAnAdmin():
        return True

    if getattr(sys, "frozen", False):
        executable = sys.executable
        arguments = subprocess.list2cmdline(sys.argv[1:])
    else:
        current_python = Path(sys.executable)
        pythonw = current_python.with_name("pythonw.exe")
        executable = str(pythonw if pythonw.exists() else current_python)
        arguments = subprocess.list2cmdline(
            [os.path.abspath(__file__), *sys.argv[1:]]
        )

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        arguments,
        os.getcwd(),
        1,
    )

    if result <= 32:
        raise OSError("관리자 권한으로 다시 실행하지 못했습니다.")

    return False


def held_left_click(x: int, y: int) -> None:
    with MOUSE_CLICK_LOCK:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        if not user32.SetCursorPos(int(x), int(y)):
            raise ctypes.WinError(ctypes.get_last_error())

        time.sleep(CURSOR_SETTLE_SECONDS)

        down = Input(
            type=0,
            mi=MouseInput(dwFlags=0x0002),
        )
        up = Input(
            type=0,
            mi=MouseInput(dwFlags=0x0004),
        )

        if user32.SendInput(
            1,
            ctypes.byref(down),
            ctypes.sizeof(Input),
        ) != 1:
            raise ctypes.WinError(ctypes.get_last_error())

        time.sleep(CLICK_HOLD_SECONDS)

        if user32.SendInput(
            1,
            ctypes.byref(up),
            ctypes.sizeof(Input),
        ) != 1:
            raise ctypes.WinError(ctypes.get_last_error())

        # 다음 분면으로 마우스가 이동하기 전에 클릭이 안정적으로
        # 처리될 시간을 둡니다.
        time.sleep(POST_CLICK_DELAY_SECONDS)


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    def as_mss(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class Target:
    key: str
    rect: Rect
    pre_image_path: Path
    image_path: Path


def monitor_quadrants() -> dict[str, Rect]:
    with mss.MSS() as capture:
        monitors = list(capture.monitors[1:])

    result: dict[str, Rect] = {}

    for monitor_number, monitor in enumerate(monitors, 1):
        left = int(monitor["left"])
        top = int(monitor["top"])
        width = int(monitor["width"])
        height = int(monitor["height"])

        half_w = width // 2
        half_h = height // 2

        cells = (
            (left, top, half_w, half_h),
            (left + half_w, top, width - half_w, half_h),
            (left, top + half_h, half_w, height - half_h),
            (left + half_w, top + half_h, width - half_w, height - half_h),
        )

        for quadrant, values in enumerate(cells, 1):
            result[f"m{monitor_number}q{quadrant}"] = Rect(*values)

    return result


def build_targets() -> list[Target]:
    quadrants = monitor_quadrants()

    required = (
        "m1q1",
        "m1q2",
        "m1q3",
        "m1q4",
        "m2q1",
        "m2q2",
    )

    missing = [key for key in required if key not in quadrants]
    if missing:
        raise RuntimeError(
            "필요한 모니터/분면을 찾을 수 없습니다: "
            + ", ".join(missing)
        )

    return [
        Target("m1q1", quadrants["m1q1"], PRE_ENHANCE1_IMAGE, ENHANCE1_IMAGE),
        Target("m1q2", quadrants["m1q2"], PRE_ENHANCE1_IMAGE, ENHANCE1_IMAGE),
        Target("m1q3", quadrants["m1q3"], PRE_ENHANCE1_IMAGE, ENHANCE1_IMAGE),
        Target("m1q4", quadrants["m1q4"], PRE_ENHANCE1_IMAGE, ENHANCE1_IMAGE),
        Target("m2q1", quadrants["m2q1"], PRE_ENHANCE2_IMAGE, ENHANCE2_IMAGE),
        Target("m2q2", quadrants["m2q2"], PRE_ENHANCE2_IMAGE, ENHANCE2_IMAGE),
    ]


def load_template(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {path}")

    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"이미지를 읽을 수 없습니다: {path}")

    return template


def find_image_center(
    gray: np.ndarray,
    template: np.ndarray,
    rect: Rect,
) -> tuple[int, int, float] | None:
    th, tw = template.shape[:2]
    gh, gw = gray.shape[:2]

    if th > gh or tw > gw:
        return None

    result = cv2.matchTemplate(
        gray,
        template,
        cv2.TM_CCOEFF_NORMED,
    )

    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < THRESHOLD:
        return None

    center_x = rect.left + max_loc[0] + tw // 2
    center_y = rect.top + max_loc[1] + th // 2

    return center_x, center_y, float(max_val)


def esc_pressed() -> bool:
    return bool(
        ctypes.windll.user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000
    )


def main() -> None:
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )

    enable_dpi_awareness()

    if not ensure_admin():
        return

    targets = build_targets()

    templates = {
        str(PRE_ENHANCE1_IMAGE): load_template(PRE_ENHANCE1_IMAGE),
        str(PRE_ENHANCE2_IMAGE): load_template(PRE_ENHANCE2_IMAGE),
        str(ENHANCE1_IMAGE): load_template(ENHANCE1_IMAGE),
        str(ENHANCE2_IMAGE): load_template(ENHANCE2_IMAGE),
    }

    last_click_at: dict[str, float] = {
        target.key: 0.0
        for target in targets
    }

    logging.info("강화 이미지 자동 클릭 시작")
    logging.info("모니터1 q1~q4 : pre_enhance1 -> enhance1")
    logging.info("모니터2 q1~q2 : pre_enhance2 -> enhance2")
    logging.info("threshold=%s", THRESHOLD)
    logging.info("클릭 위치=찾은 이미지 정중앙")
    logging.info("ESC=프로그램 종료")

    try:
        with mss.MSS() as capture:
            while True:
                if esc_pressed():
                    logging.info("ESC 감지 -> 종료")
                    break

                now = time.monotonic()

                for target in targets:
                    if esc_pressed():
                        logging.info("ESC 감지 -> 종료")
                        return

                    if (
                        now - last_click_at[target.key]
                        < CLICK_COOLDOWN_SECONDS
                    ):
                        continue

                    shot = np.asarray(
                        capture.grab(target.rect.as_mss())
                    )

                    gray = cv2.cvtColor(
                        shot,
                        cv2.COLOR_BGRA2GRAY,
                    )

                    # 1) 먼저 pre_enhance 이미지를 찾습니다.
                    pre_template = templates[str(target.pre_image_path)]

                    pre_match = find_image_center(
                        gray,
                        pre_template,
                        target.rect,
                    )

                    if pre_match is None:
                        continue

                    pre_x, pre_y, pre_score = pre_match

                    logging.info(
                        "%s %s 감지 %.3f -> 클릭 (%s, %s)",
                        target.key,
                        target.pre_image_path.stem,
                        pre_score,
                        pre_x,
                        pre_y,
                    )

                    held_left_click(pre_x, pre_y)

                    # pre 클릭 후 화면이 바뀔 시간을 조금 줍니다.
                    time.sleep(0.35)

                    # 2) 같은 분면을 다시 캡처해서 enhance를 찾습니다.
                    shot = np.asarray(
                        capture.grab(target.rect.as_mss())
                    )
                    gray = cv2.cvtColor(
                        shot,
                        cv2.COLOR_BGRA2GRAY,
                    )

                    enhance_template = templates[str(target.image_path)]

                    enhance_match = find_image_center(
                        gray,
                        enhance_template,
                        target.rect,
                    )

                    if enhance_match is None:
                        logging.info(
                            "%s %s 클릭 후 %s 미검출",
                            target.key,
                            target.pre_image_path.stem,
                            target.image_path.stem,
                        )
                        last_click_at[target.key] = time.monotonic()
                        continue

                    x, y, score = enhance_match

                    if PRE_CLICK_DELAY_SECONDS > 0:
                        time.sleep(PRE_CLICK_DELAY_SECONDS)

                    logging.info(
                        "%s %s 감지 %.3f -> 클릭 (%s, %s)",
                        target.key,
                        target.image_path.stem,
                        score,
                        x,
                        y,
                    )

                    held_left_click(x, y)
                    last_click_at[target.key] = time.monotonic()

                time.sleep(SCAN_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logging.info("Ctrl+C -> 종료")


if __name__ == "__main__":
    main()
