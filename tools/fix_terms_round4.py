# -*- coding: utf-8 -*-
"""第四轮术语修正：清理初版替换词典烘焙进译表的语义残留（Z28）。

依据：
  - 初版 replace_map.py（7179354）350 条有效替换 vs 当前 16 条；
  - 逐行以日语为主、英语为辅复核 text_v2.csv / ml_zh_fields.json / DLC。

用法：
  python tools/fix_terms_round4.py            # 预览
  python tools/fix_terms_round4.py --apply    # 备份后写回
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
DLC_P = os.path.join(paths.data("dlc"), "zh_01.tsv")
PREVIEW = paths.build("term_fix_round4_preview.tsv")

# (ja 触发子串, [(旧, 新), ...])；触发任一日文子串才应用整组替换
CSV_RULES = [
    (['のこぎりアクス'], [('铁斧', '锯斧')]),
    (['ギザギザ', 'ぎざぎざ'], [('利刃', '锯齿')]),
    (['ユニコーン'], [('灵角兽', '独角兽')]),
    (['テンガロンハット'], [('草帽', '牛仔宽帽')]),
    (['スパイクシューズ'], [('爬山鞋', '长钉鞋')]),
    (['タイガーブレード'], [('尖刺刀', '虎牙刀')]),
    (['ドリルランス'], [('尖枪', '钻头枪')]),
    (['ドリルのヤリ'], [('尖头矛', '钻头矛')]),
    (['ドリル一等兵'], [('尖头兵', '钻头兵')]),
    (['ドリル'], [('尖头', '钻头')]),
    (['ブック', 'エッチ'], [('反常之书', '工口之书')]),
    (['マッハギア'], [('马赫转盘', '马赫齿轮')]),
    (['リライト'], [('复起', '再次点火')]),
    (['ふかする', '生まれる', 'タマゴ'], [('出世', '孵化')]),
    (['みならい'], [('帮工', '学徒')]),
    (['こじいん', '孤児'], [('失亲孩子院', '孤儿院'), ('失亲孩子', '孤儿')]),
    (['殿下'], [('大人', '殿下')]),
    (['スロー'], [('情人', '斯洛'), ('斯拉乌', '斯洛')]),
    (['２倍', '2倍'], [('两份', '两倍')]),
    (['疲れ', 'つかれ'], [('困了', '累了')]),
    (['ロマン', 'ロマツク'], [('风情', '浪漫')]),
    (['きちょう', '貴重'], [('难得', '宝贵')]),
    (['せんぱい戦士'], [('长者战士', '前辈战士')]),
    (['食べる派'], [('吃法', '吃派')]),
    (['つぐなえ'], [('消你的罪', '赎罪')]),
    (['悪人というもの'], [('传说中的', '所谓的')]),
    (['ド迫力'], [('打动', '震撼')]),
    (['びっくり'], [('心里发毛', '吓一跳')]),
    (['ごきげんよう'], [('有礼', '告辞')]),
    (['アイランドウォーズ'], [('岛屿战事', '岛屿战争')]),
    (['げきアツコート'], [('防冻外套', '激热外套'), ('防冻大衣', '激热外套')]),
    (['エプロン'], [('饭单', '围裙')]),
    (['１ゴールド'], [('几块金币', '1金币')]),
]

# 指定行精确替换（避免同词在不同语境被误改）
ROW_PATCHES = {
    # 多亏：直接道谢 / 语气错误
    '5671': [('多亏多亏', '多谢多谢')],
    '36561': [('多亏你告诉我', '多谢您特意告知')],
    '42917': [('多亏帮忙', '多谢帮忙')],
    '47675': [('多亏光顾', '多谢惠顾')],
    '54947': [('多亏告知', '多谢告知')],
    '56495': [('多亏！', '太感谢了！')],
    '37042': [('多亏了魔法书', '都怪那本魔法书')],
    '33956': [('多亏您了', '谢谢您')],
    '59830': [('多亏你救了我女儿', '谢谢你救了我女儿')],
    '41440': [('多亏你', '谢谢你')],
    '39697': [('多亏相助', '多谢相助')],
    '54667': [('多亏死神魔王拉米德斯的诡计', '全因死神魔王拉米德斯的诡计')],
    # 迎战：挑戦/チャレンジ/タイムアタック
    '10790': [('发起迎战', '发起挑战')],
    '11001': [('时间迎战', '时间挑战')],
    '30568': [('想迎战极限', '想挑战极限')],
    '53553': [('迎战者', '挑战者')],
    # 难得（贵重的）
    '2327': [('难得时间', '宝贵时间')],
    '29061': [('孵化的动静', '孵化的迹象')],
    '48643': [('灵角兽', '独角兽')],
    '48704': [('灵角兽', '独角兽')],
    # しおニンジン / ソルトニンジン：盐渍胡萝卜（不误伤「红萝卜老爷」）
    '2970': [('腌红萝卜', '盐渍胡萝卜')],
    '7770': [('红萝卜', '盐渍胡萝卜')],
    '7851': [('盐渍胡萝卜', '咸胡萝卜')],
    '19882': [('红萝卜', '盐渍胡萝卜')],
    '19957': [('盐渍胡萝卜', '咸胡萝卜')],
    '22446': [('盐渍胡萝卜', '咸胡萝卜')],
    '22447': [('盐渍胡萝卜', '咸胡萝卜')],
    '22448': [('盐渍胡萝卜', '咸胡萝卜')],
    '33514': [('<红萝卜>', '<盐渍胡萝卜>')],
    '33518': [('寻找红萝卜', '寻找盐渍胡萝卜')],
    '33520': [('<红萝卜>', '<盐渍胡萝卜>')],
    '33522': [('<红萝卜>', '<盐渍胡萝卜>')],
    '33533': [('获得了红萝卜', '获得了盐渍胡萝卜')],
    '33535': [('<红萝卜>', '<盐渍胡萝卜>')],
    '33881': [('红萝卜', '盐渍胡萝卜')],
    '33882': [('红萝卜', '盐渍胡萝卜')],
    '33886': [('「红萝卜100金币', '「盐渍胡萝卜100金币')],
    '40698': [('红萝卜', '盐渍胡萝卜')],
    '40779': [('盐渍胡萝卜', '咸胡萝卜')],
    '48652': [('盐渍胡萝卜', '咸胡萝卜')],
    '48673': [('盐渍胡萝卜', '咸胡萝卜')],
    '50936': [('盐渍红萝卜', '盐渍胡萝卜')],
}

# ml_zh_fields.json：全局唯一写法
ML_RULES = [
    ('失亲孩子院', '孤儿院'),
    ('灵角兽', '独角兽'),
    ('铁斧', '锯斧'),
    ('草帽', '牛仔宽帽'),
    ('爬山鞋', '长钉鞋'),
    ('尖刺刀', '虎牙刀'),
    ('这把刀是用尖刺做的', '这把刀是用虎牙做的'),
    ('尖枪', '钻头枪'),
    ('尖头兵E-1', '钻头兵E-1'),
    ('出世', '孵化'),
    ('魔法师的帮工', '魔法师的学徒'),
    ('但太困了', '但太累了'),
    ('时间迎战', '时间挑战'),
    ('给想迎战极限的人', '给想挑战极限的人'),
    ('迎战一个超厉害的场景', '挑战一个超厉害的场景'),
    ('来迎战这些任务', '来挑战这些任务'),
    ('来迎战\n这些任务', '来挑战\n这些任务'),
    ('去迎战巨大怪物', '去挑战巨大怪物'),
    ('打动无比', '震撼无比'),
    ('多亏相助。那么', '多谢相助。那么'),
]

DLC_RULES = [
    ('多亏相救', '多谢相救'),
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
    stats = collections.Counter()
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
            stats['PROBLEM'] += 1
            continue
        if not protected_ok(zh, new):
            problems.append((r['row_id'], '占位符/标签数量变化', zh, new))
            stats['PROBLEM'] += 1
            continue
        changes.append((r['row_id'], zh, new, '+'.join(hits)))
        stats['CHANGE'] += 1
        r['zh_new'] = new
    if apply_flag and not problems:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = CSV_P + '.bak_terms4_' + ts
        shutil.copy2(CSV_P, bak)
        with io.open(CSV_P, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print('backup ->', bak)
    return changes, problems, stats


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
        bak = ML_P + '.bak_terms4_' + ts
        shutil.copy2(ML_P, bak)
        with io.open(ML_P, 'w', encoding='utf-8') as fh:
            json.dump(d2, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        print('backup ->', bak)
    return changes


def process_dlc(apply_flag):
    with io.open(DLC_P, encoding='utf-8-sig', newline='') as fh:
        text = fh.read()
    new = text
    changes = []
    for old, rep in DLC_RULES:
        if old in new:
            changes.append((old, rep, new.count(old)))
            new = new.replace(old, rep)
    if apply_flag and changes:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = DLC_P + '.bak_terms4_' + ts
        shutil.copy2(DLC_P, bak)
        with io.open(DLC_P, 'w', encoding='utf-8-sig', newline='') as fh:
            fh.write(new)
        print('backup ->', bak)
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    csv_changes, problems, stats = process_csv(args.apply)
    ml_changes = process_ml(args.apply)
    dlc_changes = process_dlc(args.apply)
    print('CSV changes:', len(csv_changes), 'problems:', len(problems))
    print('ML changes:', len(ml_changes))
    print('DLC changes:', len(dlc_changes))
    for row_id, old, new, hits in csv_changes:
        print('CSV\t%s\t%s\t=>\t%s\t[%s]' % (row_id, old, new, hits))
    for k, old, new, hits in ml_changes:
        print('ML\t%s\t%s\t=>\t%s\t[%s]' % (k, old.replace('\n', '\\n'), new.replace('\n', '\\n'), hits))
    for old, rep, n in dlc_changes:
        print('DLC\t%s -> %s x%d' % (old, rep, n))
    for p in problems:
        print('PROBLEM', p)


if __name__ == '__main__':
    main()
