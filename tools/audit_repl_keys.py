# -*- coding: utf-8 -*-
"""v2.32 REPL 规则全量审计：按装机字库判定每条规则"键用字"是否已在库。
键全在库 = 删掉后字库也不会缺字（理论上可删，但删=回到原始译文措辞）。
键仍缺字 = 规则仍在干活，删了必缺字（须保留，或先给缺字注入字形）。
输出 -> _work/_rule_audit2.txt
"""
import sys, os, re

import paths
W = paths.DATA_DIR
sys.path.insert(0, W); os.chdir(W)
import build_cn as B

rows, ents, types, end, tb, slots, chosen, cmap, st = B.build_plan()
native = st['native_set']

def cov(ch):
    return ord(ch) < 0x80 or ch in cmap or ch in native

# 按源文件的 "============ 分组 ============" 标题归组
src = open('replace_map.py', encoding='utf-8').read().splitlines()
sec = None
sec_of = {}
pat_sec = re.compile(r'^# =+ (.+?) =+$')
pat_rule = re.compile(r"^'(.+?)'\s*:\s*'(.*)',\s*$")
for ln in src:
    s = ln.strip()
    m = pat_sec.match(s)
    if m:
        sec = m.group(1)
        continue
    m2 = pat_rule.match(s)
    if m2 and sec:
        sec_of[m2.group(1)] = sec

groups, bad = {}, []
n_ok = 0
for k, v in sec_of.items():
    miss = [c for c in k if not cov(c)]
    if miss:
        bad.append((k, sec_of[k], ''.join(miss)))
    else:
        n_ok += 1
        groups.setdefault(sec_of[k], []).append(k)

out = []
out.append('可解析规则: %d 条 = 键全在库 %d + 键仍缺字 %d' % (len(sec_of), n_ok, len(bad)))
out.append('')
out.append('== 键全在库 %d 条（字库角度都可删；删=显示回原始译文措辞）==' % n_ok)
for g in groups:
    out.append('[%s] %d 条' % (g, len(groups[g])))
out.append('')
out.append('== 键仍缺字 %d 条按分组（删了必缺字，须保留）==' % len(bad))
bg = {}
for k, g, m in bad:
    bg.setdefault(g, []).append('%s(缺%s)' % (k, m))
for g in bg:
    out.append('[%s] %d 条: %s' % (g, len(bg[g]), '、'.join(bg[g])))

open(paths.build('_rule_audit2.txt'), 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
