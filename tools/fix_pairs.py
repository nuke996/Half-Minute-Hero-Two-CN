# -*- coding: utf-8 -*-
"""女神房间 → 女神选项：菜单项名/分组 label 的"所有副本"处理。

用法:
    python fix_pairs.py check   # 只检查各副本是否一致（不改文件）
    python fix_pairs.py orig    # 把这 4 组名字的所有副本还原为原文（回退方案）

背景：道具表(blob280)的每条记录没有数字分组 id，游戏只能靠 label 文本与
菜单表(blob534)的菜单项名匹配来分组。若一边翻了另一边没翻，匹配失败 -> 点进去闪退。
本脚本按 4 组名字把 label / name / name2 / cscv 孪生 全部对齐。
"""
import sys, io, os, hashlib, shutil, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import paths
B = paths.GAME_DIR
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a
import build_cn as Bc

# (菜单项日文, blob280 label 偏移, blob534 name/name2 偏移)
GROUPS = [
    ('衣装チェンジ',       (16, 220, 424, 628, 832, 1036, 1240), (20, 60)),
    ('ウィンドウスキン',    (1852, 2056, 2260, 2464),              (680, 720)),
    ('タイマースキン',      (2668, 2872, 3076, 3280),              (900, 940)),
    ('ギャラリーフルコンプ', (4300,),                              (1120, 1160)),
]
SLOTS = []           # [(blob, off, slot_len)]
for _ja, l_offs, m_offs in GROUPS:
    for o in l_offs: SLOTS.append((280, o, 32))
    for o in m_offs: SLOTS.append((534, o, 36 if o not in (20, 680, 900, 1120) else 32))

def slot_text(d, off):
    j = off
    while j < len(d) and d[j] != 0: j += 1
    return d[off:j]

def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else 'check').lower()
    rows, ents, types, end, tb, slots_, chosen, cmap, st = Bc.build_plan()
    native = st['native_set']
    from build_cn import encode_text
    revb = {}
    for ch in chosen:
        b = encode_text(ch, cmap, native)
        if b: revb[b] = ch

    def dec(d, off, limit=200):
        out = []; j = off
        while j < len(d) and j < off + limit and d[j] != 0:
            if d[j] < 0x80: out.append(chr(d[j])); j += 1; continue
            two = bytes(d[j:j+2]); out.append(revb.get(two, '<?%s>' % two.hex())); j += 2
        return ''.join(out)

    files = [('LANG_JA', 'res/LANG_JA.s2a'), ('LANG_EN', 'res/LANG_EN.s2a'), ('cscv', 'res/cscv.s2a')]
    arch = {k: s2a.Archive(os.path.join(B, v)) for k, v in files}
    baks = {'LANG_JA': 'res/LANG_JA.s2a.bak', 'LANG_EN': 'res/LANG_EN.s2a.bak', 'cscv': 'res/cscv.s2a.bak'}
    bak = {k: s2a.Archive(os.path.join(B, v)) for k, v in baks.items()}
    # cscv 孪生映射：LANG_JA.bak blob 内容哈希 -> cscv.s2a.bak 中的相同 blob
    lj = bak['LANG_JA']
    csh = {}
    for j, b in enumerate(bak['cscv'].blobs):
        csh.setdefault(hashlib.md5(bytes(b)).hexdigest(), j)

    # ---- check：同一文件内，同一组的所有副本必须一致（跨语言不必相同）----
    bad = 0
    for _ja, l_offs, m_offs in GROUPS:
        cells = {t: [] for t in ('LANG_JA', 'LANG_EN', 'cscv')}
        for bi, off, _ln in SLOTS:
            if bi == 280 and off not in l_offs: continue
            if bi == 534 and off not in m_offs: continue
            j = csh.get(hashlib.md5(bytes(lj.blobs[bi])).hexdigest()) if bi < len(lj.blobs) else None
            cells['LANG_JA'].append(dec(bytes(arch['LANG_JA'].blobs[bi]), off))
            cells['LANG_EN'].append(dec(bytes(arch['LANG_EN'].blobs[bi]), off))
            if j is not None: cells['cscv'].append(dec(bytes(arch['cscv'].blobs[j]), off))
        line = '【%s】' % _ja
        for t, vs in cells.items():
            uniq = set(vs)
            ok = len(uniq) == 1
            if not ok: bad += 1
            line += '  %s=%s%s' % (t, (vs[0][:14] if vs else '-'), '' if ok else '<<不一致%s' % sorted(uniq))
        print(line)
    print('\n不一致处: %d （同一文件内各副本应完全相同）' % bad)

    if mode != 'orig':
        return
    # ---- orig：把原文写回所有副本 ----
    edited = 0
    for tag, rel in files:
        if tag == 'cscv':
            a = s2a.Archive(os.path.join(B, rel))
            blobs = [bytearray(b) for b in a.blobs]
        else:
            a = s2a.Archive(os.path.join(B, rel))
            blobs = [bytearray(b) for b in a.blobs]
        n = 0
        for bi, off, ln in SLOTS:
            if bi >= len(blobs): continue
            if tag == 'cscv':
                j = csh.get(hashlib.md5(bytes(lj.blobs[bi])).hexdigest())
                if j is None or j >= len(blobs): continue
                src_off, src = off, bytes(bak[tag].blobs[j])
                tgt = j
            else:
                if bi >= len(bak[tag].blobs): continue
                src_off, src = off, bytes(bak[tag].blobs[bi])
                tgt = bi
            if src_off + 1 > len(src): continue
            orig = slot_text(src, src_off)
            if not orig: continue
            if src_off + ln > len(blobs[tgt]): ln2 = len(blobs[tgt]) - src_off
            else: ln2 = ln
            if len(orig) + 1 > ln2: continue
            blobs[tgt][src_off:src_off + ln2] = b'\x00' * ln2
            blobs[tgt][src_off:src_off + len(orig)] = orig
            n += 1
        if n:
            bk = os.path.join(B, rel) + '.prepair_' + time.strftime('%Y%m%d_%H%M%S')
            shutil.copyfile(os.path.join(B, rel), bk)
            s2a.pack(os.path.join(B, rel), a.entries, blobs)
            print('  %s: 还原 %d 处 (备份 %s)' % (rel, n, os.path.basename(bk)))
            edited += n
    print('共还原 %d 处 —— 这 4 个菜单项将显示原文（日文/英文）' % edited)

main()
