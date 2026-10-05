# assets/proxydll

Runtime-patch assets for the **DLL mode** (the default build mode).

## Contents

| File | Purpose | License |
|---|---|---|
| `dinput8.dll` | Proxy `dinput8` DLL (32-bit). Forwards the real system DLL and applies the character-table unlock at runtime. | MIT (project code) |
| `README.md` | This note. | - |

## Provenance

- Source: `tools/proxydll/` (`main.c`, `dinput8.def`, `build.bat`, `fix_exports.js`, ...).
- Built from that source with the zig toolchain:
  `zig cc -target i686-windows-gnu -O2 -shared -o dinput8.dll main.c -Wl,--kill-at -Wl,--subsystem,windows`.
- The DLL reads `hm2zh_patch.bin` from its own directory at load time. That file is
  **not** committed; the build generates it from the user's original `HMH2.exe.bak`
  via `tools/proxy_patch.py` (equivalently `tools/proxydll/gen_patch_bin.js`).

## Why it ships as a binary

It is our own redistributable tool (MIT), letting contributors use DLL mode without
installing a C toolchain. To rebuild it yourself, run `tools/proxydll/build.bat`
(requires `zig`); see `BUILDING.md`.

## Integrity

`dinput8.dll` never modifies files on disk. If the game executable is already in the
offline-patched state it detects that and skips patching. All patch records are
verified against expected original bytes before any write; on mismatch it aborts
without changing anything and logs to `hm2zh_patch.log`.
