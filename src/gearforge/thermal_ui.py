"""Editable thermal bodies, paths, ordered phases and temperature trajectories."""
from dataclasses import asdict
import copy
import html
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,
    QLabel,QLineEdit,QMessageBox,QPushButton,QTableWidget,QTableWidgetItem,QTabWidget,QTextBrowser,
    QTextEdit,QVBoxLayout,QWidget)

from .engineering import EngineeringStudy
from .thermal import (AMBIENT,ThermalNode,ThermalLink,ThermalPhase,ThermalStudy,
    thermal_from_study,synthetic_thermal_example,calculate_thermal_study,thermal_report_html,export_thermal_study)


class TemperaturePlot(QWidget):
    def __init__(self):
        super().__init__();self.points=[];self.body='';self.logarithmic=False;self.setMinimumHeight(300)
        self.setAccessibleName('Body temperature over the selected thermal phase')
    def set_data(self,points,body,logarithmic=False):self.points=points;self.body=body;self.logarithmic=logarithmic;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),self.palette().base());p.setPen(self.palette().text().color())
        if not self.points or self.body not in self.points[0]['temperature_c']:
            p.drawText(self.rect(),Qt.AlignCenter,'Calculate a supported thermal study to view temperatures.');return
        values=[row['temperature_c'][self.body] for row in self.points];low=min(values);high=max(values)
        margin=max(1.,(high-low)*.08);low-=margin;high+=margin
        convert=math.log1p if self.logarithmic else lambda t:t;end=convert(self.points[-1]['time_s']) or 1
        left,top,width,height=80,40,self.width()-110,self.height()-95
        p.drawText(12,22,self.body+' — temperature (°C)')
        def point(row):return QPointF(left+convert(row['time_s'])/end*width,top+(high-row['temperature_c'][self.body])/(high-low)*height)
        for i in range(6):
            y=top+height-i*height/5;p.setPen(QPen(self.palette().mid().color(),1));p.drawLine(QPointF(left,y),QPointF(left+width,y))
            p.setPen(self.palette().text().color());p.drawText(7,int(y+4),f'{low+(high-low)*i/5:.6g}')
            x=left+i*width/5;seconds=math.expm1(end*i/5) if self.logarithmic else end*i/5
            p.drawText(int(x-20),int(top+height+23),f'{seconds/60:.5g}')
        p.setPen(QPen(QColor('#b9581b'),2))
        for a,b in zip(self.points,self.points[1:]):p.drawLine(point(a),point(b))
        p.setPen(self.palette().text().color());p.drawText(int(left+width/2-85),self.height()-10,'Elapsed time in phase (minutes)')


class ThermalStudyDialog(QDialog):
    BODY_NUMBERS={'capacity_j_per_k':'Thermal capacity (J/K)','initial_temperature_c':'Initial temperature (°C)',
        'minimum_allowable_c':'Minimum allowable temperature (°C)','maximum_allowable_c':'Maximum allowable temperature (°C)',
        'model_minimum_c':'Minimum temperature supported by the model (°C)','model_maximum_c':'Maximum temperature supported by the model (°C)'}

    def __init__(self,parent=None,study=None):
        super().__init__(parent);self.resize(1280,930);self.setWindowTitle('Thermal network and cooling duty')
        self.path=None;self.result=None;self.dirty=False;self._loading=True;self.body_index=0;self.phase_index=0
        layout=QVBoxLayout(self);note=QLabel('Calculate heating and cooling through explicit thermal bodies and paths. Enter actual heat losses and cooling evidence; assumed gearbox efficiency does not supply those inputs. No production gearbox rating.')
        note.setWordWrap(True);layout.addWidget(note);form=QFormLayout();layout.addLayout(form)
        self.name=QLineEdit();self.name.textEdited.connect(self.changed);form.addRow('Study name',self.name)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        page=QWidget();body_layout=QVBoxLayout(page);controls=QHBoxLayout();body_layout.addLayout(controls)
        self.body_selector=QComboBox();self.body_selector.currentIndexChanged.connect(self.select_body);controls.addWidget(self.body_selector,1)
        self.buttons(controls,(('Add body',self.add_body),('Remove body',self.remove_body)))
        form=QFormLayout();body_layout.addLayout(form);self.body_fields={}
        for key,label in {'name':'Body name',**self.BODY_NUMBERS}.items():
            w=QLineEdit();w.setAccessibleName(label);w.textEdited.connect(self.changed);self.body_fields[key]=w;form.addRow(label,w)
            if key in self.BODY_NUMBERS:w.setPlaceholderText('Unknown — enter applicable evidence')
        status=QComboBox()
        for label,value in (('Unverified / incomplete','unverified'),('Synthetic example','synthetic'),('Declared source data','declared')):status.addItem(label,value)
        status.currentIndexChanged.connect(self.changed);self.body_fields['data_status']=status;form.addRow('Input provenance',status)
        for key,label in (('source_reference','Capacity, allowable and isothermal-body evidence'),('redistribution_basis','Rights / redistribution basis')):
            w=QTextEdit();w.setAcceptRichText(False);w.setMaximumHeight(90);w.textChanged.connect(self.changed);self.body_fields[key]=w;form.addRow(label,w)
        body_layout.addStretch();self.tabs.addTab(page,'Thermal bodies')
        page=QWidget();paths_layout=QVBoxLayout(page)
        hint=QLabel('A path joins two bodies, or one body to the imposed Ambient heat bath. Conductance is entered separately for every phase. Combine parallel paths into one justified equivalent conductance.');hint.setWordWrap(True);paths_layout.addWidget(hint)
        self.paths=self.table(['Path name','First body','Second body / Ambient']);paths_layout.addWidget(self.paths,1)
        controls=QHBoxLayout();paths_layout.addLayout(controls);self.buttons(controls,(('Add path',self.add_path),('Remove selected path',self.remove_path)))
        self.tabs.addTab(page,'Heat-transfer paths')
        page=QWidget();phase_layout=QVBoxLayout(page);controls=QHBoxLayout();phase_layout.addLayout(controls)
        self.phase_selector=QComboBox();self.phase_selector.currentIndexChanged.connect(self.select_phase);controls.addWidget(self.phase_selector,1)
        self.buttons(controls,(('Add phase',self.add_phase),('Remove phase',self.remove_phase),('Move earlier',lambda:self.move_phase(-1)),('Move later',lambda:self.move_phase(1))))
        form=QFormLayout();phase_layout.addLayout(form);self.phase_fields={}
        for key,label in (('name','Phase name'),('duration_s','Duration (seconds)'),('ambient_c','Imposed ambient temperature (°C)')):
            w=QLineEdit();w.textEdited.connect(self.changed);self.phase_fields[key]=w;form.addRow(label,w)
        self.source_case=QComboBox();self.source_case.currentIndexChanged.connect(self.changed);form.addRow('Retained operating case for context',self.source_case)
        tables=QHBoxLayout();phase_layout.addLayout(tables,1);self.heat=self.table(['Body','Heat input (W)']);self.conductance=self.table(['Path','Conductance (W/K)']);tables.addWidget(self.heat);tables.addWidget(self.conductance)
        self.loss_basis=QTextEdit();self.cooling_basis=QTextEdit()
        for label,w in (('Heat-source allocation and evidence',self.loss_basis),('Conductance, airflow and model-range evidence',self.cooling_basis)):
            w.setAcceptRichText(False);w.setMaximumHeight(80);w.textChanged.connect(self.changed);phase_layout.addWidget(QLabel(label));phase_layout.addWidget(w)
        self.tabs.addTab(page,'Ordered thermal phases')
        page=QWidget();trajectory=QVBoxLayout(page);controls=QHBoxLayout();trajectory.addLayout(controls)
        self.cycle_selector=QComboBox();self.cycle_selector.addItems(['Entered sequence','Settled repeated cycle']);self.cycle_selector.currentIndexChanged.connect(self.select_cycle);controls.addWidget(self.cycle_selector)
        self.plot_phase=QComboBox();self.plot_phase.currentIndexChanged.connect(self.update_plot);controls.addWidget(self.plot_phase,1)
        self.plot_body=QComboBox();self.plot_body.currentIndexChanged.connect(self.update_plot);controls.addWidget(self.plot_body)
        self.early=QCheckBox('Expand early times');self.early.toggled.connect(self.update_plot);controls.addWidget(self.early)
        self.plot=TemperaturePlot();trajectory.addWidget(self.plot,1);self.plot_summary=QLabel();self.plot_summary.setWordWrap(True);trajectory.addWidget(self.plot_summary);self.tabs.addTab(page,'Temperature history')
        page=QWidget();provenance=QVBoxLayout(page);self.source_view=QTextBrowser();provenance.addWidget(self.source_view,1)
        self.sequence_basis=QTextEdit();self.notes=QTextEdit()
        for label,w in (('Chronology, repeat pattern and relation to lifetime duty',self.sequence_basis),('Model assumptions and omitted effects',self.notes)):
            w.setAcceptRichText(False);w.setMaximumHeight(95);w.textChanged.connect(self.changed);provenance.addWidget(QLabel(label));provenance.addWidget(w)
        self.tabs.addTab(page,'Source and evidence');self.report=QTextBrowser();self.report.setOpenExternalLinks(False);self.tabs.addTab(self.report,'Assessment')
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status);controls=QHBoxLayout();layout.addLayout(controls)
        self.buttons(controls,(('Open study…',self.open_study),('New from gear study…',self.open_source),('Synthetic example',self.load_example),
            ('Save study…',self.save_study),('Calculate',self.calculate),('Export assessment…',self.export),('Close',self.reject)))
        self.set_study(study or thermal_from_study(EngineeringStudy()))

    @staticmethod
    def buttons(layout,items):
        for label,callback in items:
            button=QPushButton(label);button.clicked.connect(callback);layout.addWidget(button)
    def table(self,headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers);table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);table.horizontalHeader().setStretchLastSection(True);table.itemChanged.connect(self.changed);return table
    @staticmethod
    def optional(text):return None if not text.strip() else float(text)
    def changed(self,*_):
        if self._loading:return
        self.dirty=True;self.result=None;self.report.clear();self.plot.set_data([],'');self.plot_summary.clear();self.status.setText('Inputs changed. Calculate again to update temperature history and limits.')
    def show_error(self,error):QMessageBox.warning(self,'Thermal study',str(error))

    def set_study(self,study):
        study.validate();self.model=ThermalStudy.from_dict(asdict(study));self.body_index=self.phase_index=0;self._loading=True
        self.name.setText(study.name);self.sequence_basis.setPlainText(study.sequence_basis);self.notes.setPlainText(study.notes)
        self.source_view.setHtml(f"<h2>{html.escape(study.source.name)}</h2><p>Losses and chronological phases are entered independently. The source operating cases are retained for traceability.</p><pre>{html.escape(json.dumps(asdict(study.source),indent=2))}</pre>")
        self.source_case.clear();self.source_case.addItems([p.name for p in study.source.duty])
        self.result=None;self.report.clear();self.plot.set_data([],'');self.plot_summary.clear();self.dirty=False
        self.load_forms();self.status.setText('Enter thermal capacities, initial temperatures, heat sources and cooling paths. Blank values remain unassessed.')

    def load_forms(self):
        self._loading=True
        try:
            self.body_selector.clear();self.body_selector.addItems([n.name for n in self.model.nodes]);self.body_selector.setCurrentIndex(self.body_index)
            self.phase_selector.clear();self.phase_selector.addItems([p.name for p in self.model.phases]);self.phase_selector.setCurrentIndex(self.phase_index)
            node=self.model.nodes[self.body_index]
            for key,w in self.body_fields.items():
                value=getattr(node,key)
                if isinstance(w,QComboBox):w.setCurrentIndex(w.findData(value))
                elif isinstance(w,QTextEdit):w.setPlainText(value)
                else:w.setText('' if value is None else str(value))
            self.paths.setRowCount(len(self.model.links));names=[n.name for n in self.model.nodes]
            for row,link in enumerate(self.model.links):
                self.paths.setItem(row,0,QTableWidgetItem(link.name))
                for col,value in ((1,link.first),(2,link.second)):
                    combo=QComboBox();combo.addItems(names+([AMBIENT] if col==2 else []));combo.setCurrentText(value);combo.currentIndexChanged.connect(self.changed);self.paths.setCellWidget(row,col,combo)
            phase=self.model.phases[self.phase_index]
            for key,w in self.phase_fields.items():
                value=getattr(phase,key);w.setText('' if value is None else str(value))
            self.source_case.setCurrentText(phase.source_case);self.loss_basis.setPlainText(phase.loss_basis);self.cooling_basis.setPlainText(phase.cooling_basis)
            self.phase_node_names=names;self.phase_link_names=[link.name for link in self.model.links]
            for table,keys,values in ((self.heat,names,phase.heat_w),(self.conductance,self.phase_link_names,phase.conductance_w_per_k)):
                table.setRowCount(len(keys))
                for row,key in enumerate(keys):
                    item=QTableWidgetItem(key);item.setFlags(item.flags() & ~Qt.ItemIsEditable);table.setItem(row,0,item)
                    value=values[key];table.setItem(row,1,QTableWidgetItem('' if value is None else str(value)))
        finally:self._loading=False

    def capture_forms(self):
        # Build a detached draft first: failed edits must not corrupt the editor model.
        draft=copy.deepcopy(self.model);phase=draft.phases[self.phase_index]
        phase.name=self.phase_fields['name'].text();phase.duration_s=float(self.phase_fields['duration_s'].text());phase.ambient_c=self.optional(self.phase_fields['ambient_c'].text())
        phase.source_case=self.source_case.currentText();phase.loss_basis=self.loss_basis.toPlainText();phase.cooling_basis=self.cooling_basis.toPlainText()
        phase.heat_w={key:self.optional(self.heat.item(row,1).text()) for row,key in enumerate(self.phase_node_names)}
        phase.conductance_w_per_k={key:self.optional(self.conductance.item(row,1).text()) for row,key in enumerate(self.phase_link_names)}
        new_links=[ThermalLink(self.paths.item(row,0).text(),self.paths.cellWidget(row,1).currentText(),self.paths.cellWidget(row,2).currentText()) for row in range(self.paths.rowCount())]
        if len({link.name for link in new_links})!=len(new_links):raise ValueError('Thermal path names must be unique')
        for p in draft.phases:p.conductance_w_per_k={new.name:p.conductance_w_per_k[old.name] for old,new in zip(draft.links,new_links,strict=True)}
        draft.links=new_links;old=draft.nodes[self.body_index].name;node=draft.nodes[self.body_index]
        for key,w in self.body_fields.items():
            if isinstance(w,QComboBox):value=w.currentData()
            elif isinstance(w,QTextEdit):value=w.toPlainText()
            else:value=self.optional(w.text()) if key in self.BODY_NUMBERS else w.text()
            setattr(node,key,value)
        node.validate()
        if old!=node.name:
            if sum(n.name==node.name for n in draft.nodes)>1:raise ValueError('Thermal body names must be unique')
            for link in draft.links:
                if link.first==old:link.first=node.name
                if link.second==old:link.second=node.name
            for p in draft.phases:p.heat_w={node.name if name==old else name:value for name,value in p.heat_w.items()}
        draft.name=self.name.text();draft.sequence_basis=self.sequence_basis.toPlainText();draft.notes=self.notes.toPlainText()
        draft.validate();self.model=draft

    def read_study(self):self.capture_forms();self.load_forms();return ThermalStudy.from_dict(asdict(self.model))
    def select_body(self,index):
        if self._loading or index<0:return
        try:self.capture_forms();self.body_index=index
        except (ValueError,TypeError) as exc:
            self._loading=True;self.body_selector.setCurrentIndex(self.body_index);self._loading=False;self.show_error(exc);return
        self.load_forms()
    def select_phase(self,index):
        if self._loading or index<0:return
        try:self.capture_forms();self.phase_index=index
        except (ValueError,TypeError) as exc:
            self._loading=True;self.phase_selector.setCurrentIndex(self.phase_index);self._loading=False;self.show_error(exc);return
        self.load_forms()
    @staticmethod
    def unique(prefix,used):
        number=1
        while f'{prefix} {number}' in used:number+=1
        return f'{prefix} {number}'
    def change_structure(self,operation):
        try:self.capture_forms();operation();self.load_forms();self.changed()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        return True
    def add_body(self):
        def operation():
            if len(self.model.nodes)>=12:raise ValueError('At most 12 bodies are supported')
            name=self.unique('Body',{n.name for n in self.model.nodes});self.model.nodes.append(ThermalNode(name=name))
            for phase in self.model.phases:phase.heat_w[name]=None
            self.body_index=len(self.model.nodes)-1
        return self.change_structure(operation)
    def remove_body(self):
        def operation():
            if len(self.model.nodes)==1:raise ValueError('Retain at least one thermal body')
            name=self.model.nodes.pop(self.body_index).name;removed={link.name for link in self.model.links if name in (link.first,link.second)}
            self.model.links=[link for link in self.model.links if link.name not in removed]
            for phase in self.model.phases:
                phase.heat_w.pop(name)
                for path in removed:phase.conductance_w_per_k.pop(path)
            self.body_index=min(self.body_index,len(self.model.nodes)-1)
        return self.change_structure(operation)
    def add_path(self):
        def operation():
            if len(self.model.links)>=60:raise ValueError('At most 60 thermal paths are supported')
            names=[n.name for n in self.model.nodes];used={frozenset((l.first,l.second)) for l in self.model.links}
            pair=next(((a,b) for a in names for b in [AMBIENT,*names] if a!=b and frozenset((a,b)) not in used),None)
            if pair is None:raise ValueError('Every pair already has a heat-transfer path')
            name=self.unique('Path',{l.name for l in self.model.links});self.model.links.append(ThermalLink(name,*pair))
            for phase in self.model.phases:phase.conductance_w_per_k[name]=None
        return self.change_structure(operation)
    def remove_path(self):
        row=self.paths.currentRow()
        if row<0:return False
        def operation():
            name=self.model.links.pop(row).name
            for phase in self.model.phases:phase.conductance_w_per_k.pop(name)
        return self.change_structure(operation)
    def add_phase(self):
        def operation():
            if len(self.model.phases)>=200:raise ValueError('At most 200 phases are supported')
            phase=copy.deepcopy(self.model.phases[self.phase_index]);phase.name=self.unique('Phase',{p.name for p in self.model.phases})
            self.model.phases.insert(self.phase_index+1,phase);self.phase_index+=1
        return self.change_structure(operation)
    def remove_phase(self):
        def operation():
            if len(self.model.phases)==1:raise ValueError('Retain at least one thermal phase')
            self.model.phases.pop(self.phase_index);self.phase_index=min(self.phase_index,len(self.model.phases)-1)
        return self.change_structure(operation)
    def move_phase(self,delta):
        def operation():
            target=self.phase_index+delta
            if not 0<=target<len(self.model.phases):return
            self.model.phases[self.phase_index],self.model.phases[target]=self.model.phases[target],self.model.phases[self.phase_index];self.phase_index=target
        return self.change_structure(operation)

    def calculate(self):
        try:
            self.result=calculate_thermal_study(self.read_study());self.report.setHtml(thermal_report_html(self.result))
            self.plot_body.clear();self.plot_body.addItems([n['name'] for n in self.result['nodes']]);self.select_cycle();self.tabs.setCurrentWidget(self.report)
            count=len(self.result['findings']);self.status.setText(f'Calculated conditional temperatures · {count} numerical/equilibrium findings · no production gearbox rating.');return True
        except (ValueError,TypeError,RuntimeError,OverflowError) as exc:
            self.result=None;self.report.clear();self.plot.set_data([],'');self.show_error(exc);return False
    def select_cycle(self,*_):
        self.plot_phase.clear()
        if self.result is None:return
        rows=self.result['phases'] if self.cycle_selector.currentIndex()==0 else ([] if self.result['periodic_cycle'] is None else self.result['periodic_cycle']['phases'])
        self.plot_phase.addItems([row['name'] for row in rows]);self.update_plot()
    def update_plot(self,*_):
        if self.result is None:return
        rows=self.result['phases'] if self.cycle_selector.currentIndex()==0 else ([] if self.result['periodic_cycle'] is None else self.result['periodic_cycle']['phases'])
        index=self.plot_phase.currentIndex();body=self.plot_body.currentText()
        if not rows or index<0 or not body:self.plot.set_data([],'');self.plot_summary.setText('Temperature history unavailable for this cycle.');return
        row=rows[index];self.plot.set_data(row['profile'],body,self.early.isChecked())
        if not row['extrema']:self.plot_summary.setText(row['unavailable_reason']);return
        extreme=next(n for n in row['extrema'] if n['name']==body)
        self.plot_summary.setText(f"{body}: minimum {extreme['minimum_c']:.8g} °C at {extreme['minimum_at_s']:.8g} s; maximum {extreme['maximum_c']:.8g} °C at {extreme['maximum_at_s']:.8g} s. Energy residual {row['energy_residual_j']:.5g} J. Continuous extrema are checked independently of drawing samples.")
    def save_study(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Save thermal study',str(self.path or 'gearbox.gearforge-thermal'),'Thermal study (*.gearforge-thermal)')
        if not path:return False
        try:study.save(Path(path))
        except (ValueError,OSError) as exc:self.show_error(exc);return False
        self.path=Path(path);self.dirty=False;self.status.setText(f'Saved {self.path.name}');return True
    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved thermal study','Save this study before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        return self.save_study() if answer==QMessageBox.Save else answer==QMessageBox.Discard
    def open_study(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Open thermal study','','Thermal study (*.gearforge-thermal)')
        if not path:return False
        try:study=ThermalStudy.load(Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=Path(path);return True
    def open_source(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Open retained gear study','','Gear study (*.gearforge-study)')
        if not path:return False
        try:study=thermal_from_study(EngineeringStudy.load(Path(path)))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=None;self.dirty=True;return True
    def load_example(self):
        if not self.confirm_discard():return False
        self.set_study(synthetic_thermal_example());self.path=None;self.dirty=True;return True
    def export(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Choose a new thermal assessment folder','thermal-assessment','Assessment folder (*)')
        if not path:return False
        try:export_thermal_study(study,Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.status.setText(f'Exported {Path(path).name}');return True
    def reject(self):
        if self.confirm_discard():super().reject()
    def closeEvent(self,event):
        if self.confirm_discard():event.accept()
        else:event.ignore()
