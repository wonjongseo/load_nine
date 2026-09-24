import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import messagebox
import threading
import queue
import random
import atexit


# ============================================================
# Windows DLL
# ============================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


# ============================================================
# Windows Constants
# ============================================================

SPI_GETFILTERKEYS = 0x0032
SPI_SETFILTERKEYS = 0x0033

SPIF_SENDCHANGE = 0x0002

# FILTERKEYS flags
FKF_FILTERKEYSON = 0x00000001
FKF_AVAILABLE = 0x00000002
FKF_HOTKEYACTIVE = 0x00000004
FKF_CONFIRMHOTKEY = 0x00000008
FKF_HOTKEYSOUND = 0x00000010
FKF_INDICATOR = 0x00000020
FKF_CLICKON = 0x00000040


# Keyboard Hook
WH_KEYBOARD_LL = 13

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

WM_QUIT = 0x0012

LLKHF_INJECTED = 0x00000010


# ============================================================
# Windows Types
# ============================================================

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
HHOOK = wintypes.HANDLE


# ============================================================
# FILTERKEYS Structure
# ============================================================

class FILTERKEYS(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwFlags", wintypes.DWORD),
        ("iWaitMSec", wintypes.DWORD),
        ("iDelayMSec", wintypes.DWORD),
        ("iRepeatMSec", wintypes.DWORD),
        ("iBounceMSec", wintypes.DWORD),
    ]


# ============================================================
# Keyboard Hook Structure
# ============================================================

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


# ============================================================
# Callback Type
# ============================================================

LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM
)


# ============================================================
# Windows API Prototypes
# ============================================================

user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
    wintypes.UINT,
]
user32.SystemParametersInfoW.restype = wintypes.BOOL


kernel32.GetModuleHandleW.argtypes = [
    wintypes.LPCWSTR
]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    LowLevelKeyboardProc,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = HHOOK


user32.CallNextHookEx.argtypes = [
    HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallNextHookEx.restype = LRESULT


user32.UnhookWindowsHookEx.argtypes = [
    HHOOK
]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL


user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = ctypes.c_int


user32.TranslateMessage.argtypes = [
    ctypes.POINTER(wintypes.MSG)
]
user32.TranslateMessage.restype = wintypes.BOOL


user32.DispatchMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG)
]
user32.DispatchMessageW.restype = LRESULT


user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostThreadMessageW.restype = wintypes.BOOL


# ============================================================
# 기본값
# ============================================================

# 반복 시작 딜레이
DEFAULT_DELAY_MIN = 3000       # 3초
DEFAULT_DELAY_MAX = 5000       # 5초

# 반복 간격
DEFAULT_REPEAT_MIN = 3000      # 3초
DEFAULT_REPEAT_MAX = 5000      # 5초


# ============================================================
# Program State
# ============================================================

original_settings = FILTERKEYS()
original_settings.cbSize = ctypes.sizeof(FILTERKEYS)

program_active = False
program_closing = False

hook_handle = None
hook_thread_id = 0

pressed_keys = set()

event_queue = queue.Queue()


# 현재 적용 범위
delay_min_value = DEFAULT_DELAY_MIN
delay_max_value = DEFAULT_DELAY_MAX

repeat_min_value = DEFAULT_REPEAT_MIN
repeat_max_value = DEFAULT_REPEAT_MAX


# 현재 적용된 값
current_delay = None
current_repeat = None


# ============================================================
# 현재 Windows FilterKeys 설정 저장
# ============================================================

def load_original_settings():

    result = user32.SystemParametersInfoW(
        SPI_GETFILTERKEYS,
        ctypes.sizeof(FILTERKEYS),
        ctypes.byref(original_settings),
        0
    )

    if not result:
        raise ctypes.WinError(ctypes.get_last_error())


# ============================================================
# 원래 설정 복원
# ============================================================

def restore_original_settings():

    result = user32.SystemParametersInfoW(
        SPI_SETFILTERKEYS,
        ctypes.sizeof(FILTERKEYS),
        ctypes.byref(original_settings),
        SPIF_SENDCHANGE
    )

    return bool(result)


# ============================================================
# Filter Keys 적용
# ============================================================

def apply_filter_keys(delay_ms, repeat_ms):

    global current_delay
    global current_repeat

    modified = FILTERKEYS()

    modified.cbSize = ctypes.sizeof(FILTERKEYS)

    # 기존 플래그를 기반으로 함
    modified.dwFlags = original_settings.dwFlags

    # Filter Keys 활성화
    modified.dwFlags |= FKF_FILTERKEYSON

    # --------------------------------------------------------
    # 소리 OFF
    # --------------------------------------------------------

    # FilterKeys 키 클릭음 제거
    modified.dwFlags &= ~FKF_CLICKON

    # Shift 오래 누를 때 발생하는 소리 제거
    modified.dwFlags &= ~FKF_HOTKEYSOUND

    # Right Shift 8초 단축키 비활성화
    modified.dwFlags &= ~FKF_HOTKEYACTIVE

    # 단축키 확인 창 비활성화
    modified.dwFlags &= ~FKF_CONFIRMHOTKEY

    # --------------------------------------------------------
    # 시간 설정
    # --------------------------------------------------------

    # 최초 키 입력은 바로 처리
    modified.iWaitMSec = 0

    # 자동 반복이 시작될 때까지 시간
    modified.iDelayMSec = delay_ms

    # 자동 반복 시작 후 입력 간격
    modified.iRepeatMSec = repeat_ms

    # Bounce Keys OFF
    modified.iBounceMSec = 0

    result = user32.SystemParametersInfoW(
        SPI_SETFILTERKEYS,
        ctypes.sizeof(FILTERKEYS),
        ctypes.byref(modified),
        SPIF_SENDCHANGE
    )

    if not result:
        raise ctypes.WinError(ctypes.get_last_error())

    current_delay = delay_ms
    current_repeat = repeat_ms


# ============================================================
# 랜덤값 선택 및 적용
# ============================================================

def apply_random_setting():

    if not program_active:
        return

    delay_ms = random.randint(
        delay_min_value,
        delay_max_value
    )

    repeat_ms = random.randint(
        repeat_min_value,
        repeat_max_value
    )

    try:

        apply_filter_keys(
            delay_ms,
            repeat_ms
        )

        update_status(
            delay_ms,
            repeat_ms
        )

    except Exception as e:

        messagebox.showerror(
            "설정 오류",
            f"Filter Keys 설정 변경에 실패했습니다.\n\n{e}"
        )


# ============================================================
# 상태 표시
# ============================================================

def update_status(delay_ms, repeat_ms):

    status_label.config(
        text=(
            "● 실행 중\n\n"
            f"현재 반복 시작 딜레이 : {delay_ms} ms "
            f"({delay_ms / 1000:.3f}초)\n"
            f"현재 반복 간격       : {repeat_ms} ms "
            f"({repeat_ms / 1000:.3f}초)"
        )
    )


# ============================================================
# Keyboard Hook Callback
# ============================================================

def keyboard_proc(nCode, wParam, lParam):

    if nCode >= 0:

        info = ctypes.cast(
            lParam,
            ctypes.POINTER(KBDLLHOOKSTRUCT)
        ).contents

        vk_code = int(info.vkCode)

        # ----------------------------------------------------
        # 외부 프로그램에서 생성된 가상 입력 무시
        # ----------------------------------------------------

        if info.flags & LLKHF_INJECTED:

            return user32.CallNextHookEx(
                hook_handle,
                nCode,
                wParam,
                lParam
            )

        # ----------------------------------------------------
        # Key Down
        # ----------------------------------------------------

        if wParam in (
            WM_KEYDOWN,
            WM_SYSKEYDOWN
        ):

            # 이미 눌려 있는 키라면
            # 자동 반복으로 발생한 KEYDOWN이므로 무시
            if vk_code not in pressed_keys:

                pressed_keys.add(vk_code)

                if program_active:
                    event_queue.put("NEW_KEY")

        # ----------------------------------------------------
        # Key Up
        # ----------------------------------------------------

        elif wParam in (
            WM_KEYUP,
            WM_SYSKEYUP
        ):

            pressed_keys.discard(vk_code)

    # 키 입력은 차단하지 않음
    return user32.CallNextHookEx(
        hook_handle,
        nCode,
        wParam,
        lParam
    )


keyboard_callback = LowLevelKeyboardProc(
    keyboard_proc
)


# ============================================================
# Keyboard Hook Thread
# ============================================================

def keyboard_hook_worker():

    global hook_handle
    global hook_thread_id

    hook_thread_id = kernel32.GetCurrentThreadId()

    module_handle = kernel32.GetModuleHandleW(None)

    hook_handle = user32.SetWindowsHookExW(
        WH_KEYBOARD_LL,
        keyboard_callback,
        module_handle,
        0
    )

    if not hook_handle:

        error_code = ctypes.get_last_error()

        event_queue.put(
            (
                "HOOK_ERROR",
                error_code
            )
        )

        return

    event_queue.put("HOOK_OK")

    msg = wintypes.MSG()

    try:

        while True:

            result = user32.GetMessageW(
                ctypes.byref(msg),
                None,
                0,
                0
            )

            if result == 0:
                break

            if result == -1:
                break

            user32.TranslateMessage(
                ctypes.byref(msg)
            )

            user32.DispatchMessageW(
                ctypes.byref(msg)
            )

    finally:

        if hook_handle:

            user32.UnhookWindowsHookEx(
                hook_handle
            )


# ============================================================
# Hook -> UI 이벤트 처리
# ============================================================

def process_event_queue():

    if program_closing:
        return

    try:

        while True:

            event = event_queue.get_nowait()

            if event == "NEW_KEY":

                if program_active:
                    apply_random_setting()

            elif event == "HOOK_OK":

                hook_status_label.config(
                    text="키보드 감지: 정상"
                )

            elif isinstance(event, tuple):

                if event[0] == "HOOK_ERROR":

                    error_code = event[1]

                    hook_status_label.config(
                        text="키보드 감지: 실패"
                    )

                    messagebox.showerror(
                        "오류",
                        (
                            "키보드 감지를 시작할 수 없습니다.\n\n"
                            f"Windows 오류 코드: {error_code}"
                        )
                    )

    except queue.Empty:
        pass

    root.after(
        20,
        process_event_queue
    )


# ============================================================
# UI 입력값 읽기
# ============================================================

def read_ranges():

    try:

        delay_min = int(
            delay_min_entry.get().strip()
        )

        delay_max = int(
            delay_max_entry.get().strip()
        )

        repeat_min = int(
            repeat_min_entry.get().strip()
        )

        repeat_max = int(
            repeat_max_entry.get().strip()
        )

    except ValueError:

        messagebox.showerror(
            "입력 오류",
            "모든 값을 숫자로 입력해주세요."
        )

        return None

    # --------------------------------------------------------
    # 반복 시작 딜레이
    # --------------------------------------------------------

    if not 0 <= delay_min <= 20000:

        messagebox.showerror(
            "입력 오류",
            "반복 시작 딜레이 최소값은 0 ~ 20000ms 사이로 입력해주세요."
        )

        return None

    if not 0 <= delay_max <= 20000:

        messagebox.showerror(
            "입력 오류",
            "반복 시작 딜레이 최대값은 0 ~ 20000ms 사이로 입력해주세요."
        )

        return None

    if delay_min > delay_max:

        messagebox.showerror(
            "입력 오류",
            "반복 시작 딜레이 최소값이 최대값보다 클 수 없습니다."
        )

        return None

    # --------------------------------------------------------
    # 반복 간격
    # --------------------------------------------------------

    if not 1 <= repeat_min <= 20000:

        messagebox.showerror(
            "입력 오류",
            "반복 간격 최소값은 1 ~ 20000ms 사이로 입력해주세요."
        )

        return None

    if not 1 <= repeat_max <= 20000:

        messagebox.showerror(
            "입력 오류",
            "반복 간격 최대값은 1 ~ 20000ms 사이로 입력해주세요."
        )

        return None

    if repeat_min > repeat_max:

        messagebox.showerror(
            "입력 오류",
            "반복 간격 최소값이 최대값보다 클 수 없습니다."
        )

        return None

    return (
        delay_min,
        delay_max,
        repeat_min,
        repeat_max
    )


# ============================================================
# 입력창 활성 / 비활성
# ============================================================

def set_entries_enabled(enabled):

    state = "normal" if enabled else "disabled"

    delay_min_entry.config(state=state)
    delay_max_entry.config(state=state)

    repeat_min_entry.config(state=state)
    repeat_max_entry.config(state=state)


# ============================================================
# 시작
# ============================================================

def start_program():

    global program_active

    global delay_min_value
    global delay_max_value

    global repeat_min_value
    global repeat_max_value

    ranges = read_ranges()

    if ranges is None:
        return

    (
        delay_min_value,
        delay_max_value,
        repeat_min_value,
        repeat_max_value
    ) = ranges

    program_active = True

    pressed_keys.clear()

    # 시작할 때 한 번 적용
    apply_random_setting()

    set_entries_enabled(False)

    start_button.config(
        state="disabled"
    )

    stop_button.config(
        state="normal"
    )


# ============================================================
# 중지
# ============================================================

def stop_program():

    global program_active

    program_active = False

    pressed_keys.clear()

    success = restore_original_settings()

    if success:

        status_label.config(
            text=(
                "○ 중지됨\n\n"
                "원래 Windows 키보드 설정으로 복구되었습니다."
            )
        )

    else:

        status_label.config(
            text="⚠ Windows 설정 복구 실패"
        )

    set_entries_enabled(True)

    start_button.config(
        state="normal"
    )

    stop_button.config(
        state="disabled"
    )


# ============================================================
# 프로그램 종료
# ============================================================

def close_program():

    global program_active
    global program_closing

    if program_closing:
        return

    program_closing = True
    program_active = False

    # 원래 Windows 설정 복구
    restore_original_settings()

    # Hook Thread 종료
    if hook_thread_id:

        user32.PostThreadMessageW(
            hook_thread_id,
            WM_QUIT,
            0,
            0
        )

    try:
        root.destroy()
    except Exception:
        pass


# ============================================================
# 종료 시 비상 복구
# ============================================================

def emergency_restore():

    try:
        restore_original_settings()
    except Exception:
        pass


atexit.register(
    emergency_restore
)


# ============================================================
# 최초 Windows 설정 읽기
# ============================================================

try:

    load_original_settings()

except Exception as e:

    user32.MessageBoxW(
        0,
        (
            "Windows 키보드 설정을 읽을 수 없습니다.\n\n"
            f"{e}"
        ),
        "Keyboard Random Repeat",
        0x10
    )

    raise SystemExit


# ============================================================
# UI
# ============================================================

root = tk.Tk()

root.title(
    "Keyboard Random Repeat"
)

root.geometry(
    "540x520"
)

root.resizable(
    False,
    False
)


# ============================================================
# 제목
# ============================================================

title_label = tk.Label(
    root,
    text="키 반복 랜덤 설정",
    font=(
        "맑은 고딕",
        18,
        "bold"
    )
)

title_label.pack(
    pady=(25, 5)
)


description_label = tk.Label(
    root,
    text=(
        "새로운 키를 누를 때마다\n"
        "반복 시작 딜레이와 반복 간격을 랜덤으로 설정합니다."
    ),
    font=(
        "맑은 고딕",
        10
    ),
    justify="center"
)

description_label.pack(
    pady=(0, 20)
)


# ============================================================
# 반복 시작 딜레이
# ============================================================

delay_group = tk.LabelFrame(
    root,
    text="반복 시작 딜레이",
    padx=20,
    pady=15
)

delay_group.pack(
    padx=35,
    fill="x"
)


delay_row = tk.Frame(
    delay_group
)

delay_row.pack()


tk.Label(
    delay_row,
    text="최소"
).pack(
    side="left"
)


delay_min_entry = tk.Entry(
    delay_row,
    width=9,
    justify="right"
)

delay_min_entry.insert(
    0,
    str(DEFAULT_DELAY_MIN)
)

delay_min_entry.pack(
    side="left",
    padx=(5, 12)
)


tk.Label(
    delay_row,
    text="최대"
).pack(
    side="left"
)


delay_max_entry = tk.Entry(
    delay_row,
    width=9,
    justify="right"
)

delay_max_entry.insert(
    0,
    str(DEFAULT_DELAY_MAX)
)

delay_max_entry.pack(
    side="left",
    padx=(5, 5)
)


tk.Label(
    delay_row,
    text="ms"
).pack(
    side="left"
)


# ============================================================
# 반복 간격
# ============================================================

repeat_group = tk.LabelFrame(
    root,
    text="반복 간격",
    padx=20,
    pady=15
)

repeat_group.pack(
    padx=35,
    pady=(15, 0),
    fill="x"
)


repeat_row = tk.Frame(
    repeat_group
)

repeat_row.pack()


tk.Label(
    repeat_row,
    text="최소"
).pack(
    side="left"
)


repeat_min_entry = tk.Entry(
    repeat_row,
    width=9,
    justify="right"
)

repeat_min_entry.insert(
    0,
    str(DEFAULT_REPEAT_MIN)
)

repeat_min_entry.pack(
    side="left",
    padx=(5, 12)
)


tk.Label(
    repeat_row,
    text="최대"
).pack(
    side="left"
)


repeat_max_entry = tk.Entry(
    repeat_row,
    width=9,
    justify="right"
)

repeat_max_entry.insert(
    0,
    str(DEFAULT_REPEAT_MAX)
)

repeat_max_entry.pack(
    side="left",
    padx=(5, 5)
)


tk.Label(
    repeat_row,
    text="ms"
).pack(
    side="left"
)


# ============================================================
# 버튼
# ============================================================

button_frame = tk.Frame(
    root
)

button_frame.pack(
    pady=22
)


start_button = tk.Button(
    button_frame,
    text="시작",
    width=16,
    height=2,
    command=start_program
)

start_button.pack(
    side="left",
    padx=5
)


stop_button = tk.Button(
    button_frame,
    text="중지 / 원래대로",
    width=16,
    height=2,
    command=stop_program,
    state="disabled"
)

stop_button.pack(
    side="left",
    padx=5
)


# ============================================================
# 현재 상태
# ============================================================

status_label = tk.Label(
    root,
    text=(
        "○ 대기 중\n\n"
        "기본값: 3초 ~ 5초"
    ),
    font=(
        "맑은 고딕",
        10,
        "bold"
    )
)

status_label.pack(
    pady=(0, 10)
)


hook_status_label = tk.Label(
    root,
    text="키보드 감지: 시작 중...",
    font=(
        "맑은 고딕",
        9
    )
)

hook_status_label.pack()


# ============================================================
# 프로그램 종료
# ============================================================

exit_button = tk.Button(
    root,
    text="프로그램 종료 + 원래 설정 복구",
    width=34,
    height=2,
    command=close_program
)

exit_button.pack(
    pady=15
)


root.protocol(
    "WM_DELETE_WINDOW",
    close_program
)


# ============================================================
# Keyboard Hook 시작
# ============================================================

hook_thread = threading.Thread(
    target=keyboard_hook_worker,
    daemon=True
)

hook_thread.start()


# ============================================================
# Queue 처리 시작
# ============================================================

root.after(
    20,
    process_event_queue
)


# ============================================================
# 실행
# ============================================================

root.mainloop()