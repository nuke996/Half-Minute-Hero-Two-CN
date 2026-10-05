# -*- coding: utf-8 -*-
"""v2.33 装机后效果统计（上屏口径：display_text + apply_repl + ml 优先）。"""
import sys, os, csv, json

import paths
W = paths.DATA_DIR
sys.path.insert(0, W); os.chdir(W)
import build_cn as B

rows = list(csv.DictReader(open(paths.data('text_v2.csv'), encoding='utf-8')))
md = json.load(open(r'ml_zh_fields.json', encoding='utf-8'))

NEW = ['治疗', '蜘蛛', '骷髅', '玻璃', '咖喱', '牺牲', '彩虹', '僵尸', '吾', '瞧', '编辑', '隧道']
OLD = ['我主意', '具有', '白骨', '水晶', '百足', '八脚怪', '爬虫', '活死人', '调理', '叫阵']
ART = ['魔窟乙女', '泥沼引擎', '白骨骨', '水晶鞋', '药师龙', '魔窟魔女']

def texts():
    for r in rows:
        yield B.apply_repl(r.get('zh_new') or r.get('zh_3dm') or '')
    for v in md.values():
        yield B.apply_repl(v)

cnt_new = {k: 0 for k in NEW}
cnt_old = {k: 0 for k in OLD}
cnt_art = {k: 0 for k in ART}
art_ex = {}
for t in texts():
    for k in NEW:
        cnt_new[k] += t.count(k)
    for k in OLD:
        cnt_old[k] += t.count(k)
    for k in ART:
        c = t.count(k)
        if c:
            cnt_art[k] += c
            art_ex.setdefault(k, t[:50])

out = ['== v2.33 上屏口径统计 ==', '']
out.append('-- 恢复显示的原词（应>0）--')
for k in NEW:
    out.append('%s: %d' % (k, cnt_new[k]))
out.append('')
out.append('-- 旧替换词残留（应明显下降或归零）--')
for k in OLD:
    out.append('%s: %d' % (k, cnt_old[k]))
out.append('')
out.append('-- 连带/边界确认 --')
for k in ART:
    ex = ('  例: ' + art_ex[k]) if art_ex.get(k) else ''
    out.append('%s: %d%s' % (k, cnt_art[k], ex))

open(paths.build('_v233_check.txt'), 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
