"""Behavioral checks for the shared desktop UI, not a macOS certification."""
import importlib
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton

CASES = [
    ('engineering', 'EngineeringStudyDialog', 'EngineeringStudy', 'steel-spur-250w.gearforge-study'),
    ('shaft', 'ShaftStudyDialog', 'ShaftStudy', 'steel-spur-input.gearforge-shaft'),
    ('bearing', 'BearingStudyDialog', 'BearingStudy', 'steel-spur-synthetic.gearforge-bearing'),
    ('fatigue', 'FatigueStudyDialog', 'FatigueStudy', 'nasa-shaft-fatigue.gearforge-fatigue'),
    ('contact', 'ContactStudyDialog', 'ContactStudy', 'synthetic-contact.gearforge-contact'),
    ('thermal', 'ThermalStudyDialog', 'ThermalStudy', 'synthetic-thermal.gearforge-thermal'),
    ('tooth', 'ToothProfileDialog', 'ToothProfileStudy', 'synthetic-tooth.gearforge-tooth'),
    ('root', 'RootStressDialog', 'RootStressStudy', 'synthetic-root.gearforge-root'),
    ('cyclic', 'HistoryStudyDialog', 'HistoryStudy', 'synthetic-history.gearforge-history'),
]
pytestmark = pytest.mark.gui


@pytest.fixture
def app():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


@pytest.fixture(params=CASES, ids=[row[0] for row in CASES])
def editor(request, app):
    module, dialog_name, study_name, example = request.param
    ui = importlib.import_module('gearforge.' + module + '_ui')
    window = getattr(ui, dialog_name)()
    model = getattr(ui, study_name).load(Path(__file__).parents[1] / 'examples' / example)
    window.set_study(model)
    yield window, model, example
    window.dirty = False
    window.close()
    window.deleteLater()


def test_every_editor_saves_current_document_and_preserves_cancelled_save_as(editor, app, tmp_path, monkeypatch):
    window, model, example = editor
    destination = tmp_path / example
    model.save(destination)
    window.path = destination
    name = window.name if hasattr(window, 'name') else window.basis_fields['name']
    if hasattr(name, 'setPlainText'): name.setPlainText('Edited document')
    else: name.setText('Edited document')
    window.changed()
    assert window.dirty and window.isWindowModified()
    dialogs = []
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (dialogs.append(args) or ('', '')))
    assert window.save_study()
    assert not dialogs, 'Save must not prompt for the destination of an existing document'
    assert type(model).load(destination).name == 'Edited document'
    assert not window.dirty and not window.isWindowModified()
    assert window.windowFilePath() == str(destination.resolve())
    window.dirty = True
    assert not window.save_as()
    assert window.path == destination and window.dirty
    assert len(dialogs) == 1
    replacement = tmp_path / ('copy' + destination.suffix)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: (str(replacement), ''))
    assert window.save_as()
    assert window.path == replacement and replacement.is_file()
    errors = []
    window.show_error = lambda error: errors.append(str(error))
    window.dirty = True
    def failed_save(*args):
        raise OSError('Disk full')
    monkeypatch.setattr(type(model), 'save', failed_save)
    assert not window.save_study()
    assert window.path == replacement and window.dirty and errors == ['Disk full']


def test_every_editor_large_text_pages_and_return_key(editor, app):
    window, _, _ = editor
    font = QFont(window.font())
    font.setPointSizeF(14.3)
    window.setFont(font)
    window.show()
    window.resize(1024, 768)
    triggered = []
    for key, button in window.document_buttons.items():
        button.clicked.connect(lambda checked=False, key=key: triggered.append(key))
    name = window.name if hasattr(window, 'name') else window.basis_fields['name']
    name.setFocus()
    QTest.keyClick(name, Qt.Key_Return)
    app.processEvents()
    assert not triggered, 'Return in an input must not trigger an unrelated document command'
    assert window.isVisible()
    assert all(not b.autoDefault() for b in window.findChildren(QPushButton))
    assert name.accessibleName() == 'Study name'
    for i in range(window.tabs.count()):
        window.tabs.setCurrentIndex(i)
        app.processEvents()
        assert not window.grab().isNull()
        assert window.size().width() <= 1024
        for button in window.document_buttons.values():
            assert window.rect().contains(button.mapTo(window, QPoint(0, 0)))
            assert window.rect().contains(button.mapTo(window, button.rect().bottomRight()))


def test_independent_studies_keep_parent_available_and_block_quit_if_unsaved(app, tmp_path):
    from gearforge.app import MainWindow
    from gearforge.engineering_ui import EngineeringStudyDialog
    from gearforge.tooth_ui import ToothProfileDialog
    main = MainWindow(tmp_path)
    main.show()
    first = EngineeringStudyDialog(main).present()
    second = ToothProfileDialog(first).present()
    app.processEvents()
    assert QApplication.activeModalWidget() is None
    assert main.isEnabled() and first.isEnabled()
    assert second.parentWidget() is main
    second.dirty = True
    second.confirm_discard = lambda: False
    assert not main.close()
    assert main.isVisible() and second.isVisible()
    assert main.catalog.rows()
    second.confirm_discard = lambda: True
    assert main.close()
    app.processEvents()


def test_worker_commands_follow_disabled_buttons(app):
    from gearforge.root_ui import RootStressDialog
    window = RootStressDialog()
    window.set_busy(True)
    for key in ('open', 'save', 'save_as', 'calculate', 'export'):
        assert not window.document_actions[key].isEnabled()
    assert window.document_actions['Cancel calculation'].isEnabled()
    window.set_busy(False)
    assert window.document_actions['save_as'].isEnabled()
    assert not window.document_actions['Cancel calculation'].isEnabled()
    window.close()


@pytest.mark.parametrize('base,text', [('#ffffff', '#202124'), ('#28292d', '#f3f4f6')])
def test_custom_series_colors_remain_legible(app, base, text):
    from gearforge.chart_style import ChartWidget, chart_color, contrast
    widget = ChartWidget()
    palette = QPalette()
    palette.setColor(QPalette.Base, QColor(base))
    palette.setColor(QPalette.Text, QColor(text))
    widget.setPalette(palette)
    for color in ('#3478db', '#b85a15', '#475569', '#2563eb', '#bc4a0b', '#15803d', '#166a5e', '#79a2ee'):
        assert contrast(chart_color(widget, color), QColor(base)) >= 4.5


def test_report_appearance_updates_without_changing_results_or_reviving_cleared_report(app):
    from gearforge.chart_style import ReportBrowser
    browser = ReportBrowser()
    source = '<style>body{color:#172033;font:15px sans-serif}</style><h2>Result</h2><table><tr><td>42 MPa</td></tr></table>'
    browser.setHtml(source)
    original = browser.toPlainText()
    palette = browser.palette()
    palette.setColor(QPalette.Base, QColor('#28292d'))
    palette.setColor(QPalette.Text, QColor('#f3f4f6'))
    browser.setPalette(palette)
    browser.setFont(QFont(browser.font().family(), 15))
    app.processEvents()
    assert browser.toPlainText() == original
    assert '#f3f4f6' in browser.document().defaultStyleSheet()
    assert browser.document().defaultFont().pointSize() == 15
    browser.clear()
    browser.setPalette(QPalette())
    assert not browser.toPlainText()


def test_main_adapts_to_narrow_workspace_and_retains_keyboard_focus(app, tmp_path):
    from gearforge.app import MainWindow
    main = MainWindow(tmp_path)
    main.show()
    main.resize(1024, 768)
    app.processEvents()
    for _ in range(5):app.processEvents()
    assert main.design_splitter.orientation() == Qt.Vertical
    assert main.pages.widget(0).horizontalScrollBar().maximum() == 0
    main.viewer.setFocus()
    app.processEvents()
    before = main.viewer.yaw
    QTest.keyClick(main.viewer, Qt.Key_Right)
    assert main.viewer.yaw > before
    assert main.viewer.hasFocus()
    main.dirty = False
    main.close()
    reopened = MainWindow(tmp_path)
    reopened.show()
    reopened.resize(1024,768)
    for _ in range(5):app.processEvents()
    assert reopened.design_splitter.orientation() == Qt.Vertical
    assert reopened.requirements_scroll.maximumWidth() > 440
    reopened.dirty = False
    reopened.close()
