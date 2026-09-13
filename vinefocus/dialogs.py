"""业务弹窗。

提供专注产出登记和成长看板，只通过 AppState 访问数据。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .botanical_assets import BotanicalPreview
from .config import GROWTH_LAYOUTS, SCENE_CONFIG, VINE_THEMES, normalize_theme_name
from .state import AppState
from .widgets import GrowthRing, TrendChart, make_card


class FirstRunDialog(QDialog):
    """首次启动向导：一次完成节奏、植物和构图选择。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用花藤专注")
        self.setModal(True)
        self.resize(620, 560)
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(14)

        title = QLabel("让时间在桌面上生长")
        title.setObjectName("dashboardTitle")
        subtitle = QLabel("先选一株喜欢的植物。每轮专注都会生长，目标有推进时会逐渐开花。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        hero = QFrame()
        hero.setObjectName("dashboardHero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        self.preview = BotanicalPreview("月白花藤")
        self.preview.setMinimumSize(210, 250)
        self.preview.set_visual("月白花藤", 0.86, 1)
        fields = QVBoxLayout()
        fields.setSpacing(10)
        fields.addWidget(QLabel("① 选择专注节奏"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["25+5", "45+10", "60+10"])
        fields.addWidget(self.preset_combo)
        fields.addWidget(QLabel("② 选择第一株花藤"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(VINE_THEMES)
        self.theme_combo.currentTextChanged.connect(lambda name: self.preview.set_visual(name, 0.86, 1))
        fields.addWidget(self.theme_combo)
        fields.addWidget(QLabel("③ 选择桌面构图"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(GROWTH_LAYOUTS)
        fields.addWidget(self.layout_combo)
        fields.addStretch()
        hero_layout.addWidget(self.preview, stretch=1)
        hero_layout.addLayout(fields, stretch=1)
        root.addWidget(hero, stretch=1)

        note = QLabel("默认存在感 36% · 透明度 40% · 支持 Windows 托盘与 macOS 菜单栏")
        note.setObjectName("status")
        note.setWordWrap(True)
        root.addWidget(note)
        buttons = QHBoxLayout()
        later = QPushButton("稍后设置")
        later.clicked.connect(self.reject)
        start = QPushButton("开始第一轮")
        start.setObjectName("primaryButton")
        start.clicked.connect(self.accept)
        buttons.addWidget(later)
        buttons.addStretch()
        buttons.addWidget(start)
        root.addLayout(buttons)

    def choices(self) -> tuple[str, str, str]:
        return self.preset_combo.currentText(), self.theme_combo.currentText(), self.layout_combo.currentText()

class OutputDialog(QDialog):
    def __init__(self, scene_mode: str, task_type: str, goal: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("记录本轮专注产出")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.scene_mode = scene_mode
        self.task_type = task_type
        self.goal = goal
        self.config = SCENE_CONFIG.get(scene_mode, SCENE_CONFIG["自定义"])
        self.result_data = None
        self.build_ui()
        self.resize(510, 550)

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("🌸 这一轮完成了什么？")
        title.setObjectName("title")
        info = QLabel(f"场景模式：{self.scene_mode}\n任务类型：{self.task_type}\n本轮目标：{self.goal or '未填写'}")
        info.setObjectName("info")
        info.setWordWrap(True)

        self.output_edit = QTextEdit()
        self.output_edit.setPlaceholderText(self.config["output_placeholder"])
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText(self.config["detail_placeholder"])
        self.next_edit = QLineEdit()
        self.next_edit.setPlaceholderText("例如：下一轮先处理最卡住的部分")

        self.metric_toggle = QPushButton("＋ 添加成果数据（可选）")
        self.metric_toggle.setObjectName("quietButton")
        self.metric_toggle.setCheckable(True)
        self.metric_toggle.setChecked(False)
        self.metric_panel = QWidget()
        metric_row = QHBoxLayout(self.metric_panel)
        metric_row.setContentsMargins(0, 0, 0, 0)
        self.metric_spin = QSpinBox()
        self.metric_spin.setRange(0, 100000)
        self.metric_spin.setValue(0)
        metric_row.addWidget(QLabel(self.config["metric_name"]))
        metric_row.addWidget(self.metric_spin)
        metric_row.addWidget(QLabel(self.config["metric_unit"]))
        metric_row.addStretch()
        self.metric_panel.setVisible(False)
        self.metric_toggle.toggled.connect(self.metric_panel.setVisible)

        # 开花是用户对本轮的主观确认，而不是填写表单时的默认奖励；因此这里
        # 不预选任何结果，避免一次误点就让植物被错误地推进到开花阶段。
        self.outcome_group = QButtonGroup(self)
        self.outcome_group.setExclusive(True)
        self.progress_choice = QPushButton("本轮目标有推进")
        self.progress_choice.setObjectName("outcomeChoice")
        self.progress_choice.setCheckable(True)
        self.focus_choice = QPushButton("只是保持了专注")
        self.focus_choice.setObjectName("outcomeChoice")
        self.focus_choice.setCheckable(True)
        self.outcome_group.addButton(self.progress_choice)
        self.outcome_group.addButton(self.focus_choice)
        self.outcome_group.buttonClicked.connect(self._update_outcome_choice)
        outcome_row = QHBoxLayout()
        outcome_row.setSpacing(8)
        outcome_row.addWidget(self.progress_choice)
        outcome_row.addWidget(self.focus_choice)
        progress_hint = QLabel("请选择最符合这轮的结果：两种都会保存记录并让枝叶生长；只有“有推进”会促进开花。")
        progress_hint.setObjectName("muted")
        progress_hint.setWordWrap(True)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("保存本轮记录并进入休息")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_output)
        btn_row.addStretch()
        btn_row.addWidget(self.save_btn)

        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(QLabel(self.config["output_label"]))
        layout.addWidget(self.output_edit)
        layout.addWidget(QLabel(self.config["detail_label"]))
        layout.addWidget(self.notes_edit)
        layout.addWidget(QLabel("下一步"))
        layout.addWidget(self.next_edit)
        layout.addWidget(self.metric_toggle)
        layout.addWidget(self.metric_panel)
        layout.addWidget(QLabel("这一轮的结果"))
        layout.addLayout(outcome_row)
        layout.addWidget(progress_hint)
        layout.addLayout(btn_row)

        self.setStyleSheet("""
            QDialog { background: #fbfcf4; }
            QLabel#title { color: #254d27; font-size: 18px; font-weight: 700; }
            QLabel#info {
                color: #526a4f; font-size: 13px; background: rgba(232, 243, 225, 180);
                border-radius: 10px; padding: 9px;
            }
            QLabel { color: #40583d; font-size: 13px; font-weight: 600; }
            QTextEdit, QLineEdit, QSpinBox {
                background: white; color: #243d24;
                border: 1px solid rgba(89, 132, 72, 110);
                border-radius: 8px; padding: 7px; font-size: 13px;
            }
            QTextEdit { min-height: 86px; }
            QPushButton {
                background: rgba(75, 128, 61, 225); color: white; border: none;
                border-radius: 9px; padding: 8px 12px; font-size: 13px;
            }
            QPushButton:hover { background: rgba(58, 108, 49, 245); }
            QPushButton#outcomeChoice {
                background: rgba(235, 243, 229, 235); color: #40583d;
                border: 1px solid rgba(89, 132, 72, 105);
            }
            QPushButton#outcomeChoice:checked {
                background: rgba(75, 128, 61, 230); color: white;
                border: 1px solid rgba(48, 104, 53, 210);
            }
            QPushButton:disabled { background: rgba(127, 145, 122, 125); color: rgba(255, 255, 255, 170); }
        """)

    def _update_outcome_choice(self, _button):
        """用户明确选择后才允许提交，防止无意间推进开花阶段。"""
        self.save_btn.setEnabled(self.outcome_group.checkedButton() is not None)

    def save_output(self):
        output_text = self.output_edit.toPlainText().strip()
        notes_text = self.notes_edit.toPlainText().strip()
        next_text = self.next_edit.text().strip()
        has_content = bool(output_text or notes_text or next_text or self.metric_spin.value())
        selected = self.outcome_group.checkedButton()
        if selected is None:
            QMessageBox.information(self, "请选择本轮结果", "请先选择“本轮目标有推进”或“只是保持了专注”。")
            return
        effective = selected is self.progress_choice
        if effective and not has_content:
            answer = QMessageBox.question(
                self,
                "仍标记为目标有推进？",
                "你还没有填写本轮成果、补充记录或下一步。仍要标记为目标有推进吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.result_data = {
            "effective": effective,
            "output": output_text,
            "notes": notes_text,
            "next_step": next_text,
            "metric_name": self.config["metric_name"],
            "metric_unit": self.config["metric_unit"],
            "metric_value": self.metric_spin.value(),
        }
        self.accept()

    def get_result_data(self):
        return self.result_data


# =========================
# 成长看板 / 数据大屏
# =========================

class DashboardDialog(QDialog):
    RANGE_OPTIONS = ["今日", "近 7 天", "近 30 天", "全部记录"]

    def __init__(self, state: AppState, current_progress: float = 0.0, parent=None):
        super().__init__(parent)
        self.state = state
        self.current_progress = max(0.0, min(1.0, current_progress))
        self.current_range = "今日"
        self.theme_name = normalize_theme_name(self.state.get("vine_theme", "月白花藤"))
        self.report_text = ""

        self.setWindowTitle("成长看板")
        self.resize(1180, 760)
        self.build_ui()
        self.rebuild_dashboard()

    def parse_date(self, value):
        try:
            return date.fromisoformat(str(value))
        except Exception:
            return None

    def effective_records(self, records):
        return [r for r in records if r.get("effective")]

    def records_for_range(self, range_name: str):
        all_records = self.state.load_all_records()
        today = date.today()

        if range_name == "今日":
            return [r for r in all_records if r.get("date") == str(today)]

        if range_name == "近 7 天":
            start_day = today - timedelta(days=6)
            return [r for r in all_records if (parsed := self.parse_date(r.get("date"))) and parsed >= start_day]

        if range_name == "近 30 天":
            start_day = today - timedelta(days=29)
            return [r for r in all_records if (parsed := self.parse_date(r.get("date"))) and parsed >= start_day]

        return all_records

    def count_by(self, records, field: str):
        data = {}
        for r in records:
            key = r.get(field) or "未分类"
            data[key] = data.get(key, 0) + 1
        return data

    def metric_summary(self, records):
        data = {}
        for r in records:
            value = int(r.get("metric_value", 0))
            if value <= 0:
                continue
            name = r.get("metric_name") or "成果数据"
            unit = r.get("metric_unit") or ""
            key = (name, unit)
            data[key] = data.get(key, 0) + value
        return data

    def trend_counts(self, days: int):
        result = []
        today = date.today()
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            records = self.state.records_by_day(d)
            result.append((d, len(records)))
        return result

    def current_trend_days(self):
        if self.current_range == "近 30 天" or self.current_range == "全部记录":
            return 30
        return 7

    def continuous_streak(self):
        all_records = self.state.load_all_records()
        day_has_focus = set()
        for r in all_records:
            d = self.parse_date(r.get("date"))
            if d:
                day_has_focus.add(d)

        streak = 0
        today = date.today()
        for i in range(0, 366):
            d = today - timedelta(days=i)
            if d in day_has_focus:
                streak += 1
            else:
                break
        return streak

    def range_title(self):
        return f"{self.current_range}成长看板"

    def current_plant_state(self):
        completed, progress_units, chapter = self.state.growth_state()
        progress = max(self.current_progress, min(1.0, completed / 24.0))
        stage = self.state.growth_stage_name(completed, progress_units)
        return completed, progress_units, chapter, progress, stage

    def build_report_text(self):
        records = self.records_for_range(self.current_range)
        effective = self.effective_records(records)
        total_minutes = sum(int(r.get("focus_minutes", 0)) for r in records)
        # 成果数据只是可选的工作量记录，并不决定花开；无论用户是否选择
        # “目标有推进”，已填写的成果都应在回顾里被如实汇总。
        metrics = self.metric_summary(records)
        scenes = self.count_by(records, "scene_mode")
        tasks = self.count_by(records, "task_type")

        lines = []
        lines.append(f"{self.range_title()}｜{date.today()}")
        lines.append("")
        lines.append(f"统计范围：{self.current_range}")
        lines.append(f"完成专注：{len(records)} 次")
        lines.append(f"目标有推进：{len(effective)} 次")
        lines.append(f"总专注时长：{total_minutes} 分钟")
        completed, progress_units, chapter, plant_progress, stage = self.current_plant_state()
        lines.append(f"当前植物：第 {chapter} 株 · 成长 {completed}/24 · {stage}")
        lines.append(f"当前花藤进度：{int(plant_progress * 100)}%")
        lines.append(f"连续专注：{self.continuous_streak()} 天")
        lines.append(f"记录目录：{self.state.get_records_dir()}")
        lines.append("")

        if metrics:
            lines.append("产出指标：")
            for (name, unit), value in metrics.items():
                lines.append(f"- {name}：{value}{unit}")
            lines.append("")

        if scenes:
            lines.append("场景分布：")
            for k, v in scenes.items():
                lines.append(f"- {k}：{v} 次")
            lines.append("")

        if tasks:
            lines.append("任务分布：")
            for k, v in tasks.items():
                lines.append(f"- {k}：{v} 次")
            lines.append("")

        trend_days = self.current_trend_days()
        lines.append(f"最近 {trend_days} 天趋势：")
        for d, count in self.trend_counts(trend_days):
            lines.append(f"- {d.strftime('%m-%d')}：{count} 次")
        lines.append("")

        if records:
            lines.append("产出卡片：")
            for index, r in enumerate(records[-100:], start=1):
                mark = "✅ 目标有推进" if r.get("effective") else "🌿 完成专注"
                lines.append(f"{index}. {mark} {r.get('date', '')} {r.get('time', '')}｜{r.get('scene_mode', '')}｜{r.get('task_type', '')}")
                lines.append(f"   目标：{r.get('goal') or '未填写'}")
                if r.get("output"):
                    lines.append(f"   产出：{r.get('output')}")
                if r.get("next_step"):
                    lines.append(f"   下一步：{r.get('next_step')}")
        else:
            lines.append("这个范围内还没有专注记录。")

        return "\n".join(lines)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout(child_layout)

    def add_distribution_bars(self, parent_layout: QVBoxLayout, title: str, data: dict):
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        parent_layout.addWidget(title_label)

        if not data:
            empty = QLabel("暂无数据")
            empty.setObjectName("muted")
            parent_layout.addWidget(empty)
            return

        max_value = max(data.values()) or 1
        for name, value in sorted(data.items(), key=lambda x: x[1], reverse=True)[:12]:
            row = QHBoxLayout()
            name_label = QLabel(str(name))
            name_label.setMinimumWidth(100)
            name_label.setObjectName("barName")
            bar = QProgressBar()
            bar.setRange(0, max_value)
            bar.setValue(value)
            bar.setTextVisible(False)
            value_label = QLabel(f"{value} 次")
            value_label.setObjectName("barValue")
            value_label.setMinimumWidth(45)
            row.addWidget(name_label)
            row.addWidget(bar, stretch=1)
            row.addWidget(value_label)
            parent_layout.addLayout(row)

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        self.title_label = QLabel("🌿 成长看板")
        self.title_label.setObjectName("dashboardTitle")
        subtitle = QLabel("普通用户看可视化；Markdown / JSON 仍在后台长期保存。")
        subtitle.setObjectName("subtitle")
        title_col.addWidget(self.title_label)
        title_col.addWidget(subtitle)

        self.range_combo = QComboBox()
        self.range_combo.addItems(self.RANGE_OPTIONS)
        self.range_combo.currentTextChanged.connect(self.change_range)

        title_row.addLayout(title_col)
        title_row.addStretch()
        title_row.addWidget(QLabel("统计范围"))
        title_row.addWidget(self.range_combo)
        root.addLayout(title_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(self.scroll, stretch=1)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("复制看板文字")
        copy_btn.clicked.connect(self.copy_report)
        open_dir_btn = QPushButton("打开记录目录")
        open_dir_btn.clicked.connect(self.open_records_dir)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(open_dir_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self.setStyleSheet("""
            QDialog { background: #fbfcf4; }
            QLabel#dashboardTitle { color: #254d27; font-size: 26px; font-weight: 900; }
            QLabel#subtitle { color: #708266; font-size: 12px; }
            QLabel#sectionTitle { color: #254d27; font-size: 16px; font-weight: 900; margin-top: 8px; }
            QLabel#muted { color: #8a967f; font-size: 12px; }
            QLabel#barName { color: #40583d; font-size: 12px; }
            QLabel#barValue { color: #6b7d63; font-size: 12px; }
            QFrame#statCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(255,255,250,248),
                    stop:1 rgba(244,250,237,242));
                border: 1px solid rgba(139, 174, 115, 95);
                border-radius: 18px;
            }
            QLabel#cardTitle { color: #66785d; font-size: 12px; font-weight: 800; }
            QLabel#cardValue { color: #285a2c; font-size: 19px; font-weight: 900; }
            QLabel#cardSub { color: #73806d; font-size: 11px; }
            QProgressBar {
                border: 1px solid rgba(139, 174, 115, 90);
                border-radius: 7px;
                background: rgba(234, 243, 226, 170);
                height: 13px;
                color: #285a2c;
                font-size: 10px;
            }
            QProgressBar::chunk { background: rgba(99, 151, 78, 218); border-radius: 7px; }
            QScrollArea { border: none; background: transparent; }
            QPushButton {
                background: rgba(88, 140, 72, 225); color: white; border: none;
                border-radius: 11px; padding: 9px 13px; font-size: 13px; font-weight: 700;
            }
            QPushButton:hover { background: rgba(66, 118, 58, 245); }
            QComboBox {
                background: white; color: #285a2c;
                border: 1px solid rgba(139, 174, 115, 110);
                border-radius: 9px; padding: 6px; min-width: 100px;
            }
        """)

    def rebuild_dashboard(self):
        self.report_text = self.build_report_text()
        self.title_label.setText(f"🌿 {self.range_title()}")

        records = self.records_for_range(self.current_range)
        effective = self.effective_records(records)
        total_minutes = sum(int(r.get("focus_minutes", 0)) for r in records)
        metrics = self.metric_summary(records)
        scenes = self.count_by(records, "scene_mode")
        tasks = self.count_by(records, "task_type")
        trend_days = self.current_trend_days()
        trend = self.trend_counts(trend_days)
        streak = self.continuous_streak()
        completed, progress_units, chapter, plant_progress, stage = self.current_plant_state()

        self.theme_name = normalize_theme_name(self.state.get("vine_theme", self.theme_name))
        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet("background: transparent;")
        root = QVBoxLayout(content)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(12)

        # 第一层与冻结稿一致：左侧本周植物，右侧四项关键指标。
        overview = QHBoxLayout()
        overview.setSpacing(12)
        plant_card = QFrame()
        plant_card.setObjectName("dashboardHero")
        plant_card.setMinimumWidth(310)
        plant_layout = QVBoxLayout(plant_card)
        plant_layout.setContentsMargins(18, 16, 18, 16)
        plant_layout.setSpacing(6)
        plant_title = QLabel(f"第 {chapter} 株花藤")
        plant_title.setObjectName("sectionTitle")
        plant_subtitle = QLabel("在专注中生长，让更好的自己慢慢出现")
        plant_subtitle.setObjectName("cardSub")
        plant_layout.addWidget(plant_title)
        plant_layout.addWidget(plant_subtitle)
        hero_row = QHBoxLayout()
        plant_preview = BotanicalPreview(self.theme_name)
        plant_preview.setMinimumSize(190, 220)
        plant_preview.set_visual(self.theme_name, plant_progress, progress_units)
        ring = GrowthRing(int(plant_progress * 100))
        hero_row.addWidget(plant_preview, stretch=1)
        hero_row.addWidget(ring, alignment=Qt.AlignmentFlag.AlignTop)
        plant_layout.addLayout(hero_row, stretch=1)
        plant_note = QLabel(f"成长 {completed}/24 · 当前阶段 {stage} · 本株目标推进 {progress_units} 次")
        plant_note.setObjectName("status")
        plant_layout.addWidget(plant_note)
        overview.addWidget(plant_card, stretch=4)

        stats = QGridLayout()
        stats.setSpacing(10)
        stats.addWidget(make_card("◉  专注轮次", f"{len(records)} 次", f"{self.current_range}完成"), 0, 0)
        stats.addWidget(make_card("◷  专注时长", f"{total_minutes} 分钟", f"{self.current_range}累计"), 0, 1)
        stats.addWidget(make_card("♧  连续专注", f"{streak} 天", "再接再厉"), 1, 0)
        stats.addWidget(make_card("▤  目标有推进", f"{len(effective)} 次", "记录成果并推动开花"), 1, 1)
        overview.addLayout(stats, stretch=6)
        root.addLayout(overview)

        # 第二层：柱线趋势与内容分布，取代旧版的逐行进度条列表。
        analytics = QHBoxLayout()
        analytics.setSpacing(12)
        trend_card = QFrame()
        trend_card.setObjectName("dashboardPanel")
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(16, 13, 16, 13)
        trend_title = QLabel(f"近 {trend_days} 天专注趋势")
        trend_title.setObjectName("sectionTitle")
        trend_layout.addWidget(trend_title)
        trend_widget = TrendChart([(d.strftime("%m-%d"), count) for d, count in trend])
        trend_layout.addWidget(trend_widget)
        analytics.addWidget(trend_card, stretch=7)

        distribution = QFrame()
        distribution.setObjectName("dashboardPanel")
        distribution_layout = QVBoxLayout(distribution)
        distribution_layout.setContentsMargins(16, 13, 16, 13)
        distribution_layout.setSpacing(8)
        self.add_distribution_bars(distribution_layout, "专注内容分布", scenes)
        if not scenes and tasks:
            self.add_distribution_bars(distribution_layout, "任务分布", tasks)
        distribution_layout.addStretch()
        analytics.addWidget(distribution, stretch=3)
        root.addLayout(analytics)

        recent_row = QHBoxLayout()
        recent_title = QLabel("最近产出")
        recent_title.setObjectName("sectionTitle")
        recent_row.addWidget(recent_title)
        recent_row.addStretch()
        all_hint = QLabel("查看全部  ›")
        all_hint.setObjectName("cardSub")
        recent_row.addWidget(all_hint)
        root.addLayout(recent_row)

        card_grid = QGridLayout()
        card_grid.setSpacing(10)
        display_records = list(reversed(records[-6:]))
        if not display_records:
            card_grid.addWidget(make_card("等待第一次生长", "完成一次专注后会出现记录卡片", "每轮都会生长；目标有推进时会逐渐开花。"), 0, 0, 1, 3)
        else:
            for index, record in enumerate(display_records):
                mark = "目标有推进" if record.get("effective") else "完成一轮专注"
                output = record.get("output") or record.get("goal") or "本轮未填写成果摘要"
                subtitle = f"{record.get('date', '')} {record.get('time', '')} · {record.get('scene_mode', '')}"
                card_grid.addWidget(make_card(mark, output, subtitle), index // 3, index % 3)
        root.addLayout(card_grid)
        root.addStretch()
        self.scroll.setWidget(content)

    def change_range(self, text: str):
        self.current_range = text
        self.rebuild_dashboard()

    def copy_report(self):
        QGuiApplication.clipboard().setText(self.report_text)

    def open_records_dir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.state.get_records_dir())))

# =========================
# 花藤覆盖层
# =========================
