# -*- coding: utf-8 -*-
"""第三轮术语统一：T-10b / T-11 / T-12 的批量落地（只改译文，不改句子结构）。

覆盖：
  - T-10b 高置信误译/漏译：船頭、超新流星、銃士、魔道士、おじさま、悪ガキ 等
  - T-11 专名统一：歌族、海岸人鱼、艾娃、斯佩尔维亚、黄金冲击、刻耳柏洛斯、
    赞特赫尔、辛多尼克斯、贝塔、红萝卜老爷 等
  - T-12 说话人标签：按 term_review 的统一/按语境决定批量归一

数据源：
  text_v2.csv（zh_new）、ml_zh_fields.json、dlc/*.tsv、dlc/*.json、extra_review.json

用法:
  python tools/fix_terms_round3.py            # 预览
  python tools/fix_terms_round3.py --apply    # 备份后写回
"""
import argparse
import collections
import copy
import csv
import datetime
import glob
import io
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CSV_P = paths.data("text_v2.csv")
ML_P = paths.data("ml_zh_fields.json")
EXTRA_P = paths.data("extra_review.json")
DLC_DIR = paths.data("dlc")
PREVIEW = paths.build("term_fix_round3_preview.tsv")

# 英文槽位只有 3/7 字节的重复行：容量不足，保留原译并登记例外
CAPACITY_EXCEPTIONS = {'31008', '31020'}

# T-10b ⑥：超土おとこ 两句被拆到相邻槽位，按日文重新对齐
ROW_PATCHES = {
    '53227': '「我要你打败<超级泥浆怪>和<超级泥浆王>',
    '53242': '「我要你打败<超级泥浆怪>和<超级泥浆王>',
    '53228': '　它们就在北边，去打倒吧！」',
    '53243': '　它们就在北边，去打倒吧！」',
}

SPEAKER = re.compile(r'^([\s\u3000]*)([^\s\u3000「」『』]{1,24})(\s*[「：:])')
ZH_LABEL = re.compile(r'^([\s\u3000「『]*)([^\s\u3000「」『』]{1,24})(\s*[「：:])')

# 少数行的日文是上一句的续行，术语不在本行；这些写法本身唯一，可全表清理
GLOBAL_CSV_REPL = [(r'大叔大人', '大叔')]


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


def sub_all(zh, rules):
    """按顺序应用 (pattern, repl)，返回 (new, hits)。"""
    new = zh
    hits = []
    for pat, rep in rules:
        n2 = re.sub(pat, rep, new)
        if n2 != new:
            hits.append(pat)
            new = n2
    return new, hits


# ---------------------------------------------------------------- 术语规则
# (ja 子串, [(正则, 替换)], 说明, 排除子串)
TERM_RULES = [
    ('船頭', [(r'船长', '船夫')], '船頭→船夫', None),
    ('歌族', [(r'歌之族', '歌族')], '歌之族→歌族', None),
    ('陸魚人シスターズ', [(r'陆地鱼人姐妹', '海岸人鱼姐妹'),
                    (r'陆鱼人姐妹', '海岸人鱼姐妹'),
                    (r'岸鱼人姐妹', '海岸人鱼姐妹'),
                    (r'海岸人鱼(?!姐妹)', '海岸人鱼姐妹')], '陸魚人シスターズ→海岸人鱼姐妹', None),
    ('陸魚人', [(r'陆地鱼人', '海岸人鱼'), (r'陆鱼人', '海岸人鱼'),
             (r'海岸人鱼姐妹', '海岸人鱼')],
     '陸魚人→海岸人鱼', 'シスターズ'),
    ('アヴァ', [(r'艾娃(?!木偶)', '艾')], '容量回退：アヴァ→艾', 'マリオネット'),
    ('スペルヴィア', [(r'斯佩尔维亚', '斯佩维')], '容量回退：スペルヴィア→斯佩维', None),
    ('ゴールドラッシュ', [(r'淘金热', '黄金冲击')], '淘金热→黄金冲击', None),
    ('ケルベロス', [(r'瑟伯勒斯', '刻耳柏洛斯')], '瑟伯勒斯→刻耳柏洛斯', None),
    ('ザントヘル', [(r'赞特地狱', '赞特赫尔')], '赞特地狱→赞特赫尔', None),
    ('シルドニクス', [(r'辛多尼斯', '辛多尼克斯')], '辛多尼斯→辛多尼克斯', None),
    ('ベータ', [(r'贝(?!塔)', '贝塔')], '贝→贝塔', None),
    ('イプシロン', [(r'伊普西隆', '埃普西隆'), (r'埃普西(?!隆)', '埃普西隆')],
     'イプシロン→埃普西隆', None),
    ('オミクロン', [(r'奥密克戎', '奥米克戎'), (r'奥米克(?!戎)', '奥米克戎')],
     'オミクロン→奥米克戎', None),
    ('ガンマ', [(r'伽马(?!玛)', '伽玛')], '伽马→伽玛', None),
    ('銃士', [(r'射手', '火枪手'), (r'(?<!火)枪士', '火枪手'), (r'(?<!火)枪手', '火枪手')],
     '銃士→火枪手', None),
    ('ウォーリア', [(r'战士(?!团)', '勇士')], 'ウォーリア→勇士', None),
    ('魔道士', [(r'巫师', '魔法师'), (r'(?<!魔)法师', '魔法师')], '魔道士→魔法师', None),
    ('おじさま', [(r'大叔大人', '大叔')], '大叔大人→大叔', None),
    ('ニンジイ', [(r'红萝卜老伯', '红萝卜老爷'), (r'红萝卜叔叔', '红萝卜老爷')],
     'ニンジイ→红萝卜老爷', None),
    ('悪ガキ', [(r'坏小子', '小鬼')], '悪ガキ→小鬼', None),
    ('アイテム', [(r'物品', '道具')], 'アイテム→道具', None),
    ('ボウガンソード', [(r'弩炮剑', '弩枪剑'), (r'弩剑(?!枪)', '弩枪剑')],
     'ボウガンソード→弩枪剑', None),
    ('ゴールドピック', [(r'黄金采掘', '黄金镐')], 'ゴールドピック→黄金镐', None),
    ('クラスチェンジ', [(r'职业变更', '转职')], 'クラスチェンジ→转职', None),
    ('エクスペリダイブ', [(r'试验潜水', '经验俯冲')], 'エクスペリダイブ→经验俯冲', None),
    ('セリフ設定', [(r'脚本设置', '对话设置')], 'セリフ設定→对话设置', None),
    ('決定', [(r'确认', '确定')], '決定→确定', None),
    ('ブーストオール', [(r'全员强化', '全面提升')], 'ブーストオール→全面提升', None),
    ('ブーストパーティ', [(r'增益队伍', '提升队伍')], 'ブーストパーティ→提升队伍', None),
    ('登場セリフ', [(r'现身脚本', '出场台词')], '登場セリフ→出场台词', None),
    ('セーブデータセレクト', [(r'选择存档数据', '选择存档栏位')],
     'セーブデータセレクト→选择存档栏位', None),
    ('名前', [(r'^玩家$', '名称')], '名前（UI 字段）→名称', None),
]

# ---------------------------------------------------------------- 说话人标签
# ja 标签 → {现有写法: 统一写法}
LABEL_RULES = {
    '主人': {'主人': '店主', '店长': '店主'},
    '女の子': {'女孩': '小女孩'},
    '店主': {},
    'よろず屋': {'店员': '小贩', '商贩': '小贩', '杂货商': '小贩',
              '商人': '小贩', '摊贩': '小贩', '杂货店': '小贩'},
    '老人': {'大叔': '老人'},
    'やくそう屋': {'草药师': '草药商', '药师': '草药商',
               '草药店': '草药商', '药草店': '草药商'},
    'こども': {'孩子': '小孩'},
    '防具屋': {'防具商': '防具匠', '军械士': '防具匠', '铠甲匠': '防具匠',
            '防具屋': '防具匠', '铠甲商': '防具匠', '防具店老板': '防具匠'},
    '武器屋': {'武器商': '武器匠', '武器店主': '武器匠', '武器店': '武器匠'},
    'チビッコ': {'矮子': '小不点', '男孩': '小不点'},
    '青年': {'男人': '青年', '年轻人': '青年'},
    'オヤジ': {'老人': '大叔'},
    'あるじ': {'店主': '老板'},
    '装備屋': {'装备商': '装备店员', '装备商人': '装备店员', '装备店': '装备店员'},
    'ゾウチクン': {'索西': '卓奇', '佐智君': '卓奇'},
    '女学生': {'女孩': '女学生', '学生': '女学生'},
    '若者': {'青年': '年轻人'},
    '陸魚人': {'陆地鱼人': '海岸人鱼', '陆鱼人': '海岸人鱼', '海岸人鱼姐妹': '海岸人鱼'},
    'ちびっこ': {'矮子': '小不点', '矮个子': '小不点'},
    'テント': {'摊贩': '帐篷', '腾': '帐篷'},
    '少年': {'年轻人': '少年', '男孩': '少年'},
    '盾屋': {'铸盾匠': '盾匠'},
    'こども店長': {'年轻店主': '小店长', '小店主': '小店长'},
    'ジイ様': {'爷爷': '老爷爷'},
    'あやしい男': {'可疑的人': '可疑男子'},
    'バア様': {'婆婆': '老婆婆'},
    '店長': {'店主': '店长'},
    '陸魚人シスターズ': {'陆地鱼人姐妹': '海岸人鱼姐妹', '陆鱼人姐妹': '海岸人鱼姐妹',
                  '海岸人鱼': '海岸人鱼姐妹'},
    '魔族の子': {'魔族之子': '魔族小孩'},
    'おばちゃん': {'女人': '老婆婆', '大婶': '老婆婆'},
    'ははおや': {'妈妈': '母亲'},
    'オヴァちゃん': {'奥瓦莉亚': '奥瓦利亚', '欧维利亚': '奥瓦利亚'},
    'やくそうガール': {'草药小姐': '草药女孩'},
    'やくそう少女': {'草药小姐': '草药女孩'},
    'スロー': {'斯拉乌': '斯洛'},
    'ニンジイ': {'红萝卜老伯': '红萝卜老爷'},
    'おさげの女': {'辫子女': '辫子女孩'},
    'おじいさん': {'大叔': '老人', '老爷爷': '老人'},
    'カジノジジイ': {'赌场老爷爷': '赌场老头'},
    'ジジ': {'大叔': '老头'},
    '使用人': {'佣人': '助理'},
    '妖しい女': {'可疑的女人': '可疑女人'},
    '店番村長': {'村长': '店长村长'},
    '魔族の女': {'魔族女子': '女魔族'},
    'リィナの父': {'莉娜之父': '莉娜的爸爸'},
    '魔族オヤジ': {'魔族老头': '魔族大叔'},
    '男の子': {'男孩': '小男孩'},
    'やくそう売り': {'草药贩子': '药草商人', '店主': '药草商人', '草药贩': '药草商人'},
    'カップル男': {'约会男': '男友'},
    'おんじい': {'大叔': '老人'},
    '城パーツ屋': {'城堡部件店老板': '城堡零件商', '城堡部件商': '城堡零件商'},
    '雷オヤジ': {'雷电人': '闪电大叔'},
    'おんばあ': {'大婶': '老婆婆'},
    'ユウジャ': {'勇者': '羽佳'},
    '獣人ムスメ': {'兽人妹': '兽人少女'},
    '男性': {'男性': '男人'},
    '魔族の男': {'魔族男': '魔族男子'},
    'さすらいミュージシャン': {'游荡乐手': '游荡乐师'},
    'まじないし': {'咒术师': '附魔师'},
    'カップル女': {'约会女': '女友'},
    'ハウスマン': {'管家': '男仆'},
    '山男': {'山人': '山男'},
    '村長の娘': {'村长的女儿': '村长之女'},
    'せんぱい戦士': {'长者战士': '前辈战士'},
    'たんけんか': {'冒险家': '冒险者'},
    'どうくつおじさん': {'洞穴翁': '洞穴大叔'},
    'どうくつおばさん': {'洞穴婆婆': '洞穴大妈', '洞穴老婆婆': '洞穴大妈'},
    'よろず屋少年': {'少年商贩': '少年货郎'},
    'セレブ女': {'名流女': '名媛'},
    'ニイちゃん': {'男人': '小哥'},
    'バイク屋': {'骑车佬': '机车店主'},
    'モグラ屋': {'店员': '鼹鼠店员'},
    '天使あるじ': {'天使': '天使老板'},
    '村ムスメ': {'村姑': '村花'},
    '火の獣人': {'火兽人': '火之兽人'},
    '魔族っ子': {'魔族小孩': '魔族小子'},
    'こぶん': {'爪牙': '跟班', '小弟': '跟班'},
    'ぼうや': {'小孩': '男孩'},
    'よろず屋魔族': {'魔族商贩': '魔族小贩'},
    'ニコニコさん': {'含笑女孩': '笑眯眯女人', '含笑男人': '笑眯眯女人'},
    'ポリオ': {'波利-O': '波利奥'},
    '家の人': {'屋里的人': '家里人'},
    '女': {'女': '女人'},
}

# ml_zh_fields.json：按英文说话人标签统一
ML_LABEL = {
    'Armorer': {'防具商': '防具匠', '铠甲匠': '防具匠', '军械士': '防具匠'},
    'Herbalist': {'草药师': '草药商'},
    'Young Owner': {'小店主': '小店长', '年轻店主': '小店长'},
    'Grandma': {'婆婆': '老婆婆'},
    'Shorty': {'矮子': '小不点'},
    'Equipment Clerk': {'装备商': '装备店员'},
    'Tent': {'摊贩': '帐篷'},
    'Student': {'学者': '学生'},
    'Casino Gramps': {'赌场老爷爷': '赌场老头'},
    'Suspicious Woman': {'可疑的女人': '可疑女人'},
    'Ovalia': {'欧维利亚': '奥瓦利亚', '奥瓦莉亚': '奥瓦利亚'},
    'Young Man': {'少年': '年轻人'},
    'Clerk-Chief': {'村长': '店长村长'},
    'Girl': {'女孩': '小女孩', '女人': '小女孩'},
    'Mother': {'妈妈': '母亲'},
}


def label_fix(zh, mapping, en=''):
    """只替换句首说话人标签（允许前导引号）。"""
    m = ZH_LABEL.match(zh)
    if not m:
        return zh, None
    label = m.group(2)
    key = label.rstrip('：:').strip()
    new = None
    if en.startswith('Weapon Store Owner'):
        new = '武器店老板'
    elif en.startswith('Weaponsmith'):
        new = '武器匠'
    elif key in mapping:
        new = mapping[key]
    if not new or new == label:
        return zh, None
    suffix = '：' if label.endswith('：') else (':' if label.endswith(':') else '')
    return zh[:m.start(2)] + new + suffix + zh[m.end(2):], key


def term_fix(ja, zh):
    new = zh
    hits = []
    for ja_sub, rules, note, exclude in TERM_RULES:
        if ja_sub not in ja:
            continue
        if exclude and exclude in ja:
            continue
        n2, h = sub_all(new, rules)
        if h:
            new = n2
            hits.append(note)
    return new, hits


# ---------------------------------------------------------------- 数据源处理

def process_csv(argv):
    with io.open(CSV_P, encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)
    changes, problems = [], []
    stats = collections.Counter()
    for r in rows:
        ja = r.get('ja') or ''
        zh = r.get('zh_new') or ''
        if not zh:
            continue
        new, hits = term_fix(ja, zh)
        n2, gh = sub_all(new, GLOBAL_CSV_REPL)
        if gh:
            new = n2
            hits.append('global')
        m = SPEAKER.match(ja)
        if m:
            sj = m.group(2).strip().rstrip('：:')
            rule = LABEL_RULES.get(sj)
            if rule:
                new2, hit = label_fix(new, rule, r.get('en') or '')
                if hit:
                    new = new2
                    hits.append('label:' + sj)
        if r['row_id'] in ROW_PATCHES:
            new = ROW_PATCHES[r['row_id']]
            hits.append('row_patch')
        if new == zh:
            continue
        slot = int(r['slot_bytes'])
        if byte_len(new) > slot:
            if r['row_id'] in CAPACITY_EXCEPTIONS:
                stats['EXCEPTION'] += 1
                continue
            problems.append((r['row_id'], '超长 %d > %d' % (byte_len(new), slot), zh, new))
            stats['PROBLEM'] += 1
            continue
        if not protected_ok(zh, new):
            problems.append((r['row_id'], '占位符/标签数量变化', zh, new))
            stats['PROBLEM'] += 1
            continue
        changes.append(('csv', r['row_id'], zh, new, '+'.join(hits)))
        stats['+'.join(hits)] += 1
        r['zh_new'] = new
    if argv.apply and not problems:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = CSV_P + '.bak_terms3_' + ts
        shutil.copy2(CSV_P, bak)
        with io.open(CSV_P, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print('backup ->', bak)
    return changes, problems, stats


def process_ml(argv):
    with io.open(ML_P, encoding='utf-8') as fh:
        d = json.load(fh)
    d2 = copy.deepcopy(d)
    changes = []
    for k, v in d.items():
        if not isinstance(v, str) or not v:
            continue
        new, hits = v, []
        kl = k.lower()
        if 'bowgun sword' in kl:
            n2, h = sub_all(new, [(r'弩炮剑', '弩枪剑'), (r'弩剑(?!枪)', '弩枪剑')])
            if h:
                new, _ = n2, hits.append('弩枪剑')
        if kl.startswith('ava:'):
            n2, h = sub_all(new, [(r'艾娃', '艾')])
            if h:
                new, _ = n2, hits.append('艾')
        if 'cerberus' in kl:
            n2, h = sub_all(new, [(r'瑟伯勒斯', '刻耳柏洛斯')])
            if h:
                new, _ = n2, hits.append('刻耳柏洛斯')
        if 'spelvia' in kl:
            n2, h = sub_all(new, [(r'斯佩尔维亚', '斯佩维')])
            if h:
                new, _ = n2, hits.append('斯佩维')
        if 'shore merman' in kl:
            n2, h = sub_all(new, [(r'陆鱼人', '海岸人鱼')])
            if h:
                new, _ = n2, hits.append('海岸人鱼')
        if 'carroty old man' in kl:
            n2, h = sub_all(new, [(r'红萝卜老伯', '红萝卜老爷')])
            if h:
                new, _ = n2, hits.append('红萝卜老爷')
        if '<- item>' in kl:
            n2, h = sub_all(new, [(r'物品', '道具')])
            if h:
                new, _ = n2, hits.append('道具')
        if 'mage' in kl or '法师放后面' in new:
            n2, h = sub_all(new, [(r'(?<!魔)法师', '魔法师')])
            if h:
                new, _ = n2, hits.append('魔法师')
        if 'class change' in kl:
            n2, h = sub_all(new, [(r'职业变更', '转职')])
            if h:
                new, _ = n2, hits.append('转职')
        # 全局唯一写法
        for pat, rep, note in (
                (r'大叔大人', '大叔', '大叔'),
                (r'歌之族', '歌族', '歌族'),
                (r'淘金热', '黄金冲击', '黄金冲击'),
                (r'赞特地狱', '赞特赫尔', '赞特赫尔'),
                (r'辛多尼斯', '辛多尼克斯', '辛多尼克斯'),
                (r'陆地鱼人姐妹', '海岸人鱼姐妹', '海岸人鱼姐妹'),
                (r'陆鱼人姐妹', '海岸人鱼姐妹', '海岸人鱼姐妹'),
                (r'陆地鱼人', '海岸人鱼', '海岸人鱼'),
                (r'弩炮剑', '弩枪剑', '弩枪剑'),
                (r'实验潜水', '经验俯冲', '经验俯冲'),
        ):
            if not note:
                continue
            n2, h = sub_all(new, [(pat, rep)])
            if h:
                new, _ = n2, hits.append(note)
        m = re.match(r'^([^:：\n]{1,40})[:：]', k)
        if m:
            en = m.group(1).strip()
            rule = ML_LABEL.get(en)
            if rule:
                new2, hit = label_fix(new, rule, en)
                if hit:
                    new = new2
                    hits.append('label:' + en)
        if new != v:
            changes.append(('ml', k[:60], v, new, '+'.join(hits)))
            d2[k] = new
    if argv.apply:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = ML_P + '.bak_terms3_' + ts
        shutil.copy2(ML_P, bak)
        with io.open(ML_P, 'w', encoding='utf-8') as fh:
            json.dump(d2, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        print('backup ->', bak)
    return changes


def process_dlc(argv):
    changes = []
    for p in sorted(glob.glob(os.path.join(DLC_DIR, '*.tsv'))):
        with io.open(p, encoding='utf-8-sig', newline='') as fh:
            text = fh.read()
        lines = text.split('\n')
        out = []
        dirty = False
        for line in lines:
            if '\t' not in line:
                out.append(line)
                continue
            parts = line.split('\t')
            ja, zh = parts[0], parts[1]
            new, hits = term_fix(ja, zh)
            m = SPEAKER.match(ja)
            if m:
                sj = m.group(2).strip().rstrip('：:')
                rule = LABEL_RULES.get(sj)
                if rule:
                    new2, hit = label_fix(new, rule)
                    if hit:
                        new = new2
                        hits.append('label:' + sj)
            if new != zh:
                parts[1] = new
                line = '\t'.join(parts)
                changes.append((os.path.basename(p), ja[:50], zh, new, '+'.join(hits)))
                dirty = True
            out.append(line)
        if argv.apply and dirty:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy2(p, p + '.bak_terms3_' + ts)
            with io.open(p, 'w', encoding='utf-8-sig', newline='') as fh:
                fh.write('\n'.join(out))
    for p in sorted(glob.glob(os.path.join(DLC_DIR, '*.json'))):
        with io.open(p, encoding='utf-8') as fh:
            d = json.load(fh)
        d2 = copy.deepcopy(d)
        dirty = False
        for k, v in d.items():
            if not isinstance(v, str):
                continue
            new, hits = term_fix(k, v)
            m = SPEAKER.match(k)
            if m:
                sj = m.group(2).strip().rstrip('：:')
                rule = LABEL_RULES.get(sj)
                if rule:
                    new2, hit = label_fix(new, rule)
                    if hit:
                        new = new2
                        hits.append('label:' + sj)
            if new != v:
                d2[k] = new
                changes.append((os.path.basename(p), k[:50], v, new, '+'.join(hits)))
                dirty = True
        if argv.apply and dirty:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy2(p, p + '.bak_terms3_' + ts)
            indent = 0 if text_indent_zero(p) else 1
            with io.open(p, 'w', encoding='utf-8') as fh:
                json.dump(d2, fh, ensure_ascii=False, indent=indent)
                fh.write('\n')
    return changes


def text_indent_zero(p):
    with io.open(p, encoding='utf-8') as fh:
        head = fh.read(40)
    return not head.startswith('{\n ')


EXTRA_PATCH = {
    '417:206540': '超新流星',
    '954:3560': '大叔',
}


def process_extra(argv):
    with io.open(EXTRA_P, encoding='utf-8') as fh:
        d = json.load(fh)
    changes = []
    for k, new in EXTRA_PATCH.items():
        if k not in d:
            continue
        old = d[k]
        if new != old:
            d[k] = new
            changes.append(('extra', k, old, new, 'extra_patch'))
    if argv.apply and changes:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        bak = EXTRA_P + '.bak_terms3_' + ts
        shutil.copy2(EXTRA_P, bak)
        with io.open(EXTRA_P, 'w', encoding='utf-8') as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        print('backup ->', bak)
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    csv_changes, problems, stats = process_csv(args)
    ml_changes = process_ml(args)
    dlc_changes = process_dlc(args)
    extra_changes = process_extra(args)

    with io.open(PREVIEW, 'w', encoding='utf-8', newline='') as fh:
        fh.write('source\tkey\told\tnew\thit\n')
        for src, key, old, new, hit in (csv_changes + ml_changes
                                        + dlc_changes + extra_changes):
            fh.write('%s\t%s\t%s\t%s\t%s\n' % (
                src, key.replace('\t', ' ').replace('\r', '').replace('\n', '\\n'),
                old.replace('\t', ' ').replace('\r', '').replace('\n', '\\n'),
                new.replace('\t', ' ').replace('\r', '').replace('\n', '\\n'), hit))

    print('csv changes: %d  ml: %d  dlc: %d  extra: %d  problems: %d' % (
        len(csv_changes), len(ml_changes), len(dlc_changes),
        len(extra_changes), len(problems)))
    for k in sorted(stats, key=lambda x: -stats[x]):
        print('  %-40s %d' % (k, stats[k]))
    for p in problems:
        print('  [PROBLEM] %s %s\n    old=%r\n    new=%r' % p)
    print('preview ->', PREVIEW)
    if problems:
        print('有问题的条目未写入；请先处理。')
        return 1
    if not args.apply:
        print('（预览模式，未写回。加 --apply 写回）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
