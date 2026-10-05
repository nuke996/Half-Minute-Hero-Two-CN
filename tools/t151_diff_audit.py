# -*- coding: utf-8 -*-
"""t151_diff_audit.py —— G1 写入后审计：
把 live 与「写入前备份」逐字节比对，确认每一处差异都恰好落在
账本批次（称号名-G1）登记的槽范围内 ⇒ 除本批外零附带变化。
只读。
"""
import os, sys, json
import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR; os.chdir(W); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a
import t140_name_revert as T
import nmledger

PRE = paths.build('_pre_t148')
pre_dirs = sorted(d for d in os.listdir(PRE) if os.path.isdir(os.path.join(PRE, d)))
PREV = os.path.join(PRE, pre_dirs[-1])
OUT = paths.build('t151_diff_audit.txt')

bs = [b for b in nmledger.batches() if b['id'] == '称号名-G1']
edits = bs[0]['edits'] if bs else []

out = []
def p(s=''):
    out.append(s)

p('#' * 96)
p(' G1 写入审计：live vs 写入前备份 (%s)' % PREV)
p('#' * 96)
p('  账本批次 称号名-G1 槽数：%d' % len(edits))

# 按文件汇总登记范围
by_file = {}
for e in edits:
    by_file.setdefault(e['f'], {}).setdefault(e['b'], []).append(
        (e['off'], max(len(bytes.fromhex(e['new'])), len(bytes.fromhex(e['old']))), bytes.fromhex(e['new'])))

tot_seg = 0
tot_bad = 0
for tag in ('LANG_JA', 'LANG_EN'):
    cur = s2a.Archive(T.FILEMAP[tag])
    old = s2a.Archive(os.path.join(PREV, os.path.basename(T.FILEMAP[tag])))
    p('')
    p('── %s  blob 数 %d -> %d' % (tag, len(old.blobs), len(cur.blobs)))
    if len(old.blobs) != len(cur.blobs):
        p('   ⚠ blob 数变化！')
    n_diff = n_ok = n_bad = 0
    first_bad = []
    for bi in range(min(len(old.blobs), len(cur.blobs))):
        a = bytes(old.blobs[bi]); b = bytes(cur.blobs[bi])
        if a == b:
            continue
        if len(a) != len(b):
            p('   ⚠ blob%d 长度变化 %d -> %d' % (bi, len(a), len(b)))
        reg = sorted(by_file.get(tag, {}).get(bi, []))
        # 找差异段
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
            # 是否被某个登记槽覆盖
            ok = False
            for (off, ln, new) in reg:
                if off <= i and j <= off + ln:
                    ok = True
                    break
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
open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
print('done')
