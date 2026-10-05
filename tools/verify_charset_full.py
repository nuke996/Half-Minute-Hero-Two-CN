# -*- coding: utf-8 -*-
"""v2.30 字库全量覆盖验证（v2 口径修正）：
以 build_cn.display_text（= 装机真实上屏内容，含 collide/多行/mode=2 名字保留）为准，
逐字符对照装机字库（cmap 新字形 / native 原版字形 / ASCII 直写）。
附带超集口径（CSV 全部有效译文）作参考——其中"永不上屏的备用译文"缺字不算数。
"""
import os, io, sys, csv, json

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
sys.path.insert(0, W); os.chdir(W)
OUT = paths.build('_verify_charset.txt')
L = []
def log(s=''): L.append(str(s))

import build_cn as B

rows, ents, types, end, tb, slots, chosen, cmap, st = B.build_plan()
native = st['native_set']
fz = B.load_field_zh()

log('== 字库占用 ==')
log('新字形(译表专用): %d 字 / 格上限 2847, 余量 %d' % (len(chosen), 2847 - len(chosen)))
log('原版保留字形: index 0-1247 (ASCII 公式区/假名/符号) + native CP932 直显')
log('')

def scan(pick):
    bad = {}
    n_txt = n_ch = 0
    for r in rows:
        t = B.apply_repl(pick(r))
        n_txt += 1
        for ch in t:
            n_ch += 1
            o = ord(ch)
            if o < 0x80 or ch in cmap or ch in native or ch in '\n\r\t':
                continue
            bad.setdefault(ch, [0, []])
            bad[ch][0] += 1
            if len(bad[ch][1]) < 3:
                bad[ch][1].append('row' + r['row_id'])
    return n_txt, n_ch, bad

log('== 口径 A（硬结论）：真实上屏内容 display_text ==')
n1, c1, bad1 = scan(lambda r: B.display_text(r, fz))
log('扫描: %d 行 / %d 字符' % (n1, c1))
if bad1:
    log('缺字 %d 种 / %d 处:' % (len(bad1), sum(v[0] for v in bad1.values())))
    for ch, (n, whs) in sorted(bad1.items(), key=lambda x: -x[1][0])[:30]:
        log('  %r U+%04X %d 处 例:%s' % (ch, ord(ch), n, ','.join(whs)))
else:
    log('缺字: 0 —— 上屏每个字符都有字形 ✓')

log('')
log('== 口径 B（参考）：CSV 全部有效译文（含永不上屏的备用译名）==')
n2, c2, bad2 = scan(lambda r: r.get('zh_new') or r.get('zh_3dm') or '')
log('扫描: %d 行 / %d 字符' % (n2, c2))
log('缺字: %d 种 / %d 处 %s' % (len(bad2), sum(v[0] for v in bad2.values()),
    '(均为不上屏的备用文本，无影响)' if not bad1 else '<<< 有上屏缺字，见口径 A'))
if bad2:
    for ch, (n, whs) in sorted(bad2.items(), key=lambda x: -x[1][0])[:10]:
        log('  %r U+%04X %d 处 例:%s' % (ch, ord(ch), n, ','.join(whs)))

log('')
log('== 重点字确认 ==')
for ch in ('汇', '拯', '咕', '♪'):
    log('  %r: 新字形=%s 原版字形=%s' % (ch, ch in cmap, ch in native))

log('')
log('结论: %s' % ('ALL OK — 上屏文本零缺字；缺字兜底为显示?（不闪退）'
                 if not bad1 else 'FAILED — 上屏文本存在 %d 种缺字' % len(bad1)))
open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
print('done')
