from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main() -> None:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    config_file = repo / "macro_manager_config.json"
    py_file = repo / "macro_manager.py"

    if not config_file.exists():
        raise SystemExit(
            "macro_manager_config.json이 있는 레포 폴더에서 실행하세요.\n"
            '예: py set_return_wait_10s.py "C:\\\\Users\\\\Jongseo Won\\\\Desktop\\\\load_nine"'
        )

    shutil.copy2(config_file, config_file.with_suffix(".json.bak"))

    data = json.loads(config_file.read_text(encoding="utf-8"))
    data["return_wait_seconds"] = 10.0

    config_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # macro_manager.py에 20초 fallback이 하드코딩돼 있으면 10초로 맞춤
    if py_file.exists():
        text = py_file.read_text(encoding="utf-8")
        changed = False

        candidates = [
            ('config.get("return_wait_seconds", 20.0)', 'config.get("return_wait_seconds", 10.0)'),
            ("config.get('return_wait_seconds', 20.0)", "config.get('return_wait_seconds', 10.0)"),
        ]

        for old, new in candidates:
            if old in text:
                text = text.replace(old, new)
                changed = True

        if changed:
            shutil.copy2(py_file, py_file.with_suffix(".py.bak"))
            compile(text, str(py_file), "exec")
            py_file.write_text(text, encoding="utf-8")

    # JSON 유효성 재확인
    json.loads(config_file.read_text(encoding="utf-8"))

    print("[OK] 사망 전 집으로 클릭 후 대기시간 = 10초")
    print("흐름: 집으로 클릭 -> 10초 대기 -> 02 메뉴")


if __name__ == "__main__":
    main()
