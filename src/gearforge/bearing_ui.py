"""Bearing inputs remain explicit; missing values are displayed as unassessed."""
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,
    QHeaderView,QLabel,QLineEdit,QMessageBox,QPushButton,QScrollArea,QTabWidget,
    QTableWidget,QTableWidgetItem,QTextBrowser,QTextEdit,QVBoxLayout,QWidget)

from .chart_style import ReportBrowser

from .desktop_ui import StudyDialog, StudyTabs

from .bearings import (BearingCase,BearingDefinition,BearingStudy,bearings_from_shaft,
                       calculate_bearing_study,bearing_report_html,export_bearing_study)
from .engineering_ui import StudyNumber
from .shafts import ShaftStudy,calculate_shaft_study


class BearingStudyDialog(StudyDialog):
    NUMBERS = {
        'bore_mm':'Nominal bore (mm)', 'dynamic_capacity_n':'Dynamic capacity C (N)',
        'static_capacity_n':'Static capacity C0 (N)', 'speed_limit_rpm':'Applicable speed limit (rpm)',
        'minimum_dynamic_load_n':'Minimum dynamic equivalent load (N)', 'axial_limit_n':'Applicable axial load limit (N)',
        'misalignment_limit_rad':'Applicable misalignment limit (rad)',
        'minimum_temperature_c':'Minimum operating temperature (°C)', 'maximum_temperature_c':'Maximum operating temperature (°C)',
        'required_static_safety':'Required static safety factor',
    }
    CASE_NUMBERS = ('operating_temperature_c','installation_misalignment_rad','dynamic_x','dynamic_y','static_x','static_y')

    def __init__(self,parent=None,study=None):
        super().__init__(parent)
        self.resize(1260,860);self.setWindowTitle('Bearing duty and capacity')
        self.path=None;self.result=None;self.dirty=False;self._loading=True
        layout=QVBoxLayout(self)
        note=QLabel('Assess each bearing using its exact rating conditions. Blank values remain unassessed. Basic L10 estimates per-bearing fatigue; it does not establish gearbox service life.')
        note.setWordWrap(True);layout.addWidget(note)
        top=QFormLayout();layout.addLayout(top)
        self.name=QLineEdit();self.name.textEdited.connect(self.changed);top.addRow('Study name',self.name)
        self.hours=StudyNumber();self.hours.setRange(.000001,2e8);self.hours.setDecimals(6);self.hours.setSuffix(' h')
        self.hours.setKeyboardTracking(False);self.hours.valueChanged.connect(self.changed);top.addRow('Required repeated-duty duration',self.hours)
        self.tabs=StudyTabs();layout.addWidget(self.tabs,1);self.editors={}
        for position in ('a','b'):
            scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();form=QFormLayout(page);scroll.setWidget(page)
            editors={};self.editors[position]=editors
            for key,label in (('manufacturer','Manufacturer'),('designation','Exact designation')):
                widget=QLineEdit();widget.textEdited.connect(self.changed);editors[key]=widget;form.addRow(label,widget)
            kind=QComboBox();kind.addItem('Deep-groove radial ball','deep_groove_ball');kind.addItem('Cylindrical roller — radial load only','cylindrical_roller_radial')
            kind.currentIndexChanged.connect(self.changed);editors['kind']=kind;form.addRow('Bearing type',kind)
            for key,label in self.NUMBERS.items():
                widget=QLineEdit();widget.setPlaceholderText('Unknown — enter an applicable value');widget.setAccessibleName(label)
                widget.textEdited.connect(self.changed);editors[key]=widget;form.addRow(label,widget)
            status=QComboBox()
            for label,value in (('Unverified / incomplete','unverified'),('Synthetic example','synthetic'),('Declared source data','declared')):status.addItem(label,value)
            status.currentIndexChanged.connect(self.changed);editors['data_status']=status;form.addRow('Input provenance',status)
            for key,label in (('source_reference','Source, revision and location'),('rating_conditions','Applicable rating / lubrication conditions'),('redistribution_basis','Rights / redistribution basis')):
                widget=QTextEdit();widget.setAcceptRichText(False);widget.setMinimumHeight(55);widget.setMaximumHeight(90)
                widget.textChanged.connect(self.changed);editors[key]=widget;form.addRow(label,widget)
            self.tabs.addTab(scroll,f'Bearing {position.upper()}')
        page=QWidget();case_layout=QVBoxLayout(page)
        hint=QLabel('Loads come from the retained shaft study. For axial loading, enter the exact case-specific X/Y and X0/Y0 factors and their branch/source. Pure radial cases use P=P0=Fr. Bearing temperature is not shaft ambient temperature.')
        hint.setWordWrap(True);case_layout.addWidget(hint)
        self.cases=QTableWidget(0,11);self.cases.setHorizontalHeaderLabels(['Case / bearing','Fr N','Fa N','Motion','Bearing °C','Installation rad','X','Y','X0','Y0','Factor basis'])
        self.cases.setAlternatingRowColors(True)
        self.cases.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.cases.horizontalHeader().setStretchLastSection(True);self.cases.itemChanged.connect(self.changed)
        self.cases.setAccessibleName('Bearing conditions for every shaft duty case');case_layout.addWidget(self.cases,1)
        self.tabs.addTab(page,'Duty conditions')
        page=QWidget();source_layout=QVBoxLayout(page)
        self.source=ReportBrowser();source_layout.addWidget(self.source,1)
        source_layout.addWidget(QLabel('Assessment notes'))
        self.notes=QTextEdit();self.notes.setAcceptRichText(False);self.notes.setMaximumHeight(110)
        self.notes.textChanged.connect(self.changed);source_layout.addWidget(self.notes)
        self.tabs.addTab(page,'Shaft and provenance')
        self.report=ReportBrowser();self.report.setOpenExternalLinks(False);self.tabs.addTab(self.report,'Assessment')
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in (('Open bearing study…',self.open_study),('New from shaft…',self.open_shaft),
            ('Save study…',self.save_study),('Calculate',self.calculate),('Export assessment…',self.export),('Close',self.reject)):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        self.set_study(study or BearingStudy())
        self.finish_ui()


    def changed(self,*_):
        if self._loading:return
        self.dirty=True;self.result=None;self.report.clear()
        self.status.setText('Inputs changed. Calculate again to assess current bearing data and duty.')

    def set_study(self,study):
        study.validate();self._loading=True
        try:
            self.shaft=ShaftStudy.from_dict(asdict(study.shaft));self.name.setText(study.name);self.hours.setValue(study.required_hours)
            for bearing in study.bearings:
                for key,widget in self.editors[bearing.position].items():
                    value=getattr(bearing,key)
                    if isinstance(widget,QComboBox):widget.setCurrentIndex(widget.findData(value))
                    elif isinstance(widget,QTextEdit):widget.setPlainText(value)
                    else:widget.setText('' if value is None else str(value))
            shaft=calculate_shaft_study(self.shaft);loads={(c['name'],b['name']):b for c in shaft['cases'] for b in c['bearings']}
            self.case_keys=[(c.case_name,c.position) for c in study.cases];self.cases.setRowCount(len(study.cases))
            for row,condition in enumerate(study.cases):
                load=loads[condition.case_name,condition.position]
                for column,value in enumerate((f'{condition.case_name} / {condition.position.upper()}',f"{load['radial_load_n']:.9g}",f"{load['axial_load_n']:.9g}")):
                    item=QTableWidgetItem(value);item.setFlags(item.flags() & ~Qt.ItemIsEditable);self.cases.setItem(row,column,item)
                motion=QComboBox()
                for label,value in (('Continuous rotation','continuous_rotation'),('Stationary','stationary'),('Oscillation (unassessed)','oscillation')):motion.addItem(label,value)
                motion.setCurrentIndex(motion.findData(condition.motion));motion.currentIndexChanged.connect(self.changed);self.cases.setCellWidget(row,3,motion)
                for column,key in enumerate(self.CASE_NUMBERS,4):
                    value=getattr(condition,key);self.cases.setItem(row,column,QTableWidgetItem('' if value is None else str(value)))
                self.cases.setItem(row,10,QTableWidgetItem(condition.factor_basis))
            import html,json
            self.source.setHtml(f'<h2>{html.escape(self.shaft.name)}</h2><p>The embedded shaft input is recalculated for every assessment. New from shaft starts fresh bearing definitions and factors.</p><pre>{html.escape(json.dumps(asdict(self.shaft),indent=2))}</pre>')
            self.notes.setPlainText(study.notes);self.result=None;self.report.clear();self.dirty=False
            self.status.setText('Enter bearing capacities, applicable limits and operating conditions. Unknown values remain visible.')
        finally:self._loading=False

    @staticmethod
    def optional(text):return None if not text.strip() else float(text)

    def read_study(self):
        bearings=[]
        for position,editors in self.editors.items():
            data={'position':position}
            for key,widget in editors.items():
                if isinstance(widget,QComboBox):value=widget.currentData()
                elif isinstance(widget,QTextEdit):value=widget.toPlainText()
                else:value=self.optional(widget.text()) if key in self.NUMBERS else widget.text()
                data[key]=value
            bearings.append(BearingDefinition(**data))
        cases=[]
        for row,(name,position) in enumerate(self.case_keys):
            data={key:self.optional(self.cases.item(row,column).text()) for column,key in enumerate(self.CASE_NUMBERS,4)}
            cases.append(BearingCase(case_name=name,position=position,motion=self.cases.cellWidget(row,3).currentData(),
                                     factor_basis=self.cases.item(row,10).text(),**data))
        study=BearingStudy(name=self.name.text(),shaft=self.shaft,bearings=bearings,cases=cases,
                           required_hours=self.hours.value(),notes=self.notes.toPlainText())
        study.validate();return study

    def calculate(self):
        try:
            self.result=calculate_bearing_study(self.read_study());self.report.setHtml(bearing_report_html(self.result))
            self.tabs.setCurrentWidget(self.report)
            self.status.setText(' · '.join(f"Bearing {b['position'].upper()}: {b['assessment'].replace('_',' ')}" for b in self.result['bearings'])+'. No production gearbox rating.')
            return True
        except (ValueError,TypeError,RuntimeError,OverflowError) as exc:
            self.result=None;self.report.clear();self.show_error(exc);return False

    def show_error(self,error):QMessageBox.warning(self,'Bearing study',str(error))

    def save_study(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=self.save_destination('Save bearing study',str(self.path or 'bearings.gearforge-bearing'),'Bearing study (*.gearforge-bearing)')
        if not path:return False
        try:study.save(Path(path))
        except (ValueError,OSError) as exc:self.show_error(exc);return False
        self.path=Path(path);self.dirty=False;self.status.setText(f'Saved {self.path.name}');return True

    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved bearing study','Save this study before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        return self.save_study() if answer==QMessageBox.Save else answer==QMessageBox.Discard

    def open_study(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Open bearing study','','Bearing study (*.gearforge-bearing)')
        if not path:return False
        try:study=BearingStudy.load(Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=Path(path);return True

    def open_shaft(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'New bearing study from shaft','','Shaft study (*.gearforge-shaft)')
        if not path:return False
        try:study=bearings_from_shaft(ShaftStudy.load(Path(path)))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=None;self.changed();return True

    def export(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Choose a new assessment folder','bearing-assessment','Folder name (*)')
        if not path:return False
        try:export_bearing_study(study,Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.status.setText('Exported complete inputs, assessment, report and integrity manifest.');return True

    def reject(self):
        if self.confirm_discard():super().reject()

    def closeEvent(self,event):
        if self.confirm_discard():self.dirty=False;super().closeEvent(event)
        else:event.ignore()
