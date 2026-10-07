"""Desktop editor for auditable geometry and operating-duty studies."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QHeaderView,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTabWidget, QInputDialog,
    QTableWidget, QTableWidgetItem, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from .chart_style import ReportBrowser

from .desktop_ui import StudyDialog, StudyTabs

from .engineering import DutyPoint, EngineeringStudy, GearPair, calculate_study, export_study, study_html


class StudyNumber(QDoubleSpinBox):
    """Keep calculation precision without padding the editor with zeroes."""
    def textFromValue(self, value):
        text = super().textFromValue(value)
        decimal = self.locale().decimalPoint()
        return text.rstrip("0").removesuffix(decimal) if decimal in text else text


class EngineeringStudyDialog(StudyDialog):
    DUTY_FIELDS = ("name", "input_rpm", "input_torque_nm", "duration_hours", "ambient_c", "starts")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize(1120, 820)
        self.setWindowTitle("Engineering study")
        self.path = None
        self.result = None
        self.dirty = False
        self._loading = True
        self.fields = {}
        self.pair_fields = {}
        layout = QVBoxLayout(self)
        note = QLabel("Spur/helical geometry and operating loads. Fatigue, material allowables and production approval are not yet established.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = StudyTabs()
        layout.addWidget(self.tabs, 1)
        inputs = QWidget(); input_layout = QVBoxLayout(inputs)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        container = QWidget(); form = QFormLayout(container)
        self.name = QLineEdit(); form.addRow("Study name", self.name)
        self.name.textEdited.connect(self.changed)
        for key, label, lower, upper, integer, suffix in (
            ("normal_module_mm", "Normal module", .1, 50, False, " mm"),
            ("pinion_teeth", "Pinion teeth", 6, 1000, True, ""),
            ("wheel_teeth", "Wheel teeth", 6, 1000, True, ""),
            ("normal_pressure_angle_deg", "Normal pressure angle", 14, 30, False, "°"),
            ("pinion_helix_angle_deg", "Pinion helix (+ right / − left)", -45, 45, False, "°"),
            ("pinion_profile_shift", "Pinion normal profile shift", -1, 1.5, False, ""),
            ("wheel_profile_shift", "Wheel normal profile shift", -1, 1.5, False, ""),
            ("face_width_mm", "Common face width", .1, 1000, False, " mm"),
        ):
            self.pair_fields[key] = self.number(form, label, lower, upper, integer, suffix)
        for key, label, lower, upper, suffix in (
            ("target_life_hours", "Target operating life", .000001, 1000000, " h"),
            ("ambient_min_c", "Minimum ambient temperature", -80, 200, " °C"),
            ("ambient_max_c", "Maximum ambient temperature", -80, 200, " °C"),
            ("assumed_efficiency", "Assumed efficiency (0–1)", .01, 1, ""),
        ):
            self.fields[key] = self.number(form, label, lower, upper, False, suffix)
        hint = QLabel("The mating wheel has the opposite helix hand. Profile shifts affect operating center distance and tooth dimensions. Efficiency is an assumption; it does not establish thermal capacity.")
        hint.setWordWrap(True); form.addRow(hint)
        scroll.setWidget(container); input_layout.addWidget(scroll)
        self.tabs.addTab(inputs, "Geometry and targets")

        duty_page = QWidget(); duty_layout = QVBoxLayout(duty_page)
        note = QLabel("Allocate the target life across operating cases. Use matching negative speed and torque for reverse motoring. Zero speed records a stationary load; starts are recorded but not fatigue-rated.")
        note.setWordWrap(True); duty_layout.addWidget(note)
        self.duty_table = QTableWidget(0, len(self.DUTY_FIELDS))
        self.duty_table.setHorizontalHeaderLabels(["Case", "Input rpm", "Input N·m", "Hours", "Ambient °C", "Starts"])
        self.duty_table.setAccessibleName("Operating duty cases")
        self.duty_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.duty_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.duty_table.cellChanged.connect(self.changed)
        duty_layout.addWidget(self.duty_table, 1)
        buttons = QHBoxLayout()
        add = QPushButton("Add case"); add.clicked.connect(self.add_case); buttons.addWidget(add)
        remove = QPushButton("Remove selected case"); remove.clicked.connect(self.remove_case); buttons.addWidget(remove)
        buttons.addStretch(); duty_layout.addLayout(buttons)
        self.tabs.addTab(duty_page, "Operating duty")

        context = QWidget(); context_form = QFormLayout(context)
        for key, label in (("material_process", "Material and manufacturing"), ("lubrication", "Lubrication"),
                           ("standard_basis", "Calculation methods and revisions"), ("evidence_references", "Evidence references"), ("notes", "Study notes")):
            widget = QTextEdit(); widget.setAcceptRichText(False); widget.setMaximumHeight(105)
            widget.textChanged.connect(self.changed); context_form.addRow(label, widget); self.fields[key] = widget
        warning = QLabel("Record source documents and their revisions. Entering a reference does not verify its contents or approve a rating.")
        warning.setWordWrap(True); context_form.addRow(warning)
        self.tabs.addTab(context, "Materials and evidence")
        self.report = ReportBrowser(); self.report.setOpenExternalLinks(False)
        self.tabs.addTab(self.report, "Calculation")
        self.status = QLabel(); self.status.setWordWrap(True); layout.addWidget(self.status)
        actions = QHBoxLayout()
        for label, callback in (("Open study…", self.open_study), ("Save study…", self.save_study),
                                ("Calculate", self.calculate), ("Export calculation…", self.export), ("Close", self.reject)):
            button = QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
        layout.addLayout(actions)
        studies = QHBoxLayout()
        for label, callback in (("Study shaft loads…", self.study_shaft), ("Study tooth contact…", self.study_contact),
                                ("Study temperatures…", self.study_thermal), ("Study tooth roots…", self.study_tooth),
                                ("Study stress history…", self.study_history)):
            button = QPushButton(label); button.clicked.connect(callback); studies.addWidget(button)
        layout.addLayout(studies)
        for row_form in (form, context_form):
            for row in range(row_form.rowCount()):
                label_item = row_form.itemAt(row, QFormLayout.LabelRole)
                field_item = row_form.itemAt(row, QFormLayout.FieldRole)
                if label_item and field_item:
                    label_item.widget().setBuddy(field_item.widget())
                    field_item.widget().setAccessibleName(label_item.widget().text())
        self.set_study(EngineeringStudy())
        self.finish_ui()


    def number(self, form, label, lower, upper, integer, suffix):
        widget = QSpinBox() if integer else StudyNumber()
        if not integer:widget.setDecimals(10)
        widget.setRange(lower, upper); widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        widget.valueChanged.connect(self.changed); form.addRow(label, widget)
        return widget

    def changed(self, *_):
        if self._loading:return
        self.dirty = True
        self.result = None
        self.report.clear()
        self.status.setText("Inputs changed. Calculate again to obtain current results.")

    def set_study(self, study):
        study.validate()
        self._loading = True
        try:
            self.name.setText(study.name)
            for key, widget in self.pair_fields.items():widget.setValue(getattr(study.pair, key))
            for key, widget in self.fields.items():
                value = getattr(study, key)
                if isinstance(widget, QTextEdit):widget.setPlainText(value)
                else:widget.setValue(value)
            self.duty_table.setRowCount(0)
            for point in study.duty:self.add_case(point)
            self.duty_table.resizeColumnsToContents()
            self.result = None; self.report.clear(); self.dirty = False
            self.status.setText("Ready to calculate geometry and loads. No production rating is available.")
        finally:self._loading = False

    def add_case(self, point=None):
        if not isinstance(point, DutyPoint):
            point = DutyPoint(name=f"Case {self.duty_table.rowCount()+1}", duration_hours=1)
        row = self.duty_table.rowCount(); self.duty_table.insertRow(row)
        for column, key in enumerate(self.DUTY_FIELDS):
            self.duty_table.setItem(row, column, QTableWidgetItem(str(getattr(point, key))))
        self.changed()

    def remove_case(self):
        if self.duty_table.currentRow() >= 0:
            self.duty_table.removeRow(self.duty_table.currentRow()); self.changed()

    def read_study(self):
        duty = []
        for row in range(self.duty_table.rowCount()):
            values = {}
            for column, key in enumerate(self.DUTY_FIELDS):
                item = self.duty_table.item(row, column)
                if item is None:raise ValueError(f"Incomplete duty row {row+1}")
                value = item.text().strip()
                values[key] = value if key == "name" else int(value) if key == "starts" else float(value)
            duty.append(DutyPoint(**values))
        data = {key: widget.toPlainText() if isinstance(widget, QTextEdit) else widget.value()
                for key, widget in self.fields.items()}
        study = EngineeringStudy(name=self.name.text(), pair=GearPair(**{key: w.value() for key, w in self.pair_fields.items()}), duty=duty, **data)
        study.validate()
        return study

    def calculate(self):
        try:
            self.result = calculate_study(self.read_study())
            self.report.setHtml(study_html(self.result)); self.tabs.setCurrentWidget(self.report)
            count = len(self.result["geometry"]["issues"])
            self.status.setText(f"Calculation complete · {count} geometry findings · production rating unavailable")
            return True
        except (ValueError, TypeError, OverflowError) as exc:
            self.result = None; self.report.clear(); self.show_error(exc); return False

    def study_history(self):
        from .cyclic import history_from_study
        from .cyclic_ui import HistoryStudyDialog
        try:study=history_from_study(self.read_study())
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        dialog=HistoryStudyDialog(self,study);dialog.dirty=True;dialog.present();return True

    def study_tooth(self):
        from .tooth_profile import profile_from_study
        from .tooth_ui import ToothProfileDialog
        try:study=profile_from_study(self.read_study())
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        dialog=ToothProfileDialog(self,study);dialog.dirty=True;dialog.present();return True

    def study_contact(self):
        from .contact import contact_from_study
        from .contact_ui import ContactStudyDialog
        try:study=contact_from_study(self.read_study())
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        dialog=ContactStudyDialog(self,study);dialog.dirty=True;dialog.present();return True

    def study_thermal(self):
        from .thermal import thermal_from_study
        from .thermal_ui import ThermalStudyDialog
        try:study=thermal_from_study(self.read_study())
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        dialog=ThermalStudyDialog(self,study);dialog.dirty=True;dialog.present();return True

    def study_shaft(self):
        from .shafts import shaft_from_gear_study
        from .shaft_ui import ShaftStudyDialog
        try:source=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        role,ok=QInputDialog.getItem(self,"Study shaft loads","Choose the shaft; all duty cases will be transferred.",["Pinion","Wheel"],0,False)
        if not ok:return False
        try:study=shaft_from_gear_study(source,role.lower())
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        dialog=ShaftStudyDialog(self,study);dialog.dirty=True;dialog.present();return True

    def show_error(self, error):
        QMessageBox.warning(self, "Engineering study", str(error))

    def confirm_discard(self):
        if not self.dirty:return True
        answer = QMessageBox.question(self, "Unsaved engineering study", "Save the engineering study before continuing?",
                                      QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:return self.save_study()
        return answer == QMessageBox.Discard

    def save_study(self):
        try:study = self.read_study()
        except (ValueError, TypeError) as exc:self.show_error(exc); return False
        path, _ = self.save_destination("Save engineering study", str(self.path or "gearbox.gearforge-study"), "Engineering study (*.gearforge-study)")
        if not path:return False
        try:study.save(Path(path))
        except (ValueError, OSError) as exc:self.show_error(exc); return False
        self.path = Path(path); self.dirty = False
        self.status.setText(f"Saved {self.path.name}")
        return True

    def open_study(self):
        if not self.confirm_discard():return False
        path, _ = QFileDialog.getOpenFileName(self, "Open engineering study", "", "Engineering study (*.gearforge-study)")
        if not path:return False
        try:study = EngineeringStudy.load(Path(path))
        except (ValueError, OSError, TypeError) as exc:self.show_error(exc); return False
        self.set_study(study); self.path = Path(path)
        return True

    def export(self):
        try:study = self.read_study(); calculate_study(study)
        except (ValueError, TypeError, OverflowError) as exc:self.show_error(exc); return False
        path, _ = QFileDialog.getSaveFileName(self, "Choose a new calculation folder", "engineering-calculation", "Folder name (*)")
        if not path:return False
        try:result = export_study(study, Path(path))
        except (ValueError, OSError) as exc:self.show_error(exc); return False
        self.status.setText(f"Exported {result['files']} calculation files with an integrity manifest; no production rating")
        return True

    def reject(self):
        if self.confirm_discard():super().reject()

    def closeEvent(self, event):
        if self.confirm_discard():
            self.dirty = False
            super().closeEvent(event)
        else:event.ignore()
