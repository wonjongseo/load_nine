from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENGINE = BASE_DIR / "macro_manager.py"
UI = BASE_DIR / "macro_manager_ui.py"
CONFIG = BASE_DIR / "macro_manager_config.json"


def backup(path: Path, suffix: str) -> None:
    if not path.exists():
        return
    target = path.with_name(path.name + suffix)
    if not target.exists():
        target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def patch_engine() -> None:
    if not ENGINE.exists():
        raise FileNotFoundError(f"macro_manager.py 없음: {ENGINE}")

    text = ENGINE.read_text(encoding="utf-8")

    text = text.replace(
        '{"overrides": {}, "fallbacks": {}, "click_offsets": {}}',
        '{"overrides": {}, "fallbacks": {}}',
    )

    text = re.sub(
        r'(?m)^\s*"click_offsets"\s*:\s*\{\},\s*\n',
        "",
        text,
    )

    text = re.sub(
        r'\ndef target_legacy_click_offsets\(target: dict\) -> dict:\n.*?(?=\ndef save_config\(config: dict\) -> None:)',
        "\n",
        text,
        flags=re.S,
    )

    text = re.sub(
        r'\n    def configured_image_click_point\(\n.*?(?=\n    def advance\()',
        "\n",
        text,
        flags=re.S,
    )

    text = re.sub(
        r'\n\s*routine_click_offsets = target_click_offsets\(\n\s*target,\n\s*routine_id,\n\s*\)\n\s*legacy_click_offsets = target_legacy_click_offsets\(target\)',
        "",
        text,
        count=1,
    )

    patterns = [
        (
            r'click_x, click_y = self\.configured_image_click_point\(\s*'
            r'sandtimer_match,\s*sandtimer_path,\s*\{\s*\*\*sandtimer,\s*'
            r'"image_click_offset": legacy_click_offsets\.get\(\s*"002_sandtimer",\s*\[0, 0\],\s*\),\s*\},\s*\)',
            'click_x, click_y = sandtimer_match[0], sandtimer_match[1]',
        ),
        (
            r'click_x, click_y = self\.configured_image_click_point\(\s*'
            r'action_match,\s*action_path,\s*\{\s*\*\*action_step,\s*'
            r'"image_click_offset": legacy_click_offsets\.get\(\s*pre_death_stage,\s*\[0, 0\],\s*\),\s*\},\s*\)',
            'click_x, click_y = action_match[0], action_match[1]',
        ),
        (
            r'click_x, click_y = self\.configured_image_click_point\(\s*'
            r'confirmed_match,\s*image_path,\s*\{\s*\*\*step,\s*'
            r'"image_click_offset": routine_click_offsets\.get\(\s*step_id,\s*\[0, 0\],\s*\),\s*\},\s*\)',
            'click_x, click_y = confirmed_match[0], confirmed_match[1]',
        ),
    ]

    for pattern, replacement in patterns:
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
        if count == 0:
            print("[WARN] 예상 클릭 보정 블록을 찾지 못함:", replacement)

    text = re.sub(
        r'(?m)^\s*"image_click_offset"\s*:\s*\[[^\]]*\],?\s*\n',
        "",
        text,
    )

    forbidden = [
        "configured_image_click_point",
        "target_click_offsets",
        "target_legacy_click_offsets",
        "routine_click_offsets",
        "legacy_click_offsets",
        "image_click_offset",
        '"click_offsets"',
    ]
    remains = [token for token in forbidden if token in text]
    if remains:
        raise RuntimeError(
            "macro_manager.py에 클릭 보정 관련 코드가 아직 남아 있습니다: "
            + ", ".join(remains)
        )

    compile(text, str(ENGINE), "exec")
    backup(ENGINE, ".bak_before_remove_image_click_offsets")
    ENGINE.write_text(text, encoding="utf-8")
    print("[ENGINE] 이미지 클릭 보정 기능 제거 완료")


def patch_config() -> None:
    if not CONFIG.exists():
        print("[CONFIG] macro_manager_config.json 없음 - 건너뜀")
        return

    raw = CONFIG.read_text(encoding="utf-8")
    data = json.loads(raw)
    removed = 0

    def clean(value):
        nonlocal removed
        if isinstance(value, dict):
            for key in list(value.keys()):
                if key in {"click_offsets", "legacy_click_offsets", "image_click_offset"}:
                    del value[key]
                    removed += 1
                else:
                    clean(value[key])
        elif isinstance(value, list):
            for item in value:
                clean(item)

    clean(data)

    if removed:
        backup(CONFIG, ".bak_before_remove_image_click_offsets")
        CONFIG.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"[CONFIG] 클릭 보정 설정 삭제: {removed}개")


def inspect_ui() -> None:
    if not UI.exists():
        print("[UI] macro_manager_ui.py 없음 - 건너뜀")
        return

    text = UI.read_text(encoding="utf-8")

    tokens = [
        "routine_click_offsets",
        "legacy_click_offsets",
        "click_x_var",
        "click_y_var",
        '"클릭 보정 X"',
        "클릭 보정 0,0",
    ]
    remains = [token for token in tokens if token in text]

    if remains:
        print("[UI] 예전 클릭 보정 UI 흔적이 남아 있음:")
        for item in remains:
            print("  -", item)
        print("[UI] 엔진에서는 더 이상 사용되지 않음.")
    else:
        print("[UI] 클릭 보정 UI 없음 확인")


def verify_center_click() -> None:
    text = ENGINE.read_text(encoding="utf-8")
    center_code = (
        "return rect.left + location[0] + tw // 2, "
        "rect.top + location[1] + th // 2"
    )
    if center_code in text:
        print("[VERIFY] 이미지 매칭 좌표 = 템플릿 정중앙")
    else:
        print("[WARN] find() 중앙 좌표 반환 코드를 자동 확인하지 못했습니다.")


if __name__ == "__main__":
    patch_engine()
    patch_config()
    inspect_ui()
    verify_center_click()

    print()
    print("완료")
    print("- 이미지 클릭: 항상 찾은 이미지 정중앙")
    print("- 이미지 클릭 오프셋/보정: 제거")
    print("- Fallback X/Y: 유지")
    print("- 좌표 클릭 단계: 유지")
