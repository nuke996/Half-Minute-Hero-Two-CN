# -*- coding: utf-8 -*-
"""t180_verify_g3.py —— G3 装备名 功能级验收（只读）

① 源表（b147/b357/b736/b998 pos4）反解 == t172_g3_eq.json；
② 账本 装备名-G3 的每个槽反解 == 登记时的 new（含内嵌 0xFF×4 前缀副本）；
③ 译名缺字 0；
④ 4 个源表"除登记写入范围外整条记录与写入前一致"（未牵连邻字段）；
⑤ cscv 装备表孪生（b144/b338/b705/b975）名字字段仍日文原版。
"""
import os
import sys
import json
import collections

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
os.chdir(W)
sys.path.insert(0, W)
import s2a                      # noqa: E402
import t140_name_revert as T    # noqa: E402
import nmledger                 # noqa: E402
import build_cn as B            # noqa: E402

OUT = paths.build('t180_verify_g3.txt')
PREV = os.path.join(paths.BUILD_DIR, '_pre_t175', '20260919_090724')
STRIDE, POS = 268, 4
SRC = [(147, 494), (357, 614), (736, 614), (998, 96)]
BATCH = '装备名-G3'
LABEL = 'G3 装备名'
TWINS = [(144, 147, 494), (338, 357, 614), (705, 736, 614), (975, 998, 96)]
EQF = os.path.join(W, 't172_g3_eq.json')
# ★ 已参数化：新批次用薄包装脚本覆盖 LABEL/BATCH/PREV/STRIDE/POS/SRC/TWINS/EQF/OUT 再调用即可
#   （见 t191_g5_verify.py）。

rows_, _e, _t, _en, _tb, _s, _c, cmap, st_ = B.build_plan()
native = st_['native_set']
rev = {}
for ch, by in cmap.items():
    rev.setdefault(by, ch)


def dec_carrier(b):
    o, i = [], 0
    while i < len(b):
        c = b[i]
        if c < 0x80:
            o.append(chr(c)); i += 1; continue
        if 0x81 <= c <= 0x9f or 0xe0 <= c <= 0xfc:
            pair = bytes(b[i:i + 2])
            o.append(rev.get(pair) or pair.decode('cp932', 'replace'))
            i += 2
        else:
            i += 1
    return ''.join(o)


def core(arc, bi, pos, rec):
    raw = T.val_at(arc, bi, pos, rec)
    return (raw or b'')[T.strip_lead(raw or b''):]


out = []
def p(s=''):
    out.append(s)

p('#' * 100)
p(' %s 功能级验收（用当前字库反解 live）' % LABEL)
p('#' * 100)

eq = json.load(open(EQF, encoding='utf-8'))

# ① 源表反解
p('')
p('── ① 源表 pos4 名字列反解（用当前字库）')
for tag in ('LANG_JA', 'LANG_EN'):
    arc = s2a.Archive(T.FILEMAP[tag])
    jb = s2a.Archive(T.BAKMAP['LANG_JA'])
    bad = []
    n_ok = 0
    for (bi, n) in SRC:
        for rec in range(n):
            ja_s = T.dec(core(jb, bi, POS, rec))
            exp = eq.get(ja_s)
            if not exp:
                continue
            got = dec_carrier(core(arc, bi, POS, rec))
            if got == exp:
                n_ok += 1
            else:
                bad.append((bi, rec, got, exp))
    p('   %-8s 源表应译 %d 条 ｜ 反解正确 %d ｜ 不符 %d' % (tag, n_ok + len(bad), n_ok, len(bad)))
    for x in bad[:10]:
        p('      b%d rec%d 反解=%r 期望=%r' % x)

# ② 账本槽反解
p('')
p('── ② 账本槽反解')
bs = [b for b in nmledger.batches() if b['id'] == BATCH]
arcs = {}
tot = bad2 = 0
samples = []
for b in bs:
    for e in b['edits']:
        tot += 1
        if e['f'] not in arcs:
            arcs[e['f']] = s2a.Archive(T.FILEMAP[e['f']])
        blob = bytes(arcs[e['f']].blobs[e['b']])
        nb = bytes.fromhex(e['new'])
        v = blob[e['off']:e['off'] + len(nb)]
        if v != nb:
            bad2 += 1
            if len(samples) < 10:
                samples.append((e['f'], e['b'], e['off'], v.hex(), e['new']))
        if len(samples) == 0 and tot <= 6:
            pass
p('   批次 %s ｜ 槽 %d ｜ 与登记 new 不等 %d' % (BATCH, tot, bad2))
for x in samples:
    p('      ⚠ %s b%d off%d 实际=%s 期望=%s' % x)

# ③ 缺字
miss = [k for k, z in eq.items() if any(ord(c) >= 0x80 and c not in cmap and c not in native for c in z)]
p('')
p('── ③ 译名缺字：%d 条' % len(miss))
for k in miss[:10]:
    p('      %s -> %s' % (k, eq[k]))

# ④ 相邻字段未牵连（源表 4 个 blob）
p('')
p('── ④ 源表"除登记写入范围外整条记录与写入前一致"')
edits = [e for b in bs for e in b['edits']]
for (bi, n) in SRC:
    cur = s2a.Archive(T.FILEMAP['LANG_JA'])
    old = s2a.Archive(os.path.join(PREV, 'LANG_JA.s2a'))
    covered = set()
    for e in edits:
        if e['f'] != 'LANG_JA' or e['b'] != bi:
            continue
        base_e = 16 + ((e['off'] - 16) // STRIDE) * STRIDE
        span = max(len(bytes.fromhex(e['new'])), len(bytes.fromhex(e['old'])))
        for k in range(e['off'] - base_e, e['off'] - base_e + span):
            covered.add(k)
    same = 0
    for rec in range(n):
        base = 16 + rec * STRIDE
        okrec = True
        for off in range(STRIDE):
            if off in covered:
                continue
            if bytes(cur.blobs[bi])[base + off] != bytes(old.blobs[bi])[base + off]:
                okrec = False
                break
        if okrec:
            same += 1
    p('   b%-4d 未牵连记录：%d/%d ⇒ %s' % (bi, same, n, '✅' if same == n else '⚠'))

# ⑤ cscv 孪生
p('')
p('── ⑤ cscv 装备表孪生名字字段')
cs = s2a.Archive(T.FILEMAP['cscv'])
jab = s2a.Archive(T.BAKMAP['LANG_JA'])
for (cb, lb, n) in TWINS:
    nd = []
    for rec in range(n):
        o = 16 + rec * STRIDE + POS
        a = bytes(cs.blobs[cb])[o:o + 64].split(b'\x00')[0]
        b = bytes(jab.blobs[lb])[o:o + 64].split(b'\x00')[0]
        if a != b:
            nd.append((rec, a.hex(), T.dec(b)))
    p('   cscv b%-4d ≡ JA b%-4d ：%d/%d 日文原版 %s' % (cb, lb, n - len(nd), n, '✅' if not nd else 'ℹ'))
    for x in nd[:6]:
        p('       rec%-3d cscv=%s JA=%r' % x)
open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
print('\n'.join(out))
