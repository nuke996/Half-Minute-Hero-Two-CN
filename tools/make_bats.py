# -*- coding: utf-8 -*-
"""重建根目录三个一键 bat：纯 ASCII + CRLF，避免 cmd 编码/换行问题。
Python 自己负责打印中文（chcp 65001 + PYTHONIOENCODING）。
"""
import os
import sys

import paths
B = paths.GAME_DIR
TOOLSREL = os.path.relpath(os.path.join(paths.REPO_DIR, 'tools'), B)

CANDIDATES = [
    sys.executable,
    r'C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe',
    r'C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe',
]

found = [p for p in CANDIDATES if os.path.exists(p)]
print('存在的 Python:')
for p in found:
    print('  OK  ', p)
for p in CANDIDATES:
    if p not in found:
        print('  MISS', p)

HEAD = [
    '@echo off',
    'chcp 65001 >nul',
    'set PYTHONIOENCODING=utf-8',
    'cd /d "%~dp0."',
    'set "PY=' + CANDIDATES[0] + '"',
    'if not exist "%PY%" set "PY=' + CANDIDATES[1] + '"',
    'if not exist "%PY%" set "PY=python"',
    'if not exist "' + TOOLSREL + '\\build_cn.py" goto NOFILE',
]

BODY = {
    '汉化-安装.bat': [
        'echo [V2.23] full Chinese build.',
        'echo NEW in v2.23: Dash no longer shows BLANK (offset bug fixed), and every',
        'echo                 non-online string in the system-message table is Chinese',
        'echo                 (Yes / No, Level Up, Goddess Room, Gallery, Quit, Rank...).',
        'echo                 Online-only strings stay in the original language on purpose.',
        'echo Carried over from v2.21: village/town names, chapter titles, the No option',
        'echo                 and "Retry EZ Mode" are all translated.',
        'echo Glyphs: WenQuanYi Bitmap Song 13px @12x12 ink + gray thickness + dark outline.',
        'echo Entity names (items / monsters / weapons / skills) stay in the original language.',
        'echo Test: 1) dialogue font looks like the original  2) weapon skills still animate',
        'echo       3) stage select shows Chinese place names',
        'echo       4) Yes/No shows Chinese, Dash/Pray show Chinese.',
        'echo If the new font looks wrong, run  Han-hua-Jiu-Zi-Ti-Ban-An-Zhuang.bat.',
        'echo If place names / chapter titles break something, run',
        'echo   Han-hua-Di-Ming-Zhang-Jie-Huan-Yuan.bat.',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install v2.23 build...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_menu',
    ],
    '汉化-地名章节还原.bat': [
        'echo [V2.21-FALLBACK] Village names + chapter titles: show the ORIGINAL text again.',
        'echo.',
        'echo Use this ONLY if the Chinese place names or chapter titles cause a problem.',
        'echo It skips the two extra cscv record tables (place names / chapter titles),',
        'echo so they fall back to the original text. Everything else stays translated.',
        'echo [1/1] rebuilding without place names / chapter titles...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_noplace',
    ],
    '汉化-旧字体版安装.bat': [
        'echo [V2.20-GLYPH] same text, but glyphs go back to SimSun 16px (bigger, no outline).',
        'echo Use this only if you prefer the old font look.',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install old-glyph build...',
        'set HMH2_FONT=simsun',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_menu',
    ],
    '汉化-章节标题还原.bat': [
        'echo [V2.20-FALLBACK] Chapter titles: show the ORIGINAL English/Japanese again.',
        'echo.',
        'echo Use this ONLY if translating chapter titles causes a problem',
        'echo (e.g. a stage list or the title screen misbehaves).',
        'echo It removes the 89 chapter-title entries from the UI word list and reinstalls,',
        'echo so titles fall back to the original text. Everything else stays translated.',
        'echo To turn the Chinese titles back ON, run  Han-hua-Zhang-Jie-Biao-Ti-Hui-Fu.bat.',
        'echo [1/1] rebuilding without chapter titles...',
        '"%PY%" "' + TOOLSREL + '\\chap_fallback.py" off',
    ],
    '汉化-章节标题恢复.bat': [
        'echo [V2.20] Chapter titles: turn the Chinese titles back ON.',
        'echo [1/1] rebuilding with chapter titles...',
        '"%PY%" "' + TOOLSREL + '\\chap_fallback.py" on',
    ],
    '汉化-还原.bat': ['echo [1/1] restoring...', '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert'],
    '汉化-检查状态.bat': ['echo [1/1] checking...', '"%PY%" "' + TOOLSREL + '\\build_cn.py" check'],
    '汉化-技能测试A-仅字模.bat': [
        'echo [TEST A] font+table ONLY, no text translation.',
        'echo If skills STILL break with this package, the problem is in the font/atlas/table layer.',
        'echo If skills work, the problem is in the translated text layer.',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install font+table only...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_font',
    ],
    '汉化-技能测试B-不同步cscv.bat': [
        'echo [TEST B] translate LANG text but DO NOT sync duplicated blobs into cscv.',
        'echo If skills work with this package, the problem is the cscv content-sync (H4).',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install text without cscv sync...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_nosync',
    ],
    '汉化-技能测试C-同名不翻.bat': [
        'echo [TEST C] strings that also exist inside cscv scripts stay Japanese.',
        'echo If skills work with this package, scripts compare names from LANG (theory confirmed).',
        'echo NOTE: Japanese kana may display wrong glyphs in this test - that is expected.',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install with collision whitelist...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_nocollide',
    ],
    '汉化-技能测试D-机制表不翻.bat': [
        'echo [TEST D] = C + skill/class mechanic tables (blob 666/128/136/317) stay original.',
        'echo If Critical Striker works with D but not C, the mechanic tables are read by the game.',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install with mechanic-table whitelist...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_nomech',
    ],
    '汉化-菜单版安装.bat': [
        'echo [V2.22] same as  Han-hua-An-Zhuang.bat  (kept for the old shortcut).',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install v2.22 build...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_menu',
    ],
    '汉化-保守版安装.bat': [
        'echo [V2.15-SAFE] same translation, but UI key labels / section titles / chapter',
        'echo titles stay English.',
        'echo Use this if the v2.16+ labels look wrong on screen.',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install conservative build...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_menu_safe',
    ],
    '汉化-女神菜单还原.bat': [
        'echo [V2.19-FALLBACK] Goddess Room options: show the ORIGINAL names again.',
        'echo.',
        'echo Use this ONLY if clicking Change Clothes / Window Skin / Timer Skin',
        'echo still closes the game with the normal build.',
        'echo It restores the original text of those 4 menu entries (item table group',
        'echo label + menu entry name + its second copy), in LANG_JA / LANG_EN / cscv.',
        'echo Everything else stays translated.',
        'echo.',
        'echo [1/3] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/3] install normal build...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" apply_menu',
        'echo [3/3] restore original names for those 4 menu entries...',
        '"%PY%" "' + TOOLSREL + '\\fix_pairs.py" orig',
        'echo.',
        'echo Done. Enter the game and check the three sub-menus.',
        'echo To go back to the Chinese names, run  Han-hua-An-Zhuang.bat  again.',
    ],
    '汉化-女神菜单一致性检查.bat': [
        'echo [CHECK] Goddess Room option names: are all copies consistent?',
        'echo (item table label / menu entry name / second copy, in JA + EN + cscv)',
        '"%PY%" "' + TOOLSREL + '\\fix_pairs.py" check',
    ],
}

REMOVE = ['汉化-UI词表版安装.bat']

TAIL = [
    'echo.',
    'pause',
    'exit /b 0',
    ':NOFILE',
    'echo.',
    'echo ERROR: _work\\build_cn.py not found.',
    'echo Run this .bat from the game folder (where HMH2.exe is).',
    'echo.',
    'pause',
    'exit /b 1',
]

for name, body in BODY.items():
    lines = HEAD + body + TAIL
    data = '\r\n'.join(lines) + '\r\n'
    p = os.path.join(B, name)
    with open(p, 'wb') as fh:
        fh.write(data.encode('ascii'))
    print('written', name, len(data), 'bytes (ASCII/CRLF)')

for name in REMOVE:
    p = os.path.join(B, name)
    if os.path.exists(p):
        os.remove(p)
        print('removed', name)
print('OK')
