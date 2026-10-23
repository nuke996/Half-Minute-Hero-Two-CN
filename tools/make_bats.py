# -*- coding: utf-8 -*-
"""重建一键 bat：纯 ASCII + CRLF，避免 cmd 编码/换行问题。
Python 自己负责打印中文（chcp 65001 + PYTHONIOENCODING）。

两处输出位置：
  · 装机类 bat → 游戏目录（game_dir，默认 work/original）；该目录不入版本控制。
  · 校对类 bat（导出/导入/回滚）→ locales/<locale>/translator-view/，
    与校对 JSON 同目录，随仓库一起分发，译者无需拿到游戏目录里的 bat。
"""
import os
import sys

import paths
B = paths.GAME_DIR
TV = os.path.join(paths.DATA_DIR, 'translator-view')
TOOLSREL = os.path.relpath(os.path.join(paths.REPO_DIR, 'tools'), B)
TOOLSREL_TV = os.path.relpath(os.path.join(paths.REPO_DIR, 'tools'), TV)

# 与校对 JSON 一起放在 translator-view/ 的入口（导出/导入/回滚）
REVIEW_BATS = {'汉化-导出校对.bat', '汉化-导入校对.bat', '汉化-导入校对-回滚.bat',
               '汉化-导入校对-不应用词典.bat'}

CANDIDATES = [p for p in [
    sys.executable,
    r'C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe',
    r'C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12\python.exe',
] if p.isascii()]      # bat 内容必须纯 ASCII；仓库路径含中文时跳过 venv 解释器
if not CANDIDATES:
    CANDIDATES = ['python']

found = [p for p in CANDIDATES if os.path.exists(p)]
print('存在的 Python:')
for p in found:
    print('  OK  ', p)
for p in CANDIDATES:
    if p not in found:
        print('  MISS', p)

def head(tools_rel):
    return [
        '@echo off',
        'chcp 65001 >nul',
        'set PYTHONIOENCODING=utf-8',
        'cd /d "%~dp0."',
        'set "PY=' + CANDIDATES[0] + '"',
        'if not exist "%PY%" set "PY=' + CANDIDATES[1] + '"',
        'if not exist "%PY%" set "PY=python"',
        'if not exist "' + tools_rel + '\\build_cn.py" goto NOFILE',
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
    '汉化-安装-不应用词典.bat': [
        'echo [NOREPL] full Chinese build WITHOUT replace_map (hl_map still applies).',
        'echo Use this to compare the raw translation wording in game.',
        'echo [1/2] revert to original...',
        '"%PY%" "' + TOOLSREL + '\\build_cn.py" revert',
        'echo [2/2] install no-dictionary build...',
        'set HMH2_APPLY_REPL=0',
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
    '汉化-导出校对.bat': [
        'echo [REVIEW] export translator-facing JSON files into THIS folder',
        'echo          (locales/<locale>/translator-view/).',
        'echo Output: 10_ui_*.json / 20_dialogue_*.json / protected/ /',
        'echo         30_multiline.json / 40_dlc01.json / dict/.',
        'echo         Only the "zh" field should be edited.',
        'echo Needs the original game files (a clean game dir, or *.bak backups).',
        '"%PY%" "' + TOOLSREL + '\\export_review.py"',
    ],
    '汉化-导入校对.bat': [
        'echo [REVIEW] import the edited JSON back into the tables, then refresh dist/.',
        'echo Self-check runs first: oversize / unknown id / bad chars.',
        'echo If anything is wrong it ABORTS (nothing written, dist untouched) and the',
        'echo report lists exactly which entry is broken.',
        'echo This does NOT touch the game dir; run the install .bat in the game dir',
        'echo (Han-hua-An-Zhuang.bat) to test the Chinese text in game.',
        'echo To build WITHOUT the replace dictionary, use the no-dictionary import',
        'echo .bat in this folder (same edits, Z15-norepl output).',
        '"%PY%" "' + TOOLSREL + '\\import_review.py" apply',
    ],
    '汉化-导入校对-不应用词典.bat': [
        'echo [REVIEW-NOREPL] import the edited JSON back into the tables, then refresh dist/.',
        'echo Same self-check as the normal import, but the package is built WITHOUT',
        'echo replace_map (hl_map highlight translations still apply).',
        'echo Use this only to compare the raw translation wording.',
        'echo This does NOT touch the game dir; install with the game-folder .bat to test.',
        '"%PY%" "' + TOOLSREL + '\\import_review.py" apply --no-repl',
    ],
    '汉化-导入校对-回滚.bat': [
        'echo [REVIEW] restore the tables from before the last review import,',
        'echo             then refresh dist/.',
        '"%PY%" "' + TOOLSREL + '\\import_review.py" revert',
    ],
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


def tail(where):
    return [
        'echo.',
        'pause',
        'exit /b 0',
        ':NOFILE',
        'echo.',
        'echo ERROR: tools\\build_cn.py not found in the repository.',
        'echo Run this .bat from ' + where + '.',
        'echo.',
        'pause',
        'exit /b 1',
    ]


TAIL = tail('the game folder (where HMH2.exe is)')
TAIL_TV = tail('locales\\<locale>\\translator-view')

os.makedirs(TV, exist_ok=True)
for name, body in BODY.items():
    is_review = name in REVIEW_BATS
    out_dir = TV if is_review else B
    rel = TOOLSREL_TV if is_review else TOOLSREL
    lines = head(rel) + [ln.replace(TOOLSREL, rel) for ln in body] + \
            (TAIL_TV if is_review else TAIL)
    data = '\r\n'.join(lines) + '\r\n'
    p = os.path.join(out_dir, name)
    with open(p, 'wb') as fh:
        fh.write(data.encode('ascii'))
    print('written', os.path.relpath(p, paths.REPO_DIR), len(data), 'bytes (ASCII/CRLF)')

# 旧的校对 bat 曾在游戏目录，迁移后清理，避免两份入口指向不同路径
for name in sorted(REVIEW_BATS):
    p = os.path.join(B, name)
    if os.path.exists(p):
        os.remove(p)
        print('removed', os.path.relpath(p, paths.REPO_DIR))

for name in REMOVE:
    p = os.path.join(B, name)
    if os.path.exists(p):
        os.remove(p)
        print('removed', name)
print('OK')
