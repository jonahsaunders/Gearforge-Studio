"""Keep desktop controls native; customize semantic headings, not control skins."""
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

STYLE = """
QLabel#brand { font-size:17pt; font-weight:600; }
QLabel#title { font-size:19pt; font-weight:600; }
QLabel#eyebrow { font-weight:600; }
QLabel#metricValue { font-size:17pt; font-weight:600; }
QFrame#card { border:1px solid palette(mid); border-radius:6px; }
QListWidget#nav::item { padding:12px 8px; }
QTableWidget::item { padding:4px; }
"""


def system_reduced_motion():
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(["/usr/bin/defaults","read","com.apple.universalaccess","reduceMotion"],capture_output=True,text=True,timeout=1)
        return result.returncode == 0 and result.stdout.strip() in ("1","true")
    except (OSError, subprocess.TimeoutExpired):
        return False


def apply_appearance(settings):
    app = QApplication.instance()
    if not hasattr(app,"gearforge_base_font"):
        app.gearforge_base_font = QFont(app.font())
        app.gearforge_system_palette = QPalette(app.palette())
    preference = settings.value("appearance","system")
    schemes = {"system":Qt.ColorScheme.Unknown,"light":Qt.ColorScheme.Light,"dark":Qt.ColorScheme.Dark}
    app.styleHints().setColorScheme(schemes.get(preference,Qt.ColorScheme.Unknown))
    palette = QPalette(app.gearforge_system_palette)
    # macOS's platform theme owns native controls and responds to color scheme.
    if sys.platform != "darwin" and preference in ("light","dark"):
        dark = preference == "dark"
        colors = {QPalette.Window:"#202124" if dark else "#f5f5f7",
                  QPalette.WindowText:"#f3f4f6" if dark else "#202124",
                  QPalette.Base:"#28292d" if dark else "#ffffff",
                  QPalette.AlternateBase:"#323338" if dark else "#eef0f3",
                  QPalette.Text:"#f3f4f6" if dark else "#202124",
                  QPalette.Button:"#323338" if dark else "#e9ebef",
                  QPalette.ButtonText:"#f3f4f6" if dark else "#202124",
                  QPalette.Highlight:"#2868cc",QPalette.HighlightedText:"#ffffff",
                  QPalette.ToolTipBase:"#28292d" if dark else "#ffffff",
                  QPalette.ToolTipText:"#f3f4f6" if dark else "#202124"}
        for role,color in colors.items():palette.setColor(role,QColor(color))
        for role in (QPalette.Text,QPalette.ButtonText,QPalette.WindowText):
            palette.setColor(QPalette.Disabled,role,QColor("#999ca5" if dark else "#656a75"))
    if sys.platform != "darwin":app.setPalette(palette)
    font = QFont(app.gearforge_base_font)
    font.setPointSizeF(max(11.,font.pointSizeF())*float(settings.value("text_scale",1.)))
    app.setFont(font)
    scale=float(settings.value("text_scale",1.))
    stylesheet=STYLE
    for points in (17,19):stylesheet=stylesheet.replace(f"{points}pt",f"{points*scale:g}pt")
    app.setStyleSheet(stylesheet)
