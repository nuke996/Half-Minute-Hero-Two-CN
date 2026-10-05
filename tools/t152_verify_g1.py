# -*- coding: utf-8 -*-
"""t152_verify_g1.py —— G1 功能级验收（只读）
用**当前字库**（cscv）反解 live 文件里 G1 写过的槽，确认：
 ① 称号表 b931 的 252 条名称全是中文且 == 译名表；
 ② 全部 1460 槽反解 == 译名（含内嵌副本、引号装饰、章名/提示字段未受牵连）。
"""
import os, sys, json, collections
import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR; os.chdir(W); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a
import t140_name_revert as T
import nmledger

OUT = paths.build('t152_verify_g1.txt')
rows, _e, _t, _en, _tb, _s, _c, cmap, st = None, None, None, None, None, None, None, None, None
import build_cn as B
_r, _e, _t, _en, _tb, _s, _c, cmap, st = B.build_plan()
native = st['native_set']
rev = {}
for ch, by in cmap.items():
    rev.setdefault(by, ch)


def dec_carrier(b):
    o = []
    i = 0
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


def enc_ok(zh):
    """译名是否全部可用于字库（无 ? 风险）"""
    for ch in zh:
        if ord(ch) >= 0x80 and ch not in cmap and ch not in native:
            return False
    return True


out = []
def p(s=''):
    out.append(s)


bj = json.load(open(os.path.join(W, 't148_g1_titles.json'), encoding='utf-8'))
zh_map = {int(k): v for k, v in bj['titles'].items()}
for rec in range(bj['medal_from'], 252):
    zh_map[rec] = bj['medal_fmt'] % (rec - bj['medal_from'] + bj['medal_start'])

p('#' * 96)
p(' G1 功能级验收（用当前字库反解 live）')
p('#' * 96)

# ---- ① 称号表 b931 ----
for tag in ('LANG_JA', 'LANG_EN'):
    arc = s2a.Archive(T.FILEMAP[tag])
    bi = None
    for k, b in enumerate(arc.blobs):
        s_, n_ = T.hdr(bytes(b))
        if s_ == 292 and n_ == 252:
            bi = k; break
    bad = []
    for rec in range(252):
        raw = T.val_at(arc, bi, 0, rec)
        core = (raw or b'')[T.strip_lead(raw or b''):]
        got = dec_carrier(core)
        exp = zh_map.get(rec, '')
        if got != exp:
            bad.append((rec, got, exp))
    p('  %-8s b%d 称号表：252 条，反解不符 %d 条' % (tag, bi, len(bad)))
    for (rec, got, exp) in bad[:15]:
        p('      rec%-4d 反解=%-14r 期望=%-14r' % (rec, got, exp))

# ---- ② 账本全部槽反解 ----
bs = [b for b in nmledger.batches() if b['id'] == '称号名-G1']
edits = bs[0]['edits'] if bs else []
arcs = {}
bad2 = []
for e in edits:
    if e['f'] not in arcs:
        arcs[e['f']] = s2a.Archive(T.FILEMAP[e['f']])
    blob = bytes(arcs[e['f']].blobs[e['b']])
    v = blob[e['off']:e['off'] + len(bytes.fromhex(e['new']))]
    got = dec_carrier(v)
    exp = dec_carrier(bytes.fromhex(e['new']))
    if got != exp:
        bad2.append((e['f'], e['b'], e['off'], got, exp))
p('')
p('  账本槽反解：%d 槽，反解不符 %d' % (len(edits), len(bad2)))
for x in bad2[:10]:
    p('      ⚠ %s' % (x,))

# ---- ③ 缺字体检（所有译名） ----
miss = [ (r, zh) for r, zh in sorted(zh_map.items()) if not enc_ok(zh) ]
p('')
p('  译名缺字体检：%d 条有生僻字' % len(miss))
for (r, zh) in miss[:10]:
    p('      rec%-4d %r' % (r, zh))

# ---- ④ 章名/提示字段未被牵连（b931 pos32 / pos164 抽样） ----
arc = s2a.Archive(T.FILEMAP['LANG_EN'])
bak = s2a.Archive(T.BAKMAP['LANG_EN'])
bi = None
for k, b in enumerate(arc.blobs):
    s_, n_ = T.hdr(bytes(b))
    if s_ == 292 and n_ == 252:
        bi = k; break
same = 0
for rec in range(252):
    a = T.val_at(arc, bi, 32, rec)
    b = T.val_at(bak, bi, 32, rec)
    if a == b:
        same += 1
p('')
p('  b931 pos32(章名) 与写入前一致：%d/252  ⇒ %s' % (same, '✅ 未牵连' if same == 252 else '⚠ 有变化'))
open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
print('done')
