# -*- coding: utf-8 -*-
"""t153_name_apply.py —— 名字批次通用工具（G2：伙伴名 / 职业名 / 阵形名）

与 G1（t148）同款流水线，额外加两道 **cscv 硬闸**：
  ① 只打开 `res/LANG_JA.s2a` / `res/LANG_EN.s2a`，**永不打开 cscv 写**；
  ② apply 前后断言 `res/cscv.s2a` 的 md5 不变；并断言三张名字表的
     **cscv 脚本层孪生 blob（伙伴 917 / 职业 124 / 阵形 132）仍是日文原版**。

★ 为什么必须这样（v2.28「同伴技能键表」事故）
  主汉化的整表管线会把 **cscv 里的脚本层孪生副本**（与 LANG_JA 逐字节相同）
  一起写成**载体码**；脚本层按 CP932 原码比名 ⇒ 比不中 ⇒ **伙伴不能攻击/用技能**。
  本工具不碰 cscv ⇒ 脚本层按名比对永远成立。

用法
====
  python _work/t153_name_apply.py check [类]      # 只读：槽数/容量/缺字/实况
  python _work/t153_name_apply.py apply [类]      # 写入（可加 --skip-clobber）
  类 ∈ 伙伴名 | 职业名 | 阵形名 ；缺省 = 三个都做
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
import s2a            # noqa: E402
import t140_name_revert as T   # noqa: E402
import nmledger       # noqa: E402
import build_cn as B  # noqa: E402

OUT = paths.build('t153_g2.txt')
PRE = paths.build('_pre_t153')
TSV = paths.build('t153_g2_slots.tsv')
# cscv 脚本层孪生：(类 -> cscv_blob)
CSCV_TWIN = {'伙伴名': 917, '职业名': 124, '阵形名': 132}

SPECS = [
    dict(cat='阵形名', stride=272, n=11, pos=0, batch='阵形名-G2', json='t157_g2_formation.json'),
    dict(cat='职业名', stride=212, n=12, pos=4, batch='职业名-G2', json='t157_g2_job.json'),
    dict(cat='伙伴名', stride=236, n=44, pos=4, batch='伙伴名-G2', json='t157_g2_partner.json'),
]

L = []
def p(x=''):
    L.append(str(x))

def flush():
    open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
    print('\n'.join(L))


def md5_bytes(b):
    return hashlib.md5(bytes(b)).hexdigest()


def get_cmap():
    rows_, ents_, types_, end_, tb_, slots_, chosen_, cmap_, st_ = B.build_plan()
    return cmap_, st_['native_set']


def find_blob(arc, stride, n):
    for i, b in enumerate(arc.blobs):
        st, nn = T.hdr(bytes(b))
        if st == stride and nn == n:
            return i
    return None


def load_zh(spec):
    fp = os.path.join(W, spec['json'])
    if not os.path.exists(fp):
        return {}
    d = json.load(open(fp, encoding='utf-8'))
    d = d.get('names', d)
    return {int(k): v for k, v in d.items() if v}


def build_plan(spec, cmap, native):
    """返回 (liv, bak, slots, miss_chars, names)"""
    zh_map = load_zh(spec)
    liv, bak = {}, {}
    for tag in ('LANG_JA', 'LANG_EN'):
        liv[tag] = s2a.Archive(T.FILEMAP[tag])
        bak[tag] = s2a.Archive(T.BAKMAP[tag])
    bi = {}
    names = {}
    for tag in ('LANG_JA', 'LANG_EN'):
        bi[tag] = find_blob(bak[tag], spec['stride'], spec['n'])
        names[tag] = []
        for rec in range(spec['n']):
            raw = T.val_at(bak[tag], bi[tag], spec['pos'], rec)
            core = (raw or b'')[T.strip_lead(raw or b''):]
            names[tag].append(core)

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

    slots = {}
    miss = collections.Counter()
    for rec, zh in zh_map.items():
        for c in zh:
            if ord(c) >= 0x80 and c not in cmap and c not in native:
                miss[c] += 1

    for tag in ('LANG_JA', 'LANG_EN'):
        ref = 'LANG_EN' if tag == 'LANG_JA' else 'LANG_JA'
        for rec in range(spec['n']):
            nm = names[tag][rec]
            if not nm or not nm.decode('cp932', 'ignore').strip():
                continue
            txt = T.dec(nm)
            if txt.startswith('<') or txt.endswith('>'):     # <EVO_NAME__> 之类占位符
                continue
            zh = zh_map.get(rec)
            if not zh:
                continue
            enc = B.encode_text(zh, cmap, native)
            for (bi2, s, lead, rec2, pos, form, suf) in T.find_hits(idxs[tag], prefs[tag], nm):
                if form != 'EXACT' or rec2 < 0:
                    continue
                if metas[tag][bi2] != metas[ref][bi2]:
                    continue
                v = T.val_at(bak[tag], bi2, pos, rec2)
                rv = T.val_at(bak[ref], bi2, pos, rec2)
                if v is None or rv is None or v == rv:
                    continue
                st, n = metas[tag][bi2]
                base = 16 + rec2 * st
                rec_end = min(16 + (rec2 + 1) * st, len(bytes(bak[tag].blobs[bi2])))
                brun = T.slot_run(bytes(bak[tag].blobs[bi2]), base, pos, rec_end)
                if brun is None:
                    continue
                bs, be = brun
                old = bytes(bak[tag].blobs[bi2])[bs:be]
                pre = old[:T.strip_lead(old)]
                lb = bytes(liv[tag].blobs[bi2])
                lrun = T.slot_run(lb, base, pos, rec_end)
                lcur = lb[lrun[0]:lrun[1]] if lrun else b''
                lcore = lcur[T.strip_lead(lcur):]
                ocore = old[T.strip_lead(old):]
                lead_q = (ocore[:2] == b'\x81u' or lcore[:2] == b'\x81u') and not zh.startswith('「')
                trail_q = (ocore[-2:] == b'\x81v' or lcore[-2:] == b'\x81v') and not zh.endswith('」')
                new = pre + (b'\x81u' if lead_q else b'') + enc + (b'\x81v' if trail_q else b'')
                k = be
                lim = bytes(bak[tag].blobs[bi2])
                while k < rec_end and lim[k] == 0:
                    k += 1
                cap = k - bs
                key = (tag, bi2, rec2, pos)
                if key in slots:
                    continue
                if lcur == old:
                    state = 'clean'
                elif lcur == new:
                    state = 'already'
                else:
                    state = 'clobber'
                slots[key] = {'old': old, 'new': new, 'cap': cap, 'bs': bs, 'pre': lcur,
                              'zh': zh, 'ja_old': T.dec(old), 'trec': rec, 'state': state,
                              'lcur_zh': dec_carrier(lcore)}
    return liv, bak, slots, miss, names


def cscv_gate(stage):
    """cscv 硬闸：三张名字表在 **cscv 孪生 blob 里的【名字字段】** 必须仍是日文原版。
    （cscv 的说明文等其它字段主汉化翻过，不影响；出事的只有"名字=脚本层键"。）"""
    cs = s2a.Archive(T.FILEMAP['cscv'])
    ja = s2a.Archive(T.BAKMAP['LANG_JA'])
    bad = []
    for spec in SPECS:
        cat = spec['cat']
        cb = CSCV_TWIN[cat]
        lb = find_blob(ja, spec['stride'], spec['n'])
        nd = 0
        for rec in range(spec['n']):
            o = 16 + rec * spec['stride'] + spec['pos']
            a = bytes(cs.blobs[cb])[o:o + 64].split(b'\x00')[0]
            b = bytes(ja.blobs[lb])[o:o + 64].split(b'\x00')[0]
            if a != b:
                nd += 1
        if nd:
            bad.append('%s: cscv b%d 名字字段有 %d/%d 非原版' % (cat, cb, nd, spec['n']))
        else:
            p('  [cscv闸/%s] %-6s cscv b%-4d 名字字段 %d/%d 仍是日文原版 ✅'
              % (stage, cat, cb, spec['n'], spec['n']))
    for b in bad:
        p('  [cscv闸/%s] ⚠ %s' % (stage, b))
    return bad


def cscv_md5():
    cs = s2a.Archive(T.FILEMAP['cscv'])
    return md5_bytes(b''.join(bytes(x) for x in cs.blobs))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    sel = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 'all'
    force = '--skip-clobber' not in sys.argv
    cmap, native = get_cmap()
    specs = [s for s in SPECS if sel == 'all' or sel == s['cat']]

    p('#' * 100)
    p(' 名字批次（G2）· %s ｜ 类=%s ｜ cscv 绝不写入' % (mode, sel))
    p('#' * 100)
    p('')
    cscv_before = cscv_md5()
    p('  cscv.s2a md5(写前) = %s' % cscv_before[:12])
    cscv_gate('写前')

    all_edits = {}
    tsv_rows = ['\t'.join(['类', 'tag', 'blob', 'rec', 'pos', 'off', 'cap', 'state', '原版', '本批', '现况反解'])]
    for spec in specs:
        liv, bak, slots, miss, names = build_plan(spec, cmap, native)
        p('')
        p('=' * 100)
        p(' %s ｜ 槽位 %d ｜ 缺字 %d 种' % (spec['cat'], len(slots), len(miss)))
        p('=' * 100)
        per_tag = collections.Counter(t for (t, b, r, q) in slots)
        p('  按文件：%s' % dict(per_tag))
        st_cnt = collections.Counter(v['state'] for v in slots.values())
        p('  实况：原版未动 %d ｜ 已是本批译文 %d ｜ 主汉化另有措辞 %d'
          % (st_cnt['clean'], st_cnt['already'], st_cnt['clobber']))
        overflow = [(k, v) for k, v in slots.items() if len(v['new']) > v['cap']]
        p('  容量超限：%d' % len(overflow))
        for (k, v) in overflow[:10]:
            p('      %s b%d rec%d pos%d 需 %d > 容 %d (%s -> %s)'
              % (k[0], k[1], k[2], k[3], len(v['new']), v['cap'], v['ja_old'], v['zh']))
        if miss:
            p('  缺字：%s' % dict(miss))
        cl = [(k, v) for k, v in sorted(slots.items()) if v['state'] == 'clobber']
        if cl:
            p('  ★ 主汉化另有措辞的槽（%d 个，将统一为本批译文）：' % len(cl))
            for (k, v) in cl[:24]:
                p('      %s b%-5d rec%-5d pos%-4d 主汉化=%r  原版=%r  -> 本批=%r'
                  % (k[0], k[1], k[2], k[3], v['lcur_zh'], v['ja_old'], v['zh']))
        blobset = collections.Counter('%s:b%d' % (t, b) for (t, b, r, q) in slots)
        p('  涉及 blob 数：%d（top 10）' % len(blobset))
        for kb, nb in blobset.most_common(10):
            p('      %-16s %d' % (kb, nb))
        for (k, v) in sorted(slots.items())[:8]:
            p('      样例 %s b%-5d rec%-4d pos%-4d %r -> %r（占 %d/容 %d）'
              % (k[0], k[1], k[2], k[3], v['ja_old'], v['zh'], len(v['new']), v['cap']))
        for (tag, b, rec2, pos), v in sorted(slots.items()):
            tsv_rows.append('\t'.join([spec['cat'], tag, str(b), str(rec2), str(pos), str(v['bs']),
                                       str(v['cap']), v['state'], v['ja_old'], v['zh'], v['lcur_zh']]))
        all_edits[spec['cat']] = (spec, liv, bak, slots)

        if mode == 'apply':
            if overflow:
                p('  ⚠ 有容量超限，跳过本类。')
                continue
            if miss:
                p('  ⚠ 有缺字，跳过本类。')
                continue
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            dst = os.path.join(PRE, ts)
            os.makedirs(dst, exist_ok=True)
            for tag in ('LANG_JA', 'LANG_EN'):
                shutil.copy2(T.FILEMAP[tag], os.path.join(dst, os.path.basename(T.FILEMAP[tag])))
            p('  [备份] LANG_JA/LANG_EN -> %s' % dst)
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
            k = nmledger.record(spec['batch'], spec['cat'], edits,
                                note='G2 %s 全副本同改（cscv 未动）' % spec['cat'])
            p('  [写入] %d 槽（跳过已是本批 %d ｜ 未覆盖 %d ｜ 漂移 %d）→ 账本批次 %r'
              % (k, n_skip, n_conf, n_mis, spec['batch']))
    open(TSV, 'w', encoding='utf-8').write('\n'.join(tsv_rows))

    if mode == 'apply':
        p('')
        cscv_after = cscv_md5()
        p('  cscv.s2a md5(写后) = %s' % cscv_after[:12])
        p('  ★ cscv 是否被改：%s' % ('未动 ✅' if cscv_after == cscv_before else '被改了 ⚠⚠'))
        cscv_gate('写后')
        p('')
        p('  回滚：汉化-名字类回滚.bat（或 python _work/t140_name_revert.py revert 类名）')
    flush()


if __name__ == '__main__':
    main()
