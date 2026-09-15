"""VineFocus v1.7.4 轮次花期版的无界面回归测试。

覆盖轮次花期、密度正交、环屏节奏、稳定构图，以及面板/迷你窗/托盘状态切换。
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

from vinefocus.config import (  # noqa: E402
    GROWTH_LAYOUTS,
    PERIMETER_GROWTH_MODES,
    VINE_THEMES,
    normalize_theme_name,
)
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
from vinefocus.widgets import WindowControlButton  # noqa: E402


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
        self.overlay.resize(1920, 1080)
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
        self.assertEqual(dialog.perimeter_growth_combo.count(), len(PERIMETER_GROWTH_MODES))
        self.assertFalse(dialog.perimeter_growth_combo.isEnabled())
        dialog.growth_layout_combo.setCurrentText("环屏生长")
        self.assertTrue(dialog.perimeter_growth_combo.isEnabled())
        self.assertGreaterEqual(dialog.display_combo.count(), 3)
        self.assertEqual(len(dialog.choice_buttons["plant"]), 4)
        dialog.theme_combo.setCurrentText("流苏紫藤")
        self.assertTrue(dialog.choice_buttons["plant"]["流苏紫藤"].isChecked())

    def test_first_run_defaults_are_not_overwritten_by_widget_signals(self):
        self.assertEqual(self.panel.focus_spin.value(), 25)
        self.assertEqual(self.panel.rest_spin.value(), 5)
        self.assertEqual(self.panel.rounds_spin.value(), 1)
        self.assertEqual(self.panel.state.get("focus_minutes"), 25)

    def test_perimeter_growth_mode_is_applied_and_saved(self):
        self.panel.growth_layout_combo.setCurrentText("环屏生长")
        self.panel.perimeter_growth_combo.setCurrentText("自然接力")
        self.assertEqual(self.overlay.perimeter_growth_mode, "自然接力")
        self.assertEqual(self.panel.state.get("perimeter_growth_mode"), "自然接力")

    def test_title_controls_share_one_visual_canvas(self):
        self.assertIsInstance(self.panel.minimize_btn, WindowControlButton)
        self.assertIsInstance(self.panel.close_btn, WindowControlButton)
        self.assertEqual(self.panel.minimize_btn.size(), self.panel.close_btn.size())
        self.assertEqual(self.panel.minimize_btn.text(), "")
        self.assertEqual(self.panel.close_btn.text(), "")
        self.assertEqual(self.panel.minimize_btn.kind, "minimize")
        self.assertEqual(self.panel.close_btn.kind, "close")

    def test_task_plan_is_frozen_while_timer_is_running(self):
        self.panel.rounds_spin.setValue(4)
        self.panel.start()
        self.assertEqual(self.panel.get_total_rounds(), 4)
        self.assertEqual(self.panel.state.growth_target(), 4)
        self.panel.rounds_spin.setValue(8)
        self.assertEqual(self.panel.get_total_rounds(), 4)
        self.assertEqual(self.panel.state.growth_target(), 4)
        self.assertEqual(self.panel.get_focus_seconds(), 25 * 60)
        self.panel.focus_spin.setValue(10)
        self.assertEqual(self.panel.get_focus_seconds(), 25 * 60)
        self.panel.cumulative_growth_check.setChecked(False)
        self.assertTrue(self.panel.is_cumulative_growth())
        self.panel.pause()

    def test_session_snapshot_roundtrip(self):
        self.panel.elapsed_before_pause = 137
        self.panel.phase = "focus"
        self.panel.current_round = 2
        self.panel.save_session_snapshot()
        snapshot = self.panel.state.load_session_snapshot()
        self.assertEqual(snapshot["elapsed"], 137)
        self.assertEqual(snapshot["current_round"], 2)
        self.assertEqual(snapshot["session_total_rounds"], 1)
        self.assertEqual(snapshot["session_focus_seconds"], 25 * 60)
        self.assertTrue(snapshot["session_cumulative_growth"])
        self.assertIn("task", snapshot)

    def test_growth_outcome_only_controls_review_marker(self):
        self.panel.state.begin_next_growth_chapter(4)
        completed, flowers, chapter = self.panel.state.commit_growth(False)
        self.assertEqual((completed, flowers, chapter), (1, 0, 1))
        completed, flowers, chapter = self.panel.state.commit_growth(True)
        self.assertEqual((completed, flowers, chapter), (2, 1, 1))

    def test_switching_to_single_round_starts_one_consistent_new_plant(self):
        """单轮模式不能让画面满开而看板仍沿用上一株的多轮分母。"""
        self.panel.state.begin_next_growth_chapter(4)
        self.panel.state.commit_growth(False)
        completed, effective, chapter = self.panel.state.begin_next_growth_chapter(
            1,
            replace_incomplete=True,
        )
        self.assertEqual((completed, effective, chapter), (0, 0, 2))
        self.assertEqual(self.panel.state.growth_target(), 1)

    def test_focus_only_result_grows_and_blooms_only_on_desktop(self):
        """“只是保持专注”也推进桌面藤与花期，不越权修改面板装饰花。"""
        self.panel.rounds_spin.setValue(4)
        self.panel.state.begin_next_growth_chapter(4)
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
        self.assertAlmostEqual(self.overlay.progress, 1 / 4)
        self.assertAlmostEqual(self.overlay.bloom_progress, (1 / 4) ** 1.15)
        self.assertGreater(self.overlay.open_flower_count, 0)
        self.assertAlmostEqual(self.panel.focus_botanical.progress, 1 / 4)
        self.assertAlmostEqual(self.panel.growth_botanical.progress, 1 / 4)
        self.assertEqual(self.panel.focus_botanical.flower_count, 0)
        self.assertEqual(self.panel.growth_botanical.flower_count, 0)

    def test_growth_stage_uses_plain_language(self):
        stage = self.panel.state.growth_stage_name
        self.assertEqual(stage(0, 0, 8), "萌芽")
        self.assertEqual(stage(1, 0, 8), "初绽")
        self.assertEqual(stage(3, 0, 8), "渐盛")
        self.assertEqual(stage(6, 1, 8), "繁花")
        self.assertEqual(stage(8, 1, 8), "盛花")

    def test_four_and_eight_round_bloom_curves_always_advance_and_finish_full(self):
        """每轮花期严格前进；最后一轮开放当前浓密度规划的全部花位。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        self.overlay.set_density(50)
        for theme_name in VINE_THEMES:
            self.overlay.set_theme(theme_name)
            capacity = len(self.overlay.flower_nodes)
            for rounds in (4, 8):
                progresses = [
                    self.panel.state.bloom_progress(round_index, rounds)
                    for round_index in range(1, rounds + 1)
                ]
                self.assertTrue(all(
                    later > earlier for earlier, later in zip(progresses, progresses[1:])
                ), (theme_name, rounds, progresses))
                reveal_totals = []
                for round_index, bloom in enumerate(progresses, start=1):
                    self.overlay.set_progress(round_index / rounds)
                    self.overlay.set_bloom_progress(bloom)
                    reveal_totals.append(sum(
                        self.overlay._flower_reveal_amount(node)
                        for node in self.overlay.flower_nodes
                    ))
                self.assertTrue(all(
                    later > earlier for earlier, later in zip(reveal_totals, reveal_totals[1:])
                ), (theme_name, rounds, reveal_totals))
                self.assertEqual(self.overlay.open_flower_count, capacity)
                self.assertTrue(all(
                    self.overlay._flower_reveal_amount(node) == 1.0
                    for node in self.overlay.flower_nodes
                ))

    def test_density_controls_capacity_but_bloom_never_changes_density(self):
        """浓密度决定槽位数量，轮次花期只揭示槽位，二者严格正交。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        for theme_name in VINE_THEMES:
            self.overlay.set_theme(theme_name)
            capacities = []
            totals = []
            for density in (10, 50, 90):
                self.overlay.set_density(density)
                before = tuple(len(nodes) for nodes in (
                    self.overlay.leaf_nodes,
                    self.overlay.branch_nodes,
                    self.overlay.tendril_nodes,
                    self.overlay.bud_nodes,
                    self.overlay.flower_nodes,
                ))
                self.overlay.set_bloom_progress(0.55)
                after = tuple(len(nodes) for nodes in (
                    self.overlay.leaf_nodes,
                    self.overlay.branch_nodes,
                    self.overlay.tendril_nodes,
                    self.overlay.bud_nodes,
                    self.overlay.flower_nodes,
                ))
                self.assertEqual(before, after)
                self.assertLessEqual(self.overlay.open_flower_count, len(self.overlay.flower_nodes))
                capacities.append(len(self.overlay.flower_nodes))
                totals.append(sum(before))
            self.assertLess(capacities[0], capacities[1], theme_name)
            self.assertLess(capacities[1], capacities[2], theme_name)
            self.assertLess(totals[0], totals[1], theme_name)
            self.assertLess(totals[1], totals[2], theme_name)

    def test_density_never_reduces_branch_and_leaf_presence(self):
        """滑块写的是枝叶浓密度，任何主题和构图都不能越调越稀。"""
        self.overlay.resize(1920, 1080)
        for layout_name in GROWTH_LAYOUTS:
            self.overlay.set_layout(layout_name)
            for theme_name in VINE_THEMES:
                self.overlay.set_theme(theme_name)
                foliage = []
                for density in (10, 50, 90):
                    self.overlay.set_density(density)
                    foliage.append(
                        len(self.overlay.leaf_nodes) + len(self.overlay.branch_nodes)
                    )
                self.assertLess(foliage[0], foliage[1], (layout_name, theme_name, foliage))
                self.assertLess(foliage[1], foliage[2], (layout_name, theme_name, foliage))

    def test_three_perimeter_timing_modes_have_distinct_consistent_math(self):
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        self.overlay.set_progress(0.375)
        grown = self.overlay.total_length * self.overlay.progress

        self.overlay.set_perimeter_growth_mode("四边同步")
        sync = [self.overlay._gesture_visible_length(item, grown) for item in self.overlay.gestures]
        for gesture, visible in zip(self.overlay.gestures, sync):
            self.assertAlmostEqual(visible, gesture.length * 0.375, places=5)

        self.overlay.set_perimeter_growth_mode("等时接力")
        equal = [self.overlay._gesture_visible_length(item, grown) for item in self.overlay.gestures]
        self.assertAlmostEqual(equal[0], self.overlay.gestures[0].length, places=5)
        self.assertAlmostEqual(equal[1], self.overlay.gestures[1].length * 0.5, places=5)
        self.assertTrue(all(value == 0.0 for value in equal[2:]))

        self.overlay.set_perimeter_growth_mode("自然接力")
        natural = [self.overlay._gesture_visible_length(item, grown) for item in self.overlay.gestures]
        self.assertAlmostEqual(sum(natural), self.overlay.total_length * 0.375, places=5)
        self.assertNotEqual(equal, natural)

    def test_perimeter_blooms_are_balanced_across_gestures(self):
        """前四个开花位应分散到四段环屏路径，而不是挤在第一角。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        ranked = sorted(self.overlay.flower_nodes, key=lambda node: node.unlock_rank)[:4]
        gesture_indexes = [node.gesture_index for node in ranked]
        self.assertEqual(len(set(gesture_indexes)), 4)

        # 四轮任务的第一轮结束后，首批跨区域花位都位于已长成范围内。
        grown_length = self.overlay.total_length * (1 / 4)
        visible = [node for node in ranked if node.distance <= grown_length]
        self.assertEqual(len(visible), 4)

    def test_first_completed_round_has_a_visible_bloom_group(self):
        """即使设置 12 轮，第一轮完成后也已有可见桌面花位。"""
        self.overlay.resize(1920, 1080)
        self.overlay.set_layout("环屏生长")
        for theme_name in VINE_THEMES:
            self.overlay.set_theme(theme_name)
            first = min(self.overlay.flower_nodes, key=lambda node: node.unlock_rank)
            self.assertLessEqual(first.distance, self.overlay.total_length / 12, theme_name)

    def test_four_bloom_events_change_pixels_in_all_four_screen_regions(self):
        """验证最终合成结果，而不只验证内部节点：四角都必须真的画出花。"""
        self.overlay.resize(960, 540)
        self.overlay.set_layout("环屏生长")
        self.overlay.set_theme("樱雾花枝")
        self.overlay.set_presentation(44, 62, True)
        self.overlay.set_progress(1 / 4)

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

    def test_all_themes_keep_priority_organs_clear_at_high_density(self):
        """高密度允许更茂盛，但花、枝、苞、卷须和直属叶不能堆在同一关节。"""
        self.overlay.resize(1920, 1080)

        def assert_clear(candidates, blockers, gap, label):
            for node in candidates:
                for other in blockers:
                    point_gap = ((node.point.x() - other.point.x()) ** 2 + (
                        node.point.y() - other.point.y()
                    ) ** 2) ** 0.5
                    self.assertGreaterEqual(point_gap, gap * 0.82, label)
                    if node.gesture_index == other.gesture_index:
                        self.assertGreaterEqual(
                            abs(node.local_distance - other.local_distance), gap, label
                        )

        for layout_name in GROWTH_LAYOUTS:
            self.overlay.set_layout(layout_name)
            for theme_name in VINE_THEMES:
                self.overlay.set_theme(theme_name)
                self.overlay.set_density(90)
                flower_gap = 28.0 if self.overlay.profile == "glow" else 22.0
                leaf_gap = 24.0 if self.overlay.profile == "glow" else 18.0
                label = f"{layout_name} / {theme_name}"
                assert_clear(
                    self.overlay.branch_nodes, self.overlay.flower_nodes, flower_gap, label
                )
                assert_clear(
                    self.overlay.bud_nodes,
                    self.overlay.flower_nodes + self.overlay.branch_nodes,
                    flower_gap,
                    label,
                )
                assert_clear(
                    self.overlay.tendril_nodes,
                    self.overlay.flower_nodes + self.overlay.branch_nodes + self.overlay.bud_nodes,
                    20.0,
                    label,
                )
                assert_clear(
                    self.overlay.leaf_nodes,
                    self.overlay.flower_nodes + self.overlay.branch_nodes
                    + self.overlay.bud_nodes + self.overlay.tendril_nodes,
                    leaf_gap,
                    label,
                )

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

    def test_new_plant_seed_and_target_are_selected_before_timer_starts(self):
        """四轮植物完成后，新任务先换株并冻结新的八轮分母。"""
        self.panel.state.data.update({
            "growth_completed_units": 4,
            "growth_effective_units": 2,
            "growth_target_units": 4,
            "growth_chapter": 1,
        })
        self.panel.rounds_spin.setValue(8)
        self.panel.reset(confirm=False)
        self.assertEqual(self.overlay.growth_chapter, 1)
        self.panel.start()
        self.assertEqual(self.panel.state.growth_state(), (0, 0, 2))
        self.assertEqual(self.panel.state.growth_target(), 8)
        self.assertEqual(self.panel.get_total_rounds(), 8)
        self.assertEqual(self.overlay.growth_chapter, 2)
        self.assertEqual(self.overlay.progress, 0.0)
        self.assertEqual(self.overlay.open_flower_count, 0)
        self.panel.pause()

    def test_pause_freezes_the_exact_visual_growth_state(self):
        """暂停后即使刷新界面，也不能让主藤或卡片预览偷偷向前生长。"""
        self.panel.state.data.update({
            "growth_completed_units": 4,
            "growth_target_units": 8,
        })
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

    def test_next_focus_continues_from_previous_committed_growth(self):
        """记录后进入下一轮时，从上一轮终点续长，不缩回种子或停在原地。"""
        self.panel.rounds_spin.setValue(4)
        self.panel.prepare_session_plan()
        self.panel.state.begin_next_growth_chapter(4)
        result = {
            "effective": False,
            "output": "完成一轮",
            "notes": "",
            "next_step": "继续",
            "metric_name": "成果数据",
            "metric_unit": "",
            "metric_value": 0,
        }
        with patch.object(OutputDialog, "exec", return_value=0), patch.object(
            OutputDialog, "get_result_data", return_value=result
        ):
            self.assertFalse(self.panel.capture_output_after_focus())
        self.panel.finish_focus_record(False)
        self.panel.skip_rest()
        self.assertEqual(self.panel.current_round, 2)
        self.assertAlmostEqual(self.overlay.progress, 0.25)
        self.panel.start()
        now = time.monotonic()
        self.panel.start_time = now - 30.0
        self.panel.last_tick_monotonic = now
        self.panel.update_timer()
        self.assertGreater(self.overlay.progress, 0.25)
        self.assertLess(self.overlay.progress, 0.50)
        self.panel.pause()

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
        self.panel.state.data.update({
            "growth_completed_units": 2,
            "growth_effective_units": 1,
            "growth_target_units": 4,
        })
        dashboard = DashboardDialog(self.panel.state, current_progress=0.5)
        report = dashboard.build_report_text()
        self.assertIn("当前植物", report)
        self.assertIn("成长 2/4", report)
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
            "growth_target_units": 99,
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

    def test_rest_breathing_is_visibly_different_between_two_phases(self):
        self.overlay.resize(960, 540)
        self.overlay.set_layout("侧边攀援")
        self.overlay.set_theme("极光荧藤")
        self.overlay.set_presentation(52, 58, False)
        self.overlay.set_progress(1.0)
        self.overlay.set_bloom_progress(1.0)
        self.overlay.set_rest_mode(True)

        def render(wave):
            self.overlay.set_rest_wave(wave)
            image = QImage(960, 540, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            self.overlay.render(painter, QPoint())
            painter.end()
            return image

        neutral = render(0.0)
        inhale = render(1.496)
        changed = sum(
            neutral.pixel(x, y) != inhale.pixel(x, y)
            for y in range(540)
            for x in range(960)
        )
        self.assertGreater(changed, 250)

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
