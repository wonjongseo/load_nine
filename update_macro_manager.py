from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path


NEW_PREAMBLE = '''from __future__ import annotations

from macro_manager import *  # noqa: F401,F403

_UI_POLISHED_WINDOWS: set[int] = set()
_UI_WHEEL_INSTALLED = False


def _safe_configure(widget, **kwargs) -> None:
    try:
        widget.configure(**kwargs)
    except Exception:
        pass


def _is_scrollable(widget) -> bool:
    return hasattr(widget, "yview_scroll") or hasattr(widget, "xview_scroll")


def _scroll_target_from_pointer(root):
    try:
        x, y = root.winfo_pointerxy()
        widget = root.winfo_containing(x, y)
    except Exception:
        return None

    current = widget
    while current is not None:
        if _is_scrollable(current):
            return current
        current = getattr(current, "master", None)
    return None


def _on_mousewheel(root, event):
    target = _scroll_target_from_pointer(root)
    if target is None:
        return

    delta = getattr(event, "delta", 0)
    if delta == 0:
        return

    units = -int(delta / 120)
    if units == 0:
        units = -1 if delta > 0 else 1

    try:
        if event.state & 0x0001 and hasattr(target, "xview_scroll"):
            target.xview_scroll(units, "units")
        elif hasattr(target, "yview_scroll"):
            target.yview_scroll(units, "units")
        return "break"
    except Exception:
        return None


def _on_linux_wheel(root, direction, event):
    target = _scroll_target_from_pointer(root)
    if target is None:
        return

    try:
        if event.state & 0x0001 and hasattr(target, "xview_scroll"):
            target.xview_scroll(direction, "units")
        elif hasattr(target, "yview_scroll"):
            target.yview_scroll(direction, "units")
        return "break"
    except Exception:
        return None


def install_global_mousewheel(root) -> None:
    global _UI_WHEEL_INSTALLED
    if _UI_WHEEL_INSTALLED:
        return
    _UI_WHEEL_INSTALLED = True

    try:
        root.bind_all(
            "<MouseWheel>",
            lambda e, r=root: _on_mousewheel(r, e),
            add="+",
        )
        root.bind_all(
            "<Shift-MouseWheel>",
            lambda e, r=root: _on_mousewheel(r, e),
            add="+",
        )
        root.bind_all(
            "<Button-4>",
            lambda e, r=root: _on_linux_wheel(r, -1, e),
            add="+",
        )
        root.bind_all(
            "<Button-5>",
            lambda e, r=root: _on_linux_wheel(r, 1, e),
            add="+",
        )
    except Exception:
        pass


def _apply_widget_design(widget) -> None:
    try:
        cls = widget.winfo_class()
    except Exception:
        cls = ""

    if cls == "Treeview":
        try:
            widget.configure(style="Editor.Treeview", selectmode="browse")
        except Exception:
            pass

    elif cls == "TButton":
        try:
            text = str(widget.cget("text")).strip()
        except Exception:
            text = ""

        if text in {"저장", "적용", "확인", "추가", "만들기"}:
            _safe_configure(widget, style="Primary.TButton")
        elif "삭제" in text:
            _safe_configure(widget, style="Danger.TButton")
        else:
            _safe_configure(widget, style="Secondary.TButton")

    elif cls == "TEntry":
        try:
            width = int(widget.cget("width"))
            if width > 70:
                widget.configure(width=46)
        except Exception:
            pass

    elif cls == "Listbox":
        try:
            widget.configure(
                exportselection=False,
                activestyle="none",
                borderwidth=0,
                highlightthickness=1,
            )
        except Exception:
            pass

    try:
        children = widget.winfo_children()
    except Exception:
        children = []

    for child in children:
        _apply_widget_design(child)


def _polish_editor_window(window) -> None:
    try:
        wid = int(window.winfo_id())
    except Exception:
        return

    if wid in _UI_POLISHED_WINDOWS:
        return
    _UI_POLISHED_WINDOWS.add(wid)

    try:
        title = window.title()
    except Exception:
        title = ""

    is_target_editor = "분면" in title
    is_routine_editor = "루틴" in title or "Routine" in title

    if isinstance(window, tk.Toplevel):
        try:
            if is_target_editor or is_routine_editor:
                window.geometry("1180x760")
                window.minsize(1000, 680)
            else:
                window.minsize(860, 600)
            window.resizable(True, True)
        except Exception:
            pass

        try:
            window.bind("<Escape>", lambda _e, w=window: w.destroy(), add="+")
        except Exception:
            pass

        if callable(getattr(window, "save", None)):
            try:
                window.bind(
                    "<Control-s>",
                    lambda _e, w=window: (w.save(), "break")[-1],
                    add="+",
                )
            except Exception:
                pass

    _apply_widget_design(window)


def _poll_windows(root) -> None:
    try:
        stack = [root]
        while stack:
            widget = stack.pop()
            try:
                children = widget.winfo_children()
            except Exception:
                children = []

            for child in children:
                if isinstance(child, tk.Toplevel):
                    _polish_editor_window(child)
                stack.append(child)

        root.after(250, lambda: _poll_windows(root))
    except Exception:
        pass


def apply_unified_ui(root) -> None:
    def _apply():
        try:
            style = ttk.Style(root)
            themes = set(style.theme_names())

            if sys.platform.startswith("win") and "vista" in themes:
                style.theme_use("vista")
            elif "clam" in themes:
                style.theme_use("clam")

            root.option_add("*Font", ("Segoe UI", 10))
            root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

            style.configure("TLabel", padding=(0, 2))
            style.configure("TEntry", padding=5)
            style.configure("TCombobox", padding=4)
            style.configure("TCheckbutton", padding=(2, 4))
            style.configure("TRadiobutton", padding=(2, 4))

            style.configure(
                "Primary.TButton",
                padding=(14, 8),
                font=("Segoe UI Semibold", 10),
            )
            style.configure(
                "Secondary.TButton",
                padding=(11, 7),
            )
            style.configure(
                "Danger.TButton",
                padding=(11, 7),
                font=("Segoe UI Semibold", 10),
            )

            style.configure("TLabelframe", padding=12)
            style.configure(
                "TLabelframe.Label",
                font=("Segoe UI Semibold", 10),
            )

            style.configure(
                "Treeview",
                rowheight=30,
                font=("Segoe UI", 10),
                borderwidth=0,
            )
            style.configure(
                "Treeview.Heading",
                font=("Segoe UI Semibold", 10),
                padding=(8, 7),
            )
            style.configure(
                "Editor.Treeview",
                rowheight=32,
                font=("Segoe UI", 10),
            )

            style.configure(
                "TNotebook.Tab",
                padding=(16, 8),
                font=("Segoe UI Semibold", 10),
            )

            try:
                root.minsize(920, 640)
            except Exception:
                pass

            install_global_mousewheel(root)
            _apply_widget_design(root)
            _poll_windows(root)

        except Exception:
            try:
                root.after(50, _apply)
            except Exception:
                pass

    _apply()


'''


README_SECTION = '''
## UI / UX 개선

분면별 루틴 설정과 루틴 만들기/편집 화면은 같은 디자인 규칙을 사용합니다.

- Segoe UI 기반 스타일
- 편집창 크기/최소 크기 통일
- 단계 목록 행 높이 및 선택 가독성 개선
- 저장/적용/삭제 등 버튼 시각 계층 정리
- 긴 이미지 경로 입력창 폭 정리
- 좌표 입력 용어를 `Fallback X/Y`로 통일
- `Esc`로 편집창 닫기
- `Ctrl+S`로 저장 가능한 편집창 저장

### 마우스 휠 스크롤

Scrollbar가 보이지만 마우스 휠로 움직이지 않던 문제를 수정했습니다.

마우스 포인터 아래의 `Canvas`, `Treeview`, `Listbox` 등 실제 스크롤 가능한 위젯을 자동으로 찾아 스크롤합니다.

- 휠: 세로 스크롤
- `Shift + 휠`: 가로 스크롤
- Windows 고해상도 휠/터치패드 delta 대응
'''


def first_class_offset(source: str) -> int:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return sum(len(x) for x in lines[:node.lineno - 1])

    raise RuntimeError("macro_manager_ui.py에서 UI 클래스를 찾지 못했습니다.")


def ensure_apply_call(source: str) -> str:
    if "apply_unified_ui(self)" in source:
        return source

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "MacroManager":
            continue

        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            if child.name != "__init__" or not child.body:
                continue

            first = child.body[0]
            line_no = first.lineno

            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
                and len(child.body) > 1
            ):
                line_no = child.body[1].lineno

            line = lines[line_no - 1]
            indent = line[: len(line) - len(line.lstrip())]
            offset = sum(len(x) for x in lines[:line_no - 1])

            return (
                source[:offset]
                + indent
                + "apply_unified_ui(self)\n"
                + source[offset:]
            )

    raise RuntimeError("MacroManager.__init__()을 찾지 못했습니다.")


def patch_ui(ui_path: Path) -> None:
    source = ui_path.read_text(encoding="utf-8")
    offset = first_class_offset(source)
    class_body = source[offset:]

    new_source = NEW_PREAMBLE + class_body
    new_source = ensure_apply_call(new_source)

    new_source = new_source.replace('"좌표 X"', '"Fallback X"')
    new_source = new_source.replace('"좌표 Y"', '"Fallback Y"')

    compile(new_source, str(ui_path), "exec")
    ui_path.write_text(new_source, encoding="utf-8")


def patch_readme(readme_path: Path) -> None:
    if not readme_path.exists():
        return

    text = readme_path.read_text(encoding="utf-8")
    marker = "## UI / UX 개선"

    if marker in text:
        text = text.split(marker, 1)[0].rstrip()

    text = text.rstrip() + "\n\n" + README_SECTION.lstrip()
    readme_path.write_text(text, encoding="utf-8")


def main() -> None:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()

    ui_path = repo / "macro_manager_ui.py"
    readme_path = repo / "README.md"

    if not ui_path.exists():
        raise SystemExit(
            "macro_manager_ui.py가 없습니다.\n"
            "먼저 UI 분리 패치를 적용한 폴더에서 실행하세요.\n"
            '예: py update_ui_design_scroll.py "C:\\\\Users\\\\Jongseo Won\\\\Desktop\\\\auto"'
        )

    ui_backup = ui_path.with_suffix(".py.bak")
    shutil.copy2(ui_path, ui_backup)
    print(f"[BACKUP] {ui_backup}")

    if readme_path.exists():
        readme_backup = readme_path.with_suffix(".md.bak")
        shutil.copy2(readme_path, readme_backup)
        print(f"[BACKUP] {readme_backup}")

    patch_ui(ui_path)
    patch_readme(readme_path)

    print()
    print("[OK] UI 디자인/UX 패치 완료")
    print("[OK] macro_manager_ui.py 문법 검사 통과")
    print()
    print("적용 내용:")
    print("- 분면 설정/루틴 편집창 크기 및 디자인 규칙 통일")
    print("- 버튼/입력/Treeview/섹션 스타일 개선")
    print("- Fallback 용어 통일")
    print("- 마우스 휠 세로 스크롤 수정")
    print("- Shift + 휠 가로 스크롤 지원")
    print("- Canvas/Treeview/Listbox 포인터 기준 자동 스크롤")
    print("- README UI/UX 설명 갱신")
    print()
    print("매크로 실행 엔진은 수정하지 않았습니다.")


if __name__ == "__main__":
    main()
