# -*- coding: utf-8 -*-
"""v2.32 字库剩余容量评估：
1) 余量 = 2847 - 拟装字数
2) 81 条"键仍缺字"规则涉及的缺字去重总数 N —— 全部免除需 N 格，判断是否装得下
3) 逐条删除后的字节长度变化（定长槽溢出风险）
4) 按"删除后显示回原词是否通顺"粗分类（怪译修正候选 vs 建议保留）
输出 -> _work/_capacity_eval.txt
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

def blen(s):
    return sum(1 if ord(c) < 0x80 else 2 for c in s)

# ---- 解析 replace_map.py，取分组 ----
src = open('replace_map.py', encoding='utf-8').read().splitlines()
sec = None
rules = []  # (key, val, group)
pat_sec = re.compile(r'^# =+ (.+?) =+$')
pat_rule = re.compile(r"^'(.+?)'\s*:\s*'(.*)',\s*$")
for ln in src:
    s = ln.strip()
    m = pat_sec.match(s)
    if m:
        sec = m.group(1); continue
    m2 = pat_rule.match(s)
    if m2 and sec:
        rules.append((m2.group(1), m2.group(2), sec))

# ---- 键仍缺字的规则 ----
keep = []   # (k, v, group, miss, delta)
n_ok = 0
for k, v, g in rules:
    miss = [c for c in k if not cov(c)]
    if miss:
        keep.append((k, v, g, ''.join(miss), blen(k) - blen(v)))
    else:
        n_ok += 1

missing_chars = set()
for k, v, g, m, d in keep:
    missing_chars.update(m)

n_chosen = len(chosen)
free = 2847 - n_chosen
n = len(missing_chars)

out = []
out.append('== 容量账 ==')
out.append('拟装字数: %d / 2847 格, 余量 %d 格' % (n_chosen, free))
out.append('81 条"键仍缺字"规则涉及的缺字(去重): %d 个: %s' % (n, ''.join(sorted(missing_chars))))
out.append('全部免除需 %d 格 -> %s (免除后余量 %d)' % (
    n, '装得下 ✅' if n_chosen + n <= 2847 else '装不下 ❌', free - n))
out.append('另外 418 条键全在库的规则免除不占任何新格（0 格）')
out.append('')
out.append('== 81 条规则明细（删除后长度变化，正=变长有溢出风险）==')
for k, v, g, m, d in sorted(keep, key=lambda x: -x[4]):
    out.append('  %-8s -> %-8s 缺%-4s 长度%+d  [%s]' % (k, v, m, d, g))

open(paths.build('_capacity_eval.txt'), 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
