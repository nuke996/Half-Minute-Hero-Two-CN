# -*- coding: utf-8 -*-
"""v2.28 同伴技能键表修复（blob954/cscv917）：
1) 备份已装 LANG_JA.s2a / LANG_EN.s2a / cscv.s2a / text_v2.csv  (*.bak_b954_<ts>)
2) LANG_JA[954] / LANG_EN[954] / cscv[917] <- 各自 .bak 的原始字节（整 blob 还原）
3) text_v2.csv 中 blob954 的 82 行 zh_new/zh_3dm 双清空（防未来重装复发）；
   zh_3dm 原值另存 outputs/blob954_rows_3dm_backup_<ts>.tsv（信息不丢）
4) 验证：三 blob md5 回原版值；blob 数量不变；抽查 blob25/cscv23 未受影响

用法：python fix_954.py           # 修复
      python fix_954.py revert    # 一键回滚（从 bak_b954_* 恢复）
输出：_work/fix954_out.txt
"""
import os, sys, csv, json, hashlib, shutil, time

import paths
BASE = paths.GAME_DIR
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a

OUT = []
def p(s=''):
    OUT.append(str(s))

def md5(b):
    return hashlib.md5(bytes(b)).hexdigest()

STATE = paths.build('fix954_state.json')
TS = time.strftime('%Y%m%d_%H%M%S')

# 还原目标：已装文件 -> blob索引 -> 原版来源
JOBS = [
    ('res/LANG_JA.s2a', 954, 'res/LANG_JA.s2a.bak'),
    ('res/LANG_EN.s2a', 954, 'res/LANG_EN.s2a.bak'),
    ('res/cscv.s2a',    917, 'res/cscv.s2a.bak'),
]
CSV_PATH = os.path.join(paths.DATA_DIR, 'text_v2.csv')

def do_revert():
    st = json.load(open(STATE, encoding='utf-8'))
    for rel, bk in st['backups'].items():
        src = os.path.join(BASE, rel)
        shutil.copy2(bk, src)
        p('回滚: %s <- %s' % (rel, os.path.basename(bk)))
    shutil.copy2(st['csv_backup'], CSV_PATH)
    p('回滚: text_v2.csv <- %s' % os.path.basename(st['csv_backup']))
    p('回滚完成。')

if len(sys.argv) > 1 and sys.argv[1] == 'revert':
    do_revert()
    open(paths.build('fix954_out.txt'), 'w', encoding='utf-8').write('\n'.join(OUT))
    print('revert done')
    sys.exit(0)

# ---------- 1) 备份 ----------
backups = {}
for rel, _, _ in JOBS:
    src = os.path.join(BASE, rel)
    bk = src + '.bak_b954_' + TS
    shutil.copy2(src, bk)
    backups[rel] = bk
    p('备份: %s -> %s' % (rel, os.path.basename(bk)))
csv_bk = CSV_PATH + '.bak_b954_' + TS
shutil.copy2(CSV_PATH, csv_bk)
p('备份: text_v2.csv -> %s' % os.path.basename(csv_bk))
p('')

# ---------- 2) 整 blob 还原 ----------
snap = {}   # 修复前 md5 快照（用于"未误伤"抽查）
for rel, bi, _ in JOBS:
    a = s2a.Archive(os.path.join(BASE, rel))
    snap[rel] = (len(a.blobs), md5(a.blobs[bi]))
for rel, bi, bak in JOBS:
    src = os.path.join(BASE, rel)
    a = s2a.Archive(src)
    o = s2a.Archive(os.path.join(BASE, bak))
    blobs = [bytearray(b) for b in a.blobs]
    if md5(blobs[bi]) == md5(o.blobs[bi]):
        p('跳过(已是原版): %s blob%d' % (rel, bi))
        continue
    blobs[bi] = bytearray(o.blobs[bi])
    s2a.pack(src, a.entries, blobs)
    p('还原: %s blob%d (%d B) <- %s blob%d' % (rel, bi, len(o.blobs[bi]), os.path.basename(bak), bi))
p('')

# ---------- 3) CSV 清空 ----------
with open(CSV_PATH, 'rb') as f:
    head = f.read(3)
has_bom = head == b'\xef\xbb\xbf'
with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
    rows = list(csv.reader(f))

tsv_backup = paths.build('blob954_rows_3dm_backup_%s.tsv' % TS)
n_clear = 0
with open(tsv_backup, 'w', encoding='utf-8') as f:
    f.write('row_id\tblob\toffset\tja\tzh_new_old\tzh_3dm_old\n')
    for r in rows:
        if len(r) >= 10 and r[1] == '954':
            f.write('\t'.join([r[0], r[1], r[2], r[7], r[8], r[9]]) + '\n')
            r[8] = ''
            r[9] = ''
            n_clear += 1

with open(CSV_PATH, 'w', encoding='utf-8-sig' if has_bom else 'utf-8', newline='') as f:
    csv.writer(f).writerows(rows)
p('CSV: blob954 行清空 %d 行 (zh_3dm 原值 -> %s)' % (n_clear, os.path.basename(tsv_backup)))
p('')

# ---------- 4) 验证 ----------
p('=== 验证 ===')
ok = True
EXPECT_JA954 = '0f42f920349908e4233acf578276d041'
for rel, bi, bak in JOBS:
    a = s2a.Archive(os.path.join(BASE, rel))
    o = s2a.Archive(os.path.join(BASE, bak))
    m = md5(a.blobs[bi])
    good = (m == md5(o.blobs[bi]))
    ok &= good
    p('  [%s] blob%d md5=%s %s (备份前=%s) blob数 %d -> %d' % (
        rel, bi, m[:16], 'OK=原版' if good else 'FAIL',
        snap[rel][1][:16], snap[rel][0], len(a.blobs)))
    ok &= (snap[rel][0] == len(a.blobs))

mja = md5(s2a.Archive(os.path.join(BASE, 'res/LANG_JA.s2a')).blobs[954])
p('  LANG_JA[954] == 已知原版md5(%s) ? %s' % (EXPECT_JA954[:16], mja == EXPECT_JA954))
ok &= (mja == EXPECT_JA954)
mcs = md5(s2a.Archive(os.path.join(BASE, 'res/cscv.s2a')).blobs[917])
p('  cscv[917] == LANG_JA[954] (同内容键表恢复一致) ? %s' % (mcs == mja))
ok &= (mcs == mja)

# 未误伤抽查：blob25(v2.27 战斗消息) / cscv[23](孪生) / LANG blob391(v2.23 MESS)
for rel, bi in [('res/LANG_JA.s2a', 25), ('res/LANG_EN.s2a', 25),
                ('res/cscv.s2a', 23), ('res/LANG_JA.s2a', 391)]:
    a = s2a.Archive(os.path.join(BASE, rel))
    b = s2a.Archive(backups[rel])
    same = md5(a.blobs[bi]) == md5(b.blobs[bi])
    ok &= same
    p('  未误伤 [%s] blob%d 与修复前一致 ? %s' % (rel, bi, same))

with open(CSV_PATH, encoding='utf-8-sig', newline='') as f:
    rows2 = list(csv.reader(f))
n954 = sum(1 for r in rows2 if len(r) >= 10 and r[1] == '954')
leftover = sum(1 for r in rows2 if len(r) >= 10 and r[1] == '954' and (r[8] or r[9]))
p('  CSV 复查: 总行数 %d -> %d; blob954 行 %d; 残留译文 %d' % (len(rows), len(rows2), n954, leftover))
ok &= (len(rows) == len(rows2) and leftover == 0)

p('')
p('==== %s ====' % ('全部通过 ✅' if ok else '存在失败项 ❌'))

json.dump({'backups': backups, 'csv_backup': csv_bk, 'ts': TS},
          open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
p('回滚: python fix_954.py revert  (状态已存 fix954_state.json)')

open(paths.build('fix954_out.txt'), 'w', encoding='utf-8').write('\n'.join(OUT))
print('written lines=%d' % len(OUT))
