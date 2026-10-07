from __future__ import annotations

import json
import time
from pathlib import Path


def desktop_smoke(destination: Path, include_cad=False):
    """Exercise the actual desktop/process worker and save diagnostic evidence."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from .app import MainWindow,STYLE
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError("Diagnostic directory already exists")
    destination.mkdir(parents=True)
    app=QApplication.instance() or QApplication([])
    app.setApplicationName("GearForge Studio");app.setStyleSheet(STYLE)
    window=MainWindow(destination/"diagnostic-data")
    errors=[];window.error=lambda e:errors.append(str(e))
    window.show()
    started=time.monotonic();state={"cad_requested":False,"finished":False}
    timer=QTimer();timer.setInterval(100)
    def finish():
        if state["finished"]:return
        state["finished"]=True
        result={"ok":not errors,"errors":errors,"candidates":len(window.candidates),"cad_meshes":len(window.viewer.meshes),"elapsed_s":round(time.monotonic()-started,3),"simulation_points":len(window.sweep["points"]) if window.selected else 0,"native_platform":"offscreen","engineering_study":state.get("engineering_study"),"shaft_study":state.get("shaft_study"),"bearing_study":state.get("bearing_study")}
        result["fatigue_study"]=state.get("fatigue_study")
        result["contact_study"]=state.get("contact_study")
        result["thermal_study"]=state.get("thermal_study")
        result["tooth_profile"]=state.get("tooth_profile")
        result["root_stress"]=state.get("root_stress")
        result['stress_history']=state.get('stress_history')
        if window.selected:result["selected"]=window.selected.id
        (destination/"desktop-smoke.json").write_text(json.dumps(result,indent=2))
        if not errors:
            window.grab().save(str(destination/"desktop.png"))
        window.dirty=False;window.close();timer.stop();app.quit()
    def tick():
        if time.monotonic()-started>120:
            errors.append("Desktop smoke timed out");finish();return
        if errors:finish();return
        if window.process is not None:return
        if not window.candidates:
            errors.append("Search returned no candidates");finish();return
        if include_cad and not state["cad_requested"]:
            state["cad_requested"]=True;window.load_preview();return
        if include_cad and not window.viewer.meshes:
            errors.append("CAD preview returned no meshes");finish();return
        # Verify all four native pages render, then capture the CAD/design workspace.
        for index in range(window.pages.count()):
            window.nav.setCurrentRow(index)
            if window.grab().isNull():errors.append(f"Page {index} did not render")
        window.nav.setCurrentRow(0)
        if include_cad:
            count=len(window.viewer.meshes);window.viewer.step()
            if len(window.viewer.meshes)!=count or window.viewer.phase==0:errors.append("CAD single-step failed")
        window.nav.setCurrentRow(4)
        window.grab().save(str(destination/"simulation.png"))
        window.nav.setCurrentRow(0)
        timer.stop()
        # Exercise the study editor and its exporter in the installed/frozen app.
        from .engineering_ui import EngineeringStudyDialog
        from .engineering import EngineeringStudy, calculate_study, export_study
        from .maintenance import verify_bundle
        import math
        study_window=EngineeringStudyDialog(window)
        study_window.show_error=lambda error:errors.append(str(error))
        try:
            study_window.show()
            if not study_window.calculate():raise ValueError("Engineering study calculation failed")
            for index in range(study_window.tabs.count()):
                study_window.tabs.setCurrentIndex(index)
                app.processEvents()
                capture=study_window.grab()
                if capture.isNull():raise ValueError(f"Engineering study tab {index} did not render")
                capture.save(str(destination/f"engineering-study-{index}.png"))
            study=study_window.read_study()
            study.save(destination/"target.gearforge-study")
            loaded=EngineeringStudy.load(destination/"target.gearforge-study")
            result=calculate_study(loaded)
            if not math.isclose(result["duty_results"][0]["input_power_w"],250,rel_tol=1e-10):
                raise ValueError("Engineering study target input did not round-trip")
            if result["study_sha256"]!=study_window.result["study_sha256"]:
                raise ValueError("Engineering study fingerprint did not round-trip")
            export_study(loaded,destination/"engineering-calculation")
            manifest=verify_bundle(destination/"engineering-calculation")
            if result["production_approved"] or result["rated_life_hours"] is not None:
                raise ValueError("Engineering study falsely claims a production rating")
            state["engineering_study"]={"app_version":result["app_version"],"tabs_rendered":study_window.tabs.count(),
                "verified_files":len(manifest["files"]),"input_power_w":result["duty_results"][0]["input_power_w"],
                "study_sha256":result["study_sha256"],"production_approved":False}
        except Exception as exc:
            errors.append(f"Engineering study: {exc}")
        finally:
            study_window.dirty=False;study_window.close()
        from .shaft_ui import ShaftStudyDialog
        from .shafts import ShaftStudy, shaft_from_gear_study, calculate_shaft_study, export_shaft_study
        shaft_window=ShaftStudyDialog(window,shaft_from_gear_study(EngineeringStudy()))
        shaft_window.show_error=lambda error:errors.append(str(error))
        try:
            shaft_window.show()
            if not shaft_window.calculate():raise ValueError("Shaft study calculation failed")
            for index in range(shaft_window.tabs.count()):
                shaft_window.tabs.setCurrentIndex(index);app.processEvents()
                capture=shaft_window.grab()
                if capture.isNull():raise ValueError(f"Shaft study tab {index} did not render")
                capture.save(str(destination/f"shaft-study-{index}.png"))
            shaft=shaft_window.read_study();shaft.save(destination/"target.gearforge-shaft")
            loaded_shaft=ShaftStudy.load(destination/"target.gearforge-shaft")
            shaft_result=calculate_shaft_study(loaded_shaft)
            if shaft_result["study_sha256"]!=shaft_window.result["study_sha256"]:
                raise ValueError("Shaft study did not round-trip")
            export_shaft_study(loaded_shaft,destination/"shaft-calculation")
            manifest=verify_bundle(destination/"shaft-calculation")
            residual=max(abs(value) for case in shaft_result["cases"] for value in case["equilibrium_residual"].values())
            if residual>1e-8 or shaft_result["production_approved"]:raise ValueError("Shaft load balance or qualification failed")
            state["shaft_study"]={"app_version":shaft_result["app_version"],"tabs_rendered":shaft_window.tabs.count(),
                "verified_files":len(manifest["files"]),"maximum_equilibrium_residual":residual,
                "study_sha256":shaft_result["study_sha256"],"production_approved":False}
        except Exception as exc:
            errors.append(f"Shaft study: {exc}")
        finally:
            shaft_window.dirty=False;shaft_window.close()
        from .bearing_ui import BearingStudyDialog
        from .bearings import BearingStudy,synthetic_bearing_example,calculate_bearing_study,export_bearing_study
        bearing_window=BearingStudyDialog(window,synthetic_bearing_example())
        bearing_window.show_error=lambda error:errors.append(str(error))
        try:
            bearing_window.show()
            if not bearing_window.calculate():raise ValueError("Bearing assessment failed")
            for index in range(bearing_window.tabs.count()):
                bearing_window.tabs.setCurrentIndex(index);app.processEvents()
                capture=bearing_window.grab()
                if capture.isNull():raise ValueError(f"Bearing study tab {index} did not render")
                capture.save(str(destination/f"bearing-study-{index}.png"))
            bearing=bearing_window.read_study();bearing.save(destination/"target.gearforge-bearing")
            loaded_bearing=BearingStudy.load(destination/"target.gearforge-bearing")
            bearing_result=calculate_bearing_study(loaded_bearing)
            if bearing_result['study_sha256']!=bearing_window.result['study_sha256']:
                raise ValueError('Bearing study did not round-trip')
            export_bearing_study(loaded_bearing,destination/'bearing-calculation')
            manifest=verify_bundle(destination/'bearing-calculation')
            life=bearing_result['bearings'][0]['basic_l10_repeated_duty_hours']
            if not math.isclose(life,18295.51049310608,rel_tol=1e-10):raise ValueError('Synthetic bearing life arithmetic changed')
            if bearing_result['production_approved'] or bearing_result['rated_gearbox_life_hours'] is not None:
                raise ValueError('Bearing assessment falsely approves gearbox life')
            state['bearing_study']={'app_version':bearing_result['app_version'],'tabs_rendered':bearing_window.tabs.count(),
                'verified_files':len(manifest['files']),'synthetic_basic_l10_hours':life,
                'study_sha256':bearing_result['study_sha256'],'production_approved':False}
        except Exception as exc:
            errors.append(f'Bearing study: {exc}')
        finally:
            bearing_window.dirty=False;bearing_window.close()
        from .fatigue_ui import FatigueStudyDialog
        from .fatigue import FatigueStudy,nasa_example,calculate_fatigue_study,export_fatigue_study
        fatigue_window=FatigueStudyDialog(window,nasa_example())
        fatigue_window.show_error=lambda error:errors.append(str(error))
        try:
            fatigue_window.show()
            if not fatigue_window.calculate():raise ValueError('Fatigue assessment failed')
            for index in range(fatigue_window.tabs.count()):
                fatigue_window.tabs.setCurrentIndex(index);app.processEvents();capture=fatigue_window.grab()
                if capture.isNull():raise ValueError(f'Fatigue study tab {index} did not render')
                capture.save(str(destination/f'fatigue-study-{index}.png'))
            fatigue=fatigue_window.read_study();fatigue.save(destination/'example.gearforge-fatigue')
            loaded_fatigue=FatigueStudy.load(destination/'example.gearforge-fatigue')
            fatigue_result=calculate_fatigue_study(loaded_fatigue)
            if fatigue_result['study_sha256']!=fatigue_window.result['study_sha256']:
                raise ValueError('Fatigue inputs did not round-trip')
            export_fatigue_study(loaded_fatigue,destination/'fatigue-calculation')
            manifest=verify_bundle(destination/'fatigue-calculation')
            endpoint=fatigue_result['stations'][0]['cases'][0]['corrected_reference_strength_mpa']
            if not math.isclose(endpoint,125.06778394565542,rel_tol=1e-10):raise ValueError('NASA example endpoint changed')
            if fatigue_result['production_approved'] or fatigue_result['rated_gearbox_life_hours'] is not None:
                raise ValueError('Fatigue assessment falsely approves gearbox life')
            state['fatigue_study']={'app_version':fatigue_result['app_version'],'tabs_rendered':fatigue_window.tabs.count(),
                'verified_files':len(manifest['files']),'nasa_example_corrected_endpoint_mpa':endpoint,
                'study_sha256':fatigue_result['study_sha256'],'production_approved':False}
        except Exception as exc:
            errors.append(f'Fatigue study: {exc}')
        finally:
            fatigue_window.dirty=False;fatigue_window.close()
        from .contact_ui import ContactStudyDialog
        from .contact import ContactStudy,synthetic_contact_example,calculate_contact_study,export_contact_study
        contact_window=ContactStudyDialog(window,synthetic_contact_example())
        contact_window.show_error=lambda error:errors.append(str(error))
        try:
            contact_window.show()
            if not contact_window.calculate():raise ValueError('Contact assessment failed')
            for index in range(contact_window.tabs.count()):
                contact_window.tabs.setCurrentIndex(index);app.processEvents();capture=contact_window.grab()
                if capture.isNull():raise ValueError(f'Contact study tab {index} did not render')
                capture.save(str(destination/f'contact-study-{index}.png'))
            contact_window.tabs.setCurrentIndex(3)
            for index in range(contact_window.quantity.count()):
                contact_window.quantity.setCurrentIndex(index);app.processEvents();capture=contact_window.grab()
                if capture.isNull():raise ValueError(f'Contact diagram {index} did not render')
                capture.save(str(destination/f'contact-path-{index}.png'))
            contact=contact_window.read_study();contact.save(destination/'example.gearforge-contact')
            loaded_contact=ContactStudy.load(destination/'example.gearforge-contact')
            contact_result=calculate_contact_study(loaded_contact)
            if contact_result['study_sha256']!=contact_window.result['study_sha256']:
                raise ValueError('Contact inputs did not round-trip')
            export_contact_study(loaded_contact,destination/'contact-calculation')
            manifest=verify_bundle(destination/'contact-calculation')
            pressure=contact_result['cases'][0]['peak_hertz_pressure_mpa']
            if not math.isclose(pressure,342.5004364419622,rel_tol=1e-10):raise ValueError('Synthetic contact pressure changed')
            if contact_result['production_approved'] or contact_result['rated_gearbox_life_hours'] is not None:
                raise ValueError('Contact assessment falsely approves gearbox life')
            state['contact_study']={'app_version':contact_result['app_version'],'tabs_rendered':contact_window.tabs.count(),
                'diagrams_rendered':contact_window.quantity.count(),'verified_files':len(manifest['files']),
                'synthetic_peak_pressure_mpa':pressure,'study_sha256':contact_result['study_sha256'],'production_approved':False}
        except Exception as exc:
            errors.append(f'Contact study: {exc}')
        finally:
            contact_window.dirty=False;contact_window.close()
        from .thermal_ui import ThermalStudyDialog
        from .thermal import ThermalStudy,synthetic_thermal_example,calculate_thermal_study,export_thermal_study
        thermal_window=ThermalStudyDialog(window,synthetic_thermal_example())
        thermal_window.show_error=lambda error:errors.append(str(error))
        try:
            thermal_window.show()
            if not thermal_window.calculate():raise ValueError('Thermal assessment failed')
            for index in range(thermal_window.tabs.count()):
                thermal_window.tabs.setCurrentIndex(index);app.processEvents();capture=thermal_window.grab()
                if capture.isNull():raise ValueError(f'Thermal study tab {index} did not render')
                capture.save(str(destination/f'thermal-study-{index}.png'))
            thermal_window.tabs.setCurrentIndex(3);diagrams=0
            for cycle in range(2):
                thermal_window.cycle_selector.setCurrentIndex(cycle)
                for phase in range(thermal_window.plot_phase.count()):
                    thermal_window.plot_phase.setCurrentIndex(phase)
                    for body in range(thermal_window.plot_body.count()):
                        thermal_window.plot_body.setCurrentIndex(body);app.processEvents();capture=thermal_window.grab()
                        if capture.isNull() or not thermal_window.plot.points:raise ValueError('Thermal trajectory failed to render')
                        capture.save(str(destination/f'thermal-history-{cycle}-{phase}-{body}.png'));diagrams+=1
            thermal=thermal_window.read_study();thermal.save(destination/'example.gearforge-thermal')
            loaded_thermal=ThermalStudy.load(destination/'example.gearforge-thermal');thermal_result=calculate_thermal_study(loaded_thermal)
            if thermal_result['study_sha256']!=thermal_window.result['study_sha256']:raise ValueError('Thermal inputs did not round-trip')
            export_thermal_study(loaded_thermal,destination/'thermal-calculation');manifest=verify_bundle(destination/'thermal-calculation')
            maximum=thermal_result['nodes'][0]['calculated_maximum_c']
            if not math.isclose(maximum,60.79234545102813,rel_tol=1e-10):raise ValueError('Synthetic thermal peak changed')
            if thermal_result['production_approved'] or thermal_result['rated_gearbox_life_hours'] is not None:raise ValueError('Thermal study falsely approves gearbox life')
            state['thermal_study']={'app_version':thermal_result['app_version'],'tabs_rendered':thermal_window.tabs.count(),
                'diagrams_rendered':diagrams,'verified_files':len(manifest['files']),'synthetic_gear_peak_c':maximum,
                'study_sha256':thermal_result['study_sha256'],'production_approved':False}
        except Exception as exc:
            errors.append(f'Thermal study: {exc}')
        finally:
            thermal_window.dirty=False;thermal_window.close()
        from .tooth_ui import ToothProfileDialog
        from .tooth_profile import ToothProfileStudy,synthetic_profile_example,calculate_profile_study,export_profile_study
        tooth_window=ToothProfileDialog(window,synthetic_profile_example())
        tooth_window.show_error=lambda error:errors.append(str(error))
        try:
            tooth_window.show()
            if not tooth_window.calculate() or not tooth_window.result['profile_available']:raise ValueError('Generated tooth profile failed')
            for index in range(tooth_window.tabs.count()):
                tooth_window.tabs.setCurrentIndex(index);app.processEvents();capture=tooth_window.grab()
                if capture.isNull():raise ValueError(f'Tooth profile tab {index} did not render')
                capture.save(str(destination/f'tooth-profile-{index}.png'))
            tooth_window.tabs.setCurrentIndex(1)
            for view in range(2):
                tooth_window.view.setCurrentIndex(view);app.processEvents();capture=tooth_window.grab()
                if capture.isNull():raise ValueError('Generated tooth diagram did not render')
                capture.save(str(destination/f'tooth-geometry-{view}.png'))
            tooth=tooth_window.read_study();tooth.save(destination/'example.gearforge-tooth')
            loaded=ToothProfileStudy.load(destination/'example.gearforge-tooth');tooth_result=calculate_profile_study(loaded)
            if tooth_result['study_sha256']!=tooth_window.result['study_sha256']:raise ValueError('Tooth inputs did not round-trip')
            export_profile_study(loaded,destination/'tooth-calculation');manifest=verify_bundle(destination/'tooth-calculation')
            start=tooth_result['geometry']['involute_start_radius_mm']
            if not math.isclose(start,18.820066532283924,rel_tol=1e-10):raise ValueError('Generated involute start changed')
            if tooth_result['production_approved']:raise ValueError('Tooth profile falsely approves a production rating')
            state['tooth_profile']={'app_version':tooth_result['app_version'],'tabs_rendered':tooth_window.tabs.count(),
                'diagrams_rendered':2,'verified_files':len(manifest['files']),'involute_start_radius_mm':start,
                'study_sha256':tooth_result['study_sha256'],'production_approved':False}
        except Exception as exc:errors.append(f'Tooth profile: {exc}')
        finally:tooth_window.dirty=False;tooth_window.close()
        from .root_ui import RootStressDialog
        from .root_stress import RootStressStudy,synthetic_root_example
        from dataclasses import asdict
        root_window=RootStressDialog(window,synthetic_root_example())
        root_window.show_error=lambda error:errors.append(str(error))
        def wait_root_worker():
            deadline=time.monotonic()+75
            while root_window.process is not None and time.monotonic()<deadline:
                app.processEvents();time.sleep(.01)
            if root_window.process is not None:root_window.cancel_job();raise ValueError('Root worker timed out')
            if errors:raise ValueError('Root worker failed')
        try:
            root_window.show()
            if not root_window.calculate():raise ValueError('Root worker did not start')
            wait_root_worker();root_result=root_window.result
            if not root_result or not root_result['calculation_available']:raise ValueError('Root elastic fields unavailable')
            for index in range(root_window.tabs.count()):
                root_window.tabs.setCurrentIndex(index);app.processEvents();capture=root_window.grab()
                if capture.isNull():raise ValueError(f'Root study tab {index} did not render')
                capture.save(str(destination/f'root-stress-{index}.png'))
            diagrams=0;root_window.tabs.setCurrentIndex(3)
            for position in range(root_window.position_selector.count()):
                root_window.position_selector.setCurrentIndex(position)
                for view in range(2):
                    root_window.view.setCurrentIndex(view);app.processEvents();capture=root_window.grab()
                    if capture.isNull() or root_window.plot.rendered_items==0:raise ValueError('Root stress mesh did not render')
                    capture.save(str(destination/f'root-mesh-{position}-{view}.png'));diagrams+=1
            root_window.tabs.setCurrentIndex(4);app.processEvents()
            if not root_window.curves.rendered_items:raise ValueError('Root stress curves did not render')
            root=root_window.read_study();root.save(destination/'example.gearforge-root')
            loaded=RootStressStudy.load(destination/'example.gearforge-root')
            if asdict(loaded)!=root_result['inputs']:raise ValueError('Root stress inputs did not round-trip')
            if not root_window.start_job('root-export',loaded,destination/'root-calculation'):raise ValueError('Root export worker did not start')
            wait_root_worker();manifest=verify_bundle(destination/'root-calculation')
            exported=json.loads((destination/'root-calculation/calculation.json').read_text())
            if exported['study_sha256']!=root_result['study_sha256']:raise ValueError('Root exported fingerprint changed')
            peak=max(p['root_von_mises_mpa'] for p in root_result['cases'][0]['positions'])
            if not math.isclose(peak,8.183902564948463,rel_tol=1e-7):raise ValueError('Synthetic root stress changed')
            if not root_result['mesh_convergence_passed'] or not root_result['domain_sensitivity_passed']:raise ValueError('Synthetic root numerical comparison failed')
            if root_result['production_approved'] or root_result['rated_gearbox_life_hours'] is not None:raise ValueError('Root stress falsely approves gearbox life')
            state['root_stress']={'app_version':root_result['app_version'],'tabs_rendered':root_window.tabs.count(),
                'diagrams_rendered':diagrams+1,'verified_files':len(manifest['files']),'peak_sampled_root_von_mises_mpa':peak,
                'mesh_convergence_passed':True,'domain_sensitivity_passed':True,'calculation_and_export_workers':True,
                'study_sha256':root_result['study_sha256'],'production_approved':False}
        except Exception as exc:errors.append(f'Root stress: {exc}')
        finally:root_window.dirty=False;root_window.close()
        from .cyclic_ui import HistoryStudyDialog
        from .cyclic import HistoryStudy,synthetic_history_example
        history_window=HistoryStudyDialog(window,synthetic_history_example())
        history_window.show_error=lambda error:errors.append(str(error))
        def wait_history_worker():
            deadline=time.monotonic()+30
            while history_window.process is not None and time.monotonic()<deadline:
                app.processEvents();time.sleep(.01)
            if history_window.process is not None:history_window.cancel_job();raise ValueError('History worker timed out')
            if errors:raise ValueError('History worker failed')
        try:
            history_window.show()
            if not history_window.calculate():raise ValueError('History worker did not start')
            wait_history_worker();history_result=history_window.result
            if not history_result or not history_result['fatigue_damage_available']:raise ValueError('Synthetic history arithmetic unavailable')
            for index in range(history_window.tabs.count()):
                history_window.tabs.setCurrentIndex(index);app.processEvents();capture=history_window.grab()
                if capture.isNull():raise ValueError(f'History study tab {index} did not render')
                capture.save(str(destination/f'stress-history-{index}.png'))
            history_window.tabs.setCurrentIndex(4)
            for mode in range(3):
                history_window.plot_mode.setCurrentIndex(mode);app.processEvents();capture=history_window.grab()
                if capture.isNull() or not history_window.plot.rendered_items:raise ValueError('History plot did not render')
                capture.save(str(destination/f'history-plot-{mode}.png'))
            history=history_window.read_study();history.save(destination/'example.gearforge-history')
            loaded=HistoryStudy.load(destination/'example.gearforge-history')
            if asdict(loaded)!=history_result['inputs']:raise ValueError('History inputs did not round-trip')
            if not history_window.start_job('history-export',loaded,destination/'history-calculation'):raise ValueError('History export worker did not start')
            wait_history_worker();manifest=verify_bundle(destination/'history-calculation')
            exported=json.loads((destination/'history-calculation/calculation.json').read_text())
            if exported['study_sha256']!=history_result['study_sha256']:raise ValueError('History exported fingerprint changed')
            if not math.isclose(history_result['damage'],.16310411314380596,rel_tol=1e-10):raise ValueError('Synthetic history damage changed')
            if history_result['production_approved'] or history_result['rated_gearbox_life_hours'] is not None:raise ValueError('History falsely approves gearbox life')
            state['stress_history']={'app_version':history_result['application_version'],'tabs_rendered':history_window.tabs.count(),
                'diagrams_rendered':3,'verified_files':len(manifest['files']),'synthetic_damage':history_result['damage'],
                'expanded_samples':history_result['counting']['expanded_samples'],'calculation_and_export_workers':True,
                'study_sha256':history_result['study_sha256'],'production_approved':False}
        except Exception as exc:errors.append(f'Stress history: {exc}')
        finally:history_window.dirty=False;history_window.close()
        finish()
    window.generate();timer.timeout.connect(tick);timer.start()
    app.exec()
    print(json.dumps(json.loads((destination/"desktop-smoke.json").read_text()),indent=2))
    return 1 if errors else 0
