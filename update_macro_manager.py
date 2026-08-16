from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path


def backup(path: Path) -> None:
    bak = path.with_suffix(path.suffix + '.bak')
    shutil.copy2(path, bak)
    print(f'[BACKUP] {bak}')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 block, found={count}')
    return text.replace(old, new, 1)


def patch_python(path: Path) -> None:
    text = path.read_text(encoding='utf-8')

    if 'MOUSE_CLICK_LOCK = threading.Lock()' not in text:
        marker = 'CLICK_HOLD_SECONDS = 0.08\n'
        text = replace_once(
            text,
            marker,
            marker + '\n# 여러 분면이 루틴을 병행해도 실제 마우스 입력은 한 번에 하나만 보냅니다.\nMOUSE_CLICK_LOCK = threading.Lock()\n',
            'mouse lock',
        )

    old = '''def held_left_click(x: int | None = None, y: int | None = None) -> None:\n    user32 = ctypes.WinDLL("user32", use_last_error=True)\n    if x is not None and y is not None:\n        user32.SetCursorPos(int(x), int(y))\n        time.sleep(0.07)\n    down = Input(type=0, mi=MouseInput(dwFlags=0x0002))\n    up = Input(type=0, mi=MouseInput(dwFlags=0x0004))\n    if user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(Input)) != 1:\n        raise ctypes.WinError(ctypes.get_last_error())\n    time.sleep(CLICK_HOLD_SECONDS)\n    if user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(Input)) != 1:\n        raise ctypes.WinError(ctypes.get_last_error())\n'''
    new = '''def held_left_click(x: int | None = None, y: int | None = None) -> None:\n    with MOUSE_CLICK_LOCK:\n        user32 = ctypes.WinDLL("user32", use_last_error=True)\n        if x is not None and y is not None:\n            user32.SetCursorPos(int(x), int(y))\n            time.sleep(0.07)\n        down = Input(type=0, mi=MouseInput(dwFlags=0x0002))\n        up = Input(type=0, mi=MouseInput(dwFlags=0x0004))\n        if user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(Input)) != 1:\n            raise ctypes.WinError(ctypes.get_last_error())\n        time.sleep(CLICK_HOLD_SECONDS)\n        if user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(Input)) != 1:\n            raise ctypes.WinError(ctypes.get_last_error())\n'''
    if old in text:
        text = replace_once(text, old, new, 'held_left_click')

    if 'def migrate_default_hunting_v3(' not in text:
        marker = '\ndef mark_target_coordinate_steps(config: dict) -> None:\n'
        migration = '''\ndef migrate_default_hunting_v3(config: dict) -> None:\n    # 기본 루틴: 15 월드맵 -> 16 이동할 월드 -> ... -> 22 AUTO\n    # 기존 override 호환성을 위해 기존 내부 ID는 그대로 유지합니다.\n    routines = config.get("post_routines", {})\n    routine = routines.get("default_hunting")\n    if not routine:\n        return\n\n    steps = routine.setdefault("steps", [])\n    ids = [step.get("id") for step in steps]\n    if "16_world" not in ids:\n        insert_at = next((i + 1 for i, s in enumerate(steps) if s.get("id") == "15_world_map"), None)\n        if insert_at is not None:\n            steps.insert(insert_at, {\n                "id": "16_world",\n                "name": "16 이동할 월드",\n                "image": "",\n                "timeout": 5.0,\n                "on_timeout": "skip",\n                "skip_count": 1,\n                "skip_if_no_image": True,\n                "pre_click_delay": PRE_CLICK_DELAY,\n            })\n\n    renamed = {\n        "16_region": "17 이동할 지역",\n        "17_hunting_ground": "18 이동할 사냥터",\n        "18_monster": "19 몬스터",\n        "19_quick_move": "20 빠른 이동",\n        "20_confirm": "21 빠른 이동 확인",\n        "21_auto": "22 AUTO",\n    }\n    for step in steps:\n        if step.get("id") in renamed:\n            step["name"] = renamed[step["id"]]\n    config["default_hunting_v3"] = True\n\n'''
        text = text.replace(marker, migration + marker, 1)

    old = '''    if config.get("full_routines_v2"):\n        mark_target_coordinate_steps(config)\n        for target in config.get("targets", {}).values():\n            target.setdefault("post_routine_id", "default_hunting")\n        return\n'''
    new = '''    if config.get("full_routines_v2"):\n        migrate_default_hunting_v3(config)\n        mark_target_coordinate_steps(config)\n        for target in config.get("targets", {}).values():\n            target.setdefault("post_routine_id", "default_hunting")\n        return\n'''
    if old in text:
        text = replace_once(text, old, new, 'v2 migration')

    old = '''    config["steps"] = []\n    config["full_routines_v2"] = True\n    mark_target_coordinate_steps(config)\n'''
    new = '''    config["steps"] = []\n    config["full_routines_v2"] = True\n    migrate_default_hunting_v3(config)\n    mark_target_coordinate_steps(config)\n'''
    if old in text:
        text = replace_once(text, old, new, 'new migration')

    old = '''                        if (\n                            self.active_target_key is not None\n                            and key != self.active_target_key\n                        ):\n                            continue\n'''
    if old in text:
        text = replace_once(
            text, old,
            '''                        # 분면별 step/deadline 상태를 독립적으로 진행합니다.\n''',
            'active target filter',
        )

    old = '''                        if not target.get("enabled", False):\n                            if self.active_target_key == key:\n                                self.active_target_key = None\n                            continue\n'''
    new = '''                        if not target.get("enabled", False):\n                            continue\n'''
    if old in text:
        text = replace_once(text, old, new, 'disabled target')

    old = '''        if next_index == 0 and self.active_target_key == key:\n            logging.info("%s 루틴 완료 / 분면 작업 잠금 해제", key)\n            self.active_target_key = None\n'''
    new = '''        if next_index == 0:\n            logging.info("%s 루틴 완료", key)\n'''
    if old in text:
        text = replace_once(text, old, new, 'advance')

    # reset_target()에 남아있는 기존 active_target 해제 코드를 제거합니다.
    old = '''        if self.active_target_key == key:\n            self.active_target_key = None\n'''
    if old in text:
        text = text.replace(old, '', 1)

    # 잠금용 대입/로그 블록은 더 이상 필요하지 않습니다.
    text = re.sub(
        r'(?m)^(\s*)if self\.active_target_key is None:\n\1    self\.active_target_key = key\n\1    logging\.info\(\n\1        "%s 사망 진입 루틴 시작 / 분면 작업 잠금",\n\1        key,\n\1    \)\n',
        r'\1logging.info("%s 사망 진입 루틴 시작", key)\n', text)
    text = re.sub(
        r'(?m)^(\s*)if self\.active_target_key is None:\n\1    self\.active_target_key = key\n\1    logging\.info\(\n\1        "%s 사망 전 귀환 루틴 시작 / 분면 작업 잠금",\n\1        key,\n\1    \)\n',
        r'\1logging.info("%s 사망 전 귀환 루틴 시작", key)\n', text)
    text = re.sub(
        r'(?m)^(\s*)if self\.active_target_key is None:\n\1    self\.active_target_key = key\n\1    logging\.info\(\n\1        "%s 루틴 시작 / 분면 작업 잠금",\n\1        key,\n\1    \)\n',
        r'\1logging.info("%s 루틴 진행 시작", key)\n', text)
    text = re.sub(r'(?m)^\s*if self\.active_target_key == key:\n\s*self\.active_target_key = None\n', '', text)

    anchor = '''                        if step_uses_coordinate:\n                            image_path = ""\n                            fallback = routine_fallbacks.get(step_id)\n                            if fallback is None:\n                                fallback = step.get("fallback")\n                        now = time.monotonic()\n'''
    replacement = '''                        if step_uses_coordinate:\n                            image_path = ""\n                            fallback = routine_fallbacks.get(step_id)\n                            if fallback is None:\n                                fallback = step.get("fallback")\n\n                        # 이동할 월드: 분면 전용/공용 이미지가 모두 없으면 즉시 다음 단계.\n                        if step.get("skip_if_no_image") and not image_path and not step_uses_coordinate:\n                            self.app.set_row_status(\n                                key,\n                                f"{index + 1}. {step['name']} 이미지 없음 → 다음 단계",\n                            )\n                            self.advance(key, len(steps))\n                            continue\n\n                        now = time.monotonic()\n'''
    if anchor in text:
        text = replace_once(text, anchor, replacement, 'skip_if_no_image')

    path.write_text(text, encoding='utf-8')
    print(f'[OK] {path.name}')


def patch_config(path: Path) -> None:
    data = json.loads(path.read_text(encoding='utf-8'))
    routine = data.get('post_routines', {}).get('default_hunting')
    if not routine:
        raise RuntimeError('post_routines.default_hunting not found')

    steps = routine.setdefault('steps', [])
    ids = [step.get('id') for step in steps]
    if '16_world' not in ids:
        insert_at = next((i + 1 for i, s in enumerate(steps) if s.get('id') == '15_world_map'), None)
        if insert_at is None:
            raise RuntimeError('15_world_map not found')
        steps.insert(insert_at, {
            'id': '16_world',
            'name': '16 이동할 월드',
            'image': '',
            'timeout': 5.0,
            'on_timeout': 'skip',
            'skip_count': 1,
            'skip_if_no_image': True,
            'pre_click_delay': 0.5,
        })

    renamed = {
        '16_region': '17 이동할 지역',
        '17_hunting_ground': '18 이동할 사냥터',
        '18_monster': '19 몬스터',
        '19_quick_move': '20 빠른 이동',
        '20_confirm': '21 빠른 이동 확인',
        '21_auto': '22 AUTO',
    }
    for step in steps:
        if step.get('id') in renamed:
            step['name'] = renamed[step['id']]

    data['default_hunting_v3'] = True
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'[OK] {path.name}')


def main() -> None:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    py_file = repo / 'macro_manager.py'
    config_file = repo / 'macro_manager_config.json'
    if not py_file.exists() or not config_file.exists():
        raise SystemExit(
            'macro_manager.py / macro_manager_config.json이 있는 폴더에서 실행하세요.\n'
            '예: py update_macro_manager.py "C:\\Users\\Jongseo Won\\Desktop\\auto"'
        )

    backup(py_file)
    backup(config_file)
    patch_python(py_file)
    patch_config(config_file)
    print('\n수정 완료')
    print('- 여러 분면 상태를 독립적으로 진행')
    print('- 물리 마우스 클릭은 Lock으로 직렬화')
    print('- 15 월드맵 다음에 16 이동할 월드 추가')
    print('- 이동할 월드 이미지 null이면 즉시 17 이동할 지역으로 진행')
    print('- 이미지가 있으면 5초 검색 후 미검출 시 다음 단계')
    print('- 기존 내부 step ID 유지로 기존 분면별 override 보존')
    print('\n검증: py -m py_compile macro_manager.py')


if __name__ == '__main__':
    main()
