from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path


# macro_manager.py와 같은 클릭 유지 시간과 SendInput 방식을 사용합니다.
CLICK_HOLD_SECONDS = 0.08
CLICK_INTERVAL_SECONDS = 0.02

VK_F5 = 0x74
VK_F6 = 0x75
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


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


user32 = ctypes.WinDLL("user32", use_last_error=True)
stop_event = threading.Event()
click_event = threading.Event()


def ensure_admin() -> bool:
    """관리자 권한이 아니면 UAC를 요청해 이 파일을 다시 실행합니다."""
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
        None, "runas", executable, arguments, os.getcwd(), 1
    )
    if result <= 32:
        raise OSError("관리자 권한으로 다시 실행하지 못했습니다.")
    return False


def send_mouse_input(flags: int) -> None:
    mouse_input = Input(type=INPUT_MOUSE, mi=MouseInput(dwFlags=flags))
    if user32.SendInput(
        1, ctypes.byref(mouse_input), ctypes.sizeof(Input)
    ) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def held_left_click() -> None:
    """현재 마우스 위치에서 macro_manager.py와 동일하게 클릭합니다."""
    send_mouse_input(MOUSEEVENTF_LEFTDOWN)
    try:
        stop_event.wait(CLICK_HOLD_SECONDS)
    finally:
        send_mouse_input(MOUSEEVENTF_LEFTUP)


def click_worker() -> None:
    while not stop_event.is_set():
        if not click_event.wait(0.05):
            continue
        if stop_event.is_set():
            break
        try:
            held_left_click()
        except OSError as error:
            print(f"클릭 입력 오류: {error}", flush=True)
            stop_event.set()
            break
        stop_event.wait(CLICK_INTERVAL_SECONDS)


def key_is_down(virtual_key: int) -> bool:
    return bool(user32.GetAsyncKeyState(virtual_key) & 0x8000)


def run() -> None:
    print("자동 클릭 대기 중: F5 시작 / F6 종료", flush=True)
    worker = threading.Thread(target=click_worker, name="auto-clicker", daemon=True)
    worker.start()

    f5_was_down = False
    f6_was_down = False
    try:
        while not stop_event.is_set():
            f5_down = key_is_down(VK_F5)
            f6_down = key_is_down(VK_F6)

            if f6_down and not f6_was_down:
                print("F6 입력: 프로그램을 종료합니다.", flush=True)
                stop_event.set()
                click_event.set()
                break

            if f5_down and not f5_was_down and not click_event.is_set():
                click_event.set()
                print("F5 입력: 자동 클릭을 시작합니다.", flush=True)

            f5_was_down = f5_down
            f6_was_down = f6_down
            time.sleep(0.01)
    finally:
        stop_event.set()
        click_event.set()
        worker.join(timeout=1.0)


def main() -> None:
    try:
        if ensure_admin():
            run()
    except Exception as error:
        ctypes.windll.user32.MessageBoxW(
            None,
            str(error),
            "자동 클릭 프로그램 오류",
            0x00000010,
        )


if __name__ == "__main__":
    main()
