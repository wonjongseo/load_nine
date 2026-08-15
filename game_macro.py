from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

import cv2
import mss
import numpy as np
from mss.exception import ScreenShotError


BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "images"
LOG_FILE = BASE_DIR / "automation_python.log"
DEBUG_DIR = BASE_DIR / "debug_capture_python"

# mss.monitors 기준 번호입니다. 0은 전체 가상 화면, 1부터 개별 모니터입니다.
MONITOR_B = 1
ACTIVE_QUADRANTS = (1, 2, 3, 4)
SCAN_INTERVAL_SECONDS = 0.7
DEFAULT_THRESHOLD = 0.82
MENU_TIMEOUT_SECONDS = 60
TOUCH_EMPTY_SPACE_TIMEOUT_SECONDS = 5
PRE_CLICK_DELAY_SECONDS = 0.3
FAILURE_COOLDOWNS_SECONDS = (30, 60, 300)
CLICK_HOLD_SECONDS = 0.08

# 단계별 검증용 플래그
SKIP_STEPS_02_TO_09 = False

# 각 분면 왼쪽 위를 (0, 0)으로 하는 상대좌표입니다.
# None인 분면은 월드맵 단계에서 안전하게 중단합니다.
WORLD_MAP_POINTS: dict[int, tuple[int, int] | None] = {
    1: (140, 170),
    2: (148, 177),
    3: (153, 149),
    4: (149, 141),
}

# 이미지별 confidence 기준값입니다.
# 값이 높을수록 엄격하며 일반적으로 0.70~0.90 범위를 사용합니다.
IMAGE_THRESHOLDS = {
    "rest.png": 0.85,
    "001_dyied.png": 0.85,
    "002_sandtimer.png": 0.85,
    "01_revive.png": 0.85,
    "02_menu.png": 0.68,
}


# 공통 단계 중 분면별로 다른 이미지가 필요한 경우 여기에 등록합니다.
# 지정한 파일이 아직 없으면 images 루트의 기본 이미지로 fallback합니다.
QUADRANT_IMAGE_OVERRIDES: dict[int, dict[str, str]] = {
    1: {
        "01_revive.png": "quadrant_1/01_revive_pc.png",
        "02_menu.png": "quadrant_1/02_menu_pc.png",
        "03_equip_workshop.png": "quadrant_1/03_equip_workshop_pc.png",
        "04_dismantle_menu.png": "quadrant_1/04_dismantle_menu_pc.png",
        "05_auto_register.png": "quadrant_1/05_auto_register_pc.png",
        "06_dismantle_execute.png": "quadrant_1/06_dismantle_execute_pc.png",
        "07_touch_empty_space.png": "quadrant_1/07_touch_empty_space_pc.png",
        "08_close_appraisal.png": "quadrant_1/08_close_appraisal_pc.png",
        "09_close_menu.png": "quadrant_1/09_close_menu_pc.png",
        "10_general_store.png": "quadrant_1/10_general_store_pc.png",
        "quadrant_1/11_potion.png": "quadrant_1/11_potion_pc.png",
        "12_100_percent.png": "quadrant_1/12_100_percent_pc.png",
        "13_buy.png": "quadrant_1/13_buy_pc.png",
        "14_close_shop.png": "quadrant_1/14_close_shop_pc.png",
        "15_world_map.png": "quadrant_1/15_world_map_pc.png",
        "quadrant_1/16_region.png": "quadrant_1/16_region_pc.png",
        "quadrant_1/17_hunting_ground.png": (
            "quadrant_1/17_hunting_ground_pc.png"
        ),
        "quadrant_1/18_monster.png": "quadrant_1/18_monster_pc.png",
        "19_quick_move.png": "quadrant_1/19_quick_move_pc.png",
        "20_confirm.png": "quadrant_1/20_confirm_pc.png",
        "21_auto.png": "quadrant_1/21_auto_pc.png",
    },
    2: {},
    3: {},
    4: {},
}

QUADRANT_CONFIG = {
    1: {
        "potion": "quadrant_1/11_potion.png",
        "region": "quadrant_1/16_region.png",
        "hunting_ground": "quadrant_1/17_hunting_ground.png",
        "monster": "quadrant_1/18_monster.png",
        "auto": "21_auto.png",
    },
    2: {
        "potion": "quadrant_2/11_potion.png",
        "region": "quadrant_2/16_region.png",
        "hunting_ground": "quadrant_2/17_hunting_ground.png",
        "monster": "quadrant_2/18_monster.png",
        "auto": "21_auto.png",
    },
    3: {
        "potion": "quadrant_3/11_potion.png",
        "region": "quadrant_3/16_region.png",
        "hunting_ground": "quadrant_3/17_hunting_ground.png",
        "monster": "quadrant_3/18_monster.png",
        "auto": "quadrant_3/21_auto.png",
    },
    4: {
        "potion": "quadrant_4/11_potion.png",
        "region": "quadrant_4/16_region.png",
        "hunting_ground": "quadrant_4/17_hunting_ground.png",
        "monster": "quadrant_4/18_monster.png",
        "auto": "21_auto.png",
    },
}


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_mss(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class Match:
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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
    _fields_ = (("type", wintypes.DWORD), ("data", InputUnion))


class StepImageNotFound(RuntimeError):
    pass


class RestartFromRevive(RuntimeError):
    pass


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
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        executable = str(pythonw if pythonw.exists() else Path(sys.executable))
        arguments = subprocess.list2cmdline(
            [os.path.abspath(__file__), *sys.argv[1:]]
        )

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        arguments,
        os.getcwd(),
        0,  # SW_HIDE: 관리자 권한으로 재실행되는 콘솔 창 숨김
    )
    if result <= 32:
        raise OSError("관리자 권한으로 다시 실행하지 못했습니다.")
    return False


def hide_console_window() -> None:
    try:
        console_window = ctypes.windll.kernel32.GetConsoleWindow()
        if console_window:
            ctypes.windll.user32.ShowWindow(console_window, 0)
    except Exception:
        pass


def left_click_held() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    button_down = Input(
        type=0,
        mi=MouseInput(dwFlags=0x0002),
    )
    if user32.SendInput(1, ctypes.byref(button_down), ctypes.sizeof(Input)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())

    time.sleep(CLICK_HOLD_SECONDS)

    button_up = Input(
        type=0,
        mi=MouseInput(dwFlags=0x0004),
    )
    if user32.SendInput(1, ctypes.byref(button_up), ctypes.sizeof(Input)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def click_screen(x: int, y: int) -> None:
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.07)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def get_cursor_position() -> tuple[int, int]:
    point = Point()
    user32 = ctypes.windll.user32

    # MSS와 분면 좌표는 실제 픽셀 기준이므로 마우스도 물리 좌표로 취득한다.
    # GetCursorPos는 Windows 배율에 따라 논리 좌표를 반환할 수 있다.
    try:
        success = user32.GetPhysicalCursorPos(ctypes.byref(point))
    except AttributeError:
        success = user32.GetCursorPos(ctypes.byref(point))

    if not success:
        raise ctypes.WinError()
    return int(point.x), int(point.y)


def load_gray_image(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"이미지 파일이 없습니다: {path}")

    encoded = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"이미지를 읽지 못했습니다: {path}")
    return image


class GameMacro:
    def __init__(self, status_callback) -> None:
        self.status_callback = status_callback
        self.running = True
        self.busy = False
        self.stop_event = threading.Event()
        self.templates: dict[str, np.ndarray] = {}
        self.capture: mss.MSS | None = None
        self.quadrants = self._build_quadrants()
        self.failure_count = {
            quadrant: 0 for quadrant in self.quadrants
        }
        self.retry_after = {
            quadrant: 0.0 for quadrant in self.quadrants
        }
        self.next_quadrant_index = 0
        self._validate_images()

    def _build_quadrants(self) -> dict[int, Rect]:
        with mss.MSS() as capture:
            monitors = capture.monitors
        if MONITOR_B < 1 or MONITOR_B >= len(monitors):
            raise RuntimeError(
                f"MONITOR_B={MONITOR_B}가 잘못되었습니다. "
                f"사용 가능한 개별 모니터 수: {len(monitors) - 1}"
            )

        monitor = monitors[MONITOR_B]
        left, top = monitor["left"], monitor["top"]
        width, height = monitor["width"], monitor["height"]
        half_width, half_height = width // 2, height // 2

        return {
            1: Rect(left, top, half_width, half_height),
            2: Rect(left + half_width, top, width - half_width, half_height),
            3: Rect(left, top + half_height, half_width, height - half_height),
            4: Rect(
                left + half_width,
                top + half_height,
                width - half_width,
                height - half_height,
            ),
        }

    def _required_images(self) -> set[str]:
        names = {
            "rest.png",
            "001_dyied.png",
            "002_sandtimer.png",
            "01_revive.png",
            "02_menu.png",
            "03_equip_workshop.png",
            "04_dismantle_menu.png",
            "05_auto_register.png",
            "06_dismantle_execute.png",
            "07_touch_empty_space.png",
            "08_close_appraisal.png",
            "09_close_menu.png",
            "10_general_store.png",
            "12_100_percent.png",
            "13_buy.png",
            "14_close_shop.png",
            "19_quick_move.png",
            "20_confirm.png",
            "21_auto.png",
        }
        for config in QUADRANT_CONFIG.values():
            names.update(config.values())
        return names

    def _validate_images(self) -> None:
        missing = [
            str(IMAGE_DIR / name)
            for name in sorted(self._required_images())
            if not (IMAGE_DIR / name).exists()
        ]
        if missing:
            raise FileNotFoundError("필수 이미지가 없습니다:\n" + "\n".join(missing))

    def _template(self, image_name: str) -> np.ndarray:
        if image_name not in self.templates:
            self.templates[image_name] = load_gray_image(IMAGE_DIR / image_name)
        return self.templates[image_name]

    def screenshot_gray(self, rect: Rect) -> np.ndarray:
        if self.capture is None:
            raise RuntimeError("화면 캡처가 아직 초기화되지 않았습니다.")

        last_error: ScreenShotError | None = None

        for attempt in range(1, 4):
            try:
                frame = np.asarray(self.capture.grab(rect.as_mss()))
                return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
            except ScreenShotError as error:
                last_error = error
                logging.warning(
                    "BitBlt 화면 캡처 실패 (%d/3): %s",
                    attempt,
                    error,
                )

                try:
                    self.capture.close()
                except Exception:
                    pass

                time.sleep(0.3)
                self.capture = mss.MSS()

        raise ScreenShotError(
            "BitBlt 화면 캡처를 3회 재시도했지만 실패했습니다."
        ) from last_error

    def find_image(self, image_name: str, rect: Rect) -> Match | None:
        screen = self.screenshot_gray(rect)
        template = self._template(image_name)
        th, tw = template.shape[:2]

        if tw > rect.width or th > rect.height:
            raise RuntimeError(f"템플릿이 검색 범위보다 큽니다: {image_name}")

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, location = cv2.minMaxLoc(result)
        threshold = IMAGE_THRESHOLDS.get(image_name, DEFAULT_THRESHOLD)

        if confidence < threshold:
            return None

        return Match(
            x=rect.left + location[0],
            y=rect.top + location[1],
            width=tw,
            height=th,
            confidence=float(confidence),
        )

    def wait_for_image(
        self,
        image_name: str,
        rect: Rect,
        timeout: float,
    ) -> Match | None:
        deadline = time.monotonic() + timeout
        best_confidence = 0.0

        while not self.stop_event.is_set():
            match = self.find_image(image_name, rect)
            if match:
                return match

            if time.monotonic() >= deadline:
                logging.info(
                    "%s 검색 시간 초과 / 최고 confidence는 개별 프레임 로그 생략",
                    image_name,
                )
                return None
            time.sleep(0.25)

        return None

    def save_failure_capture_safe(
        self,
        quadrant: int,
        failure_name: str,
    ) -> Path | None:
        try:
            rect = self.quadrants[quadrant]
            frame = self.screenshot_gray(rect)
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)

            safe_name = "".join(
                character
                if character.isalnum() or character in ("-", "_")
                else "_"
                for character in Path(failure_name).stem
            )
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            path = DEBUG_DIR / (
                f"q{quadrant}_{safe_name}_{timestamp}.png"
            )

            success, encoded = cv2.imencode(".png", frame)
            if not success:
                raise RuntimeError("PNG 인코딩에 실패했습니다.")

            encoded.tofile(str(path))
            logging.info("실패 화면 저장: %s", path)
            return path
        except Exception as error:
            logging.warning(
                "실패 화면 저장 오류 - 자동화는 계속 진행: %s",
                error,
            )
            return None

    def register_recovery_failure(self, quadrant: int) -> int:
        self.failure_count[quadrant] += 1
        failure_index = min(
            self.failure_count[quadrant] - 1,
            len(FAILURE_COOLDOWNS_SECONDS) - 1,
        )
        cooldown = FAILURE_COOLDOWNS_SECONDS[failure_index]
        self.retry_after[quadrant] = time.monotonic() + cooldown
        return cooldown

    def reset_recovery_failure(self, quadrant: int) -> None:
        self.failure_count[quadrant] = 0
        self.retry_after[quadrant] = 0.0

    def click_image_step(
        self,
        quadrant: int,
        image_name: str,
        step_name: str,
        timeout: float,
        after_delay: float,
        required: bool = True,
    ) -> bool:
        rect = self.quadrants[quadrant]
        match = self.wait_for_image(image_name, rect, timeout)

        if not match:
            if required:
                if image_name != "01_revive.png":
                    revive_match = self.find_image("01_revive.png", rect)
                    if revive_match:
                        logging.info(
                            "%d분면 / %s 검색 실패 후 01_revive 발견 / "
                            "부활 단계부터 다시 시작 / confidence=%.4f",
                            quadrant,
                            image_name,
                            revive_match.confidence,
                        )
                        raise RestartFromRevive(
                            f"{image_name} 검색 실패 후 01_revive 발견"
                        )

                self.save_failure_capture_safe(
                    quadrant,
                    image_name,
                )
                raise StepImageNotFound(
                    f"{step_name} 이미지를 찾지 못함: {image_name}"
                )
            return False

        click_x, click_y = match.center
        time.sleep(PRE_CLICK_DELAY_SECONDS)
        click_screen(click_x, click_y)
        logging.info(
            "%d분면 / %s 클릭 / %s / %d,%d / confidence=%.4f",
            quadrant,
            step_name,
            image_name,
            click_x,
            click_y,
            match.confidence,
        )
        time.sleep(after_delay)
        return True

    def click_world_map(self, quadrant: int) -> None:
        point = WORLD_MAP_POINTS.get(quadrant)
        if point is None:
            raise RuntimeError(f"{quadrant}분면의 WORLD_MAP_POINTS가 없습니다.")

        rect = self.quadrants[quadrant]
        x, y = rect.left + point[0], rect.top + point[1]
        time.sleep(PRE_CLICK_DELAY_SECONDS)
        click_screen(x, y)
        logging.info("%d분면 / 월드맵 고정 좌표 클릭 / %d,%d", quadrant, x, y)
        time.sleep(1.0)

    def run_recovery(
        self,
        quadrant: int,
        started_from_dyied: bool = False,
        started_from_rest: bool = False,
    ) -> None:
        while not self.stop_event.is_set():
            try:
                self._run_recovery_once(
                    quadrant,
                    started_from_dyied=started_from_dyied,
                    started_from_rest=started_from_rest,
                )
                return
            except RestartFromRevive:
                started_from_dyied = False
                started_from_rest = False
                self.status_callback(
                    f"{quadrant}분면 01_revive 재발견 - 부활부터 재시작"
                )

    def _run_recovery_once(
        self,
        quadrant: int,
        started_from_dyied: bool = False,
        started_from_rest: bool = False,
    ) -> None:
        config = QUADRANT_CONFIG[quadrant]

        if started_from_dyied:
            self.click_image_step(
                quadrant,
                "001_dyied.png",
                "사망 화면",
                10,
                1.0,
            )

        if started_from_dyied or started_from_rest:
            self.click_image_step(
                quadrant,
                "002_sandtimer.png",
                "모래시계",
                15,
                1.0,
            )

        self.click_image_step(
            quadrant, "01_revive.png", "부활하기", 30, 1.5
        )

        if SKIP_STEPS_02_TO_09:
            logging.info("%d분면 / 02~09 단계 건너뜀", quadrant)
        else:
            self.click_image_step(
                quadrant, "02_menu.png", "메뉴", MENU_TIMEOUT_SECONDS, 1.0
            )
            self.click_image_step(
                quadrant, "03_equip_workshop.png", "장비공방", 15, 1.0
            )
            self.click_image_step(
                quadrant, "04_dismantle_menu.png", "분해 메뉴", 15, 0.8
            )
            self.click_image_step(
                quadrant, "05_auto_register.png", "자동 등록", 15, 0.8
            )
            dismantle = self.click_image_step(
                quadrant,
                "06_dismantle_execute.png",
                "분해 실행",
                5,
                1.0,
                required=False,
            )
            if dismantle:
                touch_found = self.click_image_step(
                    quadrant,
                    "07_touch_empty_space.png",
                    "빈 공간을 터치해주세요",
                    TOUCH_EMPTY_SPACE_TIMEOUT_SECONDS,
                    1.0,
                    required=False,
                )

                if not touch_found:
                    current_x, current_y = get_cursor_position()
                    time.sleep(PRE_CLICK_DELAY_SECONDS)
                    click_screen(current_x, current_y)
                    logging.info(
                        "%d분면 / 07 이미지 검색 실패 / "
                        "현재 마우스 위치 재클릭 / %d,%d",
                        quadrant,
                        current_x,
                        current_y,
                    )
                    time.sleep(1.0)

                self.click_image_step(
                    quadrant,
                    "08_close_appraisal.png",
                    "감정 창 닫기",
                    15,
                    0.8,
                )
            else:
                logging.info("%d분면 / 06 없음 / 07, 08 건너뜀", quadrant)

            self.click_image_step(
                quadrant, "09_close_menu.png", "메뉴 창 닫기", 15, 1.0
            )

        self.click_image_step(
            quadrant, "10_general_store.png", "잡화 상인", 20, 1.0
        )
        self.click_image_step(
            quadrant, config["potion"], "물약 선택", 15, 0.8
        )
        self.click_image_step(
            quadrant, "12_100_percent.png", "100% 수량", 15, 0.7
        )
        self.click_image_step(quadrant, "13_buy.png", "구매", 15, 1.0)
        self.click_image_step(
            quadrant, "14_close_shop.png", "상점 나가기", 15, 1.0
        )

        self.click_world_map(quadrant)
        self.click_image_step(
            quadrant, config["region"], "이동할 지역", 20, 1.0
        )
        self.click_image_step(
            quadrant, config["hunting_ground"], "이동할 사냥터", 20, 1.0
        )
        self.click_image_step(
            quadrant, config["monster"], "몬스터", 20, 0.8
        )
        self.click_image_step(
            quadrant, "19_quick_move.png", "빠른 이동", 15, 0.8
        )
        self.click_image_step(
            quadrant, "20_confirm.png", "빠른 이동 확인", 15, 1.0
        )

        logging.info("%d분면 이동 대기 시작", quadrant)
        time.sleep(20)
        self.click_image_step(
            quadrant,
            config["auto"],
            "AUTO",
            30,
            1.0,
        )

    def watch_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._watch_loop()
                return
            except Exception as error:
                logging.exception(
                    "감시 스레드 오류 - 자동 재시작: %s",
                    error,
                )
                self.busy = False
                self.capture = None

                try:
                    self.status_callback(
                        "감시 오류 복구 중 - 자동으로 다시 시작합니다"
                    )
                except Exception:
                    pass

                self.stop_event.wait(1)

    def _watch_loop(self) -> None:
        logging.info("Python 자동화 시작")
        self.capture = mss.MSS()
        try:
            while not self.stop_event.is_set():
                if not self.running or self.busy:
                    time.sleep(0.1)
                    continue

                quadrant_numbers = list(ACTIVE_QUADRANTS)
                start_index = (
                    self.next_quadrant_index
                    % len(quadrant_numbers)
                )
                ordered_quadrants = (
                    quadrant_numbers[start_index:]
                    + quadrant_numbers[:start_index]
                )
                self.next_quadrant_index = (
                    start_index + 1
                ) % len(quadrant_numbers)

                for quadrant in ordered_quadrants:
                    if self.stop_event.is_set() or not self.running:
                        break

                    if time.monotonic() < self.retry_after[quadrant]:
                        continue

                    rect = self.quadrants[quadrant]

                    try:
                        rest_match = self.find_image("rest.png", rect)
                        dyied_match = None
                        revive_match = None

                        if rest_match is None:
                            dyied_match = self.find_image(
                                "001_dyied.png",
                                rect,
                            )

                        if rest_match is None and dyied_match is None:
                            revive_match = self.find_image(
                                "01_revive.png",
                                rect,
                            )

                        started_from_rest = rest_match is not None
                        started_from_dyied = dyied_match is not None
                        match = rest_match or dyied_match or revive_match
                    except ScreenShotError as error:
                        logging.error(
                            "화면 캡처가 계속 실패하여 이번 검색을 건너뜁니다: %s",
                            error,
                        )
                        self.status_callback(
                            "화면 캡처 재연결 중 - 자동으로 다시 시도합니다"
                        )
                        time.sleep(1)
                        break
                    except Exception as error:
                        logging.exception(
                            "이미지 감시 중 오류 - 자동으로 계속 진행: %s",
                            error,
                        )
                        self.status_callback(
                            "감시 오류 발생 - 자동으로 다시 시도합니다"
                        )
                        time.sleep(1)
                        break

                    if not match:
                        continue

                    self.busy = True
                    self.status_callback(f"{quadrant}분면 복구 작업 중")
                    logging.info(
                        "%d분면에서 %s 발견 / confidence=%.4f",
                        quadrant,
                        (
                            "rest.png"
                            if started_from_rest
                            else (
                                "001_dyied.png"
                                if started_from_dyied
                                else "01_revive.png"
                            )
                        ),
                        match.confidence,
                    )
                    recovery_succeeded = False
                    try:
                        self.run_recovery(
                            quadrant,
                            started_from_dyied=started_from_dyied,
                            started_from_rest=started_from_rest,
                        )
                        recovery_succeeded = True
                        self.reset_recovery_failure(quadrant)
                        logging.info("%d분면 복구 완료", quadrant)
                    except Exception as error:
                        if not isinstance(error, StepImageNotFound):
                            self.save_failure_capture_safe(
                                quadrant,
                                "recovery_failure",
                            )
                        cooldown = self.register_recovery_failure(
                            quadrant
                        )
                        logging.error(
                            "%d분면 복구 실패 / 연속 %d회 / "
                            "%d초 쿨다운 후 재시도 / 원인: %s",
                            quadrant,
                            self.failure_count[quadrant],
                            cooldown,
                            error,
                        )
                        self.status_callback(
                            f"{quadrant}분면 실패 - "
                            f"{cooldown}초 후 재시도, 다음 분면 확인"
                        )
                    finally:
                        self.busy = False
                        self.status_callback(
                            "감시 중" if self.running else "일시정지"
                        )

                    if recovery_succeeded:
                        break

                time.sleep(SCAN_INTERVAL_SECONDS)
        finally:
            try:
                if self.capture is not None:
                    self.capture.close()
            except Exception:
                logging.exception("화면 캡처 종료 중 오류")
            self.capture = None

    def set_running(self, running: bool) -> None:
        self.running = running

    def stop(self) -> None:
        self.stop_event.set()


class ControlWindow:
    COPY_COORDINATES_HOTKEY_ID = 1
    TEST_CLICK_HOTKEY_ID = 2

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("게임 매크로 제어 - Python/OpenCV")
        self.root.geometry("900x650")
        self.root.minsize(760, 560)
        self.root.resizable(True, True)
        self.root.option_add("*Font", ("Malgun Gothic", 12))
        self.status_var = tk.StringVar(value="초기화 중")
        self.monitor_var = tk.StringVar(value="모니터 B 좌표 확인 중")
        self.coordinate_var = tk.StringVar(value="마우스 좌표 불러오는 중...")
        self.coordinate_visible = True
        self.macro: GameMacro | None = None
        self.hotkey_thread_id: int | None = None
        self.hotkey_thread: threading.Thread | None = None

        tk.Label(
            self.root,
            text="모니터 B 4분할 자동화",
            font=("Malgun Gothic", 20, "bold"),
        ).pack(pady=(28, 18))

        tk.Label(
            self.root,
            textvariable=self.status_var,
            width=68,
            height=5,
            relief="groove",
            anchor="center",
            font=("Malgun Gothic", 13),
        ).pack(padx=28)

        tk.Label(
            self.root,
            textvariable=self.monitor_var,
            width=68,
            height=2,
            relief="groove",
            anchor="center",
            font=("Malgun Gothic", 12),
        ).pack(padx=28, pady=(10, 0))

        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=22)

        self.toggle_button = tk.Button(
            button_frame,
            text="자동화 일시정지",
            width=25,
            height=2,
            command=self.toggle,
        )
        self.toggle_button.grid(row=0, column=0, padx=6)

        self.coordinate_button = tk.Button(
            button_frame,
            text="좌표 표시 끄기",
            width=25,
            height=2,
            command=self.toggle_coordinates,
        )
        self.coordinate_button.grid(row=0, column=1, padx=6)

        coordinate_frame = tk.Frame(self.root)
        coordinate_frame.pack(pady=(0, 18))

        tk.Label(
            coordinate_frame,
            textvariable=self.coordinate_var,
            width=50,
            height=4,
            relief="groove",
            anchor="center",
            font=("Malgun Gothic", 13),
        ).grid(row=0, column=0, padx=(0, 6))

        tk.Button(
            coordinate_frame,
            text="현재 좌표 복사",
            width=16,
            height=2,
            command=self.copy_coordinates,
        ).grid(row=0, column=1)

        tk.Button(
            self.root,
            text="종료",
            width=52,
            height=2,
            command=self.close,
        ).pack()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.update_coordinates()

    def set_status(self, text: str) -> None:
        self.root.after(0, self.status_var.set, text)

    def toggle(self) -> None:
        if not self.macro:
            return
        self.macro.set_running(not self.macro.running)
        self.toggle_button.config(
            text="자동화 일시정지" if self.macro.running else "자동화 시작"
        )
        self.set_status("감시 중" if self.macro.running else "일시정지")

    def cursor_details(self) -> tuple[int, int, int, int, int]:
        x, y = get_cursor_position()
        quadrant = 0
        relative_x = 0
        relative_y = 0

        if self.macro:
            for number, rect in self.macro.quadrants.items():
                if rect.left <= x < rect.right and rect.top <= y < rect.bottom:
                    quadrant = number
                    relative_x = x - rect.left
                    relative_y = y - rect.top
                    break

        return x, y, quadrant, relative_x, relative_y

    def update_coordinates(self) -> None:
        if self.coordinate_visible:
            try:
                x, y, quadrant, relative_x, relative_y = self.cursor_details()
                text = f"화면 X: {x}  Y: {y}"
                if quadrant:
                    text += (
                        f"\n{quadrant}분면 상대 X: {relative_x}  "
                        f"Y: {relative_y}"
                    )
                else:
                    text += "\n모니터 B 범위 밖"
                self.coordinate_var.set(text)
            except Exception as exc:
                self.coordinate_var.set(f"좌표 취득 실패: {exc}")

        self.root.after(100, self.update_coordinates)

    def toggle_coordinates(self) -> None:
        self.coordinate_visible = not self.coordinate_visible
        self.coordinate_button.config(
            text=(
                "좌표 표시 끄기"
                if self.coordinate_visible
                else "좌표 표시 켜기"
            )
        )
        if not self.coordinate_visible:
            self.coordinate_var.set("마우스 좌표 표시: OFF")

    def copy_coordinates(self) -> None:
        try:
            x, y, quadrant, relative_x, relative_y = self.cursor_details()
            if quadrant:
                text = (
                    f"{x}, {y} | {quadrant}분면 상대: "
                    f"{relative_x}, {relative_y}"
                )
            else:
                text = f"{x}, {y}"

            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
            self.set_status(f"좌표 복사 완료: {text}")
        except Exception as exc:
            messagebox.showerror("좌표 취득 실패", str(exc))

    def start_hotkey_listener(self) -> None:
        self.hotkey_thread = threading.Thread(
            target=self.hotkey_loop,
            name="coordinate-hotkey",
            daemon=True,
        )
        self.hotkey_thread.start()

    def test_click(self) -> None:
        try:
            x, y = get_cursor_position()
            left_click_held()
            logging.info("F5 테스트 클릭 / %d,%d / 유지 80ms", x, y)
            self.root.after(
                0,
                self.set_status,
                f"F5 테스트 클릭 완료: {x}, {y} (80ms)",
            )
        except Exception as exc:
            logging.exception("F5 테스트 클릭 실패: %s", exc)
            try:
                self.root.after(
                    0,
                    self.set_status,
                    f"F5 테스트 클릭 실패: {exc}",
                )
            except tk.TclError:
                pass

    def hotkey_loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.hotkey_thread_id = int(kernel32.GetCurrentThreadId())

        # Ctrl + Shift + C를 다른 창이 활성화된 상태에서도 받을 수 있게 한다.
        modifiers = 0x0002 | 0x0004 | 0x4000  # CONTROL | SHIFT | NOREPEAT
        registered = user32.RegisterHotKey(
            None,
            self.COPY_COORDINATES_HOTKEY_ID,
            modifiers,
            ord("C"),
        )
        if not registered:
            logging.warning("Ctrl+Shift+C 전역 단축키 등록 실패")
            try:
                self.root.after(
                    0,
                    self.set_status,
                    "Ctrl+Shift+C 단축키 등록 실패 (다른 앱에서 사용 중일 수 있음)",
                )
            except tk.TclError:
                pass
            return

        click_registered = user32.RegisterHotKey(
            None,
            self.TEST_CLICK_HOTKEY_ID,
            0x4000,  # MOD_NOREPEAT
            0x74,  # F5
        )
        if not click_registered:
            user32.UnregisterHotKey(
                None,
                self.COPY_COORDINATES_HOTKEY_ID,
            )
            logging.warning("F5 테스트 클릭 전역 단축키 등록 실패")
            try:
                self.root.after(
                    0,
                    self.set_status,
                    "F5 단축키 등록 실패 (다른 앱에서 사용 중일 수 있음)",
                )
            except tk.TclError:
                pass
            return

        logging.info("Ctrl+Shift+C 좌표 복사 / F5 테스트 클릭 단축키 등록 완료")
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:  # WM_HOTKEY
                    if message.wParam == self.COPY_COORDINATES_HOTKEY_ID:
                        try:
                            self.root.after(0, self.copy_coordinates)
                        except tk.TclError:
                            break
                    elif message.wParam == self.TEST_CLICK_HOTKEY_ID:
                        self.test_click()
        finally:
            user32.UnregisterHotKey(
                None,
                self.COPY_COORDINATES_HOTKEY_ID,
            )
            user32.UnregisterHotKey(
                None,
                self.TEST_CLICK_HOTKEY_ID,
            )
            logging.info("좌표 복사 / 테스트 클릭 전역 단축키 해제")

    def stop_hotkey_listener(self) -> None:
        if self.hotkey_thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(
                self.hotkey_thread_id,
                0x0012,  # WM_QUIT
                0,
                0,
            )
            self.hotkey_thread_id = None

    def close(self) -> None:
        logging.info("UI 종료 요청 감지")
        if self.macro:
            self.macro.stop()
        self.stop_hotkey_listener()
        self.root.destroy()

    def run(self) -> None:
        try:
            self.macro = GameMacro(self.set_status)
        except Exception as exc:
            messagebox.showerror("초기화 실패", str(exc))
            self.root.destroy()
            return

        monitor_left = min(rect.left for rect in self.macro.quadrants.values())
        monitor_top = min(rect.top for rect in self.macro.quadrants.values())
        monitor_right = max(rect.right for rect in self.macro.quadrants.values())
        monitor_bottom = max(rect.bottom for rect in self.macro.quadrants.values())
        self.monitor_var.set(
            f"모니터 B (MSS {MONITOR_B}번): "
            f"{monitor_left}, {monitor_top} ~ "
            f"{monitor_right - 1}, {monitor_bottom - 1}  "
            f"({monitor_right - monitor_left}×{monitor_bottom - monitor_top})"
        )

        self.set_status("감시 중")
        self.start_hotkey_listener()
        threading.Thread(target=self.macro.watch_loop, daemon=True).start()
        self.root.mainloop()
        logging.info("Tkinter 메인 루프 종료")


def main() -> None:
    enable_dpi_awareness()
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        encoding="utf-8",
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    ControlWindow().run()


if __name__ == "__main__":
    try:
        if ensure_admin():
            hide_console_window()
            main()
    except KeyboardInterrupt:
        logging.info("사용자 Ctrl+C 입력으로 정상 종료")
    except Exception as error:
        logging.exception("프로그램 최상위 오류로 안전 종료: %s", error)
