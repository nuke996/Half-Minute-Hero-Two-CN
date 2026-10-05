# -*- coding: utf-8 -*-
"""t175_g3_apply.py —— G3 装备名 通用写入口（t153 同款流水线 + cscv 硬闸 / 双文件）

用法
====
  python _work/t175_g3_apply.py check       # 只读：槽数/容量/缺字/实况 + cscv 闸
  python _work/t175_g3_apply.py apply       # 写入（备份 -> 账本 装备名-G3）

译名来源：_work/t172_g3_eq.json（ja 原串 -> 中文）
  由 t171（已装机批次一致性映射）+ t156（主汉化既有用词）+ t174（人工补漏）产出。

铁律遵循
  · 44：同一语言文件内**每一份副本同改**（EXACT 命中全库，含内嵌 0xFF×4 前缀副本）；
        漏副本 => 断链。
  · 45：只改"官方 EN 也改过"的字段（v != rv）；逐字节记账且 old = **写入前实况**值；
        写前整文件备份；写后跑 t162 零附带变化证书。
  · 46：CSCV 头 12~15 字节 FF FF FF FF 会与 record0 首字段连成 run（t140.build_idx 已修）。
  · 47：**只写 LANG，绝不写 cscv**。cscv 里的孪生装备表
        （b144≡JA b147 / b338≡JA b357 / b705≡JA b736 / b975≡JA b998）**一字不动**，
        写前/写后断言 cscv md5 不变（脚本层按 CP932 原码比名，写载体码 => 断链）。
"""
import os
import sys
import json
import hashlib
import shutil
import collections
import datetime

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
os.chdir(W)
sys.path.insert(0, W)
import s2a                      # noqa: E402
import t140_name_revert as T    # noqa: E402
import nmledger                 # noqa: E402
import build_cn as B            # noqa: E402

OUT = paths.build('t175_g3.txt')
PRE = paths.build('_pre_t175')
TSV = paths.build('t175_g3_slots.tsv')
EQ = os.path.join(W, 't172_g3_eq.json')

CAT = '装备名'
BATCH = '装备名-G3'
LABEL = 'G3 装备名'
STRIDE = 268
POS = 4
SRC = [(147, 494), (357, 614), (736, 614), (998, 96)]   # stride268 名字表（JA/EN 同构）
# ★ 排除某些"键名槽"：[(blob, 偏移下限, 偏移上限)] —— 命中即**不写**（铁律 49：键名绝不能改）
#   G5 事故：`b666/pos292` = 技能的**内部键名**（脚本按名比对），改了 ⇒ 主角技能全放不出来。
EXCLUDE_POS = []
# ★ 本文件已"参数化"：新批次用薄包装脚本覆盖 CAT/BATCH/LABEL/STRIDE/POS/SRC/EQ/OUT/PRE/TSV
#   /EXCLUDE_POS 再调用 main() 即可（见 t190_g5_apply.py）。

L = []
def p(x=''):
    L.append(str(x))

def flush():
    open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
    print('\n'.join(L))


def get_cmap():
    rows_, ents_, types_, end_, tb_, slots_, chosen_, cmap_, st_ = B.build_plan()
    return cmap_, st_['native_set']


def load_zh():
    d = json.load(open(EQ, encoding='utf-8'))
    return {k: v for k, v in d.items() if v}


def core_of(arc, bi, pos, rec):
    raw = T.val_at(arc, bi, pos, rec)
    return (raw or b'')[T.strip_lead(raw or b''):]


def build_plan(cmap, native):
    zh_map = load_zh()
    liv, bak = {}, {}
    for tag in ('LANG_JA', 'LANG_EN'):
        liv[tag] = s2a.Archive(T.FILEMAP[tag])
        bak[tag] = s2a.Archive(T.BAKMAP[tag])

    idxs, prefs, metas = {}, {}, {}
    for tag in ('LANG_JA', 'LANG_EN'):
        idxs[tag], prefs[tag], metas[tag] = T.build_idx(bak[tag])

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

    miss = collections.Counter()
    for ja_s, zh in zh_map.items():
        for c in zh:
            if ord(c) >= 0x80 and c not in cmap and c not in native:
                miss[c] += 1

    # 源表逐 (blob, rec)：JA 名 / EN 名 / 译名
    src_items = []
    for (bi, n) in SRC:
        if T.hdr(bytes(bak['LANG_JA'].blobs[bi])) != T.hdr(bytes(bak['LANG_EN'].blobs[bi])):
            p('  ⚠ b%d 在 JA/EN 里结构不一致，跳过' % bi)
            continue
        for rec in range(n):
            ja_b = core_of(bak['LANG_JA'], bi, POS, rec)
            en_b = core_of(bak['LANG_EN'], bi, POS, rec)
            if not ja_b:
                continue
            ja_s = T.dec(ja_b)
            zh = zh_map.get(ja_s)
            if not zh:
                continue
            src_items.append((bi, rec, ja_b, en_b, ja_s, zh))

    slots = {}
    clash = []
    unknown = collections.Counter()
    fallback = 0
    excluded = collections.Counter()
    for (bi, rec, ja_b, en_b, ja_s, zh) in src_items:
        for tag in ('LANG_JA', 'LANG_EN'):
            ref = 'LANG_EN' if tag == 'LANG_JA' else 'LANG_JA'
            nm = ja_b if tag == 'LANG_JA' else en_b
            if not nm:
                continue
            hits = T.find_hits(idxs[tag], prefs[tag], nm)
            n_raw = sum(1 for h in hits if h[5] == 'EXACT' and h[3] >= 0)
            if n_raw == 0:
                unknown['%s:%s' % (tag, ja_s if tag == 'LANG_JA' else T.dec(en_b))] += 1
            for (bi2, s, lead, rec2, pos, form, suf) in hits:
                if form != 'EXACT' or rec2 < 0:
                    continue
                if metas[tag][bi2] != metas[ref][bi2]:
                    continue
                v = T.val_at(bak[tag], bi2, pos, rec2)
                rv = T.val_at(bak[ref], bi2, pos, rec2)
                if v is None or rv is None or v == rv:
                    continue
                # ★ EN 侧：同位置（bi2,rec2,pos）在 JA 里的名字才是"这条记录的真正身份"
                #   （EN 里同一英文串会在不同表里指代不同名字：Warrior = ウォーリア / せんし）
                zh_use = zh
                if tag == 'LANG_EN':
                    jv = T.val_at(bak['LANG_JA'], bi2, pos, rec2)
                    if jv:
                        jcore = jv[T.strip_lead(jv):]
                        z2 = zh_map.get(T.dec(jcore))
                        if z2:
                            zh_use = z2
                        else:
                            fallback += 1
                enc = B.encode_text(zh_use, cmap, native)
                st, n = metas[tag][bi2]
                base = 16 + rec2 * st
                rec_end = min(16 + (rec2 + 1) * st, len(bytes(bak[tag].blobs[bi2])))
                brun = T.slot_run(bytes(bak[tag].blobs[bi2]), base, pos, rec_end)
                if brun is None:
                    continue
                bs, be = brun
                fpos0 = bs - base                       # 该槽所在"列"的偏移（键名排查用）
                if any(bi2 == eb and lo <= fpos0 < hi for (eb, lo, hi) in EXCLUDE_POS):
                    excluded[(bi2, pos, fpos0)] += 1
                    continue
                old = bytes(bak[tag].blobs[bi2])[bs:be]
                pre = old[:T.strip_lead(old)]
                lb = bytes(liv[tag].blobs[bi2])
                lrun = T.slot_run(lb, base, pos, rec_end)
                lcur = lb[lrun[0]:lrun[1]] if lrun else b''
                lcore = lcur[T.strip_lead(lcur):]
                ocore = old[T.strip_lead(old):]
                lead_q = (ocore[:2] == b'\x81u' or lcore[:2] == b'\x81u') and not zh_use.startswith('「')
                trail_q = (ocore[-2:] == b'\x81v' or lcore[-2:] == b'\x81v') and not zh_use.endswith('」')
                new = pre + (b'\x81u' if lead_q else b'') + enc + (b'\x81v' if trail_q else b'')
                k = be
                lim = bytes(bak[tag].blobs[bi2])
                while k < rec_end and lim[k] == 0:
                    k += 1
                cap = k - bs
                key = (tag, bi2, rec2, pos)
                if key in slots:
                    if slots[key]['new'] != new:
                        clash.append((key, slots[key]['zh'], zh_use, slots[key]['ja_s'], ja_s))
                    continue
                if lcur == old:
                    state = 'clean'
                elif lcur == new:
                    state = 'already'
                else:
                    state = 'clobber'
                slots[key] = {'old': old, 'new': new, 'cap': cap, 'bs': bs, 'pre': lcur,
                              'zh': zh_use, 'ja_old': T.dec(old), 'ja_s': ja_s, 'state': state,
                              'src': '%d/%d' % (bi, rec), 'lcur_zh': dec_carrier(lcore)}
    return liv, bak, slots, miss, unknown, zh_map, clash, fallback, excluded


def cscv_twins():
    """cscv 里与装备名表同构的孪生 blob（按 (stride,n) 配对，取差异最小者）"""
    cs = s2a.Archive(T.FILEMAP['cscv'])
    ja = s2a.Archive(T.BAKMAP['LANG_JA'])
    pairs = []
    for cb, blob in enumerate(cs.blobs):
        cst, cn = T.hdr(bytes(blob))
        if cst != STRIDE:
            continue
        best = None
        for (bi, n) in SRC:
            if n != cn or bi >= len(ja.blobs):
                continue
            nd = 0
            for rec in range(n):
                o = 16 + rec * cst + POS
                a = bytes(cs.blobs[cb])[o:o + 64].split(b'\x00')[0]
                b = bytes(ja.blobs[bi])[o:o + 64].split(b'\x00')[0]
                if a != b:
                    nd += 1
            if best is None or nd < best[1]:
                best = (bi, nd, n)
        if best:
            pairs.append((cb, best[0], best[1], best[2]))
    return pairs


def cscv_gate(stage):
    bad = []
    pairs = cscv_twins()
    if not pairs:
        p('  [cscv闸/%s] （cscv 里没有与装备名表同构的 blob）✅' % stage)
    for (cb, jb, nd, n) in pairs:
        if nd:
            bad.append('cscv b%d ≡ JA b%d：名字字段有 %d/%d 与**日文原版**不同（历史遗留，非本批所致）'
                       % (cb, jb, nd, n))
        else:
            p('  [cscv闸/%s] cscv b%-4d ≡ LANG_JA b%-4d (stride%d n%-4d) 名字字段 %d/%d 日文原版 ✅'
              % (stage, cb, jb, STRIDE, n, n, n))
    for b in bad:
        p('  [cscv闸/%s] ℹ %s' % (stage, b))
    return bad


def cscv_md5():
    cs = s2a.Archive(T.FILEMAP['cscv'])
    return hashlib.md5(b''.join(bytes(x) for x in cs.blobs)).hexdigest()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    force = '--skip-clobber' not in sys.argv
    cmap, native = get_cmap()

    p('#' * 100)
    p(' %s · %s ｜ stride=%d pos=%d ｜ cscv 绝不写入' % (LABEL, mode, STRIDE, POS))
    p('#' * 100)
    p('')
    cscv_before = cscv_md5()
    p('  cscv.s2a md5(blobs 拼接，写前) = %s' % cscv_before[:12])
    cscv_gate('写前')

    liv, bak, slots, miss, unknown, zh_map, clash, fallback, excluded = build_plan(cmap, native)
    p('')
    p('=' * 100)
    p(' 译名表 %d 条 ｜ 命中槽 %d ｜ 缺字 %d 种 ｜ 同名冲突 %d ｜ EN 侧退回按名取值 %d'
      % (len(zh_map), len(slots), len(miss), len(clash), fallback))
    p('=' * 100)
    if EXCLUDE_POS:
        p('  ★ 排除的键名槽（铁律 49，绝不写）：%d 个' % sum(excluded.values()))
        for (b, pos, fpos), c in excluded.most_common(10):
            p('      b%-5d 命中pos%-4d 所在列off%-5d x%d' % (b, pos, fpos, c))
    per_tag = collections.Counter(t for (t, b, r, q) in slots)
    p('  按文件：%s' % dict(per_tag))
    st_cnt = collections.Counter(v['state'] for v in slots.values())
    p('  实况：原版未动 %d ｜ 已是本批译文 %d ｜ 主汉化另有措辞 %d'
      % (st_cnt['clean'], st_cnt['already'], st_cnt['clobber']))
    p('  实际将写入：%d 槽' % (len(slots) - st_cnt['already'] - st_cnt['clobber']))
    p('')
    p('  ── 抽样核对（各状态前 12 条）')
    for want in ('clean', 'already', 'clobber'):
        got = [(k, v) for k, v in sorted(slots.items()) if v['state'] == want][:12]
        if not got:
            continue
        p('   [%s] %d 条，样例：' % (want, st_cnt[want]))
        for (k, v) in got:
            p('      %-8s b%-4d rec%-4d pos%-4d 原版=%-14r 现况=%-14r 本批=%r'
              % (k[0], k[1], k[2], k[3], v['ja_old'], v['lcur_zh'], v['zh']))
    p('')
    overflow = [(k, v) for k, v in slots.items() if len(v['new']) > v['cap']]
    p('  容量超限：%d' % len(overflow))
    for (k, v) in overflow[:20]:
        p('      %s b%d rec%d pos%d 需 %d > 容 %d (%r -> %r) src=%s'
          % (k[0], k[1], k[2], k[3], len(v['new']), v['cap'], v['ja_old'], v['zh'], v['src']))
    if miss:
        p('  缺字：%s' % dict(miss))
    if clash:
        p('  ⚠ 同一槽被两条源记录要求不同译名 %d 例：' % len(clash))
        for (k, z1, z2, j1, j2) in clash[:20]:
            p('      %s  %r -> %r  与  %r -> %r' % (k, j1, z1, j2, z2))
    cl = [(k, v) for k, v in sorted(slots.items()) if v['state'] == 'clobber']
    if cl:
        p('  ★ 主汉化另有措辞的槽（%d 个，将统一为本批译文）：' % len(cl))
        for (k, v) in cl[:30]:
            p('      %s b%-5d rec%-5d pos%-4d 主汉化=%r  原版=%r  -> 本批=%r'
              % (k[0], k[1], k[2], k[3], v['lcur_zh'], v['ja_old'], v['zh']))
    if unknown:
        p('  ℹ 源表名字在这些 (文件,名) 上"零 EXACT 副本"（占位/未使用条目）：')
        for k, c in list(unknown.items())[:40]:
            p('      %s' % k)
    blobset = collections.Counter('%s:b%d' % (t, b) for (t, b, r, q) in slots)
    p('  涉及 blob 数：%d（top 15）' % len(blobset))
    for kb, nb in blobset.most_common(15):
        p('      %-16s %d' % (kb, nb))

    tsv_rows = ['\t'.join(['tag', 'blob', 'rec', 'pos', 'off', 'cap', 'state', '原版', '本批', '现况反解', 'src'])]
    for (tag, b, rec2, pos), v in sorted(slots.items()):
        tsv_rows.append('\t'.join([tag, str(b), str(rec2), str(pos), str(v['bs']), str(v['cap']),
                                   v['state'], v['ja_old'], v['zh'], v['lcur_zh'], v['src']]))
    open(TSV, 'w', encoding='utf-8').write('\n'.join(tsv_rows))

    if mode == 'apply':
        if overflow:
            p('  ⚠ 有容量超限，中止。')
            flush()
            return
        if miss:
            p('  ⚠ 有缺字，中止。')
            flush()
            return
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dst = os.path.join(PRE, ts)
        os.makedirs(dst, exist_ok=True)
        for tag in ('LANG_JA', 'LANG_EN', 'cscv', 'DLC01_LANG_JA', 'DLC01_LANG_EN'):
            if os.path.exists(T.FILEMAP[tag]):
                shutil.copy2(T.FILEMAP[tag], os.path.join(dst, tag + '.s2a'))
        p('  [备份] LANG_JA/LANG_EN/cscv/DLC01 -> %s' % dst)
        edits = []
        n_skip = n_conf = n_mis = 0
        arcs = {'LANG_JA': liv['LANG_JA'], 'LANG_EN': liv['LANG_EN']}
        for (tag, bi2, rec2, pos), v in sorted(slots.items()):
            if v['state'] == 'already':
                n_skip += 1
                continue
            if v['state'] == 'clobber' and not force:
                n_conf += 1
                continue
            arc = arcs[tag]
            blob = bytearray(bytes(arc.blobs[bi2]))
            st, n = T.hdr(bytes(blob))
            base = 16 + rec2 * st
            rec_end = min(16 + (rec2 + 1) * st, len(blob))
            lrun = T.slot_run(bytes(arc.blobs[bi2]), base, pos, rec_end)
            if lrun is None or lrun[0] != v['bs']:
                n_mis += 1
                continue
            bs = v['bs']
            old = v['pre'] if v['state'] == 'clobber' else v['old']
            new = v['new']
            span = max(len(old), len(new))
            blob[bs:bs + span] = new + b'\x00' * (span - len(new))
            arc.blobs[bi2] = bytes(blob)
            edits.append({'f': tag, 'b': bi2, 'off': bs, 'old': old.hex(), 'new': new.hex()})
        for tag in ('LANG_JA', 'LANG_EN'):
            s2a.pack(T.FILEMAP[tag], arcs[tag].entries, arcs[tag].blobs)
        k = nmledger.record(BATCH, CAT, edits, note='%s 全副本同改（cscv 未动）' % LABEL)
        p('  [写入] %d 槽（跳过已是本批 %d ｜ 未覆盖 %d ｜ 漂移 %d）-> 账本批次 %r'
          % (k, n_skip, n_conf, n_mis, BATCH))
        p('')
        cscv_after = cscv_md5()
        p('  cscv.s2a md5(blobs 拼接，写后) = %s' % cscv_after[:12])
        p('  ★ cscv 是否被改：%s' % ('未动 ✅' if cscv_after == cscv_before else '被改了 ⚠⚠'))
        cscv_gate('写后')
        p('')
        p('  回滚：汉化-名字类回滚.bat（或 python _work/t140_name_revert.py revert 装备名）')
    flush()


if __name__ == '__main__':
    main()
