@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0."
set "PY=C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"
if not exist "..\..\..\tools\build_cn.py" goto NOFILE
echo [REVIEW] import the edited JSON back into the tables, then refresh dist/.
echo Self-check runs first: oversize / unknown id / bad chars.
echo If anything is wrong it ABORTS (nothing written, dist untouched) and the
echo report lists exactly which entry is broken.
echo This does NOT touch the game dir; run the install .bat in the game dir
echo (Han-hua-An-Zhuang.bat) to test the Chinese text in game.
echo To build WITHOUT the replace dictionary, use the no-dictionary import
echo .bat in this folder (same edits, Z15-norepl output).
echo Default import rebuilds dist/Z18-dlc-place-names (with Z17-video).
"%PY%" "..\..\..\tools\import_review.py" apply
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
