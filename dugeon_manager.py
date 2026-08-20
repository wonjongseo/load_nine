from __future__ import annotations

import argparse
import ctypes
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import cv2
import mss
import numpy as np

BASE_DIR = Path(__file__).resolve().parent

IMAGE_REVIVE = BASE_DIR / "images" / "01_revive.png"
IMAGE_MENU = BASE_DIR / "images" / "02_menu.png"
IMAGE_AUTO = BASE_DIR / "images" / "21_auto.png"

TEST_IMAGE_DIR = BASE_DIR / "images" / "test"
IMAGE_DUNGEON = TEST_IMAGE_DIR / "dungeon.png"
IMAGE_DUNGEON_A = TEST_IMAGE_DIR / "dungeon_A.png"
IMAGE_DUNGEON_B = TEST_IMAGE_DIR / "dungeon_B.png"
IMAGE_ENTER = TEST_IMAGE_DIR / "enter.png"
IMAGE_IN_DUNGEON = TEST_IMAGE_DIR / "in_dungeon.png"
IMAGE_EXIT = TEST_IMAGE_DIR / "exit.png"

DB_PATH = BASE_DIR / "dungeon_status.db"
LOG_PATH = BASE_DIR / "dungeon_manager.log"

DEFAULT_THRESHOLD = 0.82
DEFAULT_DUNGEON_DURATION_SECONDS = 60 * 60
SCAN_INTERVAL_SECONDS = 0.20
POST_CLICK_WAIT_SECONDS = 1.0
STEP_TIMEOUT_SECONDS = 30.0

# 테스트에서는 던전에서 수동으로 나가기를 눌러 정상 1시간 종료를 대신합니다.
# in_dungeon.png가 이 시간 이상 연속 미검출되면 현재 던전을 완료 처리합니다.
IN_DUNGEON_MISSING_SECONDS = 5.0
AUTO_WAIT_TIMEOUT_SECONDS = 10.0

MOUSE_CLICK_LOCK = threading.Lock()

user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def click_screen(x: int, y: int) -> None:
    with MOUSE_CLICK_LOCK:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.08)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    def as_mss(self) -> dict:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


def parse_target_key(key: str) -> tuple[int, int]:
    if not key.startswith("m") or "q" not in key:
        raise ValueError(f"잘못된 target key: {key}")
    monitor_text, quadrant_text = key[1:].split("q", 1)
    monitor_no = int(monitor_text)
    quadrant_no = int(quadrant_text)
    if quadrant_no not in (1, 2, 3, 4):
        raise ValueError(f"분면은 1~4만 가능합니다: {key}")
    return monitor_no, quadrant_no


def get_target_rect(sct: mss.mss, key: str) -> Rect:
    monitor_no, quadrant_no = parse_target_key(key)
    if monitor_no >= len(sct.monitors):
        raise ValueError(
            f"{key}: 모니터 {monitor_no}를 찾을 수 없습니다. "
            f"현재 물리 모니터 수={len(sct.monitors) - 1}"
        )

    mon = sct.monitors[monitor_no]
    half_w = mon["width"] // 2
    half_h = mon["height"] // 2

    col = 0 if quadrant_no in (1, 3) else 1
    row = 0 if quadrant_no in (1, 2) else 1

    left = mon["left"] + col * half_w
    top = mon["top"] + row * half_h
    width = half_w if col == 0 else mon["width"] - half_w
    height = half_h if row == 0 else mon["height"] - half_h

    return Rect(left, top, width, height)


def all_target_keys() -> list[str]:
    with mss.MSS() as sct:
        count = len(sct.monitors) - 1
    return [
        f"m{monitor_no}q{quadrant_no}"
        for monitor_no in range(1, count + 1)
        for quadrant_no in range(1, 5)
    ]


class ImageMatcher:
    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self._cache: dict[str, np.ndarray] = {}

    def template(self, path: Path) -> Optional[np.ndarray]:
        key = str(path)
        if key in self._cache:
            return self._cache[key]

        image = cv2.imread(key, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error("이미지를 읽을 수 없음: %s", path)
            return None

        self._cache[key] = image
        return image

    def find(
        self,
        gray: np.ndarray,
        path: Path,
        threshold: Optional[float] = None,
    ) -> Optional[tuple[int, int, float, int, int]]:
        template = self.template(path)
        if template is None:
            return None

        th, tw = template.shape[:2]
        gh, gw = gray.shape[:2]
        if th > gh or tw > gw:
            return None

        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        effective_threshold = self.threshold if threshold is None else threshold
        if max_val < effective_threshold:
            return None

        x, y = max_loc
        return x, y, float(max_val), tw, th


class DungeonRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dungeon_usage (
                    target_key TEXT NOT NULL,
                    dungeon TEXT NOT NULL,
                    usage_date TEXT NOT NULL,
                    accumulated_seconds REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'NOT_STARTED',
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (target_key, dungeon, usage_date)
                )
                """
            )
            conn.commit()

    def _ensure(self, target_key: str, dungeon: str) -> None:
        today = date.today().isoformat()
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO dungeon_usage
                    (target_key, dungeon, usage_date, accumulated_seconds, status, updated_at)
                VALUES (?, ?, ?, 0, 'NOT_STARTED', ?)
                """,
                (target_key, dungeon, today, time.time()),
            )
            conn.commit()

    def get(self, target_key: str, dungeon: str) -> sqlite3.Row:
        self._ensure(target_key, dungeon)
        today = date.today().isoformat()
        with self._lock, self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM dungeon_usage
                WHERE target_key = ? AND dungeon = ? AND usage_date = ?
                """,
                (target_key, dungeon, today),
            ).fetchone()
        assert row is not None
        return row

    def add_elapsed(self, target_key: str, dungeon: str, seconds: float, total_required: float) -> float:
        row = self.get(target_key, dungeon)
        new_total = float(row["accumulated_seconds"]) + max(0.0, seconds)
        status = "COMPLETED" if new_total >= total_required else "IN_PROGRESS"
        today = date.today().isoformat()

        with self._lock, self.connect() as conn:
            conn.execute(
                """
                UPDATE dungeon_usage
                SET accumulated_seconds = ?, status = ?, updated_at = ?
                WHERE target_key = ? AND dungeon = ? AND usage_date = ?
                """,
                (new_total, status, time.time(), target_key, dungeon, today),
            )
            conn.commit()
        return new_total

    def mark_started(self, target_key: str, dungeon: str) -> None:
        row = self.get(target_key, dungeon)
        if row["status"] == "COMPLETED":
            return
        today = date.today().isoformat()
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                UPDATE dungeon_usage
                SET status = 'IN_PROGRESS', updated_at = ?
                WHERE target_key = ? AND dungeon = ? AND usage_date = ?
                """,
                (time.time(), target_key, dungeon, today),
            )
            conn.commit()

    def mark_completed(self, target_key: str, dungeon: str, total_required: float) -> None:
        self._ensure(target_key, dungeon)
        today = date.today().isoformat()
        with self._lock, self.connect() as conn:
            conn.execute(
                """
                UPDATE dungeon_usage
                SET accumulated_seconds = CASE
                        WHEN accumulated_seconds < ? THEN ?
                        ELSE accumulated_seconds
                    END,
                    status = 'COMPLETED',
                    updated_at = ?
                WHERE target_key = ? AND dungeon = ? AND usage_date = ?
                """,
                (total_required, total_required, time.time(), target_key, dungeon, today),
            )
            conn.commit()

    def reset_today(self, target_key: Optional[str] = None) -> None:
        today = date.today().isoformat()
        with self._lock, self.connect() as conn:
            if target_key:
                conn.execute(
                    "DELETE FROM dungeon_usage WHERE usage_date = ? AND target_key = ?",
                    (today, target_key),
                )
            else:
                conn.execute("DELETE FROM dungeon_usage WHERE usage_date = ?", (today,))
            conn.commit()


class DungeonRunner(threading.Thread):
    DUNGEON_ORDER = ("A", "B")

    def __init__(
        self,
        target_key: str,
        repo: DungeonRepository,
        matcher: ImageMatcher,
        dungeon_duration_seconds: float,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name=f"DungeonRunner-{target_key}", daemon=True)
        self.target_key = target_key
        self.repo = repo
        self.matcher = matcher
        self.duration = dungeon_duration_seconds
        self.stop_event = stop_event
        self.current_dungeon: Optional[str] = None
        self.state = "SELECT_DUNGEON"
        self.state_started_at = time.monotonic()
        self.session_started_at: Optional[float] = None
        self.last_in_dungeon_seen_at: Optional[float] = None
        self.auto_wait_started_at: Optional[float] = None

    def set_state(self, state: str) -> None:
        if self.state != state:
            logging.info("[%s] %s -> %s", self.target_key, self.state, state)
        self.state = state
        self.state_started_at = time.monotonic()

    def image_for_dungeon(self) -> Path:
        if self.current_dungeon == "A":
            return IMAGE_DUNGEON_A
        if self.current_dungeon == "B":
            return IMAGE_DUNGEON_B
        raise RuntimeError("current_dungeon이 선택되지 않았습니다.")

    def select_next_dungeon(self) -> bool:
        for dungeon in self.DUNGEON_ORDER:
            row = self.repo.get(self.target_key, dungeon)
            if row["status"] != "COMPLETED":
                self.current_dungeon = dungeon
                logging.info(
                    "[%s] 오늘 던전 %s 선택: status=%s, 누적=%.1fs / %.1fs",
                    self.target_key,
                    dungeon,
                    row["status"],
                    float(row["accumulated_seconds"]),
                    self.duration,
                )
                return True

        self.current_dungeon = None
        logging.info("[%s] 오늘 A/B 던전 모두 완료", self.target_key)
        return False

    def capture_gray(self, sct: mss.mss, rect: Rect) -> np.ndarray:
        frame = np.asarray(sct.grab(rect.as_mss()))
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)

    def click_match(self, rect: Rect, match: tuple[int, int, float, int, int], label: str) -> None:
        x, y, score, tw, th = match
        click_x = rect.left + x + tw // 2
        click_y = rect.top + y + th // 2
        logging.info(
            "[%s] %s 감지 %.3f -> 클릭 (%d,%d)",
            self.target_key,
            label,
            score,
            click_x,
            click_y,
        )
        click_screen(click_x, click_y)
        time.sleep(POST_CLICK_WAIT_SECONDS)

    def finish_current_session(self) -> float:
        if self.current_dungeon is None or self.session_started_at is None:
            return 0.0

        elapsed = time.monotonic() - self.session_started_at
        total = self.repo.add_elapsed(
            self.target_key,
            self.current_dungeon,
            elapsed,
            self.duration,
        )
        logging.info(
            "[%s] 던전 %s 세션 %.1fs 누적 -> 총 %.1fs / %.1fs",
            self.target_key,
            self.current_dungeon,
            elapsed,
            total,
            self.duration,
        )
        self.session_started_at = None
        return total

    def current_total_with_live_session(self) -> float:
        if self.current_dungeon is None:
            return 0.0
        row = self.repo.get(self.target_key, self.current_dungeon)
        total = float(row["accumulated_seconds"])
        if self.session_started_at is not None:
            total += time.monotonic() - self.session_started_at
        return total

    def handle_timeout(self) -> None:
        if time.monotonic() - self.state_started_at < STEP_TIMEOUT_SECONDS:
            return
        logging.warning(
            "[%s] %s 단계 %.0fs 초과 -> 메뉴부터 재시도",
            self.target_key,
            self.state,
            STEP_TIMEOUT_SECONDS,
        )
        self.set_state("WAIT_MENU")

    def run(self) -> None:
        logging.info("[%s] DungeonRunner 시작", self.target_key)

        try:
            with mss.MSS() as sct:
                rect = get_target_rect(sct, self.target_key)
                logging.info("[%s] rect=%s", self.target_key, rect)

                if not self.select_next_dungeon():
                    self.set_state("ALL_DONE")
                else:
                    self.set_state("WAIT_MENU")

                while not self.stop_event.is_set():
                    gray = self.capture_gray(sct, rect)

                    if self.state == "ALL_DONE":
                        time.sleep(1.0)
                        continue

                    if self.state == "HUNTING":
                        revive = self.matcher.find(gray, IMAGE_REVIVE)
                        if revive is not None:
                            self.finish_current_session()
                            row = self.repo.get(self.target_key, self.current_dungeon)
                            if float(row["accumulated_seconds"]) >= self.duration:
                                self.repo.mark_completed(
                                    self.target_key,
                                    self.current_dungeon,
                                    self.duration,
                                )
                            self.click_match(rect, revive, "01_revive")
                            self.set_state("AFTER_REVIVE")
                            continue

                        # in_dungeon.png 검출 테스트
                        # 작은 이미지가 실제로 안정적으로 잡히는지 확인하기 위해
                        # 검출되면 클릭하지 않고 이미지 중앙으로 커서만 이동합니다.
                        # 던전 내부 여부 확인
                        #
                        # 테스트에서는 1시간을 실제로 기다리지 않고,
                        # 사용자가 수동으로 "나가기"를 눌러 in_dungeon.png가
                        # 5초 이상 사라지면 정상 종료로 간주합니다.
                        in_dungeon = self.matcher.find(gray, IMAGE_IN_DUNGEON)
                        now = time.monotonic()

                        if in_dungeon is not None:
                            self.last_in_dungeon_seen_at = now
                            logging.debug(
                                "[%s] in_dungeon 감지 %.3f",
                                self.target_key,
                                float(in_dungeon[2]),
                            )
                        else:
                            if self.last_in_dungeon_seen_at is None:
                                self.last_in_dungeon_seen_at = now

                            missing_for = now - self.last_in_dungeon_seen_at

                            if missing_for >= IN_DUNGEON_MISSING_SECONDS:
                                # revive는 이 블록보다 먼저 처리되므로
                                # 여기까지 왔다는 것은 "사망"이 아닌 일반 이탈입니다.
                                logging.info(
                                    "[%s] in_dungeon %.1f초 연속 미검출 -> "
                                    "던전 %s 정상 종료로 간주",
                                    self.target_key,
                                    missing_for,
                                    self.current_dungeon,
                                )

                                # 테스트에서는 수동 나가기를 1시간 정상 종료로 취급합니다.
                                self.repo.mark_completed(
                                    self.target_key,
                                    self.current_dungeon,
                                    self.duration,
                                )

                                # 현재 라이브 세션은 종료 처리.
                                self.session_started_at = None
                                self.last_in_dungeon_seen_at = None

                                logging.info(
                                    "[%s] 던전 %s DB COMPLETED 처리",
                                    self.target_key,
                                    self.current_dungeon,
                                )

                                self.set_state("NEXT_DUNGEON")
                                continue

                        live_total = self.current_total_with_live_session()
                        logging.debug(
                            "[%s] 던전 %s 누적 %.1fs (테스트에서는 시간으로 완료 판정하지 않음)",
                            self.target_key,
                            self.current_dungeon,
                            live_total,
                        )
                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "POST_DUNGEON_AUTO":
                        auto = self.matcher.find(gray, IMAGE_AUTO)
                        if auto is not None:
                            self.click_match(rect, auto, "21_auto(던전 종료 후)")
                            self.set_state("NEXT_DUNGEON")
                            continue

                        if time.monotonic() - self.state_started_at >= 5.0:
                            logging.info(
                                "[%s] 던전 종료 후 AUTO 없음 -> 다음 던전 진행",
                                self.target_key,
                            )
                            self.set_state("NEXT_DUNGEON")
                            continue

                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "NEXT_DUNGEON":
                        if self.select_next_dungeon():
                            self.set_state("WAIT_MENU")
                        else:
                            self.set_state("ALL_DONE")
                        continue

                    if self.state == "AFTER_REVIVE":
                        menu = self.matcher.find(gray, IMAGE_MENU)
                        if menu is not None:
                            row = self.repo.get(self.target_key, self.current_dungeon)
                            if row["status"] == "COMPLETED":
                                self.set_state("NEXT_DUNGEON")
                            else:
                                self.click_match(rect, menu, "02_menu")
                                self.set_state("WAIT_DUNGEON_MENU")
                            continue

                        self.handle_timeout()
                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "WAIT_MENU":
                        menu = self.matcher.find(gray, IMAGE_MENU)
                        if menu is not None:
                            self.click_match(rect, menu, "02_menu")
                            self.set_state("WAIT_DUNGEON_MENU")
                            continue
                        self.handle_timeout()
                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "WAIT_DUNGEON_MENU":
                        dungeon = self.matcher.find(gray, IMAGE_DUNGEON)
                        if dungeon is not None:
                            self.click_match(rect, dungeon, "dungeon")
                            self.set_state("WAIT_DUNGEON_SELECT")
                            continue
                        self.handle_timeout()
                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "WAIT_DUNGEON_SELECT":
                        selected = self.matcher.find(
                            gray,
                            self.image_for_dungeon(),
                        )
                        if selected is not None:
                            self.click_match(
                                rect,
                                selected,
                                f"dungeon_{self.current_dungeon}",
                            )
                            self.set_state("WAIT_ENTER")
                            continue

                        self.handle_timeout()
                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "WAIT_DUNGEON_EXIT":
                        exit_match = self.matcher.find(gray, IMAGE_EXIT)

                        if exit_match is not None:
                            self.click_match(rect, exit_match, "exit")
                            logging.info(
                                "[%s] exit 클릭 -> 다음 던전 진행",
                                self.target_key,
                            )
                            self.set_state("NEXT_DUNGEON")
                            continue

                        self.handle_timeout()
                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "WAIT_ENTER":
                        enter = self.matcher.find(gray, IMAGE_ENTER)
                        if enter is not None:
                            self.click_match(rect, enter, "enter")

                            logging.info(
                                "[%s] 입장 버튼 클릭 -> 5초 후 AUTO 탐색 시작",
                                self.target_key,
                            )

                            time.sleep(5.0)
                            self.auto_wait_started_at = time.monotonic()
                            self.set_state("WAIT_AUTO")
                            continue

                        self.handle_timeout()
                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

                    if self.state == "WAIT_AUTO":
                        auto = self.matcher.find(gray, IMAGE_AUTO)

                        if auto is not None:
                            logging.info(
                                "[%s] 21_auto 감지 -> 즉시 클릭",
                                self.target_key,
                            )

                            self.click_match(rect, auto, "21_auto")
                            self.auto_wait_started_at = None

                            self.repo.mark_started(
                                self.target_key,
                                self.current_dungeon,
                            )
                            self.session_started_at = time.monotonic()
                            self.last_in_dungeon_seen_at = None

                            logging.info(
                                "[%s] 던전 %s 사냥 세션 시작",
                                self.target_key,
                                self.current_dungeon,
                            )
                            self.set_state("HUNTING")
                            continue

                        if self.auto_wait_started_at is None:
                            self.auto_wait_started_at = time.monotonic()

                        elapsed = time.monotonic() - self.auto_wait_started_at

                        if elapsed >= AUTO_WAIT_TIMEOUT_SECONDS:
                            logging.info(
                                "[%s] AUTO %.1f초 동안 미검출 -> 던전 %s 만기로 판단",
                                self.target_key,
                                AUTO_WAIT_TIMEOUT_SECONDS,
                                self.current_dungeon,
                            )

                            self.repo.mark_completed(
                                self.target_key,
                                self.current_dungeon,
                                self.duration,
                            )
                            self.auto_wait_started_at = None

                            logging.info(
                                "[%s] 던전 %s DB COMPLETED 처리 -> exit 탐색",
                                self.target_key,
                                self.current_dungeon,
                            )
                            self.set_state("WAIT_DUNGEON_EXIT")
                            continue

                        time.sleep(SCAN_INTERVAL_SECONDS)
                        continue

        except Exception:
            logging.exception("[%s] DungeonRunner 오류", self.target_key)
        finally:
            if self.session_started_at is not None and self.current_dungeon is not None:
                try:
                    self.finish_current_session()
                except Exception:
                    logging.exception("[%s] 종료 중 세션 저장 실패", self.target_key)
            logging.info("[%s] DungeonRunner 종료", self.target_key)


def validate_images() -> None:
    required = [
        IMAGE_REVIVE,
        IMAGE_MENU,
        IMAGE_AUTO,
        IMAGE_DUNGEON,
        IMAGE_DUNGEON_A,
        IMAGE_DUNGEON_B,
        IMAGE_ENTER,
        IMAGE_IN_DUNGEON,
        IMAGE_EXIT,
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise SystemExit("필수 이미지가 없습니다.\n" + formatted)


def print_status(repo: DungeonRepository, targets: list[str], duration: float) -> None:
    print()
    print("오늘 던전 DB 상태")
    print("=" * 72)
    for target in targets:
        for dungeon in ("A", "B"):
            row = repo.get(target, dungeon)
            accumulated = float(row["accumulated_seconds"])
            print(
                f"{target:6} dungeon {dungeon} | "
                f"{row['status']:12} | "
                f"{accumulated:8.1f}s / {duration:.1f}s"
            )
    print("=" * 72)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="load_nine 던전 A/B 별도 검증 매니저")
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="실행 분면. 예: --target m1q1. 여러 번 지정 가능",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="연결된 모든 모니터의 4분면을 동시에 실행",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DUNGEON_DURATION_SECONDS,
        help="던전 1개 완료로 판단할 누적 초. 테스트 예: --duration 60",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="이미지 매칭 threshold. 기본 0.82",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="오늘 DB 상태만 출력하고 종료",
    )
    parser.add_argument(
        "--reset-today",
        action="store_true",
        help="선택 target의 오늘 던전 DB 기록 초기화",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    parser = build_parser()
    args = parser.parse_args()

    if args.duration <= 0:
        parser.error("--duration은 0보다 커야 합니다.")

    if args.all:
        targets = all_target_keys()
    elif args.target:
        targets = args.target
    else:
        targets = ["m1q1", "m1q2", "m1q3", "m1q4"]

    targets = list(dict.fromkeys(targets))
    repo = DungeonRepository(DB_PATH)

    if args.reset_today:
        for target in targets:
            repo.reset_today(target)
            print(f"[RESET] {target} 오늘 던전 기록 초기화")

    if args.status:
        print_status(repo, targets, args.duration)
        return

    validate_images()

    print()
    print("Dungeon Manager")
    print("=" * 72)
    print(f"targets   : {', '.join(targets)}")
    print(f"duration  : {args.duration:.1f}s / dungeon")
    print(f"threshold : {args.threshold:.2f}")
    print(f"db        : {DB_PATH}")
    print(f"log       : {LOG_PATH}")
    print("=" * 72)
    print("Ctrl+C 로 종료")
    print()

    print_status(repo, targets, args.duration)

    stop_event = threading.Event()
    matcher = ImageMatcher(args.threshold)
    runners = [
        DungeonRunner(
            target_key=target,
            repo=repo,
            matcher=matcher,
            dungeon_duration_seconds=args.duration,
            stop_event=stop_event,
        )
        for target in targets
    ]

    for runner in runners:
        runner.start()

    try:
        while any(runner.is_alive() for runner in runners):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n종료 요청...")
        stop_event.set()

    for runner in runners:
        runner.join(timeout=5)

    print_status(repo, targets, args.duration)


if __name__ == "__main__":
    main()
