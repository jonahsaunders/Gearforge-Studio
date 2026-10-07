"""Traceable material, critical-section and loading inputs for shaft fatigue."""
from dataclasses import asdict
import html
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,
    QLabel,QLineEdit,QMessageBox,QPushButton,QScrollArea,QTabWidget,QTableWidget,QTableWidgetItem,
    QTextBrowser,QTextEdit,QVBoxLayout,QWidget)

from .chart_style import ReportBrowser

from .desktop_ui import StudyDialog, StudyTabs

from .fatigue import (FatigueMaterial,FatigueStation,FatigueCase,FatigueStudy,fatigue_from_shaft,
    nasa_example,calculate_fatigue_study,fatigue_report_html,export_fatigue_study)
from .shafts import ShaftStudy


class FatigueStudyDialog(StudyDialog):
    NUMBERS={"yield_strength_mpa":"Yield strength at operating conditions (MPa)",
        "fatigue_coefficient_mpa":"Stress–life coefficient at one cycle (MPa)",
        "reference_strength_mpa":"Uncorrected reference fatigue strength (MPa)",
        "reference_cycles":"Cycles at reference fatigue strength",
        "minimum_cycles":"Minimum supported finite-life cycles (at least 1,000)",
        "maximum_cycles":"Maximum supported finite-life cycles",
        "minimum_temperature_c":"Minimum material operating temperature (°C)",
        "maximum_temperature_c":"Maximum material operating temperature (°C)"}
    STATION_FIELDS=("name","position_mm","side","fatigue_reduction_factor","static_bending_kt","static_torsion_kt","static_axial_kt","factor_basis")

    def __init__(self,parent=None,study=None):
        super().__init__(parent);self.resize(1280,880);self.setWindowTitle("Shaft fatigue and material evidence")
        self.path=None;self.result=None;self.dirty=False;self._loading=True
        layout=QVBoxLayout(self)
        note=QLabel("Assess selected solid-shaft sections under rotating bending and steady torque. Material evidence and application factors stay explicit. Rotation-block damage does not establish gearbox service life.")
        note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();layout.addLayout(form)
        self.name=QLineEdit();self.name.textEdited.connect(self.changed);form.addRow("Study name",self.name)
        self.numbers={}
        for key,label,lo,hi in (("required_hours","Required repeated-duty duration (h)",.000001,2e8),
            ("bending_design_factor","Alternating bending design factor",1,100),("static_design_factor","Static design factor",1,100)):
            widget=QLineEdit();widget.setAccessibleName(label);widget.textEdited.connect(self.changed)
            self.numbers[key]=widget;form.addRow(label,widget)
        self.tabs=StudyTabs();layout.addWidget(self.tabs,1)
        scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();form=QFormLayout(page);scroll.setWidget(page)
        self.material={}
        for key,label in {"designation":"Exact material and condition",**self.NUMBERS}.items():
            widget=QLineEdit();widget.textEdited.connect(self.changed);widget.setAccessibleName(label)
            if key in self.NUMBERS:widget.setPlaceholderText("Unknown — enter applicable evidence")
            self.material[key]=widget;form.addRow(label,widget)
        status=QComboBox()
        for label,value in (("Unverified / incomplete","unverified"),("Synthetic example","synthetic"),("Published numerical example","reference_example"),("Declared source data","declared")):status.addItem(label,value)
        status.currentIndexChanged.connect(self.changed);self.material["data_status"]=status;form.addRow("Input provenance",status)
        for key,label in (("source_reference","Source, revision and exact location"),("applicable_conditions","Heat treatment, surface, test conditions and survival basis"),("redistribution_basis","Rights / redistribution basis")):
            widget=QTextEdit();widget.setAcceptRichText(False);widget.setMinimumHeight(65);widget.setMaximumHeight(100)
            widget.textChanged.connect(self.changed);self.material[key]=widget;form.addRow(label,widget)
        self.tabs.addTab(scroll,"Material evidence")
        page=QWidget();sections=QVBoxLayout(page)
        hint=QLabel("Choose each critical X position and its left or right cut. Enter the combined fatigue strength reduction (0–1), including notch/surface/size effects. Static Kt factors apply separately. A midpoint placeholder is not a complete shaft assessment.")
        hint.setWordWrap(True);sections.addWidget(hint)
        self.stations=self.table(["Section","X mm","Cut side","Fatigue reduction","Static Kt bending","Static Kt torsion","Static Kt axial","Factor evidence"])
        sections.addWidget(self.stations,1);buttons=QHBoxLayout();sections.addLayout(buttons)
        for label,callback in (("Add section",self.add_station),("Remove selected section",self.remove_station)):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        self.tabs.addTab(page,"Critical sections")
        page=QWidget();cases=QVBoxLayout(page)
        hint=QLabel("Fixed bending means the force direction is fixed in the housing while the shaft rotates. Shaft temperature needs its own evidence. Starts, stops, oscillation and torsional reversals are not counted from shaft revolutions.")
        hint.setWordWrap(True);cases.addWidget(hint)
        self.cases=self.table(["Retained case","Shaft rpm","Hours","Within-block load model","Shaft °C","Load-model evidence"])
        cases.addWidget(self.cases,1);self.tabs.addTab(page,"Duty conditions")
        page=QWidget();source_layout=QVBoxLayout(page);self.source=ReportBrowser();source_layout.addWidget(self.source,1)
        self.coverage=QTextEdit();self.coverage.setAcceptRichText(False);self.coverage.setMaximumHeight(90);self.coverage.textChanged.connect(self.changed)
        source_layout.addWidget(QLabel("Duty coverage and omitted transients"));source_layout.addWidget(self.coverage)
        self.notes=QTextEdit();self.notes.setAcceptRichText(False);self.notes.setMaximumHeight(90);self.notes.textChanged.connect(self.changed)
        source_layout.addWidget(QLabel("Study notes"));source_layout.addWidget(self.notes);self.tabs.addTab(page,"Shaft and provenance")
        self.report=ReportBrowser();self.report.setOpenExternalLinks(False);self.tabs.addTab(self.report,"Assessment")
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in (("Open study…",self.open_study),("New from shaft…",self.open_shaft),("Worked example",self.load_example),
            ("Save study…",self.save_study),("Calculate",self.calculate),("Export assessment…",self.export),("Close",self.reject)):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        self.set_study(study or FatigueStudy())
        self.finish_ui()


    def table(self,headers):
        widget=QTableWidget(0,len(headers));widget.setHorizontalHeaderLabels(headers);widget.setAlternatingRowColors(True)
        widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);widget.horizontalHeader().setStretchLastSection(True)
        widget.itemChanged.connect(self.changed);return widget

    def changed(self,*_):
        if self._loading:return
        self.dirty=True;self.result=None;self.report.clear();self.status.setText("Inputs changed. Calculate again for current material, sections and duty.")

    def add_station(self,station=None):
        if not isinstance(station,FatigueStation):
            used={self.stations.item(r,0).text() for r in range(self.stations.rowCount())};number=1
            while f"Section {number}" in used:number+=1
            station=FatigueStation(name=f"Section {number}",position_mm=self.shaft.length_mm/2)
        row=self.stations.rowCount();self.stations.insertRow(row)
        for col,key in enumerate(self.STATION_FIELDS):
            value=getattr(station,key)
            if key=="side":
                side=QComboBox();side.addItems(["left","right"]);side.setCurrentText(value);side.currentIndexChanged.connect(self.changed);self.stations.setCellWidget(row,col,side)
            else:self.stations.setItem(row,col,QTableWidgetItem("" if value is None else str(value)))
        self.changed()

    def remove_station(self):
        row=self.stations.currentRow()
        if row>=0:self.stations.removeRow(row);self.changed()

    def set_study(self,study):
        study.validate();self._loading=True
        try:
            self.shaft=ShaftStudy.from_dict(asdict(study.shaft));self.name.setText(study.name)
            for key,widget in self.numbers.items():widget.setText(str(getattr(study,key)))
            for key,widget in self.material.items():
                value=getattr(study.material,key)
                if isinstance(widget,QComboBox):widget.setCurrentIndex(widget.findData(value))
                elif isinstance(widget,QTextEdit):widget.setPlainText(value)
                else:widget.setText("" if value is None else str(value))
            self.stations.setRowCount(0)
            for station in study.stations:self.add_station(station)
            self.case_keys=[c.case_name for c in study.cases];self.cases.setRowCount(len(study.cases))
            shaft_cases={c.name:c for c in self.shaft.cases}
            for row,condition in enumerate(study.cases):
                case=shaft_cases[condition.case_name]
                for col,value in enumerate((case.name,f"{case.rpm:.9g}",f"{case.duration_hours:.9g}")):
                    item=QTableWidgetItem(value);item.setFlags(item.flags() & ~Qt.ItemIsEditable);self.cases.setItem(row,col,item)
                model=QComboBox()
                for label,value in (("Unverified","unverified"),("Fixed bending, steady torque","fixed_bending_steady_torque"),("Other / unsupported","other")):model.addItem(label,value)
                model.setCurrentIndex(model.findData(condition.load_model));model.currentIndexChanged.connect(self.changed);self.cases.setCellWidget(row,3,model)
                self.cases.setItem(row,4,QTableWidgetItem("" if condition.operating_temperature_c is None else str(condition.operating_temperature_c)))
                self.cases.setItem(row,5,QTableWidgetItem(condition.basis))
            self.source.setHtml(f"<h2>{html.escape(self.shaft.name)}</h2><p>Loads are recalculated from this retained input. New from shaft starts fresh material and factors.</p><pre>{html.escape(json.dumps(asdict(self.shaft),indent=2))}</pre>")
            self.coverage.setPlainText(study.duty_coverage_basis);self.notes.setPlainText(study.notes)
            self.result=None;self.report.clear();self.dirty=False;self.status.setText("Enter material evidence, critical sections and loading conditions. Blank values remain unassessed.")
        finally:self._loading=False

    @staticmethod
    def optional(text):return None if not text.strip() else float(text)

    def read_study(self):
        data={}
        for key,widget in self.material.items():
            if isinstance(widget,QComboBox):value=widget.currentData()
            elif isinstance(widget,QTextEdit):value=widget.toPlainText()
            else:value=self.optional(widget.text()) if key in self.NUMBERS else widget.text()
            data[key]=value
        stations=[]
        for row in range(self.stations.rowCount()):
            values={}
            for col,key in enumerate(self.STATION_FIELDS):
                if key=="side":value=self.stations.cellWidget(row,col).currentText()
                else:
                    value=self.stations.item(row,col).text()
                    if key not in ("name","factor_basis"):value=self.optional(value)
                values[key]=value
            stations.append(FatigueStation(**values))
        cases=[FatigueCase(case_name=name,load_model=self.cases.cellWidget(row,3).currentData(),
            operating_temperature_c=self.optional(self.cases.item(row,4).text()),basis=self.cases.item(row,5).text()) for row,name in enumerate(self.case_keys)]
        study=FatigueStudy(name=self.name.text(),shaft=self.shaft,material=FatigueMaterial(**data),stations=stations,cases=cases,
            **{key:float(w.text()) for key,w in self.numbers.items()},duty_coverage_basis=self.coverage.toPlainText(),notes=self.notes.toPlainText())
        study.validate();return study

    def calculate(self):
        try:
            self.result=calculate_fatigue_study(self.read_study());self.report.setHtml(fatigue_report_html(self.result));self.tabs.setCurrentWidget(self.report)
            self.status.setText(" · ".join(f"{s['name']}: {s['assessment'].replace('_',' ')}" for s in self.result["stations"])+". No production gearbox rating.");return True
        except (ValueError,TypeError,RuntimeError,OverflowError) as exc:
            self.result=None;self.report.clear();self.show_error(exc);return False

    def show_error(self,error):QMessageBox.warning(self,"Shaft fatigue study",str(error))

    def save_study(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=self.save_destination("Save fatigue study",str(self.path or "shaft.gearforge-fatigue"),"Fatigue study (*.gearforge-fatigue)")
        if not path:return False
        try:study.save(Path(path))
        except (ValueError,OSError) as exc:self.show_error(exc);return False
        self.path=Path(path);self.dirty=False;self.status.setText(f"Saved {self.path.name}");return True

    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,"Unsaved fatigue study","Save this study before continuing?",QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        return self.save_study() if answer==QMessageBox.Save else answer==QMessageBox.Discard

    def open_study(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,"Open fatigue study","","Fatigue study (*.gearforge-fatigue)")
        if not path:return False
        try:study=FatigueStudy.load(Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=Path(path);return True

    def open_shaft(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,"New fatigue study from shaft","","Shaft study (*.gearforge-shaft)")
        if not path:return False
        try:study=fatigue_from_shaft(ShaftStudy.load(Path(path)))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=None;self.changed();return True

    def load_example(self):
        if not self.confirm_discard():return False
        self.set_study(nasa_example());self.path=None;self.changed();return True

    def export(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,"Choose a new assessment folder","shaft-fatigue-assessment","Folder name (*)")
        if not path:return False
        try:export_fatigue_study(study,Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.status.setText("Exported complete inputs, assessment, report and integrity manifest.");return True

    def reject(self):
        if self.confirm_discard():super().reject()

    def closeEvent(self,event):
        if self.confirm_discard():self.dirty=False;super().closeEvent(event)
        else:event.ignore()
