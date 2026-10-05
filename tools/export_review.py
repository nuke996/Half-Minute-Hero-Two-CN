# -*- coding: utf-8 -*-
"""校对导出：把可校对的译文导出成 Excel 友好格式（UTF-8 BOM CSV）。
生成 _work/校对/ 下的两个文件：
  单行译文.csv  —— text_v2.csv 中"有译文"的行（含 UI/菜单/系统消息等）
  多行译文.csv  —— ml_zh_fields.json 的整段多行对话（显示优先走这里）
约定：修订译文列留空 = 不改；填 (清空) = 恢复原文；¶ 代表换行（勿删）。
多行字段的行会在单行文件"提示"列标注 —— 显示走多行文件，改它才有效。
"""
import os, csv, json, sys

import paths
BASE = paths.GAME_DIR
WORK = paths.DATA_DIR
OUTDIR = paths.build('校对')
NL = '¶'          # 换行占位（用户可见）
CLEAR = '(清空)'   # 恢复原文关键字

sys.path.insert(0, WORK)
os.chdir(WORK)
import build_cn as B   # v2.30: 显示基线 = apply_repl 压平（与游戏实际显示一致）

os.makedirs(OUTDIR, exist_ok=True)

# ---------- 1) 单行译文 ----------
csv_path = paths.data('text_v2.csv')
rows = list(csv.DictReader(open(csv_path, encoding='utf-8', newline='')))

ml = json.load(open(os.path.join(WORK, 'ml_zh_fields.json'), encoding='utf-8'))
ml_lines = {}
for key in ml:
    for ln in str(key).split('\n'):
        if ln and ln not in ml_lines:
            ml_lines[ln] = key

n_single = n_marked = 0
out1 = os.path.join(OUTDIR, '单行译文.csv')
with open(out1, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['编号(勿动)', '原文位置(勿动)', '字数上限', '提示', '英文原文',
                '日文原文', '当前译文', '修订译文(留空=不改)'])
    for r in rows:
        zh_new = r.get('zh_new') or ''
        zh_3dm = r.get('zh_3dm') or ''
        eff = zh_new if zh_new else zh_3dm
        if not eff:
            continue          # 无译文行（原文保留/机制保护）不导出，防误改
        en = r.get('en') or ''
        tip = '⚠多行字段,显示请改[多行译文]文件' if (en and en in ml_lines) else ''
        if tip:
            n_marked += 1
        # v2.30: 显示压平后的文本（= 游戏里实际显示的样子），校对时所见即所得
        w.writerow([r['row_id'], 'blob ' + r['blob_index'], r['max_cn'], tip,
                    en, r.get('ja') or '', B.apply_repl(eff), ''])
        n_single += 1

# ---------- 2) 多行译文 ----------
n_multi = 0
out2 = os.path.join(OUTDIR, '多行译文.csv')
with open(out2, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['编号(勿动)', '英文原文(勿动)', '当前译文', '修订译文(留空=不改)'])
    for i, (key, val) in enumerate(ml.items(), 1):
        # v2.30: 压平后再换 ¶ 占位（显示与游戏一致）
        w.writerow(['M%d' % i, str(key).replace('\n', NL),
                    B.apply_repl(str(val)).replace('\n', NL), ''])
        n_multi += 1

# ---------- 使用说明 ----------
readme = os.path.join(OUTDIR, '使用说明.txt')
open(readme, 'w', encoding='utf-8').write('''【译文校对 · 使用说明】

一、这套文件是干什么的
  单行译文.csv —— 游戏 90% 的文字：菜单、系统消息、单行对话、物品说明等。
  多行译文.csv —— 一次显示好几行的对话整段（显示时优先用它）。
  英文/日文原文列只是给你对照意思用的，改不改它们都不生效。

二、怎么改（用 Excel 或 WPS 打开）
  1. 只在最后一列「修订译文(留空=不改)」里写字。
     留空 = 这行保持原样，绝不会误伤其他行。
  2. 「当前译文」就是游戏现在的文字，方便你对照。
  3. 修改后保存（保持 CSV 格式、UTF-8 编码，WPS/Excel 默认保存即可）。
  4. 改完双击游戏目录里的「汉化-导入校对.bat」，自动装进游戏并出报告。
  5. 改坏了想反悔：双击「汉化-导入校对-回滚.bat」恢复到导入前。

三、特殊写法
  (清空)   —— 填在修订列 = 这行恢复显示原文（日文/英文）。
  ¶        —— 多行译文里的换行符号，代表"在这里换行"，千万别删，
              想多一行就在中间多写一个 ¶。
  每行字数别超过「字数上限」列的数字（导入时会自动检查，超长会被拒装并提示）。

四、注意
  提示列写着「⚠多行字段」的行：游戏显示走「多行译文.csv」，
  想改它请去多行文件里改（按英文原文能对上）。
  不要增删行、不要改「勿动」列，其他列想看看没关系。
  改动数量没有限制，一行也可以，几千行也行。

五、安全
  每次「导入」都会先自动备份当前译表，随时可回滚；
  导入前请先关闭游戏（游戏开着会装不进去，报告里会提醒你）。
''')

print('done')
print('single rows: %d (marked multi-line first-row: %d)' % (n_single, n_marked))
print('multi fields: %d' % n_multi)
print('out: %s' % OUTDIR)
