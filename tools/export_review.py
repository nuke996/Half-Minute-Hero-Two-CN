# -*- coding: utf-8 -*-
"""校对导出：把可校对的译文导出为面向译者的 JSON（locales/<locale>/translator-view/）。

输出结构：
  translator-view/
    10_ui_NN.json        单行 · UI / 菜单 / 系统消息类（按 blob 分片）
    20_dialogue_NN.json  单行 · 对话类（原文含「」引号，按 blob 分片）
    30_multiline.json    多行整字段（整段对话；显示优先走这里）
    40_dlc01.json        DLC01（时之女神宝物包）译文
    protected/           当前【受保护、不会上屏】的字符串（prot_ui_NN.json，命名与外层区分）
    dict/替换词典.json    当前生效的替换词典（字库容量不足→近义词替换）
    如何校对.txt          面向译者的说明（含 protected / 替换词典 注意事项）

每条记录布局：{id, en, ja, zh, meta}，只有 zh 可改；id 稳定（导入按 id 定位）。
受保护判定直接复用生产装机（apply_menu）的 dry_run 口径，不另写一套规则。
"""
import collections
import json
import os
import sys

import paths
import review_lib as R

TOOLS = os.path.dirname(os.path.abspath(__file__))
WORK = paths.DATA_DIR
OUT = os.path.join(WORK, 'translator-view')

sys.path.insert(0, TOOLS)
sys.path.insert(0, WORK)
os.chdir(WORK)
import build_cn as B

SHARD_MAX = 4000          # 每片目标条目数（按 blob 聚合切分）

PROTECT_NOTE = {
    'collide': '疑似“名字键”：同一原文也出现在游戏脚本/数据层，按名比对，翻译会破坏机制，故保留原文',
    'mech': '机制表整表保护（技能/职业/连携技等按内容读取的表）',
    'chaptitle': '章节名/称号名保护（按字符串索引的键）',
}
HOW_TO_EDIT = ('只修改每条记录的 "zh" 字段（id/en/ja/meta 请勿改）。保存后运行 '
               '汉化-导入校对.bat 重新写回译表并刷新 dist；运行 汉化-导出校对.bat '
               '可再次导出覆盖本文件。')


def doc(kind, note, entries):
    d = collections.OrderedDict()
    d['_kind'] = kind
    d['_note'] = note
    d['_how_to_edit'] = HOW_TO_EDIT
    d['_count'] = len(entries)
    d['entries'] = entries
    return d


def is_dialogue(r):
    t = (r.get('ja') or '') + (r.get('en') or '')
    return '「' in t or '」' in t


def shard_map(items):
    """items: [(row, reason)]。按 blob 顺序聚合分片，返回 ({blob: 片号}, 片数)。"""
    counts = collections.Counter(int(r['blob_index']) for r, _ in items)
    blobs = sorted(counts)
    idx, cur, tot, k = {}, [], 0, 1
    for b in blobs:
        if cur and tot + counts[b] > SHARD_MAX:
            for x in cur:
                idx[x] = k
            cur, tot, k = [], 0, k + 1
        cur.append(b)
        tot += counts[b]
    for x in cur:
        idx[x] = k
    return idx, k


def row_entry(r, reason=None):
    eff = r.get('zh_new') or ''
    meta = {'blob': int(r['blob_index']), 'offset': int(r['offset'])}
    if str(r.get('max_cn') or '').isdigit():
        meta['cap'] = int(r['max_cn'])
    if reason:
        meta['protected'] = reason
        meta['note'] = PROTECT_NOTE.get(reason, reason)
    return {'id': 'row::%s' % r['row_id'], 'en': r.get('en') or '',
            'ja': r.get('ja') or '', 'zh': B.apply_repl(eff), 'meta': meta}


def write_shards(prefix, cat, items, outdir, idxmap, nshards, prot=False):
    cn = 'UI/菜单/系统消息' if cat == 'ui' else '对话'
    if prot:
        kind = 'protected-single-%s' % cat
        note = ('【受保护·当前不会上屏】%s类单行文本。这些原文同时出现在游戏脚本/数据层、'
                '被按名/按键比对，翻译会破坏机制，故保留原文。你仍可修改：修改会写回译表保存，'
                '但暂不显示；详见上一级目录的《如何校对.txt》第三节。' % cn)
    else:
        kind = 'single-%s' % cat
        note = '%s类单行译文。zh 为游戏当前实际显示的文本（已含替换词典压平）。' % cn
    total = 0
    for k in range(1, nshards + 1):
        rows = [row_entry(r, reason) for r, reason in items
                if idxmap.get(int(r['blob_index'])) == k]
        if not rows:
            continue
        name = ('prot_%s_%02d.json' % (cat, k)) if prot \
            else ('%s_%s_%02d.json' % (prefix, cat, k))
        R.write_json(os.path.join(outdir, name), doc(kind, note, rows))
        total += len(rows)
    return total


def main():
    rows = R.load_rows()
    md = json.load(open(os.path.join(WORK, 'ml_zh_fields.json'), encoding='utf-8'))
    stage, missing = R.ensure_stage()

    classify, ml_meta, protected_ok = {}, {}, bool(stage)
    if stage:
        print('  原版舞台: %s' % stage)
        old = B.BASE
        B.BASE = stage
        try:
            _r, _e, _t, _end, _tb, _slots, _chosen, cmap, st = B.build_plan()
            B.rewrite_text(rows, cmap, st['native_set'], sync_cscv=True,
                           keep_collide=True, skip_blobs=B.MECHANIC_BLOBS,
                           menu_exempt=True, ui_always=True,
                           slot_release=True, desc_release=True,
                           dry_run=True, classify=classify)
        finally:
            B.BASE = old
        ml_meta = R.ml_meta(stage)
    else:
        print('  [警告] 缺少原版文件 %s —— 无法判定“受保护”字符串，protected/ 将为空。'
              % ', '.join(missing))
        print('         请在有原版备份（*.bak）或干净原版目录的环境下再导出一次。')

    norm, prot = [], []
    for r in rows:
        try:
            key = (int(r['blob_index']), int(r['offset']))
        except Exception:
            continue
        reason = classify.get(key)
        if reason:
            prot.append((r, reason))
        elif r.get('zh_new'):
            norm.append((r, None))

    # 清理上次导出的产物（只删生成物，保留同目录的校对 .bat 等文件）
    import glob as _glob
    import shutil
    os.makedirs(OUT, exist_ok=True)
    for pat in ('10_*.json', '20_*.json', '30_multiline.json', '40_dlc01.json'):
        for old in _glob.glob(os.path.join(OUT, pat)):
            os.remove(old)
    for sub in ('protected', 'dict'):
        d = os.path.join(OUT, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)

    n_norm = n_prot = 0
    for cat, sel in (('ui', lambda r: not is_dialogue(r)),
                     ('dialogue', is_dialogue)):
        items = [(r, rn) for r, rn in norm if sel(r)] + \
                [(r, rn) for r, rn in prot if sel(r)]
        idxmap, nsh = shard_map(items)
        pfx = '10' if cat == 'ui' else '20'
        n_norm += write_shards(pfx, cat, [(r, rn) for r, rn in norm if sel(r)],
                               OUT, idxmap, nsh)
        n_prot += write_shards(pfx, cat, [(r, rn) for r, rn in prot if sel(r)],
                               os.path.join(OUT, 'protected'), idxmap, nsh, prot=True)

    # ---- 多行整字段 ----
    ml_entries = []
    for i, (key, val) in enumerate(md.items(), 1):
        m = ml_meta.get(key, {})
        meta = {}
        if m:
            meta = {'blob': m['blob'], 'offset': m['off'],
                    'cap': max(0, m['cap_bytes'] // 2), 'cap_bytes': m['cap_bytes']}
        ml_entries.append({'id': 'ml::%d' % i, 'en': key, 'ja': m.get('ja', ''),
                           'zh': B.apply_repl(str(val)), 'meta': meta})
    R.write_json(os.path.join(OUT, '30_multiline.json'),
                 doc('multiline', '多行整字段（一次显示多行的对话/说明整段）。'
                     '游戏显示优先走这里，zh 的换行就是屏上的换行。', ml_entries))

    # ---- DLC01 ----
    dcaps = R.dlc_caps()
    dlc_entries = []
    for i in range(1, 7):
        fn = 'zh_%02d' % i
        p = paths.data('dlc', fn + '.tsv')
        if not os.path.exists(p):
            continue
        for n, ln in enumerate(open(p, encoding='utf-8-sig').read().splitlines(), 1):
            if not ln.strip():
                continue
            ja, _, z = ln.partition('\t')
            meta = {'file': fn}
            cap = dcaps.get(ja)
            if cap is not None:
                meta['cap'] = max(0, cap // 2)
                meta['cap_bytes'] = cap
            dlc_entries.append({'id': 'dlc::%s::%d' % (fn, n), 'en': '',
                                'ja': ja, 'zh': z, 'meta': meta})
    p7 = paths.data('dlc', 'zh_07.json')
    if os.path.exists(p7):
        d7 = json.load(open(p7, encoding='utf-8'))
        for n, (ja, z) in enumerate(d7.items(), 1):
            meta = {'file': 'zh_07'}
            cap = dcaps.get(ja)
            if cap is not None:
                meta['cap'] = max(0, cap // 2)
                meta['cap_bytes'] = cap
            dlc_entries.append({'id': 'dlc::zh_07::%d' % n, 'en': '', 'ja': ja,
                                'zh': z, 'meta': meta})
    R.write_json(os.path.join(OUT, '40_dlc01.json'),
                 doc('dlc', 'DLC01（时之女神宝物包）译文；zh 的换行为屏上换行。'
                     '改不了的条目（dlc_skip.txt 列出的键）不会上屏。', dlc_entries))

    # ---- 替换词典 ----
    def load_ns(p):
        ns = {}
        if os.path.exists(p):
            exec(compile(open(p, encoding='utf-8').read(), p, 'exec'), ns)
        return ns
    repl = load_ns(paths.data('replace_map.py')).get('REPL', {})
    hl = load_ns(paths.data('hl_map.py')).get('HL', {})
    R.write_json(os.path.join(OUT, 'dict', '替换词典.json'), {
        '_note': '本文件为导出快照，请勿在此编辑。真正的词典源文件是 locales/<locale>/'
                 'replace_map.py（REPL）与 hl_map.py（HL），由开发者人工维护。',
        '_mechanism': '字库容量有限，装机时按键长降序对译文做词级替换（apply_repl）。'
                      '因此 JSON 里的 zh 是“压平后”的显示值。',
        'replace_map(REPL)': repl,
        'hl_map(HL)': hl,
    })

    # ---- 说明 ----
    with open(os.path.join(OUT, '如何校对.txt'), 'w', encoding='utf-8') as f:
        f.write(HOWTO % {'n_norm': n_norm, 'n_prot': n_prot, 'n_ml': len(ml_entries),
                         'n_dlc': len(dlc_entries),
                         'n_repl': len(repl), 'n_hl': len(hl),
                         'prot_ok': ('已生成' if protected_ok else
                                     '未生成（缺原版文件，见导出日志）')})

    print('done. 普通 %d 条 / 受保护 %d 条 / 多行 %d 条 / DLC %d 条'
          % (n_norm, n_prot, len(ml_entries), len(dlc_entries)))
    print('out: %s' % OUT)


HOWTO = '''【面向译者的校对文件 · 使用说明】

一、这些文件是什么
  本目录下每个 *.json 都是一片可校对的译文，放在 locales/zh-CN/translator-view/：
    10_ui_*.json        菜单 / 系统消息 / 物品说明等 UI 类单行文本
    20_dialogue_*.json  对话类单行文本（原文带「」引号）
    30_multiline.json   多行整字段（一次显示几行的对话整段，游戏显示优先走它）
    40_dlc01.json       DLC01（时之女神宝物包）文本
    protected/          受保护、当前【不会上屏】的文本（文件名 prot_ui_*.json，见第三节）
    dict/替换词典.json   当前生效的替换词典（见第四节）
    汉化-导出校对.bat    重新导出译文（覆盖上面的 JSON，不删本目录其它文件）
    汉化-导入校对.bat    把改好的 zh 写回译表并刷新 dist/
    汉化-导入校对-回滚.bat  撤销上次导入

二、怎么改
  1. 每条记录 = {id, en, ja, zh, meta}，只允许改 "zh"，其它字段请勿改动。
     en / ja 是英文、日文原文，只作对照；meta 是位置与容量信息。
  2. zh 就是游戏当前实际显示的文字；留空 = 不动这一条。
  3. 保存（保持 UTF-8 编码，推荐用 VS Code / 记事本；Excel 另存会损坏）后，
     双击本目录里的 汉化-导入校对.bat（与本文件同目录）：
       · 先把你的修改写回译表；
       · 再做自检（超长、无法识别等），有问题会【中断并输出日志】，指出是哪一条；
       · 通过后刷新 dist/ 目录里的完整补丁。
  4. 想立刻在游戏里看到效果：再双击游戏目录里的 汉化-安装.bat 装机
     （导入校对不改游戏目录）。
  5. 改坏了想反悔：双击本目录里的 汉化-导入校对-回滚.bat 恢复到上次导入前的译表。
  6. 想重新导出一份最新译文（会覆盖本目录下的 JSON，但不会删本目录的 .bat）：

     双击本目录里的 汉化-导出校对.bat。导出需要开发者机器上的原版游戏文件
     （config.local.json / HMH2_GAME_DIR 指向），因此通常由开发者执行。

三、protected/（受保护的文本 —— 改了也不会马上上屏）
  放进 protected/ 的，是项目已验证「翻译会破坏游戏机制」而【故意保留原文】的文本：
    · 名字键类（meta.protected = "collide"）：这些原文同时出现在游戏脚本/数据层，
      游戏按名字比对它们；翻译会导致技能失效、章节/关卡找不到等。
    · 机制表类（"mech"）：技能/职业/连携技等会被游戏按内容读取的表。
    · 章节名 / 称号名（"chaptitle"）：按字符串索引的键。
  它们【仍可修改】：修改会被写回译表保存下来，但当前不会显示在屏幕上；
  将来若保护被解除（例如找到安全方案），这些译文即可直接生效。
  请勿为了“让它上屏”而删除 protected/ 文件，那不会改变保护规则。

四、替换词典（字库容量导致的近义词替换）
  受游戏字库格数限制，装机时会在译文上再做一次“词级替换”：把占格宝贵/缺字形的词
  换成占用更省的同义词，规则表就是 dict/替换词典.json。
  · 因为替换先于显示，JSON 里的 zh 已经是“压平后”的字面，所见即所得。
  · 词典真正的源文件是 locales/zh-CN/replace_map.py 与 hl_map.py（纯文本，形如
    {"原文词": "替换词"}），由开发者人工维护；本目录下的 JSON 只是快照，改它无效。
  · 若你的 zh 里某个词显示成了别的词，多半就是命中了这里的一条规则。

五、注意
  · 不要增删记录、不要改 id；不要改 meta（容量上限、是否受保护等）。
  · 单行 / 多行 / DLC 各片是相互独立的文件，改错文件不会影响别的文件。
  · 每次导入前请先关闭游戏；导入有自检，出问题会中断并告诉你哪一条需要修。

【本次导出】普通文本 %(n_norm)d 条、受保护文本 %(n_prot)d 条（%(prot_ok)s）、
多行整字段 %(n_ml)d 条、DLC %(n_dlc)d 条；
替换词典 replace_map %(n_repl)d 条 / hl_map %(n_hl)d 条。
'''


if __name__ == '__main__':
    main()
