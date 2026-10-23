@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0."
set "PY=C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"
if not exist "..\..\..\tools\build_cn.py" goto NOFILE
echo [REVIEW-NOREPL] import the edited JSON back into the tables, then refresh dist/.
echo Same self-check as the normal import, but the package is built WITHOUT
echo replace_map (hl_map highlight translations still apply).
echo Use this only to compare the raw translation wording.
echo This does NOT touch the game dir; install with the game-folder .bat to test.
"%PY%" "..\..\..\tools\import_review.py" apply --no-repl
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
