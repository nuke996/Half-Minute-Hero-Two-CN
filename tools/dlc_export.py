# -*- coding: utf-8 -*-
"""DLC01 汉化 Step1 导出（只读）：
  - 取装机字库口径（build_cn.build_plan: cmap 新字形 + native 原版字形 + ASCII）= 本次翻译可用字符集
  - 取审计 JSON 逐串分类 c（0 可翻 / 1 复用主译 / 2 确认键 / 3 键疑）
  - 逐字段算容量（dlc_lib.field_slots）
  - 产出：
      _work/dlc/dlc_work.tsv     逐槽作业表（cat0+cat1，可翻）
      _work/dlc/dlc_unique.tsv   去重翻译工作单（distinct ja → 条目数/分类/复用译文）
      _work/dlc/dlc_charset.txt  可用字符集（翻译只能用它）
      _work/dlc/dlc_stats.txt    统计
"""
import os, sys, csv, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import dlc_lib as D
import s2a

OUTDIR = paths.data('dlc')
os.makedirs(OUTDIR, exist_ok=True)

L = []
def log(s=''):
    L.append(str(s))

# ---------- 1) 装机可用字符集 ----------
import build_cn as B
rows, ents, types, end, tb, slots, chosen, cmap, st = B.build_plan()
native = st['native_set']
ascii_set = set(chr(c) for c in range(0x20, 0x7F))
avail = set(cmap) | set(native) | ascii_set
log('== 装机字库 ==')
log('译表专用字形(cmappable): %d；原版直显 native: %d；可用合计: %d；余量 %d'
    % (len(cmap), len(native), len(avail), 2847 - len(chosen)))

# ---------- 2) 审计分类 ----------
AUD = json.load(open(paths.data('DLC01-审计数据.json'), encoding='utf-8'))
cat_of = {}      # (blob, off) -> (c, zh)
cat_by_str = {}  # (blob, 剥掉 f8f3 标记的串) -> (c, zh)
verdict_of = {}
def _strip(s):
    n = 0
    while n < len(s) and s[n] == '\uf8f3':
        n += 1
    return s[n:]
for bl in AUD['blobs']:
    verdict_of[bl['i']] = bl['verdict']
    for it in bl['strings']:
        cat_of[(bl['i'], it['o'])] = (it['c'], it.get('zh'))
        cat_by_str[(bl['i'], _strip(it['s']))] = (it['c'], it.get('zh'))

# ---------- 3) DLC 表 ----------
a_ja = s2a.Archive(D.P_JA)
a_en = s2a.Archive(D.P_EN)
log('DLC01 LANG_JA blobs=%d  LANG_EN blobs=%d' % (len(a_ja.blobs), len(a_en.blobs)))

work = []          # 逐槽
uniq = collections.OrderedDict()   # ja -> dict
skipped_nonjp = collections.Counter()
per_blob = []
for i in range(len(a_ja.blobs)):
    b = bytes(a_ja.blobs[i]); e = bytes(a_en.blobs[i])
    slots = D.field_slots(b)
    eslots = {f[0]: f[2] for f in D.field_slots(e)}
    n_keep = 0
    n_tr = 0
    for off, pos, s, cap in slots:
        c, zh = cat_of.get((i, off), (None, None))
        if c is None:
            c, zh = cat_by_str.get((i, s), (None, None))
        if c is None:
            continue
        if c in (2, 3) or i in D.SKIP_BLOBS:
            n_keep += 1
            continue
        # 只翻"含日文"的显示串：排除 ASCII 脚本变量名/文件名/坐标数值
        if not D.is_jp(s):
            n_keep += 1
            skipped_nonjp[s] += 1
            continue
        en = eslots.get(off, '')
        maxcn = max(0, (cap - 1) // 2)
        work.append({'blob': i, 'offset': off, 'pos': pos, 'cap': cap,
                     'maxcn': maxcn, 'cat': c, 'ja': s, 'en': en,
                     'zh_auto': zh or ''})
        n_tr += 1
        u = uniq.setdefault(s, {'n': 0, 'cat': c, 'zh_auto': zh or '', 'en': collections.Counter(),
                                 'maxcn': 9999})
        u['n'] += 1
        if en:
            u['en'][en] += 1
        u['maxcn'] = min(u['maxcn'], maxcn)
        if c == 0 and u['cat'] != 0:
            u['cat'] = 0
    per_blob.append((i, len(slots), n_tr, n_keep, verdict_of.get(i, '?')))

# ---------- 4) 字符可用性预检 ----------
miss = collections.Counter()
for s in uniq:
    for ch in s:
        if ord(ch) < 0x80 or ch in avail or ch in '\n\r\t':
            continue
        miss[ch] += 1
log('')
log('== 日文原串用字（翻译时只需保证中文用字在库；日文缺字不影响）==')
log('日文侧缺字 %d 种: %s' % (len(miss), ' '.join('%s(%d)' % (c, n) for c, n in miss.most_common(30))))

# ---------- 5) 写文件 ----------
with open(os.path.join(OUTDIR, 'dlc_work.tsv'), 'w', encoding='utf-8', newline='') as f:
    f.write('blob\toffset\tpos\tcap\tmaxcn\tcat\tja\ten\tzh_auto\n')
    for r in sorted(work, key=lambda x: (x['blob'], x['offset'])):
        f.write('%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\n'
                % (r['blob'], r['offset'], r['pos'], r['cap'], r['maxcn'], r['cat'],
                   r['ja'].replace('\t', ' '), r['en'].replace('\t', ' '), r['zh_auto']))

with open(os.path.join(OUTDIR, 'dlc_unique.tsv'), 'w', encoding='utf-8', newline='') as f:
    f.write('n\tcat\tmaxcn\tja\ten\tzh_auto\n')
    for s, u in sorted(uniq.items(), key=lambda x: (x[1]['cat'], -x[1]['n'])):
        en_best = u['en'].most_common(1)[0][0] if u['en'] else ''
        f.write('%d\t%d\t%d\t%s\t%s\t%s\n' % (u['n'], u['cat'], u['maxcn'],
                                              s.replace('\t', ' '), en_best.replace('\t', ' '),
                                              u['zh_auto'].replace('\t', ' ')))

open(os.path.join(OUTDIR, 'dlc_charset.txt'), 'w', encoding='utf-8').write(
    ''.join(sorted(avail)))
json.dump(sorted(avail), open(os.path.join(OUTDIR, 'dlc_avail_chars.json'), 'w', encoding='utf-8'),
          ensure_ascii=False)

# ---------- 6) 统计 ----------
log('')
log('== 统计 ==')
log('可翻槽位(cat0+cat1, 含日文, 已排除名字键表/纯ASCII): %d' % len(work))
log('  其中 cat0 需翻译: %d；cat1 复用主译: %d'
    % (sum(1 for r in work if r['cat'] == 0), sum(1 for r in work if r['cat'] == 1)))
log('去重后 distinct 串: %d（cat0 %d / cat1 %d）'
    % (len(uniq), sum(1 for u in uniq.values() if u['cat'] == 0),
       sum(1 for u in uniq.values() if u['cat'] == 1)))
log('（另已排除纯 ASCII 非日文串 %d 种 / %d 槽：脚本变量/文件名/坐标）'
    % (len(skipped_nonjp), sum(skipped_nonjp.values())))
log('')
log('== 逐 blob（blob: 字段数 / 可翻 / 保留 | 判定）==')
for i, nf, ntr, nk, v in per_blob:
    log('  b%-3d fields=%-4d 可翻=%-4d 保留=%-4d | %s' % (i, nf, ntr, nk, v))

open(os.path.join(OUTDIR, 'dlc_stats.txt'), 'w', encoding='utf-8').write('\n'.join(L))
print('ok')
