"""VineFocus 视觉令牌与 Qt 样式。

提供夜色流光、温室晨雾和薄荷汽水三套界面主题；本模块只生成 QSS，
不保存设置，也不直接操作任何窗口。
"""

from __future__ import annotations


THEME_TOKENS = {
    "夜色流光": {
        "text": "#EAF0F4",
        "muted": "#8495A4",
        "soft": "#B3C0CA",
        "shell": "rgba(8, 17, 29, 232)",
        "shell_top": "rgba(15, 30, 45, 232)",
        "shell_bottom": "rgba(6, 14, 25, 238)",
        "card": "rgba(23, 37, 52, 176)",
        "card_alt": "rgba(29, 46, 63, 156)",
        "input": "rgba(13, 25, 39, 210)",
        "border": "rgba(148, 174, 194, 45)",
        "border_focus": "#5AAFA7",
        "accent": "#2B968C",
        "accent_hover": "#35A79C",
        "accent_pressed": "#22766F",
        "accent_soft": "rgba(65, 164, 151, 30)",
        "focus_glow": "rgba(20, 69, 79, 170)",
        "primary_top": "#2AA398",
        "primary_bottom": "#207A75",
        "danger": "#B99483",
        "disabled": "#607584",
    },
    "温室晨雾": {
        "text": "#294637",
        "muted": "#728477",
        "soft": "#526C5D",
        "shell": "rgba(247, 248, 241, 248)",
        "shell_top": "rgba(252, 253, 248, 246)",
        "shell_bottom": "rgba(239, 244, 235, 250)",
        "card": "rgba(255, 255, 251, 238)",
        "card_alt": "rgba(239, 246, 235, 226)",
        "input": "rgba(255, 255, 253, 248)",
        "border": "rgba(104, 142, 104, 86)",
        "border_focus": "#5D9666",
        "accent": "#4E8D5A",
        "accent_hover": "#5A9B66",
        "accent_pressed": "#3E7649",
        "accent_soft": "rgba(91, 153, 96, 38)",
        "focus_glow": "rgba(226, 240, 220, 220)",
        "primary_top": "#5C9967",
        "primary_bottom": "#437C50",
        "danger": "#9A7564",
        "disabled": "#96A29A",
    },
    "薄荷汽水": {
        "text": "#173F43",
        "muted": "#66898A",
        "soft": "#3F696C",
        "shell": "rgba(239, 251, 248, 248)",
        "shell_top": "rgba(247, 255, 253, 246)",
        "shell_bottom": "rgba(227, 246, 241, 250)",
        "card": "rgba(253, 255, 254, 238)",
        "card_alt": "rgba(225, 247, 240, 228)",
        "input": "rgba(255, 255, 255, 248)",
        "border": "rgba(73, 153, 145, 82)",
        "border_focus": "#20A999",
        "accent": "#2AA899",
        "accent_hover": "#35B7A7",
        "accent_pressed": "#208D81",
        "accent_soft": "rgba(42, 168, 153, 42)",
        "focus_glow": "rgba(211, 242, 235, 220)",
        "primary_top": "#36AA9D",
        "primary_bottom": "#258D84",
        "danger": "#A17B73",
        "disabled": "#8BA3A0",
    },
}


def build_app_qss(theme_name: str = "夜色流光", glass_effect: bool = True) -> str:
    """按主题返回完整 QSS；关闭玻璃时使用更实的卡片背景。"""
    token = THEME_TOKENS.get(theme_name, THEME_TOKENS["夜色流光"])
    card = token["card"] if glass_effect else token["input"]
    return f"""
QWidget {{
    color: {token['text']};
    font-family: "PingFang SC", "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}}

QDialog {{ background: {token['shell']}; }}

QWidget#appShell {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {token['shell_top']}, stop:0.55 {token['shell']}, stop:1 {token['shell_bottom']});
    border: 1px solid {token['border']};
    border-radius: 26px;
}}

QFrame#focusCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {token['card']}, stop:0.58 {token['focus_glow']}, stop:1 {token['card']});
    border: 1px solid {token['border']};
    border-radius: 22px;
}}

QFrame#taskCard, QFrame#settingsCard, QFrame#settingSection, QFrame#statCard,
QFrame#growthCard, QFrame#dashboardHero, QFrame#dashboardPanel {{
    background: {card};
    border: 1px solid {token['border']};
    border-radius: 18px;
}}

QLabel#brandTitle {{ color: {token['text']}; font-size: 22px; font-weight: 800; }}
QLabel#dashboardTitle {{ color: {token['text']}; font-size: 26px; font-weight: 850; }}
QLabel#brandSub, QLabel#sectionHint, QLabel#metaText, QLabel#fieldLabel,
QLabel#muted, QLabel#subtitle, QLabel#cardSub {{ color: {token['muted']}; font-size: 11px; }}
QLabel#sectionTitle {{ color: {token['text']}; font-size: 15px; font-weight: 750; }}
QLabel#taskSummaryTitle {{ color: {token['text']}; font-size: 20px; font-weight: 800; }}

QLabel#phasePill {{
    color: {token['text']}; background: {token['accent_soft']};
    border: 1px solid {token['border']}; border-radius: 11px;
    padding: 5px 12px; font-size: 11px; font-weight: 750;
}}
QLabel#phasePill[phaseState="focus"] {{ color:#DDF1ED; background:rgba(48,143,130,42); border-color:rgba(99,177,166,72); }}
QLabel#phasePill[phaseState="paused"] {{ color:#EAE5F5; background:rgba(126,108,180,38); border-color:rgba(155,139,202,66); }}
QLabel#phasePill[phaseState="rest"] {{ color:#E6E6F4; background:rgba(103,113,175,38); border-color:rgba(136,145,196,66); }}
QLabel#phasePill[phaseState="done"] {{ color:#DCEBF2; background:rgba(65,124,162,38); border-color:rgba(101,151,183,66); }}

QLabel#time {{
    color: {token['text']}; font-family: "Segoe UI", "SF Pro Display", sans-serif;
    font-size: 58px; font-weight: 800; letter-spacing: 1px;
}}

QLabel#status, QLabel#path {{
    color: {token['soft']}; background: {token['accent_soft']};
    border-radius: 11px; padding: 8px 11px; font-size: 11px;
}}

QLabel#cardTitle {{ color: {token['muted']}; font-size: 11px; font-weight: 700; }}
QLabel#cardValue {{ color: {token['text']}; font-size: 18px; font-weight: 800; }}
QLabel#densityValue {{
    color: {token['text']}; background: {token['accent_soft']};
    border: 1px solid {token['border']}; border-radius: 9px;
    padding: 3px 9px; font-size: 11px; font-weight: 750;
}}

QPushButton {{
    min-height: 36px; padding: 0 14px; color: {token['soft']};
    background: {token['card_alt']}; border: 1px solid {token['border']};
    border-radius: 11px; font-weight: 650;
}}
QPushButton:hover {{ color: {token['text']}; border-color: {token['border_focus']}; }}
QPushButton:pressed {{ background: {token['accent_soft']}; }}
QPushButton:disabled {{ color: {token['disabled']}; border-color: {token['border']}; }}

QPushButton#primaryButton {{
    min-height: 44px; color: #F1F7F7;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {token['primary_top']}, stop:1 {token['primary_bottom']});
    border: 1px solid rgba(160, 224, 214, 54);
    border-radius: 13px; font-size: 14px; font-weight: 800;
}}
QPushButton#primaryButton:hover {{ background: {token['accent_hover']}; border-color:rgba(183, 235, 227, 76); }}
QPushButton#primaryButton:pressed {{ background: {token['accent_pressed']}; }}
QPushButton#quietButton {{ color: {token['soft']}; background: transparent; border-color: transparent; }}
QPushButton#quietButton:hover {{ color: {token['text']}; background: {token['accent_soft']}; }}

QPushButton#choiceCard, QPushButton#plantChoiceCard, QPushButton#segmentChoice, QPushButton#outcomeChoice {{
    color: {token['muted']}; background: {token['card_alt']};
    border: 1px solid {token['border']}; border-radius: 13px;
    text-align: left; padding: 9px 12px; font-weight: 650;
}}
QPushButton#choiceCard:checked, QPushButton#plantChoiceCard:checked,
QPushButton#segmentChoice:checked, QPushButton#outcomeChoice:checked {{
    color: {token['text']}; background: {token['accent_soft']};
    border: 2px solid {token['border_focus']};
}}
QPushButton#plantChoiceCard {{ text-align: left; }}
QPushButton#segmentChoice, QPushButton#outcomeChoice {{ text-align: center; min-height: 34px; }}

QPushButton#titleButton {{
    min-width: 34px; max-width: 34px; min-height: 30px; max-height: 30px;
    padding: 0; color: {token['muted']}; background: transparent;
    border: none; border-radius: 9px; font-size: 17px; font-weight: 700;
}}
QPushButton#titleButton:hover {{ color: {token['text']}; background: {token['accent_soft']}; }}
QPushButton#dangerQuietButton {{ color: {token['danger']}; background: transparent; }}

QLineEdit, QTextEdit, QComboBox, QSpinBox {{
    min-height: 36px; padding: 0 10px; color: {token['text']};
    background: {token['input']}; border: 1px solid {token['border']};
    border-radius: 11px; selection-background-color: {token['accent']};
}}
QTextEdit {{ padding: 9px; }}
QLineEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {token['border_focus']}; }}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {token['border_focus']}; }}
QComboBox::drop-down {{ width: 28px; border: none; }}

QCheckBox {{ color: {token['soft']}; spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; }}

QSlider::groove:horizontal {{ height: 4px; background: {token['card_alt']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {token['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; background: {token['text']}; border-radius: 8px; }}

QTabWidget::pane {{ margin-top: 8px; background: transparent; border: none; }}
QTabBar::tab {{
    min-width: 104px; min-height: 36px; margin-right: 5px; padding: 0 12px;
    color: {token['muted']}; background: {token['card_alt']}; border: 1px solid transparent;
    border-radius: 10px;
}}
QTabBar::tab:selected {{ color: {token['text']}; background: {token['accent_soft']}; font-weight: 750; }}

QScrollArea {{ background: transparent; border: none; }}
QProgressBar {{
    border: 1px solid {token['border']}; border-radius: 6px;
    background: {token['card_alt']}; height: 10px; color: {token['soft']};
}}
QProgressBar::chunk {{ background: {token['accent']}; border-radius: 5px; }}
"""


APP_QSS = build_app_qss()
