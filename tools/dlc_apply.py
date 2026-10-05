# -*- coding: utf-8 -*-
"""DLC01 汉化写入器（v2，2026-09-13 修根因）

⚠️ v1 的致命 bug：写入用 `enc + 0x00 填满到 cap`，而"记录内最后一个字段"的 cap 会一直
   算到记录末 —— 于是把**每条记录末尾 4 字节的记录 ID / 分隔标记（FF FF FF FF）整片清零**，
   导致对话记录的链接断掉、剧情无法触发（用户实测：泳装店 NPC 起整个村子对话失效）。
   v2 规则：**只在自己原文占用的字节范围内改写 + 清残留**，绝不越界清零。

用法：  python dlc_apply.py plan | apply | verify | revert
"""
import os, sys, csv, glob, time, shutil, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import dlc_lib as D

os.makedirs(paths.BUILD_DIR, exist_ok=True)
OUT = paths.data('dlc')
LOG = os.path.join(paths.BUILD_DIR, '_dlc_apply_out.txt')


def _cap_by_off(blob):
    return {off: cap for off, _pos, _s, cap in D.field_slots(blob)}


def load_zh():
    zh = {}
    for fp in sorted(glob.glob(os.path.join(OUT, 'zh_*.tsv'))):
        if os.path.basename(fp) == 'zh_07.tsv':
            continue        # 索引表，正文见 zh_07.json（多行台词含 \n）
        for ln in open(fp, encoding='utf-8-sig').read().splitlines():
            if ln.strip():
                ja, _, z = ln.partition('\t')
                zh[ja] = z
    with open(os.path.join(OUT, 'dlc_unique.tsv'), encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if r['cat'] == '1':
                z = r['zh_auto'] or ('离开村庄' if r['ja'] == '村を出る' else '')
                if z:
                    zh.setdefault(r['ja'], z)
    for j in open(os.path.join(OUT, 'dlc_skip.txt'), encoding='utf-8').read().splitlines():
        zh.pop(j, None)
    return zh


def load_multi():
    """多行台词补译（ja 含 \\n -> zh）。"""
    fp = os.path.join(OUT, 'zh_07.json')
    return json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) else {}


def build_plan():
    """plan 每项：off / cap / limit（两侧较小）/ orig_end（两侧较大）/ cap_eff。"""
    import build_cn as B
    rows, ents, types, end, tb, slots, chosen, cmap, st = B.build_plan()
    native = st['native_set']
    zh = load_zh()
    mzh = load_multi()

    o_ja = D.s2a.Archive(D.P_JA + D.BAK_SUFFIX)     # 原件
    o_en = D.s2a.Archive(D.P_EN + D.BAK_SUFFIX)
    L = []
    def log(s=''): L.append(str(s))

    plan = []
    planned = set()
    n_missing = 0
    n_multi = 0

    def add_slot(bi, bja, ben, cja, cen, off, pos, s, cand):
        nonlocal n_missing
        disp = B.apply_repl(cand)
        enc = B.encode_text(disp, cmap, native)
        for ch in disp:
            if ord(ch) < 0x80 or ch in cmap or ch in native or ch in '\n\r\t':
                continue
            n_missing += 1
            break
        cap1 = min(cja.get(off, 10 ** 9), cen.get(off, 10 ** 9))
        lim_ja = D.field_limit(bja, off, cap1)
        lim_en = D.field_limit(ben, off, cap1)
        limit = min(lim_ja, lim_en)
        orig_end = min(max(D.field_text_end(bja, off), D.field_text_end(ben, off)), limit)
        plan.append({'blob': bi, 'off': off, 'pos': pos, 'ja': s, 'zh': cand,
                     'disp': disp, 'enc': enc, 'cap': cap1, 'limit': limit,
                     'orig_end': orig_end, 'cap_eff': limit - off})
        planned.add((bi, off))

    for bi in range(len(o_ja.blobs)):
        bja = bytes(o_ja.blobs[bi]); ben = bytes(o_en.blobs[bi])
        cja = _cap_by_off(bja); cen = _cap_by_off(ben)
        for off, pos, s, capj in D.field_slots(bja):
            if s in zh:
                add_slot(bi, bja, ben, cja, cen, off, pos, s, zh[s])
        # 第二遍：捞回被 field_slots 漏掉的多行台词（段内含 \n）
        if mzh:
            stride = D.cscv_header(bja)[0] if D.cscv_header(bja) else 0
            for off, s in D.segs_lf(bja):
                if (bi, off) in planned or s not in mzh:
                    continue
                add_slot(bi, bja, ben, cja, cen, off,
                         (off - 16) % stride if stride else 0, s, mzh[s])
                n_multi += 1

    over = [p for p in plan if len(p['enc']) >= p['cap_eff']]
    log('== DLC01 汉化写入计划 v2 ==')
    log('待写槽位: %d（含多行补译 %d）  blob 数: %d'
        % (len(plan), n_multi, len({p['blob'] for p in plan})))
    log('编码缺字: %d' % n_missing)
    log('超容量: %d' % len(over))
    for p in over[:30]:
        log('   b%-3d off=%-7d cap_eff=%-4d len=%-4d %r -> %r'
            % (p['blob'], p['off'], p['cap_eff'], len(p['enc']), p['ja'][:24], p['disp'][:24]))
    log('')
    log('样例 12 条（保护区 = 硬边界之后到 cap 的字节，必须原样保留）：')
    for p in plan[:12]:
        prot = bytes(o_ja.blobs[p['blob']])[p['limit']:p['off'] + p['cap']]
        log('   b%-3d pos=%-4d cap=%-4d 限=%-4d 保护区%-4dB %s  %r -> %r'
            % (p['blob'], p['pos'], p['cap'], p['cap_eff'], len(prot),
               prot[:4].hex() if prot else '-      ', p['ja'][:16], p['disp'][:16]))
    return plan, over, L


def cmd_plan():
    plan, over, L = build_plan()
    open(LOG, 'w', encoding='utf-8').write('\n'.join(L))
    print('ok')


def _write_slots(blob, p):
    """只改原文自身范围 + 填终止符；不越界清零。"""
    off, end = p['off'], p['off'] + len(p['enc'])
    blob[off:end] = p['enc']
    if end < p['orig_end']:
        blob[end:p['orig_end']] = b'\x00' * (p['orig_end'] - end)
    elif end < p['limit']:
        blob[end] = 0


def cmd_apply():
    plan, over, L = build_plan()
    if over:
        L.append('')
        L.append('!! 存在超容量，已中止写入')
        open(LOG, 'w', encoding='utf-8').write('\n'.join(L))
        print('abort')
        return
    ts = time.strftime('%Y%m%d_%H%M%S')
    for p in (D.P_JA, D.P_EN):
        shutil.copy2(p, p + '.bak_dlcapplyv2_' + ts)
    L.append('')
    L.append('备份: *.bak_dlcapplyv2_%s' % ts)
    for path in (D.P_JA, D.P_EN):
        a = D.s2a.Archive(path)
        blobs = [bytearray(bytes(b)) for b in a.blobs]
        for p in plan:
            _write_slots(blobs[p['blob']], p)
        D.s2a.pack(path, a.entries, blobs)
        L.append('写入 %s : %d 处（blob=%d，大小=%d）'
                 % (os.path.basename(path), len(plan), len(blobs), os.path.getsize(path)))
    open(LOG, 'w', encoding='utf-8').write('\n'.join(L))
    print('ok')


def cmd_verify():
    """三重验证：
       ① 译文槽读回 == 期望（cmap 反查解码）
       ② 所有"非零→零"的字节都落在被改写字段的原文范围内（无越界清零）
       ③ 每条记录末尾 4 字节 == 原件；EN 与 JA 完全一致
    """
    import build_cn as B
    rows, ents, types, end, tb, slots, chosen, cmap, st = B.build_plan()
    native = st['native_set']
    rev = D.make_decoder(cmap, native)
    zh = load_zh()
    a_ja = D.s2a.Archive(D.P_JA); a_en = D.s2a.Archive(D.P_EN)
    o_ja = D.s2a.Archive(D.P_JA + D.BAK_SUFFIX); o_en = D.s2a.Archive(D.P_EN + D.BAK_SUFFIX)
    plan, _over, _L = build_plan()
    by_blob = {}
    for p in plan:
        by_blob.setdefault(p['blob'], []).append(p)

    L = []
    def log(s=''): L.append(str(s))
    n_ok = n_bad = 0
    bad = []
    n_en_mis = 0
    en_ex = []
    n_actx = 0            # 非零被清零的字节数
    n_actx_out = 0        # 越界的（不该有）
    out_ex = []
    n_nz_created = 0
    for bi in range(len(a_en.blobs)):
        nb = bytes(a_ja.blobs[bi]); ob = bytes(o_ja.blobs[bi])
        if nb == ob and not by_blob.get(bi):
            continue
        allowed = [(p['off'], p['orig_end']) for p in by_blob.get(bi, [])]
        allowed_new = [(p['off'], p['off'] + len(p['enc'])) for p in by_blob.get(bi, [])]
        for i in range(len(ob)):
            if nb[i] == ob[i]:
                continue
            if ob[i] != 0 and nb[i] == 0:
                n_actx += 1
                if not any(a <= i < b for a, b in allowed):
                    n_actx_out += 1
                    if len(out_ex) < 20:
                        out_ex.append('b%-3d @%-7d 原=0x%02X 新=0x00' % (bi, i, ob[i]))
            elif ob[i] == 0 and nb[i] != 0:
                n_nz_created += 1
                if not any(a <= i < b for a, b in allowed_new):
                    n_actx_out += 1
                    if len(out_ex) < 20:
                        out_ex.append('b%-3d @%-7d 原=0x00 新=0x%02X (越界写入)' % (bi, i, nb[i]))
    for p in plan:
        cur = bytes(a_ja.blobs[p['blob']])[p['off']:p['limit']].split(b'\x00')[0]
        got = D.decode_installed(cur, rev)
        if got == p['disp']:
            n_ok += 1
        else:
            n_bad += 1
            if len(bad) < 20:
                bad.append('b%-3d pos=%-4d want=%r got=%r'
                           % (p['blob'], p['pos'], p['disp'][:26], got[:26]))
        en_cur = bytes(a_en.blobs[p['blob']])[p['off']:p['limit']]
        ja_cur = bytes(a_ja.blobs[p['blob']])[p['off']:p['limit']]
        if en_cur != ja_cur:
            n_en_mis += 1
            if len(en_ex) < 15:
                en_ex.append('b%-3d off=%-7d pos=%-4d JA=%s | EN=%s'
                             % (p['blob'], p['off'], p['pos'], ja_cur.hex()[:40],
                                en_cur.hex()[:40]))
    # 记录尾标记
    n_foot_bad = 0
    for bi in range(len(a_ja.blobs)):
        h = D.cscv_header(bytes(o_ja.blobs[bi]))
        if not h:
            continue
        stride, n = h
        o = bytes(o_ja.blobs[bi]); nb = bytes(a_ja.blobs[bi])
        for r in range(n):
            base = 16 + r * stride
            if o[base + stride - 4:base + stride] != nb[base + stride - 4:base + stride]:
                n_foot_bad += 1
    log('== DLC01 装后验证 v2 ==')
    log('① 译文槽位: 正确 %d / 不符 %d' % (n_ok, n_bad))
    for x in bad:
        log('     ' + x)
    log('② 非零被清零的字节: %d ；其中越界(不该有): %d' % (n_actx, n_actx_out))
    for x in out_ex:
        log('     ' + x)
    log('   零变非零字节数: %d（新译文写入）' % n_nz_created)
    log('③ 记录尾 4 字节被改动: %d 条' % n_foot_bad)
    log('   EN 与 JA 不一致槽位: %d' % n_en_mis)
    for x in en_ex:
        log('     ' + x)
    log('   blob 数 JA=%d(原%d) EN=%d(原%d)；大小 JA=%d(原%d) EN=%d(原%d)'
        % (len(a_ja.blobs), len(o_ja.blobs), len(a_en.blobs), len(o_en.blobs),
           os.path.getsize(D.P_JA), os.path.getsize(D.P_JA + D.BAK_SUFFIX),
           os.path.getsize(D.P_EN), os.path.getsize(D.P_EN + D.BAK_SUFFIX)))
    ok = (n_bad == 0 and n_en_mis == 0 and n_actx_out == 0 and n_foot_bad == 0)
    log('结论: %s' % ('ALL OK' if ok else 'FAILED'))
    open(os.path.join(paths.BUILD_DIR, '_dlc_verify_out.txt'), 'w', encoding='utf-8').write('\n'.join(L))
    print('ok')


def cmd_revert():
    n = 0
    for p in (D.P_JA, D.P_EN):
        src = p + D.BAK_SUFFIX
        if os.path.exists(src):
            shutil.copy2(src, p); n += 1
    open(LOG, 'w', encoding='utf-8').write('已从 .bak_dlc01_20260913 还原 %d 个文件' % n)
    print('ok')


if __name__ == '__main__':
    m = sys.argv[1] if len(sys.argv) > 1 else 'plan'
    {'plan': cmd_plan, 'apply': cmd_apply, 'verify': cmd_verify, 'revert': cmd_revert}[m]()
