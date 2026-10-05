# -*- coding: utf-8 -*-
"""v2.33：免除全部"键仍缺字"的 REPL 规则（81 条去重键 / 82 行）。
步骤：
  1) 用当前装机字库判定哪些规则的键含缺字 -> 免除清单
  2) 备份 replace_map.py -> .bak_v232_20260913
  3) 逐行删除免除规则，并在 REPL 开头插入说明注释
  4) 预检"子串连带"：免除键在剩余规则下会被改成什么（仅报告，不阻断）
输出 -> _work/_free_repl_report.txt
"""
import sys, os, re, shutil

import paths
W = paths.DATA_DIR
sys.path.insert(0, W); os.chdir(W)
import build_cn as B   # 旧 replace_map 仍在，用它的装机字库判定

rows, ents, types, end, tb, slots, chosen, cmap, st = B.build_plan()
native = st['native_set']

def cov(ch):
    return ord(ch) < 0x80 or ch in cmap or ch in native

SRC = os.path.join(W, 'replace_map.py')
BAK = SRC + '.bak_v232_20260913'
shutil.copy2(SRC, BAK)

# ---- 解析当前规则 ----
lines = open(SRC, encoding='utf-8').read().splitlines()
pat_sec = re.compile(r'^# =+ (.+?) =+$')
pat_rule = re.compile(r"^'(.+?)'\s*:\s*'(.*)',\s*$")
sec = None
parsed = []          # (lineno, key, val)
for i, ln in enumerate(lines):
    s = ln.strip()
    m = pat_sec.match(s)
    if m:
        sec = m.group(1); continue
    m2 = pat_rule.match(s)
    if m2 and sec:
        parsed.append((i, m2.group(1), m2.group(2)))

free = set()
for _i, k, v in parsed:
    if any(not cov(c) for c in k):
        free.add((k, v))
free_lines = {(k, v) for k, v in free}

out = []
out.append('免除规则(去重键): %d 个' % len({k for k, _ in free}))
out.append('将删除的行数    : %d' % sum(1 for _i, k, v in parsed if (k, v) in free_lines))

# ---- 重写文件 ----
new_lines = []
removed = 0
inserted = False
for ln in lines:
    s = ln.strip()
    m2 = pat_rule.match(s)
    if m2 and (m2.group(1), m2.group(2)) in free_lines:
        removed += 1
        continue
    new_lines.append(ln)
    if not inserted and s == 'REPL = {':
        new_lines += [
            '',
            '    # ============ v2.33 免除全部"键仍缺字"规则（经用户确认全免） ============',
            '    # 缺字时代的最后一批代用替换：键中的 69 个缺字（去重）已随装机自动入格',
            '    # （v2.32 时 2719/2847 格，免除后约 2788/2847，余约 59）。删除后显示回',
            '    # 原始译文用词（治疗/蜘蛛/骷髅/玻璃/咖喱/吾/瞧/疼…），替换词均为生硬代用。',
            '    # 保留的 418 条"键全在库"规则多为统一译名/风格职能，无字库收益，不动。',
            '    # 免除明细: _work/_capacity_eval.txt | 本文件备份: replace_map.py.bak_v232_20260913',
            '',
        ]
        inserted = True
open(SRC, 'w', encoding='utf-8').write('\n'.join(new_lines) + '\n')
out.append('已删除行数      : %d（备份 %s）' % (removed, os.path.basename(BAK)))

# ---- 预检子串连带（用改后的 REPL 重算）----
import importlib
import replace_map
importlib.reload(replace_map)
import build_cn as B2
B2.REPL = replace_map.REPL
art = []
for k, _v in sorted(free):
    r = B2.apply_repl(k)
    if r != k:
        art.append('%s -> %s（被剩余规则连带改写）' % (k, r))
out.append('')
out.append('== 子串连带预检（免除键在剩余规则下的显示结果）==')
out.append('\n'.join(art) if art else '无 —— 所有免除键显示回原词')

# ---- 语法自检 ----
import ast
ast.parse(open(SRC, encoding='utf-8').read())
out.append('')
out.append('replace_map.py 语法自检 OK；REPL 现有条数: %d' % len(replace_map.REPL))

open(paths.build('_free_repl_report.txt'), 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
