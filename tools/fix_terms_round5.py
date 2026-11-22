# -*- coding: utf-8 -*-
"""第五轮术语修正：继续清理初版替换词典烘焙进译表的语义残留（Z29）。

依据：7179354 版 replace_map.py（350 条有效 REPL）与当前 16 条；
逐行以日语为主、英语为辅复核 text_v2.csv / ml_zh_fields.json / DLC。

用法：
  python tools/fix_terms_round5.py            # 预览
  python tools/fix_terms_round5.py --apply    # 备份后写回
"""
import argparse
import collections
import csv
import datetime
import io
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CSV_P = paths.data("text_v2.csv")
ML_P = paths.data("ml_zh_fields.json")
PREVIEW = paths.build("term_fix_round5_preview.tsv")

# (ja 触发子串, [(旧, 新), ...])；触发任一日文子串才应用整组替换
CSV_RULES = [
    (['キレツ', '地割れ'], [('破口', '裂缝')]),
    (['にょいぼう'], [('王杖', '如意棒')]),
    (['キョウダイ'], [('手足', '兄弟')]),
    (['つりざお'], [('钓具', '钓竿')]),
    (['シマシマ', 'ボーダー'], [('格子', '条纹')]),
    (['エグゼキュート'], [('照办者', '执行者')]),
    (['任務'], [('照办机密任务', '执行机密任务'),
              ('照办绝密任务', '执行绝密任务'),
              ('照办任务', '执行任务')]),
    (['キレあじ'], [('切碎效果', '锋利度')]),
    (['お礼', 'ほうび', 'ほうしゅう', 'バウンティ', 'ハンティング'],
     [('奖金', '奖励')]),
    (['あったかニット', 'こころがホット'],
     [('热乎毛线帽', '保暖毛线帽'), ('热乎内心', '温暖内心')]),
    (['大罪人'], [('大恶人', '大罪人')]),
    (['うらない'], [('预言', '占卜')]),
    (['襲来', '襲ってきた'], [('杀到', '袭来')]),
    (['身代わり大作戦'], [('分身大作战', '替身大作战')]),
    (['気配'], [('有动静显示', '有迹象显示')]),
    (['小娘'], [('小家伙', '小丫头')]),
]

# 指定行精确替换（避免同词在不同语境被误改）
ROW_PATCHES = {
    # 巴望（楽しみ/期待）
    '5396': [('巴望', '期待')], '25030': [('巴望', '期待')],
    '25637': [('巴望', '期待')], '32636': [('巴望', '期待')],
    '36139': [('巴望', '期待')], '36212': [('巴望', '期待')],
    '37298': [('巴望', '期待')], '41727': [('巴望', '期待')],
    '44823': [('巴望', '期待')], '46671': [('巴望', '期待')],
    '52603': [('巴望', '期待')], '52604': [('巴望', '期待')],
    '52664': [('巴望', '期待')], '56649': [('巴望', '期待')],
    '60299': [('巴望', '期待')],
    # 得令（かしこまりました/はっ/ラジャー/リョウカイ）
    '3207': [('得令', '遵命')], '3243': [('得令', '遵命')],
    '9738': [('得令', '遵命')], '9745': [('得令', '遵命')],
    '13692': [('得令', '遵命')], '18676': [('得令', '遵命')],
    '18964': [('得令', '遵命')], '20870': [('得令', '遵命')],
    '20875': [('得令', '遵命')], '44946': [('得令', '遵命')],
    '24760': [('得令', '收到')], '30146': [('得令', '收到')],
    '54818': [('得令', '收到')],
    # 且慢
    '2927': [('且慢', '稍等')],
    '28626': [('且慢', '稍等')],
    '49403': [('且慢', '稍等')],
    # 大作（魔王のしわざ）
    '38792': [('魔王的大作', '魔王的杰作')],
    '54597': [('魔王的大作', '魔王的杰作')],
    # 拿走了（盗まれた）
    '14782': [('拿走了', '偷走了')],
    '22592': [('拿走了', '偷走了')],
    '22594': [('拿走了', '偷走了')],
    '55155': [('拿走了', '偷走了')],
    # 收场（結果オーライ）
    '56542': [('收场好就万事好', '结果好就万事好')],
    # 看准（determine）
    '958': [('看准', '判断')],
    # 门限（curfew）
    '30708': [('赶不上关门', '赶不上门禁')],
    '30714': [('赶不上关门', '赶不上门禁')],
    '30720': [('赶不上关门', '赶不上门禁')],
    # 足がすくんで
    '2321': [('我怕得动弹不得', '我吓得动弹不得')],
    # 奖金：赏金语境（全局规则先把奖金→奖励）
    '10503': [('奖励', '赏金')],
    '53511': [('奖励猎人', '赏金猎人')],
    '57441': [('奖金', '奖励')],
    '57463': [('奖金', '奖励')],
    # 日文未含触发词、但同属同一批语义残留
    '25388': [('下次奖金', '称号数')],
    '29226': [('有动静显示', '有迹象显示')],
    '29277': [('有动静显示', '有迹象显示')],
    '29345': [('有动静显示', '有迹象显示')],
    '29396': [('有动静显示', '有迹象显示')],
    '35424': [('破口', '裂缝')],
    '32160': [('钓具村', '钓竿村')],
    '36199': [('照办任务', '执行任务')],
    '45716': [('手足', '兄弟')],
    '56133': [('预言', '占卜')],
    '56147': [('预言', '占卜')],
    '56941': [('王杖', '如意棒')],
}

ML_RULES = [
    ('魔王的大作', '魔王的杰作'),
    ('破口', '裂缝'),
    ('王杖', '如意棒'),
    ('钓具', '钓竿'),
    ('热乎毛线帽', '保暖毛线帽'),
    ('拿走了', '偷走了'),
    ('预言天使', '占卜天使'),
    ('抓到他就有奖金', '抓到他就有赏金'),
    ('换奖金', '换赏金'),
    ('<陆地事件-奖金>', '<陆地事件-奖励>'),
    ('及其奖金', '及其奖励'),
    ('<对话事件-奖金>', '<对话事件-奖励>'),
    ('设置奖金', '设置奖励'),
    ('奖金包括', '奖励包括'),
    ('作为奖金', '作为奖励'),
]


def byte_len(s):
    return sum(1 if ord(ch) < 0x80 else 2 for ch in s)


def protected_ok(old, new):
    for ch in '<>{}':
        if old.count(ch) != new.count(ch):
            return False
    for tok in ('%s', '%d', '%1$s', '%2$s'):
        if old.count(tok) != new.count(tok):
            return False
    return True


def apply_rules(ja, zh):
    new = zh
    hits = []
    for triggers, rules in CSV_RULES:
        if not any(t in ja for t in triggers):
            continue
        for old, rep in rules:
            if old in new:
                new = new.replace(old, rep)
                hits.append('%s->%s' % (old, rep))
    return new, hits


def process_csv(apply_flag):
    with io.open(CSV_P, encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)
    changes, problems = [], []
    for r in rows:
        zh = r.get('zh_new') or ''
        if not zh:
            continue
        new, hits = apply_rules(r.get('ja') or '', zh)
        for old, rep in ROW_PATCHES.get(r['row_id'], []):
            if old in new:
                new = new.replace(old, rep)
                hits.append('%s->%s' % (old, rep))
        if new == zh:
            continue
        slot = int(r['slot_bytes'])
        if byte_len(new) > slot:
            problems.append((r['row_id'], '超长 %d > %d' % (byte_len(new), slot), zh, new))
            continue
        if not protected_ok(zh, new):
            problems.append((r['row_id'], '占位符/标签数量变化', zh, new))
            continue
        changes.append((r['row_id'], zh, new, '+'.join(hits)))
        r['zh_new'] = new
    if apply_flag and not problems:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = CSV_P + '.bak_terms5_' + ts
        shutil.copy2(CSV_P, bak)
        with io.open(CSV_P, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print('backup ->', bak)
    return changes, problems


def process_ml(apply_flag):
    with io.open(ML_P, encoding='utf-8') as fh:
        d = json.load(fh)
    d2 = dict(d)
    changes = []
    for k, v in d.items():
        if not isinstance(v, str) or not v:
            continue
        new = v
        hits = []
        for old, rep in ML_RULES:
            if old in new:
                new = new.replace(old, rep)
                hits.append('%s->%s' % (old, rep))
        if new != v:
            changes.append((k[:70], v, new, '+'.join(hits)))
            d2[k] = new
    if apply_flag:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = ML_P + '.bak_terms5_' + ts
        shutil.copy2(ML_P, bak)
        with io.open(ML_P, 'w', encoding='utf-8') as fh:
            json.dump(d2, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        print('backup ->', bak)
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    csv_changes, problems = process_csv(args.apply)
    ml_changes = process_ml(args.apply)
    print('CSV changes:', len(csv_changes), 'problems:', len(problems))
    print('ML changes:', len(ml_changes))
    for row_id, old, new, hits in csv_changes:
        print('CSV\t%s\t%s\t=>\t%s\t[%s]' % (row_id, old, new, hits))
    for k, old, new, hits in ml_changes:
        print('ML\t%s\t%s\t=>\t%s\t[%s]' % (k, old.replace('\n', '\\n'), new.replace('\n', '\\n'), hits))
    for p in problems:
        print('PROBLEM', p)


if __name__ == '__main__':
    main()
