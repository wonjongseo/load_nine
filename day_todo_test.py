from __future__ import annotations

import argparse
import ctypes
import logging
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import mss
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "day_todo_test.log"
THRESHOLD = 0.82
SCAN_INTERVAL = 0.15
PRE_SEARCH_DELAY = 0.3
CLICK_HOLD_SECONDS = 0.08
DEFAULT_TIMEOUT = 15.0


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
class Match:
    x: int
    y: int
    confidence: float


IMAGE_NAMES = {
    "menu": "02_menu.png",
    "proof": "todo_proof.png",
    "card": "todo_card.png",
    "mission_select": "todo_mission_select.png",
    "proof_exit": "todo_proof_exit.png",
    "guild": "todo_guild.png",
    "guild_donation": "todo_guild_donation.png",
    "donate": "todo_donate.png",
    "guild_donation_exit": "todo_guild_donation_exit.png",
    "guild_exit": "todo_guild_exit.png",
    "close_shop": "14_close_shop.png",
    "event_shop": "event_shop.png",
    "bulk_buy": "todo_bulk_buy.png",
    "buy": "13_buy.png",
}


class TodoTest:
    def __init__(
        self,
        monitor: int,
        quadrant: int,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.monitor = monitor
        self.quadrant = quadrant
        self.image_root = BASE_DIR / "macro_images" / f"monitor_{monitor}"
        self.stop_event = stop_event or threading.Event()
        self.templates: dict[Path, np.ndarray] = {}
        self.image_paths = {
            key: self.resolve_image(filename)
            for key, filename in IMAGE_NAMES.items()
        }
        self.validate_images()

    def resolve_image(self, filename: str) -> Path:
        candidates = [
            self.image_root / f"quadrant_{self.quadrant}" / filename,
            self.image_root / filename,
        ]
        if self.monitor == 2:
            candidates.append(self.image_root / "quadrant_2" / filename)
        candidates.append(BASE_DIR / "images" / filename)
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def validate_images(self) -> None:
        missing = [
            f"{key}: {path}"
            for key, path in self.image_paths.items()
            if not path.is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "필요한 이미지가 없습니다:\n" + "\n".join(missing)
            )

    def quadrant_rect(self, capture: mss.MSS) -> Rect:
        if self.monitor >= len(capture.monitors):
            raise RuntimeError(
                f"모니터 {self.monitor}을 찾을 수 없습니다. "
                f"감지된 개별 모니터 수: {len(capture.monitors) - 1}"
            )
        monitor = capture.monitors[self.monitor]
        half_width = monitor["width"] // 2
        half_height = monitor["height"] // 2
        column = (self.quadrant - 1) % 2
        row = (self.quadrant - 1) // 2
        left = monitor["left"] + column * half_width
        top = monitor["top"] + row * half_height
        width = half_width if column == 0 else monitor["width"] - half_width
        height = half_height if row == 0 else monitor["height"] - half_height
        return Rect(left, top, width, height)

    def template(self, path: Path) -> np.ndarray:
        cached = self.templates.get(path)
        if cached is not None:
            return cached
        encoded = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise RuntimeError(f"이미지를 읽지 못했습니다: {path}")
        self.templates[path] = image
        return image

    def find(self, capture: mss.MSS, rect: Rect, key: str) -> Match | None:
        frame = np.asarray(capture.grab(rect.as_mss()))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        template = self.template(self.image_paths[key])
        height, width = template.shape
        if height > gray.shape[0] or width > gray.shape[1]:
            return None
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, location = cv2.minMaxLoc(result)
        if confidence < THRESHOLD:
            return None
        return Match(
            rect.left + location[0] + width // 2,
            rect.top + location[1] + height // 2,
            float(confidence),
        )

    @staticmethod
    def escape_pressed() -> bool:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)

    def stopped(self) -> bool:
        return self.stop_event.is_set() or self.escape_pressed()

    def wait_or_stop(self, seconds: float) -> None:
        if self.stop_event.wait(seconds) or self.escape_pressed():
            raise KeyboardInterrupt

    @staticmethod
    def scroll_up(x: int, y: int) -> None:
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        drag_distance = 240
        drag_steps = 12
        try:
            for step in range(1, drag_steps + 1):
                next_y = y - round(drag_distance * step / drag_steps)
                user32.SetCursorPos(int(x), int(next_y))
                time.sleep(0.025)
        finally:
            user32.mouse_event(0x0004, 0, 0, 0, 0)

    def click_proof_with_scroll(
        self,
        capture: mss.MSS,
        rect: Rect,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> tuple[int, int]:
        self.wait_or_stop(PRE_SEARCH_DELAY)
        deadline = time.monotonic() + timeout
        guild_anchor: tuple[int, int] | None = None
        while time.monotonic() < deadline:
            if self.stopped():
                raise KeyboardInterrupt
            proof_match = self.find(capture, rect, "proof")
            if proof_match:
                self.click(proof_match.x, proof_match.y)
                logging.info(
                    "증명의 사고 클릭 / %d,%d / confidence=%.4f",
                    proof_match.x,
                    proof_match.y,
                    proof_match.confidence,
                )
                return proof_match.x, proof_match.y

            guild_match = self.find(capture, rect, "guild")
            if guild_match:
                guild_anchor = (guild_match.x, guild_match.y)
            if guild_anchor:
                self.scroll_up(*guild_anchor)
                logging.info(
                    "증명의 사고 미감지 / todo_guild 위치에서 위로 드래그 / %d,%d",
                    guild_anchor[0],
                    guild_anchor[1],
                )
                self.wait_or_stop(0.5)
            else:
                self.wait_or_stop(SCAN_INTERVAL)
        raise RuntimeError(
            f"증명의 사고 이미지를 {timeout:g}초 동안 찾지 못했습니다."
        )

    @staticmethod
    def click(x: int, y: int) -> None:
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(CLICK_HOLD_SECONDS)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def wait_and_click(
        self,
        capture: mss.MSS,
        rect: Rect,
        key: str,
        label: str,
        timeout: float = DEFAULT_TIMEOUT,
        skip_on_timeout: bool = False,
    ) -> tuple[int, int] | None:
        self.wait_or_stop(PRE_SEARCH_DELAY)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.stopped():
                raise KeyboardInterrupt
            match = self.find(capture, rect, key)
            if match:
                self.click(match.x, match.y)
                logging.info(
                    "%s 클릭 / %d,%d / confidence=%.4f",
                    label,
                    match.x,
                    match.y,
                    match.confidence,
                )
                return match.x, match.y
            self.wait_or_stop(SCAN_INTERVAL)

        if skip_on_timeout:
            logging.info("%s %g초 미감지 / 다음 단계로 이동", label, timeout)
            return None
        raise RuntimeError(f"{label} 이미지를 {timeout:g}초 동안 찾지 못했습니다.")

    def run(self) -> None:
        logging.info(
            "모니터 %d / %d분면 TODO 테스트 시작",
            self.monitor,
            self.quadrant,
        )
        with mss.MSS() as capture:
            rect = self.quadrant_rect(capture)
            self.wait_and_click(capture, rect, "menu", "02 메뉴")
            self.click_proof_with_scroll(capture, rect)
            self.wait_and_click(capture, rect, "card", "카드")
            self.wait_and_click(capture, rect, "mission_select", "임무 선택")
            self.wait_and_click(capture, rect, "proof_exit", "증명의 사고 나가기")

            guild_point = self.wait_and_click(capture, rect, "guild", "길드")
            self.wait_or_stop(5.0)
            self.click(*guild_point)
            logging.info("길드 클릭 5초 후 저장 좌표 터치 / %d,%d", *guild_point)
            self.wait_and_click(capture, rect, "guild_donation", "길드 기부")

            for repetition in range(1, 4):
                donate_point = self.wait_and_click(
                    capture,
                    rect,
                    "donate",
                    f"기부 {repetition}/3",
                )
                self.wait_or_stop(5.0)
                self.click(*donate_point)
                logging.info(
                    "기부 %d/3 클릭 5초 후 저장 좌표 터치 / %d,%d",
                    repetition,
                    donate_point[0],
                    donate_point[1],
                )

            self.wait_and_click(
                capture, rect, "guild_donation_exit", "길드 기부 나가기"
            )
            self.wait_and_click(capture, rect, "guild_exit", "길드 나가기")
            self.wait_and_click(capture, rect, "event_shop", "이벤트 상점")

            logging.info("일괄 구매 전 5초 대기")
            self.wait_or_stop(5.0)
            self.wait_and_click(capture, rect, "bulk_buy", "일괄 구매")
            buy_point = self.wait_and_click(
                capture,
                rect,
                "buy",
                "13 구매",
                timeout=5.0,
                skip_on_timeout=True,
            )
            if buy_point is None:
                logging.info("13 구매 미감지 / 16번 구매 결과 확인 스킵")
            else:
                self.wait_or_stop(5.0)
                self.click(*buy_point)
                logging.info(
                    "13 구매 클릭 5초 후 저장 좌표 터치 / %d,%d",
                    buy_point[0],
                    buy_point[1],
                )
            self.wait_and_click(capture, rect, "close_shop", "14 상점 나가기")
        logging.info(
            "모니터 %d / %d분면 TODO 테스트 완료",
            self.monitor,
            self.quadrant,
        )


def choose_target() -> tuple[int, int]:
    import tkinter as tk

    selected = {"value": (0, 0)}
    root = tk.Tk()
    root.title("TODO 버튼 테스트")
    root.resizable(False, False)
    tk.Label(root, text="테스트할 모니터와 분면을 선택하세요.", padx=20, pady=12).pack()
    button_frame = tk.Frame(root, padx=12, pady=8)
    button_frame.pack()

    def select(monitor: int, quadrant: int) -> None:
        selected["value"] = (monitor, quadrant)
        root.destroy()

    for monitor in range(1, 3):
        for quadrant in range(1, 5):
            tk.Button(
                button_frame,
                text=f"모니터 {monitor} / {quadrant}분면",
                width=18,
                command=lambda m=monitor, q=quadrant: select(m, q),
            ).grid(row=monitor - 1, column=quadrant - 1, padx=5, pady=5)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return selected["value"]


def main() -> int:
    parser = argparse.ArgumentParser(description="TODO 루틴 단독 테스트")
    parser.add_argument("--monitor", type=int, choices=range(1, 3))
    parser.add_argument("--quadrant", type=int, choices=range(1, 5))
    args = parser.parse_args()
    if args.monitor and args.quadrant:
        monitor, quadrant = args.monitor, args.quadrant
    else:
        monitor, quadrant = choose_target()
    if not monitor or not quadrant:
        return 0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    try:
        TodoTest(monitor, quadrant).run()
        return 0
    except KeyboardInterrupt:
        logging.info("ESC 감지 / 테스트 중지")
        return 130
    except Exception as error:
        logging.exception("TODO 테스트 실패: %s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
