@echo off
rem build.bat - compile 32-bit dinput8 proxy DLL with zig cc
cd /d "%~dp0"
set ZIG=tools\zigpkg\ziglang\zig.exe
if not exist "%ZIG%" (
  echo ERROR: zig not found at %ZIG%
  exit /b 1
)
"%ZIG%" cc -target i686-windows-gnu -O2 -shared -o dinput8.dll main.c -Wl,--kill-at -Wl,--subsystem,windows
if errorlevel 1 (
  echo BUILD FAILED
  exit /b 1
)
echo BUILD OK: dinput8.dll
dir dinput8.dll | findstr dinput8
