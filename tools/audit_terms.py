# -*- coding: utf-8 -*-
"""术语一致性 / 疑似误译审计（只读译文，不修改任何译表）。

扫描范围：
  locales/zh-CN/translator-view/*.json（主线 UI/对话/多行/额外/视频）
  locales/zh-CN/translator-view/40_dlc01.json（DLC01）
  locales/zh-CN/text_v2.csv（补足未导出的机制/名字槽）

检查项：
  A. 权威术语（术语表 §1–§10、已应用的专名清单、旧专名核对表）在译文中的写法
  B. 名表内部同一日文名出现多种中文
  C. 自动发现同一日文术语的多种中文写法（共现 n-gram 聚类）
  D. 缩写/别名：长词与其前缀/后缀简称的中文是否互相矛盾
  E. 职衔/身份词是否在中文里体现（副隊長→二当家 一类）
  F. 专名修饰语丢失（超/四天/元/真/王様/量産型/G 编号等）
  G. 说话人标签写法不统一

输出：
  locales/zh-CN/proofread/term_audit_suspects_<date>.tsv
  locales/zh-CN/proofread/term_audit_variants_<date>.tsv
  locales/zh-CN/proofread/speaker_label_variants_<date>.tsv

用法：
  python tools/audit_terms.py --date 20261121
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOC = os.path.join(ROOT, 'locales', 'zh-CN')
VIEW = os.path.join(LOC, 'translator-view')
PROOF = os.path.join(LOC, 'proofread')
CSV_P = os.path.join(LOC, 'text_v2.csv')
GLOSSARY = os.path.join(LOC, '术语表.md')

KATA_RE = re.compile(r'[ァ-ヺ][ァ-ヺー・\d]*')
KANJI_RUN = re.compile(r'[一-龥々]+')
CJK_RE = re.compile(r'[\u3400-\u9fff]')
ASCII_TOKEN = re.compile(r'[A-Za-z][A-Za-z0-9]*|\d+[A-Za-z]*')
PUNCT = set('。、！？!?…「」『』（）()【】〈〉《》・：:；;，,～~—―-「」')
PARTICLES = set('はがをにでとへもやの')

# 职衔/身份：日文 -> 中文中应体现的写法（任一即可）
ROLE_ALLOWED = {
    '副隊長': ['副队长'],
    '隊長': ['队长'],
    '兵長': ['兵长'],
    '大将': ['大将'],
    '中将': ['中将'],
    '少佐': ['少佐'],
    '大佐': ['大佐'],
    '王女': ['公主'],
    '女王': ['女王'],
    '王子': ['王子'],
    '王様': ['王'],
    '皇帝': ['皇帝'],
    '女帝': ['女帝'],
    '大臣': ['大臣'],
    '宰相': ['宰相'],
    '司令官': ['司令官'],
    '船長': ['船长'],
    '村長': ['村长'],
    '店長': ['店长'],
    '所長': ['所长'],
    '賢者': ['贤者'],
    '勇者': ['勇者'],
    '魔王': ['魔王'],
    '女神': ['女神'],
    '女神さま': ['女神'],
    '神官': ['神官'],
    '僧侶': ['僧侣'],
    '騎士': ['骑士'],
    '戦士': ['战士'],
    '魔女': ['魔女'],
    '巫女': ['巫女'],
    '盗賊': ['盗贼'],
    '商人': ['商人'],
    '船乗り': ['水手'],
    '船頭': ['船夫'],
    '姐さん': ['大姐'],
    'おじさま': ['大叔大人'],
    'おじさん': ['大叔'],
    'おばさん': ['阿姨', '大妈'],
    '奥さん': ['太太', '夫人'],
    '若様': ['少爷'],
    'お嬢様': ['大小姐'],
    '師匠': ['师父'],
    '先生': ['老师', '先生'],
    '博士': ['博士'],
    '教授': ['教授'],
    '兵士': ['士兵'],
    '兵隊': ['士兵'],
    '隊員': ['队员'],
    '団長': ['团长'],
    '組長': ['组长'],
    '番長': ['番长'],
}

# 语境里经常自然省略/改写，仅作低优先提示
AMBIG_ROLES = {'先生', '戦士', '兵士', '兵隊', '隊員', '商人', '僧侶', '騎士'}

STOP_ZH = {
    '我们', '你们', '他们', '她们', '咱们', '大家', '自己', '这个', '那个', '这些', '那些',
    '这里', '那里', '哪里', '什么', '怎么', '为什么', '因为', '所以', '但是', '可是',
    '而且', '然后', '已经', '还是', '就是', '不是', '没有', '可以', '不能', '不会',
    '知道', '觉得', '现在', '时候', '地方', '东西', '家伙', '事情', '样子', '感觉',
    '一个', '一边', '一起', '一样', '一下', '一点', '这种', '那种', '这样', '那样',
    '真是', '真的', '好像', '似乎', '不过', '只有', '如果', '虽然', '当然', '原来',
    '你可以', '我可以', '他可以', '你们', '我们', '他们', '这里', '那里', '这个', '那个',
    '一起', '已经', '还没', '就是', '不是', '没有', '不会', '不能', '可能', '应该',
}

PRIORITY_ORDER = {'P1': 0, 'P2': 1, 'P3': 2}


def norm(s: str) -> str:
    s = (s or '').strip()
    # 全角 ASCII -> 半角
    s = ''.join(chr(ord(c) - 0xFEE0) if '０' <= c <= '９' or 'Ａ' <= c <= 'Ｚ' or 'ａ' <= c <= 'ｚ' else c
                for c in s)
    s = re.sub(r'<[A-Za-z][A-Za-z0-9_]*>|<\d+>|<%[sd]>|\{\d+\}|<>', '', s)
    return re.sub(r'[\s\u3000]+', '', s).rstrip('：:')


def loose(s: str) -> str:
    """去掉“的/间隔号”后再比较，允许「德川的忍者」≈「德川忍者」。"""
    return re.sub(r'[的·・]', '', norm(s))


# 术语表 §12 已登记的“刻意差异 / 短槽回退”，只作提示
KNOWN_EXCEPTIONS = {'ジェリー', 'オメガ', 'ゴールドラッシュ', 'ビヨージェリー',
                    'セクシーネイル', 'ジェリーパック', '全めくり'}


def row_term_noise(entry: dict, ja_term: str) -> bool:
    """长句里的同形词/助词句不是术语写法问题。"""
    jan = norm(entry['ja'])
    if re.search(r'[をがはにでとへも]', jan) and not re.search(r'[をがはにでとへも]', ja_term):
        return True
    en = (entry.get('en') or '').lower()
    if ja_term == 'リッチ' and 'rich' in en and 'lich' not in en:
        return True
    return False


def is_termish(ja: str, info: dict) -> bool:
    """是否值得当作“术语”做共现分析。"""
    if info.get('source') in ('glossary', 'name_todo', 'name_canon'):
        return True
    if KATA_RE.fullmatch(ja) and len(ja) >= 3:
        return True
    if ja in ROLE_ALLOWED:
        return True
    if ja.endswith(('長', '兵', '官', '王', '女', '男', '士', '師', '者', '団', '軍', '隊', '神', '魔王')):
        return len(ja) >= 2
    return False


def has_punct(s: str) -> bool:
    return any(c in PUNCT for c in s)


def is_term_like(ja: str, zh: str) -> bool:
    ja = (ja or '').strip()
    zh = (zh or '').strip()
    if not ja or not zh:
        return False
    if len(ja) > 24 or len(zh) > 24:
        return False
    if has_punct(ja) or has_punct(zh):
        return False
    if '\n' in ja or '\n' in zh:
        return False
    if not (KATA_RE.search(ja) or KANJI_RUN.search(ja)):
        return False
    # 整句/助词串（如「どうして」「ありがとう」）不作为名表项
    if len(ja) >= 4 and sum(1 for c in ja if c in PARTICLES) >= 2:
        return False
    if ja.endswith(('する', 'した', 'して', 'です', 'ます', 'だ。', 'のだ')):
        return False
    return True


# ---------------------------------------------------------------- 语料加载

def load_entries() -> list[dict]:
    entries = []
    seen_row = set()
    for p in sorted(glob.glob(os.path.join(VIEW, '*.json'))):
        base = os.path.basename(p)
        if base.startswith('60_'):
            kind = 'video'
        elif base.startswith('40_'):
            kind = 'dlc'
        elif base.startswith('30_'):
            kind = 'multiline'
        elif base.startswith('50_'):
            kind = 'extra'
        elif base.startswith('20_'):
            kind = 'dialogue'
        else:
            kind = 'ui'
        with io.open(p, encoding='utf-8') as fh:
            d = json.load(fh)
        items = d.get('entries', []) if isinstance(d, dict) else d
        for e in items:
            ja = (e.get('ja') or '').strip()
            zh = (e.get('zh') or '').strip()
            if not ja or not zh:
                continue
            eid = e.get('id') or ''
            if eid.startswith('row::'):
                seen_row.add(eid[5:])
            entries.append({
                'id': eid, 'ja': ja, 'zh': zh, 'en': (e.get('en') or '').strip(),
                'kind': kind, 'file': base,
            })

    # 补足未导出的译表行（机制名/名字槽等）
    if os.path.exists(CSV_P):
        with io.open(CSV_P, encoding='utf-8-sig', newline='') as fh:
            for r in csv.DictReader(fh):
                rid = r.get('row_id') or ''
                if rid in seen_row:
                    continue
                ja = (r.get('ja') or '').strip()
                zh = (r.get('zh_new') or '').strip()
                if not ja or not zh:
                    continue
                entries.append({
                    'id': 'row::' + rid, 'ja': ja, 'zh': zh, 'en': (r.get('en') or '').strip(),
                    'kind': 'csv', 'file': 'text_v2.csv',
                })
    return entries


# ---------------------------------------------------------------- 权威术语

def parse_known_unresolved() -> list[dict]:
    """解析术语表 §12「待确认 / 多种译名并存」。"""
    out = []
    p = GLOSSARY
    if not os.path.exists(p):
        return out
    in_sec = False
    with io.open(p, encoding='utf-8') as fh:
        for line in fh:
            s = line.strip()
            if s.startswith('## '):
                in_sec = s.startswith('## 12')
                continue
            if not in_sec or not s.startswith('|'):
                continue
            cells = [c.strip() for c in s.strip('|').split('|')]
            if len(cells) < 2 or cells[0] in ('日文', '---'):
                continue
            variants = []
            for v in re.split(r'\s*/\s*', cells[1]):
                v = re.sub(r'（[^）]*）|\([^)]*\)', '', v).strip()
                if not v or '省略' in v or '其他' in v or '×' in v:
                    continue
                if v not in variants:
                    variants.append(v)
            if len(variants) < 2:
                continue
            for jt in re.split(r'\s*/\s*', cells[0]):
                jt = jt.strip()
                if jt and _ok_term_cell(jt):
                    out.append({'ja': jt, 'variants': variants,
                                'note': cells[2] if len(cells) > 2 else ''})
    return out


def check_known_unresolved(entries, occ, known):
    """术语表已登记、但当前译文仍并存多种写法的词。"""
    suspects = []
    for k in known:
        ja = k['ja']
        rows = list(occ.get(ja, []))
        seen = {i for i, _ in rows}
        # 基础名的派生写法（アヴァ・マリオネット 等）也纳入统计
        for i, e in enumerate(entries):
            if i in seen:
                continue
            if e['ja'].startswith(ja + '・') or e['ja'].startswith(ja + '：'):
                rows.append((i, 0))
        if len(rows) < 2:
            continue
        variants = sorted(k['variants'], key=len, reverse=True)
        variants = [v for v in variants if '「' not in v and '主线' not in v and 'DLC' not in v]
        if len(variants) < 2:
            continue
        cnt = collections.Counter()
        for i, _ in rows:
            z = loose(entries[i]['zh'])
            for v in variants:
                vv = loose(v)
                if vv and (vv in z or (len(vv) >= 3 and vv[:3] in z)):
                    cnt[v] += 1
                    break
        present = [v for v in variants if cnt[v] >= 1]
        if len(present) < 2:
            continue
        pri = 'P1' if min(cnt[v] for v in present) >= 2 else 'P2'
        ex = rows[0][0]
        suspects.append({
            'priority': pri, 'category': '术语表§12已知未统一',
            'ja_term': ja, 'canonical': ' / '.join(variants),
            'observed': '；'.join(f'{v}×{cnt[v]}' for v in present),
            'alias_of': '', 'occurrences': len(rows),
            'rows': ','.join(entries[i]['id'] for i, _ in rows[:5]),
            'example_ja': entries[ex]['ja'][:80],
            'example_zh': entries[ex]['zh'][:80],
            'evidence': '术语表§12已登记；' + (k.get('note') or '')[:80],
        })
    return suspects


def parse_glossary() -> list[dict]:
    out = []
    if not os.path.exists(GLOSSARY):
        return out
    with io.open(GLOSSARY, encoding='utf-8') as fh:
        lines = fh.readlines()
    section = ''
    for line in lines:
        s = line.strip()
        if s.startswith('## '):
            section = s[3:].strip()
            continue
        if section.startswith(('12', '13')):  # 待确认/技术约束
            continue
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 2:
            continue
        ja_cell, zh_cell = cells[0], cells[1]
        if ja_cell in ('日文', '---') or set(ja_cell) <= set('-: '):
            continue
        if ja_cell.startswith('表') or '槽位' in ja_cell:
            continue
        if not ja_cell or not zh_cell:
            continue
        ja_terms = [x.strip() for x in re.split(r'\s*/\s*', ja_cell) if x.strip()]
        zh_terms = [re.sub(r'（.*?）|\(.*?\)', '', x).strip()
                    for x in re.split(r'\s*/\s*', zh_cell) if x.strip()]
        zh_terms = [x for x in zh_terms if x]
        if not zh_terms:
            continue
        for jt in ja_terms:
            # 跳过含说明的单元格
            if any(c in jt for c in '【】「」'):
                continue
            if len(jt) > 18:
                continue
            # 表里混入的短语（イベントチップや / マップをつくる）不是术语
            if re.search(r'[をはがにでとへ]', jt) or jt.endswith(('や', 'など', 'する', 'した')):
                continue
            for zt in zh_terms:
                out.append({'ja': jt, 'zh': zt, 'source': 'glossary', 'section': section})
    return out


def _ok_term_cell(ja: str) -> bool:
    if not ja or len(ja) > 18:
        return False
    if re.search(r'[ \u3000「」<>～▼★♪…]', ja):
        return False
    if re.search(r'[をはがにでとへ]', ja) or ja.endswith('や'):
        return False
    return True


def load_prior_names() -> list[dict]:
    out = []
    p = os.path.join(PROOF, 'name_consistency_todo.tsv')
    if os.path.exists(p):
        with io.open(p, encoding='utf-8-sig', newline='') as fh:
            for r in csv.DictReader(fh, delimiter='\t'):
                if (r.get('status') or '').strip() not in ('applied', '已修复'):
                    continue
                ja = (r.get('ja') or r.get('ja_name') or '').strip()
                ja = re.sub(r'<[^>]*>', '', ja).strip()
                zh = (r.get('new_zh') or '').strip()
                if ja and zh and _ok_term_cell(ja):
                    out.append({'ja': ja, 'zh': zh, 'source': 'name_todo'})
    p = os.path.join(PROOF, 'name_inconsistencies.tsv')
    if os.path.exists(p):
        with io.open(p, encoding='utf-8-sig', newline='') as fh:
            for r in csv.DictReader(fh, delimiter='\t'):
                ja = (r.get('ja_term') or '').strip()
                ja = re.sub(r'<[^>]*>', '', ja).strip()
                zh = (r.get('mechanism_name') or '').strip()
                if ja and zh and len(ja) >= 2 and _ok_term_cell(ja):
                    out.append({'ja': ja, 'zh': zh, 'source': 'name_canon'})
    return out


# ---------------------------------------------------------------- 术语扫描

def build_term_dict(entries, glossary, prior):
    terms = {}  # ja -> {'canon': set, 'source': str, 'section': str}

    def add(ja, zh, source, section=''):
        if not ja or not zh:
            return
        rank = {'glossary': 4, 'name_todo': 3, 'name_canon': 2, 'nametable': 0}
        t = terms.get(ja)
        r = rank.get(source, 0)
        if t is None:
            terms[ja] = {'canon': {zh}, 'source': source, 'section': section, '_rank': r}
            return
        if r > t['_rank']:
            t['canon'] = {zh}
            t['source'] = source
            t['_rank'] = r
        elif r == t['_rank']:
            t['canon'].add(zh)
        if section and not t['section']:
            t['section'] = section

    for g in glossary:
        add(g['ja'], g['zh'], 'glossary', g.get('section', ''))
    for g in prior:
        add(g['ja'], g['zh'], g['source'])

    # 自动名表：短、无标点的对齐对
    groups = collections.defaultdict(collections.Counter)
    for e in entries:
        if is_term_like(e['ja'], e['zh']):
            groups[e['ja']][norm(e['zh'])] += 1
    auto_pairs = {}
    for ja, cnt in groups.items():
        if len(ja) < 2:
            continue
        zh = cnt.most_common(1)[0][0]
        auto_pairs[ja] = zh
        add(ja, zh, 'nametable')
    return terms, groups, auto_pairs


def _is_kata(c: str) -> bool:
    return bool(c) and ('\u30a1' <= c <= '\u30fa' or c in 'ー・')


def _is_hira(c: str) -> bool:
    return bool(c) and ('\u3041' <= c <= '\u309f' or c == 'ー')


def _is_kanji(c: str) -> bool:
    return bool(c) and ('\u3400' <= c <= '\u9fff' or c == '々')


def boundary_ok(ja: str, pos: int, length: int, term: str) -> bool:
    """避免把术语当成更长单词的子串命中（とうふ∈せんとうふく 等）。"""
    before = ja[pos - 1] if pos > 0 else ''
    after = ja[pos + length] if pos + length < len(ja) else ''
    if term.isascii():
        return not ((before.isascii() and before.isalnum()) or
                    (after.isascii() and after.isalnum()))
    has_kata = any(_is_kata(c) for c in term)
    has_hira = any(_is_hira(c) and c != 'ー' for c in term)
    has_kanji = any(_is_kanji(c) for c in term)
    if has_kata and not has_hira and not has_kanji:
        return not (_is_kata(before) or _is_kata(after))
    if has_hira and not has_kanji:
        return not (_is_hira(before) or _is_hira(after))
    return not (_is_kanji(before) or _is_kanji(after))


def scan_occurrences(entries, terms):
    by_first = collections.defaultdict(set)
    for t in terms:
        by_first[t[0]].add(len(t))
    occ = collections.defaultdict(list)  # ja -> [(entry_idx, start)]
    for i, e in enumerate(entries):
        ja = e['ja']
        spans = []
        for pos, ch in enumerate(ja):
            for L in by_first.get(ch, ()):
                sub = ja[pos:pos + L]
                if len(sub) == L and sub in terms and boundary_ok(ja, pos, L, sub):
                    spans.append((pos, pos + L, sub))
        if not spans:
            continue
        spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        last_end = -1
        for s, t, sub in spans:
            if s < last_end:
                continue
            occ[sub].append((i, s))
            last_end = t
    return occ


# ---------------------------------------------------------------- n-gram 工具

def ngrams_zh(zh: str, lo=2, hi=8):
    z = re.sub(r'<[A-Za-z][A-Za-z0-9_]*>|<\d+>|<%[sd]>|\{\d+\}', ' ', zh)
    out = set()
    for run in CJK_RE.findall(z):
        pass
    for run in re.findall(r'[\u3400-\u9fff]+', z):
        for L in range(lo, min(hi, len(run)) + 1):
            for i in range(0, len(run) - L + 1):
                out.add(run[i:i + L])
    for tok in ASCII_TOKEN.findall(z):
        if len(tok) >= 1:
            out.add(tok)
    return out


def build_background(entries):
    df = collections.Counter()
    n = 0
    for e in entries:
        grams = ngrams_zh(e['zh'])
        if not grams:
            continue
        n += 1
        for g in grams:
            df[g] += 1
    return df, max(n, 1)


def discover_renderings(rows_zh, bg_df, bg_n, min_occ=4, topk=6):
    """同一术语出现的各行中文里，找出高覆盖、低背景的 n-gram 聚类。"""
    n = len(rows_zh)
    if n < min_occ:
        return []
    df = collections.Counter()
    rows_with = collections.defaultdict(set)
    grams_by_row = []
    for idx, zh in enumerate(rows_zh):
        grams = ngrams_zh(zh)
        grams_by_row.append(grams)
        for g in grams:
            df[g] += 1
            rows_with[g].add(idx)
    need = max(3, int(0.2 * n + 0.999))
    cands = []
    for g, c in df.items():
        if c < need:
            continue
        if g in STOP_ZH or g.isdigit():
            continue
        if len(g) < 2 or len(g) > 6:
            continue
        if len(g) == 1 and not g.isascii():
            continue
        bg = bg_df.get(g, 0) / bg_n
        ratio = c / n
        if bg >= 0.12 or bg > ratio * 0.45:
            continue
        cands.append((g, c, ratio))
    cands.sort(key=lambda x: (-x[2], -len(x[0])))
    selected = []
    selected_rows = []
    covered = set()
    for g, c, ratio in cands:
        if any(g in s or s in g for s in selected):
            continue
        new_rows = rows_with[g] - covered
        if len(new_rows) < 2 and selected:
            continue
        # 与已选写法高度重叠 => 同一写法的上下文噪音，不是竞争译名
        if any(len(rows_with[g] & sr) > 0.6 * min(len(rows_with[g]), len(sr))
               for sr in selected_rows):
            continue
        selected.append(g)
        selected_rows.append(rows_with[g])
        covered |= rows_with[g]
        if len(selected) >= topk:
            break
    return [(g, len(rows_with[g]) / n) for g in selected]


# ---------------------------------------------------------------- 检查项

def check_glossary(entries, occ, terms):
    suspects = []
    for ja, info in terms.items():
        if not info['canon'] or info['source'] not in ('glossary', 'name_todo', 'name_canon'):
            continue
        rows = occ.get(ja, [])
        if not rows:
            continue
        # 只在“术语基本占满该槽位”的行里要求规范写法；长句里的自然省略/代词
        # 交给共现检测，避免把「勇者」被省略成代词误判为不一致。
        rows = [(i, p) for i, p in rows
                if len(norm(entries[i]['ja'])) <= len(ja) + 12
                and not row_term_noise(entries[i], ja)]
        if not rows:
            continue
        sec = info.get('section', '')
        canon = sorted(info['canon'])
        canon_loose = [loose(c) for c in canon]
        agree = 0
        bad = []
        for i, _ in rows:
            z = loose(entries[i]['zh'])
            if any(c and c in z for c in canon_loose):
                agree += 1
            else:
                bad.append(i)
        if not bad:
            continue
        share = agree / len(rows)
        if share >= 0.9:
            continue
        if info['source'] == 'name_canon':
            pri = 'P2' if share < 0.5 else 'P3'
        elif ja in KNOWN_EXCEPTIONS:
            pri = 'P3'
        else:
            m = re.match(r'(\d+)', sec)
            sec_no = int(m.group(1)) if m else 99
            if sec_no <= 7 and len(rows) >= 5 and share < 0.5:
                pri = 'P1'
            else:
                pri = 'P2'
        ex = bad[:5]
        suspects.append({
            'priority': pri, 'category': '权威术语写法不符',
            'ja_term': ja, 'canonical': ' / '.join(canon),
            'observed': f'{len(bad)}/{len(rows)} 处未出现规范写法',
            'alias_of': '', 'occurrences': len(rows),
            'rows': ','.join(entries[i]['id'] for i in ex),
            'example_ja': entries[ex[0]]['ja'][:80],
            'example_zh': entries[ex[0]]['zh'][:80],
            'evidence': f'source={info["source"]}; section={sec}; 一致率={share:.0%}',
        })
    return suspects


def check_name_conflicts(groups, auto_pairs):
    suspects = []
    variants = []
    for ja, cnt in groups.items():
        if len(ja) < 2:
            continue
        variants_ = [(z, c) for z, c in cnt.items() if z]
        if len(variants_) < 2:
            continue
        total = sum(c for _, c in variants_)
        if total < 2:
            continue
        variants_.sort(key=lambda x: -x[1])
        top, topc = variants_[0]
        # 至少两个写法各出现 >=2，或总次数多且存在长写法
        strong = sum(1 for _, c in variants_ if c >= 2)
        if strong < 2 and total < 4:
            continue
        # 忽略纯数字/纯符号差异
        if all(re.fullmatch(r'[\d\W_]+', z or '') for z, _ in variants_):
            continue
        pri = 'P1' if strong >= 2 else 'P2'
        if ja in KNOWN_EXCEPTIONS:
            pri = 'P3'
        suspects.append({
            'priority': pri, 'category': '名表同词多译',
            'ja_term': ja, 'canonical': top,
            'observed': '；'.join(f'{z}×{c}' for z, c in variants_[:6]),
            'alias_of': '', 'occurrences': total,
            'rows': '', 'example_ja': ja, 'example_zh': top,
            'evidence': f'共 {len(variants_)} 种写法（{total} 处）',
        })
        for z, c in variants_:
            variants.append({
                'ja_term': ja, 'zh_variant': z, 'count': c,
                'share': f'{c / total:.0%}', 'canonical': top,
                'priority': pri, 'category': '名表同词多译',
            })
    return suspects, variants


def check_discovered(entries, occ, terms, bg_df, bg_n):
    suspects = []
    variants = []
    for ja, info in terms.items():
        rows = occ.get(ja, [])
        if len(rows) < 4 or len(ja) < 2:
            continue
        if not is_termish(ja, info):
            continue
        # 含助词/动词的短语不作为术语
        if any(c in ja for c in 'はがをにでとへもやの') and info['source'] not in (
                'glossary', 'name_todo', 'name_canon'):
            continue
        idxs = [i for i, _ in rows]
        zhs = [entries[i]['zh'] for i in idxs]
        clusters = discover_renderings(zhs, bg_df, bg_n)
        if len(clusters) < 2:
            continue
        canon = {loose(c) for c in info['canon']} if info['canon'] else set()
        # 权威译名在多数出现行里已存在 => 其余多为上下文噪音
        canon_rows = sum(1 for z in zhs if any(c and c in loose(z) for c in canon)) if canon else 0
        canon_share = canon_rows / len(rows) if canon else 0.0
        if canon and canon_share >= 0.6:
            continue
        # 候选只是规范译名的分段（砖块+男孩 = 砖块男孩）=> 不是异译
        if canon:
            seg = ''.join(g for g, _ in clusters)
            if any(seg in c or c in seg for c in canon):
                continue
        pri = 'P2'
        obs = '；'.join(f'{g}×{r:.0%}' for g, r in clusters[:5])
        ex_i = idxs[0]
        suspects.append({
            'priority': pri, 'category': '共现发现多写法',
            'ja_term': ja, 'canonical': ' / '.join(sorted(canon)) if canon else '',
            'observed': obs, 'alias_of': '', 'occurrences': len(rows),
            'rows': ','.join(entries[i]['id'] for i in idxs[:5]),
            'example_ja': entries[ex_i]['ja'][:80],
            'example_zh': entries[ex_i]['zh'][:80],
            'evidence': f'共现聚类 {len(clusters)} 种；样本 {len(rows)} 行',
        })
        for g, r in clusters:
            variants.append({
                'ja_term': ja, 'zh_variant': g, 'count': int(round(r * len(rows))),
                'share': f'{r:.0%}', 'canonical': ' / '.join(sorted(canon)) if canon else '',
                'priority': pri, 'category': '共现发现多写法',
            })
    return suspects, variants


def check_alias(entries, occ, terms, auto_pair_en, auto_pairs):
    """检测“长词 vs 它的截短简称”译法不一致。

    只认真正的截短：英文名也是同一个单词的前缀（Grimoire→Grimo），
    排除“骑士枪→骑士”“龙枪→龙”这类复合词修饰关系。
    """
    suspects = []
    for ja, info in terms.items():
        if not KATA_RE.fullmatch(ja) or len(ja) < 4:
            continue
        rows = occ.get(ja, [])
        if len(rows) < 3:
            continue
        long_en = (auto_pair_en.get(ja) or '').strip().lower()
        for L in range(3, len(ja)):
            short = ja[:L]
            if short not in terms or short == ja:
                continue
            if short in auto_pairs:      # 本身是独立词/职业/怪物，不是简称
                continue
            srows = occ.get(short, [])
            if len(srows) < 2:
                continue
            short_en = (auto_pair_en.get(short) or '').strip().lower()
            en_ok = False
            if long_en and short_en:
                first = long_en.split()[0]
                if not (first != short_en and first.startswith(short_en)):
                    continue
                en_ok = True
            long_ids = {i for i, _ in rows}
            s_alone = [i for i, _ in srows if i not in long_ids]
            if len(s_alone) < 2:
                continue
            canon_long = {norm(c) for c in info['canon']} if info['canon'] else set()
            canon_short = {norm(c) for c in terms[short]['canon']} if terms[short]['canon'] else set()
            if canon_long and canon_short and canon_long & canon_short:
                continue
            # 已登记的全称/简称互为前缀（如 格瑞莫瓦尔 / 格瑞莫）不属于异译
            if canon_long and canon_short and any(
                    l.startswith(s) or s.startswith(l)
                    for l in canon_long for s in canon_short):
                continue
            short_top = collections.Counter(norm(entries[i]['zh']) for i in s_alone).most_common(3)
            if canon_long and all(any(c and c in z for c in canon_long) for z, _ in short_top):
                continue
            short_txt = '；'.join(f'{z}×{c}' for z, c in short_top)
            pri = 'P1' if (canon_long and en_ok) else 'P2'
            suspects.append({
                'priority': pri, 'category': '缩写/别名异译',
                'ja_term': f'{ja} → {short}',
                'canonical': ' / '.join(sorted(canon_long)) if canon_long else '',
                'observed': short_txt,
                'alias_of': short, 'occurrences': len(s_alone) + len(rows),
                'rows': ','.join(entries[i]['id'] for i in s_alone[:5]),
                'example_ja': entries[s_alone[0]]['ja'][:80],
                'example_zh': entries[s_alone[0]]['zh'][:80],
                'evidence': f'简称独立出现 {len(s_alone)} 行；英文名 {long_en!r}/{short_en!r}',
            })
            break
    return suspects


def check_roles(entries, occ):
    suspects = []
    for ja, allowed in ROLE_ALLOWED.items():
        rows = occ.get(ja, [])
        if not rows:
            continue
        bad = []
        for i, _ in rows:
            z = entries[i]['zh']
            if not any(a in z for a in allowed):
                bad.append(i)
        if not bad:
            continue
        share = 1 - len(bad) / len(rows)
        if share >= 0.9:
            continue
        ex = bad[:5]
        suspects.append({
            'priority': 'P3' if ja in AMBIG_ROLES else 'P2', 'category': '职衔/身份未体现',
            'ja_term': ja, 'canonical': ' / '.join(allowed),
            'observed': f'{len(bad)}/{len(rows)} 处未出现 {allowed[0]}',
            'alias_of': '', 'occurrences': len(rows),
            'rows': ','.join(entries[i]['id'] for i in ex),
            'example_ja': entries[ex[0]]['ja'][:80],
            'example_zh': entries[ex[0]]['zh'][:80],
            'evidence': f'一致率={share:.0%}；示例 {len(ex)} 条',
        })
    return suspects


MOD_RULES = [
    ('四天', ['四天'], '四天'),
    ('超', ['超', '超级', '巨型', '巨大', '特大', '无畏', '超绝'], '超'),
    ('真', ['真'], '真'),
    ('元', ['元', '原', '前'], '元'),
    ('王様', ['王'], '王様'),
    ('量産型', ['量产'], '量産型'),
    ('試作型', ['试作'], '試作型'),
]


def check_modifiers(groups, auto_pairs):
    suspects = []
    for ja, cnt in groups.items():
        if len(ja) < 2 or len(ja) > 18:
            continue
        if any(c in ja for c in ' \u3000<>「」') or any(c in ja for c in 'はがをにでとへもやの'):
            continue
        zh = cnt.most_common(1)[0][0]
        zn = norm(zh)
        jan = norm(ja)
        miss = []
        for key, allow, label in MOD_RULES:
            if key in jan and not any(a in zn for a in allow):
                miss.append(label)
        m = re.search(r'G(\d+)', jan)
        if m and not re.search(r'G\s*' + str(int(m.group(1))), zn):
            miss.append('G' + str(int(m.group(1))))
        if miss and ja not in STOP_ZH:
            suspects.append({
                'priority': 'P2', 'category': '专名修饰语丢失',
                'ja_term': ja, 'canonical': zh,
                'observed': '缺少 ' + '、'.join(miss), 'alias_of': '',
                'occurrences': sum(cnt.values()), 'rows': '',
                'example_ja': ja, 'example_zh': zh,
                'evidence': '现有主译名未保留原文区分成分',
            })
    return suspects


SPEAKER_JA = re.compile(r'^[\s\u3000]*([^\s\u3000「」『』]{1,16})「')
SPEAKER_ZH = re.compile(r'^[\s\u3000]*([^\s\u3000「」『』]{1,16})「')


def check_speakers(entries):
    groups = collections.defaultdict(collections.Counter)
    examples = {}
    for e in entries:
        if e['kind'] not in ('dialogue', 'multiline', 'dlc'):
            continue
        mj = SPEAKER_JA.match(e['ja'])
        mz = SPEAKER_ZH.match(e['zh'])
        if not mj or not mz:
            continue
        sj = mj.group(1).strip().rstrip('：:')
        sz = mz.group(1).strip().rstrip('：:')
        if not sj or not sz:
            continue
        groups[sj][sz] += 1
        examples.setdefault((sj, sz), e['id'])
    out = []
    for sj, cnt in groups.items():
        if len(cnt) < 2:
            continue
        total = sum(cnt.values())
        # 只有一个出现 1 次的多半是笔误/标点，仍保留但降级
        strong = sum(1 for _, c in cnt.items() if c >= 2)
        pri = 'P2' if strong >= 2 else 'P3'
        top = cnt.most_common(1)[0][0]
        out.append({
            'priority': pri, 'category': '说话人标签多译',
            'ja_term': sj, 'canonical': top,
            'observed': '；'.join(f'{z}×{c}' for z, c in cnt.most_common(6)),
            'alias_of': '', 'occurrences': total, 'rows': '',
            'example_ja': sj, 'example_zh': top,
            'evidence': f'{len(cnt)} 种写法 / {total} 行',
        })
    return out


# ---------------------------------------------------------------- 输出

COLS = ['priority', 'category', 'ja_term', 'canonical', 'observed',
        'alias_of', 'occurrences', 'rows', 'example_ja', 'example_zh', 'evidence']


def write_tsv(path, rows, cols):
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter='\t', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({c: (r.get(c, '') if r.get(c) is not None else '') for c in cols})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=datetime.date.today().strftime('%Y%m%d'))
    ap.add_argument('--min-occ', type=int, default=4)
    args = ap.parse_args()

    entries = load_entries()
    glossary = parse_glossary()
    known = parse_known_unresolved()
    prior = load_prior_names()
    terms, groups, auto_pairs = build_term_dict(entries, glossary, prior)

    # 术语 -> 英文名（用于别名证据）
    pair_en = {}
    for e in entries:
        if e['en'] and is_term_like(e['ja'], e['zh']):
            pair_en.setdefault(e['ja'], e['en'])

    occ = scan_occurrences(entries, terms)
    bg_df, bg_n = build_background(entries)

    suspects = []
    variants = []
    suspects += check_glossary(entries, occ, terms)
    s, v = check_name_conflicts(groups, auto_pairs)
    suspects += s
    variants += v
    s, v = check_discovered(entries, occ, terms, bg_df, bg_n)
    suspects += s
    variants += v
    suspects += check_alias(entries, occ, terms, pair_en, auto_pairs)
    suspects += check_known_unresolved(entries, occ, known)
    suspects += check_roles(entries, occ)
    suspects += check_modifiers(groups, auto_pairs)
    suspects += check_speakers(entries)

    # 排序 + 去重
    uniq = {}
    for r in suspects:
        key = (r['category'], r['ja_term'], r['observed'])
        if key not in uniq:
            uniq[key] = r
    suspects = list(uniq.values())
    suspects.sort(key=lambda r: (PRIORITY_ORDER.get(r['priority'], 9),
                                 -r.get('occurrences', 0), r['ja_term']))

    os.makedirs(PROOF, exist_ok=True)
    p1 = os.path.join(PROOF, f'term_audit_suspects_{args.date}.tsv')
    p2 = os.path.join(PROOF, f'term_audit_variants_{args.date}.tsv')
    p3 = os.path.join(PROOF, f'speaker_label_variants_{args.date}.tsv')
    write_tsv(p1, suspects, COLS)
    write_tsv(p2, variants, ['ja_term', 'zh_variant', 'count', 'share',
                             'canonical', 'priority', 'category'])
    write_tsv(p3, [r for r in suspects if r['category'] == '说话人标签多译'], COLS)

    by_cat = collections.Counter(r['category'] for r in suspects)
    by_pri = collections.Counter(r['priority'] for r in suspects)
    print('entries:', len(entries), 'terms:', len(terms), 'occurrences:', sum(len(v) for v in occ.values()))
    print('suspects:', len(suspects), dict(sorted(by_pri.items())), dict(sorted(by_cat.items())))
    print('out:', p1)
    print('out:', p2)
    print('out:', p3)


if __name__ == '__main__':
    sys.exit(main())
