@echo off
rem build.bat - compile 32-bit dinput8 proxy DLL with zig cc, then undecorate exports
cd /d "%~dp0"
rem ZIG 解析顺序：外部环境变量 > PATH > 仓库内 tools/zigpkg
if defined ZIG goto HAVE_ZIG
for %%I in (zig.exe) do if not "%%~$PATH:I"=="" set "ZIG=%%~$PATH:I"
if not defined ZIG set ZIG=..\zigpkg\ziglang\zig.exe
:HAVE_ZIG
if not exist "%ZIG%" (
  echo ERROR: zig not found at %ZIG%
  echo        install zig and put it on PATH, or set the ZIG environment variable.
  exit /b 1
)
rem 说明（zig 0.13 实测）：
rem   * 目标三元组用 x86-windows-gnu（zig 的 arch 名是 x86，旧的 i686-... 已不被接受）
rem   * zig 的 lld 不支持 --kill-at，因此编译产物导出名会带 @N 装饰，
rem     由 fix_exports.js 原位截断为未装饰名（游戏按未装饰名导入）
rem   * -mstackrealign：strncmp 钩子 stub 在游戏栈上以 cdecl 回调本 DLL 函数，
rem     栈对齐不由 ABI 保证，强制重对齐可避免 SSE 访问未对齐栈导致崩溃
"%ZIG%" cc -target x86-windows-gnu -O2 -mstackrealign -shared -o dinput8.dll main.c -Wl,--subsystem,windows
if errorlevel 1 (
  echo BUILD FAILED
  exit /b 1
)
node fix_exports.js dinput8.dll
if errorlevel 1 (
  echo FIX EXPORTS FAILED
  exit /b 1
)
node check_dll.js dinput8.dll
echo BUILD OK: dinput8.dll
dir dinput8.dll | findstr dinput8
