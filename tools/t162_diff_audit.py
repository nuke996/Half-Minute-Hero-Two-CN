# -*- coding: utf-8 -*-
"""t162_diff_audit.py —— 通用写入审计：live vs 写入前备份
用法：python t162_diff_audit.py <备份根目录> <批次id,批次id,...>
把 live 与"写入前最早那次备份"逐字节比对，确认每一处差异都落在账本登记的槽范围内。
"""
import os, sys
import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR; os.chdir(W); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a
import t140_name_revert as T
import nmledger

PRE_ROOT = os.path.join(paths.BUILD_DIR, sys.argv[1] if len(sys.argv) > 1 else '_pre_t153')
IDS = (sys.argv[2] if len(sys.argv) > 2 else '').split(',')
OUT = paths.build('t162_diff_audit.txt')

dirs = sorted(d for d in os.listdir(PRE_ROOT) if os.path.isdir(os.path.join(PRE_ROOT, d)))
if os.path.exists(os.path.join(PRE_ROOT, 'LANG_JA.s2a')):
    PREV = PRE_ROOT                                  # 直接给了含文件的目录
else:
    PREV = os.path.join(PRE_ROOT, dirs[0])           # 否则取"最早那次"= 全部写入之前

bs = [b for b in nmledger.batches() if b['id'] in IDS]
edits = [e for b in bs for e in b['edits']]

out = []
def p(s=''):
    out.append(s)

p('#' * 100)
p(' 写入审计：live vs 写入前备份')
p('   备份（最早）= %s' % PREV)
p('   账本批次     = %s' % IDS)
p('   槽数合计     = %d' % len(edits))
p('#' * 100)

by_file = {}
for e in edits:
    sp = max(len(bytes.fromhex(e['new'])), len(bytes.fromhex(e['old'])))
    by_file.setdefault(e['f'], {}).setdefault(e['b'], []).append((e['off'], sp))

tot_seg = tot_bad = 0
for tag in ('LANG_JA', 'LANG_EN'):
    cur = s2a.Archive(T.FILEMAP[tag])
    old = s2a.Archive(os.path.join(PREV, os.path.basename(T.FILEMAP[tag])))
    p('')
    p('── %s  blob 数 %d -> %d' % (tag, len(old.blobs), len(cur.blobs)))
    n_diff = n_ok = n_bad = 0
    first_bad = []
    for bi in range(min(len(old.blobs), len(cur.blobs))):
        a = bytes(old.blobs[bi]); b = bytes(cur.blobs[bi])
        if a == b:
            continue
        if len(a) != len(b):
            p('   ⚠ blob%d 长度变化 %d -> %d' % (bi, len(a), len(b)))
        reg = sorted(by_file.get(tag, {}).get(bi, []))
        n = min(len(a), len(b))
        i = 0
        while i < n:
            if a[i] == b[i]:
                i += 1
                continue
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            n_diff += 1
            ok = any(off <= i and j <= off + sp for (off, sp) in reg)
            if ok:
                n_ok += 1
            else:
                n_bad += 1
                if len(first_bad) < 10:
                    first_bad.append((bi, i, j, a[i:j].hex(), b[i:j].hex()))
            i = j
    p('   差异段 %d ｜ 命中登记槽 %d ｜ 未登记(意外) %d' % (n_diff, n_ok, n_bad))
    for (bi, i, j, ah, bh) in first_bad:
        p('      ⚠ b%d off%d..%d  旧=%s 新=%s' % (bi, i, j, ah, bh))
    tot_seg += n_diff; tot_bad += n_bad

p('')
p('  合计：差异段 %d ｜ 未登记 %d  ⇒ %s'
  % (tot_seg, tot_bad, '✅ 除本批外零附带变化' if tot_bad == 0 else '⚠ 有意外改动'))

# cscv / DLC01 必须零改动
p('')
p('── 其它文件（应零改动）')
import hashlib
for tag in ('cscv', 'DLC01_LANG_JA', 'DLC01_LANG_EN'):
    f = T.FILEMAP[tag]
    cand = os.path.join(PREV, tag + '.s2a')          # 与 t140 do_snapshot 的命名一致
    if not os.path.exists(cand):
        p('   %-12s （备份中无此文件，跳过）' % tag); continue
    ha = hashlib.md5(open(f, 'rb').read()).hexdigest()
    hb = hashlib.md5(open(cand, 'rb').read()).hexdigest()
    p('   %-12s md5 %s %s' % (tag, '未改 ✅' if ha == hb else '被改 ⚠', ha[:12]))
open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
print('done')
