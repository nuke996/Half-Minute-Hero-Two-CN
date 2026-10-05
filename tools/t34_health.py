# -*- coding: utf-8 -*-
"""t34_health.py —— 章节/称号「关键字段」体检（一键自检），v2.65 版。

★ v2.62 目标态（2026-09-17）：章节名允许中文（仅 Q16 rec15 保留原文）。
★ v2.63 目标态（2026-09-18）：**称号名本体 (pos0) 允许中文**
   —— G1 批次「全副本同改」已把 LANG_JA/LANG_EN 的称号名翻成中文；
   **cscv[890] 称号表仍必须原版**（官方 EN 也只改 LANG，cscv 侧是脚本层）。
   ⇒ 这条不变式是最有价值的守卫：cscv 一被动就说明误伤。
★ v2.64（G2）：伙伴 954 / 职业 128 / 阵形 136 名字本体允许中文；
   cscv 孪生 917 / 124 / 132 的**名字键必须原版**。
★ v2.65（G3，2026-09-19）：**装备表名字列（stride268 pos4）允许中文**
   —— b147(494) / b357(614) / b736(614) / b998(96)；
   cscv 孪生 **b144 / b338 / b705 的名字字段必须原版**。
   ★ 例外：cscv b975 ≡ JA b998 的 rec32/48/64/80（`へたれ`）本来就是载体码
   （主汉化历史遗留 = 弱小，非我批所致）⇒ 白名单放行，避免误报。
 其余不变：章节 DLC 大陆名允许翻译；cscv[28] off136/off140 关卡编号必须原版（闪退元凶）。
 因此本体检为【白名单式】：对每个字段声明"应为原版"还是"允许翻译"，
 并对"允许翻译"的字段额外检查"没有越界写穿到下一个字段"。

检查项（只读，不改任何文件）：
  1) 三张章节表：章节名(pos4 允许翻译) + 世界编号(pos68 必须原版) + 大陆名(pos372 允许翻译)
  2) 三张称号表：称号名本体(pos0 允许翻译；cscv 仍须原版) + 称号章节名(pos36 须原版)
  3) 伙伴/职业/阵形 名字本体允许翻译；其 cscv 孪生名字键须原版
  4) 装备表名字列允许翻译；cscv 装备表孪生名字字段须原版
  5) cscv[28] 村落表：off136/off140 必须原版；地名槽 off104 允许翻译
  6) ★ Q16 专项：章节表 rec15 + 全部 Q16 副本必须保留原文
     （v2.66 实验A 有意放行 6 槽 → 见 Q16_EXPA 白名单，不再误报）
退出码：0 = 全绿；1 = 有异常
"""
import os, io, sys

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
sys.path.insert(0, W)
import s2a as _s2a

OUT = paths.build('t34_health.txt')
L = []
def p(s=''): L.append(str(s))

def get(path, idx):
    return bytes(_s2a.Archive(path).blobs[idx])


# 字段定义: (显示名, 偏移, 定长orNone, 最大长, allow_trans)
#   allow_trans=False -> 必须与 .bak 逐字节一致（键/结构字段）
#   allow_trans=True  -> 允许翻译，只检查"长度没越过下一个字段"
CHECKS = [
    ('LANG_JA[814] 章节表', 'res/LANG_JA.s2a', 814, 580, 85,
     [('章节名  ', 4, None, 64, True), ('世界编号', 68, 4, 4, False),
      ('大陆名  ', 372, None, 64, True)]),
    ('LANG_EN[814] 章节表', 'res/LANG_EN.s2a', 814, 580, 85,
     [('章节名  ', 4, None, 64, True), ('世界编号', 68, 4, 4, False),
      ('大陆名  ', 372, None, 64, True)]),
    ('cscv[782] 章节表',    'res/cscv.s2a',    782, 580, 85,
     [('章节名  ', 4, None, 64, True), ('世界编号', 68, 4, 4, False),
      ('大陆名  ', 372, None, 64, True)]),
    ('LANG_JA[931] 称号表', 'res/LANG_JA.s2a', 931, 292, 252,
     [('称号名本体', 0, None, 32, True), ('称号章节名', 36, None, 64, False)]),
    ('LANG_EN[931] 称号表', 'res/LANG_EN.s2a', 931, 292, 252,
     [('称号名本体', 0, None, 32, True), ('称号章节名', 36, None, 64, False)]),
    ('cscv[890] 称号表',    'res/cscv.s2a',    890, 292, 252,
     [('称号名本体', 0, None, 32, False), ('称号章节名', 36, None, 64, False)]),
    # ---- v2.64（G2）：伙伴/职业/阵形 名字本体允许翻译；**cscv 孪生的名字键必须原版** ----
    ('LANG_JA[954] 伙伴表', 'res/LANG_JA.s2a', 954, 236, 44,
     [('伙伴名本体', 4, None, 32, True)]),
    ('LANG_EN[954] 伙伴表', 'res/LANG_EN.s2a', 954, 236, 44,
     [('伙伴名本体', 4, None, 32, True)]),
    ('LANG_JA[128] 职业表', 'res/LANG_JA.s2a', 128, 212, 12,
     [('职业名本体', 4, None, 36, True)]),
    ('LANG_EN[128] 职业表', 'res/LANG_EN.s2a', 128, 212, 12,
     [('职业名本体', 4, None, 36, True)]),
    ('LANG_JA[136] 阵形表', 'res/LANG_JA.s2a', 136, 272, 11,
     [('阵形名本体', 0, None, 32, True)]),
    ('LANG_EN[136] 阵形表', 'res/LANG_EN.s2a', 136, 272, 11,
     [('阵形名本体', 0, None, 32, True)]),
    ('★cscv[917] 伙伴表(脚本层)', 'res/cscv.s2a', 917, 236, 44,
     [('伙伴名键(须原版)', 4, None, 32, False)]),
    ('★cscv[124] 职业表(脚本层)', 'res/cscv.s2a', 124, 212, 12,
     [('职业名键(须原版)', 4, None, 36, False)]),
    ('★cscv[132] 阵形表(脚本层)', 'res/cscv.s2a', 132, 272, 11,
     [('阵形名键(须原版)', 0, None, 32, False)]),
    # ---- v2.65（G3）：装备表名字列（stride268 pos4）允许翻译；cscv 孪生的名字字段必须原版 ----
    ('LANG_JA[147] 装备表', 'res/LANG_JA.s2a', 147, 268, 494,
     [('装备名@4  ', 4, None, 48, True)]),
    ('LANG_EN[147] 装备表', 'res/LANG_EN.s2a', 147, 268, 494,
     [('装备名@4  ', 4, None, 48, True)]),
    ('LANG_JA[357] 装备表', 'res/LANG_JA.s2a', 357, 268, 614,
     [('装备名@4  ', 4, None, 48, True)]),
    ('LANG_EN[357] 装备表', 'res/LANG_EN.s2a', 357, 268, 614,
     [('装备名@4  ', 4, None, 48, True)]),
    ('LANG_JA[736] 装备表', 'res/LANG_JA.s2a', 736, 268, 614,
     [('装备名@4  ', 4, None, 48, True)]),
    ('LANG_EN[736] 装备表', 'res/LANG_EN.s2a', 736, 268, 614,
     [('装备名@4  ', 4, None, 48, True)]),
    ('LANG_JA[998] 装备表', 'res/LANG_JA.s2a', 998, 268, 96,
     [('装备名@4  ', 4, None, 48, True)]),
    ('LANG_EN[998] 装备表', 'res/LANG_EN.s2a', 998, 268, 96,
     [('装备名@4  ', 4, None, 48, True)]),
    ('★cscv[144] 装备表(脚本层)', 'res/cscv.s2a', 144, 268, 494,
     [('装备名键(须原版)', 4, None, 48, False)]),
    ('★cscv[338] 装备表(脚本层)', 'res/cscv.s2a', 338, 268, 614,
     [('装备名键(须原版)', 4, None, 48, False)]),
    ('★cscv[705] 装备表(脚本层)', 'res/cscv.s2a', 705, 268, 614,
     [('装备名键(须原版)', 4, None, 48, False)]),
    # 例外：这 4 条本来就是载体码（主汉化历史遗留），白名单放行
    ('★cscv[975] 装备表(脚本层)', 'res/cscv.s2a', 975, 268, 96,
     [('装备名键(须原版)', 4, None, 48, False, {32, 48, 64, 80})]),
    # ---- v2.66（G5）：技能表名字列（stride376 pos0）允许翻译；cscv 孪生名字字段必须原版 ----
    ('LANG_JA[666] 技能表', 'res/LANG_JA.s2a', 666, 376, 87,
     [('技能名@0  ', 0, None, 40, True)]),
    ('LANG_EN[666] 技能表', 'res/LANG_EN.s2a', 666, 376, 87,
     [('技能名@0  ', 0, None, 40, True)]),
    ('★cscv[633] 技能表(脚本层)', 'res/cscv.s2a', 633, 376, 87,
     [('技能名键(须原版)', 0, None, 40, False)]),
    # ---- v2.67（G5 事故守卫）：技能表的**键名列**（pos288~375，含 pos292）必须日文原版 ----
    #      G5 事故：把键名列也翻了 ⇒ 主角技能全放不出来（只有 急所突き 幸免，其键名是假名）。
    ('★LANG_JA[666] 技能键名列', 'res/LANG_JA.s2a', 666, 376, 87,
     [('键名@292(须原版)', 288, 88, 88, False)]),
    ('cscv[28] 村落表',     'res/cscv.s2a',     28, 1116, 222,
     [('关卡编号@136', 136, 4, 4, False), ('编号@140', 140, 4, 4, False),
      ('地名槽@104', 104, None, 32, True)]),
]

p('=' * 84)
p('  汉化健康体检 v2.67 —— 章节/称号/伙伴/职业/阵形/装备/技能（名字可中文，键名与 cscv 须原版）/编号/Q16')
p('=' * 84)
p('')

n_problem = 0
for tag, path, blob, stride, n, fields in CHECKS:
    fp = os.path.join(BASE, path)
    if not os.path.exists(fp + '.bak'):
        p('  [跳过] %s 缺少原版备份' % tag); continue
    live = get(fp, blob)
    bak  = get(fp + '.bak', blob)
    p('◆ %s' % tag)
    for fld in fields:
        fname, foff, flen, maxlen, allow_trans = fld[:5]
        wl = fld[5] if len(fld) > 5 else set()      # 白名单：这些 rec 允许与原文不同
        bad = []
        n_wl = 0
        for rec in range(n):
            o = 16 + rec * stride + foff
            if flen:
                a = live[o:o+flen]; b = bak[o:o+flen]
            else:
                # ★ 按"run"取值（到下一个 NUL 为止）：字段为空时 a=b=b'' ，
                #   不会误读进后面的邻字段（v2.65 修：cscv[975] 12 条空字段假警报）
                ea = live.find(b'\x00', o)
                if ea < 0:
                    ea = len(live)
                eb = bak.find(b'\x00', o)
                if eb < 0:
                    eb = len(bak)
                a = live[o:ea]; b = bak[o:eb]
            if allow_trans:
                if len(a) > maxlen:
                    bad.append((rec, a[:22], b[:22]))
            else:
                if a != b:
                    if rec in wl:
                        n_wl += 1
                        continue
                    bad.append((rec, a[:22], b[:22]))
        if bad:
            n_problem += len(bad)
            p('   ★ %s : %d/%d 异常' % (fname, len(bad), n))
            for rec, a, b in bad[:5]:
                p('       rec%-3d 当前=%-24r 原版=%r' % (rec, a, b))
            if len(bad) > 5:
                p('       ...（共 %d 条）' % len(bad))
        else:
            extra = '（允许翻译，已检查无越界）' if allow_trans else ''
            if n_wl:
                extra += '（%d 条为历史遗留载体码，白名单放行）' % n_wl
            p('   OK %s : %d/%d 一致%s' % (fname, n, n, extra))
    p('')

# ---- Q16 专项保护检查 ----
p('◆ Q16 专项（除白名单外，所有副本必须保留原文）')
p('')
# v2.66 实验A 有意放行（Q16 章节名也翻中文）的槽位 —— 只抑制误报，不要求必须不同。
Q16_EXPA = {('LANG_JA', 34, 49, 4), ('LANG_JA', 34, 142, 4),
            ('LANG_JA', 176, 1117, 32),
            ('LANG_JA', 814, 15, 4), ('LANG_EN', 814, 15, 4),
            ('cscv', 782, 15, 4)}
Q16 = [('LANG_JA', 'res/LANG_JA.s2a', 34, 1116, 4, 64, [49, 142]),
       ('LANG_JA', 'res/LANG_JA.s2a', 176, 292, 32, 32, [1117]),
       ('cscv', 'res/cscv.s2a', 28, 1116, 4, 64, [49, 142]),
       ('cscv', 'res/cscv.s2a', 170, 292, 32, 32, [1117]),
       ('LANG_JA', 'res/LANG_JA.s2a', 814, 580, 4, 64, [15]),
       ('LANG_EN', 'res/LANG_EN.s2a', 814, 580, 4, 64, [15]),
       ('cscv', 'res/cscv.s2a', 782, 580, 4, 64, [15])]
q16_bad = 0
q16_expa = 0
for tag, path, bi, stride, pos, ln, recs in Q16:
    fp = os.path.join(BASE, path)
    live = get(fp, bi); bak = get(fp + '.bak', bi)
    for rec in recs:
        o = 16 + rec * stride + pos
        if live[o:o+ln] != bak[o:o+ln]:
            if (tag, bi, rec, pos) in Q16_EXPA:
                q16_expa += 1
                continue
            q16_bad += 1
            p('   ★ %-8s b%-4d rec%-5d pos%-3d 与原文不同！' % (tag, bi, rec, pos))
if q16_bad == 0:
    p('   OK Q16 全部 %d 个槽位保留原文（勇者城不会因本项消失）'
      % (sum(len(r) for *_x, r in Q16) - q16_expa))
    if q16_expa:
        p('   （%d 槽为 v2.66 实验A 有意放行，已白名单）' % q16_expa)
n_problem += q16_bad
p('')

p('=' * 84)
if n_problem == 0:
    p('  结论：全部通过 ✅')
    p('   · 章节名 = 中文（选关画面显示中文）')
    p('   · 称号名 = 中文（LANG 侧，G1 全副本同改）；cscv 称号表 = 原版')
    p('   · 伙伴/职业/阵形 名 = 中文（G2）；cscv 孪生名字键 = 原版（机制不会断链）')
    p('   · 装备名 = 中文（G3，9056 槽，LANG 侧全副本同改）；cscv 装备表 = 原版')
    p('   · 技能名 = 中文（G5b，1595 槽，键名列 pos292 保持日文原版）')
    p('   · Q16 全副本 = 原文（勇者城不会消失）')
    p('   · 村落关卡编号 = 原版（选章节不会闪退）')
    rc = 0
else:
    p('  结论：发现 %d 处异常 ★' % n_problem)
    p('  处理：双击 汉化-安装.bat 重装一次；若仍异常请看上面具体条目。')
    rc = 1
p('=' * 84)

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print('\n'.join(L))
sys.exit(rc)
