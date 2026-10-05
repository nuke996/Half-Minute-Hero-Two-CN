# -*- coding: utf-8 -*-
"""用 v2.27 装机时的 CSV（修复前备份）临时换入，跑 verify_v223 / verify_q47，
验证已装文件正确、此前 verify 失败纯属 cmap 与新 CSV 错位。跑完恢复新 CSV（finally 保证）。"""
import os, json, shutil, subprocess

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
PY = sys.executable

st = json.load(open(paths.build('fix954_state.json'), encoding='utf-8'))
CSV = paths.data('text_v2.csv')
BAK = st['csv_backup']
TMP = CSV + '.swap_tmp'

shutil.copy2(CSV, TMP)          # 新表（82行已清空）暂存
shutil.copy2(BAK, CSV)          # v2.27 状态的表就位
try:
    r1 = subprocess.run([PY, 'runner.py', 'verify_v223.py'], cwd=W, capture_output=True, text=True)
    r2 = subprocess.run([PY, 'runner.py', 'verify_q47.py'], cwd=W, capture_output=True, text=True)
    open(paths.build('swap_verify_run.txt'), 'w', encoding='utf-8').write(
        'v223 rc=%s\n%s\n\nq47 rc=%s\n%s\n' % (r1.returncode, r1.stdout, r2.returncode, r2.stdout))
finally:
    shutil.copy2(TMP, CSV)      # 恢复新表
    os.remove(TMP)

# 复核：恢复后的 CSV 应是"82行清空"状态
import csv as _csv
rows = list(_csv.reader(open(CSV, encoding='utf-8-sig', newline='')))
n954 = sum(1 for r in rows if len(r) >= 10 and r[1] == '954')
left = sum(1 for r in rows if len(r) >= 10 and r[1] == '954' and (r[8] or r[9]))
open(paths.build('swap_verify_run.txt'), 'a', encoding='utf-8').write(
    'CSV已恢复: 总行数=%d blob954行=%d 残留译文=%d\n' % (len(rows), n954, left))
print('ok')
