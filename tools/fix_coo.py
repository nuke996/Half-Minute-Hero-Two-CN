# -*- coding: utf-8 -*-
"""v2.29 Coo 角色译名统一：明确称呼角色的"咕/咕咕" -> "小咕"。

判定（保守）：
  text_v2.csv 行: ja 含 'クゥ'（角色名原文，术语表口径） -> 角色行 -> 改
                  ja 无 'クゥ' 但 en 含 'Coo'           -> 人工档（不改，仅列出防误判，
                                                            如 row678 鸽子拟声 Coo coo coo）
  ml_zh_fields:   键(en 整字段) 含 'Coo' -> 角色行（扫描 10 条已人工核验全为角色对话）
  hl_map.py:      '<Coo>': '<咕>' -> '<Coo>': '<小咕>'（build_cn 把 HL 合并进 REPL，
                    该标记最终显示为 <咕>，需同步统一）
替换：先 '咕咕'->'小咕'（叠词统一），再 '咕'->'小咕'；结果写 zh_new（zh_3dm 保留不动）。
防线：替换后 len(zh_new) > max_cn 则跳过；写回后全表复核（行数/row_id 序列/en+ja 列/
      非目标行 zh_new 全部不变，目标行等于期望值）。
模式：plan（默认，只出计划）/ apply（备份+执行+自检）/ revert（按状态文件恢复）。
输出：_fix_coo_out.txt
"""
import os, csv, json, shutil, datetime, sys, re

import paths
BASE = paths.GAME_DIR
WORK = paths.DATA_DIR
CSV_P = paths.data('text_v2.csv')
MJ_P = os.path.join(WORK, 'ml_zh_fields.json')
HL_P = os.path.join(WORK, 'hl_map.py')
OUT = paths.build('_fix_coo_out.txt')
STATE = paths.build('fix_coo_state.json')
TS = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
HL_OLD = "'<Coo>': '<咕>'"
HL_NEW = "'<Coo>': '<小咕>'"
# 特例：ja 该行未写クゥ（跨行句），但 en/ja 上下文明确指角色 Coo
EXTRA_ROWS = {'27458'}

lines = []
def P(s=''):
    lines.append(str(s))

def conv(zh):
    """裸'咕'（含叠词'咕咕'）-> '小咕'；已有'小咕'原样保护。
    返回 (新串, 裸咕处数)。"""
    if '咕' not in zh:
        return zh, 0
    tmp = zh.replace('小咕', '\x01')          # 保护已有"小咕"
    n = tmp.count('咕')
    if n == 0:
        return zh, 0                           # 纯"小咕"，无需改
    new = re.sub(r'咕咕|咕', '小咕', tmp)      # 叠词优先，一步替换
    return new.replace('\x01', '小咕'), n

def load_csv(path):
    with open(path, encoding='utf-8', newline='') as f:
        rd = csv.DictReader(f)
        return rd.fieldnames, list(rd)

def collect_csv_plan(path=CSV_P):
    """返回 (表头, 行, 计划列表, 人工档列表, 统计)。计划项为 (行索引, row, 旧eff, 新zh, 处数)。"""
    fn, rows = load_csv(path)
    plan, manual = [], []
    stat = {'gu_rows': 0, 'role': 0, 'manual': 0, 'over': 0, 'changed': 0, 'places': 0}
    for i, r in enumerate(rows):
        zh_new = r.get('zh_new') or ''
        zh_3dm = r.get('zh_3dm') or ''
        eff = zh_new if zh_new else zh_3dm
        if '咕' not in eff:
            continue
        stat['gu_rows'] += 1
        en = r.get('en') or ''
        ja = r.get('ja') or ''
        if 'クゥ' not in ja:
            if r.get('row_id') in EXTRA_ROWS:
                pass                      # 显式特例：上下文明确指角色
            elif 'Coo' in en:
                stat['manual'] += 1
                manual.append((r, eff))
                continue
            else:
                continue
        stat['role'] += 1
        new, n = conv(eff)
        if n == 0:
            continue                              # 已是"小咕"，无需改
        plan_item = (i, r, eff, new, n)
        try:
            maxcn = int(r.get('max_cn') or '-1')
        except ValueError:
            maxcn = -1
        if maxcn >= 0 and len(new) > maxcn:
            stat['over'] += 1
            P('[超限跳过] row=%s blob=%s off=%s maxcn=%s 新长=%d' % (
                r['row_id'], r['blob_index'], r['offset'], maxcn, len(new)))
            P('   新译文: %s' % new)
            continue
        plan.append(plan_item)
    return fn, rows, plan, manual, stat

def collect_ml_plan(path=MJ_P):
    d = json.load(open(path, encoding='utf-8'))
    plan = []
    for key, val in d.items():
        v = str(val)
        if '咕' in v and 'Coo' in str(key):
            new, n = conv(v)
            plan.append((key, v, new, n))
    return d, plan

def do_revert():
    st = json.load(open(STATE, encoding='utf-8'))
    for tag, path in st['backs'].items():
        shutil.copy2(path, path.split('.bak_coo_')[0])
        P('已恢复: %s <- %s' % (os.path.basename(path), os.path.basename(path)))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('REVERT OK ->', OUT)

def do_verify():
    """基于备份生成期望值，比对磁盘当前文件。"""
    st = json.load(open(STATE, encoding='utf-8'))
    bak_csv = st['backs']['csv']
    bak_mj = st['backs']['ml']
    P('==== fix_coo verify (apply at %s) ====' % st.get('ts', ''))
    ok = True
    _, rows_bak, plan, manual, stat = collect_csv_plan(bak_csv)
    _, rows2 = load_csv(CSV_P)
    exp = {int(r['row_id']): new for _, r, old, new, n in plan}
    if len(rows_bak) != len(rows2):
        ok = False
        P('  [X] 行数变化 %d -> %d' % (len(rows_bak), len(rows2)))
    n_hit = 0
    for r1, r2 in zip(rows_bak, rows2):
        rid = int(r1['row_id'])
        e = exp.get(rid)
        if e is None:
            if (r1.get('zh_new') or '') != (r2.get('zh_new') or ''):
                ok = False
                P('  [X] 非目标行 zh_new 变化 row=%s' % rid)
        elif r2.get('zh_new') != e:
            ok = False
            P('  [X] 目标行不符 row=%s' % rid)
        else:
            n_hit += 1
    P('  CSV: 目标行命中 %d/%d | 非目标行未动 %s' % (n_hit, len(plan), 'OK' if ok else 'FAIL'))
    md_bak, ml_plan2 = collect_ml_plan(bak_mj)
    md2 = json.load(open(MJ_P, encoding='utf-8'))
    m_hit = sum(1 for key, old, new, n in ml_plan2 if md2.get(key) == new)
    for key, old, new, n in ml_plan2:
        if md2.get(key) != new:
            ok = False
            P('  [X] ml 目标条不符: %s' % key[:50])
    P('  ml : 目标条命中 %d/%d' % (m_hit, len(ml_plan2)))
    hl_txt = open(HL_P, encoding='utf-8').read()
    if HL_NEW in hl_txt:
        P('  hl_map.py: %s ✓' % HL_NEW)
    else:
        ok = False
        P('  [X] hl_map.py 未找到 %s' % HL_NEW)
    P('verify: %s' % ('ALL OK' if ok else 'FAILED'))
    _flush()

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'plan'
    if mode == 'revert':
        do_revert()
        return
    if mode == 'verify':
        do_verify()
        return

    apply_mode = (mode == 'apply')
    P('==== fix_coo %s %s ====' % (mode, TS))

    fn, rows, plan, manual, stat = collect_csv_plan()
    md, ml_plan = collect_ml_plan()

    P('')
    P('== 统计 ==')
    P('  text_v2.csv 含咕行 %d | 角色行(改) %d | 人工档(不改) %d | 超限跳过 %d'
      % (stat['gu_rows'], stat['role'], stat['manual'], stat['over']))
    P('  ml_zh_fields 角色条(改) %d' % len(ml_plan))
    P('')

    if manual:
        P('== 人工档（en 提及 Coo 但 ja 无 クゥ，默认不改）==')
        for r, eff in manual:
            P('  row=%s blob=%s | EN: %s | JA: %s | ZH: %s' % (
                r['row_id'], r['blob_index'],
                (r.get('en') or '')[:60], (r.get('ja') or '')[:60], eff[:60]))
        P('')

    P('== text_v2.csv 改动清单（%d 行）==' % len(plan))
    for i, r, old, new, n in plan:
        P('  row=%s blob=%s off=%s (+%d处)' % (r['row_id'], r['blob_index'], r['offset'], n))
        P('    EN: %s' % (r.get('en') or '')[:90].replace('\n', '\\n'))
        P('    JA: %s' % (r.get('ja') or '')[:90].replace('\n', '\\n'))
        P('    旧: %s' % old[:90].replace('\n', '\\n'))
        P('    新: %s' % new[:90].replace('\n', '\\n'))

    P('')
    P('== ml_zh_fields.json 改动清单（%d 条）==' % len(ml_plan))
    for key, old, new, n in ml_plan:
        P('  (+%d处) EN: %s' % (n, key[:80].replace('\n', '\\n')))
        P('    旧: %s' % old[:80].replace('\n', '\\n'))
        P('    新: %s' % new[:80].replace('\n', '\\n'))

    if not apply_mode:
        P('')
        P('[plan 模式] 未写任何文件。确认清单后运行: fix_coo.py apply')
        _flush()
        return

    # ---------- apply ----------
    P('')
    P('== 执行 ==')
    bak_csv = CSV_P + '.bak_coo_' + TS
    bak_mj = MJ_P + '.bak_coo_' + TS
    bak_hl = HL_P + '.bak_coo_' + TS
    shutil.copy2(CSV_P, bak_csv)
    shutil.copy2(MJ_P, bak_mj)
    shutil.copy2(HL_P, bak_hl)
    P('备份: %s / %s / %s' % (os.path.basename(bak_csv), os.path.basename(bak_mj), os.path.basename(bak_hl)))

    # hl_map.py：精确替换一条
    hl_txt = open(HL_P, encoding='utf-8').read()
    if HL_OLD in hl_txt:
        hl_txt = hl_txt.replace(HL_OLD, HL_NEW)
        open(HL_P, 'w', encoding='utf-8').write(hl_txt)
        P('hl_map.py: %s -> %s' % (HL_OLD, HL_NEW))
        hl_ok = True
    elif HL_NEW in hl_txt:
        P('hl_map.py: 已是 %s（无需改）' % HL_NEW)
        hl_ok = True
    else:
        P('hl_map.py: 未找到 %s ！检查该文件后重跑。' % HL_OLD)
        hl_ok = False

    # CSV 写入
    n_changed = n_places = 0
    for i, r, old, new, n in plan:
        rows[i]['zh_new'] = new
        n_changed += 1
        n_places += n
    with open(CSV_P, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        w.writerows(rows)
    P('text_v2.csv: 改 %d 行 / %d 处' % (n_changed, n_places))

    # ml 写入
    m_changed = m_places = 0
    for key, old, new, n in ml_plan:
        md[key] = new
        m_changed += 1
        m_places += n
    json.dump(md, open(MJ_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    P('ml_zh_fields.json: 改 %d 条 / %d 处' % (m_changed, m_places))

    # ---------- 自检 ----------
    P('')
    P('== 自检 ==')
    plan_map = {i: new for i, r, old, new, n in plan}
    fn2, rows2 = load_csv(CSV_P)
    ok = True
    if len(rows2) != len(rows):
        ok = False
        P('  [X] 行数变化 %d -> %d' % (len(rows), len(rows2)))
    diff_guard = 0
    for i, (r1, r2) in enumerate(zip(rows, rows2)):
        for col in ('row_id', 'blob_index', 'offset', 'en', 'ja'):
            if (r1.get(col) or '') != (r2.get(col) or ''):
                ok = False
                P('  [X] 行%d 列%s 变化' % (i, col))
        old_new = r1.get('zh_new') or ''
        exp = plan_map.get(i)
        if exp is None:
            if old_new != (r2.get('zh_new') or ''):
                ok = False
                diff_guard += 1
                if diff_guard <= 5:
                    P('  [X] 非目标行 zh_new 变化 row=%s' % r1.get('row_id'))
        else:
            if r2.get('zh_new') != exp:
                ok = False
                P('  [X] 目标行 zh_new 不符 row=%s' % r1.get('row_id'))
    if diff_guard == 0 and ok:
        P('  CSV 复核: 行数 %d / row_id+en+ja 全等 / 非目标行 zh_new 未动 / 目标行=期望  ✓' % len(rows2))
    md2 = json.load(open(MJ_P, encoding='utf-8'))
    md_bak = json.load(open(bak_mj, encoding='utf-8'))
    if set(md2.keys()) == set(md_bak.keys()):
        n_diff = sum(1 for k in md_bak if md_bak[k] != md2.get(k))
        if n_diff == m_changed:
            P('  ml 复核: 键集合不变 / 恰好 %d 条值变化  ✓' % n_diff)
        else:
            ok = False
            P('  [X] ml 值变化条数 %d != 期望 %d' % (n_diff, m_changed))
    else:
        ok = False
        P('  [X] ml 键集合变化')
    if not hl_ok:
        ok = False

    json.dump({'ts': TS, 'backs': {'csv': bak_csv, 'ml': bak_mj, 'hl': bak_hl},
               'csv_rows': n_changed, 'csv_places': n_places,
               'ml_rows': m_changed, 'ml_places': m_places},
              open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    P('')
    P('状态文件: fix_coo_state.json | 回滚: fix_coo.py revert')
    P('下一步: build_cn.py apply_menu 重装，再跑回归。')
    _flush()

def _flush():
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('OK ->', OUT)

if __name__ == '__main__':
    main()
