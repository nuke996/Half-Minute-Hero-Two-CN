# -*- coding: utf-8 -*-
"""t140_name_revert.py —— 名字类「全量回滚」总闸（账本制 / 幂等 / 零误伤）

用途
====
把 **我们名字批次（G1~G5 + 实验D/E）真正写过的槽**，一次性还原成原版字节，
回到"机制还能正常触发"的状态。

为什么不是"按字段整列还原"
==========================
因为主汉化本身就在部分字段翻过这些名字（`おじさま`→`老爷子`、`マオウメダル５１`→`魔王勋章51`、
`Geezer`→…）且游戏正常；按字段回滚会把它们退回日文 = 回归。
⇒ 只回滚 `_work/name_ledger.json` 里记过账的槽。**精确、幂等、零误伤。**

模式
====
  list                        列出账本里的批次（类 / 时间 / 槽数 / 备注）
  scan                        每个批次：当前是"已应用"还是"已还原"
  check                       全部已还原？(exit 0 / 1)
  revert [all|类|批次id]       按账本还原（先整文件备份到 _work/_pre_t140/<ts>/）
  adopt <id> <类> <blob,blob>  把"当前 vs 原版"在这些 blob 里的差异**登记**成批次
                              （用于把已应用的实验 D/E 补进账本）
  audit                       只读：字段级"名字槽"全景（含主汉化的改动，仅诊断用）
  snapshot                    把 LANG_JA/EN + cscv (+DLC01) 整文件快照到 _work/_name_good/<ts>/
  restore                     从最近一次 snapshot 整文件还原（兜底大招）

用法
====
  python _work/t140_name_revert.py list
  python _work/t140_name_revert.py scan
  python _work/t140_name_revert.py revert all
  python _work/t140_name_revert.py revert 称号名
  python _work/t140_name_revert.py check
"""
import os
import sys
import json
import shutil
import collections
import datetime

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
os.chdir(W)
sys.path.insert(0, W)
import s2a  # noqa: E402
import nmledger  # noqa: E402

RES = os.path.join(BASE, 'res')
DLC = os.path.join(BASE, 'DLC01')
OUT = paths.build('t140_name_revert.txt')
PRE = paths.build('_pre_t140')
SNAP = paths.build('_name_good')

FILEMAP = {
    'LANG_JA': os.path.join(RES, 'LANG_JA.s2a'),
    'LANG_EN': os.path.join(RES, 'LANG_EN.s2a'),
    'cscv': os.path.join(RES, 'cscv.s2a'),
    'DLC01_LANG_JA': os.path.join(DLC, 'LANG_JA.s2a'),
    'DLC01_LANG_EN': os.path.join(DLC, 'LANG_EN.s2a'),
}
BAKMAP = {
    'LANG_JA': os.path.join(RES, 'LANG_JA.s2a.bak'),
    'LANG_EN': os.path.join(RES, 'LANG_EN.s2a.bak'),
    'cscv': os.path.join(RES, 'cscv.s2a.bak'),
    'DLC01_LANG_JA': os.path.join(DLC, 'LANG_JA.s2a.bak_dlc01_20260913'),
    'DLC01_LANG_EN': os.path.join(DLC, 'LANG_EN.s2a.bak_dlc01_20260913'),
}
SNAP_FILES = ['LANG_JA', 'LANG_EN', 'cscv', 'DLC01_LANG_JA', 'DLC01_LANG_EN']

CATS = [
    ('技能名', [(376, 87, 0)]),
    ('装备名', [(268, 494, 4), (268, 614, 4), (268, 96, 4)]),
    ('伙伴名', [(236, 44, 4)]),
    ('称号名', [(292, 252, 0)]),
    ('职业名', [(212, 12, 4)]),
    ('阵形名', [(272, 11, 0)]),
]

L = []
EXACT_ONLY = '--derived' not in sys.argv


def p(x=''):
    L.append(str(x))


def flush():
    open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
    print('\n'.join(L))


# ------------------------------------------------------------------ 基础工具
def hdr(b):
    if bytes(b[:4]) == b'CSCV':
        return int.from_bytes(b[4:8], 'little'), int.from_bytes(b[8:12], 'little')
    return 0, 0


def runs(b):
    out = []
    n = len(b)
    i = 0
    while i < n:
        if b[i] == 0:
            i += 1
            continue
        j = i
        while j < n and b[j] != 0:
            j += 1
        out.append((i, j))
        i = j
    return out


def strip_lead(raw):
    """剥掉内嵌名字前的图标/控制符前缀。

    ★ 真实前缀 = **单个 0xFF 重复 4 次**（cp932 把 0xFF 解成 U+F8F3），不是 `F8 F3` 对；
      早期脚本按 `F8 F3` 剥 ⇒ 所有内嵌副本漏检。
    """
    k = 0
    while k < len(raw) and raw[k] == 0xFF:
        k += 1
    while k + 1 < len(raw) and raw[k] == 0xF8 and raw[k + 1] == 0xF3:
        k += 2
    return k


def dec(raw):
    try:
        return raw.decode('cp932')
    except Exception:
        return raw.decode('cp932', 'replace')


def textlike(core):
    # ★ 不能要求偶数字节：英文名字常为奇数字节（`Brave Break` = 11B）
    if len(core) < 2 or len(core) > 80:
        return False
    try:
        s = core.decode('cp932')
    except Exception:
        return False
    for ch in s:
        if ord(ch) < 0x20 and ch != '\n':
            return False
    return any(ord(c) >= 0x80 or c.isalnum() for c in s)


def valid_name(core):
    if not textlike(core):
        return False
    s = dec(core)
    return not ('<' in s or '>' in s) and len(core) >= 4


def slot_run(b, base, pos, rec_end):
    q = base + pos
    if q >= len(b):
        return None
    if b[q] == 0:
        return (q, q)
    s0 = q
    while s0 > base and b[s0 - 1] != 0:
        s0 -= 1
    e0 = q
    while e0 < rec_end and e0 < len(b) and b[e0] != 0:
        e0 += 1
    return (s0, e0)


def build_idx(arc):
    idx = collections.defaultdict(list)
    meta = []
    for bi, blob in enumerate(arc.blobs):
        b = bytes(blob)
        st, n = hdr(b)
        meta.append((st, n))
        for (s, e) in runs(b):
            raw = b[s:e]
            core = raw[strip_lead(raw):]
            if not textlike(core):
                continue
            if st and s >= 16:
                rec, pos = (s - 16) // st, (s - 16) % st
            elif st:
                # ★ CSCV 头第 12~15 字节 = FF FF FF FF，会与 **record0 的首字段**
                #   连成一条 run（起点=12<16）⇒ 旧算法得 rec = -4//st = -1 被丢弃。
                #   该 run 只可能属于 record0，且 strip_lead 正好剥掉这 4 个 0xFF，
                #   core 与 record0/pos0 的值完全相同 ⇒ 安全归入 (0, 0)。
                rec, pos = 0, 0
            else:
                rec, pos = -1, -1
            idx[core].append((bi, s, strip_lead(raw) // 2, rec, pos))
    pref = collections.defaultdict(set)
    for core in idx:
        if len(core) >= 6:
            pref[core[:6]].add(core)
    return idx, pref, meta


def find_hits(idx, pref, name):
    hits = []
    for (bi, s, lead, rec, pos) in idx.get(name, []):
        hits.append((bi, s, lead, rec, pos, 'EXACT', ''))
    if len(name) >= 6:
        for core in pref.get(name[:6], ()):
            if len(core) <= len(name) or not core.startswith(name):
                continue
            suf = core[len(name):]
            ss = dec(suf)
            if ss is None or len(ss) > 8 or not ss.isprintable():
                continue
            if ss[0].isdigit() or '０' <= ss[0] <= '９':
                continue
            for (bi, s, lead, rec, pos) in idx.get(core, []):
                hits.append((bi, s, lead, rec, pos, 'DERIVED', ss))
    return hits


def val_at(arc, bi, pos, rec):
    b = bytes(arc.blobs[bi])
    st, n = hdr(b)
    if not st or rec >= n:
        return None
    base = 16 + rec * st
    q = base + pos
    if q >= len(b):
        return None
    s0 = q
    while s0 > base and b[s0 - 1] != 0:
        s0 -= 1
    e0 = q
    while e0 < len(b) and b[e0] != 0:
        e0 += 1
    return bytes(b[s0:e0])


def class_names(arc, meta, srcs):
    out = set()
    for (st, n, pos) in srcs:
        for bi, (mst, mn) in enumerate(meta):
            if mst != st or mn != n:
                continue
            b = bytes(arc.blobs[bi])
            for rec in range(n):
                base = 16 + rec * st
                q = base + pos
                if q >= len(b):
                    continue
                s0 = q
                while s0 > base and b[s0 - 1] != 0:
                    s0 -= 1
                e0 = q
                while e0 < len(b) and b[e0] != 0:
                    e0 += 1
                raw = bytes(b[s0:e0])
                core = raw[strip_lead(raw):]
                if valid_name(core):
                    out.add(core)
    return out


# ------------------------------------------------------------------ 账本操作
def do_list():
    bs = nmledger.batches()
    p('#' * 96)
    p(' 名字类翻译账本（_work/name_ledger.json）')
    p('#' * 96)
    if not bs:
        p('  （空）尚无批次。可用 adopt 把已应用的改动登记进来。')
    p('  %-22s %-8s %-16s %-7s %s' % ('批次id', '类', '时间', '槽数', '备注'))
    for b in bs:
        p('  %-22s %-8s %-16s %-7d %s'
          % (b['id'], b['class'], b.get('ts', ''), len(b['edits']), b.get('note', '')))
    tot = sum(len(b['edits']) for b in bs)
    p('')
    p('  合计批次 %d ｜ 合计槽 %d' % (len(bs), tot))


def do_scan(sel='all'):
    allb = nmledger.batches()
    bs = [b for b in allb
          if sel == 'all' or sel == b['class'] or sel == b['id']]
    # 「被后续批次覆盖」判定：同槽若等于**更靠后批次**的 new，就是被后续批次改过（不是异常）
    later_new = {}
    for idx, b in enumerate(allb):
        for e in b['edits']:
            later_new.setdefault((e['f'], e['b'], e['off'], idx), set()).add(e['new'])
    arcs = {}
    p('#' * 96)
    p(' 名字类账本状态（scan 只读）')
    p('#' * 96)
    p('  %-24s %-10s %-8s %-8s %-8s %s' % ('批次id', '类', '槽数', '已应用', '已还原', '其它'))
    for b in bs:
        n_app = n_rev = n_unk = n_sup = 0
        for e in b['edits']:
            if e['f'] not in arcs:
                arcs[e['f']] = s2a.Archive(FILEMAP[e['f']])
            blob = bytes(arcs[e['f']].blobs[e['b']])
            off = e['off']
            new = bytes.fromhex(e['new'])
            old = bytes.fromhex(e['old'])
            seg = blob[off:off + max(len(new), len(old))]
            if seg[:len(new)] == new:
                n_app += 1
            elif seg[:len(old)] == old:
                n_rev += 1
            else:
                # 是否被更靠后的批次覆盖
                sup = False
                for (f2, b2, o2, idx2), news in later_new.items():
                    if f2 == e['f'] and b2 == e['b'] and o2 == e['off']:
                        for hx in news:
                            nb = bytes.fromhex(hx)
                            if nb and seg[:len(nb)] == nb:
                                sup = True
                if sup:
                    n_sup += 1
                else:
                    n_unk += 1
        note = ''
        if n_sup:
            note += ' 已被后续批次覆盖 %d（正常，反序回滚可还原）' % n_sup
        if n_unk:
            note += ' ⚠未识别 %d' % n_unk
        p('  %-24s %-10s %-8d %-8d %-8d%s'
          % (b['id'], b['class'], len(b['edits']), n_app, n_rev, note))
    p('')
    p('  ★ 全量回滚请用 `revert all`（工具已按**批次反序**执行）。')
    p('')


def do_check(sel='all'):
    bs = [b for b in nmledger.batches()
          if sel == 'all' or sel == b['class'] or sel == b['id']]
    arcs = {}
    bad = 0
    for b in bs:
        for e in b['edits']:
            if e['f'] not in arcs:
                arcs[e['f']] = s2a.Archive(FILEMAP[e['f']])
            blob = bytes(arcs[e['f']].blobs[e['b']])
            off = e['off']
            old = bytes.fromhex(e['old'])
            new = bytes.fromhex(e['new'])
            seg = blob[off:off + max(len(old), len(new))]
            if seg[:len(old)] != old:
                bad += 1
    p('check：账本共 %d 批次；非原版槽 = %d' % (len(bs), bad))
    p('→ %s' % ('✅ 全绿：所有名字批次均已还原' if bad == 0 else '⚠ 仍有 %d 槽是"已应用"状态' % bad))
    return bad


def do_revert(sel='all'):
    bs = [b for b in nmledger.batches()
          if sel == 'all' or sel == b['class'] or sel == b['id']]
    if not bs:
        p('账本为空，无需回滚。')
        return
    # ★ 必须**按批次反序**回滚（最后写的先退）：
    #   同一槽若被多个批次写过（如 パンイチ 先被 G1 写成"一条内裤"、又被改名批次写成"只穿内裤"），
    #   正序回滚会让先退的批次"冲突跳过"，留下中间态；反序才能干净回到原文。
    bs = bs[::-1]
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(PRE, ts)
    os.makedirs(dst, exist_ok=True)
    p('#' * 96)
    p(' 名字类回滚 · 执行（备份 -> %s）' % dst)
    p('#' * 96)
    arcs = {}
    for tag in sorted({e['f'] for b in bs for e in b['edits']}):
        if os.path.exists(FILEMAP[tag]):
            shutil.copy2(FILEMAP[tag], os.path.join(dst, os.path.basename(FILEMAP[tag])))
            p('  [备份] %s' % os.path.basename(FILEMAP[tag]))
            arcs[tag] = s2a.Archive(FILEMAP[tag])
    for b in bs:
        n_ok = n_skip = n_bad = 0
        touched = set()
        for e in b['edits']:
            tag = e['f']
            arc = arcs.get(tag)
            if arc is None:
                continue
            blob = bytearray(bytes(arc.blobs[e['b']]))
            off = e['off']
            old = bytes.fromhex(e['old'])
            new = bytes.fromhex(e['new'])
            span = max(len(old), len(new))
            seg = bytes(blob[off:off + span])
            if seg[:len(new)] == new:                 # 已应用 -> 还原
                blob[off:off + span] = old + b'\x00' * (span - len(old))
                arc.blobs[e['b']] = bytes(blob)
                n_ok += 1
                touched.add(e['b'])
            elif seg[:len(old)] == old:               # 已是原版
                n_skip += 1
            else:
                n_bad += 1
        p('  [%s] 还原 %d ｜ 已是原版 %d%s'
          % (b['id'], n_ok, n_skip, ('  ⚠冲突 %d' % n_bad) if n_bad else ''))
    for tag, arc in arcs.items():
        s2a.pack(FILEMAP[tag], arc.entries, arc.blobs)
        p('  [写回] %s' % os.path.basename(FILEMAP[tag]))
    p('')
    p('  完成。跑 `check` 复核。')


def do_adopt(batch_id, klass, fieldspec):
    """fieldspec: `blob:pos,blob:pos,...`（**按精确字段**，不要按整个 blob，
    否则会把主汉化在别处的改动也登记进来）"""
    fields = []
    for tok in fieldspec.replace(' ', '').split(','):
        if not tok:
            continue
        b, q = tok.split(':')
        fields.append((int(b), int(q)))
    edits = []
    for tag in ('LANG_JA', 'LANG_EN'):
        live = s2a.Archive(FILEMAP[tag])
        bak = s2a.Archive(BAKMAP[tag])
        for (bi, pos) in fields:
            if bi >= len(live.blobs) or bi >= len(bak.blobs):
                continue
            a = bytes(live.blobs[bi])
            b = bytes(bak.blobs[bi])
            st, n = hdr(b)
            if not st:
                continue
            for rec in range(n):
                base = 16 + rec * st
                rec_end = min(16 + (rec + 1) * st, len(b))
                brun = slot_run(b, base, pos, rec_end)
                lrun = slot_run(a, base, pos, rec_end)
                if brun is None or lrun is None:
                    continue
                old = b[brun[0]:brun[1]]
                new = a[lrun[0]:lrun[1]]
                if old == new or not old:
                    continue
                edits.append({'f': tag, 'b': bi, 'off': brun[0],
                              'old': old.hex(), 'new': new.hex()})
    k = nmledger.record(batch_id, klass, edits, note='adopt fields=%s' % fieldspec)
    p('已登记批次 %r（类 %s）：%d 条 edit（字段 %s）' % (batch_id, klass, k, fieldspec))


def do_audit():
    """字段级名字槽全景（含主汉化改动）——仅诊断，勿用于回滚"""
    arcs, baks, metas, idxs, prefs = {}, {}, {}, {}, {}
    for tag in ('LANG_JA', 'LANG_EN'):
        arcs[tag] = s2a.Archive(FILEMAP[tag])
        baks[tag] = s2a.Archive(BAKMAP[tag])
        idxs[tag], prefs[tag], metas[tag] = build_idx(baks[tag])
    p('#' * 96)
    p(' audit：字段级"名字槽"（EXACT=%s）——含主汉化改动，仅供诊断' % (not EXACT_ONLY or True))
    p('#' * 96)
    p('  %-8s %-8s %-8s %-8s' % ('类', '文件', '槽数', '≠原版'))
    for cat, srcs in CATS:
        for tag in ('LANG_JA', 'LANG_EN'):
            ref = 'LANG_EN' if tag == 'LANG_JA' else 'LANG_JA'
            names = class_names(baks[tag], metas[tag], srcs)
            got = set()
            for nm in names:
                for (bi, s, lead, rec, pos, form, suf) in find_hits(idxs[tag], prefs[tag], nm):
                    if EXACT_ONLY and form != 'EXACT':
                        continue
                    if rec < 0 or bi >= len(baks[tag].blobs) or bi >= len(baks[ref].blobs):
                        continue
                    if metas[tag][bi] != metas[ref][bi]:
                        continue
                    v = val_at(baks[tag], bi, pos, rec)
                    rv = val_at(baks[ref], bi, pos, rec)
                    if v is None or rv is None or v == rv:
                        continue
                    got.add((bi, rec, pos))
            nd = 0
            for (bi, rec, pos) in got:
                st, n = metas[tag][bi]
                base = 16 + rec * st
                rec_end = min(16 + (rec + 1) * st, len(bytes(arcs[tag].blobs[bi])))
                a = slot_run(bytes(arcs[tag].blobs[bi]), base, pos, rec_end)
                b = slot_run(bytes(baks[tag].blobs[bi]), base, pos, rec_end)
                if a and b and bytes(arcs[tag].blobs[bi])[a[0]:a[1]] != bytes(baks[tag].blobs[bi])[b[0]:b[1]]:
                    nd += 1
            p('  %-8s %-8s %-8d %-8d' % (cat, tag, len(got), nd))
    p('')


def do_snapshot():
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(SNAP, ts)
    os.makedirs(dst, exist_ok=True)
    for tag in SNAP_FILES:
        if os.path.exists(FILEMAP[tag]):
            shutil.copy2(FILEMAP[tag], os.path.join(dst, tag + '.s2a'))
            p('  [快照] %s' % tag)
    p('快照目录：%s' % dst)
    return dst


def do_restore():
    if not os.path.isdir(SNAP):
        p('没有快照目录。')
        return
    cands = sorted(os.listdir(SNAP))
    if not cands:
        p('快照目录为空。')
        return
    src = os.path.join(SNAP, cands[-1])
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bk = os.path.join(PRE, 'restore_' + ts)
    os.makedirs(bk, exist_ok=True)
    p('从快照还原：%s' % src)
    for tag in SNAP_FILES:
        f = os.path.join(src, tag + '.s2a')
        if os.path.exists(f) and os.path.exists(FILEMAP[tag]):
            shutil.copy2(FILEMAP[tag], os.path.join(bk, os.path.basename(FILEMAP[tag])))
            shutil.copy2(f, FILEMAP[tag])
            p('  [还原] %s' % tag)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'list'
    arg = sys.argv[2] if len(sys.argv) > 2 else 'all'
    if mode == 'list':
        do_list()
    elif mode == 'scan':
        do_scan(arg)
    elif mode == 'check':
        n = do_check(arg)
        flush()
        sys.exit(0 if n == 0 else 1)
    elif mode == 'revert':
        do_revert(arg)
    elif mode == 'adopt':
        do_adopt(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == 'audit':
        do_audit()
    elif mode == 'snapshot':
        do_snapshot()
    elif mode == 'restore':
        do_restore()
    else:
        p('未知模式：%s' % mode)
    flush()


if __name__ == '__main__':
    main()
