# -*- coding: utf-8 -*-
"""手术式回滚器 —— 只撤销"某一批改动"，不动其它任何工作。

原理
----
每批改动都留下了"改动前快照"和"改动后快照"（= 下一批的改动前快照）。
本工具用这两个快照做**差分**，得到该批真正改过的行：

  · 值被改写的行  -> 把 zh_new 还原成"改动前"的值
  · 该批新加的行  -> 整行删掉

**安全性**：还原时逐行核对"当前值是否仍等于改动后的值"；
若某行后来被别的批次再改过，则**跳过并报告**，不会覆盖后面的工作。
⇒ 所以做完 TODO-4 之类的大改动之后，仍可安全地单独回滚早期某一批。

配套：`ui_always.json` 的放行键也按批次登记，只删自己那批的键。

用法
----
  python revert_surgical.py list               列出全部批次与规模
  python revert_surgical.py check  <批次>      只预演（不改文件）
  python revert_surgical.py apply  <批次>      备份 + 回滚（随后需重装）
  python revert_surgical.py restore <备份名>   从快照整体还原（应急用）
"""
import os, sys, csv, json, shutil, time, glob

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
OUT = paths.build()
CSV = os.path.join(OUT, 'text_v2.csv')
UI = os.path.join(W, 'ui_always.json')
KEYS_T2C = os.path.join(W, 't2c_pilot_kinds.json')     # 70 个说话人名放行键

S = {  # 快照短名 -> 文件（按时间顺序）
    'a': 'text_v2.csv.bak_todo3a_20260915_192151',            # 0 行基准
    'b': 'text_v2.csv.bak_todo3a_20260915_201613',            # +29
    'c': 'text_v2.csv.bak_b2_fixes_20260915_203515',          # +25
    'd': 'text_v2.csv.bak_todo5_before_20260915_204810',      # +49
    'e': 'text_v2.csv.bak_t5b1_20260915_205221',              # +168
    'f': 'text_v2.csv.bak_t5b1x_20260915_210232',             # +1 +4
    'g': 'text_v2.csv.bak_t1school_20260915_211726',          # +14
    'h': 'text_v2.csv.bak_t1repl_20260915_212137',            # +25
    'i': 'text_v2.csv.bak_t2b_20260915_213537',               # +3263
    'j': 'text_v2.csv.bak_arch_20260915_224622',              # 新增 11 行（60796）
    'k': 'text_v2.csv.bak_t6comp_20260916_190020',            # +2 行（60797/60798）
    'l': 'text_v2.csv.bak_arch_20260916_204246',              # v2.52 修复前（= v2.51 基线）
    'm': 'text_v2.csv.bak_arch_20260916_205004',              # v2.52 修复后（内情->剧情 8 行）
}

# TODO-2 收尾批次1（放行 A 类 13 槽；CSV 未动，只加了 7 个放行键）
UI_T2A = [
    '<開始できます>', '<ネームエントリー>', '<最大魔王撃破数>：',
    '<イベント会話のセリフは>', '<アテナ：%sゴールド>',
    '＊\u3000<EVO_NAME__>は<２０００ゴールド>もらった！', '<しょうたいのみ>',
]
UI_T2B = ['<タイム>\u3000\u3000\u3000\u3000：']

BATCHES = [
    # 顺序 = 时间顺序；规模以"相邻快照差分"为准
    dict(id='todo3a',      label='TODO-3 方案A（两行对话连读，15 组）',              before='a', after='b'),
    dict(id='todo3b1',     label='TODO-3 方案B 批次1（13 组）',                     before='b', after='c'),
    dict(id='todo3b2',     label='TODO-3 方案B 批次2（26 组）',                     before='c', after='d'),
    dict(id='todo5a',      label='TODO-5 阶段1：英文占位符汉化 168 行',             before='d', after='e'),
    dict(id='todo5b',      label='TODO-5：4 条真漏译 + 阶段2 批次1（blob387 行级修订）', before='e', after='f'),
    dict(id='todo1school', label='TODO-1 收尾：学园→学院 对齐',                     before='f', after='g'),
    dict(id='todo1repl',   label='TODO-1 收尾：破词修复（摩托/姑娘/净水…）',         before='g', after='h'),
    dict(id='todo1align',  label='TODO-1 收尾：全表对齐 apply_repl 终态（3,263 行）', before='h', after='i'),
    dict(id='todo2a',      label='TODO-2 收尾批次1：放行 13 槽（仅 ui_always +7）',  before=None, after=None, ui=UI_T2A),
    dict(id='todo2b',      label='TODO-2 收尾批次2：新增 11 行 + ui_always +1',      before='i', after='j', ui=UI_T2B),
    dict(id='todo2c',      label='TODO-2 收尾批次3 试点：放行说话人名 70 种 / 991 槽（仅 ui_always +70）',
         before=None, after=None, ui_from=KEYS_T2C),
    # v2.49：这批**不动 text_v2.csv / ui_always.json**，只把 slot_release.json 的开关关掉再重装即可
    dict(id='todo2d',      label='TODO-2 收尾批次3 第二步：说话人名【槽位级放行】(stride292/pos96)',
         before=None, after=None, flag='slot_release'),
    # v2.50：Story Mode 章节浏览「XXXX completed!」——补登记 blob681 rec0/rec1 的 pos16（OVERTURE/JUDGEMENT）
    dict(id='t6comp',      label='章节浏览通关文本：补翻 OVERTURE / JUDGEMENT 2 槽（blob681 off16/376）',
         before='j', after='k'),
    # v2.51：说明文汉化 —— 放行 (268/44)(376/32)(376/160)(212/84)(272/64) + 补译 542 条
    dict(id='desc',        label='v2.51 说明文汉化（装备/技能/职业/阵形说明放行 + 542 条补译）',
         before=None, after=None, flag='desc_release', flagscale='关放行开关 + 删 542 行'),
    # v2.52：修掉「内情」错误用词 —— 删 replace_map 里的 '剧情'->'内情' + 译表 8 行
    dict(id='t7repl',      label='v2.52 修掉「内情」错误用词（REPL 规则 + 译表 8 处）',
         before='l', after='m', flag='t7_repl',
         flagscale='删 REPL 规则 + 8 行改回「内情」'),
    # v2.53：TODO-4 对话格式日式统一（名字：台词 → 名字「台词」+ 行2 全角缩进）
    dict(id='todo4',       label='v2.53 TODO-4 对话格式日式统一（20,234 槽「」化）',
         before=None, after=None, flag='todo4',
         flagscale='还原 20,234 行 + 46 条整字段 + build_cn.py 判据'),
    # v2.54：修掉「紧张 -> 发紧」错误用词（删 replace_map 规则 + 译表 13 行）
    dict(id='t9repl',      label='v2.54 修掉「紧张 -> 发紧」错误用词（REPL 规则 + 译表 13 处）',
         before=None, after=None, flag='t9_repl',
         flagscale='删 REPL 规则 + 13 行改回「发紧」'),
    # v2.55：修掉「战争 -> 战事」错误用词（删 replace_map 规则 + 译表 31 行 + 整字段 1 条 + DLC01 1 行）
    dict(id='t9brepl',     label='v2.55 修掉「战争 -> 战事」错误用词（REPL 规则 + 译表 31 处 + 整字段/DLC）',
         before=None, after=None, flag='t9b_repl',
         flagscale='删 REPL 规则 + 31 行 + 1 条整字段 + DLC01 1 行改回「战事」'),
]

BY_ID = {b['id']: b for b in BATCHES}

# 组合批次：一次撤销一整个 TODO 的若干批次（**必须按时间倒序**，这样逐批的"当前值核对"才成立）
GROUPS = {
    'todo3': ['todo3b2', 'todo3b1', 'todo3a'],
    'todo5': ['todo5b', 'todo5a'],
    'todo1': ['todo1align', 'todo1repl', 'todo1school'],
}

FIELDS = None
L = []


def p(x=''):
    L.append(str(x))


def read_csv(path):
    """返回 (fieldnames, [rowdict...], 顺序 key 列表)"""
    with open(path, encoding='utf-8', newline='') as f:
        rd = csv.DictReader(f)
        return rd.fieldnames, list(rd)


def key_of(r):
    return (int(r['blob_index']), int(r['offset']))


def ui_keys_of(b):
    if b.get('ui'):
        return list(b['ui'])
    if b.get('ui_from'):
        return list(json.load(open(b['ui_from'], encoding='utf-8')))
    return []


def compute(b):
    """返回 (changed, added, ui_keys)；changed=[(key, before_zh, before_row, after_zh)]"""
    ui = ui_keys_of(b)
    if not b.get('before'):
        return [], [], ui
    _, r0 = read_csv(os.path.join(OUT, S[b['before']]))
    _, r1 = read_csv(os.path.join(OUT, S[b['after']]))
    m0 = {key_of(r): r for r in r0}
    m1 = {key_of(r): r for r in r1}
    changed, added = [], []
    for k in m1:
        if k not in m0:
            added.append((k, m1[k]))
        elif (m1[k].get('zh_new') or '') != (m0[k].get('zh_new') or ''):
            changed.append((k, m0[k].get('zh_new') or '', m0[k], m1[k].get('zh_new') or ''))
    return changed, added, ui


def do_flag_slot_release(b, mode):
    """特殊批次：槽位级放行（TODO-2D）。本批不动译表 ⇒ 回滚 = 关开关 + 重装。"""
    f = os.path.join(W, 'slot_release.json')
    p('== 手术式回滚 · %s ==' % b['label'])
    p('批次 id: %s   （%s）' % (b['id'], mode))
    p('')
    try:
        d = json.load(open(f, encoding='utf-8'))
    except Exception:
        d = None
    if d is None:
        p('!! 找不到 %s' % f)
        return 1
    p('本批不修改 text_v2.csv / ui_always.json，只靠 %s 的 enabled 开关控制。' % os.path.basename(f))
    p('当前 enabled = %s' % d.get('enabled'))
    p('')
    if mode == 'check':
        p('回滚将执行：enabled -> false（然后需重装才生效）')
        p('（这是预演，未修改任何文件）')
        return 0
    if not d.get('enabled'):
        p('已经是关闭状态，无需回滚。')
        return 0
    ts = time.strftime('%Y%m%d_%H%M%S')
    bak = f + '.bak_rollback_%s' % ts
    shutil.copy2(f, bak)
    d['enabled'] = False
    with open(f, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    p('已关闭槽位级放行（备份 %s）' % os.path.basename(bak))
    p('')
    p('⚠ 还需重装才生效：python _work/build_cn.py apply_menu（会自动同步 DLC01）')
    return 0


def do_flag_desc_release(b, mode):
    """v2.51 说明文汉化回滚 = 删掉本批 542 行 + 关掉 desc_release 放行开关。"""
    import subprocess
    f = os.path.join(W, 'desc_release.json')
    p('== 手术式回滚 · %s ==' % b['label'])
    p('批次 id: %s   （%s）' % (b['id'], mode))
    p('')
    script = os.path.join(W, 'desc_rollback.py')
    if not os.path.exists(script):
        p('!! 找不到 %s' % script)
        return 1
    p('本批 = ① 译表新增 542 行（row_id 60798..61339）② desc_release.json 的 enabled')
    p('')
    act = 'check' if mode == 'check' else 'apply'
    try:
        r = subprocess.run([sys.executable, script, act],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        for ln in (r.stdout or '').splitlines():
            p('   ' + ln)
        for ln in (r.stderr or '').splitlines():
            p('   !! ' + ln)
        rc = r.returncode
    except Exception as e:
        p('!! 调用失败：%r' % e)
        return 1
    if mode != 'check':
        p('')
        p('⚠ 还需重装才生效：python _work/build_cn.py apply_menu（会自动同步 DLC01）')
    return rc


def do_flag_t7_repl(b, mode):
    """v2.52「内情 -> 剧情」回滚 = 删掉 REPL 规则改回去 + 译表 8 行改回「内情」。

    注意：本批还会动 replace_map.py（`t7_repl_fix.py` 里带备份）。
    """
    import subprocess
    p('== 手术式回滚 · %s ==' % b['label'])
    p('批次 id: %s   （%s）' % (b['id'], mode))
    p('')
    script = os.path.join(W, 't7_repl_fix.py')
    if not os.path.exists(script):
        p('!! 找不到 %s' % script)
        return 1
    p('本批 = ① replace_map.py 里删掉 \'剧情\': \'内情\' ')
    p('       ② text_v2.csv 里 8 处「剧情」改回「内情」')
    p('')
    act = 'check' if mode == 'check' else 'revert'
    try:
        r = subprocess.run([sys.executable, script, act],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        for ln in (r.stdout or '').splitlines():
            p('   ' + ln)
        for ln in (r.stderr or '').splitlines():
            p('   !! ' + ln)
        rc = r.returncode
    except Exception as e:
        p('!! 调用失败：%r' % e)
        return 1
    if mode != 'check':
        p('')
        p('⚠ 还需重装才生效：python _work/build_cn.py apply_menu（会自动同步 DLC01）')
    return rc


def do_flag_todo4(b, mode):
    """v2.53 TODO-4 对话格式日式统一回滚 = 还原译表 20,234 行 + 46 条整字段 + build_cn.py 判据。"""
    import subprocess
    p('== 手术式回滚 · %s ==' % b['label'])
    p('批次 id: %s   （%s）' % (b['id'], mode))
    p('')
    script = os.path.join(W, 't4_rollback.py')
    if not os.path.exists(script):
        p('!! 找不到 %s' % script)
        return 1
    p('本批 = ① text_v2.csv 20,234 行（名字：台词 → 名字「台词」）')
    p('       ② ml_zh_fields.json 46 条多行整字段')
    p('       ③ build_cn.py 放宽"带引号对话放行"判据（新增 4 槽）')
    p('')
    act = 'check' if mode == 'check' else 'apply'
    try:
        r = subprocess.run([sys.executable, script, act],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        for ln in (r.stdout or '').splitlines():
            p('   ' + ln)
        for ln in (r.stderr or '').splitlines():
            p('   !! ' + ln)
        rc = r.returncode
    except Exception as e:
        p('!! 调用失败：%r' % e)
        return 1
    if mode != 'check':
        p('')
        p('⚠ 还需重装才生效：python _work/build_cn.py revert → apply_menu（会自动同步 DLC01）')
    return rc


def do_flag_t9_repl(b, mode):
    """v2.54「紧张 -> 发紧」回滚 = 恢复 REPL 规则 + 译表 13 行改回「发紧」。"""
    import subprocess
    p('== 手术式回滚 · %s ==' % b['label'])
    p('批次 id: %s   （%s）' % (b['id'], mode))
    p('')
    script = os.path.join(W, 't9_tight_fix.py')
    if not os.path.exists(script):
        p('!! 找不到 %s' % script)
        return 1
    p("本批 = ① replace_map.py 里恢复 '紧张': '发紧'")
    p('       ② text_v2.csv 里 13 处「紧张」改回「发紧」')
    p('')
    act = 'check' if mode == 'check' else 'revert'
    try:
        r = subprocess.run([sys.executable, script, act],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        for ln in (r.stdout or '').splitlines():
            p('   ' + ln)
        for ln in (r.stderr or '').splitlines():
            p('   !! ' + ln)
        rc = r.returncode
    except Exception as e:
        p('!! 调用失败：%r' % e)
        return 1
    if mode != 'check':
        p('')
        p('⚠ 还需重装才生效：python _work/build_cn.py revert → apply_menu（会自动同步 DLC01）')
    return rc


def do_flag_t9b_repl(b, mode):
    """v2.55「战争 -> 战事」回滚 = 恢复 REPL 规则 + 译表 31 行 + 整字段 1 条 + DLC01 1 行。"""
    import subprocess
    p('== 手术式回滚 · %s ==' % b['label'])
    p('批次 id: %s   （%s）' % (b['id'], mode))
    p('')
    script = os.path.join(W, 't9b_war_fix.py')
    if not os.path.exists(script):
        p('!! 找不到 %s' % script)
        return 1
    p("本批 = ① replace_map.py 里恢复 '战争': '战事'")
    p('       ② text_v2.csv 里 31 处「战争」改回「战事」')
    p('       ③ ml_zh_fields.json 1 条 + DLC01 zh_05.tsv 1 行改回')
    p('       （清单 _work/t9b_war_manifest.json，逐行核对"当前值==本批改后值"才还原）')
    p('')
    act = 'check' if mode == 'check' else 'revert'
    try:
        r = subprocess.run([sys.executable, script, act],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        for ln in (r.stdout or '').splitlines():
            p('   ' + ln)
        for ln in (r.stderr or '').splitlines():
            p('   !! ' + ln)
        rc = r.returncode
    except Exception as e:
        p('!! 调用失败：%r' % e)
        return 1
    if mode != 'check':
        p('')
        p('⚠ 还需重装才生效：python _work/build_cn.py revert → apply_menu（会自动同步 DLC01）')
    return rc


def cmd_list():
    p('== 可单独回滚的批次 ==')
    p('%-12s %-58s %s' % ('批次 id', '说明', '规模'))
    for b in BATCHES:
        if b.get('flag'):
            p('%-12s %-58s %s' % (b['id'], b['label'],
                                  b.get('flagscale', '关开关（不涉及译表）')))
            continue
        ch, ad, ui = compute(b)
        scale = []
        if ch:
            scale.append('改 %d 行' % len(ch))
        if ad:
            scale.append('删 %d 行' % len(ad))
        if ui:
            scale.append('删 %d 个放行键' % len(ui))
        p('%-12s %-58s %s' % (b['id'], b['label'], ' + '.join(scale) or '—'))
    p('')
    p('用法：  python revert_surgical.py check <批次 id>   （先预演，不改文件）')
    p('        python revert_surgical.py apply <批次 id>   （执行回滚，随后需重装）')


def do(bid, mode):
    if bid in GROUPS:
        ids = GROUPS[bid]
        p('== 组合回滚 %s ==（按时间倒序执行：%s）' % (bid, ' -> '.join(ids)))
        if mode == 'check':
            p('⚠ 说明：组合回滚的"预演"是**逐批静态核对**，后几批会显示"被后续批次改过"（因为前几批还没真的回滚）；')
            p('   实际 `apply` 是**逐批真实回滚**，前一批回滚后，后一批的核对就会通过。所以这里显示的可回滚数会偏保守。')
        p('')
        rc = 0
        for x in ids:
            rc |= do(x, mode)
            p('')
            p('-' * 60)
            p('')
        return rc
    b = BY_ID.get(bid)
    if not b:
        p('!! 未知批次 %r；可用：%s ／ 组合：%s'
          % (bid, ', '.join(BY_ID), ', '.join(GROUPS)))
        return 1
    if b.get('flag') == 'slot_release':
        return do_flag_slot_release(b, mode)
    if b.get('flag') == 'desc_release':
        return do_flag_desc_release(b, mode)
    if b.get('flag') == 't7_repl':
        return do_flag_t7_repl(b, mode)
    if b.get('flag') == 'todo4':
        return do_flag_todo4(b, mode)
    if b.get('flag') == 't9_repl':
        return do_flag_t9_repl(b, mode)
    if b.get('flag') == 't9b_repl':
        return do_flag_t9b_repl(b, mode)
    ch, ad, ui = compute(b)
    p('== 手术式回滚 · %s ==' % b['label'])
    p('批次 id: %s   （%s）' % (bid, mode))
    p('')
    p('本批规模：改写 %d 行 / 新增 %d 行 / 放行键 %d 个' % (len(ch), len(ad), len(ui)))
    p('')

    _, cur = read_csv(CSV)
    curmap = {key_of(r): r for r in cur}
    ui_cur = json.load(open(UI, encoding='utf-8'))

    # —— 逐行核对 ——
    todo_chg, skip_chg = [], []
    for k, old_zh, _old_row, aft_zh in ch:
        r = curmap.get(k)
        if r is None:
            skip_chg.append((k, '当前表里已无此行', aft_zh, ''))
            continue
        now = r.get('zh_new') or ''
        if now == aft_zh:
            todo_chg.append((k, old_zh, r, aft_zh))
        elif now == old_zh:
            skip_chg.append((k, '已是"改动前"的值（可能已回滚过）', aft_zh, now))
        else:
            skip_chg.append((k, '**当前值被后续批次改过**', aft_zh, now))

    todo_del, skip_del = [], []
    for k, row in ad:
        r = curmap.get(k)
        if r is None:
            skip_del.append((k, '已不存在'))
        elif (r.get('zh_new') or '') == (row.get('zh_new') or ''):
            todo_del.append((k, r))
        else:
            skip_del.append((k, '**内容被后续批次改过**'))

    todo_ui = [k for k in ui if k in ui_cur]
    p('将执行：')
    p('  改写回原文 %d 行 ｜ 删除本批新增 %d 行 ｜ 删除放行键 %d 个' % (len(todo_chg), len(todo_del), len(todo_ui)))
    if skip_chg or skip_del:
        p('')
        p('⚠ 跳过 %d 处（不会覆盖后续工作）：' % (len(skip_chg) + len(skip_del)))
        for k, why, a, n in skip_chg[:20]:
            p('   b%d/%d  %s' % (k[0], k[1], why))
            p('        本批改后=%r  当前=%r' % (a[:30], n[:30]))
        for k, why in skip_del[:20]:
            p('   b%d/%d  新增行 %s' % (k[0], k[1], why))
    p('')
    p('不受影响：其它批次改过的行 / 其它放行键 / replace_map.py / ml_zh_fields.json / hl_map.py')

    if mode == 'check':
        p('')
        p('（这是预演，未修改任何文件）')
        return 0

    ts = time.strftime('%Y%m%d_%H%M%S')
    bak = CSV + '.bak_rollback_%s_%s' % (bid, ts)
    shutil.copy2(CSV, bak)
    msgs = ['备份: %s' % os.path.basename(bak)]

    out_rows = []
    chg_map = {k: old for k, old, _r, _a in todo_chg}
    del_set = {k for k, _ in todo_del}
    for r in cur:
        k = key_of(r)
        if k in del_set:
            continue
        if k in chg_map:
            r = dict(r)
            r['zh_new'] = chg_map[k]
        out_rows.append(r)

    with open(CSV, 'w', encoding='utf-8', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=cur[0].keys(), lineterminator='\r\n',
                            quoting=csv.QUOTE_MINIMAL)
        wr.writeheader()
        wr.writerows(out_rows)
    msgs.append('已回滚 text_v2.csv：改写 %d 行、删除 %d 行（现 %d 行）'
                % (len(todo_chg), len(todo_del), len(out_rows)))

    if todo_ui:
        ub = UI + '.bak_rollback_%s_%s' % (bid, ts)
        shutil.copy2(UI, ub)
        for k in todo_ui:
            ui_cur.pop(k, None)
        json.dump(ui_cur, open(UI, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        msgs.append('已删放行键 %d 个（ui_always %d 条）。备份 %s'
                    % (len(todo_ui), len(ui_cur), os.path.basename(ub)))

    p('')
    for m in msgs:
        p(m)
    p('')
    p('⚠ 还需重装才生效：python _work/build_cn.py apply_menu（会自动同步 DLC01）')
    return 0


def cmd_restore(bakname):
    """应急：从某个快照整体还原 text_v2.csv。"""
    src = bakname
    if not os.path.isabs(src) and not os.path.exists(src):
        for cand in (os.path.join(OUT, bakname), os.path.join(W, bakname)):
            if os.path.exists(cand):
                src = cand
                break
    if not os.path.exists(src):
        p('!! 找不到快照 %r' % bakname)
        return 1
    ts = time.strftime('%Y%m%d_%H%M%S')
    shutil.copy2(CSV, CSV + '.bak_pre_restore_' + ts)
    shutil.copy2(src, CSV)
    p('已从 %s 整体还原 text_v2.csv' % os.path.basename(src))
    p('（当前表已备份为 text_v2.csv.bak_pre_restore_%s）' % ts)
    p('⚠ 还需重装：python _work/build_cn.py apply_menu')
    return 0


if __name__ == '__main__':
    argv = sys.argv[1:]
    if not argv or argv[0] == 'list':
        cmd_list()
    elif argv[0] in ('check', 'apply') and len(argv) > 1:
        do(argv[1], argv[0])
    elif argv[0] == 'restore' and len(argv) > 1:
        cmd_restore(argv[1])
    else:
        p('用法：list | check <批次> | apply <批次> | restore <快照文件>')
    txt = '\n'.join(L)
    open(paths.build('_revert_surgical_out.txt'), 'w', encoding='utf-8').write(txt)
    print(txt)
