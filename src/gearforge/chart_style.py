"""Readable custom charts and reports that follow the native app palette."""
import re

from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTextBrowser, QWidget


def contrast(first, second):
    def luminance(color):
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                  for v in (color.redF(), color.greenF(), color.blueF())]
        return sum(v * weight for v, weight in zip(values, (.2126, .7152, .0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + .05) / (a + .05)


def chart_color(widget, value):
    """Preserve each series' hue while maintaining contrast with its surface."""
    color = QColor(value)
    background = widget.palette().base().color()
    target = widget.palette().text().color()
    original = QColor(color)
    for step in range(21):
        if contrast(color, background) >= 4.5:
            break
        blend = (step + 1) / 21
        color = QColor.fromRgbF(*[a * (1 - blend) + b * blend for a, b in zip(
            (original.redF(), original.greenF(), original.blueF()),
            (target.redF(), target.greenF(), target.blueF()))])
    return color


class ChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleDescription('Use the assessment or calculation report and exported data for numerical values. Color alone does not establish qualification.')

    def showEvent(self, event):
        self.update_text_space()
        super().showEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.FontChange:
            self.update_text_space()
        if event.type() in (QEvent.FontChange, QEvent.PaletteChange):
            self.update()
        super().changeEvent(event)

    def update_text_space(self):
        # Scrollable study pages retain readable captions on narrow displays.
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance('M') * 70)


class ReportBrowser(QTextBrowser):
    """Style the in-app report independently of its printable HTML export."""
    def setHtml(self, source):
        self._report_source = source
        self._render_report()

    def _render_report(self):
        # Report producers own their HTML. Remove only their presentation CSS;
        # leave headings, tables, links, emphasis and all calculation text intact.
        source = re.sub(r'<style\b[^>]*>.*?</style>', '', self._report_source,
                        flags=re.IGNORECASE | re.DOTALL)
        palette = self.palette()
        text, base = palette.text().color().name(), palette.base().color().name()
        rule = palette.mid().color().name()
        self.document().setDefaultFont(self.font())
        self.document().setDefaultStyleSheet(
            f'body {{color:{text}; background-color:{base}}}'
            'table {border-collapse:collapse} td, th {padding:6px;'
            f'border:1px solid {rule}}} th {{background-color:{palette.alternateBase().color().name()}}}'
            'pre {white-space:pre-wrap} h1 {font-size:150%} h2 {font-size:125%}'
        )
        super().setHtml(source)

    def setPlainText(self, text):
        self._report_source = None
        super().setPlainText(text)

    def clear(self):
        self._report_source = None
        super().clear()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.PaletteChange, QEvent.FontChange) and getattr(self, '_report_source', None):
            scroll = self.verticalScrollBar().value()
            self._render_report()
            self.verticalScrollBar().setValue(scroll)
