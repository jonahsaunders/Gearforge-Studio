"""Desktop editor and path diagrams for explicit tooth-contact evidence."""
from dataclasses import asdict
import html
import json
from pathlib import Path

from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import (QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,
    QLabel,QLineEdit,QMessageBox,QPushButton,QScrollArea,QTabWidget,QTableWidget,QTableWidgetItem,
    QTextBrowser,QTextEdit,QVBoxLayout,QWidget)

from .chart_style import ChartWidget, ReportBrowser, chart_color

from .desktop_ui import StudyDialog, StudyTabs

from .contact import (ContactMaterial,ContactLifePoint,ContactCase,ContactStudy,contact_from_study,
    synthetic_contact_example,calculate_contact_study,contact_report_html,export_contact_study)
from .engineering import EngineeringStudy


class ContactPlot(ChartWidget):
    QUANTITIES={"Peak Hertz pressure (MPa)":"peak_pressure_mpa","Contact half-width (mm)":"half_width_mm",
        "Sliding speed (m/s)":"sliding_speed_m_s","Pair load fraction":"pair_load_fraction"}
    def __init__(self):
        super().__init__();self.profile=[];self.quantity=next(iter(self.QUANTITIES));self.setMinimumHeight(280)
        self.setAccessibleName("Tooth contact profile along the line of action")
    def set_profile(self,profile,quantity):self.profile=profile;self.quantity=quantity;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),self.palette().base());p.setPen(self.palette().text().color())
        if not self.profile:
            p.drawText(self.rect(),Qt.AlignCenter,"Calculate a supported study with elastic constants and load factors to view the path.");return
        key=self.QUANTITIES[self.quantity];values=[row[key] for row in self.profile]
        x0=self.profile[0]['relative_to_pitch_mm'];x1=self.profile[-1]['relative_to_pitch_mm']
        maximum=max(values)*1.08 or 1;left,top,width,height=90,40,self.width()-120,self.height()-95
        p.drawText(12,22,self.quantity+" — exact critical limits joined by display samples")
        def point(row):return QPointF(left+(row['relative_to_pitch_mm']-x0)/(x1-x0)*width,top+height-row[key]/maximum*height)
        for i in range(6):
            y=top+height-i*height/5;p.setPen(QPen(self.palette().mid().color(),1));p.drawLine(QPointF(left,y),QPointF(left+width,y))
            p.setPen(self.palette().text().color());p.drawText(5,int(y+4),f"{i*maximum/5:.5g}")
            x=left+i*width/5;p.drawText(int(x-18),int(top+height+23),f"{x0+(x1-x0)*i/5:.4g}")
        if x0<=0<=x1:
            x=left-x0/(x1-x0)*width;p.setPen(QPen(self.palette().mid().color(),1,Qt.DashLine));p.drawLine(QPointF(x,top),QPointF(x,top+height))
        p.setPen(QPen(chart_color(self,'#2878b8'),2))
        for a,b in zip(self.profile,self.profile[1:]):p.drawLine(point(a),point(b))
        p.setPen(self.palette().text().color());p.drawText(int(left+width/2-100),self.height()-10,"Distance from pitch point (mm)")


class ContactStudyDialog(StudyDialog):
    NUMBERS={"youngs_modulus_mpa":"Young's modulus at operating conditions (MPa)","poisson_ratio":"Poisson ratio",
        "maximum_elastic_pressure_mpa":"Declared maximum elastic contact pressure (MPa)",
        "minimum_temperature_c":"Minimum operating temperature (°C)","maximum_temperature_c":"Maximum operating temperature (°C)"}
    CASE_NUMBERS=("normal_load_multiplier","face_line_load_multiplier","effective_face_width_mm","pinion_temperature_c","wheel_temperature_c")

    def __init__(self,parent=None,study=None):
        super().__init__(parent);self.resize(1280,900);self.setWindowTitle("Tooth contact and surface fatigue")
        self.path=None;self.result=None;self.dirty=False;self._loading=True
        layout=QVBoxLayout(self);note=QLabel("Inspect spur-tooth contact pressure along the mesh and compare each flank's duty with applicable pressure-life data. Material values and load factors need evidence; this is not a production gearbox rating.")
        note.setWordWrap(True);layout.addWidget(note);form=QFormLayout();layout.addLayout(form)
        self.name=QLineEdit();self.name.textEdited.connect(self.changed);form.addRow("Study name",self.name)
        self.sharing=QComboBox();self.sharing.addItem("Full mesh-load envelope at each pair","full_load_envelope");self.sharing.addItem("Ideal equal sharing between contacting pairs","equal_pairs")
        self.sharing.currentIndexChanged.connect(self.changed);form.addRow("Load-sharing assumption",self.sharing)
        self.factor=QLineEdit();self.factor.textEdited.connect(self.changed);form.addRow("Pressure design factor (not a load multiplier)",self.factor)
        self.tabs=StudyTabs();layout.addWidget(self.tabs,1);self.materials={};self.curves={}
        for role in ('pinion','wheel'):
            scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();page_layout=QVBoxLayout(page);form=QFormLayout();page_layout.addLayout(form);scroll.setWidget(page)
            editors={};self.materials[role]=editors
            for key,label in {"designation":"Exact material, treatment and surface",**self.NUMBERS}.items():
                w=QLineEdit();w.setAccessibleName(label);w.textEdited.connect(self.changed)
                if key in self.NUMBERS:w.setPlaceholderText("Unknown — enter applicable evidence")
                editors[key]=w;form.addRow(label,w)
            status=QComboBox()
            for label,value in (("Unverified / incomplete","unverified"),("Synthetic example","synthetic"),("Declared source data","declared")):status.addItem(label,value)
            status.currentIndexChanged.connect(self.changed);editors['data_status']=status;form.addRow("Input provenance",status)
            for key,label in (("source_reference","Source, revision and exact location"),("applicable_conditions","Surface, lubricant, slide/roll, temperature and survival basis"),("redistribution_basis","Rights / redistribution basis")):
                w=QTextEdit();w.setAcceptRichText(False);w.setMinimumHeight(55);w.setMaximumHeight(85);w.textChanged.connect(self.changed);editors[key]=w;form.addRow(label,w)
            hint=QLabel("Applicable pressure-life curve: increasing cycles, decreasing peak Hertz pressure. Log-log interpolation only; no extrapolation or infinite-life plateau.");hint.setWordWrap(True);page_layout.addWidget(hint)
            table=self.table(['Cycles to defined surface-fatigue endpoint','Peak Hertz pressure (MPa)']);table.setMinimumHeight(160);self.curves[role]=table;page_layout.addWidget(table)
            buttons=QHBoxLayout();page_layout.addLayout(buttons)
            for label,callback in (("Add curve point",lambda checked=False,r=role:self.add_point(r)),("Remove selected point",lambda checked=False,r=role:self.remove_point(r))):
                button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
            self.tabs.addTab(scroll,role.title()+" evidence")
        page=QWidget();cases_layout=QVBoxLayout(page)
        hint=QLabel("Normal load multiplier covers application and dynamics. Face multiplier represents peak line-load concentration. Enter effective face width and each gear's operating temperature; ambient temperature is not substituted.")
        hint.setWordWrap(True);cases_layout.addWidget(hint)
        self.cases=self.table(['Retained case','Pinion rpm','Hours','Normal load ×','Face line-load ×','Effective face mm','Pinion °C','Wheel °C','Factor evidence'])
        cases_layout.addWidget(self.cases,1);self.tabs.addTab(page,'Duty conditions')
        page=QWidget();path_layout=QVBoxLayout(page);controls=QHBoxLayout();path_layout.addLayout(controls)
        self.case_selector=QComboBox();self.case_selector.currentIndexChanged.connect(self.update_plot);controls.addWidget(self.case_selector)
        self.quantity=QComboBox();self.quantity.addItems(ContactPlot.QUANTITIES);self.quantity.currentIndexChanged.connect(self.update_plot);controls.addWidget(self.quantity)
        self.plot=ContactPlot();path_layout.addWidget(self.plot,1);self.path_summary=QLabel();self.path_summary.setWordWrap(True);path_layout.addWidget(self.path_summary)
        self.tabs.addTab(page,'Contact path')
        page=QWidget();provenance=QVBoxLayout(page);self.source_view=ReportBrowser();provenance.addWidget(self.source_view,1)
        self.sharing_basis=QTextEdit();self.notes=QTextEdit()
        for label,w in (("Load-sharing basis and omitted effects",self.sharing_basis),("Study notes",self.notes)):
            w.setAcceptRichText(False);w.setMaximumHeight(90);w.textChanged.connect(self.changed);provenance.addWidget(QLabel(label));provenance.addWidget(w)
        self.tabs.addTab(page,'Gear study and provenance')
        self.report=ReportBrowser();self.report.setOpenExternalLinks(False);self.tabs.addTab(self.report,'Assessment')
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in (("Open study…",self.open_study),("New from gear study…",self.open_source),("Synthetic example",self.load_example),
            ("Save study…",self.save_study),("Calculate",self.calculate),("Export assessment…",self.export),("Close",self.reject)):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        self.set_study(study or ContactStudy())
        self.finish_ui()


    def table(self,headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers);table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);table.horizontalHeader().setStretchLastSection(True);table.itemChanged.connect(self.changed);return table

    def changed(self,*_):
        if self._loading:return
        self.dirty=True;self.result=None;self.report.clear();self.plot.set_profile([],self.quantity.currentText());self.path_summary.clear()
        self.status.setText("Inputs changed. Calculate again to update contact pressures and flank exposure.")

    def add_point(self,role,point=None):
        table=self.curves[role];row=table.rowCount();table.insertRow(row)
        for col,value in enumerate((point.cycles,point.pressure_mpa) if isinstance(point,ContactLifePoint) else ('','')):
            table.setItem(row,col,QTableWidgetItem(str(value)))
        self.changed()

    def remove_point(self,role):
        table=self.curves[role]
        if table.currentRow()>=0:table.removeRow(table.currentRow());self.changed()

    def set_study(self,study):
        study.validate();self._loading=True
        try:
            self.source=EngineeringStudy.from_dict(asdict(study.source));self.name.setText(study.name)
            self.sharing.setCurrentIndex(self.sharing.findData(study.load_sharing));self.factor.setText(str(study.pressure_design_factor))
            for material in study.materials:
                for key,w in self.materials[material.role].items():
                    value=getattr(material,key)
                    if isinstance(w,QComboBox):w.setCurrentIndex(w.findData(value))
                    elif isinstance(w,QTextEdit):w.setPlainText(value)
                    else:w.setText('' if value is None else str(value))
                self.curves[material.role].setRowCount(0)
                for point in material.life_curve:self.add_point(material.role,point)
            duty={c.name:c for c in self.source.duty};self.case_keys=[c.case_name for c in study.cases];self.cases.setRowCount(len(study.cases))
            for row,condition in enumerate(study.cases):
                c=duty[condition.case_name]
                for col,value in enumerate((c.name,f'{c.input_rpm:.9g}',f'{c.duration_hours:.9g}')):
                    item=QTableWidgetItem(value);item.setFlags(item.flags() & ~Qt.ItemIsEditable);self.cases.setItem(row,col,item)
                for col,key in enumerate(self.CASE_NUMBERS,3):
                    value=getattr(condition,key);self.cases.setItem(row,col,QTableWidgetItem('' if value is None else str(value)))
                self.cases.setItem(row,8,QTableWidgetItem(condition.factor_basis))
            self.source_view.setHtml(f"<h2>{html.escape(self.source.name)}</h2><p>The retained geometry and duty are recalculated. New from gear study starts fresh material and factor inputs.</p><pre>{html.escape(json.dumps(asdict(self.source),indent=2))}</pre>")
            self.sharing_basis.setPlainText(study.load_sharing_basis);self.notes.setPlainText(study.notes)
            self.result=None;self.report.clear();self.case_selector.clear();self.plot.set_profile([],self.quantity.currentText());self.path_summary.clear();self.dirty=False
            self.status.setText('Enter material evidence, applicable load factors and pressure-life curves. Blank values remain unassessed.')
        finally:self._loading=False

    @staticmethod
    def optional(text):return None if not text.strip() else float(text)

    def read_study(self):
        materials=[]
        for role,editors in self.materials.items():
            data={}
            for key,w in editors.items():
                if isinstance(w,QComboBox):value=w.currentData()
                elif isinstance(w,QTextEdit):value=w.toPlainText()
                else:value=self.optional(w.text()) if key in self.NUMBERS else w.text()
                data[key]=value
            curve=self.curves[role]
            points=[ContactLifePoint(float(curve.item(row,0).text()),float(curve.item(row,1).text())) for row in range(curve.rowCount())]
            materials.append(ContactMaterial(role=role,life_curve=points,**data))
        cases=[ContactCase(case_name=name,**{key:self.optional(self.cases.item(row,col).text()) for col,key in enumerate(self.CASE_NUMBERS,3)},factor_basis=self.cases.item(row,8).text()) for row,name in enumerate(self.case_keys)]
        study=ContactStudy(name=self.name.text(),source=self.source,materials=materials,cases=cases,
            load_sharing=self.sharing.currentData(),pressure_design_factor=float(self.factor.text()),
            load_sharing_basis=self.sharing_basis.toPlainText(),notes=self.notes.toPlainText())
        study.validate();return study

    def calculate(self):
        try:
            self.result=calculate_contact_study(self.read_study());self.report.setHtml(contact_report_html(self.result))
            self.case_selector.clear();self.case_selector.addItems([c['name'] for c in self.result['cases']]);self.update_plot();self.tabs.setCurrentWidget(self.report)
            self.status.setText(' · '.join(f"{m['role'].title()}: {m['assessment'].replace('_',' ')}" for m in self.result['members'])+'. No production gearbox rating.');return True
        except (ValueError,TypeError,RuntimeError,OverflowError) as exc:
            self.result=None;self.report.clear();self.plot.set_profile([],self.quantity.currentText());self.show_error(exc);return False

    def update_plot(self,*_):
        index=self.case_selector.currentIndex()
        if self.result is None or index<0:return
        case=self.result['cases'][index];self.plot.set_profile(case['profile'],self.quantity.currentText())
        if case['worst_contact'] is None:self.path_summary.setText('Contact model unavailable. '+ ' '.join(self.result['geometry_findings']));return
        worst=case['worst_contact']
        self.path_summary.setText(f"Maximum Hertz pressure {case['peak_hertz_pressure_mpa']:.8g} MPa, at {worst['relative_to_pitch_mm']:.8g} mm from pitch ({worst['side']} limit). Half-width {worst['half_width_mm']:.8g} mm. Geometry gives {worst['simultaneous_pairs']} contacting pairs here. Exact interval limits determine maxima; the curve is for display.")

    def show_error(self,error):QMessageBox.warning(self,'Tooth contact study',str(error))

    def save_study(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=self.save_destination('Save contact study',str(self.path or 'tooth.gearforge-contact'),'Contact study (*.gearforge-contact)')
        if not path:return False
        try:study.save(Path(path))
        except (ValueError,OSError) as exc:self.show_error(exc);return False
        self.path=Path(path);self.dirty=False;self.status.setText(f'Saved {self.path.name}');return True

    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved contact study','Save this study before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        return self.save_study() if answer==QMessageBox.Save else answer==QMessageBox.Discard

    def open_study(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Open contact study','','Contact study (*.gearforge-contact)')
        if not path:return False
        try:study=ContactStudy.load(Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=Path(path);return True

    def open_source(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'New contact study from gear study','','Engineering study (*.gearforge-study)')
        if not path:return False
        try:study=contact_from_study(EngineeringStudy.load(Path(path)))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=None;self.changed();return True

    def load_example(self):
        if not self.confirm_discard():return False
        self.set_study(synthetic_contact_example());self.path=None;self.changed();return True

    def export(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Choose a new contact assessment folder','tooth-contact-assessment','Folder name (*)')
        if not path:return False
        try:export_contact_study(study,Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.status.setText('Exported complete source, evidence, pressures, flank exposure, report and integrity manifest.');return True

    def reject(self):
        if self.confirm_discard():super().reject()

    def closeEvent(self,event):
        if self.confirm_discard():self.dirty=False;super().closeEvent(event)
        else:event.ignore()
