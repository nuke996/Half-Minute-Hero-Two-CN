@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0."
set "PY=C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not exist "%PY%" set "PY=C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=python"
if not exist "..\..\..\tools\build_cn.py" goto NOFILE
echo [REVIEW] restore the tables from before the last review import,
echo             then refresh dist/.
"%PY%" "..\..\..\tools\import_review.py" revert
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
