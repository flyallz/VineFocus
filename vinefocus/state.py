"""本地设置与专注记录。

负责 JSON 设置、结构化记录和每日 Markdown 的持久化，不依赖任何界面组件。
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

class AppState:
    def __init__(self):
        self.app_dir = Path.home() / ".vine_pomodoro"
        self.app_dir.mkdir(exist_ok=True)
        self.file_path = self.app_dir / "settings.json"

        self.data = {
            "preset": "25+5",
            "focus_minutes": 25,
            "rest_minutes": 5,
            "rounds": 1,
            "density": "标准",
            "plant_density": 50,
            "ui_theme": "夜色流光",
            "vine_theme": "月白花藤",
            "growth_layout": "静谧单株",
            "display_target": "follow",
            "plant_presence": 36,
            "plant_opacity": 40,
            "reduce_motion": False,
            "glass_effect": True,
            "start_minimized": False,
            "mini_when_hidden": True,
            "always_on_top": False,
            "cumulative_growth": True,
            "notifications": True,
            "completion_sound": True,
            "skip_final_rest": False,
            "start_with_system": False,
            "close_behavior": "收起到托盘 / 菜单栏",
            "records_dir": str(self.app_dir / "records"),
            "last_scene_mode": "科研论文",
            "last_task_type": "论文写作",
            "last_custom_task": "",
            "last_goal": "",
            "today_date": str(date.today()),
            "today_completed": 0,
            "growth_chapter": 1,
            "growth_completed_units": 0,
            "growth_effective_units": 0,
        }
        self.load()
        self.ensure_records_dir()
        self.ensure_today()

    def load(self):
        if self.file_path.exists():
            try:
                loaded = json.loads(self.file_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                    if "plant_density" not in loaded:
                        self.data["plant_density"] = {
                            "清爽": 20, "标准": 50, "茂盛": 85
                        }.get(str(loaded.get("density", "标准")), 50)
            except Exception:
                pass

    @staticmethod
    def _atomic_write_json(path: Path, payload) -> None:
        """先写临时文件再替换，避免异常退出留下半份 JSON。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def save(self) -> bool:
        try:
            self._atomic_write_json(self.file_path, self.data)
            return True
        except Exception:
            return False

    def get(self, key, default=None):
        return self.data.get(key, default)

    def ensure_records_dir(self):
        records_dir = Path(self.data.get("records_dir") or (self.app_dir / "records"))
        records_dir.mkdir(parents=True, exist_ok=True)
        self.data["records_dir"] = str(records_dir)
        self.save()

    def get_records_dir(self) -> Path:
        self.ensure_records_dir()
        return Path(self.data["records_dir"])

    def set_records_dir(self, folder: str):
        """验证目标可写后再切换，失败时保留原目录并向调用方抛出异常。"""
        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".vinefocus-write-test.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        self.data["records_dir"] = str(path)
        self.save()

    def ensure_today(self):
        if self.data.get("today_date") != str(date.today()):
            self.data["today_date"] = str(date.today())
            self.data["today_completed"] = 0
            self.save()

    def add_completed_focus(self):
        self.ensure_today()
        self.data["today_completed"] = int(self.data.get("today_completed", 0)) + 1
        self.save()

    def records_json_path(self) -> Path:
        return self.get_records_dir() / "records.json"

    def daily_markdown_path(self, day: date | None = None) -> Path:
        d = day or date.today()
        return self.get_records_dir() / f"{d}_花藤专注.md"

    def load_all_records(self):
        path = self.records_json_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def save_all_records(self, records: list):
        path = self.records_json_path()
        if path.exists():
            for index in range(3, 0, -1):
                source = path.with_suffix(path.suffix + (f".bak{index - 1}" if index > 1 else ""))
                target = path.with_suffix(path.suffix + f".bak{index}")
                if source.exists():
                    try:
                        shutil.copy2(source, target)
                    except OSError:
                        pass
        self._atomic_write_json(path, records)

    def add_focus_record(self, record: dict):
        records = self.load_all_records()
        records.append(record)
        records = records[-3000:]
        self.save_all_records(records)
        self.append_markdown_record(record)

    def growth_state(self) -> tuple[int, int, int]:
        """返回当前植株的完成轮次、有进展轮次和植株编号。"""
        # 设置文件可以来自旧版本，也可能被用户手动编辑；在读取边界处收紧
        # 不变量，确保看板与覆盖层都不会出现“推进次数大于完成轮次”的假状态。
        completed = max(0, min(24, int(self.data.get("growth_completed_units", 0))))
        effective_units = max(0, min(completed, int(self.data.get("growth_effective_units", 0))))
        chapter = max(1, int(self.data.get("growth_chapter", 1)))
        return (
            completed,
            effective_units,
            chapter,
        )

    def commit_growth(self, effective: bool, chapter_size: int = 24) -> tuple[int, int, int]:
        """提交一次正常完成的专注；满章后由下一次提交开启新章节。"""
        completed, effective_units, chapter = self.growth_state()
        if completed >= chapter_size:
            completed, effective_units, chapter = 0, 0, chapter + 1
        completed += 1
        if effective:
            effective_units += 1
        self.data["growth_completed_units"] = completed
        self.data["growth_effective_units"] = effective_units
        self.data["growth_chapter"] = chapter
        self.save()
        return completed, effective_units, chapter

    @staticmethod
    def growth_stage_name(completed: int, progress_units: int, chapter_size: int = 24) -> str:
        """把内部计数转换成用户可理解的自然生长阶段。"""
        completed = max(0, int(completed))
        progress_units = max(0, int(progress_units))
        ratio = min(1.0, completed / max(1, chapter_size))
        if completed == 0 or ratio < 0.12:
            return "萌芽"
        if ratio < 0.34:
            return "长叶"
        if progress_units == 0:
            return "孕蕾"
        if progress_units <= 2:
            return "初花"
        if progress_units <= 5 or ratio < 0.72:
            return "渐盛"
        return "盛花"

    def session_snapshot_path(self) -> Path:
        return self.app_dir / "active_session.json"

    def save_session_snapshot(self, snapshot: dict) -> bool:
        try:
            self._atomic_write_json(self.session_snapshot_path(), snapshot)
            return True
        except Exception:
            return False

    def load_session_snapshot(self) -> dict | None:
        path = self.session_snapshot_path()
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def clear_session_snapshot(self):
        try:
            self.session_snapshot_path().unlink(missing_ok=True)
        except OSError:
            pass

    def today_records(self):
        today = str(date.today())
        return [r for r in self.load_all_records() if r.get("date") == today]

    def records_by_day(self, target_day: date):
        day = str(target_day)
        return [r for r in self.load_all_records() if r.get("date") == day]

    def today_completed(self):
        records = self.today_records()
        if records:
            return len(records)
        self.ensure_today()
        return int(self.data.get("today_completed", 0))

    def append_markdown_record(self, record: dict):
        path = self.daily_markdown_path()
        if not path.exists():
            header = f"# 花藤专注日报｜{date.today()}\n\n> 每轮专注都会生长；目标有推进时，植物会更接近盛花。\n\n---\n\n"
            path.write_text(header, encoding="utf-8")

        effective = "✅ 目标有推进" if record.get("effective") else "🌿 完成一轮专注"
        output = record.get("output") or "无"
        notes = record.get("notes") or "无"
        next_step = record.get("next_step") or "无"
        goal = record.get("goal") or "未填写"
        metric_name = record.get("metric_name") or "成果数据"
        metric_value = int(record.get("metric_value", 0))
        metric_unit = record.get("metric_unit") or ""
        metric_line = f"- **{metric_name}**：{metric_value}{metric_unit}" if metric_value > 0 else ""

        block = f"""
## {record.get("time", "")}｜{record.get("scene_mode", "普通专注")}｜{record.get("task_type", "任务")}｜{effective}

- **本轮目标**：{goal}
- **专注时长**：{record.get("focus_minutes", 0)} 分钟
- **生长模式**：{record.get("growth_mode", "")}
{metric_line}

### 本轮产出

{output}

### 关键记录 / 问题 / 笔记

{notes}

### 下一步

{next_step}

---

"""
        with path.open("a", encoding="utf-8") as f:
            f.write(block)
