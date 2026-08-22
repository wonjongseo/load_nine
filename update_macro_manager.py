from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).with_name("macro_manager_ui.py")

if not TARGET.exists():
    raise FileNotFoundError(
        f"macro_manager_ui.py를 찾을 수 없습니다: {TARGET}"
    )

text = TARGET.read_text(encoding="utf-8")
original = text

CLASSES_CODE = '\nclass RangeTestRunner:\n    """기본 전체 루틴의 일부 구간을 모든 모니터/분면에서 테스트합니다."""\n\n    def __init__(self, app: "MacroManager") -> None:\n        self.app = app\n        self.stop_event = threading.Event()\n        self.threads: list[threading.Thread] = []\n        self._remaining = 0\n        self._lock = threading.Lock()\n        self.running = False\n\n    def stop(self) -> None:\n        self.stop_event.set()\n\n    def start(self, test_range: dict) -> None:\n        if self.running:\n            return\n\n        config = self.app.config_snapshot()\n        routine = (\n            config.get("post_routines", {})\n            .get("default_hunting", {})\n        )\n        all_steps = list(routine.get("steps", []))\n\n        start_id = test_range.get("start_id")\n        end_id = test_range.get("end_id")\n\n        start_index = next(\n            (\n                i\n                for i, step in enumerate(all_steps)\n                if step.get("id") == start_id\n            ),\n            None,\n        )\n        end_index = next(\n            (\n                i\n                for i, step in enumerate(all_steps)\n                if step.get("id") == end_id\n            ),\n            None,\n        )\n\n        if start_index is None or end_index is None:\n            raise ValueError(\n                "테스트 시작/종료 단계를 현재 기본 루틴에서 찾을 수 없습니다."\n            )\n\n        if start_index > end_index:\n            raise ValueError(\n                "테스트 시작 단계가 종료 단계보다 뒤에 있습니다."\n            )\n\n        steps = all_steps[start_index:end_index + 1]\n        if not steps:\n            raise ValueError("테스트할 단계가 없습니다.")\n\n        self.stop_event.clear()\n        self.running = True\n        self.threads = []\n\n        targets = list(self.app.targets.items())\n\n        with self._lock:\n            self._remaining = len(targets)\n\n        if not targets:\n            self.running = False\n            return\n\n        for key, (label, rect) in targets:\n            thread = threading.Thread(\n                target=self._run_target,\n                args=(\n                    key,\n                    label,\n                    rect,\n                    steps,\n                    config,\n                ),\n                name=f"range-test-{key}",\n                daemon=True,\n            )\n            self.threads.append(thread)\n            thread.start()\n\n    def _wait(self, seconds: float) -> bool:\n        return self.stop_event.wait(max(0.0, float(seconds)))\n\n    def _finish_target(self) -> None:\n        done = False\n\n        with self._lock:\n            self._remaining -= 1\n            done = self._remaining <= 0\n\n        if done:\n            self.running = False\n            try:\n                self.app.root.after(\n                    0,\n                    self.app.on_range_test_completed,\n                )\n            except tk.TclError:\n                pass\n\n    def _capture_gray(\n        self,\n        capture: mss.MSS,\n        rect: Rect,\n    ) -> np.ndarray:\n        frame = np.asarray(\n            capture.grab(rect.as_mss())\n        )\n        return cv2.cvtColor(\n            frame,\n            cv2.COLOR_BGRA2GRAY,\n        )\n\n    def _run_target(\n        self,\n        key: str,\n        label: str,\n        rect: Rect,\n        steps: list[dict],\n        config: dict,\n    ) -> None:\n        try:\n            target = (\n                config.get("targets", {})\n                .get(key, {})\n            )\n\n            overrides, fallbacks = target_step_settings(\n                target,\n                "default_hunting",\n            )\n\n            with mss.MSS() as capture:\n                for range_index, step in enumerate(\n                    steps,\n                    1,\n                ):\n                    if self.stop_event.is_set():\n                        return\n\n                    if not self._execute_step(\n                        capture,\n                        key,\n                        rect,\n                        step,\n                        overrides,\n                        fallbacks,\n                        range_index,\n                        len(steps),\n                    ):\n                        return\n\n            self.app.set_row_status(\n                key,\n                "구간 테스트 완료",\n            )\n\n        except Exception as exc:\n            logging.exception(\n                "%s 구간 테스트 오류",\n                label,\n            )\n            self.app.set_row_status(\n                key,\n                f"테스트 오류: {exc}",\n            )\n        finally:\n            self._finish_target()\n\n    def _execute_step(\n        self,\n        capture: mss.MSS,\n        key: str,\n        rect: Rect,\n        step: dict,\n        overrides: dict,\n        fallbacks: dict,\n        range_index: int,\n        range_count: int,\n    ) -> bool:\n        step_id = step.get("id", "")\n        step_name = step.get("name", step_id)\n\n        fallback = fallbacks.get(step_id)\n        if fallback is None:\n            fallback = step.get("fallback")\n\n        coordinate_only = (\n            step.get("fallback") is not None\n            or bool(step.get("coordinate_from_target"))\n        )\n\n        if coordinate_only:\n            if not fallback or len(fallback) != 2:\n                self.app.set_row_status(\n                    key,\n                    f"테스트 {range_index}/{range_count} "\n                    f"{step_name}: 좌표 없음",\n                )\n                return False\n\n            if self._wait(\n                float(\n                    step.get(\n                        "pre_click_delay",\n                        PRE_CLICK_DELAY,\n                    )\n                )\n            ):\n                return False\n\n            x = rect.left + int(fallback[0])\n            y = rect.top + int(fallback[1])\n\n            held_left_click(x, y)\n\n            self.app.set_row_status(\n                key,\n                f"테스트 {range_index}/{range_count} "\n                f"{step_name} 좌표 클릭",\n            )\n\n            if self._wait(\n                float(\n                    step.get(\n                        "after_click_delay",\n                        0.0,\n                    )\n                )\n            ):\n                return False\n\n            return True\n\n        image_path = (\n            overrides.get(step_id)\n            or step.get("image", "")\n        )\n\n        if not image_path:\n            if step.get("skip_if_no_image"):\n                self.app.set_row_status(\n                    key,\n                    f"테스트 {range_index}/{range_count} "\n                    f"{step_name}: 이미지 없음 → 건너뜀",\n                )\n                return True\n\n            self.app.set_row_status(\n                key,\n                f"테스트 {range_index}/{range_count} "\n                f"{step_name}: 이미지 없음",\n            )\n            return False\n\n        delay_before = float(\n            step.get("delay_before", 0.0)\n        )\n\n        if self._wait(delay_before):\n            return False\n\n        timeout = max(\n            0.0,\n            float(\n                step.get(\n                    "timeout",\n                    10.0,\n                )\n            ),\n        )\n        deadline = time.monotonic() + timeout\n\n        while not self.stop_event.is_set():\n            gray = self._capture_gray(\n                capture,\n                rect,\n            )\n\n            match = self.app.engine.find(\n                gray,\n                image_path,\n                rect,\n            )\n\n            if match:\n                pre_delay = float(\n                    step.get(\n                        "pre_click_delay",\n                        PRE_CLICK_DELAY,\n                    )\n                )\n\n                self.app.set_row_status(\n                    key,\n                    f"테스트 {range_index}/{range_count} "\n                    f"{step_name} 감지 → {pre_delay:g}초 후 클릭",\n                )\n\n                if self._wait(pre_delay):\n                    return False\n\n                fresh_gray = self._capture_gray(\n                    capture,\n                    rect,\n                )\n                confirmed = self.app.engine.find(\n                    fresh_gray,\n                    image_path,\n                    rect,\n                )\n\n                if confirmed is None:\n                    continue\n\n                click_x = confirmed[0]\n                click_y = confirmed[1]\n\n                # 기본 루틴 17 몬스터의 기존 특수 클릭 규칙.\n                if step_id == "17_monster":\n                    click_x += 10\n\n                held_left_click(\n                    click_x,\n                    click_y,\n                )\n\n                self.app.set_row_status(\n                    key,\n                    f"테스트 {range_index}/{range_count} "\n                    f"{step_name} 클릭",\n                )\n\n                if self._wait(\n                    float(\n                        step.get(\n                            "after_click_delay",\n                            0.0,\n                        )\n                    )\n                ):\n                    return False\n\n                return True\n\n            if time.monotonic() >= deadline:\n                if fallback and len(fallback) == 2:\n                    pre_delay = float(\n                        step.get(\n                            "pre_click_delay",\n                            PRE_CLICK_DELAY,\n                        )\n                    )\n\n                    if self._wait(pre_delay):\n                        return False\n\n                    x = rect.left + int(fallback[0])\n                    y = rect.top + int(fallback[1])\n\n                    held_left_click(x, y)\n\n                    self.app.set_row_status(\n                        key,\n                        f"테스트 {range_index}/{range_count} "\n                        f"{step_name}: 미검출 → 좌표 클릭",\n                    )\n                    return True\n\n                if step.get("on_timeout") == "skip":\n                    self.app.set_row_status(\n                        key,\n                        f"테스트 {range_index}/{range_count} "\n                        f"{step_name}: timeout → 건너뜀",\n                    )\n                    return True\n\n                if step.get("on_timeout") == "click_current":\n                    if self._wait(\n                        float(\n                            step.get(\n                                "pre_click_delay",\n                                PRE_CLICK_DELAY,\n                            )\n                        )\n                    ):\n                        return False\n\n                    held_left_click()\n\n                    self.app.set_row_status(\n                        key,\n                        f"테스트 {range_index}/{range_count} "\n                        f"{step_name}: timeout → 현재 위치 클릭",\n                    )\n                    return True\n\n                self.app.set_row_status(\n                    key,\n                    f"테스트 {range_index}/{range_count} "\n                    f"{step_name}: timeout",\n                )\n                return False\n\n            self._wait(SCAN_INTERVAL)\n\n        return False\n\n\nclass TestRangeManager(tk.Toplevel):\n    """공유 테스트 구간을 추가/삭제합니다."""\n\n    def __init__(self, app: "MacroManager") -> None:\n        super().__init__(app.root)\n        self.app = app\n        self.title("구간 테스트 관리")\n        self.transient(app.root)\n        self.resizable(False, False)\n        center_on_parent(\n            self,\n            app.root,\n            720,\n            500,\n        )\n\n        frame = ttk.Frame(\n            self,\n            padding=16,\n        )\n        frame.pack(\n            fill="both",\n            expand=True,\n        )\n\n        ttk.Label(\n            frame,\n            text="모든 모니터/분면이 공유하는 테스트 구간",\n            font=("Segoe UI Semibold", 13),\n        ).pack(\n            anchor="w",\n            pady=(0, 10),\n        )\n\n        self.listbox = tk.Listbox(\n            frame,\n            width=80,\n            height=14,\n            exportselection=False,\n        )\n        self.listbox.pack(\n            fill="both",\n            expand=True,\n        )\n\n        buttons = ttk.Frame(frame)\n        buttons.pack(\n            fill="x",\n            pady=(12, 0),\n        )\n\n        ttk.Button(\n            buttons,\n            text="새 테스트 추가",\n            command=self.add_test,\n        ).pack(\n            side="left",\n        )\n\n        ttk.Button(\n            buttons,\n            text="선택 테스트 삭제",\n            command=self.delete_test,\n        ).pack(\n            side="left",\n            padx=6,\n        )\n\n        ttk.Button(\n            buttons,\n            text="닫기",\n            command=self.destroy,\n        ).pack(\n            side="right",\n        )\n\n        self.refresh()\n\n    def test_ranges(self) -> list[dict]:\n        return self.app.config.setdefault(\n            "test_ranges",\n            [],\n        )\n\n    def default_steps(self) -> list[dict]:\n        return list(\n            self.app.config.get(\n                "post_routines",\n                {},\n            )\n            .get(\n                "default_hunting",\n                {},\n            )\n            .get(\n                "steps",\n                [],\n            )\n        )\n\n    def step_display(self, step: dict) -> str:\n        return step.get(\n            "name",\n            step.get("id", ""),\n        )\n\n    def refresh(self) -> None:\n        self.listbox.delete(\n            0,\n            "end",\n        )\n\n        steps = {\n            step.get("id"): self.step_display(step)\n            for step in self.default_steps()\n        }\n\n        for item in self.test_ranges():\n            start_name = steps.get(\n                item.get("start_id"),\n                item.get("start_id", "?"),\n            )\n            end_name = steps.get(\n                item.get("end_id"),\n                item.get("end_id", "?"),\n            )\n\n            self.listbox.insert(\n                "end",\n                f"{item.get(\'name\', \'테스트\')}  |  "\n                f"{start_name} → {end_name}",\n            )\n\n    def add_test(self) -> None:\n        steps = self.default_steps()\n\n        if not steps:\n            messagebox.showerror(\n                "기본 루틴 없음",\n                "기본 전체 루틴 단계가 없습니다.",\n                parent=self,\n            )\n            return\n\n        dialog = tk.Toplevel(self)\n        dialog.title("새 구간 테스트")\n        dialog.transient(self)\n        dialog.resizable(False, False)\n        center_on_parent(\n            dialog,\n            self,\n            620,\n            310,\n        )\n\n        body = ttk.Frame(\n            dialog,\n            padding=18,\n        )\n        body.pack(\n            fill="both",\n            expand=True,\n        )\n\n        displays = [\n            self.step_display(step)\n            for step in steps\n        ]\n        display_to_id = {\n            self.step_display(step): step.get("id")\n            for step in steps\n        }\n\n        name_var = tk.StringVar(\n            value="새 구간 테스트"\n        )\n        start_var = tk.StringVar(\n            value=displays[0]\n        )\n        end_var = tk.StringVar(\n            value=displays[-1]\n        )\n\n        ttk.Label(\n            body,\n            text="테스트 이름",\n        ).grid(\n            row=0,\n            column=0,\n            sticky="w",\n            pady=7,\n        )\n\n        ttk.Entry(\n            body,\n            textvariable=name_var,\n            width=42,\n        ).grid(\n            row=0,\n            column=1,\n            sticky="ew",\n            pady=7,\n        )\n\n        ttk.Label(\n            body,\n            text="시작 단계",\n        ).grid(\n            row=1,\n            column=0,\n            sticky="w",\n            pady=7,\n        )\n\n        ttk.Combobox(\n            body,\n            textvariable=start_var,\n            values=displays,\n            state="readonly",\n            width=38,\n        ).grid(\n            row=1,\n            column=1,\n            sticky="ew",\n            pady=7,\n        )\n\n        ttk.Label(\n            body,\n            text="종료 단계",\n        ).grid(\n            row=2,\n            column=0,\n            sticky="w",\n            pady=7,\n        )\n\n        ttk.Combobox(\n            body,\n            textvariable=end_var,\n            values=displays,\n            state="readonly",\n            width=38,\n        ).grid(\n            row=2,\n            column=1,\n            sticky="ew",\n            pady=7,\n        )\n\n        body.columnconfigure(\n            1,\n            weight=1,\n        )\n\n        button_row = ttk.Frame(body)\n        button_row.grid(\n            row=3,\n            column=0,\n            columnspan=2,\n            sticky="e",\n            pady=(18, 0),\n        )\n\n        def save_test() -> None:\n            name = name_var.get().strip()\n            start_id = display_to_id.get(\n                start_var.get()\n            )\n            end_id = display_to_id.get(\n                end_var.get()\n            )\n\n            if not name:\n                messagebox.showerror(\n                    "이름 필요",\n                    "테스트 이름을 입력하세요.",\n                    parent=dialog,\n                )\n                return\n\n            ids = [\n                step.get("id")\n                for step in steps\n            ]\n\n            try:\n                start_index = ids.index(start_id)\n                end_index = ids.index(end_id)\n            except ValueError:\n                messagebox.showerror(\n                    "단계 오류",\n                    "시작/종료 단계를 다시 선택하세요.",\n                    parent=dialog,\n                )\n                return\n\n            if start_index > end_index:\n                messagebox.showerror(\n                    "구간 오류",\n                    "시작 단계는 종료 단계보다 앞이어야 합니다.",\n                    parent=dialog,\n                )\n                return\n\n            self.test_ranges().append(\n                {\n                    "id": f"test_{time.time_ns()}",\n                    "name": name,\n                    "start_id": start_id,\n                    "end_id": end_id,\n                }\n            )\n\n            self.app.persist()\n            self.app.refresh_test_ranges()\n            self.refresh()\n            dialog.destroy()\n\n        ttk.Button(\n            button_row,\n            text="취소",\n            command=dialog.destroy,\n        ).pack(\n            side="right",\n            padx=(6, 0),\n        )\n\n        ttk.Button(\n            button_row,\n            text="추가",\n            command=save_test,\n        ).pack(\n            side="right",\n        )\n\n        dialog.bind(\n            "<Return>",\n            lambda _event: save_test(),\n        )\n        dialog.bind(\n            "<Escape>",\n            lambda _event: dialog.destroy(),\n        )\n\n    def delete_test(self) -> None:\n        selected = self.listbox.curselection()\n\n        if not selected:\n            return\n\n        index = selected[0]\n        items = self.test_ranges()\n\n        if index >= len(items):\n            return\n\n        name = items[index].get(\n            "name",\n            "선택 테스트",\n        )\n\n        if not messagebox.askyesno(\n            "테스트 삭제",\n            f"\'{name}\' 테스트를 삭제할까요?",\n            parent=self,\n        ):\n            return\n\n        del items[index]\n\n        self.app.persist()\n        self.app.refresh_test_ranges()\n        self.refresh()\n'
MACRO_METHODS = '\n    def test_ranges(self) -> list[dict]:\n        return self.config.setdefault(\n            "test_ranges",\n            [],\n        )\n\n    def refresh_test_ranges(self) -> None:\n        names = [\n            item.get("name", item.get("id", "테스트"))\n            for item in self.test_ranges()\n        ]\n\n        if hasattr(self, "test_range_combo"):\n            self.test_range_combo.configure(\n                values=names,\n            )\n\n        current = self.test_range_var.get()\n\n        if current not in names:\n            self.test_range_var.set(\n                names[0] if names else ""\n            )\n\n    def selected_test_range(self) -> dict | None:\n        name = self.test_range_var.get()\n\n        return next(\n            (\n                item\n                for item in self.test_ranges()\n                if item.get("name") == name\n            ),\n            None,\n        )\n\n    def open_test_range_manager(self) -> None:\n        TestRangeManager(self)\n\n    def start_range_test(self) -> None:\n        if self.test_runner.running or self._test_mode:\n            messagebox.showinfo(\n                "테스트 실행 중",\n                "이미 구간 테스트가 실행 중입니다.",\n                parent=self.root,\n            )\n            return\n\n        test_range = self.selected_test_range()\n\n        if not test_range:\n            messagebox.showinfo(\n                "테스트 없음",\n                "먼저 구간 테스트를 추가하거나 선택하세요.",\n                parent=self.root,\n            )\n            return\n\n        self._test_resume_normal = bool(\n            self.engine.thread\n            and self.engine.thread.is_alive()\n            and not self.engine.stop_event.is_set()\n        )\n\n        self._test_mode = True\n        self._pending_test_range = dict(test_range)\n\n        self.engine.stop()\n\n        self.global_status.set(\n            f"기존 감시 중지 중 → 테스트 준비: "\n            f"{test_range.get(\'name\', \'구간 테스트\')}"\n        )\n\n        self._wait_normal_engine_for_test()\n\n    def _wait_normal_engine_for_test(self) -> None:\n        thread = self.engine.thread\n\n        if thread and thread.is_alive():\n            self.root.after(\n                100,\n                self._wait_normal_engine_for_test,\n            )\n            return\n\n        test_range = self._pending_test_range\n\n        if not self._test_mode or not test_range:\n            return\n\n        try:\n            self.test_runner.start(\n                test_range\n            )\n        except Exception as exc:\n            self._test_mode = False\n            self._pending_test_range = None\n\n            messagebox.showerror(\n                "테스트 시작 실패",\n                str(exc),\n                parent=self.root,\n            )\n\n            self._resume_normal_after_test()\n            return\n\n        self.global_status.set(\n            f"구간 테스트 실행 중: "\n            f"{test_range.get(\'name\', \'테스트\')} "\n            f"(모든 모니터 / 모든 분면)"\n        )\n\n    def stop_range_test(self) -> None:\n        if not self._test_mode:\n            return\n\n        self.global_status.set(\n            "구간 테스트 중지 중"\n        )\n\n        self.test_runner.stop()\n        self._wait_test_threads_then_resume()\n\n    def _wait_test_threads_then_resume(self) -> None:\n        alive = any(\n            thread.is_alive()\n            for thread in self.test_runner.threads\n        )\n\n        if alive:\n            self.root.after(\n                100,\n                self._wait_test_threads_then_resume,\n            )\n            return\n\n        self.test_runner.running = False\n        self._finish_test_mode(\n            "구간 테스트 중지"\n        )\n\n    def on_range_test_completed(self) -> None:\n        if not self._test_mode:\n            return\n\n        self._finish_test_mode(\n            "구간 테스트 완료"\n        )\n\n    def _finish_test_mode(\n        self,\n        reason: str,\n    ) -> None:\n        self._test_mode = False\n        self._pending_test_range = None\n\n        should_resume = self._test_resume_normal\n        self._test_resume_normal = False\n\n        if should_resume:\n            self.engine.start()\n            self.global_status.set(\n                f"{reason} → 기존 감시 재개"\n            )\n        else:\n            self.global_status.set(\n                f"{reason} → 기존 감시는 중지 상태 유지"\n            )\n\n    def _resume_normal_after_test(self) -> None:\n        should_resume = self._test_resume_normal\n        self._test_resume_normal = False\n\n        if should_resume:\n            self.engine.start()\n            self.global_status.set(\n                "테스트 시작 실패 → 기존 감시 재개"\n            )\n'


# ------------------------------------------------------------
# 1. RangeTestRunner / TestRangeManager 삽입
# ------------------------------------------------------------
if "class RangeTestRunner:" not in text:
    marker = "\nclass MacroManager:"
    pos = text.find(marker)

    if pos == -1:
        raise RuntimeError(
            "MacroManager 클래스 위치를 찾지 못했습니다."
        )

    text = (
        text[:pos]
        + "\n"
        + CLASSES_CODE
        + "\n"
        + text[pos:]
    )


# ------------------------------------------------------------
# 2. MacroManager.__init__ 테스트 상태 추가
# ------------------------------------------------------------
if "self.test_runner = RangeTestRunner(self)" not in text:
    anchor = "        self.engine = MacroEngine(self)\n"

    if anchor not in text:
        raise RuntimeError(
            "MacroManager.__init__의 engine 생성 위치를 찾지 못했습니다."
        )

    addition = (
        anchor
        + "        self.test_runner = RangeTestRunner(self)\n"
        + "        self.test_range_var = tk.StringVar(value=\"\")\n"
        + "        self.test_range_combo: ttk.Combobox | None = None\n"
        + "        self._test_mode = False\n"
        + "        self._test_resume_normal = False\n"
        + "        self._pending_test_range: dict | None = None\n"
    )

    text = text.replace(
        anchor,
        addition,
        1,
    )


# ------------------------------------------------------------
# 3. build_ui에 공유 테스트 바 추가
# ------------------------------------------------------------
if 'text="구간 테스트"' not in text:
    anchor = (
        '        ttk.Label(top, text="F5 테스트 클릭 / Ctrl+Shift+C 좌표 복사").pack(side="right")\n'
        '        ttk.Label(self.root, textvariable=self.global_status, relief="groove", padding=8).pack(fill="x", padx=10)\n'
    )

    if anchor not in text:
        raise RuntimeError(
            "build_ui 상단 상태 UI 위치를 찾지 못했습니다."
        )

    replacement = (
        '        ttk.Label(top, text="F5 테스트 클릭 / Ctrl+Shift+C 좌표 복사").pack(side="right")\n'
        '\n'
        '        test_bar = ttk.LabelFrame(\n'
        '            self.root,\n'
        '            text="구간 테스트",\n'
        '            padding=(10, 7),\n'
        '        )\n'
        '        test_bar.pack(fill="x", padx=10, pady=(0, 6))\n'
        '\n'
        '        ttk.Label(\n'
        '            test_bar,\n'
        '            text="공유 테스트",\n'
        '        ).pack(side="left")\n'
        '\n'
        '        self.test_range_combo = ttk.Combobox(\n'
        '            test_bar,\n'
        '            textvariable=self.test_range_var,\n'
        '            state="readonly",\n'
        '            width=30,\n'
        '        )\n'
        '        self.test_range_combo.pack(side="left", padx=6)\n'
        '\n'
        '        ttk.Button(\n'
        '            test_bar,\n'
        '            text="테스트 관리",\n'
        '            command=self.open_test_range_manager,\n'
        '        ).pack(side="left", padx=3)\n'
        '\n'
        '        ttk.Button(\n'
        '            test_bar,\n'
        '            text="테스트 실행",\n'
        '            style="Primary.TButton",\n'
        '            command=self.start_range_test,\n'
        '        ).pack(side="left", padx=3)\n'
        '\n'
        '        ttk.Button(\n'
        '            test_bar,\n'
        '            text="테스트 중지",\n'
        '            command=self.stop_range_test,\n'
        '        ).pack(side="left", padx=3)\n'
        '\n'
        '        ttk.Label(\n'
        '            test_bar,\n'
        '            text="실행 시 기존 감시 일시중지 · 모든 모니터/모든 분면 테스트",\n'
        '        ).pack(side="left", padx=(12, 0))\n'
        '\n'
        '        self.refresh_test_ranges()\n'
        '\n'
        '        ttk.Label(self.root, textvariable=self.global_status, relief="groove", padding=8).pack(fill="x", padx=10)\n'
    )

    text = text.replace(
        anchor,
        replacement,
        1,
    )


# ------------------------------------------------------------
# 4. MacroManager 메서드 추가
# ------------------------------------------------------------
if "def start_range_test(self) -> None:" not in text:
    marker = "\n    def routine_names(self) -> list[str]:"
    pos = text.find(
        marker,
        text.find("class MacroManager:"),
    )

    if pos == -1:
        raise RuntimeError(
            "MacroManager.routine_names 위치를 찾지 못했습니다."
        )

    text = (
        text[:pos]
        + "\n"
        + MACRO_METHODS
        + text[pos:]
    )


# ------------------------------------------------------------
# 5. close 시 테스트도 중지
# ------------------------------------------------------------
close_anchor = (
    "    def close(self) -> None:\n"
    "        self.engine.stop()\n"
)

if close_anchor in text and "        self.test_runner.stop()\n" not in text[
    text.find(close_anchor):
    text.find(close_anchor) + 180
]:
    text = text.replace(
        close_anchor,
        (
            "    def close(self) -> None:\n"
            "        self.test_runner.stop()\n"
            "        self.engine.stop()\n"
        ),
        1,
    )


# ------------------------------------------------------------
# 6. 문법 및 기능 토큰 검증
# ------------------------------------------------------------
required = [
    "class RangeTestRunner:",
    "class TestRangeManager(",
    "self.test_runner = RangeTestRunner(self)",
    'text="구간 테스트"',
    "def start_range_test(self) -> None:",
    "def stop_range_test(self) -> None:",
    '"test_ranges"',
]

missing = [
    token
    for token in required
    if token not in text
]

if missing:
    raise RuntimeError(
        "반영 실패: "
        + ", ".join(missing)
    )

compile(
    text,
    str(TARGET),
    "exec",
)

backup = TARGET.with_name(
    TARGET.name
    + ".bak_before_range_test"
)

if not backup.exists():
    backup.write_text(
        original,
        encoding="utf-8",
    )

TARGET.write_text(
    text,
    encoding="utf-8",
)

print("=" * 72)
print("구간 테스트 기능 추가 완료")
print("=" * 72)
print("공유 테스트 추가/삭제: 테스트 관리")
print("테스트 실행: 기존 감시 정지 후 모든 모니터/모든 분면 실행")
print("테스트 중지: 테스트 중단 후 기존 감시 재개")
print("테스트 자연 완료: 기존 감시 자동 재개")
print("설정 저장: macro_manager_config.json -> test_ranges")
print("=" * 72)
print("백업:", backup)
