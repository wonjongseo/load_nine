from __future__ import annotations

import ctypes
import logging
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox

import cv2
import mss
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "images"
LOG_FILE = BASE_DIR / "automation_python.log"
DEBUG_DIR = BASE_DIR / "debug_capture_python"

# mss.monitors 기준 번호입니다. 0은 전체 가상 화면, 1부터 개별 모니터입니다.
MONITOR_B = 1
SCAN_INTERVAL_SECONDS = 0.7
DEFAULT_THRESHOLD = 0.78
MENU_TIMEOUT_SECONDS = 60
PRE_CLICK_DELAY_SECONDS = 0.5

# 단계별 검증용 플래그
SKIP_STEPS_02_TO_09 = False

# 각 분면 왼쪽 위를 (0, 0)으로 하는 상대좌표입니다.
# None인 분면은 월드맵 단계에서 안전하게 중단합니다.
WORLD_MAP_POINTS: dict[int, tuple[int, int] | None] = {
    1: None,
    2: (148, 177),
    3: (153, 149),
    4: (149, 141),
}

# 이미지별 confidence 기준값입니다.
# 값이 높을수록 엄격하며 일반적으로 0.70~0.90 범위를 사용합니다.
IMAGE_THRESHOLDS = {
    "01_revive.png": 0.70,
    "02_menu.png": 0.68,
}

QUADRANT_CONFIG = {
    1: {
        "potion": "quadrant_1/11_potion.png",
        "region": "quadrant_1/16_region.png",
        "hunting_ground": "quadrant_1/17_hunting_ground.png",
        "monster": "quadrant_1/18_monster.png",
    },
    2: {
        "potion": "quadrant_2/11_potion.png",
        "region": "quadrant_2/16_region.png",
        "hunting_ground": "quadrant_2/17_hunting_ground.png",
        "monster": "quadrant_2/18_monster.png",
    },
    3: {
        "potion": "quadrant_3/11_potion.png",
        "region": "quadrant_3/16_region.png",
        "hunting_ground": "quadrant_3/17_hunting_ground.png",
        "monster": "quadrant_3/18_monster.png",
    },
    4: {
        "potion": "quadrant_4/11_potion.png",
        "region": "quadrant_4/16_region.png",
        "hunting_ground": "quadrant_4/17_hunting_ground.png",
        "monster": "quadrant_4/18_monster.png",
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


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


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
        frame = np.asarray(self.capture.grab(rect.as_mss()))
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)

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
                self.save_failure_capture(quadrant, image_name)
                raise RuntimeError(f"{step_name} 이미지를 찾지 못함: {image_name}")
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

    def run_recovery(self, quadrant: int) -> None:
        config = QUADRANT_CONFIG[quadrant]

        self.click_image_step(
            quadrant, "01_revive.png", "부활하기", 10, 1.5
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
                    10,
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
        time.sleep(15)
        self.click_image_step(quadrant, "21_auto.png", "AUTO", 30, 1.0)

    def save_failure_capture(self, quadrant: int, image_name: str) -> Path:
        if self.capture is None:
            raise RuntimeError("화면 캡처가 아직 초기화되지 않았습니다.")
        DEBUG_DIR.mkdir(exist_ok=True)
        rect = self.quadrants[quadrant]
        frame = np.asarray(self.capture.grab(rect.as_mss()))
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = DEBUG_DIR / f"q{quadrant}_{Path(image_name).stem}_{timestamp}.png"
        cv2.imencode(".png", frame)[1].tofile(str(path))
        logging.info("실패 화면 저장: %s", path)
        return path

    def watch_loop(self) -> None:
        logging.info("Python 자동화 시작")
        self.capture = mss.MSS()
        try:
            while not self.stop_event.is_set():
                if not self.running or self.busy:
                    time.sleep(0.1)
                    continue

                for quadrant, rect in self.quadrants.items():
                    if self.stop_event.is_set() or not self.running:
                        break

                    match = self.find_image("01_revive.png", rect)
                    if not match:
                        continue

                    self.busy = True
                    self.status_callback(f"{quadrant}분면 복구 작업 중")
                    logging.info(
                        "%d분면에서 사망 발견 / confidence=%.4f",
                        quadrant,
                        match.confidence,
                    )
                    try:
                        self.run_recovery(quadrant)
                        logging.info("%d분면 복구 완료", quadrant)
                    except Exception:
                        logging.exception("%d분면 복구 실패", quadrant)
                        self.status_callback(f"{quadrant}분면 복구 실패 - 로그 확인")
                        time.sleep(3)
                    finally:
                        self.busy = False
                        self.status_callback(
                            "감시 중" if self.running else "일시정지"
                        )
                    break

                time.sleep(SCAN_INTERVAL_SECONDS)
        finally:
            self.capture.close()
            self.capture = None

    def set_running(self, running: bool) -> None:
        self.running = running

    def stop(self) -> None:
        self.stop_event.set()


class ControlWindow:
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

    def close(self) -> None:
        if self.macro:
            self.macro.stop()
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
        threading.Thread(target=self.macro.watch_loop, daemon=True).start()
        self.root.mainloop()


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
    main()
