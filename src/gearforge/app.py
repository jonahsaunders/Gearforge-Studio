from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sqlite3
import sys
import tempfile
from dataclasses import asdict, fields
from pathlib import Path

from PySide6.QtCore import QEvent, QProcess, QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton, QInputDialog,
    QScrollArea, QSlider, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QSizePolicy, QTabWidget, QTextBrowser, QTextEdit, QVBoxLayout, QWidget,
)

from . import __version__
from .calibration import calibrate_profile
from .catalog import Catalog
from .exporting import report_html
from .models import FAMILIES, MODES, Candidate, PrintProfile, Project, Requirements, atomic_text, candidate_from_dict, read_text_limited
from .viewer import AssemblyViewer

from .appearance import STYLE, apply_appearance, system_reduced_motion
from .simulation import operating_sweep, shaft_rates
from .plots import OperatingPlot
from .layouts import FlowLayout


def label(text,name=None):
    widget=QLabel(text)
    if name:widget.setObjectName(name)
    return widget


def table(headers):
    result=QTableWidget(0,len(headers))
    result.setHorizontalHeaderLabels(headers)
    result.setAlternatingRowColors(True)
    result.setSelectionBehavior(QTableWidget.SelectRows)
    result.setEditTriggers(QTableWidget.NoEditTriggers)
    result.verticalHeader().hide()
    result.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    result.horizontalHeader().setStretchLastSection(True)
    return result


def fill_table(widget,rows):
    widget.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            item=QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            widget.setItem(i,j,item)


def number(value,minimum,maximum,decimals=2,suffix=""):
    widget=QDoubleSpinBox()
    widget.setRange(minimum,maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setSuffix(suffix)
    widget.setKeyboardTracking(False)
    return widget


class MainWindow(QMainWindow):
    def __init__(self,data_dir=None):
        super().__init__()
        self.setWindowTitle("Untitled gearbox[*] — GearForge Studio")
        self.resize(1340,920)
        self.setMinimumSize(1100,720)
        self.data_dir=Path(data_dir or os.environ.get("GEARFORGE_DATA_DIR") or QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
        self.data_dir.mkdir(parents=True,exist_ok=True)
        from .maintenance import lock_data_directory
        self.data_lock=lock_data_directory(self.data_dir)
        try:self.catalog=Catalog(self.data_dir/"catalog.sqlite")
        except Exception:
            self.data_lock.unlock();raise
        self.project=Project()
        self.path=None
        self.dirty=False
        self.candidates=[]
        self.selected=None
        self.result_snapshot=None
        self.process=None
        self.job_temp=None
        self.job_callback=None
        self.fields={}
        self.profile_fields={}
        self.settings=QSettings(str(self.data_dir/"settings.ini"),QSettings.IniFormat)
        apply_appearance(self.settings)
        self.reduced_motion=self.settings.value("reduced_motion",system_reduced_motion(),type=bool)
        self._menus()
        self._layout()
        self._accessibility()
        self.populate()
        self.refresh_catalog()
        self.statusBar().showMessage("Offline workspace ready · all design results are preliminary")
        self.autosave=QTimer(self)
        self.autosave.setInterval(30000)
        self.autosave.timeout.connect(self.save_recovery)
        self.autosave.start()
        geometry=self.settings.value("geometry")
        if geometry:self.restoreGeometry(geometry)
        splitter_state=self.settings.value("design_splitter")
        if splitter_state:self.design_splitter.restoreState(splitter_state)
        self.sidebar.setVisible(self.settings.value("sidebar_visible",True,type=bool))
        self.sidebar_action.setChecked(self.sidebar.isVisibleTo(self))
        self.sync_actions()
        self.update_text_metrics()

    def update_text_metrics(self):
        self.sidebar.setMinimumWidth(max(225,self.nav.fontMetrics().horizontalAdvance("Simulation workspace")+50))
        self.navigate(self.nav.currentRow())

    def _accessibility(self):
        for form in self.findChildren(QFormLayout):
            for row in range(form.rowCount()):
                label_item=form.itemAt(row,QFormLayout.LabelRole);field_item=form.itemAt(row,QFormLayout.FieldRole)
                if label_item and field_item and isinstance(label_item.widget(),QLabel) and field_item.widget():
                    label_item.widget().setBuddy(field_item.widget());field_item.widget().setAccessibleName(label_item.widget().text())
        for w,name in [(self.nav,"Workspace navigation"),(self.project_name,"Project name"),(self.mode,"Manufacturing mode"),
                       (self.stages,"Maximum stages"),(self.priority,"Design priority"),(self.catalog_query,"Search component catalog"),
                       (self.candidate_table,"Generated gearbox alternatives"),(self.check_table,"Engineering checks and assumptions"),
                       (self.stage_table,"Gear train stages"),(self.bom_table,"Bill of materials"),(self.catalog_table,"Component catalog"),
                       (self.sim_table,"Operating points, including overload status"),(self.explode_slider,"Assembly exploded view separation")]:
            w.setAccessibleName(name)
        self.viewer.reduced_motion=self.reduced_motion

    def _menus(self):
        self.command_actions={}
        file=self.menuBar().addMenu("File")
        actions=[("New project",self.new_project,QKeySequence.New),("Open project…",self.open_project,QKeySequence.Open),
                 ("Save project",self.save_project,QKeySequence.Save),("Save project as…",lambda:self.save_project(True),QKeySequence.SaveAs),
                 ("Export selected design…",self.export_selected,"Ctrl+Shift+E"),("Restore autosave…",self.restore_recovery,None),("Quit",self.close,QKeySequence.Quit)]
        for title,callback,shortcut in actions:
            action=QAction(title,self)
            action.triggered.connect(lambda checked=False,cb=callback:cb())
            if shortcut:action.setShortcut(shortcut)
            if title=="Quit":action.setMenuRole(QAction.QuitRole)
            file.addAction(action)
            self.command_actions[title]=action
        design=self.menuBar().addMenu("Design")
        for title,callback,shortcut in [("Engineering study…",self.engineering_study,None),("Shaft and bearing loads…",self.shaft_study,None),("Bearing duty and capacity…",self.bearing_study,None),("Shaft fatigue and material evidence…",self.fatigue_study,None),("Study selected stage…",self.study_selected_stage,None),("Generate designs",self.generate,"Ctrl+Return"),("Load CAD preview",self.load_preview,"Ctrl+Shift+L"),("Sample tooth meshing…",self.check_mesh,None),("Compare selected rows",self.compare,None)]:
            action=QAction(title,self);action.triggered.connect(callback)
            if shortcut:action.setShortcut(shortcut)
            design.addAction(action)
            self.command_actions[title]=action
        view=self.menuBar().addMenu("View")
        self.sidebar_action=QAction("Show sidebar",self,checkable=True,checked=True)
        self.sidebar_action.setShortcut("Ctrl+Alt+S")
        self.sidebar_action.toggled.connect(lambda shown:self.sidebar.setVisible(shown));view.addAction(self.sidebar_action)
        for title,callback in [("Reset 3D view",lambda:self.viewer.reset_view()),("Step one input tooth",lambda:self.viewer.step())]:
            action=QAction(title,self);action.triggered.connect(callback);view.addAction(action)
        settings_action=QAction("Settings…",self);settings_action.setMenuRole(QAction.PreferencesRole)
        settings_action.setShortcut("Ctrl+,");settings_action.triggered.connect(self.preferences);view.addAction(settings_action)
        window=self.menuBar().addMenu("Window")
        minimize=QAction("Minimize",self);minimize.setShortcut("Ctrl+M");minimize.triggered.connect(self.showMinimized);window.addAction(minimize)
        helpmenu=self.menuBar().addMenu("Help")
        action=QAction("About and release status",self)
        action.setMenuRole(QAction.AboutRole)
        action.triggered.connect(lambda:QMessageBox.information(self,"GearForge Studio",f"GearForge Studio {__version__}\n\nDesktop release candidate. Spur, helical and planetary prototype CAD; bevel, worm and cycloidal concept searches.\n\nEngineering calculations are preliminary screens, not certified load ratings. No network or telemetry.\n\nApplication code: Apache-2.0. Uses PySide6/Qt under LGPLv3 terms; bundled dependencies retain their own licenses."))
        helpmenu.addAction(action)
        licenses=QAction("Open third-party license notices…",self);licenses.triggered.connect(self.open_licenses);helpmenu.addAction(licenses)

    def engineering_study(self):
        from .engineering_ui import EngineeringStudyDialog
        EngineeringStudyDialog(self).exec()

    def shaft_study(self):
        from .shaft_ui import ShaftStudyDialog
        from .shafts import shaft_from_gear_study
        from .engineering import EngineeringStudy
        ShaftStudyDialog(self,shaft_from_gear_study(EngineeringStudy())).exec()

    def bearing_study(self):
        from .bearing_ui import BearingStudyDialog
        from .bearings import bearings_from_shaft
        from .shafts import shaft_from_gear_study
        from .engineering import EngineeringStudy
        BearingStudyDialog(self,bearings_from_shaft(shaft_from_gear_study(EngineeringStudy()))).exec()

    def fatigue_study(self):
        from .fatigue_ui import FatigueStudyDialog
        from .fatigue import fatigue_from_shaft
        from .shafts import shaft_from_gear_study
        from .engineering import EngineeringStudy
        FatigueStudyDialog(self,fatigue_from_shaft(shaft_from_gear_study(EngineeringStudy()))).exec()

    def study_selected_stage(self):
        from .engineering import study_for_stage
        from .engineering_ui import EngineeringStudyDialog
        from .models import Requirements
        try:
            payload=self.ready_payload();index=0
            if len(self.selected.stages)>1:
                choices=[f"Stage {i+1}: {s.driver.teeth} / {s.driven.teeth} teeth" for i,s in enumerate(self.selected.stages)]
                choice,ok=QInputDialog.getItem(self,"Study selected stage","Gear stage",choices,0,False)
                if not ok:return
                index=choices.index(choice)
            study=study_for_stage(self.selected,Requirements(**payload["requirements"]),index)
            dialog=EngineeringStudyDialog(self);dialog.set_study(study);dialog.dirty=True;dialog.exec()
        except (ValueError,TypeError) as exc:self.error(exc)

    def open_licenses(self):
        path=Path(sys._MEIPASS)/"licenses" if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[2]/"release-licenses"
        if path.is_dir():QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:QMessageBox.information(self,"License notices","Application code: Apache-2.0. Dependencies retain their licenses.\n\nSource releases include THIRD_PARTY_NOTICES.md; native bundles include collected license files. For an installed Python environment, inspect its exact distribution metadata and upstream notices.")

    def preferences(self):
        dialog=QDialog(self);dialog.setWindowTitle("Settings");form=QFormLayout(dialog)
        appearance=QComboBox();appearance.addItems(["System","Light","Dark"])
        appearance.setCurrentIndex(["system","light","dark"].index(self.settings.value("appearance","system")))
        form.addRow("Appearance",appearance)
        textsize=QComboBox();textsize.addItems(["Default","Larger (115%)","Largest (130%)"])
        textsize.setCurrentIndex(min(range(3),key=lambda i:abs([1,1.15,1.3][i]-float(self.settings.value("text_scale",1.)))))
        form.addRow("Interface text",textsize)
        motion=QCheckBox("Use single-step simulation instead of playback");motion.setChecked(self.reduced_motion);form.addRow("Reduce motion",motion)
        note=QLabel("macOS Reduce Motion is read at launch. Simulation playback always requires an explicit action.");note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.Accepted:
            self.settings.setValue("appearance",["system","light","dark"][appearance.currentIndex()]);self.settings.setValue("text_scale",[1,1.15,1.3][textsize.currentIndex()])
            self.settings.setValue("reduced_motion",motion.isChecked());self.reduced_motion=motion.isChecked();self.viewer.reduced_motion=self.reduced_motion
            if self.reduced_motion:self.viewer.animate(False)
            self.animate_box.setEnabled(not self.reduced_motion);apply_appearance(self.settings)
            self.update_text_metrics()

    def _layout(self):
        root=QWidget();self.setCentralWidget(root)
        layout=QHBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        sidebar=QWidget();self.sidebar=sidebar;sidebar.setMinimumWidth(225);sidebar.setMaximumWidth(320);side=QVBoxLayout(sidebar)
        side.setContentsMargins(16,25,12,16)
        side.addWidget(label("GearForge","brand"))
        tagline=label("TRANSMISSION STUDIO","eyebrow");tagline.setWordWrap(True);side.addWidget(tagline)
        side.addSpacing(25)
        self.nav=QListWidget();self.nav.setObjectName("nav")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);self.nav.setTextElideMode(Qt.ElideRight)
        self.nav.addItems(["Design workspace","Component catalog","Print calibration","Design report","Simulation workspace"])
        side.addWidget(self.nav)
        side.addWidget(label("LOCAL / OFFLINE","eyebrow"))
        side.addWidget(label("Version "+__version__,"subtle"))
        shell=QSplitter(Qt.Horizontal);shell.addWidget(sidebar);layout.addWidget(shell)
        content=QWidget();column=QVBoxLayout(content);column.setContentsMargins(24,20,24,12)
        header=QHBoxLayout()
        self.title=label("Design workspace","title");header.addWidget(self.title)
        self.title.setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Preferred)
        header.addStretch()
        self.project_name=QLineEdit(self.project.name);self.project_name.setMaximumWidth(270)
        self.project_name.textChanged.connect(self.mark_dirty)
        header.addWidget(self.project_name)
        save=QPushButton("Save project");save.clicked.connect(lambda:self.save_project());header.addWidget(save)
        column.addLayout(header)
        self.job_bar=QProgressBar();self.job_bar.hide();column.addWidget(self.job_bar)
        busyrow=QHBoxLayout();self.job_status=label("","subtle");busyrow.addWidget(self.job_status)
        busyrow.addStretch();self.cancel_button=QPushButton("Cancel job");self.cancel_button.clicked.connect(self.cancel_job);self.cancel_button.hide();busyrow.addWidget(self.cancel_button)
        column.addLayout(busyrow)
        self.pages=QStackedWidget();column.addWidget(self.pages)
        self._design_page();self._catalog_page();self._profile_page();self._report_page()
        self.pages.addWidget(self.simulation_page)
        self.nav.currentRowChanged.connect(self.navigate)
        self.nav.setCurrentRow(0)
        shell.addWidget(content);shell.setSizes([240,1100]);shell.setStretchFactor(1,1)

    def navigate(self,index):
        if index<0:return
        self.pages.setCurrentIndex(index)
        self.title.setText(["Design workspace","Component catalog","Print calibration","Design report","Simulation workspace"][index])
        self.title.ensurePolished();self.title.setMinimumWidth(self.title.fontMetrics().horizontalAdvance(self.title.text())+8)
        if index==3:self.update_report()

    def _design_page(self):
        page=QWidget();outer=QVBoxLayout(page);outer.setContentsMargins(0,0,0,0)
        self.notice=label("Generate alternatives from requirements. Prototype geometry and engineering screens require validation.","subtle")
        self.notice.setWordWrap(True);outer.addWidget(self.notice)
        splitter=QSplitter(Qt.Horizontal);self.design_splitter=splitter;outer.addWidget(splitter)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumWidth(330);scroll.setMaximumWidth(440)
        form_widget=QWidget();form=QVBoxLayout(form_widget);form.setContentsMargins(10,10,18,10)
        form.addWidget(label("OPERATING REQUIREMENTS","eyebrow"))
        fieldform=QFormLayout();fieldform.setVerticalSpacing(12)
        fieldform.setRowWrapPolicy(QFormLayout.WrapLongRows)
        configs=[("input_rpm","Input speed",1200,.1,100000,1," rpm"),("input_torque_nm","Motor torque",.08,.0001,100000,4," N·m"),
                 ("output_rpm","Output speed",100,.01,100000,2," rpm"),("output_torque_nm","Required torque",.65,.0001,100000,4," N·m")]
        for key,title,value,lo,hi,dec,suffix in configs:
            w=number(value,lo,hi,dec,suffix);self.fields[key]=w;fieldform.addRow(title,w);w.valueChanged.connect(self.mark_dirty)
        form.addLayout(fieldform)
        self.ratio_label=label("Target reduction: 12:1","eyebrow");form.addWidget(self.ratio_label)
        self.fields["input_rpm"].valueChanged.connect(self.update_ratio);self.fields["output_rpm"].valueChanged.connect(self.update_ratio)
        form.addSpacing(14);form.addWidget(label("MANUFACTURING","eyebrow"))
        self.mode=QComboBox();self.mode.addItems(["Hybrid components","Printed gears","Commercial catalog gears"]);self.mode.currentIndexChanged.connect(self.mark_dirty);form.addWidget(self.mode)
        self.mode.setToolTip("Printed mode uses purchased steel shafts, bearings and fasteners. Commercial mode uses catalog gears and a custom machined housing.")
        familylayout=QGridLayout();self.families={}
        for i,f in enumerate(FAMILIES):
            w=QCheckBox(f.title());w.toggled.connect(self.mark_dirty);self.families[f]=w;familylayout.addWidget(w,i//2,i%2)
            if f in ("bevel","worm","cycloidal"):w.setToolTip("Concept search only; no detailed manufacturing geometry or tooth simulation")
        form.addLayout(familylayout)
        concepts=label("Bevel, worm and cycloidal: concept layouts.","subtle");concepts.setWordWrap(True);form.addWidget(concepts)
        self.stages=QComboBox();self.stages.addItems(["Up to 2 stages","Single stage only"]);self.stages.currentIndexChanged.connect(self.mark_dirty);form.addWidget(self.stages)
        form.addSpacing(12);form.addWidget(label("MAXIMUM ENVELOPE","eyebrow"))
        envelope=QFormLayout()
        for key,text,default in [("max_x_mm","Width X",250),("max_y_mm","Depth Y",180),("max_z_mm","Height Z",110)]:
            w=number(default,20,2000,1," mm");self.fields[key]=w;envelope.addRow(text,w);w.valueChanged.connect(self.mark_dirty)
        form.addLayout(envelope)
        self.priority=QComboBox();self.priority.addItems(["Balanced","Smallest package","Lowest cost estimate","Highest efficiency","Lowest backlash"]);self.priority.currentIndexChanged.connect(self.mark_dirty);form.addWidget(self.priority)
        advanced=QPushButton("Advanced constraints…");advanced.setToolTip("Load, life, safety, motor curve and supplier filters");advanced.clicked.connect(self.advanced_dialog);form.addWidget(advanced)
        profile_note=label("Print profile: edit under Print calibration.","subtle");profile_note.setWordWrap(True);form.addWidget(profile_note)
        self.generate_button=QPushButton("Generate designs  →");self.generate_button.setObjectName("primary");self.generate_button.clicked.connect(self.generate);form.addWidget(self.generate_button)
        form.addStretch();scroll.setWidget(form_widget);splitter.addWidget(scroll)
        right=QWidget();rightlayout=QVBoxLayout(right);rightlayout.setContentsMargins(10,0,0,0)
        metrics=QHBoxLayout();self.metrics={}
        for key,caption in [("ratio","REDUCTION"),("rpm","OUTPUT RPM"),("torque","AVAILABLE N·m"),("eff","EFFICIENCY")]:
            card=QFrame();card.setObjectName("card");cardlayout=QVBoxLayout(card)
            value=label("—","metricValue");self.metrics[key]=value;cardlayout.addWidget(value);cardlayout.addWidget(label(caption,"metricCaption"));metrics.addWidget(card)
        rightlayout.addLayout(metrics)
        self.viewer=AssemblyViewer();rightlayout.addWidget(self.viewer,3)
        toolrow=QWidget();tools=FlowLayout(toolrow);self.cad_button=QPushButton("Load 3D CAD");self.cad_button.clicked.connect(self.load_preview);tools.addWidget(self.cad_button)
        reset=QPushButton("Reset view");reset.clicked.connect(self.viewer.reset_view);tools.addWidget(reset)
        self.animate_box=QCheckBox("Play");self.animate_box.toggled.connect(self.viewer.animate);self.animate_box.setEnabled(not self.reduced_motion);tools.addWidget(self.animate_box)
        self.viewer.playbackChanged.connect(self.animate_box.setChecked)
        show=QCheckBox("Housing");show.toggled.connect(lambda v:(setattr(self.viewer,"show_housing",v),self.viewer.update()));tools.addWidget(show)
        tools.addWidget(label("Explode","subtle"));explode=QSlider(Qt.Horizontal);self.explode_slider=explode;explode.setMaximumWidth(110);explode.setRange(0,100);explode.valueChanged.connect(lambda v:(setattr(self.viewer,"explode",v/25),self.viewer.update()));tools.addWidget(explode)
        rightlayout.addWidget(toolrow)
        simrow=QWidget();simtools=FlowLayout(simrow)
        step=QPushButton("Step tooth");step.clicked.connect(self.viewer.step);simtools.addWidget(step)
        simtools.addWidget(label("Time scale"));self.time_scale=QComboBox();self.time_scale.addItems(["0.001×","0.01×","0.1×","1×"]);self.time_scale.setCurrentIndex(1);self.time_scale.setMaximumWidth(95)
        self.time_scale.setAccessibleName("Playback time scale");self.time_scale.currentIndexChanged.connect(lambda i:setattr(self.viewer.clock,"time_scale",[.001,.01,.1,1][i]));simtools.addWidget(self.time_scale)
        self.reverse=QCheckBox("Reverse");self.reverse.toggled.connect(lambda v:setattr(self.viewer.clock,"speed_factor",-1. if v else 1.));simtools.addWidget(self.reverse)
        self.sim_time=number(0,0,3600,4," s");self.sim_time.setAccessibleName("Seek simulation time");self.sim_time.setMaximumWidth(130)
        self.sim_time.editingFinished.connect(lambda:self.viewer.seek(self.sim_time.value()));simtools.addWidget(self.sim_time)
        self.viewer.timeChanged.connect(self.simulation_time_changed);rightlayout.addWidget(simrow)
        candidatetitle=QHBoxLayout();self.candidate_count=label("CANDIDATE DESIGNS","eyebrow");candidatetitle.addWidget(self.candidate_count);candidatetitle.addStretch()
        compare=QPushButton("Compare selected");self.compare_button=compare;compare.clicked.connect(self.compare);candidatetitle.addWidget(compare)
        export=QPushButton("Export design…");self.export_button=export;export.clicked.connect(lambda:self.export_selected(True));candidatetitle.addWidget(export);rightlayout.addLayout(candidatetitle)
        self.candidate_table=table(["Score","Family / stages","Ratio","Efficiency","Backlash °","Envelope mm","Status"])
        self.candidate_table.setSelectionMode(QTableWidget.ExtendedSelection);self.candidate_table.itemSelectionChanged.connect(self.selection_changed)
        self.candidate_table.setMinimumHeight(120);rightlayout.addWidget(self.candidate_table,2)
        self.inspection=QTabWidget();self.check_table=table(["Status","Check","Value","Limit","Method / assumptions"]);self.bom_table=table(["Part","Qty","Source","SKU","Description","Unit cost"])
        self.stage_table=table(["Stage","Driver","Driven","Module","Ratio","RPM in","Torque in","Torque out"])
        self.inspection.addTab(self.check_table,"Engineering checks");self.inspection.addTab(self.stage_table,"Gear train");self.inspection.addTab(self.bom_table,"Bill of materials")
        simulation=QWidget();simlayout=QVBoxLayout(simulation)
        self.sim_summary=label("Select a design to calculate its motor/load envelope.");self.sim_summary.setWordWrap(True);simlayout.addWidget(self.sim_summary)
        self.sim_plot=OperatingPlot();simlayout.addWidget(self.sim_plot)
        self.sim_table=table(["Input rpm","Output rpm","Available N·m","Input W","Output W","Loss W","Load margin N·m","Status"]);simlayout.addWidget(self.sim_table)
        row=QHBoxLayout();check=QPushButton("Check sampled tooth meshing…");self.mesh_check_button=check;check.clicked.connect(self.check_mesh);row.addWidget(check)
        save=QPushButton("Export simulation data…");self.sim_export_button=save;save.clicked.connect(self.export_simulation);row.addWidget(save);row.addStretch();simlayout.addLayout(row)
        self.mesh_summary=label("Exact tooth intersections have not been sampled.");self.mesh_summary.setWordWrap(True);simlayout.addWidget(self.mesh_summary)
        self.simulation_page=simulation
        self.sim_plot.setMinimumHeight(240);self.sim_plot.setMaximumHeight(320)
        self.sim_table.setMinimumHeight(200)
        simulation_link=QWidget();linklayout=QVBoxLayout(simulation_link)
        note=label("Inspect the motor/load envelope, power losses and sampled tooth intersections in the simulation workspace.");note.setWordWrap(True);linklayout.addWidget(note)
        open_sim=QPushButton("Open simulation workspace");open_sim.clicked.connect(lambda:self.nav.setCurrentRow(4));linklayout.addWidget(open_sim);linklayout.addStretch()
        self.inspection.addTab(simulation_link,"Simulation")
        self.inspection.setMinimumHeight(150);rightlayout.addWidget(self.inspection,2)
        splitter.addWidget(right);splitter.setSizes([330,850]);self.pages.addWidget(page)

    def _catalog_page(self):
        page=QWidget();column=QVBoxLayout(page)
        intro=label("Source-traceable component records. Catalog load ratings depend on supplier conditions; stock and prices require current quotations.","subtle");intro.setWordWrap(True);column.addWidget(intro)
        row=QHBoxLayout();self.catalog_query=QLineEdit();self.catalog_query.setPlaceholderText("Search SKU, supplier, module or material…");self.catalog_query.textChanged.connect(self.refresh_catalog);row.addWidget(self.catalog_query)
        for title,callback in [("Import CSV…",self.import_catalog),("Export CSV / template…",self.export_catalog)]:
            button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        column.addLayout(row)
        self.catalog_table=table(["SKU","Supplier","Family","Module","Teeth","Bore mm","Face mm","Bending N·m","Contact N·m","Price","Retrieved","Source"])
        self.catalog_table.cellDoubleClicked.connect(self.open_catalog_source);column.addWidget(self.catalog_table)
        column.addWidget(label("Double-click a row to open its supplier source. Import validates all rows before updating the SQLite catalog.","subtle"))
        self.pages.addWidget(page)

    def _profile_page(self):
        page=QWidget();column=QVBoxLayout(page)
        info=label("Dimensional calibration and material assumptions are separate. A coupon establishes dimensional compensation; load capability requires independent tests.","subtle");info.setWordWrap(True);column.addWidget(info)
        splitter=QSplitter(Qt.Horizontal)
        editor=QWidget();form=QFormLayout(editor)
        self.profile_name=QLineEdit();self.profile_material=QLineEdit();form.addRow("Profile name",self.profile_name);form.addRow("Material",self.profile_material)
        self.profile_name.textChanged.connect(self.mark_dirty);self.profile_material.textChanged.connect(self.mark_dirty)
        for key,title,lo,hi,dec,suffix in [
            ("allowable_mpa","Assumed allowable strength",.1,1000,2," MPa"),("modulus_mpa","Elastic modulus",1,300000,0," MPa"),
            ("density_g_cm3","Density",.1,25,3," g/cm³"),("cost_per_kg","Material cost / kg",0,10000,2,""),
            ("nozzle_mm","Nozzle diameter",.1,2,2," mm"),("layer_mm","Layer height",.03,1,2," mm"),
            ("backlash_mm","Total mesh backlash",.01,2,3," mm"),("bore_compensation_mm","Bore compensation",-1,2,3," mm"),
            ("shrink_percent","Uniform shrink",-3,10,3," %"),("bearing_clearance_mm","Bearing seat clearance",-.5,1,3," mm"),
            ("max_temperature_c","Screening temperature ceiling",-20,200,1," °C")]:
            w=number(getattr(self.project.profile,key),lo,hi,dec,suffix);self.profile_fields[key]=w;form.addRow(title,w);w.valueChanged.connect(self.mark_dirty)
        self.orientation=QLineEdit();form.addRow("Print orientation",self.orientation);self.orientation.textChanged.connect(self.mark_dirty)
        self.evidence=QTextEdit();self.evidence.setPlaceholderText("Test identifier, printer, orientation, temperatures, loading, measurements and uncertainty…");self.evidence.setMaximumHeight(100);form.addRow("Evidence / notes",self.evidence);self.evidence.textChanged.connect(self.mark_dirty)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(editor);splitter.addWidget(scroll)
        tools=QWidget();toolslayout=QVBoxLayout(tools)
        toolslayout.addWidget(label("DIMENSIONAL COUPON","eyebrow"))
        toolslayout.addWidget(label("Print the 40 × 40 × 6 mm coupon with a 10 mm center bore.\nMeasure the outside and bore after cooling.","subtle"))
        couponform=QFormLayout();self.outer_measure=number(40,1,500,3," mm");self.bore_measure=number(10,1,100,3," mm")
        couponform.addRow("Measured outside",self.outer_measure);couponform.addRow("Measured bore",self.bore_measure);toolslayout.addLayout(couponform)
        coupon=QPushButton("Export calibration coupon…");coupon.clicked.connect(self.export_coupon);toolslayout.addWidget(coupon)
        apply=QPushButton("Apply dimensional measurements");apply.clicked.connect(self.apply_calibration);toolslayout.addWidget(apply)
        toolslayout.addSpacing(24);toolslayout.addWidget(label("SAVED PRINT PROFILES","eyebrow"))
        self.profile_list=QListWidget();self.profile_list.itemDoubleClicked.connect(self.load_profile);toolslayout.addWidget(self.profile_list)
        save=QPushButton("Save current profile");save.clicked.connect(self.save_profile);toolslayout.addWidget(save)
        note=label("Strength values begin as conservative illustrative assumptions. Attaching evidence does not automatically certify a profile.","subtle");note.setWordWrap(True);toolslayout.addWidget(note)
        splitter.addWidget(tools);splitter.setSizes([600,450]);column.addWidget(splitter);self.pages.addWidget(page);self.refresh_profiles()

    def _report_page(self):
        page=QWidget();column=QVBoxLayout(page)
        tools=QHBoxLayout();tools.addWidget(label("Traceable calculations, assumptions and build documentation","subtle"));tools.addStretch()
        for title,callback in [("Export report only…",lambda:self.export_selected(False)),("Export full design…",self.export_selected)]:
            b=QPushButton(title);b.clicked.connect(lambda checked=False,cb=callback:cb());tools.addWidget(b)
        column.addLayout(tools);self.report_browser=QTextBrowser();self.report_browser.setOpenExternalLinks(False);column.addWidget(self.report_browser)
        self.pages.addWidget(page)

    def mark_dirty(self,*args):
        self.dirty=True
        if hasattr(self,"notice") and self.candidates:
            self.notice.setText("Requirements or profile changed. Regenerate designs before CAD/export.")
        self.setWindowModified(True)
        if hasattr(self,"evidence"):
            self.sync_actions()
            try:stale=self.result_snapshot and self.result_snapshot!=self.capture()
            except (ValueError,TypeError):stale=True
            if stale:self.viewer.animate(False)

    def update_ratio(self,*args):
        self.ratio_label.setText(f"Target reduction: {self.fields['input_rpm'].value()/self.fields['output_rpm'].value():.4g}:1")

    def capture(self):
        data=asdict(self.project.requirements)
        data.update({k:w.value() for k,w in self.fields.items()})
        data["mode"]=["hybrid","printed","commercial"][self.mode.currentIndex()]
        data["families"]=[f for f,w in self.families.items() if w.isChecked()]
        data["max_stages"]=2 if self.stages.currentIndex()==0 else 1
        data["priority"]=["balanced","size","cost","efficiency","backlash"][self.priority.currentIndex()]
        req=Requirements(**data);req.validate()
        p=asdict(self.project.profile);p.update({k:w.value() for k,w in self.profile_fields.items()})
        p.update(name=self.profile_name.text(),material=self.profile_material.text(),orientation=self.orientation.text(),test_evidence=self.evidence.toPlainText())
        profile=PrintProfile(**p);profile.validate()
        self.project.requirements,self.project.profile=req,profile
        self.project.name=self.project_name.text() or "Untitled gearbox"
        self.project.selected_id=self.selected.id if self.selected else ""
        self.project.design_snapshot=asdict(self.selected) if self.selected else None
        return asdict(req),asdict(profile)

    def populate(self):
        r,p=self.project.requirements,self.project.profile
        self.project_name.setText(self.project.name)
        for k,w in self.fields.items():w.setValue(getattr(r,k))
        self.mode.setCurrentIndex(["hybrid","printed","commercial"].index(r.mode))
        for f,w in self.families.items():w.setChecked(f in r.families)
        self.stages.setCurrentIndex(0 if r.max_stages==2 else 1)
        self.priority.setCurrentIndex(["balanced","size","cost","efficiency","backlash"].index(r.priority))
        for k,w in self.profile_fields.items():w.setValue(getattr(p,k))
        self.profile_name.setText(p.name);self.profile_material.setText(p.material);self.orientation.setText(p.orientation);self.evidence.setPlainText(p.test_evidence)
        self.dirty=False;self.setWindowModified(False);self.update_ratio()

    def advanced_dialog(self):
        try:self.capture()
        except Exception as exc:self.error(exc);return
        dialog=QDialog(self);dialog.setWindowTitle("Advanced constraints and motor curve");dialog.resize(580,720)
        outer=QVBoxLayout(dialog);form=QFormLayout();r=self.project.requirements;widgets={}
        for key,title,lo,hi,dec,suffix in [
            ("peak_factor","Peak load multiplier",1,10,2,""),("safety_factor","Safety factor",1,10,2,""),
            ("life_hours","Required bearing life",.1,100000,1," h"),("ratio_tolerance_percent","Ratio tolerance",.01,20,2," %"),
            ("max_backlash_deg","Maximum output backlash",.01,180,3," °"),("ambient_c","Ambient temperature",-20,150,1," °C"),
            ("min_module_mm","Minimum module",.8,3,2," mm"),("max_module_mm","Maximum module",.8,3,2," mm"),
            ("input_shaft_mm","Minimum input shaft diameter",3,50,1," mm"),("output_shaft_mm","Minimum output shaft diameter",3,50,1," mm"),
            ("budget","Budget (0 = unset)",0,1e8,2,"")]:
            w=number(getattr(r,key),lo,hi,dec,suffix);widgets[key]=w;form.addRow(title,w)
        supplier=QLineEdit(r.supplier);form.addRow("Supplier filter",supplier)
        currency=QLineEdit(r.currency);form.addRow("Cost currency",currency)
        mounting=QComboBox();mounting.addItems(["Foot","Flange"]);mounting.setCurrentIndex(0 if r.mounting=="foot" else 1);form.addRow("Mounting",mounting)
        outer.addLayout(form)
        outer.addWidget(label("Motor curve JSON: [[rpm, torque_Nm], …]. Empty uses Motor torque.","subtle"))
        curve=QTextEdit(json.dumps(r.motor_curve));curve.setMaximumHeight(90);outer.addWidget(curve)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);outer.addWidget(buttons)
        if dialog.exec()==QDialog.Accepted:
            try:
                data=asdict(r);data.update({k:w.value() for k,w in widgets.items()});data.update(supplier=supplier.text(),currency=currency.text().upper(),mounting=["foot","flange"][mounting.currentIndex()],motor_curve=json.loads(curve.toPlainText() or "[]"))
                result=Requirements(**data);result.validate();self.project.requirements=result;self.mark_dirty()
            except Exception as exc:self.error(exc)

    def start_job(self,task,payload,callback):
        if self.process is not None:self.error("Another job is running. Wait or cancel it first.");return
        self.job_temp=tempfile.TemporaryDirectory(prefix="gearforge-job-",dir=self.data_dir)
        result_path=Path(self.job_temp.name)/"result.json"
        payload=dict(payload,task=task,result_path=str(result_path))
        self.job_callback=callback
        process=QProcess(self);self.process=process
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.finished.connect(lambda code,status:self.job_finished(result_path,code))
        process.errorOccurred.connect(self.job_error)
        # File protocol also works in macOS/Windows windowed frozen executables
        # where PyInstaller intentionally leaves sys.stdin unavailable.
        input_path=Path(self.job_temp.name)/"input.json"
        atomic_text(input_path,json.dumps(payload,allow_nan=False))
        args=["--worker-file",str(input_path)] if getattr(sys,"frozen",False) else ["-m","gearforge.cli","--worker-file",str(input_path)]
        self.pending_job=json.dumps(payload,allow_nan=False).encode()
        process.start(sys.executable,args)
        self.job_bar.setRange(0,0);self.job_bar.show();self.cancel_button.show()
        self.job_status.setText({"search":"Searching and checking gearbox alternatives…","preview":"Building parametric CAD and preview meshes…","export":"Checking interference and exporting design files…","coupon":"Generating calibration coupon…","mesh-check":"Sampling exact tooth intersections at 12 input phases…"}[task])
        self.generate_button.setEnabled(False);self.cad_button.setEnabled(False)
        self.sync_actions()

    def send_job(self):
        if self.process:
            self.process.write(self.pending_job);self.process.closeWriteChannel()

    def job_error(self,error):
        if self.process and error==QProcess.FailedToStart:
            message=self.process.errorString();self.cleanup_job();self.error(message)

    def job_finished(self,path,code):
        if self.process is None:return
        errors=bytes(self.process.readAllStandardError()).decode(errors="replace")[-4000:]
        callback=self.job_callback
        try:
            response=json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            response={"ok":False,"error":errors or "Worker did not return a result"}
        self.cleanup_job()
        if code == 0 and response.get("ok"):
            try:callback(response["result"])
            except Exception as exc:self.error(exc)
        else:
            logging.error("Worker failure: %s",response.get("error"));self.error(response.get("error","Job failed"))

    def cleanup_job(self):
        if self.process:self.process.deleteLater()
        self.process=None;self.job_callback=None
        if self.job_temp:self.job_temp.cleanup()
        self.job_temp=None;self.job_bar.hide();self.cancel_button.hide();self.job_status.setText("")
        self.generate_button.setEnabled(True);self.cad_button.setEnabled(True)
        self.sync_actions()

    def cancel_job(self):
        if self.process:
            process=self.process
            process.finished.disconnect()
            process.kill();process.waitForFinished(3000)
            self.cleanup_job();self.statusBar().showMessage("Job cancelled. Completed exports, if any, remain on disk.")

    def generate(self):
        if self.process is not None:
            self.error("Another job is running. Wait or cancel it first.")
            return
        try:
            req,p=self.capture()
            self.search_snapshot=(req,p)
            self.search_catalog_text=self.catalog.export_csv()
            self.start_job("search",dict(requirements=req,profile=p,catalog_text=self.search_catalog_text),self.apply_result)
        except Exception as exc:self.error(exc)

    def apply_result(self,result):
        if self.search_catalog_text != self.catalog.export_csv():
            self.reset_results()
            self.notice.setText("Catalog changed during search. Regenerate designs.")
            return
        self.result_snapshot=self.search_snapshot
        self.result_catalog_text=self.search_catalog_text
        self.candidates=[candidate_from_dict(c) for c in result["candidates"]]
        rows=[(c.score,c.family.title()+f" / {len(c.stages)}",f"{c.ratio:.4g}:1",f"{c.efficiency:.0%}",f"{c.backlash_deg:.3f}"," × ".join(f"{v:.0f}" for v in c.size_mm),"Concept" if c.export_level=="concept" else "Prototype"+(" · Pareto" if c.pareto else "")) for c in self.candidates]
        fill_table(self.candidate_table,rows)
        self.candidate_count.setText(f"{len(self.candidates)} CANDIDATES · {result['evaluated']:,} EVALUATED")
        self.notice.setText(" ".join(result["explanations"][:2]))
        self.statusBar().showMessage(f"Search completed in {result['elapsed_s']:.2f}s · {len(self.candidates)} displayed designs")
        if self.candidates:self.candidate_table.selectRow(0)
        else:
            self.selected=None;self.viewer.set_candidate(None)
            reasons="\n".join(f"{k}: {v} rejected" for k,v in list(result["rejected"].items())[:12])
            self.error("No feasible design.\n\n"+reasons+"\n\n"+"\n".join(result["explanations"]))

    def selection_changed(self):
        indexes=self.candidate_table.selectionModel().selectedRows()
        if not indexes:return
        row=self.candidate_table.currentRow()
        if row<0:row=indexes[0].row()
        if row>=len(self.candidates):return
        self.selected=c=self.candidates[row];self.viewer.set_candidate(c)
        self.viewer.backlash_mm=self.result_snapshot[1]["backlash_mm"]
        self.viewer.clock.time_scale=[.001,.01,.1,1][self.time_scale.currentIndex()]
        self.viewer.clock.speed_factor=-1. if self.reverse.isChecked() else 1.
        self.mesh_result=None;self.mesh_summary.setText("Exact tooth intersections have not been sampled.")
        req=Requirements(**self.result_snapshot[0]);self.sweep=operating_sweep(c,req)
        points=self.sweep["points"]
        self.sim_plot.set_data(points,req.output_torque_nm)
        fill_table(self.sim_table,[(f"{p['input_rpm']:.1f}",f"{p['output_rpm']:.1f}",f"{p['available_output_nm']:.4g}",f"{p['input_power_w']:.3g}",f"{p['output_power_w']:.3g}",f"{p['loss_power_w']:.3g}",f"{p['load_margin_nm']:.4g}",p['status']) for p in points])
        self.sim_summary.setText(self.sweep["method"] + (" Planetary mesh forces are total sun force; load sharing is unvalidated." if c.family=="planetary" else ""))
        self.viewer.setAccessibleDescription(f"{c.label}. Input {req.input_rpm:g} rpm; output {c.output_rpm:g} rpm. Arrow keys orbit, plus/minus zoom, R resets, Space toggles playback. Contact unvalidated.")
        self.metrics["ratio"].setText(f"{c.ratio:.3g}:1");self.metrics["rpm"].setText(f"{c.output_rpm:.1f}")
        self.metrics["torque"].setText(f"{c.available_output_nm:.3f}");self.metrics["eff"].setText(f"{c.efficiency:.0%}")
        fill_table(self.check_table,[(k.status.upper(),k.name,"—" if k.value is None else f"{k.value:g} {k.unit}","—" if k.limit is None else f"{k.limit:g}",k.detail) for k in c.checks])
        fill_table(self.stage_table,[(i+1,s.driver.sku or str(s.driver.teeth)+"T print",s.driven.sku or str(s.driven.teeth)+"T print",s.driver.module_mm,f"{s.ratio:.4g}",f"{s.input_rpm:.1f}",f"{s.input_torque_nm:.4f}",f"{s.output_torque_nm:.4f}") for i,s in enumerate(c.stages)])
        fill_table(self.bom_table,[(b["part"],b["quantity"],b["source"],b["sku"],b["description"],"Unknown" if b["unit_cost"] is None else b["unit_cost"]) for b in c.bom])
        self.update_report()
        self.sync_actions()

    def sync_actions(self):
        if not hasattr(self,"cad_button"):return
        idle=self.process is None;valid=False
        if self.selected and self.result_snapshot:
            try:valid=self.result_snapshot==self.capture()
            except (ValueError,TypeError):pass
        for title in ("Export selected design…","Load CAD preview","Sample tooth meshing…"):
            enabled=idle and valid and (title=="Export selected design…" or self.selected.export_level!="concept")
            self.command_actions[title].setEnabled(enabled)
        self.command_actions["Generate designs"].setEnabled(idle)
        self.command_actions["Study selected stage…"].setEnabled(idle and valid and self.selected.family in ("spur","helical"))
        self.cad_button.setEnabled(self.command_actions["Load CAD preview"].isEnabled())
        self.export_button.setEnabled(self.command_actions["Export selected design…"].isEnabled())
        self.mesh_check_button.setEnabled(self.command_actions["Sample tooth meshing…"].isEnabled())
        self.sim_export_button.setEnabled(idle and valid)
        self.compare_button.setEnabled(idle and len(self.candidate_table.selectionModel().selectedRows())>=2)
        self.animate_box.setEnabled(valid and not self.reduced_motion and self.selected.export_level!="concept")

    def simulation_time_changed(self,seconds):
        if not hasattr(self,"sim_time"):return
        self.sim_time.blockSignals(True);self.sim_time.setValue(min(3600,seconds));self.sim_time.blockSignals(False)
        if self.selected:
            rates=shaft_rates(self.selected,self.viewer.clock.input_rpm*self.viewer.clock.speed_factor)
            self.sim_time.setToolTip(f"Simulated time {seconds:.4f} s. Input {rates[0]:g} rpm; output {rates[-1]:g} rpm. Display scale does not change operating RPM.")

    def check_mesh(self):
        try:
            payload=self.ready_payload();payload["samples"]=12
            self.viewer.animate(False);self.start_job("mesh-check",payload,self.apply_mesh_check)
        except Exception as exc:self.error(exc)

    def apply_mesh_check(self,result):
        if not self.selected or result["candidate_id"]!=self.selected.id:return
        try:
            if self.result_snapshot!=self.capture():self.statusBar().showMessage("Mesh result belongs to earlier requirements. Regenerate to continue.");return
        except (ValueError,TypeError):return
        self.mesh_result=result
        self.mesh_summary.setText(f"{result['status']}: max overlap {result['maximum_overlap_mm3']:.6g} mm³ at {result['samples']} poses. One input revolution; continuous contact and full assembly cycle remain unvalidated.")
        self.statusBar().showMessage(self.mesh_summary.text())

    def export_simulation(self):
        try:self.ready_payload()
        except Exception as exc:self.error(exc);return
        path,_=QFileDialog.getSaveFileName(self,"Export simulation evidence","simulation-"+self.selected.id+".json","JSON (*.json)")
        if path:
            try:atomic_text(Path(path),json.dumps({"sweep":self.sweep,"sampled_mesh_check":getattr(self,"mesh_result",None)},indent=2,allow_nan=False))
            except Exception as exc:self.error(exc)

    def ready_payload(self):
        req,p=self.capture()
        if self.selected is None:raise ValueError("Generate and select a design first")
        if self.result_snapshot!=(req,p):raise ValueError("Requirements or print profile changed. Regenerate designs before CAD/export.")
        return dict(candidate=asdict(self.selected),requirements=req,profile=p)

    def load_preview(self):
        try:
            payload=self.ready_payload()
            if self.selected.export_level=="concept":raise ValueError("This family has a concept layout. Detailed manufacturing geometry is not available in this release.")
            self.animate_box.setChecked(False)
            self.start_job("preview",payload,self.apply_preview)
        except Exception as exc:self.error(exc)

    def apply_preview(self,result):
        try:
            if self.result_snapshot!=self.capture():self.statusBar().showMessage("CAD result belongs to earlier requirements. Regenerate to continue.");return
        except (ValueError,TypeError):return
        if self.selected and self.selected.id==result["candidate_id"]:self.viewer.set_meshes(result["meshes"])
        self.statusBar().showMessage("CAD ready for rigid-body playback · use Simulation for operating sweep and sampled meshing")

    def compare(self):
        rows=sorted({i.row() for i in self.candidate_table.selectionModel().selectedRows()})
        if len(rows)<2:self.error("Select two or more candidate rows with Ctrl / Cmd or Shift.");return
        chosen=[self.candidates[i] for i in rows[:6]]
        dialog=QDialog(self);dialog.setWindowTitle("Compare gearbox alternatives");dialog.resize(1000,440);layout=QVBoxLayout(dialog)
        t=table(["Metric"]+[c.label for c in chosen]);layout.addWidget(t)
        metrics=[("Score",lambda c:c.score),("Output speed rpm",lambda c:round(c.output_rpm,2)),("Available output N·m",lambda c:round(c.available_output_nm,4)),("Efficiency",lambda c:f"{c.efficiency:.1%}"),("Backlash deg",lambda c:round(c.backlash_deg,4)),("Envelope mm",lambda c:" × ".join(f"{v:.1f}" for v in c.size_mm)),("Total cost",lambda c:"Unknown" if c.estimated_cost is None else c.estimated_cost),("Export status",lambda c:c.export_level),("Uncharacterized checks",lambda c:sum(k.status=="warn" for k in c.checks))]
        fill_table(t,[(name,*[get(c) for c in chosen]) for name,get in metrics]);dialog.exec()

    def export_selected(self,include_cad=True):
        if isinstance(include_cad,bool):pass
        else:include_cad=True
        try:payload=self.ready_payload()
        except Exception as exc:self.error(exc);return
        parent=QFileDialog.getExistingDirectory(self,"Choose parent folder for a new design export")
        if not parent:return
        suffix="";i=1;dest=Path(parent)/("GearForge-"+self.selected.id)
        while dest.exists():
            i+=1;dest=Path(parent)/("GearForge-"+self.selected.id+f"-{i}")
        payload.update(destination=str(dest),include_cad=include_cad,
                       project=asdict(self.project),catalog_text=self.result_catalog_text)
        self.start_job("export",payload,lambda result:self.statusBar().showMessage(f"Exported {result['files']} files to {result['destination']}"))

    def update_report(self):
        if not hasattr(self,"report_browser"):return
        if self.selected and self.result_snapshot:
            req,p=self.result_snapshot
            self.report_browser.setHtml(report_html(self.selected,Requirements(**req),PrintProfile(**p)))
        else:self.report_browser.setHtml("<h2>Select a generated design to review its report.</h2>")

    def refresh_catalog(self,*args):
        self.catalog_rows=self.catalog.rows(self.catalog_query.text())
        fill_table(self.catalog_table,[(r["sku"],r["supplier"],r["family"],r["module_mm"],r["teeth"],r["bore_mm"],r["width_mm"],r["bending_nm"],r["contact_nm"],"Unknown" if r["price"] is None else r["price"],r["retrieved_date"],r["source_url"]) for r in self.catalog_rows])

    def import_catalog(self):
        path,_=QFileDialog.getOpenFileName(self,"Import component catalog","","CSV (*.csv)")
        if path:
            try:
                count=self.catalog.import_csv(read_text_limited(Path(path),5_000_000,"Catalog","utf-8-sig"))
                self.cancel_job();self.reset_results();self.refresh_catalog()
                self.statusBar().showMessage(f"Imported {count} validated catalog records. Regenerate existing designs.")
            except Exception as exc:self.error(exc)

    def export_catalog(self):
        path,_=QFileDialog.getSaveFileName(self,"Export catalog and CSV template","gears.csv","CSV (*.csv)")
        if path:
            try:atomic_text(Path(path),self.catalog.export_csv())
            except Exception as exc:self.error(exc)

    def open_catalog_source(self,row,column):
        url=self.catalog_rows[row]["source_url"]
        if url.startswith("https://"):QDesktopServices.openUrl(QUrl(url))

    def refresh_profiles(self):
        self.saved_profiles=self.catalog.profiles();self.profile_list.clear();self.profile_list.addItems([p.name for p in self.saved_profiles])

    def save_profile(self):
        try:self.capture();self.catalog.save_profile(self.project.profile);self.refresh_profiles();self.statusBar().showMessage("Print profile saved")
        except Exception as exc:self.error(exc)

    def load_profile(self,item):
        self.project.profile=self.saved_profiles[self.profile_list.row(item)]
        self.populate();self.mark_dirty()

    def apply_calibration(self):
        try:
            self.capture();self.project.profile=calibrate_profile(self.project.profile,self.outer_measure.value(),40,self.bore_measure.value(),10,f"40 mm coupon outside={self.outer_measure.value():g}, bore={self.bore_measure.value():g} mm; strength not measured")
            self.populate();self.mark_dirty()
            self.statusBar().showMessage("Dimensional compensation updated. Reprint coupon to verify the correction.")
        except Exception as exc:self.error(exc)

    def export_coupon(self):
        path,_=QFileDialog.getSaveFileName(self,"Export uncompensated coupon","calibration-coupon.stl","STL (*.stl)")
        if path:self.start_job("coupon",dict(path=path),lambda r:self.statusBar().showMessage("Coupon saved to "+r["destination"]))

    def may_discard(self):
        if not self.dirty:return True
        result=QMessageBox.question(self,"Unsaved project","Save your current project before continuing?",QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
        if result==QMessageBox.Save:return self.save_project()
        return result==QMessageBox.Discard

    def reset_results(self):
        self.candidates=[];self.selected=None;self.result_snapshot=None;self.candidate_table.setRowCount(0);self.viewer.set_candidate(None)
        self.check_table.setRowCount(0);self.bom_table.setRowCount(0);self.stage_table.setRowCount(0)
        for value in self.metrics.values():value.setText("—")
        self.candidate_count.setText("CANDIDATE DESIGNS");self.update_report()
        self.sim_table.setRowCount(0);self.sim_plot.set_data([],0);self.mesh_result=None;self.sweep=None;self.sync_actions()

    def new_project(self):
        if not self.may_discard():return
        self.cancel_job();self.project=Project();self.path=None;self.reset_results();self.populate()
        self.setWindowTitle("Untitled gearbox[*] — GearForge Studio");self.setWindowFilePath("")

    def open_project(self,path=None):
        if not self.may_discard():return False
        if path is None:path,_=QFileDialog.getOpenFileName(self,"Open gearbox project","","GearForge (*.gearforge)")
        if not path:return False
        try:
            project=Project.load(Path(path));self.cancel_job();self.project=project;self.path=Path(path);self.reset_results();self.populate()
            self.setWindowTitle(self.project.name+"[*] — GearForge Studio");self.setWindowFilePath(str(self.path));self.statusBar().showMessage("Project loaded. Generate designs to recalculate against the current catalog.")
            return True
        except Exception as exc:self.error(exc);return False

    def save_project(self,save_as=False):
        try:self.capture()
        except Exception as exc:self.error(exc);return False
        destination=self.path
        if destination is None or save_as:
            path,_=QFileDialog.getSaveFileName(self,"Save project",self.project.name+".gearforge","GearForge (*.gearforge)")
            if not path:return False
            destination=Path(path)
        try:
            self.project.save(destination);self.path=destination;self.dirty=False;self.setWindowModified(False)
            self.setWindowTitle(self.project.name+"[*] — GearForge Studio");self.setWindowFilePath(str(self.path));self.statusBar().showMessage("Project saved: "+str(self.path));return True
        except Exception as exc:self.error(exc);return False

    def save_recovery(self):
        if self.dirty:
            try:self.capture();self.project.save(self.data_dir/"recovery.gearforge")
            except Exception:logging.exception("Autosave unavailable")

    def restore_recovery(self):
        recovery=self.data_dir/"recovery.gearforge"
        if not recovery.exists():self.error("No autosaved project is available.");return
        if self.open_project(recovery):
            self.path=None;self.setWindowFilePath("");self.mark_dirty()

    def error(self,error):
        QMessageBox.warning(self,"GearForge Studio",str(error))

    def closeEvent(self,event):
        if not self.may_discard():event.ignore();return
        self.autosave.stop()
        self.cancel_job();self.viewer.animate(False);self.settings.setValue("geometry",self.saveGeometry());self.settings.setValue("design_splitter",self.design_splitter.saveState());self.settings.setValue("sidebar_visible",self.sidebar_action.isChecked());self.settings.sync();self.catalog.close();self.data_lock.unlock();event.accept()


class DocumentApplication(QApplication):
    """Receive Finder document-open events without argv emulation."""
    window=None
    pending_document=None

    def event(self,event):
        if event.type()==QEvent.FileOpen and event.file().endswith(".gearforge"):
            if self.window:self.window.open_project(event.file())
            else:self.pending_document=event.file()
            return True
        return super().event(event)


def main():
    if "--worker" in sys.argv or "--worker-file" in sys.argv:
        from .cli import main as dispatch
        return dispatch()
    app=QApplication.instance() or DocumentApplication(sys.argv)
    app.setApplicationName("GearForge Studio");app.setOrganizationName("GearForge")
    from importlib.resources import files
    app.setWindowIcon(QIcon(str(files("gearforge").joinpath("data/icon.png"))))
    data_dir=Path(os.environ.get("GEARFORGE_DATA_DIR") or QStandardPaths.writableLocation(QStandardPaths.AppDataLocation));data_dir.mkdir(parents=True,exist_ok=True)
    handler=logging.handlers.RotatingFileHandler(data_dir/"gearforge.log",maxBytes=1_000_000,backupCount=2)
    logging.basicConfig(level=logging.INFO,handlers=[handler])
    try:window=MainWindow(data_dir)
    except (OSError,RuntimeError,ValueError,sqlite3.Error) as exc:
        QMessageBox.critical(None,"GearForge Studio",str(exc));return 1
    window.show()
    if isinstance(app,DocumentApplication):
        app.window=window
        if app.pending_document:window.open_project(app.pending_document)
    return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
