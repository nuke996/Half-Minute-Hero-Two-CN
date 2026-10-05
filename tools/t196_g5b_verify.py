# -*- coding: utf-8 -*-
"""t196_g5b_verify.py —— G5b（排除键名槽）功能级验收（只读）

① 技能表 b666 pos0 反解 == t194_g5_eq2.json；
② 账本 技能名-G5b 每个槽反解 == 登记 new；
③ 译名缺字 0；
④ 源表 b666"除登记写入范围外整条记录与写入前一致"；
⑤ **★ 键名列 b666/pos292（288~399）必须与日文原版逐字节一致**（本次事故的守卫）；
⑥ cscv 孪生 b633 ≡ LANG_JA b666 名字字段仍日文原版。
"""
import os
import sys
import json

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
os.chdir(W)
sys.path.insert(0, W)
import s2a                      # noqa: E402
import t140_name_revert as T    # noqa: E402
import nmledger                 # noqa: E402
import build_cn as B            # noqa: E402

OUT = paths.build('t196_g5b_verify.txt')
PREV = os.path.join(paths.BUILD_DIR, '_pre_t195', '20260919_100303')
STRIDE, POS, N = 376, 0, 87
BATCH = '技能名-G5b'
EQF = os.path.join(W, 't194_g5_eq2.json')
KEYCOL = (288, 376)     # 键名列区间（pos292；376 起属于下一条记录）

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
p(' G5b 技能名（排除键名槽）功能级验收')
p('#' * 100)
eq = json.load(open(EQF, encoding='utf-8'))

p('')
p('── ① 源表 pos0 名字列反解')
for tag in ('LANG_JA', 'LANG_EN'):
    arc = s2a.Archive(T.FILEMAP[tag])
    jb = s2a.Archive(T.BAKMAP['LANG_JA'])
    bad = []
    n_ok = 0
    for rec in range(N):
        ja_s = T.dec(core(jb, 666, POS, rec))
        exp = eq.get(ja_s)
        if not exp:
            continue
        got = dec_carrier(core(arc, 666, POS, rec))
        if got == exp:
            n_ok += 1
        else:
            bad.append((rec, got, exp))
    p('   %-8s 应译 %d ｜ 反解正确 %d ｜ 不符 %d' % (tag, n_ok + len(bad), n_ok, len(bad)))
    for x in bad[:8]:
        p('      rec%d 反解=%r 期望=%r' % x)

p('')
p('── ② 账本槽反解')
bs = [b for b in nmledger.batches() if b['id'] == BATCH]
arcs = {}
tot = bad2 = 0
for b in bs:
    for e in b['edits']:
        tot += 1
        if e['f'] not in arcs:
            arcs[e['f']] = s2a.Archive(T.FILEMAP[e['f']])
        blob = bytes(arcs[e['f']].blobs[e['b']])
        nb = bytes.fromhex(e['new'])
        if blob[e['off']:e['off'] + len(nb)] != nb:
            bad2 += 1
p('   批次 %s ｜ 槽 %d ｜ 与登记 new 不等 %d' % (BATCH, tot, bad2))

miss = [k for k, z in eq.items() if any(ord(c) >= 0x80 and c not in cmap and c not in native for c in z)]
p('')
p('── ③ 译名缺字：%d 条' % len(miss))

p('')
p('── ④ 源表"除登记写入范围外整条记录与写入前一致"')
edits = [e for b in bs for e in b['edits']]
cur = s2a.Archive(T.FILEMAP['LANG_JA'])
old = s2a.Archive(os.path.join(PREV, 'LANG_JA.s2a'))
covered = set()
for e in edits:
    if e['f'] != 'LANG_JA' or e['b'] != 666:
        continue
    base_e = 16 + ((e['off'] - 16) // STRIDE) * STRIDE
    span = max(len(bytes.fromhex(e['new'])), len(bytes.fromhex(e['old'])))
    for k in range(e['off'] - base_e, e['off'] - base_e + span):
        covered.add(k)
same = 0
for rec in range(N):
    base = 16 + rec * STRIDE
    okrec = True
    for off in range(STRIDE):
        if off in covered:
            continue
        if bytes(cur.blobs[666])[base + off] != bytes(old.blobs[666])[base + off]:
            okrec = False
            break
    if okrec:
        same += 1
p('   b666 未牵连记录：%d/%d ⇒ %s' % (same, N, '✅' if same == N else '⚠'))

p('')
p('── ⑤ ★ 键名列 b666/pos288~399 必须与日文原版逐字节一致（本次事故守卫）')
jab = s2a.Archive(T.BAKMAP['LANG_JA'])
badk = []
blen = len(bytes(cur.blobs[666]))
for rec in range(N):
    for off in range(KEYCOL[0], KEYCOL[1]):   # 288~375（376 起属于下一条记录）
        o = 16 + rec * STRIDE + off
        if o >= blen:
            break
        if bytes(cur.blobs[666])[o] != bytes(jab.blobs[666])[o]:
            badk.append((rec, off))
            break
p('   键名列仍与日文原版一致：%d/%d ⇒ %s' % (N - len(badk), N, '✅' if not badk else '⚠ %s' % badk[:6]))

p('')
p('── ⑥ cscv 技能表孪生名字字段')
cs = s2a.Archive(T.FILEMAP['cscv'])
nd = []
for rec in range(N):
    o = 16 + rec * STRIDE + POS
    a = bytes(cs.blobs[633])[o:o + 64].split(b'\x00')[0]
    b = bytes(jab.blobs[666])[o:o + 64].split(b'\x00')[0]
    if a != b:
        nd.append(rec)
p('   cscv b633 ≡ JA b666 ：%d/%d 日文原版 %s' % (N - len(nd), N, '✅' if not nd else 'ℹ'))

open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
print('\n'.join(out))
