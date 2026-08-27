from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MACRO = BASE_DIR / "macro_manager.py"
CONFIG = BASE_DIR / "macro_manager_config.json"


def backup(path: Path, suffix: str) -> None:
    if not path.exists():
        return

    dst = path.with_name(path.name + suffix)

    if not dst.exists():
        dst.write_text(
            path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def patch_macro_manager() -> None:
    if not MACRO.exists():
        raise FileNotFoundError(
            f"macro_manager.py를 찾을 수 없습니다: {MACRO}"
        )

    text = MACRO.read_text(encoding="utf-8")
    original = text

    marker = '    config["default_hunting_v4"] = True\n'

    if marker not in text:
        raise RuntimeError(
            "migrate_default_hunting_v4() 끝 위치를 찾지 못했습니다."
        )

    rule_code = '''    # 13 구매는 최대 5초만 찾고, 못 찾으면 클릭 없이 14단계로 넘어갑니다.
    for step in routine.get("steps", []):
        if step.get("id") == "13_buy":
            step["timeout"] = 5.0
            step["on_timeout"] = "skip"
            step["skip_count"] = 1
            break

'''

    if 'if step.get("id") == "13_buy":' not in text:
        text = text.replace(
            marker,
            rule_code + marker,
            1,
        )

    compile(
        text,
        str(MACRO),
        "exec",
    )

    backup(
        MACRO,
        ".bak_before_13_buy_skip_5sec",
    )

    MACRO.write_text(
        text,
        encoding="utf-8",
    )

    print("[OK] macro_manager.py")
    print("     13_buy.timeout = 5.0")
    print('     13_buy.on_timeout = "skip"')
    print("     13_buy.skip_count = 1")


def patch_config() -> None:
    if not CONFIG.exists():
        print(
            "[INFO] macro_manager_config.json 없음 "
            "- 다음 프로그램 실행 때 자동 적용됩니다."
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

    found = False

    for step in routine.get("steps", []):
        if step.get("id") == "13_buy":
            step["timeout"] = 5.0
            step["on_timeout"] = "skip"
            step["skip_count"] = 1
            found = True
            break

    if not found:
        raise RuntimeError(
            'macro_manager_config.json의 기본 루틴에서 id="13_buy"를 찾지 못했습니다.'
        )

    backup(
        CONFIG,
        ".bak_before_13_buy_skip_5sec",
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
    print("     13_buy.timeout = 5.0")
    print('     13_buy.on_timeout = "skip"')
    print("     13_buy.skip_count = 1")


if __name__ == "__main__":
    patch_macro_manager()
    patch_config()

    print()
    print("=" * 72)
    print("13 구매 timeout 처리 수정 완료")
    print("=" * 72)
    print("12 100% 수량")
    print("→ 13 구매 이미지 검색 시작")
    print("→ 최대 5초 검색")
    print()
    print("13 구매 발견:")
    print("→ 기존처럼 13 구매 클릭")
    print("→ 14 상점 닫기 검색")
    print()
    print("13 구매 5초 동안 미발견:")
    print("→ 아무 좌표도 클릭하지 않음")
    print("→ 13 구매 스킵")
    print("→ 바로 14 상점 닫기 검색")
    print("=" * 72)
