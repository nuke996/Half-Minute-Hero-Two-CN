# -*- coding: utf-8 -*-
"""存档当前状态 —— 在大改动（如 TODO-4 日式格式统一）之前先跑一次。

产物：
  outputs/text_v2.csv.bak_arch_<时间戳>
  _work/ui_always.json.bak_arch_<时间戳>
  outputs/存档记录.md（追加一行：时间 / 版本标签 / 两文件 SHA-256 前 16 位 / 行数 / 条目数）

用法：python snapshot.py [版本标签]      例如：python snapshot.py v2.47-格式统一前
"""
import os, sys, csv, json, shutil, time, hashlib
import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
CSV = paths.data('text_v2.csv')
UI = os.path.join(W, 'ui_always.json')
REC = paths.build('存档记录.md')

tag = sys.argv[1] if len(sys.argv) > 1 else '(未命名)'
ts = time.strftime('%Y%m%d_%H%M%S')

def sha16(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()[:16]

c_bak = paths.build('text_v2.csv.bak_arch_' + ts)
u_bak = paths.build('ui_always.json.bak_arch_' + ts)
shutil.copy2(CSV, c_bak)
shutil.copy2(UI, u_bak)

n_rows = sum(1 for _ in open(CSV, encoding='utf-8')) - 1
n_ui = len(json.load(open(UI, encoding='utf-8')))

line = ('| %s | %s | `%s` | `%s` | %d | %d |\n'
        % (ts, tag, sha16(c_bak), sha16(u_bak), n_rows, n_ui))
if not os.path.exists(REC):
    open(REC, 'w', encoding='utf-8').write(
        '# 存档记录（大改动前的基线）\n\n'
        '| 时间 | 标签 | text_v2.csv SHA256-16 | ui_always.json SHA256-16 | CSV 行数 | ui_always 条目 |\n'
        '|---|---|---|---|---|---|\n')
with open(REC, 'a', encoding='utf-8') as f:
    f.write(line)

print('已存档：')
print('  text_v2.csv      -> %s  (SHA256-16 %s, %d 行)' % (os.path.basename(c_bak), sha16(c_bak), n_rows))
print('  ui_always.json   -> %s  (SHA256-16 %s, %d 条)' % (os.path.basename(u_bak), sha16(u_bak), n_ui))
print('  记录 -> outputs/存档记录.md')
print('')
print('要还原到这次存档：把上面两个 .bak_arch_<时间戳> 拷回原名，再跑 build_cn.py revert && apply_menu')
