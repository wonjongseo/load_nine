from __future__ import annotations

import shutil
import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: 예상 코드 블록을 정확히 1개 찾지 못했습니다. found={count}"
        )
    return text.replace(old, new, 1)


def main() -> None:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    py_file = repo / "macro_manager.py"

    if not py_file.exists():
        raise SystemExit(
            "macro_manager.py가 있는 레포 폴더에서 실행하거나 레포 경로를 지정하세요.\n"
            '예: py enable_fallback_coordinates.py "C:\\Users\\Jongseo Won\\Desktop\\auto"'
        )

    backup = py_file.with_suffix(".py.bak")
    shutil.copy2(py_file, backup)
    print(f"[BACKUP] {backup}")

    text = py_file.read_text(encoding="utf-8")

    # ------------------------------------------------------------
    # 1) 실행 엔진:
    #    이미지 단계도 분면별 fallback 좌표를 읽도록 변경
    # ------------------------------------------------------------
    old_engine = '''                        step_uses_coordinate = (
                            step.get("fallback") is not None
                            or bool(step.get("coordinate_from_target"))
                        )
                        fallback = None
                        if step_uses_coordinate:
                            image_path = ""
                            fallback = routine_fallbacks.get(step_id)
                            if fallback is None:
                                fallback = step.get("fallback")
'''
    new_engine = '''                        step_uses_coordinate = (
                            step.get("fallback") is not None
                            or bool(step.get("coordinate_from_target"))
                        )

                        # fallback 좌표는 이미지 단계에서도 사용할 수 있습니다.
                        # 이미지 단계:
                        #   이미지 탐색 -> timeout -> fallback 좌표 클릭
                        # 좌표 전용 단계:
                        #   기존처럼 이미지를 사용하지 않고 fallback 좌표 사용
                        fallback = routine_fallbacks.get(step_id)
                        if fallback is None:
                            fallback = step.get("fallback")

                        if step_uses_coordinate:
                            image_path = ""
'''
    text = replace_once(
        text,
        old_engine,
        new_engine,
        "이미지 단계 fallback 로딩",
    )

    # ------------------------------------------------------------
    # 2) UI:
    #    좌표 컬럼 이름을 fallback임이 명확하게 변경
    # ------------------------------------------------------------
    old_headers = '''        headers = (
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
    new_headers = '''        headers = (
            "단계 (클릭=캡처)",
            "공용 이미지",
            "현재 적용 이미지 (변경 시 분면 전용)",
            "클릭 보정 X",
            "Y",
            "Fallback X",
            "Y",
            "",
        )
'''
    text = replace_once(
        text,
        old_headers,
        new_headers,
        "fallback 헤더 변경",
    )

    # ------------------------------------------------------------
    # 3) UI 값:
    #    routine 행은 이미지 단계라도 기존 fallback 값을 표시
    #    legacy 행은 현재 동작을 유지
    # ------------------------------------------------------------
    old_point = '''            point = fallbacks.get(sid) or ["", ""] if coordinate_step else ["", ""]
            x_var, y_var = tk.StringVar(value=str(point[0])), tk.StringVar(value=str(point[1]))
'''
    new_point = '''            if scope == "routine":
                point = fallbacks.get(sid) or ["", ""]
            else:
                point = (
                    fallbacks.get(sid) or ["", ""]
                    if coordinate_step
                    else ["", ""]
                )
            x_var = tk.StringVar(value=str(point[0]))
            y_var = tk.StringVar(value=str(point[1]))
'''
    text = replace_once(
        text,
        old_point,
        new_point,
        "fallback 좌표 표시",
    )

    # ------------------------------------------------------------
    # 4) UI 입력 활성화:
    #    routine 행은 모두 fallback X/Y 입력 가능
    #    legacy 행은 기존 coordinate_step일 때만 활성
    # ------------------------------------------------------------
    old_x = '''            ttk.Entry(
                self.body,
                textvariable=x_var,
                width=6,
                state="normal" if coordinate_step else "disabled",
            ).grid(row=row_index, column=5, padx=2)
'''
    new_x = '''            ttk.Entry(
                self.body,
                textvariable=x_var,
                width=6,
                state=(
                    "normal"
                    if scope == "routine" or coordinate_step
                    else "disabled"
                ),
            ).grid(row=row_index, column=5, padx=2)
'''
    text = replace_once(text, old_x, new_x, "Fallback X 활성화")

    old_y = '''            ttk.Entry(
                self.body,
                textvariable=y_var,
                width=6,
                state="normal" if coordinate_step else "disabled",
            ).grid(row=row_index, column=6, padx=2)
'''
    new_y = '''            ttk.Entry(
                self.body,
                textvariable=y_var,
                width=6,
                state=(
                    "normal"
                    if scope == "routine" or coordinate_step
                    else "disabled"
                ),
            ).grid(row=row_index, column=6, padx=2)
'''
    text = replace_once(text, old_y, new_y, "Fallback Y 활성화")

    # ------------------------------------------------------------
    # 5) row metadata:
    #    fallback 저장 가능 여부 추가
    # ------------------------------------------------------------
    old_row = '''                "coordinate": coordinate_step,
                "click_enabled": click_enabled,
                "scope": scope,
'''
    new_row = '''                "coordinate": coordinate_step,
                "fallback_enabled": (
                    scope == "routine" or coordinate_step
                ),
                "click_enabled": click_enabled,
                "scope": scope,
'''
    text = replace_once(
        text,
        old_row,
        new_row,
        "fallback_enabled 추가",
    )

    # ------------------------------------------------------------
    # 6) 저장:
    #    fallback 좌표와 이미지 override를 서로 독립적으로 저장
    #
    #    - routine 이미지 단계: 이미지 + fallback 둘 다 저장 가능
    #    - 좌표 전용 단계: fallback만 저장
    # ------------------------------------------------------------
    old_save = '''                if row["coordinate"]:
                    x, y = row["x"].get().strip(), row["y"].get().strip()
                    if x or y:
                        if not x or not y:
                            raise ValueError
                        fallbacks[row["id"]] = [int(x), int(y)]
                    else:
                        fallbacks.pop(row["id"], None)
                else:
                    override = row["override"].get().strip()
                    if override and override != row["common"]:
                        overrides[row["id"]] = override
                    else:
                        overrides.pop(row["id"], None)
'''
    new_save = '''                if row.get("fallback_enabled", row["coordinate"]):
                    x = row["x"].get().strip()
                    y = row["y"].get().strip()
                    if x or y:
                        if not x or not y:
                            raise ValueError
                        fallbacks[row["id"]] = [int(x), int(y)]
                    else:
                        fallbacks.pop(row["id"], None)

                # 좌표 전용 단계가 아닌 경우에는 이미지 설정도 별도로 저장합니다.
                if not row["coordinate"]:
                    override = row["override"].get().strip()
                    if override and override != row["common"]:
                        overrides[row["id"]] = override
                    else:
                        overrides.pop(row["id"], None)
'''
    text = replace_once(
        text,
        old_save,
        new_save,
        "fallback/이미지 독립 저장",
    )

    # ------------------------------------------------------------
    # 7) 오류 메시지를 X/Y 한 쌍 입력이라는 점이 보이게 개선
    # ------------------------------------------------------------
    text = text.replace(
        'messagebox.showerror("좌표 오류", "X와 Y에는 정수를 입력하세요.", parent=self)',
        'messagebox.showerror('
        '"좌표 오류", '
        '"Fallback X와 Y는 둘 다 비우거나 둘 다 정수로 입력하세요.", '
        'parent=self'
        ')',
        1,
    )

    # 최종 문법 검사
    compile(text, str(py_file), "exec")
    py_file.write_text(text, encoding="utf-8")

    print()
    print("[OK] macro_manager.py 수정 완료")
    print("[OK] Python syntax 검사 통과")
    print()
    print("변경 내용:")
    print("- 01~22 모든 루틴 행에서 Fallback X/Y 입력 가능")
    print("- 이미지 단계는 timeout까지 이미지 검색")
    print("- timeout 시 fallback X/Y가 있으면 해당 상대좌표 클릭")
    print("- fallback X/Y가 없으면 기존처럼 이미지 대기 반복")
    print("- 15 월드맵 같은 좌표 전용 단계는 기존 동작 유지")
    print("- fallback 좌표는 분면 왼쪽 위 기준 상대좌표")
    print()
    print(f"백업: {backup}")


if __name__ == "__main__":
    main()
