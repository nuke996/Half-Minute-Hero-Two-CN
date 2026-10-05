# -*- coding: utf-8 -*-
"""校对导入：把用户在 校对/单行译文.csv、校对/多行译文.csv 里填的"修订译文"
合并回 text_v2.csv / ml_zh_fields.json，然后自动重装进游戏并生成大白话报告。

约定：
  修订列留空 = 不改；填 (清空) = 恢复原文；¶ = 换行。
  只认"修订译文"列；"当前译文"列改动不会被应用（会提醒）。
安全：
  - 应用前 REPL 写平（apply_repl），保证 CSV 登记值 == 装机显示值（铁律）。
  - 写回前备份三表 *.bak_import_时间戳，可 revert。
  - 单行容量预检（len > max_cn 拒装并提示缩短）。
  - Excel "另存为"会把文件转成 GBK 且丢失 ♪/¶ —— 健康检查拦下并给出解法。
  - 装机前检测 HMH2.exe 是否被占用（游戏开着会拒绝）。
模式：apply（默认）/ revert（恢复最近一次导入前的译表并重装）。
"""
import os, sys, csv, json, shutil, subprocess, datetime, io

import paths
BASE = paths.GAME_DIR
WORK = paths.DATA_DIR
RDIR = paths.build('校对')
CSV_P = paths.data('text_v2.csv')
MJ_P = os.path.join(WORK, 'ml_zh_fields.json')
EXE = os.path.join(BASE, 'HMH2.exe')
NL, CLEAR = '¶', '(清空)'
PY = sys.executable
BUILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_cn.py')

sys.path.insert(0, WORK)
os.chdir(WORK)
import build_cn as B          # 复用 REPL（apply_repl）

RPT = os.path.join(RDIR, '导入报告.txt')
L = []
def P(s=''): L.append(str(s))

def smart_read(path):
    """utf-8-sig 优先，Excel 另存出的 GBK 兜底。返回 (text, 编码)。"""
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'gbk'):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError('未知编码', b'', 0, 1, 'decode fail')

def read_rows(path):
    text, enc = smart_read(path)
    return list(csv.DictReader(io.StringIO(text))), enc

def game_locked():
    try:
        f = open(EXE, 'r+b'); f.close()
        return False
    except PermissionError:
        return True

def run_install():
    p = subprocess.run([PY, BUILD, 'apply_menu'], capture_output=True)
    out = p.stdout.decode('utf-8', 'replace')
    err = p.stderr.decode('utf-8', 'replace')
    return p.returncode, out, err

def do_apply():
    P('==== 校对导入报告  %s ====' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    # ---------- 读库 ----------
    rows = list(csv.DictReader(open(CSV_P, encoding='utf-8', newline='')))
    md = json.load(open(MJ_P, encoding='utf-8'))
    by_rid = {r['row_id']: r for r in rows}

    # ---------- 读校对文件 ----------
    f1 = os.path.join(RDIR, '单行译文.csv')
    f2 = os.path.join(RDIR, '多行译文.csv')
    if not (os.path.exists(f1) or os.path.exists(f2)):
        P('没找到校对文件（%s）。请先双击「汉化-导出校对.bat」生成，改完再导入。' % RDIR)
        _flush(); return

    # 健康检查：Excel 另存为 GBK 会把 ♪/¶ 变问号
    for path, kind in ((f1, '单行'), (f2, '多行')):
        if not os.path.exists(path):
            continue
        text, enc = smart_read(path)
        if enc != 'utf-8-sig':
            P('[提醒] %s 不是 UTF-8 编码（%s，多半是 Excel"另存为"导致）。'
              '已按 %s 兼容读取，但原文件里的音符♪等符号可能已丢失。' % (os.path.basename(path), enc, enc))
        lib_notes = 0
        if kind == '单行':
            rd = list(csv.DictReader(io.StringIO(text)))
            for r in rd:
                lib_notes += ((by_rid.get(r.get('编号(勿动)', ''), {}).get('zh_new') or
                               by_rid.get(r.get('编号(勿动)', ''), {}).get('zh_3dm') or '')
                              ).count('♪')
            file_notes = sum(str(r.get('当前译文', '')).count('♪') for r in rd)
        else:
            rd = list(csv.DictReader(io.StringIO(text)))
            file_notes = sum(str(r.get('当前译文', '')).count(NL) for r in rd)
            lib_notes = sum(str(v).count('\n') for v in md.values())
        if lib_notes >= 10 and file_notes < lib_notes * 0.5:
            P('')
            P('[X] 编码健康检查未通过：%s 里特殊符号大量丢失（♪/换行符）。' % kind)
            P('    直接导入会把损坏文字装进游戏，已终止。解决办法：')
            P('    用记事本打开该文件 → 另存为 → 编码选 UTF-8 → 覆盖保存，再重新导入。')
            _flush(); return

    # ---------- 收集修订 ----------
    ok = []          # (target描述, 库定位, final, rev)
    reject = []      # (描述, 原因)
    repl_hits = []   # 被 REPL 规则改写的
    curcol_edits = 0

    if os.path.exists(f1):
        rd, _ = read_rows(f1)
        for r in rd:
            rid = (r.get('编号(勿动)') or '').strip()
            rev = (r.get('修订译文(留空=不改)') or '').strip()
            cur = (r.get('当前译文') or '').strip()
            tr = by_rid.get(rid)
            if tr is None:
                if rid:
                    reject.append(('单行 编号%s' % rid, '编号无法识别（可能被改动）'))
                continue
            eff = (tr.get('zh_new') or tr.get('zh_3dm') or '')
            eff_disp = B.apply_repl(eff)   # v2.30: 基线=游戏实际显示（压平后），与导出的"当前译文"列同口径
            if cur != eff_disp.strip():
                curcol_edits += 1
            if not rev or rev == eff_disp.strip():
                continue
            if rev == CLEAR:
                ok.append(('单行 编号%s' % rid, ('row', tr), '', rev))
                continue
            try:
                cap = int(tr.get('max_cn') or '-1')
            except ValueError:
                cap = -1
            if cap >= 0 and len(rev) > cap:
                reject.append(('单行 编号%s（%s…）' % (rid, rev[:12]), '共 %d 字，超过上限 %d 字，请缩短' % (len(rev), cap)))
                continue
            final = B.apply_repl(rev)
            if final != rev:
                repl_hits.append(('单行 编号%s' % rid, rev, final))
            ok.append(('单行 编号%s' % rid, ('row', tr), final, rev))

    if os.path.exists(f2):
        rd, _ = read_rows(f2)
        for r in rd:
            key = (r.get('英文原文(勿动)') or '').replace(NL, '\n')
            rev = (r.get('修订译文(留空=不改)') or '').replace(NL, '\n').strip()
            cur = (r.get('当前译文') or '')
            if key not in md:
                if key:
                    reject.append(('多行 %s…' % key[:20].replace('\n', '¶'), '找不到对应字段（英文原文列可能被改动）'))
                continue
            eff = str(md[key])
            eff_disp = B.apply_repl(eff)   # v2.30: 基线=游戏实际显示（压平后）
            if not rev or rev == eff_disp.strip():
                continue
            if rev == CLEAR:
                ok.append(('多行 %s…' % key[:20].replace('\n', '¶'), ('ml', key), '', rev))
                continue
            final = B.apply_repl(rev)
            if final != rev:
                repl_hits.append(('多行 %s…' % key[:20].replace('\n', '¶'), rev, final))
            ok.append(('多行 %s…' % key[:20].replace('\n', '¶'), ('ml', key), final, rev))

    P('')
    P('一、改动清点')
    P('  收到有效修订: %d 处（单行+多行）' % len(ok))
    if curcol_edits:
        P('  [提醒] 有 %d 行你把字改在了「当前译文」列——那一列只是对照用，没有生效。' % curcol_edits)
        P('         想改的话请把新文字填到「修订译文(留空=不改)」列再导入一次。')
    if not ok:
        P('  没有需要应用的修订，游戏文件保持原样，无需重装。')
        _flush(); return
    if reject:
        P('  拒绝 %d 处（未装入游戏）:' % len(reject))
        for t, why in reject[:30]:
            P('    ✗ %s —— %s' % (t, why))
        if len(reject) > 30:
            P('    …（其余 %d 处见略）' % (len(reject) - 30))
    if repl_hits:
        P('  [说明] 有 %d 处译文触发了游戏内置的旧替换规则（历史缺字时期的词级替换），' % len(repl_hits))
        P('         实际显示会按下面右边一列来，属正常现象:')
        for t, old, new in repl_hits[:20]:
            P('    %s: %r -> %r' % (t, old[:30], new[:30]))
        if len(repl_hits) > 20:
            P('    …（其余 %d 处见略）' % (len(repl_hits) - 20))

    # ---------- 备份 + 写回 ----------
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backs = {}
    for tag, path in (('csv', CSV_P), ('ml', MJ_P)):
        bak = path + '.bak_import_' + ts
        shutil.copy2(path, bak)
        backs[tag] = bak
    n_row = n_ml = 0
    for _t, loc, final, _rev in ok:
        if loc[0] == 'row':
            loc[1]['zh_new'] = final
            n_row += 1
        else:
            md[loc[1]] = final
            n_ml += 1
    with open(CSV_P, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json.dump(md, open(MJ_P, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump({'ts': ts, 'backs': backs, 'n_row': n_row, 'n_ml': n_ml},
              open(os.path.join(RDIR, '_import_state.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    P('')
    P('二、写入译表')
    P('  已更新 单行 %d 处 / 多行 %d 处' % (n_row, n_ml))
    P('  备份: text_v2.csv%s 等两个文件（时间戳 %s）' % ('', ts))

    # ---------- 装机 ----------
    P('')
    P('三、装进游戏')
    if game_locked():
        P('  [X] 游戏好像正开着（HMH2.exe 被占用）。译表已保存，')
        P('      请先完全退出游戏，再双击一次「汉化-导入校对.bat」即可完成安装。')
        _flush(); return
    rc, out, err = run_install()
    for ln in out.splitlines():
        if any(k in ln for k in ('覆盖', 'slot', '溢出', '空槽', '写入', '孪生', '地名', '完成', '错误', 'Traceback')):
            P('  ' + ln.strip())
    if rc != 0 or 'Traceback' in err:
        P('  [X] 安装过程报错（错误详情见 _work/_apply_err.txt）。译表改动已保存，')
        P('      可运行「汉化-导入校对-回滚.bat」恢复。把报告发给小W可以帮忙排查。')
        open(paths.build('_apply_err.txt'), 'w', encoding='utf-8').write(out + '\n--- STDERR ---\n' + err)
    else:
        if '溢出 0' not in out:
            P('  [X] 检测到溢出不是 0！可能有译文超长被截断，建议回滚后缩短该译文。')
        else:
            P('  ✓ 安装完成，无溢出。进游戏看效果吧！')
    P('')
    P('四、回滚方式')
    P('  双击「汉化-导入校对-回滚.bat」→ 恢复本次导入前的译表并重新安装。')
    _flush()

def do_revert():
    P('==== 校对导入回滚  %s ====' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    stf = os.path.join(RDIR, '_import_state.json')
    if not os.path.exists(stf):
        P('没找到导入记录（从未导入过，或已回滚）。无需操作。')
        _flush(); return
    st = json.load(open(stf, encoding='utf-8'))
    for tag, bak in st['backs'].items():
        dst = CSV_P if tag == 'csv' else MJ_P
        if os.path.exists(bak):
            shutil.copy2(bak, dst)
            P('  已恢复 %s <- %s' % (os.path.basename(dst), os.path.basename(bak)))
    os.remove(stf)
    if game_locked():
        P('  [X] 游戏正开着，请先退出游戏再运行一次本回滚（译表文件已恢复，重装还没做）。')
        _flush(); return
    rc, out, err = run_install()
    P('  重装: %s' % ('完成 ✓' if rc == 0 else '失败 ✗（详情 _work/_apply_err.txt）'))
    if rc != 0:
        open(paths.build('_apply_err.txt'), 'w', encoding='utf-8').write(out + '\n--- STDERR ---\n' + err)
    P('  游戏已恢复到导入前的状态。')
    _flush()

def _flush():
    open(RPT, 'w', encoding='utf-8').write('\n'.join(L))
    print('OK ->', RPT)

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'apply'
    if mode == 'revert':
        do_revert()
    else:
        do_apply()
