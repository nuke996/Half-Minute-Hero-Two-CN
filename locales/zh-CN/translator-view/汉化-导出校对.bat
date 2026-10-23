@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0."
set "PY=C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"
if not exist "..\..\..\tools\build_cn.py" goto NOFILE
echo [REVIEW] export translator-facing JSON files into THIS folder
echo          (locales/<locale>/translator-view/).
echo Output: 10_ui_*.json / 20_dialogue_*.json / protected/ /
echo         30_multiline.json / 40_dlc01.json / dict/.
echo         Only the "zh" field should be edited.
echo Needs the original game files (a clean game dir, or *.bak backups).
"%PY%" "..\..\..\tools\export_review.py"
echo.
pause
exit /b 0
:NOFILE
echo.
echo ERROR: tools\build_cn.py not found in the repository.
echo Run this .bat from locales\<locale>\translator-view.
echo.
pause
exit /b 1
