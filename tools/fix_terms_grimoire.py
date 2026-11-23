# -*- coding: utf-8 -*-
"""格里莫瓦尔批次：故事/UI 显示文本音译（2026-11-23）。

规则（用户已确认）：
  · グリモワール（全称） -> 格瑞莫瓦尔
  · グリモ / Grimo（简称）-> 格瑞莫
  · 昵称 <小典> / <魔法书>（row 28447/28448）-> <小莫>
  · 武器道具「Grimoire」仍译「魔法书」：权威行 row::7402、+1/2卷变体、
    融合说明、图鉴长说明、获得提示一律不动。
  · 机制名/键一律不动：b609 off47564 pos28 为关卡/剧本标识（row 32917）；
    b931 pos36 为称号表章节名副本（row 53626/53629，构建本身保留日文）。
  · 4 条 BGM 英文曲名不动。

只改 zh_new 与 ml_zh_fields.json，不改句子结构；写回前校验槽位与占位符。

用法:
  python tools/fix_terms_grimoire.py            # 预览
  python tools/fix_terms_grimoire.py --apply    # 备份后写回
"""
import argparse
import csv
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CSV_P = paths.data('text_v2.csv')
ML_P = paths.data('ml_zh_fields.json')
ML_VIEW = os.path.join(paths.DATA_DIR, 'translator-view', '30_multiline.json')
PREVIEW = paths.build('grimoire_term_preview.tsv')

FULL = '格瑞莫瓦尔'
SHORT = '格瑞莫'
OLD = '魔法书'

# 武器道具「Grimoire」及其名称/说明/副本、获得提示
ITEM_ROWS = {
    7402, 8013, 8014, 8018,
    19510, 20184, 20185, 20189,
    40328, 40865, 41079, 41080, 41084,
    4665, 4668, 4674,
    16980, 16981,
    38317, 38318, 38319,
    34043,
}
# 机制名/键：脚本标识、称号表章节名副本、英文曲名
MECH_ROWS = {
    32917,            # b609 off47564 pos28 关卡/剧本标识「グリモワール１」
    53626, 53629,     # b931 pos36 称号表章节名副本（chaptitle 保护）
    17023, 17025, 17170, 17173,  # BGM 英文曲名
}
KEEP_ROWS = ITEM_ROWS | MECH_ROWS

# 分句半句：原文半句没有术语，译文按相邻句补出；按上下文指定形式
FULL_HALVES = {16840, 16903, 16906, 28439, 44944, 44951, 44953, 44959, 45025}
SHORT_HALVES = {44874, 45003, 59969, 59973}

# 昵称：日文 <グリモ> 的可爱叫法
NICK_ROWS = {28447: ('<小典>', '<小莫>'), 28448: ('<魔法书>', '<小莫>')}

# 多行译表中的道具图鉴说明（保持「魔法书」）
ML_ITEM_PREFIX = 'Grimoire\nFull of embarrassing youthful indiscretions'

SHORT_RE = re.compile('グリモ(?!ワール)')


def byte_len(s):
    return sum(1 if ord(ch) < 128 else 2 for ch in s)


def load_ml_caps():
    """{en整字段: cap_bytes}，来自当前校对视图；缺失时返回空。"""
    try:
        d = json.load(open(ML_VIEW, encoding='utf-8'))
        return {e['en']: (e.get('meta') or {}).get('cap_bytes')
                for e in d.get('entries', [])}
    except Exception:
        return {}


def validate(old, new, slot, max_cn, label, problems):
    if new.count('<') != old.count('<') or new.count('>') != old.count('>'):
        problems.append('%s 占位符数量变化: %r -> %r' % (label, old, new))
        return False
    if byte_len(new) > slot:
        problems.append('%s 超长 %d > %d 字节: %r' % (label, byte_len(new), slot, new))
        return False
    if len(new) > max_cn:
        problems.append('%s 超长 %d > %d 字: %r' % (label, len(new), max_cn, new))
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    with open(CSV_P, encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh))
    fields = list(rows[0].keys())

    ml = json.load(open(ML_P, encoding='utf-8'))
    caps = load_ml_caps()

    changes = []
    problems = []
    stats = {'full': 0, 'short': 0, 'halves': 0, 'nick': 0, 'ml': 0}
    hit_ids = set()

    for r in rows:
        rid = int(r['row_id'])
        ja = r['ja'] or ''
        zh = r['zh_new'] or ''
        if rid in KEEP_ROWS:
            # 道具/机制名必须继续是「魔法书」
            continue
        if rid in NICK_ROWS:
            a, b = NICK_ROWS[rid]
            if a in zh:
                new = zh.replace(a, b)
                if validate(zh, new, int(r['slot_bytes']), int(r['max_cn']),
                            'row::%d' % rid, problems):
                    changes.append((rid, r, new, 'nick'))
                    stats['nick'] += 1
            continue
        if OLD not in zh:
            continue
        if 'グリモワール' in ja:
            target, kind = FULL, 'full'
        elif SHORT_RE.search(ja):
            target, kind = SHORT, 'short'
        elif rid in FULL_HALVES:
            target, kind = FULL, 'halves'
        elif rid in SHORT_HALVES:
            target, kind = SHORT, 'halves'
        else:
            problems.append('row::%d 无法判断全称/简称: ja=%r' % (rid, ja))
            continue
        new = zh.replace(OLD, target)
        if not validate(zh, new, int(r['slot_bytes']), int(r['max_cn']),
                        'row::%d' % rid, problems):
            continue
        changes.append((rid, r, new, kind))
        hit_ids.add(rid)
        stats[kind] += 1

    # 多行译表：8 条故事文本；道具图鉴说明保持
    ml_changes = []
    for en, zh in ml.items():
        if OLD not in zh:
            continue
        if en.startswith(ML_ITEM_PREFIX):
            continue
        if 'grimoire' not in en.lower():
            problems.append('ml 条目含「魔法书」但英文无 Grimoire: %r' % en[:50])
            continue
        new = zh.replace(OLD, FULL)
        cap = caps.get(en)
        if cap and byte_len(new) > int(cap):
            problems.append('ml 超长 %d > %d: %r' % (byte_len(new), cap, en[:40]))
            continue
        ml_changes.append((en, zh, new))
        stats['ml'] += 1

    # 预期数量自检
    expect = {'full': 42, 'short': 45, 'halves': 13, 'nick': 2, 'ml': 8}
    for k, v in expect.items():
        if stats[k] != v:
            problems.append('数量异常 %s: %d != 预期 %d' % (k, stats[k], v))

    with open(PREVIEW, 'w', encoding='utf-8', newline='') as fh:
        fh.write('kind\tid\tblob\toffset\told\tnew\n')
        for rid, r, new, kind in changes:
            fh.write('%s\trow::%d\t%s\t%s\t%s\t%s\n' % (
                kind, rid, r['blob_index'], r['offset'],
                r['zh_new'].replace('\t', ' '), new.replace('\t', ' ')))
        for en, old, new in ml_changes:
            fh.write('ml\t%s\t\t\t%s\t%s\n' % (
                en.split('\n')[0][:40], old.replace('\n', ' / ').replace('\t', ' '),
                new.replace('\n', ' / ').replace('\t', ' ')))

    print('CSV changed: %d  (full %d / short %d / halves %d / nick %d)'
          % (len(changes), stats['full'], stats['short'], stats['halves'], stats['nick']))
    print('ML  changed: %d' % len(ml_changes))
    print('problems: %d' % len(problems))
    for p in problems:
        print('  [PROBLEM]', p)
    print('preview ->', PREVIEW)
    if problems:
        print('存在问题，未写回。')
        return 1
    if not args.apply:
        print('（预览模式，未写回。加 --apply 写回）')
        return 0

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    bak_csv = CSV_P + '.bak_grimoire_' + ts
    bak_ml = ML_P + '.bak_grimoire_' + ts
    shutil.copy2(CSV_P, bak_csv)
    shutil.copy2(ML_P, bak_ml)

    for rid, r, new, kind in changes:
        r['zh_new'] = new

    # CSV 原文件无 BOM，使用 \r\n 行尾
    with open(CSV_P, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    for en, old, new in ml_changes:
        ml[en] = new
    with open(ML_P, 'w', encoding='utf-8', newline='') as fh:
        fh.write(json.dumps(ml, ensure_ascii=False, indent=1) + '\n')

    print('backup ->', bak_csv)
    print('backup ->', bak_ml)
    print('written ->', CSV_P)
    print('written ->', ML_P)
    return 0


if __name__ == '__main__':
    sys.exit(main())
