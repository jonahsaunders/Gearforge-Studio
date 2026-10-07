"""Shared native desktop behavior for engineering document windows."""
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenuBar,
    QPushButton, QScrollArea, QTabWidget, QTableWidget, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)

from .layouts import FlowLayout


def scroll_page(page):
    scroll = QScrollArea()
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setWidgetResizable(True)
    scroll.setWidget(page)
    return scroll


def labeled_control_row(entries):
    """Wrap label/control pairs together, keeping chart selectors compact."""
    row = FlowLayout()
    for title, control in entries:
        pair = QWidget()
        layout = QHBoxLayout(pair)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setBuddy(control)
        control.setAccessibleName(title)
        if isinstance(control, QComboBox):
            control.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(12)
            control.currentTextChanged.connect(control.setToolTip)
            control.setToolTip(control.currentText())
        layout.addWidget(label)
        layout.addWidget(control)
        row.addWidget(pair)
    return row


def add_edit_menu(bar):
    menu = bar.addMenu('Edit')
    entries = [('Undo', 'undo', QKeySequence.Undo), ('Redo', 'redo', QKeySequence.Redo),
               ('Cut', 'cut', QKeySequence.Cut), ('Copy', 'copy', QKeySequence.Copy),
               ('Paste', 'paste', QKeySequence.Paste), ('Select All', 'selectAll', QKeySequence.SelectAll)]
    for title, method, shortcut in entries:
        action = menu.addAction(title)
        action.setShortcut(shortcut)
        def invoke(checked=False, name=method):
            widget = QApplication.focusWidget()
            callback = getattr(widget, name, None)
            if callable(callback):
                callback()
        action.triggered.connect(invoke)
        def refresh(a=action, name=method):
            widget = QApplication.focusWidget()
            enabled = callable(getattr(widget, name, None))
            if name in ('cut', 'paste', 'undo', 'redo') and hasattr(widget, 'isReadOnly'):
                enabled = enabled and not widget.isReadOnly()
            a.setEnabled(enabled)
        menu.aboutToShow.connect(refresh)
    return menu


def accessible_forms(owner):
    """Use real labels, including when enlarged text requires stacked rows."""
    for form in owner.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for row in range(form.rowCount()):
            label = form.itemAt(row, QFormLayout.LabelRole)
            field = form.itemAt(row, QFormLayout.FieldRole)
            if label and field and isinstance(label.widget(), QLabel) and field.widget():
                label.widget().setBuddy(field.widget())
                field.widget().setAccessibleName(label.widget().text())


class StudyTabs(QTabWidget):
    """Keep long forms reachable without increasing the window's minimum size."""
    def addTab(self, page, title):
        page.setAccessibleName(title)
        if not isinstance(page, QAbstractScrollArea):
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            scroll.setAccessibleName(title)
            page = scroll
        index = super().addTab(page, title)
        self.setTabToolTip(index, title)
        self.setUsesScrollButtons(True)
        self.setElideMode(Qt.ElideNone)
        return index

    def indexOf(self, page):
        index = super().indexOf(page)
        if index < 0:
            for i in range(self.count()):
                wrapper = self.widget(i)
                if isinstance(wrapper, QScrollArea) and wrapper.widget() is page:
                    return i
        return index

    def setCurrentWidget(self, page):
        index = self.indexOf(page)
        if index >= 0:
            self.setCurrentIndex(index)


class StudyDialog(QDialog):
    """A resizable study document; short prompts remain modal dialogs."""
    @property
    def dirty(self):
        return getattr(self, '_dirty', False)

    @dirty.setter
    def dirty(self, value):
        self._dirty = bool(value)
        self.update_document_title()

    @property
    def path(self):
        return getattr(self, '_path', None)

    @path.setter
    def path(self, value):
        self._path = Path(value) if value else None
        self.update_document_title()

    def update_document_title(self):
        if not hasattr(self, '_study_title'):
            return
        name = self.path.name if self.path else 'Untitled'
        self.setWindowTitle(f'{name}[*] — {self._study_title}')
        self.setWindowFilePath(str(self.path.resolve()) if self.path else '')
        self.setWindowModified(self.dirty)

    def save_destination(self, title, suggested, file_filter):
        if self.path and not getattr(self, '_saving_as', False):
            return str(self.path), file_filter
        return QFileDialog.getSaveFileName(self, title, suggested, file_filter)

    def save_as(self):
        self._saving_as = True
        try:
            return self.save_study()
        finally:
            self._saving_as = False

    def finish_ui(self):
        """Called after each editor has built its controls and loaded its model."""
        self._study_title = self.windowTitle()
        self.setWindowFlags(Qt.Window)
        self.update_document_title()
        accessible_forms(self)
        # Labels in plot controls and prose editors are often outside forms.
        for layout in self.findChildren(QHBoxLayout) + self.findChildren(QVBoxLayout):
            for i in range(layout.count() - 1):
                label, field = layout.itemAt(i).widget(), layout.itemAt(i + 1).widget()
                if isinstance(label, QLabel) and isinstance(field, (QComboBox, QLineEdit, QTextEdit)):
                    label.setBuddy(field)
                    if not field.accessibleName():
                        field.setAccessibleName(label.text())
        for key, widget in vars(self).items():
            if isinstance(widget, (QComboBox, QLineEdit, QTextEdit, QTableWidget)) and not widget.accessibleName():
                widget.setAccessibleName(key.replace('_', ' ').capitalize())
        for table in self.findChildren(QTableWidget):
            if not table.accessibleName():
                headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount()) if table.horizontalHeaderItem(i)]
                table.setAccessibleName('Data table: ' + ', '.join(headers))
            table.setAlternatingRowColors(True)
        self.status.setAccessibleName('Study status')
        self.tabs.setAccessibleName('Study sections')
        for browser in self.findChildren(QTextBrowser):
            browser.setOpenExternalLinks(False)
        # Keep native controls and their existing callbacks/worker enable state.
        # Consolidate only document-level action rows, never table edit controls.
        outer = self.layout()
        buttons = []
        for i in range(outer.count() - 1, -1, -1):
            row = outer.itemAt(i).layout()
            if not isinstance(row, QHBoxLayout):
                continue
            items = [row.itemAt(j) for j in range(row.count())]
            if not items or any(item.widget() and not isinstance(item.widget(), QPushButton) or item.layout() for item in items):
                continue
            row_buttons = [item.widget() for item in items if item.widget()]
            if not row_buttons:
                continue
            buttons[0:0] = row_buttons
            while row.count():
                row.takeAt(0)
            outer.takeAt(i)
            row.deleteLater()
        self.document_buttons = {}
        secondary = QWidget()
        flow = FlowLayout(secondary)
        self.button_box = QDialogButtonBox()
        close = None
        for button in buttons:
            text = button.text()
            button.setAutoDefault(False)
            button.setDefault(False)
            if text == 'Close':
                close = button
                continue
            if text.startswith('Open'):
                button.setText('Open…'); key = 'open'
            elif text.startswith('Save'):
                button.setText('Save'); key = 'save'
            elif text.startswith('Export'):
                button.setText('Export…'); key = 'export'
            elif text == 'Calculate':
                key = 'calculate'
            else:
                key = text
            self.document_buttons[key] = button
            if key == 'calculate' or text == 'Cancel calculation':
                self.button_box.addButton(button, QDialogButtonBox.ActionRole)
            else:
                flow.addWidget(button)
        if close is None:
            close = QPushButton('Close')
            close.clicked.connect(self.reject)
        self.button_box.addButton(close, QDialogButtonBox.RejectRole)
        close.setAutoDefault(False)
        outer.addWidget(secondary)
        outer.addWidget(self.button_box)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self._document_menus()
        self.setMinimumSize(720, 520)

    def _document_menus(self):
        bar = QMenuBar(self)
        self.layout().setMenuBar(bar)
        file = bar.addMenu('File')
        add_edit_menu(bar)
        study = bar.addMenu('Study')
        self.document_actions = {}
        self._button_actions = {}
        for key, title, shortcut in [('open', 'Open…', QKeySequence.Open), ('save', 'Save', QKeySequence.Save),
                                      ('save_as', 'Save As…', QKeySequence.SaveAs), ('export', 'Export…', 'Ctrl+Shift+E')]:
            if key != 'save_as' and key not in self.document_buttons:
                continue
            action = file.addAction(title)
            action.setShortcut(shortcut)
            if key == 'save_as':
                action.triggered.connect(self.save_as)
                button = self.document_buttons['save']
            else:
                button = self.document_buttons[key]
                action.triggered.connect(button.click)
            self.document_actions[key] = action
            self._button_actions.setdefault(button, []).append(action)
        file.addSeparator()
        close = file.addAction('Close Window')
        close.setShortcut(QKeySequence.Close)
        close.triggered.connect(self.close)
        self.document_actions['close'] = close
        owner = self.parentWidget()
        while isinstance(owner, StudyDialog):
            owner = owner.parentWidget()
        quit_action = file.addAction('Quit')
        quit_action.setMenuRole(QAction.QuitRole)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(owner.close if owner else self.close)
        for key, button in self.document_buttons.items():
            if key in ('open', 'save', 'export'):
                continue
            action = study.addAction(button.text())
            action.triggered.connect(button.click)
            if key == 'calculate':
                action.setShortcut('Ctrl+Return')
            self.document_actions[key] = action
            self._button_actions.setdefault(button, []).append(action)
        for button, actions in self._button_actions.items():
            button.installEventFilter(self)
            for action in actions:
                action.setEnabled(button.isEnabled())
        window = bar.addMenu('Window')
        minimize = window.addAction('Minimize')
        minimize.setShortcut('Ctrl+M')
        minimize.triggered.connect(self.showMinimized)
        fullscreen = window.addAction('Toggle Full Screen')
        fullscreen.setShortcut(QKeySequence.FullScreen)
        fullscreen.triggered.connect(lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen())

    def eventFilter(self, watched, event):
        if event.type() == QEvent.EnabledChange:
            for action in getattr(self, '_button_actions', {}).get(watched, []):
                action.setEnabled(watched.isEnabled())
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_fitted_to_screen', False):
            self._fitted_to_screen = True
            available = self.screen().availableGeometry()
            self.resize(min(self.width(), available.width() - 40), min(self.height(), available.height() - 60))

    def present(self):
        """Retain independent documents at the main window, not a modal parent."""
        owner = self.parentWidget()
        while isinstance(owner, StudyDialog):
            owner = owner.parentWidget()
        self.setParent(owner, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowModality(Qt.NonModal)
        self.show()
        self.raise_()
        self.activateWindow()
        return self


def close_studies(owner):
    """Route quit through every document's existing save/cancel guard."""
    studies = [w for w in QApplication.topLevelWidgets() if isinstance(w, StudyDialog) and w.parentWidget() is owner and w.isVisible()]
    for study in studies:
        if not study.close():
            study.raise_()
            study.activateWindow()
            return False
    return True
