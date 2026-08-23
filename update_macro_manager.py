from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MACRO = BASE_DIR / "macro_manager.py"
CONFIG = BASE_DIR / "macro_manager_config.json"

TARGET_IDS = (
    "16_favorite",
    "17_monster",
    "18_quick_move",
    "19_confirm",
)

NEW_DELAY = 0.5


def backup(path: Path, suffix: str) -> None:
    if not path.exists():
        return

    dst = path.with_name(path.name + suffix)
    if not dst.exists():
        dst.write_text(
            path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def patch_step_block(text: str, step_id: str) -> tuple[str, bool]:
    pattern = re.compile(
        r'(?P<block>\{\s*'
        + rf'"id"\s*:\s*"{re.escape(step_id)}"\s*,'
        + r'.*?'
        + r'\})',
        re.S,
    )

    match = pattern.search(text)
    if not match:
        return text, False

    block = match.group("block")

    delay_pattern = re.compile(
        r'"pre_click_delay"\s*:\s*[-0-9.]+'
    )

    if not delay_pattern.search(block):
        raise RuntimeError(
            f'{step_id} 블록에 pre_click_delay가 없습니다.'
        )

    new_block = delay_pattern.sub(
        f'"pre_click_delay": {NEW_DELAY}',
        block,
        count=1,
    )

    return (
        text[:match.start()]
        + new_block
        + text[match.end():],
        True,
    )


def patch_macro_manager() -> None:
    if not MACRO.exists():
        raise FileNotFoundError(
            f"macro_manager.py를 찾을 수 없습니다: {MACRO}"
        )

    text = MACRO.read_text(encoding="utf-8")
    original = text

    changed_ids = []

    for step_id in TARGET_IDS:
        text, changed = patch_step_block(text, step_id)
        if changed:
            changed_ids.append(step_id)

    missing = [step_id for step_id in TARGET_IDS if step_id not in changed_ids]
    if missing:
        raise RuntimeError(
            "macro_manager.py에서 다음 단계를 찾지 못했습니다: "
            + ", ".join(missing)
        )

    compile(text, str(MACRO), "exec")

    backup(
        MACRO,
        ".bak_before_steps_16_19_preclick_05",
    )

    MACRO.write_text(
        text,
        encoding="utf-8",
    )

    print("[OK] macro_manager.py")
    for step_id in TARGET_IDS:
        print(f"     {step_id}.pre_click_delay = {NEW_DELAY}")


def patch_config() -> None:
    if not CONFIG.exists():
        print(
            "[INFO] macro_manager_config.json 없음 "
            "- 다음 실행 시 macro_manager.py 값 사용"
        )
        return

    data = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    routine = (
        data.get("post_routines", {})
        .get("default_hunting")
    )

    if not routine:
        raise RuntimeError(
            "macro_manager_config.json에 default_hunting이 없습니다."
        )

    found = set()

    for step in routine.get("steps", []):
        step_id = step.get("id")

        if step_id in TARGET_IDS:
            step["pre_click_delay"] = NEW_DELAY
            found.add(step_id)

    missing = [step_id for step_id in TARGET_IDS if step_id not in found]
    if missing:
        raise RuntimeError(
            "macro_manager_config.json에서 다음 단계를 찾지 못했습니다: "
            + ", ".join(missing)
        )

    backup(
        CONFIG,
        ".bak_before_steps_16_19_preclick_05",
    )

    CONFIG.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("[OK] macro_manager_config.json")
    for step_id in TARGET_IDS:
        print(f"     {step_id}.pre_click_delay = {NEW_DELAY}")


if __name__ == "__main__":
    patch_macro_manager()
    patch_config()

    print()
    print("=" * 72)
    print("수정 완료")
    print("=" * 72)
    print("16 즐겨찾기       클릭 전 대기: 0.5초")
    print("17 몬스터         클릭 전 대기: 0.5초")
    print("18 빠른 이동      클릭 전 대기: 0.5초")
    print("19 빠른 이동 확인 클릭 전 대기: 0.5초")
    print()
    print("기존 동작 유지:")
    print("19 빠른 이동 확인 클릭 후 5초 대기")
    print("20 AUTO 감지 후 15초 대기 뒤 클릭")
    print("=" * 72)
