; A complete per-user installer. No downloads or administrator access at install time.
Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"

Name "GearForge Studio ${VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\GearForge Studio"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
VIProductVersion "${NUMERIC_VERSION}"
VIAddVersionKey "ProductName" "GearForge Studio"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "FileDescription" "GearForge Studio offline Windows installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "GearForge Studio contributors"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\GearForgeStudio"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "Install GearForge Studio and its complete desktop and CAD runtime.$\r$\n$\r$\nNo Python installation or internet connection is needed to run the app.$\r$\n$\r$\nThis is an unsigned engineering release candidate. Production gearbox load and life ratings remain unqualified."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${PROJECT_DIR}\LICENSE"
!define MUI_DIRECTORYPAGE_TEXT_TOP "Choose an empty folder for GearForge Studio. To replace an existing installation, uninstall it first; your projects and settings are kept."
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\GearForgeStudio.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "GearForge Studio requires 64-bit Windows." /SD IDOK
    SetErrorLevel 1
    Quit
  ${EndIf}
  SetRegView 64
  SetShellVarContext current
FunctionEnd

Section "GearForge Studio" SEC_MAIN
  ; NSIS file operations must stay within the legacy Windows path limit.
  StrLen $0 "$INSTDIR"
  IntCmp $0 ${MAX_INSTALL_DIR_LENGTH} path_length_ok path_length_ok path_too_long
  path_too_long:
    MessageBox MB_OK|MB_ICONSTOP "The installation path is too long. Choose a shorter folder so every program and license file can be installed." /SD IDOK
    SetErrorLevel 1
    Abort
  path_length_ok:
  ; Never overlay another application or a user's nonempty folder.
  IfFileExists "$INSTDIR\." 0 directory_ready
  FindFirst $0 $1 "$INSTDIR\*"
  check_entry:
    StrCmp $1 "" directory_empty
    StrCmp $1 "." next_entry
    StrCmp $1 ".." next_entry
    FindClose $0
    MessageBox MB_OK|MB_ICONSTOP "The destination folder is not empty. Choose another folder or uninstall the existing version first." /SD IDOK
    SetErrorLevel 1
    Abort
  next_entry:
    FindNext $0 $1
    Goto check_entry
  directory_empty:
    FindClose $0
  directory_ready:
  SetOutPath "$INSTDIR"
  File /r "${SOURCE_DIR}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\GearForge Studio"
  CreateShortcut "$SMPROGRAMS\GearForge Studio\GearForge Studio.lnk" "$INSTDIR\GearForgeStudio.exe"
  CreateShortcut "$SMPROGRAMS\GearForge Studio\Uninstall GearForge Studio.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "GearForge Studio"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "GearForge Studio contributors"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\GearForgeStudio.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "URLInfoAbout" "https://github.com/jonahsaunders/Gearforge-Studio"
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "EstimatedSize" ${INSTALLED_KIB}
SectionEnd

Function un.onInit
  SetRegView 64
  SetShellVarContext current
FunctionEnd

Section "Uninstall"
  SetOutPath "$TEMP"
  ; Only delete files shipped by this build. Never recursively remove user data.
  !include "${UNINSTALL_FILES}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ; Another installation may have since claimed the shared shortcuts/registry.
  ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "InstallLocation"
  ${If} $0 == $INSTDIR
    Delete "$SMPROGRAMS\GearForge Studio\GearForge Studio.lnk"
    Delete "$SMPROGRAMS\GearForge Studio\Uninstall GearForge Studio.lnk"
    RMDir "$SMPROGRAMS\GearForge Studio"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
  ${EndIf}
SectionEnd
