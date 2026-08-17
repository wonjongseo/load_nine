from pathlib import Path
import shutil
import sys

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: 예상한 코드가 정확히 1개가 아닙니다. found={count}")
    return text.replace(old, new, 1)

def main():
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    path = repo / "macro_manager.py"

    if not path.exists():
        raise SystemExit(
            "macro_manager.py가 있는 폴더에서 실행하거나 레포 경로를 지정하세요.\n"
            '예: py update_target_editor_ui.py "C:\\\\Users\\\\Jongseo Won\\\\Desktop\\\\load_nine"'
        )

    backup = path.with_suffix(".py.bak")
    shutil.copy2(path, backup)
    print(f"[BACKUP] {backup}")

    text = path.read_text(encoding="utf-8")

    old_headers = '''        headers = (
            "단계 (클릭=캡처)",
            "공용 이미지",
            "현재 적용 이미지 (변경 시 분면 전용)",
            "클릭 보정 X",
            "Y",
            "분면별 좌표 X (좌표 클릭만)",
            "Y",
            "",
        )
'''
    new_headers = '''        headers = (
            "단계 (클릭=캡처)",
            "공용 이미지",
            "현재 적용 이미지 (변경 시 분면 전용)",
            "클릭 보정 X",
            "Y",
            "좌표 X",
            "Y",
            "",
        )
'''
    text = replace_once(text, old_headers, new_headers, "좌표 헤더 축소")

    old_flags = '''            click_enabled = scope == "routine" and not coordinate_step
'''
    new_flags = '''            # 사망 전/진입(legacy) 단계도 분면별 전용 이미지를 수정할 수 있어야 합니다.
            # 클릭 보정은 기존처럼 전체 루틴 단계에서만 사용합니다.
            image_editable = not coordinate_step
            click_enabled = scope == "routine" and not coordinate_step
'''
    text = replace_once(text, old_flags, new_flags, "legacy 이미지 편집 활성화")

    old_entry = '''            override_entry = ttk.Entry(
                self.body,
                textvariable=override_var,
                width=75,
                state="normal" if click_enabled else "disabled",
            )
'''
    new_entry = '''            override_entry = ttk.Entry(
                self.body,
                textvariable=override_var,
                width=75,
                state="normal" if image_editable else "disabled",
            )
'''
    text = replace_once(text, old_entry, new_entry, "이미지 Entry 활성화")

    old_x = '''            ttk.Entry(
                self.body,
                textvariable=x_var,
                width=8,
                state="normal" if coordinate_step else "disabled",
            ).grid(row=row_index, column=5)
'''
    new_x = '''            ttk.Entry(
                self.body,
                textvariable=x_var,
                width=6,
                state="normal" if coordinate_step else "disabled",
            ).grid(row=row_index, column=5, padx=2)
'''
    text = replace_once(text, old_x, new_x, "좌표 X 폭 축소")

    old_y = '''            ttk.Entry(
                self.body,
                textvariable=y_var,
                width=8,
                state="normal" if coordinate_step else "disabled",
            ).grid(row=row_index, column=6)
'''
    new_y = '''            ttk.Entry(
                self.body,
                textvariable=y_var,
                width=6,
                state="normal" if coordinate_step else "disabled",
            ).grid(row=row_index, column=6, padx=2)
'''
    text = replace_once(text, old_y, new_y, "좌표 Y 폭 축소")

    old_button_state = '''            image_button_state = "disabled" if coordinate_step else "normal"
'''
    new_button_state = '''            image_button_state = "normal" if image_editable else "disabled"
'''
    text = replace_once(text, old_button_state, new_button_state, "이미지 버튼 활성화")

    compile(text, str(path), "exec")
    path.write_text(text, encoding="utf-8")

    print(f"[OK] {path} 수정 완료")
    print("- 사망 전 물약 10개 감지 / 뒤로가기 / 집으로: 분면별 이미지 수정 가능")
    print("- 분면별 좌표 헤더 축소")
    print("- 좌표 입력칸 width 8 -> 6")
    print("- macro_manager_config.json 변경 없음")
    print("- Python syntax 검사 통과")

if __name__ == "__main__":
    main()
