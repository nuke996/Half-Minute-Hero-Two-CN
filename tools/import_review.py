# -*- coding: utf-8 -*-
"""校对导入：读 translator-view/*.json 的 zh，写回译表，自检后刷新 dist。

约定：
  · 只认每条记录的 "zh" 字段；与当前值相同 = 未改动；清空 = 恢复显示原文。
  · 单行条目不允许换行；多行整字段与 DLC 多行条目允许换行。
  · JSON 必须保持 UTF-8 编码（带 BOM 亦可）。

自检（有任一错误即【中断】：不写译表、不打包，并输出日志指明是哪一条）：
  · 超长：编码字节数超过该槽位上限（装机时会被静默截断）
  · id 无法识别 / 找不到对应字段（导出后又改过译表，或 id 被改动）
  · JSON 结构损坏、非法控制字符、单行条目含换行

通过自检后：
  1) 备份译表 → 写回 text_v2.csv / ml_zh_fields.json / dlc/*.tsv / dlc/zh_07.json
  2) 运行 tools/build.py package（隔离模式）刷新 dist/，**不改游戏目录**

模式：apply（默认）/ revert（恢复上次导入前的译表并重新刷新 dist）。
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

import paths
import review_lib as R

TOOLS = os.path.dirname(os.path.abspath(__file__))
WORK = paths.DATA_DIR
TV = os.path.join(WORK, 'translator-view')
RDIR = paths.build('校对')
os.makedirs(RDIR, exist_ok=True)
CSV_P = paths.data('text_v2.csv')
MJ_P = os.path.join(WORK, 'ml_zh_fields.json')
DLC_DIR = paths.data('dlc')
STATE = os.path.join(RDIR, '_import_state.json')
RPT = os.path.join(RDIR, '导入报告.txt')

sys.path.insert(0, TOOLS)
sys.path.insert(0, WORK)
os.chdir(WORK)
import build_cn as B

L = []
def P(s=''):
    L.append(str(s))


def now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _flush():
    open(RPT, 'w', encoding='utf-8').write('\n'.join(L))
    print('OK ->', RPT)


def collect_files():
    """(路径, 是否 protected) 列表：单行分片 + 多行 + DLC。"""
    out = []
    for base, prot in ((TV, False), (os.path.join(TV, 'protected'), True)):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.endswith('.json'):
                continue
            # 普通分片：10_*/20_*；受保护分片：prot_*（命名与外层不同，避免混用）
            if name.startswith('prot_') if prot else name[:2] in ('10', '20'):
                out.append((os.path.join(base, name), prot))
    for name in ('30_multiline.json', '40_dlc01.json'):
        p = os.path.join(TV, name)
        if os.path.exists(p):
            out.append((p, False))
    return out


def bad_chars(s, allow_nl):
    """非法控制字符：<0x20 且非 \\n（allow_nl=True 时 \\n 合法）。返回命中的字符列表。"""
    bad = []
    for ch in s:
        o = ord(ch)
        if o < 0x20 and not (ch == '\n' and allow_nl):
            if ch == '\r':
                bad.append('\\r')
            elif ch == '\t':
                bad.append('\\t')
            else:
                bad.append('U+%04X' % o)
    return bad


def run_package():
    p = subprocess.run([sys.executable, os.path.join(TOOLS, 'build.py'), 'package'],
                       capture_output=True)
    return (p.returncode, p.stdout.decode('utf-8', 'replace'),
            p.stderr.decode('utf-8', 'replace'))


def do_apply():
    P('==== 校对导入报告  %s ====' % now())
    files = collect_files()
    if not files:
        P('没找到校对文件（%s）。请先双击同目录的「汉化-导出校对.bat」生成，改完再导入。'
          % TV)
        _flush(); return

    rows = R.load_rows()
    by_rid = {r['row_id']: r for r in rows}
    rcaps = R.row_caps(rows)
    md = json.load(open(MJ_P, encoding='utf-8'))
    stage, missing = R.ensure_stage()
    if not stage:
        P('[提醒] 缺少原版文件（%s）：多行/DLC 的容量自检将退回 JSON 里的 meta。' % ', '.join(missing))
    mlm = R.ml_meta(stage) if stage else {}
    dcaps = R.dlc_caps()

    edits = []       # (描述, 目标类型, 定位, 新值, 是否受保护)
    errs = []        # (描述, 原因)
    repl_hits = []   # (描述, 原文, 替换后)
    unchanged = 0

    def add(kind, loc, new, desc, is_prot, cap_bytes=None, after_nl=False):
        """统一登记一条修订（含 REPL 命中记录与超长检查）。"""
        eff = B.apply_repl(new)
        if eff != new:
            repl_hits.append((desc, new, eff))
        if cap_bytes is not None:
            n = R.byte_est(eff)
            if n > cap_bytes:
                errs.append((desc, '超长：编码 %d 字节 > 上限 %d 字节（装机时会被截断），请缩短 %d 字节'
                             % (n, cap_bytes, n - cap_bytes)))
                return
        edits.append((desc, kind, loc, new, is_prot))

    # ---- 单行 / 受保护 ----
    for path, is_prot in files:
        name = os.path.relpath(path, TV)
        if name in ('30_multiline.json', '40_dlc01.json'):
            continue
        try:
            d = json.load(open(path, encoding='utf-8-sig'))
        except Exception as ex:
            errs.append((name, '无法解析（JSON 损坏或非 UTF-8）：%s' % ex))
            continue
        ents = d.get('entries')
        if not isinstance(ents, list):
            errs.append((name, '结构损坏：entries 不是数组，请重新导出'))
            continue
        for e in ents:
            eid = str(e.get('id') or '')
            if not eid.startswith('row::'):
                if eid:
                    errs.append((eid, '无法识别的 id（%s）' % name))
                continue
            rid = eid[5:]
            tr = by_rid.get(rid)
            if tr is None:
                errs.append((eid, '编号无法识别（译表已更新？请重新导出校对文件）'))
                continue
            if e.get('zh') is None:
                continue
            new = B.strip_ascii_ws(str(e['zh']))
            cur = B.apply_repl(tr.get('zh_new') or '')
            if new == cur:
                unchanged += 1
                continue
            desc = '单行 %s' % eid
            bad = bad_chars(new, False)
            if '\n' in new and not bad:
                bad.append('\\n')
            if bad:
                errs.append((desc, '含不允许的字符 %s（单行条目不能换行）' % ' '.join(bad)))
                continue
            sb = rcaps.get(rid, (None, None))[0]
            add('row', tr, new, desc, is_prot, cap_bytes=sb)

    # ---- 多行整字段 ----
    mlp = os.path.join(TV, '30_multiline.json')
    if os.path.exists(mlp):
        try:
            d = json.load(open(mlp, encoding='utf-8-sig'))
            ents = d.get('entries') or []
        except Exception as ex:
            errs.append(('30_multiline.json', '无法解析：%s' % ex)); ents = []
        for e in ents:
            key = e.get('en')
            if key not in md:
                errs.append((str(e.get('id') or '?'), '找不到对应多行字段（en 可能被改动，请重新导出）'))
                continue
            if e.get('zh') is None:
                continue
            new = str(e['zh'])
            if new == B.apply_repl(str(md[key])):
                unchanged += 1
                continue
            desc = '多行 %s…' % key[:16].replace('\n', '¶')
            bad = bad_chars(new, True)
            if bad:
                errs.append((desc, '含不允许的字符 %s' % ' '.join(bad)))
                continue
            cap = (mlm.get(key) or {}).get('cap_bytes')
            if cap is None:
                cap = (e.get('meta') or {}).get('cap_bytes')
            add('ml', key, new, desc, False, cap_bytes=cap)

    # ---- DLC01 ----
    dlp = os.path.join(TV, '40_dlc01.json')
    if os.path.exists(dlp):
        try:
            d = json.load(open(dlp, encoding='utf-8-sig'))
            ents = d.get('entries') or []
        except Exception as ex:
            errs.append(('40_dlc01.json', '无法解析：%s' % ex)); ents = []
        per_file = {}
        for e in ents:
            eid = str(e.get('id') or '')
            parts = eid.split('::')
            if len(parts) != 3 or parts[0] != 'dlc':
                errs.append((eid or '?', '无法识别的 DLC id')); continue
            fn, n = parts[1], parts[2]
            m = (e.get('meta') or {})
            cap = dcaps.get(e.get('ja')) or m.get('cap_bytes')
            if e.get('zh') is None:
                continue
            new = str(e['zh'])
            if fn in ('zh_01', 'zh_02', 'zh_03', 'zh_04', 'zh_05', 'zh_06'):
                p = os.path.join(DLC_DIR, fn + '.tsv')
                if not os.path.exists(p):
                    errs.append((eid, '源文件 %s.tsv 不存在' % fn)); continue
                lines = per_file.get(fn)
                if lines is None:
                    lines = open(p, encoding='utf-8-sig').read().splitlines()
                    per_file[fn] = lines
                try:
                    idx = int(n) - 1
                except Exception:
                    errs.append((eid, '序号非法')); continue
                if idx < 0 or idx >= len(lines):
                    errs.append((eid, '序号越界（%s.tsv 只有 %d 行，可能被改动）' % (fn, len(lines))))
                    continue
                ja, sep, old = lines[idx].partition('\t')
                if not sep or ja != e.get('ja'):
                    errs.append((eid, '原文对不上（%s.tsv 第 %d 行已改动？）' % (fn, int(n))))
                    continue
                if new == old:
                    unchanged += 1; continue
                bad = bad_chars(new, False)
                if bad or '\n' in new:
                    errs.append((eid, '含不允许的字符 %s（DLC 单行条目不能换行）' % ' '.join(bad)))
                    continue
                add('dlc_tsv', (fn, idx), new, eid, False,
                    cap_bytes=(cap if cap is not None else None))
            elif fn == 'zh_07':
                p7 = os.path.join(DLC_DIR, 'zh_07.json')
                if not os.path.exists(p7):
                    errs.append((eid, 'zh_07.json 不存在')); continue
                d7 = per_file.get('zh_07')
                if d7 is None:
                    d7 = json.load(open(p7, encoding='utf-8'))
                    per_file['zh_07'] = d7
                key = e.get('ja')
                if key not in d7:
                    errs.append((eid, 'zh_07.json 里找不到该原文（可能被改动）')); continue
                if new == d7[key]:
                    unchanged += 1; continue
                bad = bad_chars(new, True)
                if bad:
                    errs.append((eid, '含不允许的字符 %s' % ' '.join(bad)))
                    continue
                add('dlc_json', key, new, eid, False, cap_bytes=cap)
            else:
                errs.append((eid, '未知 DLC 源 %s' % fn))

    # ---- 报告：清点 ----
    P('')
    P('一、改动清点')
    P('  收到有效修订: %d 处（未改动 %d 处）' % (len(edits), unchanged))
    n_prot = sum(1 for _d, _k, _l, _n, pr in edits if pr)
    if n_prot:
        P('  其中受保护(protected/)条目 %d 处 —— 会写进译表保存，但当前不会上屏。' % n_prot)

    # ---- 自检：有错即中断 ----
    if errs:
        P('')
        P('二、自检未通过 —— 已中断（未写译表、未打包）')
        P('  错误 %d 条，请修正后重新运行 汉化-导入校对.bat：' % len(errs))
        for t, why in errs[:60]:
            P('    ✗ %s —— %s' % (t, why))
        if len(errs) > 60:
            P('    …（其余 %d 条略）' % (len(errs) - 60))
        P('')
        P('  修好后再导入。为避免误装，本次一个字节都没有写入。')
        _flush(); return

    if not edits:
        P('')
        P('没有需要应用的修订，译表与 dist 保持原样。')
        _flush(); return

    if repl_hits:
        P('')
        P('  [说明] %d 处译文命中替换词典（字库容量→近义词替换），实际显示按右边一列为准：'
          % len(repl_hits))
        for t, old, new in repl_hits[:15]:
            P('    %s: %r -> %r' % (t, old[:26], new[:26]))
        if len(repl_hits) > 15:
            P('    …（其余 %d 处略；规则见 dict/替换词典.json）' % (len(repl_hits) - 15))

    # ---- 备份 + 写回 ----
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    touched = {CSV_P, MJ_P}
    for _d, kind, loc, _n, _p in edits:
        if kind == 'dlc_tsv':
            touched.add(os.path.join(DLC_DIR, loc[0] + '.tsv'))
        elif kind == 'dlc_json':
            touched.add(os.path.join(DLC_DIR, 'zh_07.json'))
    backs = {}
    for path in sorted(touched):
        if os.path.exists(path):
            bak = path + '.bak_review_' + ts
            shutil.copy2(path, bak)
            backs[path] = bak

    n_row = n_ml = n_dl = 0
    dlc_mod = {}
    for _d, kind, loc, new, _p in edits:
        if kind == 'row':
            loc['zh_new'] = new
            n_row += 1
        elif kind == 'ml':
            md[loc] = new
            n_ml += 1
        elif kind == 'dlc_tsv':
            dlc_mod.setdefault(loc[0], {})[loc[1]] = new
            n_dl += 1
        elif kind == 'dlc_json':
            d7 = per_file['zh_07']
            d7[loc] = new
            n_dl += 1

    import csv as _csv
    with open(CSV_P, 'w', encoding='utf-8', newline='') as f:
        w = _csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(MJ_P, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(md, f, ensure_ascii=False, indent=1)
        f.write('\n')
    for fn, mods in dlc_mod.items():
        if fn == 'zh_07':
            with open(os.path.join(DLC_DIR, 'zh_07.json'), 'w', encoding='utf-8', newline='\n') as f:
                json.dump(d7, f, ensure_ascii=False, indent=0)
                f.write('\n')
        else:
            p = os.path.join(DLC_DIR, fn + '.tsv')
            lines = per_file[fn]
            for idx, val in mods.items():
                ja = lines[idx].partition('\t')[0]
                lines[idx] = ja + '\t' + val
            with open(p, 'w', encoding='utf-8-sig', newline='\n') as f:
                f.write('\n'.join(lines) + '\n')

    json.dump({'ts': ts, 'backs': backs, 'n_row': n_row, 'n_ml': n_ml, 'n_dlc': n_dl},
              open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    P('')
    P('三、写入译表')
    P('  单行 %d 处 / 多行 %d 处 / DLC %d 处' % (n_row, n_ml, n_dl))
    P('  备份: %s 等 %d 个文件（时间戳 %s）' % (os.path.basename(CSV_P), len(backs), ts))

    # ---- 刷新 dist（隔离打包，不动游戏目录）----
    P('')
    P('四、刷新 dist（隔离打包）')
    rc, out, err = run_package()
    for ln in out.splitlines():
        s = ln.strip()
        if any(k in s for k in ('已改', '打包完成', '打包中止', 'staging', '母本',
                                '空槽', '溢出', '覆盖', '写入', 'DLC01')):
            P('  ' + s)
    if rc != 0:
        P('  [X] 打包失败（退出码 %s）。译表已写入，可运行「汉化-导入校对-回滚.bat」恢复。'
          % rc)
        open(paths.build('_review_package_err.txt'), 'w', encoding='utf-8').write(
            out + '\n--- STDERR ---\n' + err)
        P('      错误详情: %s' % paths.build('_review_package_err.txt'))
    else:
        P('  ✓ 打包完成，dist/ 已刷新。')
    P('')
    P('五、如何在游戏里看效果')
    P('  本次导入不改游戏目录。想立刻进游戏验证，请双击游戏目录里的「汉化-安装.bat」装机。')
    P('  想撤销本次导入：双击 translator-view 目录里的「汉化-导入校对-回滚.bat」。')
    _flush()


def do_revert():
    P('==== 校对导入回滚  %s ====' % now())
    if not os.path.exists(STATE):
        P('没找到导入记录（从未导入过，或已回滚）。无需操作。')
        _flush(); return
    st = json.load(open(STATE, encoding='utf-8'))
    n = 0
    for path, bak in st['backs'].items():
        if os.path.exists(bak):
            shutil.copy2(bak, path)
            P('  已恢复 %s' % os.path.basename(path))
            n += 1
    os.remove(STATE)
    P('  共恢复 %d 个文件。' % n)
    P('')
    P('  重新刷新 dist（隔离打包）…')
    rc, out, err = run_package()
    for ln in out.splitlines():
        s = ln.strip()
        if any(k in s for k in ('已改', '打包完成', '打包中止', '空槽', '溢出')):
            P('  ' + s)
    P('  %s' % ('✓ dist 已按回滚后的译表刷新。' if rc == 0 else '[X] 打包失败（退出码 %s）' % rc))
    _flush()


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'apply'
    if mode == 'revert':
        do_revert()
    else:
        do_apply()
