from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).with_name("macro_manager_ui.py")

if not TARGET.exists():
    raise FileNotFoundError(f"macro_manager_ui.py를 찾을 수 없습니다: {TARGET}")

text = TARGET.read_text(encoding="utf-8")
original = text

if "import sqlite3\n" not in text:
    text = text.replace(
        "from macro_manager import *  # noqa: F401,F403\n",
        "from macro_manager import *  # noqa: F401,F403\n\nimport sqlite3\n",
        1,
    )

start = text.find("class DungeonSettingsWindow(tk.Toplevel):")
if start != -1:
    end = text.find("\nclass MacroManager:", start)
    if end == -1:
        raise RuntimeError("기존 DungeonSettingsWindow 끝을 찾지 못했습니다.")
    text = text[:start] + text[end + 1:]

if "class TargetDungeonSettingsWindow(tk.Toplevel):" not in text:
    marker = "\nclass MacroManager:"
    if marker not in text:
        raise RuntimeError("MacroManager 클래스 위치를 찾지 못했습니다.")
    text = text.replace(
        marker,
        "\n" + 'class TargetDungeonSettingsWindow(tk.Toplevel):\n    IMAGE_ITEMS = (\n        ("menu", "메뉴", "02_menu.png"),\n        ("dungeon", "던전 메뉴", "dungeon.png"),\n        ("dungeon_A", "던전 A", "dungeon_A.png"),\n        ("dungeon_B", "던전 B", "dungeon_B.png"),\n        ("enter", "입장", "enter.png"),\n        ("auto", "AUTO", "21_auto.png"),\n        ("in_dungeon", "던전 내부 확인", "in_dungeon.png"),\n        ("exit", "나가기", "exit.png"),\n    )\n\n    def __init__(self, app: "MacroManager", key: str) -> None:\n        super().__init__(app.root)\n        self.app = app\n        self.key = key\n        self.title(f"던전 설정 - {app.targets[key][0]}")\n        self.transient(app.root)\n        self.minsize(980, 680)\n        center_on_parent(self, app.root, 1080, 760)\n\n        dungeon_root = self.app.config.setdefault("dungeon_daily", {})\n        targets = dungeon_root.setdefault("targets", {})\n        self.cfg = targets.setdefault(\n            key,\n            {"A": True, "B": True, "images": {}},\n        )\n        self.cfg.setdefault("images", {})\n\n        self.a_var = tk.BooleanVar(value=bool(self.cfg.get("A", True)))\n        self.b_var = tk.BooleanVar(value=bool(self.cfg.get("B", True)))\n        self.a_status = tk.StringVar(value="이용가능")\n        self.b_status = tk.StringVar(value="이용가능")\n        self.image_vars: dict[str, tk.StringVar] = {}\n\n        outer = ttk.Frame(self, padding=16)\n        outer.pack(fill="both", expand=True)\n\n        title_row = ttk.Frame(outer)\n        title_row.pack(fill="x", pady=(0, 12))\n\n        ttk.Label(\n            title_row,\n            text=f"{app.targets[key][0]} - 매일 던전",\n            font=("Segoe UI Semibold", 14),\n        ).pack(side="left")\n\n        ttk.Button(\n            title_row,\n            text="오늘 상태 새로고침",\n            command=self.refresh_statuses,\n        ).pack(side="right")\n\n        use_box = ttk.LabelFrame(outer, text="실행할 던전", padding=12)\n        use_box.pack(fill="x", pady=(0, 12))\n\n        ttk.Checkbutton(\n            use_box,\n            text="Dungeon A 입장",\n            variable=self.a_var,\n        ).grid(row=0, column=0, sticky="w", padx=(0, 12))\n\n        ttk.Label(\n            use_box,\n            textvariable=self.a_status,\n            width=12,\n            anchor="center",\n        ).grid(row=0, column=1, padx=(0, 30))\n\n        ttk.Checkbutton(\n            use_box,\n            text="Dungeon B 입장",\n            variable=self.b_var,\n        ).grid(row=0, column=2, sticky="w", padx=(0, 12))\n\n        ttk.Label(\n            use_box,\n            textvariable=self.b_status,\n            width=12,\n            anchor="center",\n        ).grid(row=0, column=3)\n\n        ttk.Label(\n            outer,\n            text=(\n                "이미지는 이 분면 전용으로 저장됩니다. "\n                "모니터 해상도/배율이 다르면 각 분면에서 따로 캡처하세요."\n            ),\n        ).pack(anchor="w", pady=(0, 8))\n\n        image_box = ttk.LabelFrame(\n            outer,\n            text="분면 전용 던전 이미지",\n            padding=10,\n        )\n        image_box.pack(fill="both", expand=True)\n\n        headers = ("구분", "현재 적용 이미지", "파일", "캡처")\n        for col, title in enumerate(headers):\n            ttk.Label(\n                image_box,\n                text=title,\n                font=("Segoe UI Semibold", 10),\n                anchor="center",\n            ).grid(row=0, column=col, padx=4, pady=(0, 8), sticky="ew")\n\n        image_box.columnconfigure(1, weight=1)\n\n        saved_images = self.cfg.setdefault("images", {})\n\n        for row, (image_id, label, default_name) in enumerate(\n            self.IMAGE_ITEMS,\n            1,\n        ):\n            default_path = self.default_image_path(default_name)\n            value = saved_images.get(image_id, "") or default_path\n            var = tk.StringVar(value=value)\n            self.image_vars[image_id] = var\n\n            ttk.Label(\n                image_box,\n                text=label,\n                width=18,\n                anchor="w",\n            ).grid(row=row, column=0, padx=4, pady=4, sticky="w")\n\n            ttk.Entry(\n                image_box,\n                textvariable=var,\n                width=68,\n            ).grid(row=row, column=1, padx=4, pady=4, sticky="ew")\n\n            ttk.Button(\n                image_box,\n                text="파일",\n                width=7,\n                command=lambda v=var: self.choose_image(v),\n            ).grid(row=row, column=2, padx=3, pady=4)\n\n            ttk.Button(\n                image_box,\n                text="캡처",\n                width=7,\n                command=lambda iid=image_id, v=var: self.capture_image(\n                    iid,\n                    v,\n                ),\n            ).grid(row=row, column=3, padx=3, pady=4)\n\n        footer = ttk.Frame(outer)\n        footer.pack(fill="x", pady=(14, 0))\n\n        ttk.Button(\n            footer,\n            text="닫기",\n            command=self.destroy,\n        ).pack(side="right", padx=(6, 0))\n\n        ttk.Button(\n            footer,\n            text="저장",\n            style="Primary.TButton",\n            command=self.save,\n        ).pack(side="right")\n\n        self.refresh_statuses()\n\n    def default_image_path(self, filename: str) -> str:\n        test_path = BASE_DIR / "images" / "test" / filename\n        normal_path = BASE_DIR / "images" / filename\n\n        if test_path.exists():\n            return str(test_path)\n        if normal_path.exists():\n            return str(normal_path)\n        return ""\n\n    def choose_image(self, variable: tk.StringVar) -> None:\n        path = filedialog.askopenfilename(\n            parent=self,\n            initialdir=BASE_DIR / "images",\n            filetypes=[\n                ("이미지", "*.png *.jpg *.jpeg *.bmp"),\n                ("모든 파일", "*.*"),\n            ],\n        )\n        if path:\n            variable.set(path)\n\n    def capture_image(\n        self,\n        image_id: str,\n        variable: tk.StringVar,\n    ) -> None:\n        destination = CAPTURE_DIR / "dungeon" / self.key\n\n        path = self.app.capture_and_crop(\n            self.key,\n            f"dungeon_{image_id}",\n            destination_dir=destination,\n            parent=self,\n            suggested_filename=f"dungeon_{image_id}.png",\n        )\n\n        if path:\n            variable.set(path)\n\n    def dungeon_status_db_path(self) -> Path:\n        return BASE_DIR / "dungeon_status.db"\n\n    def read_today_status(self, dungeon: str) -> str:\n        db_path = self.dungeon_status_db_path()\n        if not db_path.exists():\n            return "이용가능"\n\n        try:\n            today = time.strftime("%Y-%m-%d")\n            with sqlite3.connect(db_path) as conn:\n                row = conn.execute(\n                    "SELECT status FROM dungeon_usage "\n                    "WHERE target_key = ? AND dungeon = ? AND usage_date = ?",\n                    (self.key, dungeon, today),\n                ).fetchone()\n\n            if row and str(row[0]).upper() == "COMPLETED":\n                return "만료"\n            return "이용가능"\n        except Exception:\n            logging.exception(\n                "던전 상태 DB 읽기 실패: %s / %s",\n                self.key,\n                dungeon,\n            )\n            return "확인 실패"\n\n    def refresh_statuses(self) -> None:\n        self.a_status.set(self.read_today_status("A"))\n        self.b_status.set(self.read_today_status("B"))\n\n    def save(self) -> None:\n        self.cfg["A"] = bool(self.a_var.get())\n        self.cfg["B"] = bool(self.b_var.get())\n\n        images = self.cfg.setdefault("images", {})\n        for image_id, variable in self.image_vars.items():\n            value = variable.get().strip()\n            if value:\n                images[image_id] = value\n            else:\n                images.pop(image_id, None)\n\n        self.app.persist()\n        self.app.global_status.set(\n            f"{self.app.targets[self.key][0]} 던전 설정 저장 완료"\n        )\n        self.destroy()\n' + marker,
        1,
    )

for block in [
    """        ttk.Button(
            top,
            text="던전",
            command=self.open_dungeon_settings,
        ).pack(side="left", padx=3)
""",
    """        ttk.Button(top, text="던전", command=self.open_dungeon_settings).pack(side="left", padx=3)
""",
]:
    text = text.replace(block, "", 1)

text = text.replace(
    """    def open_dungeon_settings(self) -> None:
        DungeonSettingsWindow(self)
""",
    "",
    1,
)

header_pairs = [
    (
        'headers = ("사용", "대상", "상태", "선택 루틴", "루틴 설정", "현재 위치 테스트")',
        'headers = ("사용", "대상", "상태", "선택 루틴", "루틴 설정", "던전", "현재 위치 테스트")',
    ),
    (
        'headers = ("사용", "대상", "상태", "선택 루틴", "분면 루틴 설정", "현재 위치 테스트")',
        'headers = ("사용", "대상", "상태", "선택 루틴", "분면 루틴 설정", "던전", "현재 위치 테스트")',
    ),
    (
        'headers = ("사용", "대상", "상태", "선택 루틴", "루틴 이미지·좌표", "현재 위치 테스트")',
        'headers = ("사용", "대상", "상태", "선택 루틴", "루틴 이미지·좌표", "던전", "현재 위치 테스트")',
    ),
]

header_done = False
for old, new in header_pairs:
    if old in text:
        text = text.replace(old, new, 1)
        header_done = True
        break

if not header_done:
    raise RuntimeError("메인 테이블 headers를 찾지 못했습니다.")

row_pairs = [
    (
        '            ttk.Button(container, text="루틴 설정", command=lambda k=key: TargetEditor(self, k)).grid(row=row, column=4, padx=5)\n'
        '            ttk.Button(container, text="분면 중앙 클릭", command=lambda k=key: self.test_target(k)).grid(row=row, column=5, padx=5)\n',
        '            ttk.Button(container, text="루틴 설정", command=lambda k=key: TargetEditor(self, k)).grid(row=row, column=4, padx=5)\n'
        '            ttk.Button(container, text="던전", command=lambda k=key: TargetDungeonSettingsWindow(self, k)).grid(row=row, column=5, padx=5)\n'
        '            ttk.Button(container, text="분면 중앙 클릭", command=lambda k=key: self.test_target(k)).grid(row=row, column=6, padx=5)\n',
    ),
    (
        '            ttk.Button(container, text="분면 루틴 설정", command=lambda k=key: TargetEditor(self, k)).grid(row=row, column=4, padx=5)\n'
        '            ttk.Button(container, text="분면 중앙 클릭", command=lambda k=key: self.test_target(k)).grid(row=row, column=5, padx=5)\n',
        '            ttk.Button(container, text="분면 루틴 설정", command=lambda k=key: TargetEditor(self, k)).grid(row=row, column=4, padx=5)\n'
        '            ttk.Button(container, text="던전", command=lambda k=key: TargetDungeonSettingsWindow(self, k)).grid(row=row, column=5, padx=5)\n'
        '            ttk.Button(container, text="분면 중앙 클릭", command=lambda k=key: self.test_target(k)).grid(row=row, column=6, padx=5)\n',
    ),
]

row_done = False
for old, new in row_pairs:
    if old in text:
        text = text.replace(old, new, 1)
        row_done = True
        break

if not row_done:
    raise RuntimeError("메인 테이블 분면 버튼 영역을 찾지 못했습니다.")

if text == original:
    raise RuntimeError("변경 사항이 없습니다.")

backup = TARGET.with_suffix(".py.bak_before_target_dungeon_ui")
if not backup.exists():
    backup.write_text(original, encoding="utf-8")

compile(text, str(TARGET), "exec")
TARGET.write_text(text, encoding="utf-8")

print("수정 완료:", TARGET)
print("백업:", backup)
print()
print("- header 던전 버튼 제거")
print("- 분면별 행에 던전 버튼 추가")
print("- 분면별 A/B 체크 + 오늘 상태")
print("- 분면별 던전 이미지 등록/캡처")
print("- menu/dungeon/A/B/enter/auto/in_dungeon/exit")
print("- 저장 위치: dungeon_daily.targets.<target>.images")
