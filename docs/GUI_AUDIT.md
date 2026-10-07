# Apple HIG audit and implemented improvements — rc2

Scope: Qt Widgets desktop application reviewed against Apple's macOS, keyboard,
accessibility, motion and appearance guidance. This is a code and Linux offscreen
audit, not Apple certification or evidence of macOS/VoiceOver compatibility.

| Area | Finding in rc1 | Implemented in rc2 | Verification boundary |
| --- | --- | --- | --- |
| Native controls | Forced Fusion and custom skins | Platform style; native controls and menus; semantic heading styles only | Linux rendered; macOS manual pass pending |
| Typography | Fixed 12 px and non-system font | System font; readable default; 115%/130% settings | Native Qt font inspected |
| Appearance | Dark-only application | System/light/dark preferences; platform color-scheme hint | Qt may not support override on every platform |
| Window layout | Fixed sidebar and cramped inspection | Resizable, hideable sidebar; saved design split; dedicated simulation page | Five pages rendered at default size |
| Menu behavior | Missing view/settings/window commands | File, Design, View, Window and Help; native About/Preferences/Quit roles | Qt QAction roles configured; macOS positioning pending |
| Shortcuts | Control shortcuts without systematic review | Standard New/Open/Save/Save As/Quit; Cmd on macOS through Qt mapping; no Save As conflict | Keyboard viewer regression test |
| Document state | Modified marker absent from title | Qt document marker and represented path; Finder file-open handler | Save/load integration tested; Finder pending |
| Input accessibility | Names/buddies incomplete | Named controls, form label buddies, explicit table/viewer descriptions | Qt properties tested; screen reader audit pending |
| Status | Bright colors on dark only | PASS/WARN/FAIL and Overload text; native selection palette | Color-independent values verified |
| Viewer access | Mouse-only orbit/zoom | Focusable viewer; arrow orbit, +/− zoom, R reset, Space play | Qt keyboard regression test |
| Motion | No accessible control; frame-based schematic | Explicit play/pause/seek/step; reduced-motion setting; macOS setting read at launch | Reduced-motion test; OS preference detection needs Mac test |
| Task feedback | CAD actions available without valid selection | Menu actions disabled while busy or stale; cancellable worker and progress | Worker/stale-state tests |
| Desktop bundle | macOS build lacked .app metadata | .app target, icon, project UTI and document type; windowed Mac/Windows entry | Only Linux binary built locally |

The CAD canvas uses an intentional dark technical surface in both appearances.
It presents readable text and geometry; it does not emulate Liquid Glass or use
transparency effects. A full custom-canvas accessibility tree is still absent;
the named viewer, numeric stage table and operating table provide alternatives.

## Before promoting a macOS release

Run on a real supported Mac, including launch from Finder, project double-click,
document proxy path, application menu, Cmd shortcuts, window resizing/full screen,
VoiceOver, Full Keyboard Access, system light/dark changes, Increase Contrast,
130% text, Reduce Motion and display scaling. Check the app's actual permission
to read the launch-time motion setting. Sign with Developer ID, enable hardened
runtime with reviewed Qt/Python entitlements, notarize, staple and assess with
Gatekeeper. No signing or accessibility claim should be made before this pass.

## Primary guidance

- [Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos)
- [Keyboards](https://developer.apple.com/design/human-interface-guidelines/keyboards)
- [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)
- [Motion](https://developer.apple.com/design/human-interface-guidelines/motion)
- [Dark Mode](https://developer.apple.com/design/human-interface-guidelines/dark-mode)
- [Reduced Motion evaluation](https://developer.apple.com/help/app-store-connect/manage-app-accessibility/reduced-motion-evaluation-criteria)
- [Qt macOS behavior and modifier mapping](https://doc.qt.io/qtforpython-6/overviews/qtdoc-macos-issues.html)
- [Qt 6.8 color-scheme hints](https://doc.qt.io/qtforpython-6.8/PySide6/QtGui/QStyleHints.html)

Reviewed October 6, 2026. Platform tests are recorded separately in VALIDATION.json.

## Generated-root elastic editor

Seven native tabs expose material evidence, support/mesh controls, all retained
duty cases, mesh/stress maps, root curves, assessment and complete source inputs.
Numerical work runs in a separate cancellable file-protocol process. Inputs are
disabled during that work; edits invalidate results. Failed saves preserve the
previous path and unsaved state. Case/position selectors control both stress views;
deformation exaggeration and field units stay visible. Automated source/native
smoke captures every tab, six mesh views and a curve view, then reopens inputs,
exports through the worker and checks the complete integrity manifest.
