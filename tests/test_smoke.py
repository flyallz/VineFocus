"""VineFocus v1.7.3 用户优先生长版的无界面冒烟测试。

覆盖三种构图、稳定节点、有效产出开花，以及主面板/迷你窗/托盘的状态切换。
"""

import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, qAlpha  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from vinefocus.config import GROWTH_LAYOUTS, VINE_THEMES, normalize_theme_name  # noqa: E402
from vinefocus.botanical_assets import (  # noqa: E402
    AURORA_TRANSFORMS,
    BotanicalAssets,
    ORGAN_NAMES,
    ORGAN_TRANSFORMS,
    THEME_ASSETS,
    WISTERIA_TRANSFORMS,
)
from vinefocus.dialogs import DashboardDialog, OutputDialog  # noqa: E402
from vinefocus.overlay import VineOverlay  # noqa: E402
from vinefocus.panel import PomodoroPanel  # noqa: E402
from vinefocus.single_instance import SingleInstanceGuard  # noqa: E402
from vinefocus.tray import TrayController  # noqa: E402


class VineFocusSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home_patch = patch(
            "vinefocus.state.Path.home",
            return_value=Path(self.temp_dir.name),
        )
        self.home_patch.start()
        self.overlay = VineOverlay()
        self.panel = PomodoroPanel(self.overlay)
        self.tray = TrayController(self.panel)

    def tearDown(self):
        self.tray.tray.hide()
        self.panel.settings_dialog.hide()
        self.panel.hide()
        self.overlay.hide()
        self.home_patch.stop()
        self.temp_dir.cleanup()

    def test_vine_layout_is_stable(self):
        self.overlay.resize(1280, 720)
        self.overlay.set_density("标准")
        first = [
            (round(node.distance, 4), node.side, node.variant, round(node.scale, 4))
            for node in self.overlay.leaf_nodes
        ]
        self.overlay.rebuild_path()
        second = [
            (round(node.distance, 4), node.side, node.variant, round(node.scale, 4))
            for node in self.overlay.leaf_nodes
        ]
        self.assertEqual(first, second)

    def test_high_dpi_scale_is_capped_and_joints_keep_clearance(self):
        """4K 不无限放大器官，枝根与花位附近不再叠直属叶片。"""
        self.overlay.resize(3891, 1967)
        self.overlay.set_layout("环屏生长")
        self.assertAlmostEqual(self.overlay._resolution_scale(), 1.35)
        reserved = self.overlay.branch_nodes + self.overlay.bud_nodes + self.overlay.flower_nodes
        self.assertTrue(all(
            leaf.gesture_index != other.gesture_index
            or abs(leaf.local_distance - other.local_distance) >= 17.0
            for leaf in self.overlay.leaf_nodes
            for other in reserved
        ))

    def test_density_tiers_have_distinct_node_counts(self):
        """密度不是透明度别名，三档必须产生递增的器官数量。"""
        counts = {}
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        for density in ("清爽", "标准", "茂盛"):
            self.overlay.set_density(density)
            counts[density] = sum(len(items) for items in (
                self.overlay.leaf_nodes,
                self.overlay.branch_nodes,
                self.overlay.tendril_nodes,
                self.overlay.bud_nodes,
                self.overlay.flower_nodes,
            ))
        self.assertLess(counts["清爽"], counts["标准"])
        self.assertLess(counts["标准"], counts["茂盛"])

    def test_organ_anchors_match_growth_direction(self):
        """普通叶从下部连接，紫藤与极光叶使用各自的顶部悬垂锚点。"""
        self.assertLess(ORGAN_TRANSFORMS["leaf_mature"][0], 0.25)
        self.assertGreater(ORGAN_TRANSFORMS["leaf_mature"][1], 0.90)
        for organ in ("leaf_mature", "bud_swollen", "bloom_open"):
            self.assertLess(WISTERIA_TRANSFORMS[organ][1], 0.15)
        for organ in ("leaf_tiny", "leaf_small", "leaf_medium", "leaf_mature"):
            self.assertAlmostEqual(AURORA_TRANSFORMS[organ][0], 0.50)
            self.assertLess(AURORA_TRANSFORMS[organ][1], 0.10)

    def test_side_climb_stays_inside_a_fixed_edge_band(self):
        """2K/4K 宽屏的主藤仍贴边，而不是按宽度百分比漂进内容区。"""
        self.overlay.resize(3891, 1967)
        self.overlay.set_layout("侧边攀援")
        for theme_name in ("月白花藤", "樱雾花枝", "极光荧藤"):
            self.overlay.set_theme(theme_name)
            self.assertLess(max(point.x() for point in self.overlay.path_points), 82.0)
        self.overlay.set_theme("流苏紫藤")
        self.assertGreater(min(point.x() for point in self.overlay.path_points), 3891 - 82.0)

    def test_density_is_continuous_and_does_not_change_presentation(self):
        self.overlay.set_presentation(44, 38)
        original = (self.overlay.plant_presence, self.overlay.plant_opacity)
        counts = []
        for value in (10, 50, 90):
            self.overlay.set_density(value)
            counts.append(sum(len(items) for items in (
                self.overlay.leaf_nodes, self.overlay.branch_nodes,
                self.overlay.bud_nodes, self.overlay.flower_nodes,
            )))
            self.assertEqual((self.overlay.plant_presence, self.overlay.plant_opacity), original)
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])

    def test_all_visual_profiles_render(self):
        """四套植物、三种构图和多个生长阶段都能离屏绘制。"""
        layout_counts = {}
        for theme_name in VINE_THEMES:
            self.overlay.set_theme(theme_name)
            for layout_name in GROWTH_LAYOUTS:
                self.overlay.resize(960, 540)
                self.overlay.set_layout(layout_name)
                layout_counts[layout_name] = len(self.overlay.gestures)
                for progress in (0.12, 0.48, 1.0):
                    self.overlay.set_progress(progress)
                    self.overlay.set_open_flower_count(1)
                    image = QImage(960, 540, QImage.Format.Format_ARGB32_Premultiplied)
                    image.fill(QColor("#111417"))
                    painter = QPainter(image)
                    self.overlay.render(painter, QPoint())
                    painter.end()
                    self.assertFalse(image.isNull())
        self.assertEqual(layout_counts["静谧单株"], 1)
        self.assertEqual(layout_counts["侧边攀援"], 1)
        self.assertEqual(layout_counts["环屏生长"], 4)

    def test_high_fidelity_assets_are_available_with_alpha(self):
        """四套枝叶、细分器官与兼容花朵图集都能透明合成。"""
        self.assertEqual(set(THEME_ASSETS), set(VINE_THEMES))
        for theme_name in VINE_THEMES:
            pixmap = BotanicalAssets.base(theme_name)
            self.assertFalse(pixmap.isNull(), theme_name)
            self.assertTrue(pixmap.hasAlphaChannel(), theme_name)
            self.assertTrue(BotanicalAssets.has_organ_atlas(theme_name), theme_name)
            for organ_name in ORGAN_NAMES:
                organ = BotanicalAssets.organ_pixmap(theme_name, organ_name)
                self.assertFalse(organ.isNull(), f"{theme_name}: {organ_name}")
                self.assertTrue(organ.hasAlphaChannel(), f"{theme_name}: {organ_name}")
                image = organ.toImage()
                corners = (
                    image.pixel(0, 0), image.pixel(image.width() - 1, 0),
                    image.pixel(0, image.height() - 1),
                    image.pixel(image.width() - 1, image.height() - 1),
                )
                self.assertTrue(all(qAlpha(pixel) <= 8 for pixel in corners), f"{theme_name}: {organ_name}")
        atlas = BotanicalAssets.flower_atlas()
        self.assertFalse(atlas.isNull())
        self.assertTrue(atlas.hasAlphaChannel())
        self.overlay.set_progress(1.0)
        self.overlay.set_open_flower_count(0)
        self.assertEqual(self.overlay.open_flower_count, 0)
        self.overlay.set_open_flower_count(2)
        self.assertEqual(self.overlay.open_flower_count, 2)

    def test_perimeter_assets_touch_all_screen_edges_without_mirror_repetition(self):
        """环屏构图按真实植物边界贴边，并使用不等尺寸形成自然主次。"""
        bounds = QRectF(0, 0, 1920, 1080)
        for theme_name in VINE_THEMES:
            placements = BotanicalAssets.placements(theme_name, "环屏生长", bounds, 0.45)
            self.assertEqual(len(placements), 4)
            self.assertTrue(any(item.rect.left() < 0 for item in placements), theme_name)
            self.assertTrue(any(item.rect.right() > bounds.right() for item in placements), theme_name)
            self.assertTrue(any(item.rect.top() < 0 for item in placements), theme_name)
            self.assertTrue(any(item.rect.bottom() > bounds.bottom() for item in placements), theme_name)
            self.assertGreater(len({round(item.rect.height()) for item in placements}), 2, theme_name)
            self.assertGreater(max(item.opacity for item in placements), min(item.opacity for item in placements))

    def test_legacy_theme_names_are_migrated(self):
        self.assertEqual(normalize_theme_name("清新绿藤"), "月白花藤")
        self.assertEqual(normalize_theme_name("樱花粉藤"), "樱雾花枝")
        self.assertEqual(normalize_theme_name("紫藤萝"), "流苏紫藤")
        self.assertEqual(normalize_theme_name("夜间萤光"), "极光荧藤")

    def test_v17_settings_are_available(self):
        dialog = self.panel.settings_dialog
        self.assertEqual(dialog.ui_theme_combo.count(), 3)
        self.assertEqual(dialog.growth_layout_combo.count(), 3)
        self.assertEqual(dialog.theme_combo.count(), 4)
        self.assertTrue(hasattr(dialog, "presence_slider"))
        self.assertTrue(hasattr(dialog, "density_slider"))
        self.assertEqual(dialog.density_slider.minimum(), 0)
        self.assertEqual(dialog.density_slider.maximum(), 100)
        self.assertTrue(hasattr(dialog, "reduce_motion_check"))
        self.assertTrue(hasattr(dialog, "skip_final_rest_check"))
        self.assertGreaterEqual(dialog.display_combo.count(), 3)
        self.assertEqual(len(dialog.choice_buttons["plant"]), 4)
        dialog.theme_combo.setCurrentText("流苏紫藤")
        self.assertTrue(dialog.choice_buttons["plant"]["流苏紫藤"].isChecked())

    def test_first_run_defaults_are_not_overwritten_by_widget_signals(self):
        self.assertEqual(self.panel.focus_spin.value(), 25)
        self.assertEqual(self.panel.rest_spin.value(), 5)
        self.assertEqual(self.panel.rounds_spin.value(), 1)
        self.assertEqual(self.panel.state.get("focus_minutes"), 25)

    def test_session_snapshot_roundtrip(self):
        self.panel.elapsed_before_pause = 137
        self.panel.phase = "focus"
        self.panel.current_round = 2
        self.panel.save_session_snapshot()
        snapshot = self.panel.state.load_session_snapshot()
        self.assertEqual(snapshot["elapsed"], 137)
        self.assertEqual(snapshot["current_round"], 2)
        self.assertIn("task", snapshot)

    def test_growth_outcome_controls_flower_count(self):
        completed, flowers, chapter = self.panel.state.commit_growth(False)
        self.assertEqual((completed, flowers, chapter), (1, 0, 1))
        completed, flowers, chapter = self.panel.state.commit_growth(True)
        self.assertEqual((completed, flowers, chapter), (2, 1, 1))

    def test_focus_only_result_visibly_grows_without_opening_flowers(self):
        """“只是保持专注”走完整保存流程后，主藤和两处预览都前进 1/24。"""
        result = {
            "effective": False,
            "output": "完成了一轮阅读",
            "notes": "",
            "next_step": "继续阅读",
            "metric_name": "成果数据",
            "metric_unit": "",
            "metric_value": 0,
        }
        with patch.object(OutputDialog, "exec", return_value=0), patch.object(
            OutputDialog, "get_result_data", return_value=result
        ):
            self.assertFalse(self.panel.capture_output_after_focus())
        self.assertEqual(self.panel.state.growth_state(), (1, 0, 1))
        self.assertAlmostEqual(self.overlay.progress, 1 / 24)
        self.assertEqual(self.overlay.open_flower_count, 0)
        self.assertAlmostEqual(self.panel.focus_botanical.progress, 1 / 24)
        self.assertAlmostEqual(self.panel.growth_botanical.progress, 1 / 24)

    def test_growth_stage_uses_plain_language(self):
        stage = self.panel.state.growth_stage_name
        self.assertEqual(stage(0, 0), "萌芽")
        self.assertEqual(stage(10, 0), "孕蕾")
        self.assertEqual(stage(18, 1), "初花")
        self.assertEqual(stage(18, 4), "渐盛")
        self.assertEqual(stage(22, 9), "盛花")

    def test_perimeter_blooms_are_balanced_across_gestures(self):
        """前四个开花位应分散到四段环屏路径，而不是挤在第一角。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        ranked = sorted(self.overlay.flower_nodes, key=lambda node: node.unlock_rank)[:4]
        gesture_indexes = [node.gesture_index for node in ranked]
        self.assertEqual(len(set(gesture_indexes)), 4)

        # 四轮均有推进时，四处花簇必须都位于已长成范围内，不能只在数据上解锁。
        grown_length = self.overlay.total_length * (4 / 24)
        visible = [node for node in ranked if node.distance <= grown_length]
        self.assertEqual(len(visible), 4)

    def test_first_effective_round_has_a_visible_bloom_group(self):
        """第一轮有效推进结束后就有可见花簇，不必等到第三、四轮。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        for theme_name in VINE_THEMES:
            self.overlay.set_theme(theme_name)
            first = min(self.overlay.flower_nodes, key=lambda node: node.unlock_rank)
            self.assertLessEqual(first.distance, self.overlay.total_length / 24, theme_name)

    def test_four_bloom_events_change_pixels_in_all_four_screen_regions(self):
        """验证最终合成结果，而不只验证内部节点：四角都必须真的画出花。"""
        self.overlay.resize(960, 540)
        self.overlay.set_layout("环屏生长")
        self.overlay.set_theme("樱雾花枝")
        self.overlay.set_presentation(44, 62, True)
        self.overlay.set_progress(4 / 24)

        def render(flower_count):
            self.overlay.set_open_flower_count(flower_count)
            image = QImage(960, 540, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            self.overlay.render(painter, QPoint())
            painter.end()
            return image

        without_flowers = render(0)
        with_flowers = render(4)
        changed = [0, 0, 0, 0]
        for y in range(540):
            for x in range(960):
                if without_flowers.pixel(x, y) != with_flowers.pixel(x, y):
                    changed[(2 if y >= 270 else 0) + (1 if x >= 480 else 0)] += 1
        self.assertTrue(all(pixel_count > 20 for pixel_count in changed), changed)

    def test_aurora_leaves_face_inward_without_duplicate_anchors(self):
        """极光心形叶朝向内容区，同一根茎不再叠放一对共锚叶片。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        self.overlay.set_theme("极光荧藤")
        for node in self.overlay.leaf_nodes:
            self.assertEqual(node.side, self.overlay._inward_side(node.point, node.angle))
        for index, first in enumerate(self.overlay.leaf_nodes):
            for second in self.overlay.leaf_nodes[index + 1:]:
                if first.gesture_index == second.gesture_index:
                    self.assertGreater(abs(first.local_distance - second.local_distance), 0.5)

    def test_tray_menu_has_explicit_contrasting_theme(self):
        """托盘菜单始终同时声明前景和背景，杜绝系统浅色菜单白底白字。"""
        dark_qss = self.tray.menu.styleSheet()
        self.assertIn("QMenu", dark_qss)
        self.assertIn("color: #EAF0F4", dark_qss)
        self.assertIn("background: rgba(6, 14, 25, 238)", dark_qss)
        self.panel.ui_theme_combo.setCurrentText("温室晨雾")
        self.app.processEvents()
        light_qss = self.tray.menu.styleSheet()
        self.assertIn("color: #294637", light_qss)
        self.assertIn("background: rgba(239, 244, 235, 250)", light_qss)

    def test_panel_height_follows_content_and_previews_match_growth(self):
        """主面板不保留大片空白，小植物也不再伪装成至少半成熟。"""
        self.panel.show_panel()
        self.app.processEvents()
        self.panel._fit_panel_to_content()
        self.assertEqual(self.panel.height(), self.panel.container.sizeHint().height())
        self.assertLess(self.panel.height(), 700)
        collapsed_height = self.panel.height()
        self.panel.toggle_task_editor()
        self.app.processEvents()
        self.assertGreater(self.panel.height(), collapsed_height)
        self.assertEqual(self.panel.height(), self.panel.container.sizeHint().height())
        self.panel.toggle_task_editor()
        self.app.processEvents()
        self.assertEqual(self.panel.height(), collapsed_height)

        self.overlay.set_progress(1 / 24)
        self.overlay.set_open_flower_count(0)
        self.panel.sync_botanical_previews()
        self.assertAlmostEqual(self.panel.focus_botanical.progress, 1 / 24)
        self.assertAlmostEqual(self.panel.growth_botanical.progress, 1 / 24)
        self.assertEqual(self.panel.focus_botanical.flower_count, 0)

    def test_new_plant_seed_is_selected_before_its_first_timer_starts(self):
        """满 24 轮后的下一株先换种子再计时，提交时不会突然跳形。"""
        self.panel.state.data.update({
            "growth_completed_units": 24,
            "growth_effective_units": 9,
            "growth_chapter": 1,
        })
        self.panel.reset(confirm=False)
        self.assertEqual(self.overlay.growth_chapter, 1)
        self.panel.start()
        self.assertEqual(self.panel.state.growth_state(), (0, 0, 2))
        self.assertEqual(self.overlay.growth_chapter, 2)
        self.assertEqual(self.overlay.progress, 0.0)
        self.assertEqual(self.overlay.open_flower_count, 0)
        self.panel.pause()

    def test_pause_freezes_the_exact_visual_growth_state(self):
        """暂停后即使刷新界面，也不能让主藤或卡片预览偷偷向前生长。"""
        self.panel.state.data["growth_completed_units"] = 4
        self.panel.reset(confirm=False)
        self.panel.start()
        now = time.monotonic()
        self.panel.start_time = now - 15.0
        self.panel.last_tick_monotonic = now
        self.panel.update_timer()
        self.panel.pause()
        frozen = self.overlay.progress
        preview_frozen = self.panel.focus_botanical.progress
        self.panel.update_timer()
        self.app.processEvents()
        self.assertAlmostEqual(self.overlay.progress, frozen)
        self.assertAlmostEqual(self.panel.focus_botanical.progress, preview_frozen)

    def test_output_metric_is_optional_and_hidden_by_default(self):
        dialog = OutputDialog("自定义", "自定义任务", "完成当前步骤")
        self.assertFalse(dialog.metric_panel.isVisible())
        self.assertFalse(dialog.progress_choice.isChecked())
        self.assertFalse(dialog.focus_choice.isChecked())
        self.assertFalse(dialog.save_btn.isEnabled())
        dialog.focus_choice.click()
        self.assertTrue(dialog.focus_choice.isChecked())
        self.assertTrue(dialog.save_btn.isEnabled())
        self.assertIn("成果数据", dialog.metric_toggle.text())
        dialog.close()

    def test_dashboard_report_separates_plant_and_history_language(self):
        dashboard = DashboardDialog(self.panel.state, current_progress=0.5)
        report = dashboard.build_report_text()
        self.assertIn("当前植物", report)
        self.assertIn("目标有推进", report)
        self.assertNotIn("待开花苞", report)
        self.assertNotIn("花簇 /", report)
        self.assertEqual({}, dashboard.metric_summary([{"metric_name": "数量", "metric_value": 0}]))
        dashboard.close()

    def test_optional_metric_is_not_limited_to_goal_progress_records(self):
        dashboard = DashboardDialog(self.panel.state)
        totals = dashboard.metric_summary([
            {"effective": False, "metric_name": "页数", "metric_unit": "页", "metric_value": 3},
            {"effective": True, "metric_name": "页数", "metric_unit": "页", "metric_value": 2},
        ])
        self.assertEqual(totals, {("页数", "页"): 5})
        dashboard.close()

    def test_growth_state_clamps_invalid_legacy_counts(self):
        self.panel.state.data.update({
            "growth_completed_units": 99,
            "growth_effective_units": 101,
            "growth_chapter": 0,
        })
        self.assertEqual(self.panel.state.growth_state(), (24, 24, 1))

    def test_rest_animation_has_an_independent_timer(self):
        self.overlay.set_presentation(36, 40, False)
        self.overlay.set_rest_mode(True)
        self.assertTrue(self.overlay._rest_animation_timer.isActive())
        before = self.overlay.rest_wave
        self.overlay._advance_rest_animation()
        self.assertGreaterEqual(self.overlay.rest_wave, before)
        self.overlay.set_rest_mode(False)
        self.assertFalse(self.overlay._rest_animation_timer.isActive())

    def test_side_climb_has_room_for_multiple_bloom_events(self):
        """标准侧边构图至少容纳五次开花事件，不会长期只显示一朵花。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("侧边攀援")
        self.overlay.set_density(50)
        for theme_name in VINE_THEMES:
            self.overlay.set_theme(theme_name)
            self.assertGreaterEqual(len(self.overlay.flower_nodes), 5, theme_name)
            self.overlay.set_open_flower_count(5)
            self.assertEqual(self.overlay.open_flower_count, 5)

    def test_single_instance_notifies_existing_process(self):
        key = f"vinefocus-test-{uuid.uuid4()}"
        first = SingleInstanceGuard(key)
        second = SingleInstanceGuard(key)
        self.assertTrue(first.acquire_or_notify())
        self.assertFalse(second.acquire_or_notify())
        first.server.close()

    def test_window_state_cycle(self):
        original_id = id(self.panel)
        self.panel.show_panel()
        self.app.processEvents()
        self.assertEqual(self.panel.display_mode, "panel")
        self.assertTrue(self.panel.isVisible())

        for _ in range(25):
            self.panel.hide_panel_only()
            self.panel.show_panel()
        self.app.processEvents()
        self.assertEqual(id(self.panel), original_id)
        self.assertTrue(self.panel.isVisible())
        self.assertFalse(self.panel.mini_button.isVisible())

        self.panel.hide_to_mini()
        self.assertEqual(self.panel.display_mode, "mini")
        self.assertFalse(self.panel.isVisible())
        self.assertTrue(self.panel.mini_button.isVisible())

        self.panel.show_panel()
        self.app.processEvents()
        self.assertEqual(self.panel.display_mode, "panel")
        self.assertTrue(self.panel.isVisible())
        self.assertFalse(self.panel.mini_button.isVisible())

        self.panel.hide_panel_only()
        self.assertEqual(self.panel.display_mode, "tray")
        self.assertFalse(self.panel.isVisible())
        self.assertFalse(self.panel.mini_button.isVisible())

        self.tray.toggle_panel()
        self.app.processEvents()
        self.assertEqual(self.panel.display_mode, "panel")
        self.assertTrue(self.panel.isVisible())


if __name__ == "__main__":
    unittest.main()
