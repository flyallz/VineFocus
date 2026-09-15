"""应用静态配置。

维护场景任务、产出字段与花藤主题色；本模块不读写磁盘，也不创建界面。
"""

SCENE_TASKS = {
    "普通专注": ["深度专注", "整理待办", "阅读", "思考规划", "处理杂事", "自定义任务"],
    "学习备考": ["课程复习", "刷题练习", "背单词", "整理错题", "看网课", "考试冲刺", "知识点总结"],
    "科研论文": ["文献阅读", "论文写作", "数据分析", "代码复现", "实验记录", "图表制作", "组会准备", "投稿修改", "审稿回复"],
    "写作创作": ["文章初稿", "脚本创作", "大纲整理", "修改润色", "选题收集", "素材整理", "日更写作"],
    "办公工作": ["写方案", "做 PPT", "处理邮件", "会议纪要", "项目推进", "客户跟进", "资料整理"],
    "代码开发": ["写代码", "修 Bug", "看文档", "代码重构", "测试调试", "提交 Commit", "技术笔记"],
    "自定义": ["自定义任务", "深度专注", "整理记录", "复盘总结"],
}

SCENE_CONFIG = {
    "普通专注": {
        "output_label": "本轮完成了什么",
        "output_placeholder": "- 完成了一个明确任务\n- 整理了一个待办\n- 推进了一件重要事情",
        "detail_label": "补充记录 / 想法 / 阻碍",
        "detail_placeholder": "可以记录中途遇到的问题、想法、干扰来源。",
        "metric_name": "完成事项",
        "metric_unit": "项",
    },
    "学习备考": {
        "output_label": "本轮学习成果",
        "output_placeholder": "- 完成 20 道题\n- 背完 50 个单词\n- 复习完一章知识点",
        "detail_label": "错题 / 不会的点 / 需要回顾的知识",
        "detail_placeholder": "例如：条件概率还不熟，明天需要重做第 3 题。",
        "metric_name": "完成题数",
        "metric_unit": "题",
    },
    "科研论文": {
        "output_label": "本轮科研产出",
        "output_placeholder": "- 读完 1 篇论文\n- 整理出 3 条可引用观点\n- 完成 Introduction 第 2 段修改",
        "detail_label": "关键笔记 / 发现 / 问题",
        "detail_placeholder": "支持 Markdown。可写核心结论、方法、疑问、下一步需要查证的点。",
        "metric_name": "写作字数",
        "metric_unit": "字",
    },
    "写作创作": {
        "output_label": "本轮写作产出",
        "output_placeholder": "- 完成 800 字初稿\n- 修改完第 2 节\n- 整理出 5 个选题",
        "detail_label": "灵感 / 修改点 / 卡住的地方",
        "detail_placeholder": "例如：开头还不够有冲突，下一轮先改第一段。",
        "metric_name": "写作字数",
        "metric_unit": "字",
    },
    "办公工作": {
        "output_label": "本轮工作产出",
        "output_placeholder": "- 完成方案第一版\n- 整理会议纪要\n- 回复 5 封重要邮件",
        "detail_label": "待跟进事项 / 会议结论 / 风险点",
        "detail_placeholder": "例如：需要明天找 XX 确认预算。",
        "metric_name": "完成事项",
        "metric_unit": "项",
    },
    "代码开发": {
        "output_label": "本轮开发产出",
        "output_placeholder": "- 修复登录 Bug\n- 完成一个函数\n- 阅读完 API 文档并写了笔记",
        "detail_label": "技术笔记 / Bug 原因 / 下一步",
        "detail_placeholder": "例如：问题来自 token 过期判断，下一步补测试。",
        "metric_name": "Commit / 修复数",
        "metric_unit": "个",
    },
    "自定义": {
        "output_label": "本轮产出",
        "output_placeholder": "- 完成了什么\n- 有什么结果\n- 有什么下一步",
        "detail_label": "补充记录",
        "detail_placeholder": "支持 Markdown。",
        "metric_name": "成果数据",
        "metric_unit": "项",
    },
}


# =========================
# 界面与花藤视觉主题
# =========================

UI_THEMES = ("夜色流光", "温室晨雾", "薄荷汽水")
GROWTH_LAYOUTS = ("静谧单株", "侧边攀援", "环屏生长")
PERIMETER_GROWTH_MODES = ("四边同步", "等时接力", "自然接力")

VINE_THEMES = {
    "月白花藤": {
        "profile": "ivy",
        "vine": (93, 111, 69),
        "vine_light": (171, 164, 105),
        "tendril": (153, 162, 91),
        "leaf": (78, 119, 88),
        "leaf_dark": (30, 66, 53),
        "leaf_vein": (190, 216, 190),
        "bud": (229, 219, 207),
        "flower_a": (228, 222, 214),
        "flower_b": (255, 251, 241),
        "flower_edge": (188, 179, 169),
        "center": (221, 178, 82),
        "spark": (205, 238, 224),
    },
    "樱雾花枝": {
        "profile": "cherry",
        "vine": (104, 68, 63),
        "vine_light": (177, 119, 103),
        "tendril": (143, 104, 83),
        "leaf": (105, 143, 86),
        "leaf_dark": (51, 83, 58),
        "leaf_vein": (214, 229, 190),
        "bud": (234, 142, 170),
        "flower_a": (242, 163, 191),
        "flower_b": (255, 224, 234),
        "flower_edge": (202, 105, 147),
        "center": (232, 184, 86),
        "spark": (241, 198, 217),
    },
    "流苏紫藤": {
        "profile": "wisteria",
        "vine": (70, 91, 68),
        "vine_light": (132, 143, 91),
        "tendril": (132, 151, 86),
        "leaf": (68, 105, 79),
        "leaf_dark": (28, 58, 49),
        "leaf_vein": (168, 203, 175),
        "bud": (113, 83, 166),
        "flower_a": (141, 105, 198),
        "flower_b": (194, 170, 231),
        "flower_edge": (76, 52, 122),
        "center": (225, 215, 238),
        "spark": (150, 205, 219),
        "pearl": (225, 225, 239),
        "accent": (158, 181, 86),
    },
    "极光荧藤": {
        "profile": "glow",
        "vine": (39, 105, 96),
        "vine_light": (63, 177, 161),
        "tendril": (75, 153, 132),
        "leaf": (41, 126, 118),
        "leaf_dark": (20, 64, 69),
        "leaf_vein": (102, 225, 218),
        "bud": (119, 115, 212),
        "flower_a": (124, 112, 220),
        "flower_b": (164, 165, 238),
        "flower_edge": (76, 76, 164),
        "center": (231, 205, 111),
        "spark": (89, 236, 218),
    },
}


# 旧版本主题名迁移到新的产品命名；读取历史 settings.json 时不会退回默认项。
THEME_ALIASES = {
    "清新绿藤": "月白花藤",
    "清新常春藤": "月白花藤",
    "樱花粉藤": "樱雾花枝",
    "东方樱花枝": "樱雾花枝",
    "紫藤萝": "流苏紫藤",
    "虹彩流光紫藤": "流苏紫藤",
    "夜间萤光": "极光荧藤",
}


def normalize_theme_name(name: str) -> str:
    """返回当前有效主题名，并兼容 v12 及更早版本的保存值。"""
    normalized = THEME_ALIASES.get(name, name)
    return normalized if normalized in VINE_THEMES else "月白花藤"
