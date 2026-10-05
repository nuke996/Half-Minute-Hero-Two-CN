# -*- coding: utf-8 -*-
"""
勇者30 汉化 —— 简体字模补丁构建器（方案B：专属 CP932 载体码）

机制（已由游戏内实验证实：交换字符表条目 -> 游戏内字形随之交换）：
    LANG 文本字节 --(CP932解码)--> 字符 --> cscv 字符表(字符->index) --> 图集格子 --> 像素

做法：
  1) 统计译文(zh_new)里每个简体字的使用频率
  2) 给最常用的 N 个字各分配一个【专属 CP932 载体码】（优先 User-Defined 区 0xF040+，
     不会与游戏自身任何日文字符冲突）
  3) 把该简体字的 SimSun 16px 点阵画进对应图集格子
  4) 重写字符表：index -> 载体码
  5) 重写 LANG_JA/LANG_EN 文本：简体字 -> 载体码的 CP932 字节；ASCII/符号保持原样
  6) HMH2.exe 还原原版（游戏按 CP932 解码，不改 exe）

用法:
  python build_cn.py plan     # 统计覆盖率，不改文件
  python build_cn.py apply    # 构建并安装（自动 .bak 备份）
  python build_cn.py revert   # 还原
"""
import os, sys, io, csv, json, shutil, collections, ctypes, struct

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
BASE = paths.GAME_DIR          # game install dir (HMH2.exe, res/, DLC01/)
WORK = paths.DATA_DIR          # translation data (text_v2.csv, guards, dlc/)
import s2a
from PIL import Image, ImageDraw, ImageFont
from ctypes import wintypes

CSV = os.path.join(WORK, 'text_v2.csv')
EXE = os.path.join(BASE, 'HMH2.exe')

CELL, COLS_B, COLS_A = 16, 32, 32   # 图集A 也按 32 列布局（游戏用 (x&31,y&31) 取格）
B_HASH = 0x45781F74      # 图集B 512x512 32列 1024格
A_HASH = 0x52B69FD4      # 图集A 256x256 16列 256格
TBL_HASH = 0xCCCEDC89
TBL_OFF = 0x10
IDX_FIRST = 256          # 0-255 假名/全角字母/符号 保留
IDX_LAST = 1023
A_IDX_BASE = 1248        # index 1248..1279 -> 图集A 格 224..255
A_CELL_BASE = 224
N_A = 32

# ---- v2.6 扩格尝试（已实测失败，默认关闭）----
# 曾把 index 1280..1407（128 个全角空格空位）+ 图集A 放大到 256x512。
# ❌ 2026-09-12 用户实测：原本显示 `?` 的字变成**粉色 @**（无一个字变汉字）。
# 机制：反汇编 `0x4D88C0` 的建表循环硬跑 **1280 次**（cmp edi,0x13fc），
#       字符二分查找范围常量 0x4ff(=1279) → **坐标表只有 1280 项**。
#       字符能被查找表命中，但坐标表[index] 未初始化 → 垃圾坐标 → 粉 @。
# 结论：**游戏硬限 1280 项，index>=1280 必须改 exe 才能用**。
# ---- v2.8 解开字符表 1280 上限（需要改 exe）----
# 背景：exe 建表循环 `cmp edi,0x13fc` 硬跑 **1280** 轮 → index>=1280 没有坐标 → 粉 @。
# 事实（probe_dead.py 实测）：
#   * 字符表本身有 **1410 项**，其中 1280-1407 是 U+3000 空位（现成可用）
#   * blob 头 offset 8 = 89，而 89*16 = 1424 = (2864-16)/2 → 这就是"项数上限"
#   * 排序表紧邻坐标表之后：坐标表 0x5D36E0、排序表 0x5D4AE0（各 1280*4=5120）
# 做法（4 类共 6 处立即数 + 1 个新节）：
#   1) 新增可写节 `.atbl`（VA 0x5F4000, 16KB）承载"扩容后的排序表"
#      —— 因为坐标表扩到 1408 项(5632B)会盖掉原排序表 0x5D4AE0
#   2) `cmp edi,0x13fc` → edi 到 1408*4 停（= 执行 1408 轮）
#   3) 二分查找 `mov ebx,0x4ff`（hi=1279）→ 1407
#      （注：`mov ecx,0x480` 只是"起始 mid"的启发式，范围是 lo=0/hi=0x4ff，无需改）
#   4) 排序表基址 0x5D4AE0/0x5D4AE4 → 新节 0x5F4000/0x5F4004（4 处）
UNLOCK_1280 = True
A_TBL_VA = 0x5F4000          # .atbl 节基址（4096 模式下 = 坐标表基址）
A_TBL_VA_SORT = 0x5F8000     # 4096 模式：排序表基址（坐标表之后 16KB）
A_TBL_SIZE = 0x8000          # 节大小 32KB（坐标表 16KB + 排序表 16KB）
ENABLE_A_EXT = UNLOCK_1280
A_EXT_FIRST = 1248       # v2.14：简体字统一从 index 1248 起（原版 0-1247 全部保留）

# ==== v2.14：扩到 4096 + 保留原版全部字形（假名/日文汉字/姓名/符号/ASCII）====
# 【沿革，别重犯】
#   v2.11(图集2048x2048) / v2.12(1024x1024) 两次「启动即闪退」，
#   真正原因 = 建表循环上限写成 `N*4`，**正确值是 `4N-4`**
#   （循环 `cmp edi,L ; jl`，edi=4i-4 ⇒ 迭代次数 = L/4+1；原版 N=1280 用的正是 0x13FC=4*1280-4）。
#   写 4N 会多跑一轮 i=N：排序表指针写到 sortbase+4N，N=4096 时 = 0x5FC000 = `.atbl` 末尾之外
#   → 越界写 → 闪退。（v2.8 N=1408 / v2.9 N=2048 时那一轮落在节内，所以没暴露。）
#
# 【v2.13 已完成】修好循环上限后 4096 格可用、覆盖率 100%、问号清零。实测通过。
#
# 【v2.14 本版要解决的两件事】
#   ① 省略号「…」等符号出现蓝绿色描边。原因：v2.13 的取格公式让 index 1024..1279
#      从**图集A** 换到了**图集B**，而两张图集的调色板不同（A 的 idx19/20 = 灰
#      (100,98,100)/(10,8,10)，B 的同名 idx = 青绿 (127,220,216)/(0,154,143)）
#      → 跨图集搬迁必须做调色板映射，否则串色。
#   ② 用户要求「恢复日语假名 + 对齐日语汉字」，使日语环境/日文名旧存档能正确显示日文。
#
# 【v2.14 解法：换一套取格公式，让原版内容**一格都不跨图集**，且给新字腾出空间】
#   * 建表函数：`shr ecx,9` -> **`shr ecx,11`**  ⇒ x = (i>>11)*16 + i%16（≤31）
#   * 渲染：U = (x & 31)*16（**原版掩码，不改**）、V = (y & 63)*16（&31 -> &63）
#   * 页号：**62 + ((i>>10) & 1)**（15 字节等长替换）
#   * 位覆盖：col ← bit0-3 + bit11 ； row ← bit4-9 ； page ← bit10
#     ⇒ 12 位全用上，4096 索引一一对应（design214.py 实测 4096 格 0 重复 0 越界）
#   * 四块位置（每块 1024 格）：
#       i    0-1023 → 页62  U 0..240   （图集B 左半）
#       i 1024-2047 → 页63  U 0..240   （图集A 左半）★原版 1024-1279 仍在此页！
#       i 2048-3071 → 页62  U 256..496 （图集B 右半）
#       i 3072-4095 → 页63  U 256..496 （图集A 右半）
#   * **关键收益：原版 index 与图集页的对应关系保持不变**（0-1023→B、1024-1279→A），
#     所以 **跨图集搬迁数 = 0** → 调色板问题从根源消失。
#   * 原版内容位置变化只发生在 **i 512-1023**（图集B 内 U256-496/V0-496 → U0-240/V512-1008），
#     同图集内搬迁 ⇒ 调色板一致 ⇒ 颜色不变。
#   * 图集仍 512x1024（宽 512 与高 1024 都是实测可用尺寸）。
#
# 【保留原版字形的代价与容量】
#   * 不再回收假名格(162)/日文汉字格(256-1023)/STAFF区(1024-1119) —— 全部保留原版。
#   * 简体字统一用 **index 1248..4095**（其中 1408='ED' 标记保留）
#     = 1248-1279(32) + 1280-2047(768) + 2048-3071(1024) + 3072-4095(1024) = **2847 格**
#     → 足够装下全部简体字（v2.13 实装 2640 字，且新方案下"与日文汉字同形的字"还能免占格）
#   * ⚠️ 图集A 的 x∈[0,256) y∈[96,224) 是**硬编码 ASCII 路径**占用区
#     （0x4D8CF2 `mov [esi],0x3f` 页号写死 63；0x4D8D21 u=(c&15)*16；
#       0x4D8D2E/36 v=(c&~15)+0x60），该路径只处理 c∈[0x01,0x7F]（c>=0x80 走双字节分支）
#     → 实际占用 V∈[128,208]；本版新分配格**无一落入**该带（design214.py 实测 0）。
#     ascii_reserved() 仍照常把落在带内的索引排除，作为双保险。
EXPAND_4096 = True
TBL_SLOTS = 4096 if EXPAND_4096 else 2048

# ---- v2.9 大扩容：加长字符表 blob（2048 项）+ 图集A 放大到 256x1024 ----
# 事实（`probe_tbl_enc.py` 实测，2026-09-12）：
#   * 字符表 blob 是【定长 2 字节/项】（小端 u16 CP932 码值），**不是变长**！
#     blob = 16 字节头 + 1424 槽 x 2；项 i 在偏移 16+2i。
#   * 头 offset 8 = 89 → 89*16 = 1424 = 槽数；游戏 `mov ecx,[blob+8]; shl ecx,4`
#     → **项数上限完全来自 blob 头**（与文件长度无关）→ 改头字段即可扩容。
#   * index 1408 = 0x4445（'E','D' 打包，疑似结束标记）；1409-1423 = 0x0000 空槽。
#   * exe 里**没有** 2864/1410 长度硬编码（`probe_ext2.py` 扫 0xB30/0x582 全为虚警）。
# 做法：blob 加长到 TBL_SLOTS 项 + 头字段改 TBL_SLOTS/16 + exe 循环/hi 同步放大。
#   坐标表在 BSS 0x5D36E0（容量到 0x5D5EE0 = 2560 项），排序表已在 .atbl(16KB)。
#   TBL_SLOTS=2048 → 坐标表 8192B（0x5D56E0 止），距变量数组还有 2048B 余量。
TBL_SLOTS = TBL_SLOTS          # 见上方 v2.11 定义（4096 或 2048）
A_IDX_MAX = TBL_SLOTS - 1

# ---- ⭐ v2.10 关键修正：图集A 必须按 **32 列** 布局，尺寸 512x512 ----
# 真相（用户实测 v2.9 反推 + 反汇编坐标公式）：游戏取格用的是
#     x = (i//512)*16 + i%16 ;  y = i//16
#     实际格 = (y & 31) * 32 + (x & 31)          ← 两个图集都按 32 列 / 32 行取
# 所以：
#   · 图集B（512x512，32x32）天然匹配 —— 我们旧的 blk_cell() 恰好等价于此公式
#   · 图集A **原来我按 16 列画，是错的**：
#       index 1024..1535 -> x∈[32,47] -> x&31 = i%16   -> 列 0..15  （碰巧与 16 列同像素 → 一直正常）
#       index 1536..2047 -> x∈[48,63] -> x&31 = 16+i%16 -> 列 16..31 （旧做法差 16 列 → 读到空白）
#   用户实测证据：i=1517 "史" 显示 / i=1652 "诗" 显示为空格 / i=2000 "甩" 空格
# 修法：图集A 放大成 **512x512**（32列 x 32行 = 1024 格），并用 32 列布局画字，
#       index 1024..2047 即可全部有效（左半 = 1024..1535，右半 = 1536..2047）。
A_W = 512 if ENABLE_A_EXT else 256      # v2.13：两张图集都 512x1024（宽512/高1024 均实测可用）
A_TALL = 1024 if EXPAND_4096 else 512
A_EXT_LAST = TBL_SLOTS - 1


PX_SHIFT = 11        # 建表函数：x = ((i>>11) << 4) + i%16   （v2.14 打补丁：shr ecx,11）
PG_SHIFT = 10        # 页号 = 62 + ((i>>10) & 1)             （v2.14 打补丁）
U_MASK = 31          # U = (x & 31)*16   ← 原版值，不改
V_MASK = 63          # V = (y & 63)*16   ← v2.13 起打补丁
ASCII_BAND = (0, 256, 96, 224)   # 图集A 中硬编码 ASCII 路径占用：x∈[0,256) y∈[96,224)


def game_cell(i):
    """按**改后 exe 的真实公式**算 index i 的图集格 → (页, u, v)，页 62=图集B / 63=图集A。
    必须与 verify 脚本的独立复算逐项一致。"""
    x = (((i >> PX_SHIFT) << 4) + (i & 15)) & 0xFF
    y = (i >> 4) & 0xFF
    page = 62 + ((i >> PG_SHIFT) & 1)
    return page, (x & U_MASK) * CELL, (y & V_MASK) * CELL


def old_cell(i):
    """**原版** exe 公式算出的格（用于把原版字形从旧位置搬到新位置）。"""
    x = (((i >> 9) << 4) + (i & 15)) & 0xFF
    y = (i >> 4) & 0xFF
    page = 62 + (i >> 10)
    return page, (x & 31) * CELL, (y & 31) * CELL


def a_cell(idx):
    """（仅 v2.10 回退路径用）图集A 格号：32 列 x 32 行布局。"""
    x = (idx // 512) * 16 + idx % 16
    y = idx // 16
    return (y & 31) * 32 + (x & 31)


def ascii_reserved():
    """新布局下会落进「硬编码 ASCII 带」的索引（这些格必须留给 ASCII 字形）。"""
    x0, x1, y0, y1 = ASCII_BAND
    out = []
    for i in range(1024, TBL_SLOTS):
        pg, u, v = game_cell(i)
        if pg == 63 and x0 <= u < x1 and y0 <= v < y1:
            out.append(i)
    return out


# 'ED' 结束标记(1408) + 硬编码 ASCII 带所占索引：保留原样、不进槽位
A_EXT_SKIP = (1408,) + tuple(ascii_reserved())

# ---- v2.14：**不再回收** STAFF/版权姓名区 ----
# 用户要求让日语环境/日文名旧存档能显示日文（版权页姓名、角色名等），
# 故 index 1024-1119 的原版姓名汉字字形**保留**，不改为简体字。
RECLAIM_STAFF = False
STAFF_FIRST, STAFF_LAST = 1024, 1119

# ---- v2.14：**不再回收** U+3000 死格 ----
# 1140-1151 / 1247 原本是 U+3000 死格且图集位置为空白，v2.7b 曾回收。
# v2.14 起简体字有充足新区（1248-4095 共 2847 格），无需再动这些格子，
# 保持原样可减少变量（也避免误判 ASCII 带边界）。
RECLAIM_DEAD_SPACE = False
DEAD_SPACE_SLOTS = list(range(1140, 1152)) + [1247]

# ---- 方案1：回收假名区 ----
# 字符表 index 0-255 的【条目】必须保留（删了闪退，已验证），
# 但其中【假名】的图集格子中文版用不到 -> 保留条目、只重画像素。
# 被分配到假名格的简体字直接借用假名自己的 CP932 码当载体码（查表天然通）。
KANA_RANGES = ((0x3041, 0x3096),   # 平假名
               (0x309B, 0x309C),   # 濁点/半濁点
               (0x30A1, 0x30FA),   # 片假名
               (0x30FC, 0x30FC))   # 长音符 ー


def is_kana(ch):
    if not ch or len(ch) != 1:
        return False
    o = ord(ch)
    return any(a <= o <= b for a, b in KANA_RANGES)


# ---- 方案2：缺字替换表（词级优先），从 replace_map.py 加载 ----
REPL = {}
FORCE_CHARS = '左右斩饿御沙香锅影醒调餐掌荡砍奖肉岛墟陛罪叉嘴夜菇沼'

# ---- DLC01 汉化专用字（2026-09-13）----
# DLC01（时之女神宝物包）译文用到的字，主译表 text_v2.csv 里没有，因此 char_freq 扫不到。
# 处理：在 build_plan 里把这些字**追加到候选末尾**——只占剩余空槽，不移动主译表既有字格，
#       对已装机文字零影响。容量不足时会在 do_plan 打印警告。
# 判据（用户 2026-09-13 确认）：字较常用，且换成别的字会导致指代/理解错误时才加。
DLC_EXTRA_CHARS = '鸭苹橘掀糯鲑蚝朗乳鼬樱'


# 技能/职业机制表：游戏会按内容读取，翻译会导致技能无动画无效果（2026-09-12 测试D 实锤）
#   666 = 技能升级链表（技能名→下一级→说明→思いつき率）
#   128/136 = 职业表（职业名/能力值/说明）
#   317 = 连携技表
MECHANIC_BLOBS = (666, 128, 136, 317)

# ---- v2.2 菜单豁免（2026-09-12）----
# 实测E证伪"全量统一翻译"，但用户确认E版菜单变中文 → 菜单文本链路安全。
# analyze_menus2.py 分层分析：blob 358(UI) 被白名单挡的 133 串中，
# 只有 陣形/クラス 2 个串出现在机制/武器表字段（硬危险，绝不翻）；
# 其余 131 个纯 UI 串（装備/パーティ/オプション/セーブ...）仅在 cscv 脚本
# 中作为显示标签出现 → 豁免翻译，且只在 blob 358 生效（其他 blob 不碰）。
MENU_EXEMPT_BLOBS = (186, 354, 358, 440, 516, 715, 763)
MENU_OK_FILE = os.path.join(WORK, 'menu_ok.json')


def load_menu_ok():
    import json
    try:
        return set(json.load(open(MENU_OK_FILE, encoding='utf-8')))
    except Exception:
        return set()

# ---- v2.15 可选增强：跨 blob 的"纯 UI 标签/提示"词表（ui_always.json）----
# 默认【不启用】。启用后，这些串即使命中碰撞白名单也照常翻译（仅 UI 词，不含人名/道具/技能名）。
UI_ALWAYS_FILE = os.path.join(WORK, 'ui_always.json')


def load_ui_always():
    import json
    try:
        return set(json.load(open(UI_ALWAYS_FILE, encoding='utf-8')))
    except Exception:
        return set()


# ---- v2.58 章节名/称号保护（chap_title_guard.json）----
# 2026-09-17 实验实锤：章节名与称号名是【按字符串索引的键】——
#   ① Steam 语言=日语时 Q16「勇者城」出得来，=英语时出不来（章节名被翻成中文 ⇒ 对不上英文原表）；
#   ② 翻译称号名会导致称号无法取得（例 Master Part-Timer）。
# 规则 = [(blob, stride, pos), ...]，命中即【保留原文】（即使译文行存在也不写）。
# 默认规则见 _work/chap_title_guard.json（enabled=false 可整体关闭）。
#
# ★ v2.62：新增【按记录号】保护 rec_rules —— 规则形如
#   {"blob":814,"stride":580,"pos":4,"recs":[15]} / {"pos":32,"recs":[1117],"blob_any":true}
#   语义：只保护指定记录号上的字段，同表其它记录照常翻译。
#   用途：用户本轮要求「章节名翻译成中文，但 Q16（勇者城）整条例外」——
#   整字段规则 (blob,stride,pos) 做不到这种"只放行一条记录"的粒度。
CHAP_TITLE_GUARD_FILE = os.path.join(WORK, 'chap_title_guard.json')


def load_chap_title_guard():
    """返回 (whole_rules, rec_rules, value_rules)。
    whole_rules : set[(blob, stride, pos)]             整字段保护
    rec_rules   : list[(blob_or_None, stride, pos, frozenset(recs))]
                  blob 为 None 表示"任意 blob"（用于同 stride/pos 的孪生副本）。
    value_rules : list[str]                            按【值】保护
                  —— 凡槽内文本等于该串者，任意 blob/stride/pos 一律保留原文。
                  ★ v2.63：Q16「勇者城」这类"脚本按名匹配的标识"必须两侧同保，
                  官方 EN 只改 LANG 显示层、cscv 层保持日文；只护"正表"会漏。
    """
    import json
    try:
        d = json.load(open(CHAP_TITLE_GUARD_FILE, encoding='utf-8'))
        if not d.get('enabled', True):
            return set(), [], []
        whole = {(int(r['blob']), int(r['stride']), int(r['pos']))
                 for r in d.get('rules', ())}
        recs = []
        for r in d.get('rec_rules', ()):
            b = None if r.get('blob_any') else int(r['blob'])
            recs.append((b, int(r['stride']), int(r['pos']),
                         frozenset(int(x) for x in r['recs'])))
        vals = [str(r['value']) for r in d.get('value_rules', ()) if r.get('value')]
        return whole, recs, vals
    except Exception:
        return set(), [], []


def chap_title_hit(whole, recs, bi, stride, pos, rec, value=None):
    """该槽是否受章节/称号保护。rec = 记录号（不可知时传 -1）；
    value = 该槽的日文原文（用于 value_rules 按值保护）。"""
    if stride and (bi, stride, pos) in whole:
        return True
    for b, st, ps, rs in recs:
        if st == stride and ps == pos and rec in rs and (b is None or b == bi):
            return True
    if value is not None and value in _CT_VALUE_CACHE:
        return True
    return False


# value_rules 的快速查找集（load_chap_title_guard 时刷新）
_CT_VALUE_CACHE = set()


# ---- v2.49 槽位级放行（slot_release.json）----
# TODO-2C 第二步：对话表 pos=96「说话人名」是**纯显示字段**（引擎原样输出 + 变量替换，不查表），
# 但它的 JA 原文常与武器/道具/敌人名同串 ⇒ 命中 collide 白名单被整条挡住、装机保留日文。
# ui_always.json 是【按字符串】放行 ⇒ 会连带翻译其它表的同名副本（露露菲路径，实测会坏）。
# 这里改为【按槽位】放行：只有落在指定 (stride, pos) 上的槽才放行，同名副本一律不动。
# 规则来自 _work/slot_release.json（enabled=false 即整体关闭 → 退回旧行为）。
SLOT_RELEASE_FILE = os.path.join(WORK, 'slot_release.json')
_STRIDE_CACHE = {}


def load_slot_release():
    try:
        d = json.load(open(SLOT_RELEASE_FILE, encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(d, dict) or not d.get('enabled'):
        return None
    return d


def blob_stride(arc, bi):
    """blob 的 CSCV stride（每记录字节数）；非 CSCV 返回 0。"""
    k = (id(arc), bi)
    v = _STRIDE_CACHE.get(k)
    if v is not None:
        return v
    b = bytes(arc.blobs[bi]) if bi < len(arc.blobs) else b''
    v = int.from_bytes(b[4:8], 'little') if b[:4] == b'CSCV' else 0
    _STRIDE_CACHE[k] = v
    return v


def slot_release_hit(rel, arc, bi, off):
    """槽位级放行判定：off 在记录内的偏移 pos 命中规则即放行。"""
    st = blob_stride(arc, bi)
    if not st:
        return False
    pos = (off - 16) % st
    for r in rel.get('rules', ()):
        try:
            if int(r.get('stride', -1)) == st and int(r.get('pos', -1)) == pos:
                return True
        except Exception:
            continue
    return False


def slot_release_excl(rel, s):
    """exclude_contains 命中则不放行（如 '<' = 引擎变量引用记号，必须保留原文）。"""
    for ex in rel.get('exclude_contains', ()):
        if ex and ex in s:
            return True
    return False


# ---- v2.51 说明文槽位级放行（desc_release.json）----
# 背景（2026-09-16 定位）：技能/道具/装备的**说明文字**一直没有上屏，但原因不是"翻译会坏机制"，
# 而是两道保护把它们一起挡住了：
#   ① skip_blobs=666/128/136/317 整表不翻（保护的是表里的【名字】字段）；
#   ② collide 白名单（判据是"该串在 cscv 独有 blob 里出现过"）—— 而 cscv 里的命中其实
#      全是**同一张表的副本**（cscv[144]/[338]/[705] 尺寸与 LANG[147]/[357]/[736] 完全一致），
#      不是脚本按名比对的键 ⇒ 对说明文来说是**假命中**。
# 证据（说明文字段是纯显示）：
#   ① 引擎按名比对只发生在【名字】字段之间（武器表 pos172/204/236 ↔ 技能链表 pos0/292）；
#      说明文只出现在自己那条记录的说明字段里，全库无第二处引用；
#   ② HMH2.exe 里搜不到任何一条说明文（cp932 / utf-16le 均为 0 命中）；
#   ③ 合成表(blob99)与图鉴的说明文早已装机显示中文，实机无副作用；
#   ④ 装备表 (268,44) 已有 78 条说明文靠 ui_always 上了屏，当前版本游戏正常。
# 因此按【槽位】精确放行：只放 (blob, stride, pos) 命中的说明字段，同表名字字段一律不动。
DESC_RELEASE_FILE = os.path.join(WORK, 'desc_release.json')


def load_desc_release():
    try:
        d = json.load(open(DESC_RELEASE_FILE, encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(d, dict) or not d.get('enabled'):
        return None
    return d


def desc_release_hit(rel, arc, bi, off):
    """说明文放行判定：blob 在规则白名单内、且该槽的记录内偏移 pos 命中。

    这些字段没有 4 字节 0xFF 前缀（说明文不像名字那样带标记），
    但为稳妥，同时接受 pos 与 pos+k (k<=3) 两种可能（前缀标记会让 offset 前移）。
    """
    st = blob_stride(arc, bi)
    if not st:
        return False
    pos = (off - 16) % st
    for r in rel.get('rules', ()):
        if r.get('enabled') is False:
            continue                      # v2.51：规则可单独关（见 desc_release.json / desc_toggle.py）
        try:
            if int(r.get('stride', -1)) != st:
                continue
        except Exception:
            continue
        bl = r.get('blobs')
        if bl is not None and bi not in [int(x) for x in bl]:
            continue
        want = r.get('pos')
        wants = [int(x) for x in want] if isinstance(want, (list, tuple)) else [int(want)]
        if any(pos == w or pos == w + k for w in wants for k in (0, 1, 2, 3)):
            return True
    return False


def desc_release_excl(rel, s):
    for ex in rel.get('exclude_contains', ()):
        if ex and ex in s:
            return True
    return False


_rm = os.path.join(WORK, 'replace_map.py')
if os.path.exists(_rm):
    _ns = {}
    exec(compile(open(_rm, encoding='utf-8').read(), _rm, 'exec'), _ns)
    REPL = _ns.get('REPL', {})
    _repl_items = sorted(REPL.items(), key=lambda kv: -len(kv[0]))

# ---- 高亮标记 <...> 补译表（2026-09-12 补全未翻译文本）----
_hlm = os.path.join(WORK, 'hl_map.py')
if os.path.exists(_hlm):
    _ns2 = {}
    exec(compile(open(_hlm, encoding='utf-8').read(), _hlm, 'exec'), _ns2)
    REPL = dict(REPL)
    REPL.update(_ns2.get('HL', {}))
    _repl_items = sorted(REPL.items(), key=lambda kv: -len(kv[0]))


def apply_repl(t):
    """对译文做缺字替换（词级优先：长词先替换）。"""
    if not REPL:
        return t
    for a, b in _repl_items:
        if a in t:
            t = t.replace(a, b)
    return t


# ---- v2.22 修复：字段原始值可能带 \uf8f3 前缀（ff ff ff ff 的 CP932 解码）----
# 碰撞白名单里有 3796 个"以 \uf8f3 开头的串"，那是扫描二进制数据产生的噪音。
# 若直接拿【带前缀】的字段串去比对 collide，会假命中 -> 该行被当作"专有名词"保留原文
# （blob391/MESS 表 63 条就是这样漏翻的，包括 Dash）。比对前先剥前缀即可。
def strip_f8f3(s):
    while s and '\uf8f0' <= s[0] <= '\uf8ff':
        s = s[1:]
    return s


# ---- v2.23：译文首尾只剥 ASCII 空白，保留全角空格 U+3000（排版对齐用）----
def strip_ascii_ws(s):
    return s.strip(' \t\r\n\v\f\x00')

TEXT_FILES = ['res/LANG_JA.s2a', 'res/LANG_EN.s2a']
ATLAS_FILES = ['res/texture.s2a', 'res/cscv.s2a']
ALL_FILES = ['HMH2.exe'] + TEXT_FILES + ATLAS_FILES

# ---------------- exe 补丁模式：dll（运行时，默认） / exe（离线改写） ----------------
# dll（默认）：不改磁盘 HMH2.exe，部署 dinput8.dll + hm2zh_patch.bin，由代理 DLL 运行时打补丁
# exe        ：离线改写 HMH2.exe（旧行为，patch_exe_unlock）
EXE_MODE = (os.environ.get('HMH2_EXE_MODE') or 'dll').lower()
PROXY_DLL_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'assets', 'proxydll', 'dinput8.dll')
PROXY_FILES = ['dinput8.dll', 'hm2zh_patch.bin']


def deploy_proxy():
    """dll 模式：生成 hm2zh_patch.bin 并把 dinput8.dll + bin 部署到游戏目录。"""
    if not os.path.exists(PROXY_DLL_SRC):
        raise SystemExit('!! DLL 模式缺少代理 DLL: %s\n   请从 tools/proxydll 构建（build.bat，需 zig），或放入该路径。'
                         % PROXY_DLL_SRC)
    import proxy_patch
    binp = proxy_patch.build(os.path.join(BASE, 'HMH2.exe.bak'), paths.build('hm2zh_patch.bin'))
    shutil.copy2(PROXY_DLL_SRC, os.path.join(BASE, 'dinput8.dll'))
    shutil.copy2(binp, os.path.join(BASE, 'hm2zh_patch.bin'))
    print('  [DLL模式] 已部署 dinput8.dll + hm2zh_patch.bin 到游戏目录（HMH2.exe 保持原版）')


def remove_proxy():
    n = 0
    for name in PROXY_FILES:
        p = os.path.join(BASE, name)
        if os.path.exists(p):
            os.remove(p)
            n += 1
    if n:
        print('  [DLL模式] 已移除 %d 个代理文件' % n)


# ---------------- GDI 取点阵 ----------------
gdi32 = ctypes.WinDLL('gdi32')
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateBitmap.restype = wintypes.HBITMAP
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.CreateFontW.restype = ctypes.c_void_p
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [ctypes.c_uint] * 8 + [wintypes.LPCWSTR]
gdi32.GetBitmapBits.argtypes = [wintypes.HBITMAP, ctypes.c_long, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int
gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]


class BM(ctypes.Structure):
    _fields_ = [('bmType', ctypes.c_long), ('bmWidth', ctypes.c_long), ('bmHeight', ctypes.c_long),
                ('bmWidthBytes', ctypes.c_long), ('bmPlanes', ctypes.c_ushort), ('bmBitsPixel', ctypes.c_ushort),
                ('bmBits', ctypes.c_void_p)]


def glyph(ch, face='SimSun', height=16):
    hdc = gdi32.CreateCompatibleDC(None)
    bmp = gdi32.CreateBitmap(CELL, CELL, 1, 1, None)
    old = gdi32.SelectObject(hdc, bmp)
    gdi32.SetBkMode(hdc, 1)
    gdi32.SetTextColor(hdc, 0x00FFFFFF)
    hf = gdi32.CreateFontW(-height, 0, 0, 0, 400, 0, 0, 0, 0x86, 0, 0, 0, 0, face)
    oldf = gdi32.SelectObject(hdc, hf)
    gdi32.TextOutW(hdc, 0, 0, ch, 1)
    gdi32.SelectObject(hdc, oldf)
    gdi32.DeleteObject(hf)
    bm = BM()
    gdi32.GetObjectW(bmp, ctypes.sizeof(bm), ctypes.byref(bm))
    stride = bm.bmWidthBytes or 4
    buf = ctypes.create_string_buffer(stride * CELL)
    gdi32.GetBitmapBits(bmp, len(buf), buf)
    gdi32.SelectObject(hdc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    raw = buf.raw
    return [[(raw[y * stride + x // 8] >> (7 - x % 8)) & 1 for x in range(CELL)] for y in range(CELL)]


# ============ 字形来源：文泉驿点阵宋体 + 原版三层描边（v2.17）============
# 实测原版图集字形是「三层立体字」（图集B / 图集A 各有一套索引）：
#   · 白面    idx1  (255,255,255)          —— 笔画主体
#   · 灰厚度  idx86 / idx19 (100,100,100)  —— 笔画正下方 1px（实测 100% 落在白面 4 邻膨胀内）
#   · 近黑描边 idx96 / idx20 (10,10,10)    —— 整体 8 邻 1px 外圈（实测 8 邻环的 ~56% 在 4 邻膨胀内）
#   · idx0 (0,0,0) 是**透明键**，绝不能用它画描边
# 统计（图集B 1024 格）：白 47.6 / 灰 29.2 / 描边 80.3 像素每格。
#
# 字体选型（_work/gp*.py 实测，判据「灰阶数=2 即真内嵌点阵、无抗锯齿」）：
#   12px.ttf @size15 -> 字面 10x11（偏小）
#   13px.ttf @size15 -> 字面 12x12（与原版汉字区众数完全一致）★ 选它
#   14px.ttf @size15 -> 字面 13x13（偏大）
#   16px.ttf @size18 -> 字面 13x15（过大）
# 覆盖率：chosen 2713 字**全部命中内嵌点阵**，无缺字、无轮廓渲染，12x12 占 82%。
GLYPH_FONT = os.environ.get('HMH2_FONT', 'wqy13')
FONT_TABLE = {
    'wqy12': (r'C:\Windows\Fonts\WenQuanYi Bitmap Song 12px.ttf', 15),
    'wqy13': (paths.FONT_PATH, 15),
    'wqy14': (r'C:\Windows\Fonts\WenQuanYi Bitmap Song 14px.ttf', 15),
    'wqy16': (r'C:\Windows\Fonts\WenQuanYi Bitmap Song 16px.ttf', 18),
    'simsun': (None, 16),          # 回退：GDI SimSun 16px，单色无描边（= v2.16 之前的行为）
}
GLYPH_OX, GLYPH_OY = 2, 0          # 字身在 16x16 格内的落点（实测 2713 字零溢出，水平居中）
GLYPH_THICK = os.environ.get('HMH2_THICK', '1') != '0'      # 下方 1px 灰厚度
GLYPH_OUTLINE = os.environ.get('HMH2_OUTLINE', '1') != '0'  # 四周 1px 近黑描边
LAYER = {62: (1, 86, 96), 63: (1, 19, 20)}   # page -> (白面, 灰厚度, 近黑描边)

_font_cache = {}


def _glyph_font():
    if GLYPH_FONT in _font_cache:
        return _font_cache[GLYPH_FONT]
    path, size = FONT_TABLE.get(GLYPH_FONT, FONT_TABLE['wqy13'])
    f = None
    if path and os.path.exists(path):
        try:
            f = ImageFont.truetype(path, size)
        except Exception as e:
            print('  !! 字体加载失败 %s: %s' % (path, e))
    if f is None:
        print('  !! 字体不可用，回退 SimSun 16px 单色（无描边）')
        _font_cache[GLYPH_FONT] = None
        return None
    _font_cache[GLYPH_FONT] = f
    return f


CAN = CELL + 8


def glyph3(ch, page=62):
    """返回 16x16 值矩阵：0=透明, 1=白面, 2=灰厚度, 3=近黑描边。

    GLYPH_FONT='simsun' 或字体不可用时，退化为纯 0/1（= v2.16 前的行为）。
    """
    f = _glyph_font()
    if f is None:
        m = glyph(ch)
        return [[1 if c else 0 for c in row] for row in m]
    im = Image.new('L', (CAN, CAN), 0)
    ImageDraw.Draw(im).text((GLYPH_OX, GLYPH_OY), ch, font=f, fill=255)
    data = im.tobytes()
    ink = {(i % CAN, i // CAN) for i, v in enumerate(data) if v > 127}
    if not ink:
        return [[0] * CELL for _ in range(CELL)]
    thick = set()
    if GLYPH_THICK:
        thick = {(x, y + 1) for (x, y) in ink} - ink
    base = ink | thick
    edge = set()
    if GLYPH_OUTLINE:
        for (x, y) in base:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    edge.add((x + dx, y + dy))
        edge -= base
    out = [[0] * CELL for _ in range(CELL)]
    for (x, y) in edge:
        if 0 <= x < CELL and 0 <= y < CELL:
            out[y][x] = 3
    for (x, y) in thick:
        if 0 <= x < CELL and 0 <= y < CELL:
            out[y][x] = 2
    for (x, y) in ink:
        if 0 <= x < CELL and 0 <= y < CELL:
            out[y][x] = 1
    return out


def blk_cell(i):
    if i < 192:
        g, j = divmod(i, 16); return g * 32 + j
    if i < 256:
        g, j = divmod(i - 192, 16); return (12 + g) * 32 + j
    if i < 512:
        g, j = divmod(i - 256, 16); return (16 + g) * 32 + j
    if i < 576:
        g, j = divmod(i - 512, 16); return g * 32 + 16 + j
    g, j = divmod(i - 576, 16); return (4 + g) * 32 + 16 + j


# ---------------- 字符表解析 ----------------
def parse_entries(blob):
    """字符表是**定长 2 字节/项**（小端 u16 = CP932 码值），索引 = i*2。
    依据：反汇编 0x4D88C0 `movzx eax, byte ptr [esi+edx*2]`（edx=i）；
    实测 `probe_tbl_enc.py`：blob 2864 = 16 头 + 1424 槽 x 2。
    返回 (ents, types, end)；ents[i]=None 表示空槽或异常项。
    """
    n = max(0, (len(blob) - TBL_OFF) // 2)
    ents, types = [], []
    for i in range(n):
        o = TBL_OFF + i * 2
        w = blob[o] | (blob[o + 1] << 8)
        c = None
        if w != 0:
            try:
                c = bytes(blob[o:o + 2]).decode('cp932')
            except Exception:
                c = None
            if c is not None and len(c) != 1:
                c = None          # 多字符（如 'ED' 打包）= 标记项，视为空
        ents.append(c)
        types.append(1 if not c else 2)
    return ents, types, TBL_OFF + n * 2


def is_cjk(ch):
    return ch is not None and len(ch) == 1 and '\u4e00' <= ch <= '\u9fff'


# ---------------- 载体码池 ----------------
def carrier_pool(reserved):
    """返回可用的 CP932 双字节码列表。

    优先使用【常规汉字区】—— 这条查表路径已在游戏内实测通过；
    User-Defined 区(0xF040+)作为备用（理论上同样按 CP932 解码，但未实测）。
    """
    pool = []
    seen = set()
    # 1) CP932 常规汉字区（实测可用）
    for hi in list(range(0x88, 0x9A)) + list(range(0xE0, 0xEB)):
        for lo in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            b = bytes((hi, lo))
            try:
                ch = b.decode('cp932')
            except Exception:
                continue
            if ch in reserved or ch in seen:
                continue
            seen.add(ch)
            pool.append(b)
    n_kanji = len(pool)
    # 2) 备用：CP932 用户定义区 0xF040-0xF9FC
    for hi in range(0xF0, 0xFA):
        for lo in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            b = bytes((hi, lo))
            try:
                ch = b.decode('cp932')
            except Exception:
                continue
            if ch in reserved or ch in seen:
                continue
            seen.add(ch)
            pool.append(b)
    return pool, n_kanji


# ---------------- 频率 ----------------
def display_text(r, field_zh=None):
    """这一行【最终真的会显示】的中文。
    多行字段（EN 含 \\n）优先取整字段译文；否则用 zh_new/zh_3dm。
    这样字频统计的是屏幕实际内容，而不是过时的单行译文。"""
    if field_zh:
        try:
            bi = int(r['blob_index']); off = int(r['offset'])
            en = _en_archive()
            if bi < len(en.blobs) and off < len(en.blobs[bi]):
                raw = bytes(en.blobs[bi])
                et = raw[off:read_run(raw, off)].decode('cp932', 'replace')
                if '\n' in et and et in field_zh:
                    return field_zh[et]
        except Exception:
            pass
    return strip_ascii_ws(r.get('zh_new') or '') or strip_ascii_ws(r.get('zh_3dm') or '')


_EN_CACHE = None
def _en_archive():
    global _EN_CACHE
    if _EN_CACHE is None:
        _EN_CACHE = s2a.Archive(os.path.join(BASE, 'res/LANG_EN.s2a.bak'))
    return _EN_CACHE


def char_freq(rows):
    field_zh = load_field_zh()
    cnt = collections.Counter()
    tot = 0
    for r in rows:
        t = display_text(r, field_zh)
        t = apply_repl(t)
        for ch in t:
            if ord(ch) < 0x80:
                continue
            if ch in ('\n', '\r', '\t'):
                continue
            cnt[ch] += 1
            tot += 1
    return cnt, tot


# ---------------- 规划 ----------------
def build_plan():
    """返回 (slots, chosen, cmap, stats)"""
    rows = list(csv.DictReader(open(CSV, encoding='utf-8')))
    tbl = s2a.Archive(os.path.join(BASE, 'res/cscv.s2a.bak'))
    tb = tbl.blobs[tbl.hash_map()[TBL_HASH]]
    ents, types, end = parse_entries(tb)

    # ---- v2.14 可用槽位 ----
    # index 1248..4095（排除 'ED'(1408) 与 ASCII 保留带）：
    #   1248-1279(32) + 1280-2047(768) + 2048-3071(1024) + 3072-4095(1024) = 2847 格
    # 原版 index 0-1247 全部保留：假名(0-255) / 日文汉字(256-1023) /
    #   STAFF 姓名(1024-1119) / 符号(1120-1151) / 图集A ASCII 区(1152-1247)
    slots = [i for i in range(A_EXT_FIRST, TBL_SLOTS) if i not in A_EXT_SKIP]
    kana_slots = []                     # v2.14：假名格不再回收（保留原版字形）
    n_ext = len(slots)
    n_staff = 0
    n_dead = 0
    kana_set = set()
    n_slot = len(slots)

    reserved = {c for c in ents if c}
    pool, n_kanji = carrier_pool(reserved)

    cnt, tot = char_freq(rows)

    # v2.31：小咕之歌歌词的用字也计入字库频率。歌词译文有两部分不在 text_v2.csv
    # 行内可统计的范围外（cscv[355] 英文行整套不在 CSV；LANG b1025 行在 CSV 但
    # 这里统一兜底），不计入会导致歌词生僻字装机后显示"？"。
    for _sk, _sja, _szh in SONG_EN_LINES:
        for _ch in apply_repl(_szh):
            if ord(_ch) < 0x80 or _ch in '\n\r\t':
                continue
            cnt[_ch] += 1

    # 已被"保留格"覆盖的字（符号/图标/姓名汉字等）不必占用我们的槽位
    # ⭐ v2.14：只把**非汉字**（标点/符号/假名/全角字母数字）视为"原版已有、免占格"。
    #   汉字一律走载体码 → 图集里画 SimSun 简体字形，保证中文观感与 v2.13 一致；
    #   原版 0-1247 的汉字条目/字形则留给**日文原文**（日语环境、日文名旧存档）使用。
    overwrite_set = set(slots)
    native_chars = {ents[i] for i in range(len(ents))
                    if i not in overwrite_set and ents[i] and len(ents[i]) == 1
                    and ord(ents[i]) >= 0x80 and not is_cjk(ents[i])}

    candidates = [c for c, _ in cnt.most_common() if c not in native_chars]

    # 保底字优先入字库：左右/斩 等难以替换的核心字（方向词、技能名用字）。
    # 只挤掉频次相近的尾部字，损失极小。
    # 注意：替换表的值必须全部使用高频已装字（check_repl.py 校验），
    # 不做"值用字自动优先"，否则几百个低频字会把高频尾部字挤出字库，得不偿失。
    force = [c for c in FORCE_CHARS if c in cnt and c not in native_chars]
    candidates = force + [c for c in candidates if c not in force]

    # ---- DLC01 汉化专用字：追加到末尾（不挤占既有字格，只用剩余空槽）----
    _dlc_add = [c for c in DLC_EXTRA_CHARS if c not in candidates and c not in native_chars]
    candidates = candidates + _dlc_add
    if len(candidates) > n_slot:
        print('  !! 候选字 %d > 可用格 %d —— 尾部 %d 字将被挤出（DLC 追加字在末尾，先被挤）'
              % (len(candidates), n_slot, len(candidates) - n_slot))
    chosen = candidates[:n_slot]

    cmap = {}
    k = 0
    for idx, ch in zip(slots, chosen):
        if idx in kana_set:
            # 借用假名自己的 CP932 码当载体码（字符表条目保持原样）
            cmap[ch] = ents[idx].encode('cp932')
        else:
            cmap[ch] = pool[k]
            k += 1

    covered = sum(cnt[c] for c in chosen) + sum(cnt[c] for c in cnt if c in native_chars)
    statistics = dict(rows=len(rows), total=tot, unique=len(cnt),
                      slots=n_slot, chosen=len(chosen), pool=len(pool), kanji=n_kanji,
                      kana_slots=len(kana_slots), kana_set=kana_set, slots_list=slots,
                      n_ext=n_ext, n_staff=n_staff, n_dead=n_dead,
                      native=sum(cnt[c] for c in cnt if c in native_chars),
                      native_set=native_chars,
                      coverage=covered / tot if tot else 0)
    return rows, ents, types, end, tb, slots, chosen, cmap, statistics


# ---------------- 应用 ----------------
def do_plan():
    rows, ents, types, end, tb, slots, chosen, cmap, st = build_plan()
    print('CSV 行数           : %d' % st['rows'])
    print('非ASCII 出现总次数  : %d' % st['total'])
    print('非ASCII 唯一字数    : %d' % st['unique'])
    _nb = len([i for i in st['slots_list'] if i < 256])          # 假名格
    _nA = len([i for i in st['slots_list'] if i >= 1024])         # 图集A 格
    print('可用图集格          : %d   (图集B汉字格 %d + 假名格 %d + 图集A格 %d)'
          % (st['slots'], st['slots'] - _nb - _nA, _nb, _nA))
    print('拟装入字数          : %d' % st['chosen'])
    print('载体码池            : %d  (其中 CP932 常规汉字区 %d)' % (st['pool'], st['kanji']))
    print('预计覆盖率          : %.2f%%' % (st['coverage'] * 100))
    cnt, tot = char_freq(rows)
    nat = st['native_set']
    uncovered = [(c, n) for c, n in cnt.most_common() if c not in cmap and c not in nat]
    print('原版已有(免占格)    : 出现 %d 次 (%.2f%%)' % (st['native'], st['native'] / tot * 100))
    print('未覆盖字数          : %d (出现 %d 次, %.2f%%)'
          % (len(uncovered), sum(n for _, n in uncovered),
             sum(n for _, n in uncovered) / tot * 100))
    print('最常用未覆盖字      : %s' % ''.join(c for c, _ in uncovered[:40]))
    print('装入字样例          : %s' % ''.join(chosen[:60]))


def encode_text(s, cmap, native):
    out = bytearray()
    for ch in s:
        o = ord(ch)
        if o < 0x80:
            out += bytes((o,))
        elif ch in cmap:
            out += cmap[ch]
        elif ch in native:
            out += ch.encode('cp932')       # 原版图集里就有，直接显示
        else:
            out += b'?'                     # 未覆盖的生僻字 -> 问号
    return bytes(out)


def fit_slot(enc, sb):
    """把编码结果裁剪到 <= sb 字节（不切断双字节字符）"""
    if len(enc) <= sb:
        return enc
    i = 0
    while i < len(enc):
        c = enc[i]
        ln = 1 if c < 0x80 or c == 0 else (2 if (0x81 <= c <= 0x9f or 0xe0 <= c <= 0xfc) else 1)
        if i + ln > sb:
            break
        i += ln
    return enc[:i]


# ---------------- 多行字段（整字段读写） ----------------
# 背景（2026-09-12 诊断）：多行台词是【同一条记录】内的一个字段，
#   [第1行]\x0A[第2行]\x0A...\x00 + 0填充
# 记录是定长块（128/256/416/512 字节），字段结束后是 0 填充，
# 下一个非零字节即下一条记录的头（ff ff ff ff ...）。
# 旧实现按 CSV 的 slot_bytes(=EN第1行+LF) 只写第1行，把 \x0A 一起清零，
# 导致第2行起丢失/残留，这是"多行只显示第一行"的根因。
#
# 现改为：整字段一起写（保留 \n），容量 = 到下一个非零字节 - 1（留 \x00）。
# 缺译文时退化为"只写第1行且清干净"（不再留残渣，至少不出乱码）。
FIELD_ZH_FILE = os.path.join(WORK, 'ml_zh_fields.json')
# 长文（>=6 行）阈值：编辑器/教程长句含 `<- BG>` 等菜单引用，属"故意保留原文"范围。
# 无译文时整段保留原文，**不做**"只留第 1 行"的退化成残句。
ML_LONG_LINES = 6


def load_field_zh():
    """{EN整字段文本(含\\n): 中文整字段文本(含\\n)}"""
    import json
    try:
        return json.load(open(FIELD_ZH_FILE, encoding='utf-8'))
    except Exception:
        return {}


def read_run(data, off, allow_lf=True):
    """从 off 读取文本 run，返回结束位置（0x20-0x7E / 双字节CP932 / 可选 0x0A）"""
    j, n = off, len(data)
    while j < n:
        c = data[j]
        if 0x20 <= c <= 0x7E or (allow_lf and c == 0x0A):
            j += 1
        elif 0x81 <= c <= 0xFE and j + 1 < n:
            try:
                data[j:j + 2].decode('cp932')
            except Exception:
                break
            j += 2
        else:
            break
    return j


def field_end(data, off):
    """字段结束位置（含 0 填充）：文本 run 之后的连续 0 全部吃掉"""
    k = read_run(data, off, True)
    while k < len(data) and data[k] == 0:
        k += 1
    return k


COLLIDE_CACHE = os.path.join(paths.BUILD_DIR, 'collide_cache.json')


def compute_collisions():
    """返回应保留原文的 LANG 槽位【日文原文】集合。

    判据：原文（<=64字节，含于 LANG 槽）同时以子串形式出现在
    cscv 的"独有 blob"（= 脚本/数据，非 681 个内容重复 blob）中。
    这类字符串可能被脚本按名字比对，翻译会导致比对失败（技能不生效假设）。
    结果缓存到 _work/collide_cache.json。
    """
    import json, hashlib
    if os.path.exists(COLLIDE_CACHE):
        try:
            return set(json.load(open(COLLIDE_CACHE, encoding='utf-8')))
        except Exception:
            pass
    lj = s2a.Archive(os.path.join(BASE, 'res/LANG_JA.s2a.bak'))
    cs = s2a.Archive(os.path.join(BASE, 'res/cscv.s2a.bak'))
    lang_hashes = {hashlib.md5(bytes(b)).hexdigest() for b in lj.blobs}
    uniq = [bytes(b) for b in cs.blobs
            if hashlib.md5(bytes(b)).hexdigest() not in lang_hashes]
    print('  碰撞分析: cscv 独有 blob %d 个' % len(uniq))
    texts = set()
    for b in lj.blobs:
        bb = bytes(b)
        i = 0
        while i < len(bb):
            j = bb.find(b'\x00', i)
            if j < 0:
                j = len(bb)
            seg = bb[i:j]
            i = j + 1
            if not (2 <= len(seg) <= 64):
                continue
            try:
                t = seg.decode('cp932')
            except Exception:
                continue
            if not t.strip():
                continue
            texts.add(t)
    print('  碰撞分析: 候选串 %d 个' % len(texts))
    result = set()
    for n, t in enumerate(texts):
        if n % 2000 == 0:
            print('    ... %d/%d' % (n, len(texts)))
        tb = t.encode('cp932')
        for ub in uniq:
            if ub.find(tb) >= 0:
                result.add(t)
                break
    print('  碰撞分析: 命中 %d 个' % len(result))
    try:
        os.makedirs(os.path.dirname(COLLIDE_CACHE), exist_ok=True)
        json.dump(sorted(result), open(COLLIDE_CACHE, 'w', encoding='utf-8'), ensure_ascii=True)
    except Exception:
        pass
    return result


def field_spans(run):
    """yield (相对起点, 长度, 解码串) —— 0x00 分界的 run 内可作为"字段值"的候选段：
    1) 剥掉前导 0xFF 标记后的整段（武器表：ff ff ff ff | 名字 | 00 ...）
    2) key=值 形式里 = 号之后的值段"""
    k = 0
    while k < len(run) and run[k] == 0xFF:
        k += 1
    seg = run[k:]
    if 2 <= len(seg) <= 64:
        try:
            t = seg.decode('cp932')
            yield k, len(seg), t
        except Exception:
            pass
    if b'=' in seg:
        v = seg.split(b'=', 1)[1]
        if 2 <= len(v) <= 64:
            try:
                t = v.decode('cp932')
                yield k + len(seg) - len(v), len(v), t
            except Exception:
                pass


def build_canonical(rows, lang_a, collide, cmap, native):
    """一致翻译模式核心：
    1) 扫描 cscv独有 blob 中所有 \\x00 分界字段 -> {日文原文: [字段长度...]}
    2) 对每个碰撞串取统一译文（该原文在 LANG 槽位中最常见的 zh_new）
    3) 仅当译文能放进它的【所有】LANG 槽位和【所有】cscv独有 字段时才翻译；
       否则整串保留原文（全有或全无，保证跨表比对双方永远一致）
    返回 (canonical: {ja: enc字节或None}, fields: {ja: [字段长度...]})
    """
    import hashlib
    cs = s2a.Archive(os.path.join(BASE, 'res/cscv.s2a.bak'))
    lang_hashes = {hashlib.md5(bytes(b)).hexdigest() for b in lang_a.blobs}
    uniq = [bytes(b) for b in cs.blobs
            if hashlib.md5(bytes(b)).hexdigest() not in lang_hashes]

    # 1) 独有 blob 字段清单（字段 = 0x00 分界的 run，剥掉前导 0xFF 标记后即字符串；
    #    武器表记录形如 ff ff ff ff | 名字 | 00 00 ...，名字前是 0xFF 不是 0x00。
    #    另支持 key=值 形式：值部分单独登记）
    fields = collections.defaultdict(list)
    for b in uniq:
        i, n = 0, len(b)
        while i < n:
            j = b.find(b'\x00', i)
            if j < 0:
                j = n
            run = b[i:j]
            i = j + 1
            for _s, _l, t in field_spans(run):
                if t.strip():
                    fields[t].append(_l)

    # 2) LANG 侧按原文分组 -> [Counter(zh), min槽位长度]
    lang_groups = collections.defaultdict(lambda: [collections.Counter(), 10 ** 9])
    seen = set()
    for r in rows:
        try:
            bi, off, sb = int(r['blob_index']), int(r['offset']), int(r['slot_bytes'])
        except Exception:
            continue
        if (bi, off) in seen or bi >= len(lang_a.blobs) or off + sb > len(lang_a.blobs[bi]):
            continue
        seen.add((bi, off))
        seg = bytes(lang_a.blobs[bi][off:off + sb]).split(b'\x00')[0]
        if not (2 <= len(seg) <= 64):
            continue
        try:
            ja = seg.decode('cp932')
        except Exception:
            continue
        if ja not in collide:
            continue
        zh = apply_repl(strip_ascii_ws(r.get('zh_new') or ''))
        if zh:
            lang_groups[ja][0][zh] += 1
        lang_groups[ja][1] = min(lang_groups[ja][1], sb)

    # 3) 决策：全有或全无
    canonical = {}
    for ja in collide:
        cnt, min_sb = lang_groups.get(ja, [None, 10 ** 9])
        if not cnt:
            canonical[ja] = None
            continue
        zh = cnt.most_common(1)[0][0]
        enc = encode_text(zh, cmap, native)
        if not enc or len(enc) > min_sb:
            canonical[ja] = None
            continue
        # cscv独有 字段 fit；从未作为完整字段出现 -> 保守不翻
        fl = fields.get(ja)
        if not fl or any(len(enc) > sl for sl in fl):
            canonical[ja] = None
            continue
        canonical[ja] = enc
    return canonical, fields


def rewrite_text(rows, cmap, native, sync_cscv=True, keep_collide=False, skip_blobs=(), consistent=False,
                 menu_exempt=False, field_fix=True, ui_always=False, slot_release=False,
                 desc_release=False):
    """把译文写进 LANG_JA / LANG_EN / cscv(与 LANG 重复的部分)。

    cscv.s2a 里有大量与 LANG 逐字节相同的 blob（实测 681 个），游戏可能从它读文本，
    所以按【内容相同 -> 同一套 offset 编辑】的方式一并改写，保证两边一致。

    field_fix=True 时，多行字段按【整字段】写入（保留 \\n），修复"只显示第一行"。
    """
    stats = collections.Counter()
    import hashlib
    collide = compute_collisions() if (keep_collide or consistent) else set()
    if keep_collide and not consistent:
        print('  碰撞白名单(保留原文): %d 个不同字符串' % len(collide))
    menu_ok = load_menu_ok() if menu_exempt else set()
    ui_set = load_ui_always() if ui_always else set()
    if ui_always:
        print('  UI 词表增强: %d 个纯 UI 串跨 blob 翻译 (ui_always.json)' % len(ui_set))
    if menu_exempt:
        print('  菜单豁免(blobs %s): %d 个 UI 串照常翻译'
              % (','.join(str(b) for b in MENU_EXEMPT_BLOBS), len(menu_ok)))
    slot_rel = load_slot_release() if slot_release else None
    if slot_release:
        if slot_rel:
            print('  槽位级放行: %s 排除含 %s'
                  % (slot_rel.get('rules'), slot_rel.get('exclude_contains')))
        else:
            print('  槽位级放行: 未启用（slot_release.json 缺失或 enabled=false）')
    desc_rel = load_desc_release() if desc_release else None
    if desc_release:
        if desc_rel:
            print('  说明文放行: %s'
                  % ', '.join('%s(b%s/%s/%s)' % (r.get('name'), r.get('blobs'),
                                                 r.get('stride'), r.get('pos'))
                              for r in desc_rel.get('rules', ())))
        else:
            print('  说明文放行: 未启用（desc_release.json 缺失或 enabled=false）')

    # ---- 1) 计算每个 LANG blob 的编辑清单 ----
    lang_a = s2a.Archive(os.path.join(BASE, 'res/LANG_JA.s2a.bak'))
    en_a = s2a.Archive(os.path.join(BASE, 'res/LANG_EN.s2a.bak')) if field_fix else None
    field_zh = load_field_zh() if field_fix else {}
    if field_fix:
        print('  多行整字段译表: %d 条' % len(field_zh))
    # ---- v2.58 章节名/称号保护：这些槽位是【按字符串索引的键】，一律保留原文 ----
    # 2026-09-17 实验结论：Steam 语言=日语时 Q16 城出现、=英语时不出现 ⇒ 章节名是键；
    # 称号名同理（翻译后称号无法取得）。故整表保留原文，且装机后无需再手工还原。
    ct_guard, ct_recs, ct_vals = load_chap_title_guard()
    global _CT_VALUE_CACHE
    _CT_VALUE_CACHE = set(ct_vals)
    if ct_guard or ct_recs or ct_vals:
        print('  章节名/称号保护: %d 个整字段槽位 + %d 条按记录规则 + %d 条按值规则 一律保留原文'
              % (len(ct_guard), len(ct_recs), len(ct_vals)))

    if consistent:
        # ======= 一致翻译模式（测试E）：同一个日文原文在 LANG 槽位与
        # cscv独有 字段里的所有出现统一译成同一个 CP932 串（全有或全无）=======
        canonical, fields = build_canonical(rows, lang_a, collide, cmap, native)
        n_canon = sum(1 for v in canonical.values() if v is not None)
        print('  一致翻译: 碰撞串 %d, 可统一翻译 %d, 保留原文 %d'
              % (len(canonical), n_canon, len(canonical) - n_canon))

    edits = collections.defaultdict(list)     # blob_index -> [(off, sb, newbytes)]
    # ★★ v2.64（2026-09-17，批次 t101）：cscv 同步"键名保护"集合。
    # 背景（t95~t98 实锤）：cscv.s2a 里有 653~687 个"与 LANG_JA 内容逐字节相同"的
    #   重复 blob。步骤 3 会把 LANG 侧的 edits 原样同步进去 —— 包括用【载体码】编码的
    #   译文。但 cscv 里这些 blob 是【游戏脚本/数据层】：游戏在那里按 **CP932 解码后的
    #   字符串**做【按名比对】。写入载体码后字符串彻底变了：
    #       '勇者城' 9745 8ED2 8FE9  ->  88FC 88DB 8972  = '蔭維詠'
    #       '魔王ザントヘル'          ->  '易緯駆悦淳飲'
    #   其中 stride288 pos28 =【关卡/剧本标识符】字段，全表 27 处原值 '勇者城'
    #   → 装机后全变 '蔭維詠' → 游戏按键名找不到关卡资源 → **勇者城消失**。
    #   这同时解释 EN/JP 双侧都坏（cscv 只有一份，与 Steam 语言无关）。
    #   对照：官方 EN 版完全不翻 cscv（'Hero Castle' 在 cscv.bak 中 0 处）。
    #
    # 修法：cscv 的"内容匹配同步"**只同步显示类槽位**，跳过"键名类"槽位。
    #   判据 = 该槽位的【日文原文】∈ collide 白名单
    #   （collide 的定义正是"该串在 cscv 独有 blob 里出现过" ⇒ 会被脚本按名比对）。
    #   实测命中率呈双峰（`t101_collide.py`）：
    #     键名字段——292/96=67% 424/24=100% 660/4,40=99% 580/4=90% 580/372=98%
    #              288/28=79% 288/92=83% 424/260=78% 440/208,240,272,304=100%
    #     台词字段——292/160=6% 196/164=0% 292/224=0% 288/156=2% 288/220=0%
    #   ⇒ 精准命中键名、几乎不误伤台词。
    cscv_skip_keys = set()                    # {(bi, off)} 只在 cscv 侧跳过
    seen = set()
    for r in rows:
        try:
            bi = int(r['blob_index']); off = int(r['offset']); sb = int(r['slot_bytes'])
        except Exception:
            continue
        if (bi, off) in seen:
            continue
        seen.add((bi, off))
        # v2.58 章节名/称号保护：命中 (blob, stride, pos) 的槽位一律保留原文
        # v2.62 扩展：支持"按记录号"保护（Q16 单条例外），见 chap_title_hit()
        # v2.63 扩展：支持"按值"保护 —— 先解出该槽日文原文再判定（value_rules）
        if ct_guard or ct_recs or _CT_VALUE_CACHE:
            _st = blob_stride(lang_a, bi)
            _val = None
            if _CT_VALUE_CACHE and bi < len(lang_a.blobs) and off < len(lang_a.blobs[bi]):
                _raw = bytes(lang_a.blobs[bi][off:off + sb]).split(b'\x00')[0]
                try:
                    _val = strip_f8f3(_raw.decode('cp932').strip())
                except Exception:
                    _val = None
            if _st and chap_title_hit(ct_guard, ct_recs, bi, _st,
                                      (off - 16) % _st, (off - 16) // _st, _val):
                stats['chaptitle'] += 1
                continue
        # v2.51 说明文放行：命中 (blob, stride, pos) 规则的说明字段，即使本表在 skip_blobs 里也照常翻译
        desc_ok = bool(desc_rel) and desc_release_hit(desc_rel, lang_a, bi, off)
        if bi in skip_blobs and not desc_ok:
            stats['skipblob'] += 1
            continue
        if bi in skip_blobs:
            stats['descskipok'] += 1    # 机制表内被放行的说明槽
        if bi >= len(lang_a.blobs) or off + sb > len(lang_a.blobs[bi]):
            continue
        raw = bytes(lang_a.blobs[bi][off:off + sb]).split(b'\x00')[0]
        try:
            ja = raw.decode('cp932').strip()
        except Exception:
            ja = ''
        # v2.22：字段值可能带 \uf8f3 前缀（ff ff ff ff）——碰撞/豁免判定统一用剥离后的串，
        # 否则会假命中 collide（白名单里有 3796 个 f8f3 前缀噪音串）而被误判为专有名词保留。
        ja_cmp = strip_f8f3(ja)
        if consistent and ja in canonical:
            enc = canonical[ja]
            if enc is None:
                stats['kept'] += 1
                continue
            edits[bi].append((off, sb, 0, enc))
            stats['canon'] += 1
            continue
        # --- 多行字段的 EN 原文（也用于下面"名字保留原文"的路径）---
        en_txt = None
        if field_fix:
            eb = bytes(en_a.blobs[bi]) if bi < len(en_a.blobs) else b''
            if eb and off < len(eb):
                en_txt = eb[off:read_run(eb, off)].decode('cp932', 'replace')
        if keep_collide and not consistent:
            if ja_cmp and ja_cmp in collide:
                if ja_cmp in SONG_OK:
                    pass  # v2.31 小咕之歌歌词放行：纯显示文本，不参与按名比对（见 SONG_OK 注释）
                elif menu_exempt and bi in MENU_EXEMPT_BLOBS and ja_cmp in menu_ok:
                    pass  # v2.2 菜单豁免：纯 UI 串在 UI blob 里照常翻译
                elif ui_set and ja_cmp in ui_set:
                    pass  # v2.15 UI 词表增强：纯 UI 标签/提示，跨 blob 照常翻译
                elif desc_rel and desc_release_hit(desc_rel, lang_a, bi, off):
                    # v2.51 说明文放行：说明字段命中 collide 属【假命中】（cscv 里是同一张表的副本，
                    # 不是按名比对的键）⇒ 照常翻译。同表的名字字段不在规则内，仍保留原文。
                    stats['descrel'] += 1
                elif (slot_rel and not slot_release_excl(slot_rel, ja_cmp)
                      and slot_release_hit(slot_rel, lang_a, bi, off)):
                    # v2.49 槽位级放行（TODO-2C 第二步）：说话人名字段是纯显示字段，
                    # 命中 collide 也照常翻译；同名副本（其它表/其它 pos）不受影响。
                    stats['slotrel'] += 1
                elif '「' in ja_cmp:
                    # v2.24 对话放行：带引号的对话文本（前半句「… / 整段 名字「…」）
                    # 不是机制比对目标——名字串（道具/武器/敌人名）均不含引号。
                    # 修复"剧情两行只翻第二行"（Q47 革命等）：前半句带「命中 collide 被留英文，
                    # 后半句带全角空格前缀被 .strip() 剥掉而意外翻掉（实测翻后无副作用）。
                    # 实测范围：此类保留槽 3020 个，全部在机制 blob 外、全部有译文。
                    # ★ v2.53(TODO-4) 放宽：原判据要求 startswith('「') 或 endswith('」')，
                    #   漏掉了"跨行对话的第 1 行"——形如 `マオウ「わたしが協力する人間は`
                    #   （以名字开头、句未收尾），实测新增放行恰好 4 槽（b427×2 / b757×2），
                    #   全部有译文、全部在机制 blob 之外（`t4_collide_probe.py` 实测）。
                    pass
                else:
                    # v2.15：专有名词（敌人/道具名）第一行【保留原文】——
                    # 名字字节原样不动，不影响脚本按名字比对；只把后面几行说明翻成中文。
                    # mode=2：写入时 = 本文件自己的第一行 + 译文说明。
                    if field_fix and en_txt and '\n' in en_txt:
                        fz = field_zh.get(en_txt)
                        if fz and '\n' in fz:
                            rest = fz.split('\n', 1)[1]
                            enc = encode_text(apply_repl(rest), cmap, native)
                            jd = bytes(lang_a.blobs[bi])
                            ebd = bytes(en_a.blobs[bi]) if bi < len(en_a.blobs) else b''
                            kj = jd.find(b'\n', off)
                            ke = ebd.find(b'\n', off)
                            hja = (kj - off + 1) if kj >= 0 else 0
                            hen = (ke - off + 1) if ke >= 0 else 0
                            cap = (min(field_end(jd, off), field_end(ebd, off)) - off - 1
                                   if ebd else 0)
                            if enc and hja and hen and len(enc) + max(hja, hen) <= cap:
                                edits[bi].append((off, sb, 2, enc))
                                stats['ml_name_kept'] += 1
                                continue
                    stats['kept'] += 1
                    continue
        # --- 多行字段：整字段写入（保留 \n），修复"只显示第一行" ---
        if en_txt and '\n' in en_txt:
            fz = field_zh.get(en_txt)
            if not fz and en_txt.count('\n') + 1 >= ML_LONG_LINES:
                stats['ml_skip_long'] += 1     # 长文无译文 -> 整段保留原文（不写、不清）
                continue
            if fz:
                t = apply_repl(fz)
            else:
                t = apply_repl(strip_ascii_ws(r.get('zh_new') or ''))   # 无整字段译文 -> 退化：只写第1行但清干净
                stats['ml_notrans'] += 1
            if not t.strip(' \t\r\n\v\f\x00'):
                stats['empty'] += 1
                continue
            enc = encode_text(t, cmap, native)
            cap = min(field_end(bytes(lang_a.blobs[bi]), off),
                      field_end(bytes(en_a.blobs[bi]), off)) - off - 1
            if len(enc) > cap:
                stats['ml_overflow'] += 1
                continue
            edits[bi].append((off, sb, 1, enc))
            stats['ml'] += 1
            continue
        # v2.23 修复：只剥 ASCII 空白，**保留全角空格 U+3000**。
        # 某些字段（如 TOWNPLACEHOLDERLONG「　　　　　　村」）用前导全角空格做排版对齐，
        # 用 .strip() 会把它们一起去掉 → 对齐全丢。
        t = apply_repl(strip_ascii_ws(r.get('zh_new') or ''))
        if not t:
            stats['empty'] += 1
            continue
        enc = fit_slot(encode_text(t, cmap, native), sb)
        if len(enc) > sb:
            stats['overflow'] += 1
            continue
        edits[bi].append((off, sb, 0, enc))
    # ★★ v2.64：算出"cscv 键名保护"集合 —— 这些槽位在 LANG 侧照常翻译，
    # 但在 cscv 的"内容匹配同步"（步骤 3）里必须保留原版 CP932 字节。
    # 判据：该槽位的日文原文 ∈ collide（= 在 cscv 独有 blob 里作为按名比对的键出现）。
    if collide:
        for r in rows:
            try:
                bi2 = int(r['blob_index']); off2 = int(r['offset']); sb2 = int(r['slot_bytes'])
            except Exception:
                continue
            if bi2 >= len(lang_a.blobs) or off2 + sb2 > len(lang_a.blobs[bi2]):
                continue
            if (bi2, off2) not in seen:
                continue                     # 不是本轮的编辑槽位，无需记录
            _raw = bytes(lang_a.blobs[bi2][off2:off2 + sb2]).split(b'\x00')[0]
            try:
                _ja = strip_f8f3(_raw.decode('cp932').strip())
            except Exception:
                continue
            if _ja and _ja in collide:
                cscv_skip_keys.add((bi2, off2))
        if cscv_skip_keys:
            print('  ★cscv 键名保护: %d 个槽位在 cscv 侧保持原版 CP932（LANG 侧照常翻译）'
                  % len(cscv_skip_keys))

    print('  待改写 slot 数: %d (覆盖 %d 个 blob)%s%s%s'
          % (sum(len(v) for v in edits.values()), len(edits),
             ' [统一译名 %d]' % stats['canon'] if consistent else '',
             ' [槽位级放行命中 %d]' % stats['slotrel'] if stats['slotrel'] else '',
             ' [说明文放行命中 %d / 机制表内放行 %d]' % (stats['descrel'], stats['descskipok'])
             if desc_rel else ''))

    # 内容 -> LANG blob 索引
    lang_hash = {}
    for i, b in enumerate(lang_a.blobs):
        if edits.get(i):
            lang_hash.setdefault(hashlib.md5(bytes(b)).hexdigest(), i)

    # ---- 2) LANG_JA / LANG_EN ----
    for rel in TEXT_FILES:
        src = os.path.join(BASE, rel)
        bk = src + '.bak'
        if not os.path.exists(src):
            continue
        if not os.path.exists(bk):
            shutil.copy2(src, bk)
        a = s2a.Archive(bk)
        blobs = [bytearray(b) for b in a.blobs]
        n = 0
        for bi, lst in edits.items():
            if bi >= len(blobs):
                continue
            orig = bytes(blobs[bi])
            for off, sb, mode, enc in lst:
                sb2 = (field_end(orig, off) - off) if mode else sb
                if sb2 <= 0 or off + sb2 > len(blobs[bi]):
                    continue
                blobs[bi][off:off + sb2] = b'\x00' * sb2
                if mode == 2:
                    # mode2 = 名字保留原文：保留本文件自己的第一行，其后写译文说明
                    k = orig.find(b'\n', off, off + sb2)
                    if k < 0:
                        continue
                    head = bytes(orig[off:k + 1])
                    if len(head) + len(enc) > sb2:
                        continue
                    blobs[bi][off:off + len(head)] = head
                    blobs[bi][off + len(head):off + len(head) + len(enc)] = enc
                else:
                    blobs[bi][off:off + len(enc)] = enc
                n += 1
        s2a.pack(src, a.entries, blobs)
        print('  文本 %s: 写入 %d 处' % (rel, n))

    # ---- 3) cscv.s2a（内容匹配；读【当前】文件，因为字符表已在其上更新）----
    # ★★ v2.64：跳过"键名保护"槽位（cscv 是脚本层，按 CP932 原码做按名比对，
    #    写入载体码会让字符串彻底变掉 ⇒ 勇者城/魔王名等资源找不到）。
    rel = 'res/cscv.s2a'
    src = os.path.join(BASE, rel)
    if sync_cscv and os.path.exists(src):
        a = s2a.Archive(src)
        blobs = [bytearray(b) for b in a.blobs]
        n = 0
        n_key = 0
        for j, b in enumerate(a.blobs):
            h = hashlib.md5(bytes(b)).hexdigest()
            bi = lang_hash.get(h)
            if bi is None:
                continue
            orig = bytes(blobs[j])
            for off, sb, mode, enc in edits[bi]:
                if (bi, off) in cscv_skip_keys:
                    n_key += 1
                    continue
                sb2 = (field_end(orig, off) - off) if mode else sb
                if sb2 <= 0 or off + sb2 > len(blobs[j]):
                    continue
                blobs[j][off:off + sb2] = b'\x00' * sb2
                if mode == 2:
                    k = orig.find(b'\n', off, off + sb2)
                    if k < 0:
                        continue
                    head = bytes(orig[off:k + 1])
                    if len(head) + len(enc) > sb2:
                        continue
                    blobs[j][off:off + len(head)] = head
                    blobs[j][off + len(head):off + len(head) + len(enc)] = enc
                else:
                    blobs[j][off:off + len(enc)] = enc
                n += 1
        s2a.pack(src, a.entries, blobs)
        print('  文本 %s: 写入 %d 处 (内容匹配的重复 blob)%s'
              % (rel, n, '，键名保护跳过 %d 处' % n_key if n_key else ''))

    # ---- 4) cscv独有 blob 的同名字段替换（一致翻译模式）----
    if consistent and sync_cscv and os.path.exists(src):
        a = s2a.Archive(src)
        blobs = [bytearray(b) for b in a.blobs]
        lang_hashes = {hashlib.md5(bytes(b)).hexdigest() for b in lang_a.blobs}
        n = 0
        for j, b in enumerate(a.blobs):
            bb = bytes(b)
            if hashlib.md5(bb).hexdigest() in lang_hashes:
                continue                     # 重复 blob 已由步骤3处理
            out = bytearray(bb)
            i, ln = 0, len(bb)
            while i < ln:
                k = bb.find(b'\x00', i)
                if k < 0:
                    k = ln
                run = bb[i:k]
                i = k + 1
                for s_off, s_len, t in field_spans(run):
                    enc = canonical.get(t)
                    if not enc or len(enc) > s_len:
                        continue
                    out[i + s_off: i + s_off + s_len] = \
                        enc + b'\x00' * (s_len - len(enc))
                    n += 1
            blobs[j] = out
        s2a.pack(src, a.entries, blobs)
        print('  文本 %s: 独有字段同步替换 %d 处' % (rel, n))
    print('  空槽 %d / 溢出 %d' % (stats['empty'], stats['overflow']))
    print('  多行整字段 %d 处 (其中无译文退化为单行 %d, 长文保留原文 %d, 超容量跳过 %d,'
          ' 名字保留原文仅翻说明 %d)'
          % (stats['ml'], stats['ml_notrans'], stats['ml_skip_long'], stats['ml_overflow'],
             stats['ml_name_kept']))
    return stats


def rewrite_atlas_cscv(slots, chosen, cmap, kana_set=frozenset()):
    # ---- 图集 ----
    at = s2a.Archive(os.path.join(BASE, 'res/texture.s2a.bak'))
    hm = at.hash_map()
    blobs = [bytes(b) for b in at.blobs]

    ob = Image.open(io.BytesIO(blobs[hm[B_HASH]]))      # 原版图集B 512x512 (32列)
    oa = Image.open(io.BytesIO(blobs[hm[A_HASH]]))      # 原版图集A 256x256 (16列)

    if EXPAND_4096:
        # ---- v2.13：两张图集均 512x1024 ----
        # ① 原版整幅贴到 (0,0)：
        #    · 图集A 的 ASCII 硬编码带(x<256, y 96..223) 就地保留 → 数字/英文安全
        #    · 图集B 的 i 0..511 新格=旧格，天然原位
        # ② 把「原版有内容但新格≠旧格」的字形搬到新格（i 512..1279）
        # ③ 最后画我们分配的汉字
        nb = Image.new('P', (A_W, A_TALL), 0)
        nb.putpalette(ob.getpalette())
        nb.paste(ob, (0, 0))
        na = Image.new('P', (A_W, A_TALL), 0)
        na.putpalette(oa.getpalette())
        na.paste(oa, (0, 0))
        aset = set(slots)
        n_moved = n_skip = 0
        for i in range(0, 1280):                 # 原版只有 0..1279 有字形
            if i in aset:
                continue                         # 会重画，无需搬
            opg, ou, ov = old_cell(i)
            src = ob if opg == 62 else oa
            if ou + CELL > src.size[0] or ov + CELL > src.size[1]:
                n_skip += 1
                continue                         # 旧格在图集外（原版空位区）
            npg, nu, nv = game_cell(i)
            if (npg, nu, nv) == (opg, ou, ov):
                continue                         # 位置不变
            (nb if npg == 62 else na).paste(
                src.crop((ou, ov, ou + CELL, ov + CELL)), (nu, nv))
            n_moved += 1
        pxb, pxA = nb.load(), na.load()

        def put(px, u, v, m, page):
            """三层写入：0 透明 / 1 白面 / 2 灰厚度 / 3 近黑描边（索引按图集查 LAYER）"""
            w, g, e = LAYER[page]
            for y in range(CELL):
                row = m[y]
                for x in range(CELL):
                    c = row[x]
                    px[u + x, v + y] = w if c == 1 else (g if c == 2 else (e if c == 3 else 0))

        for idx, ch in zip(slots, chosen):
            page, u, v = game_cell(idx)
            put(pxb if page == 62 else pxA, u, v, glyph3(ch, page), page)
        print('  图集搬迁: 原版字形移动 %d 格, 跳过 %d (图集外/空位)' % (n_moved, n_skip))
    else:
        pb = ob.getpalette()
        nb = Image.new('P', (512, 512), 0)
        nb.putpalette(pb)
        nb.paste(ob, (0, 0))
        pxb = nb.load()
        _nw, _nh = max(oa.size[0], A_W), max(oa.size[1], A_TALL)
        if (_nw, _nh) != oa.size:
            na = Image.new('P', (_nw, _nh), 0)
            na.putpalette(oa.getpalette())
            na.paste(oa, (0, 0))
        else:
            na = oa.copy()
        pxA = na.load()

        def draw(px, cell, cols, m, page):
            w, g, e = LAYER[page]
            r, c = divmod(cell, cols)
            for y in range(CELL):
                row = m[y]
                for x in range(CELL):
                    v = row[x]
                    px[c * CELL + x, r * CELL + y] = w if v == 1 else (g if v == 2 else (e if v == 3 else 0))

        for idx, ch in zip(slots, chosen):
            if idx < 1024:
                draw(pxb, blk_cell(idx), COLS_B, glyph3(ch, 62), 62)
            else:
                draw(pxA, a_cell(idx), COLS_A, glyph3(ch, 63), 63)   # v2.10: 32 列布局

    for img, h, tag in ((nb, B_HASH, 'B'), (na, A_HASH, 'A')):
        o = io.BytesIO()
        img.save(o, format='BMP')
        blobs[hm[h]] = o.getvalue()
    s2a.pack(os.path.join(BASE, 'res/texture.s2a'), at.entries, blobs)
    if EXPAND_4096:
        print('  图集已重画: 图集B/A 各 %dx%d (32x64 格, U&31 / V&63, 支持 index 0-%d)'
              % (nb.size[0], nb.size[1], TBL_SLOTS - 1))
    else:
        print('  图集已重画: 图集B(512x512) + 图集A(%dx%d, 32列布局, 支持 index 1024-%d)'
              % (na.size[0], na.size[1], A_EXT_LAST))

    # ---- 字符表（定长 2 字节/项；v2.9 加长到 TBL_SLOTS 项）----
    import struct as _st
    ac = s2a.Archive(os.path.join(BASE, 'res/cscv.s2a.bak'))
    ahm = ac.hash_map()
    blob = ac.blobs[ahm[TBL_HASH]]
    ents, types, end = parse_entries(blob)
    if len(ents) < 1409:
        raise SystemExit('!! 字符表解析异常: 仅 %d 项 (<1409)，中止' % len(ents))
    new = list(ents)
    if len(new) < TBL_SLOTS:
        new += [None] * (TBL_SLOTS - len(new))      # v2.9：追加空槽供扩容使用
    n_kana_keep = 0
    for idx, ch in zip(slots, chosen):
        if idx in kana_set:
            n_kana_keep += 1          # 方案1：假名条目保留，只重画了像素
            continue
        new[idx] = cmap[ch].decode('cp932')     # 载体码对应的字符
    body = bytearray()
    _skip_set = set(A_EXT_SKIP)
    for i, c in enumerate(new):
        if i in _skip_set and TBL_OFF + i * 2 + 2 <= len(blob):
            body += bytes(blob[TBL_OFF + i * 2: TBL_OFF + i * 2 + 2])   # 保留原样（'ED' 标记）
        elif not c:
            body += b'\x00\x00'
        else:
            e = c.encode('cp932')
            if len(e) == 1:
                e += b'\x00'
            body += bytes(e[:2])
    newblob = bytearray(blob[:TBL_OFF]) + body
    _st.pack_into('<I', newblob, 8, TBL_SLOTS // 16)   # 头 offset8 = 项数上限/16
    print('  字符表: %d 项/%d 字节 -> %d 项/%d 字节, 头[8]=%d [假名条目保留 %d 格]'
          % (len(ents), len(blob), TBL_SLOTS, len(newblob), TBL_SLOTS // 16, n_kana_keep))
    cb = [bytearray(x) for x in ac.blobs]
    cb[ahm[TBL_HASH]] = bytearray(newblob)
    s2a.pack(os.path.join(BASE, 'res/cscv.s2a'), ac.entries, cb)


def patch_exe_unlock():
    """解开字符表 1280 上限：新增 .atbl 节 + 改 6 处立即数。可在 revert 时从 .bak 还原。"""
    import struct as _s
    src = EXE + '.bak'
    if not os.path.exists(src):
        raise SystemExit('!! 缺少 HMH2.exe.bak，无法打补丁')
    d = bytearray(open(src, 'rb').read())

    def u16(o): return _s.unpack_from('<H', d, o)[0]
    def u32(o): return _s.unpack_from('<I', d, o)[0]
    def w16(o, v): _s.pack_into('<H', d, o, v)
    def w32(o, v): _s.pack_into('<I', d, o, v)

    pe = u32(0x3C)
    if bytes(d[pe:pe + 4]) != b'PE\0\0':
        raise SystemExit('!! 不是 PE 文件')
    nsec = u16(pe + 6)
    optsz = u16(pe + 20)
    opt = pe + 24
    imgbase = u32(opt + 28)
    sec_align = u32(opt + 32)
    file_align = u32(opt + 36)
    sec_tab = opt + optsz

    def al(v, a):
        return (v + a - 1) // a * a

    secs = []
    for i in range(nsec):
        o = sec_tab + i * 40
        nm = bytes(d[o:o + 8]).rstrip(b'\0').decode('latin1')
        vsize, vaddr, rawsz, rawptr = _s.unpack_from('<IIII', d, o + 8)
        secs.append((nm, vaddr, vsize, rawptr, rawsz))
    if any(s[0] == '.atbl' for s in secs):
        raise SystemExit('!! exe 已含 .atbl 节（请先 revert）')

    last_end = max(vaddr + al(vsize, sec_align) for _, vaddr, vsize, _, _ in secs)
    new_va = al(last_end, sec_align)              # 这是 RVA（节表里存的）
    if new_va + imgbase != A_TBL_VA:
        raise SystemExit('!! 新节 RVA 0x%08X -> VA 0x%08X，与常量 A_TBL_VA=0x%08X 不符，中止'
                         % (new_va, new_va + imgbase, A_TBL_VA))
    file_size = len(d)
    new_raw = al(file_size, file_align)
    new_size = al(A_TBL_SIZE, file_align)  # v2.11: 32KB（坐标表 16KB + 排序表 16KB）

    def va2off(va):
        rva = va - imgbase
        for _nm, vaddr, vsize, rawptr, rawsz in secs:
            if vaddr <= rva < vaddr + max(vsize, rawsz):
                return rawptr + (rva - vaddr)
        return None

    N = TBL_SLOTS                          # 4096 项（EXPAND_4096）

    # --- 改指令（先改，再追加节，避免偏移失效；都在已存在数据内） ---
    p = va2off(0x4D895B)                   # cmp edi, 0x13fc
    if p is None or bytes(d[p:p + 2]) != b'\x81\xff':
        raise SystemExit('!! 循环上限指令未匹配 (%s)' % (hex(p) if p else 'None'))
    # ⚠️ 必须写 4N-4：循环 `cmp edi,L ; jl`（edi = 4i-4）迭代次数 = L/4 + 1。
    #    写成 N*4 会多跑一轮（i=N），排序表指针写到 .atbl 末尾之外 → **越界写 → 闪退**
    #    （v2.11/v2.12 崩溃的根因；原版 N=1280 用的正是 0x13FC = 4*1280-4）。
    w32(p + 2, N * 4 - 4)

    p = va2off(0x4D861F)                   # mov ebx, 0x4ff
    if p is None or d[p] != 0xBB:
        raise SystemExit('!! 二分查找 hi 指令未匹配')
    w32(p + 1, N - 1)

    if EXPAND_4096:
        # ---- v2.11 追加改动 ----
        # 8) 二分起始 mid：0x480 -> N/2（仅影响迭代次数，非必需）
        p = va2off(0x4D8624)
        if p is None or d[p] != 0xB9:
            raise SystemExit('!! 二分起始 mid 指令未匹配')
        w32(p + 1, N // 2)

        # 4) 坐标表 4096 项 = 16KB > BSS 可用 10240B(2560 项) → 搬进 .atbl
        #    建表函数里 4 处 `[edi + 0x5d36eX]`（edi = 4i-4，基址 0x5D36E0）
        for va, old, new in ((0x4D88E9, 0x5D36E6, A_TBL_VA + 6),
                             (0x4D88EF, 0x5D36E7, A_TBL_VA + 7),
                             (0x4D88F5, 0x5D36E4, A_TBL_VA + 4),
                             (0x4D891A, 0x5D36E5, A_TBL_VA + 5)):
            p = va2off(va)
            if p is None:
                raise SystemExit('!! 坐标表基址指令 0x%08X 无映射' % va)
            blob = bytes(d[p:p + 12])
            i = blob.find(_s.pack('<I', old))
            if i < 0:
                raise SystemExit('!! 0x%08X 处未找到旧坐标表基址 0x%08X (bytes %s)'
                                 % (va, old, blob.hex(' ')))
            w32(p + i, new)

        # 2) 建表函数 x 的移位：`shr ecx,9` -> `shr ecx,11`
        #    ⇒ x = (i>>11)*16 + i%16 ≤ 31（仍是单字节），col=x&31 承载 i 的 bit11
        p = va2off(0x4D88D9)
        if p is None or bytes(d[p:p + 3]) != b'\xc1\xe9\x09':
            raise SystemExit('!! 建表 x 移位指令未匹配 (%s)'
                             % (bytes(d[p:p + 3]).hex(' ') if p else 'None'))
        d[p + 2] = 0x0B

        # 5) V 掩码 &31 -> &63（**只改 V**；U 保持原版 &31）
        p = va2off(0x4D8E36)
        if p is None or bytes(d[p:p + 5]) != b'\x25\x1f\x00\x00\x80':
            raise SystemExit('!! V 掩码指令 0x4D8E36 未匹配')
        d[p + 1] = 0x3F

        # 6) movsx -> movzx：x/y 是单字节，无符号取模才对（4 处）
        for va, exp in ((0x4D8DE6, b'\x0f\xbe\x41\x02'),
                        (0x4D8DF6, b'\x0f\xbe\x49\x03'),
                        (0x4D8E13, b'\x0f\xbe\x41\x02'),
                        (0x4D8E2A, b'\x0f\xbe\x41\x03')):
            p = va2off(va)
            if p is None or bytes(d[p:p + 4]) != exp:
                raise SystemExit('!! movsx 指令 0x%08X 未匹配' % va)
            d[p + 1] = 0xB6

        # 3) 页号：62 + (i/1024)  ->  62 + ((i>>10) & 1)
        #    原 15 字节：99 | 81 E2 FF 03 00 00 | 03 C2 | C1 F8 0A | 83 C0 3E
        #    新 15 字节：shr eax,0xa | and eax,1 | or eax,0x3e | 6x nop
        p = va2off(0x4D8E02)
        _old15 = bytes([0x99, 0x81, 0xE2, 0xFF, 0x03, 0x00, 0x00, 0x03, 0xC2,
                        0xC1, 0xF8, 0x0A, 0x83, 0xC0, 0x3E])
        if p is None or bytes(d[p:p + 15]) != _old15:
            raise SystemExit('!! 页号指令序列未匹配 (got %s)'
                             % (bytes(d[p:p + 15]).hex(' ') if p else 'None'))
        d[p:p + 15] = bytes([0xC1, 0xE8, 0x0A,        # shr eax, 0xa
                             0x83, 0xE0, 0x01,        # and eax, 1
                             0x83, 0xC8, 0x3E,        # or  eax, 0x3e
                             0x90, 0x90, 0x90, 0x90, 0x90, 0x90])
        print('  v2.14 取格公式补丁: shr x>>11 / V&63 / 页号62+bit10 / movzx / 循环 4N-4')

    _sort = A_TBL_VA_SORT if EXPAND_4096 else A_TBL_VA
    for va, old, new in ((0x4D8630, 0x5D4AE0, _sort),
                         (0x4D868C, 0x5D4AE0, _sort),
                         (0x4D8932, 0x5D4AE0, _sort),
                         (0x4D8920, 0x5D4AE4, _sort + 4)):
        p = va2off(va)
        if p is None:
            raise SystemExit('!! 排序表基址指令 0x%08X 无映射' % va)
        blob = bytes(d[p:p + 12])
        i = blob.find(_s.pack('<I', old))
        if i < 0:
            raise SystemExit('!! 0x%08X 处未找到旧基址 0x%08X (bytes %s)' % (va, old, blob.hex(' ')))
        w32(p + i, new)

    # --- 新增节 ---
    o = sec_tab + nsec * 40
    if o + 40 > len(d):
        raise SystemExit('!! 节表后无空间写新节项（节表紧贴节数据）')
    d[o:o + 8] = b'.atbl\0\0\0'
    _s.pack_into('<II', d, o + 8, new_size, new_va)      # VirtualSize, VirtualAddress
    _s.pack_into('<II', d, o + 16, new_size, new_raw)    # SizeOfRawData, PointerToRawData
    _s.pack_into('<II', d, o + 24, 0, 0)                 # reloc/linenum ptr
    _s.pack_into('<HH', d, o + 32, 0, 0)
    _s.pack_into('<I', d, o + 36, 0xC0000040)            # INITIALIZED|READ|WRITE
    w16(pe + 6, nsec + 1)
    w32(opt + 56, al(new_va + new_size, sec_align))       # SizeOfImage

    if len(d) < new_raw:
        d.extend(b'\x00' * (new_raw - len(d)))
    d.extend(b'\x00' * new_size)

    open(EXE, 'wb').write(bytes(d))
    print('  HMH2.exe 已打补丁: 新增节 .atbl @0x%08X (%d 字节), 字符表上限 1280 -> %d'
          % (new_va + imgbase, new_size, N))


# ---------------------------------------------------------------- v2.21 地名
# 村落/关卡记录表在游戏里存【两份】：
#   LANG_JA.blob34 (247768B) —— CSV blob_index=34，正常翻译
#   cscv.blob28    (247768B) —— 与 LANG[34] 仅 10 字节之差，但索引不同，
#                              "内容匹配同步"永远配不上 -> 补丁从不写它
#                              -> 选关界面地名显示日文原文
# 所以需要一条【显式按 cscv 索引写入】的通道。
CSCV_PLACE_BLOB = 28
CSCV_PLACE_OFF = 104         # 记录内 地名 槽偏移
# ★ v2.61 修正 CSCV_PLACE_LEN: 40 -> 32（越界事故，与 pos68 同类）。
# 实测（t48_place.py）：地名槽真实容量 = 32（184 条记录）/ 40（38 条）。
# 原写法固定 40，并用 `blob[off:off+40] = e + b'\x00'*(40-len(e))` 写入 ——
# 对容量只有 32 的那 184 条，多写的 8 个 0 会盖住 off136..off143，而 off136
# 是 int32 的【关卡/幕编号】（原值 1/2/3/4，49~64 条非零）；off140 另有一个
# int32。被清 0 后游戏选完章节进入时按该编号索引 -> 越界 -> 闪退（t50 实锤：
# off136 被清 64 条、off140 被清 49 条）。
# 修正：槽长取【保守最小值 32】，并保证只覆盖到 off135，不再触碰 off136。
CSCV_PLACE_LEN = 32          # 槽长（保守最小容量；真实为 32 或 40）
CSCV_PLACE_STRIDE = 1116     # 记录步长
CSCV_PLACE_MAP = os.path.join(WORK, 'place_map_raw.json')

# v2.21 补丁2：章节标题在 cscv 侧也有一份孪生表，同样配不上"内容匹配同步"：
#   cscv[782] (stride=580 n=85)  == LANG_JA[814]（章节标题主表）
#   cscv[890] (stride=292 n=252) == LANG_JA[931]（称号表 +36 章节标题）
# 不写它 -> 游戏读 cscv 那份 -> 章节标题显示日文原文（v2.20 遗留缺陷）。
CSCV_CHAP_JOBS = [
    # ★ v2.59 修正 slen: 68 -> 64。
    # 章节名槽位真实长度 = 64（pos4..pos67），译表 slot_bytes 也是 64。
    # 原写法 slen=68 会连 pos68..pos71 一起清 0，而 pos68 是 int32 的
    # 【世界/章节组编号】（0→1→2→3→4→6），全表 73/85 条非零。
    # 被清 0 后游戏选章节时按世界索引越界 -> 闪退。
    (782, 'res/LANG_JA.s2a', 814, 580, 85, 4, 64, '章节标题表'),
    (890, 'res/LANG_JA.s2a', 931, 292, 252, 36, 64, '称号表章节标题'),
    # v2.22：MESS 系统消息表的 cscv 孪生。cscv[368] n=102 vs LANG_JA[391] n=109，
    # 尺寸不同 -> 走不了"内容匹配同步"；前 10306 字节逐字节一致，之后才分叉。
    # 值槽在 +36（含 ff ff ff ff 前缀），长 128。只同步两边都有的前 102 条。
    (368, 'res/LANG_JA.s2a', 391, 168, 102, 36, 128, 'MESS系统消息表'),
    # v2.27：战斗/系统消息表 blob25 的 cscv 部分孪生（cscv[23] n=380 vs LANG_JA[25] n=382，
    # 前 380 条仅 5 条空格/圈号排版差异）。战斗消息与属性栏在部分界面读 cscv 这份
    # （先例：Dash 只翻 LANG 侧不生效，补孪生同步后才显示）。
    (23, 'res/LANG_JA.s2a', 25, 168, 380, 36, 128, '战斗消息表'),
]


def _cscv_blobs_read(cscv):
    """统一入口：总是从【当前】cscv 读，避免多个补丁互相覆盖。"""
    return s2a.Archive(cscv)


def apply_cscv_chap(do_write=True):
    """把 LANG 侧文本同步进 cscv 孪生表（章节标题 / 称号 / MESS）。返回写入槽数。"""
    cscv = os.path.join(BASE, 'res/cscv.s2a')
    a = _cscv_blobs_read(cscv)
    blobs = [bytearray(b) for b in a.blobs]
    total = 0
    # ★ v2.62：孪生同步也要走 Q16 保护（否则 rewrite_text 保住了原文，
    # 但这里又按 LANG 侧字节覆写一遍 —— 用户的"Q16 例外"会失效）。
    ct_whole, ct_recs, ct_vals = load_chap_title_guard()
    for cb, srel, sb, stride, n, soff, slen, desc in CSCV_CHAP_JOBS:
        sp = os.path.join(BASE, srel)
        if not os.path.exists(sp):
            print('  [孪生] 缺 %s，跳过' % srel); continue
        sar = s2a.Archive(sp)
        if sb >= len(sar.blobs) or cb >= len(blobs):
            print('  [孪生] %s blob 数不足，跳过' % desc); continue
        src = bytes(sar.blobs[sb])
        dst = blobs[cb]
        st_, n_ = struct.unpack_from('<II', bytes(dst), 4)
        if st_ != stride or n_ != n:
            print('  [孪生] !! %s 结构不符 (stride=%d n=%d != %d/%d)，跳过'
                  % (desc, st_, n_, stride, n))
            continue
        ok = skip = guard = protect = 0
        for i in range(n):
            o = 16 + i * stride + soff
            raw = src[o:o + slen].split(b'\x00')[0]
            _v = None
            if ct_vals and raw:
                try:
                    _v = strip_f8f3(raw.decode('cp932').strip())
                except Exception:
                    _v = None
            if chap_title_hit(ct_whole, ct_recs, cb, stride, soff, i, _v):
                protect += 1
                continue
            if not raw:
                skip += 1; continue
            # ★ v2.59 越界守卫：定长写入不得溢出 soff+slen。
            # 万一某条 JOBS 的 slen 写得偏大，把紧随其后的字段也按原型回填，
            # 保证"除目标字段外零附带变化"。（pos68 世界编号清零事故的兜底）
            _tail = bytes(dst[o + slen: o + slen + 4])
            dst[o:o + slen] = raw + b'\x00' * (slen - len(raw))
            if dst[o + slen: o + slen + 4] != _tail:
                dst[o + slen: o + slen + 4] = _tail
                guard += 1
            ok += 1
        print('  [孪生] cscv[%d] <- %s[%d] (%s): 写入 %d / 空槽 %d%s%s'
              % (cb, srel, sb, desc, ok, skip,
                 (' 保护跳过 %d' % protect) if protect else '',
                 (' 越界回填 %d' % guard) if guard else ''))
        total += ok
    if do_write and total:
        s2a.pack(cscv, a.entries, blobs)
        print('  [孪生] 已写入 cscv.s2a (%d 槽)' % total)
    return total


def apply_cscv_place(cmap, native, do_write=True):
    """把村落地名写进 cscv blob28 的 +104 槽。返回 (写入数, 跳过数)。"""
    if not os.path.exists(CSCV_PLACE_MAP):
        print('  [地名] 未找到 %s，跳过' % os.path.basename(CSCV_PLACE_MAP))
        return (0, 0)
    pm = json.load(open(CSCV_PLACE_MAP, encoding='utf-8'))
    cscv = os.path.join(BASE, 'res/cscv.s2a')
    # 总是从【当前】cscv 读：章节标题补丁可能刚写过它，从 .bak 读会把那些改动丢掉
    src = cscv
    a = s2a.Archive(src)
    blobs = [bytearray(b) for b in a.blobs]
    if CSCV_PLACE_BLOB >= len(blobs):
        print('  [地名] cscv blob 数不足，跳过'); return (0, 0)
    blob = blobs[CSCV_PLACE_BLOB]
    orig = bytes(blob)
    n_ok = n_skip = 0
    plan = []
    for o in pm:
        off, zh = o['off'], o['zh']
        e = encode_text(apply_repl(zh), cmap, native)
        rec_end = 16 + ((off - 16) // CSCV_PLACE_STRIDE + 1) * CSCV_PLACE_STRIDE
        # ★ v2.61 逐条实测真实容量：地名槽从 off 起，到其后第一个非 0 字节为止。
        # 原版此地名槽后面紧跟 off136 的 int32（关卡/幕编号），所以"到下一个非 0"
        # 就是槽的真实边界（32 或 40）。取 min(实测容量, CSCV_PLACE_LEN) 双保险。
        k = off
        while k < rec_end and orig[k] != 0:
            k += 1
        z = k
        while z < rec_end and orig[z] == 0:
            z += 1
        real_cap = z - off
        cap = min(CSCV_PLACE_LEN, real_cap, rec_end - off)
        if cap <= 0 or len(e) > cap:
            print('  [地名] !! rec%3d %r 编码 %d > 容量 %d，跳过'
                  % (o['rec'], zh, len(e), cap))
            n_skip += 1
            continue
        plan.append((o['rec'], off, zh, e, cap))
        n_ok += 1
    print('  [地名] cscv[%d]+%d: 可写 %d / 跳过 %d'
          % (CSCV_PLACE_BLOB, CSCV_PLACE_OFF, n_ok, n_skip))
    if not do_write or not plan:
        return (n_ok, n_skip)
    guard = 0
    for rec, off, zh, e, cap in plan:
        # ★ v2.61 越界守卫：写入只覆盖 off..off+cap-1，其后 4 字节必须原样保留
        # （pos68 / off136 两次同型事故的兜底）。
        _tail = bytes(blob[off + cap: off + cap + 4])
        blob[off:off + cap] = e + b'\x00' * (cap - len(e))
        if bytes(blob[off + cap: off + cap + 4]) != _tail:
            blob[off + cap: off + cap + 4] = _tail
            guard += 1
    s2a.pack(cscv, a.entries, blobs)
    print('  [地名] 已写入 cscv.s2a (%d 处%s)'
          % (n_ok, '，越界回填 %d' % guard if guard else ''))
    return (n_ok, n_skip)


# ---------------------------------------------------------------- v2.31 小咕之歌歌词
# 背景：歌词同时存在于两处 ——
#   ① 主线剧情 LANG b1025（两副本×3槽，text_v2.csv row 58913-58915 / 58939-58941）；
#   ② 女神房间歌词表 cscv blob355（日英双语，每组 4 条记录 =
#      [全角空格/注音行][日文行][英文行][空行]，文本槽锚点 0x1F4+0xA0*k，槽长 0x80）。
# 漏翻原因：歌词日文原文以子串出现在 cscv 独有 blob(355) 里 → 命中 collide 白名单
#   被整段保留原文（白名单本意是保护"游戏按内容比对"的键串）。歌词是纯显示文本，
#   不参与任何按名比对；主线两副本写同一译文，无比对风险 → 放行（SONG_OK）。
# 方案：① LANG 侧 = text_v2.csv 原有译文行 + SONG_OK 放行，由 rewrite_text 正常写入；
#   ② cscv[355] 侧 = apply_song_lyrics() 显式写 28 个英文行槽；日文行/注音行/
#   空行/♪ 间奏一律不动。英文行按【同记录日文行】译出（原英文与日文并非逐行对应，
#   且 Steam=english 时游戏读英文行）。
CSCV_SONG_BLOB = 355
CSCV_SONG_ANCHOR = 0x1F4      # 首条文本槽偏移
CSCV_SONG_STRIDE = 0xA0       # 记录步长（32B 头 + 128B 文本槽）
CSCV_SONG_SLOT = 0x80         # 文本槽定长

# collide 放行清单：LANG b1025 歌词行的日文原文（主线两副本同串）。
SONG_OK = frozenset(['おさなき日々の　あのせんりつは', '宝石よりも', 'まぶしくかがやいている'])

# (k, 同记录日文行-校验用, 中文译文)。英文行槽锚点 = 0x1F4 + 0xA0*k，日文行在 k-1。
# k=2/6 沿用 text_v2.csv 已有译文（在 LANG 侧拆两槽写入）；第 14 句保留前导全角
# 空格与"生命/の/結晶"间距（与注音行（いのち）（クリスタル）对位）。
SONG_EN_LINES = [
    (2,   'おさなき日々の　あのせんりつは', '唤起我年少时光的旋律'),
    (6,   '宝石よりもまぶしくかがやいている', '比宝石更闪耀夺目'),
    (10,  '記憶の底に眠りつづけていた', '一直沉睡在记忆深处的'),
    (14,  '熱い思いがむねの奥　ほとばしるの', '炽热的心意　正从胸中喷涌而出'),
    (18,  'わずらいを消し去る　ととのえられた音色たちよ', '驱散忧伤的　和谐悦耳的音色啊'),
    (22,  'この歌　たずさえて旅に出よう', '带上这首歌　踏上旅途吧'),
    (26,  'きっとだれにも　止められない', '一定谁也无法阻挡'),
    (30,  '静かにわき起こる　情熱は', '那静静涌起的　热情'),
    (34,  'どんな場所でも私は歌う', '无论身在何处　我都要歌唱'),
    (38,  'さあ今こそ船出の時よ', '来吧　现在正是启航之时'),
    (42,  '自分の運命におびえながらも', '纵然畏惧着自身的命运'),
    (46,  '激しく鳴らす調べは希望のあかし', '激越奏响的旋律　是希望的明证'),
    (50,  '心をこめた歌声だけが', '唯有倾注心意的歌声'),
    (54,  '\u3000\u3000\u3000ふるわせている\u3000生命\u3000の\u3000結晶\u3000\u3000\u3000',
          '\u3000\u3000\u3000正震颤着\u3000生命\u3000的\u3000结晶'),
    (58,  '迷わせる鏡に　負けない心を反射して', '把不输给迷镜的心　映照回去'),
    (62,  '恐れず選んだ　道だから', '因为这是无畏而选的道路'),
    (66,  'きっと進んで　ゆけるはずよ', '一定能够　继续前行'),
    (70,  '聖域突きぬけどこまでも', '穿透圣域　直至天涯海角'),
    (74,  'あらしの中　私は歌う', '在风暴之中　我放声歌唱'),
    (78,  'さあここから旅を始めよう', '来吧　从这里开始旅程'),
    (82,  '時をうれう　聖なる者　さずけし悲しみ受け入れ', '忧叹时光的　圣洁之人　接纳被授予的悲伤'),
    (86,  '高ぶる想い　むねにしずめ　いざ立ち向かえ', '将激荡的心绪　收于胸中　挺身迎战吧'),
    (104, 'よどみなき剣が　えがくきせきの美しさ', '清澈无滞之剑　描绘出的奇迹之美'),
    (108, 'ありったけの勇気を　ささげたい', '愿献上全部的勇气'),
    (112, '心つらぬく　強い光', '贯穿心灵的　强烈光芒'),
    (116, 'その先にきっと未来がある', '那前方一定有着未来'),
    (120, '過去と未来の　時をつないだ', '将过去与未来的　时光相连'),
    (124, '遥かな空間きらめいていた', '曾在遥远的天空　闪耀光芒'),
]


def apply_song_lyrics(cmap, native):
    """v2.31：把小咕之歌 28 个英文行槽写进 cscv blob355（原位定长写入，\\x00 填充）。
    同记录日文行做校验，不符则跳过该句（防结构变化写错位）。幂等：重复安装结果一致。
    返回写入槽数。"""
    src = os.path.join(BASE, 'res/cscv.s2a')
    if not os.path.exists(src):
        print('  [歌词] 缺 res/cscv.s2a，跳过')
        return 0
    a = s2a.Archive(src)
    if CSCV_SONG_BLOB >= len(a.blobs):
        print('  [歌词] cscv blob 数不足，跳过')
        return 0
    b = bytearray(a.blobs[CSCV_SONG_BLOB])
    n = 0
    for k, ja_ref, zh in SONG_EN_LINES:
        off = CSCV_SONG_ANCHOR + CSCV_SONG_STRIDE * k
        joff = CSCV_SONG_ANCHOR + CSCV_SONG_STRIDE * (k - 1)
        if joff + CSCV_SONG_SLOT > len(b) or off + CSCV_SONG_SLOT > len(b):
            print('  [歌词] !! k=%d 越界，跳过' % k)
            continue
        try:
            ja_cur = bytes(b[joff:joff + CSCV_SONG_SLOT]).split(b'\x00')[0].decode('cp932')
        except Exception:
            ja_cur = '<UNDEC>'
        if ja_cur != ja_ref:
            print('  [歌词] !! k=%d 日文行不符 %r，跳过' % (k, ja_cur))
            continue
        enc = encode_text(apply_repl(zh), cmap, native)
        if len(enc) > CSCV_SONG_SLOT - 2 or b'?' in enc:
            print('  [歌词] !! k=%d 编码异常 (len=%d)，跳过' % (k, len(enc)))
            continue
        b[off:off + CSCV_SONG_SLOT] = b'\x00' * CSCV_SONG_SLOT
        b[off:off + len(enc)] = enc
        n += 1
    if n:
        a.blobs[CSCV_SONG_BLOB] = b
        s2a.pack(src, a.entries, a.blobs)
    print('  [歌词] cscv[%d] 英文行: 写入 %d / 共 %d (日文行/注音/间奏不动)'
          % (CSCV_SONG_BLOB, n, len(SONG_EN_LINES)))
    return n


def do_apply(text=True, sync_cscv=True, keep_collide=True, skip_blobs=MECHANIC_BLOBS,
             consistent=False, menu_exempt=False, field_fix=True, ui_always=False,
             place=True, chap=True, song=True, slot_release=False, desc_release=False,
             exe_mode=None):
    """生产安装 = 同名不翻(keep_collide) + 机制表不翻(skip_blobs)。
    这是 2026-09-12 测试C/D 验证过的"技能全可用"组合。
    v2.2/2.3: menu_exempt=True 额外豁免 UI blob(186/354/358/440/516/715/763) 的
    148 个纯 UI 串（v2.2 blob358 131 串已实测安全 + v2.3 词表 17 串）。
    v2.21: place=True 额外把村落地名显式写进 cscv blob28（见 apply_cscv_place）。"""
    em = (exe_mode or EXE_MODE).lower()
    rows, ents, types, end, tb, slots, chosen, cmap, st = build_plan()
    print('== 安装简体字模补丁%s ==' % ('' if text else '（测试包A：仅字模，不翻文本）'))
    print('覆盖 %.2f%% (%d 字/%d 格, 保留原版字形 index 0-1247)'
          % (st['coverage'] * 100, st['chosen'], st['slots']))
    # 0) 确保全部有原版备份
    for rel in ALL_FILES:
        p = os.path.join(BASE, rel)
        if os.path.exists(p) and not os.path.exists(p + '.bak'):
            shutil.copy2(p, p + '.bak')
            print('  备份 %s -> .bak' % rel)
    # 1) exe：先还原原版；exe 模式离线改写，dll 模式保持原版（改由代理 DLL 运行时打补丁）
    if os.path.exists(EXE + '.bak'):
        shutil.copy2(EXE + '.bak', EXE)
        if em == 'exe':
            if UNLOCK_1280:
                patch_exe_unlock()
            else:
                print('  HMH2.exe 已还原原版')
        else:
            print('  HMH2.exe 已还原原版（DLL 模式：不改磁盘 exe）')
    # 2) 图集 + 字符表（cscv.s2a）
    rewrite_atlas_cscv(slots, chosen, cmap, st['kana_set'])
    # 3) 文本（LANG_JA / LANG_EN / cscv.s2a）
    if text:
        if consistent:
            keep_collide = False
            skip_blobs = ()
        rewrite_text(rows, cmap, st['native_set'], sync_cscv, keep_collide, skip_blobs,
                     consistent, menu_exempt, field_fix, ui_always, slot_release, desc_release)
        # v2.21：cscv 侧孪生表必须显式写（内容匹配同步配不上索引不同的孪生）
        if place:
            apply_cscv_place(cmap, st['native_set'])
        if chap:
            apply_cscv_chap()
        if song:
            apply_song_lyrics(cmap, st['native_set'])
    if em == 'dll':
        deploy_proxy()
    print('完成。还原命令: python tools/build.py revert')


def do_revert():
    for rel in ALL_FILES:
        p = os.path.join(BASE, rel)
        if os.path.exists(p + '.bak'):
            shutil.copy2(p + '.bak', p)
            print('  还原', rel)
        else:
            print('  无备份', rel)
    remove_proxy()


def do_test_a():
    """测试包A：还原后只装字模+字符表，不翻任何文本（测字模层是否影响技能）"""
    do_revert()
    do_apply(text=False)


def do_test_b():
    """测试包B：翻 LANG 文本但不同步 cscv 重复 blob（测 cscv 同步是否破坏技能）"""
    do_revert()
    do_apply(text=True, sync_cscv=False)


def do_test_c():
    """测试包C：脚本里也存在的字符串（名字类）保留日文不翻，其余照翻
    —— 验证"cscv 脚本按名字比对 LANG 字符串"假设"""
    do_revert()
    do_apply(text=True, sync_cscv=True, keep_collide=True)


def do_test_d():
    """测试包D = C + 技能/职业机制表(666/128/136/317)整表保留原文"""
    do_revert()
    do_apply(text=True, sync_cscv=True, keep_collide=True, skip_blobs=MECHANIC_BLOBS)


def do_apply_noplace():
    """v2.21 回退版：不写 cscv 孪生表（村落地名/章节标题回原文，其余照旧）"""
    do_apply(text=True, sync_cscv=True, keep_collide=True, skip_blobs=MECHANIC_BLOBS,
             menu_exempt=True, ui_always=True, place=False, chap=False)


def do_check():
    import hashlib
    for rel in ALL_FILES:
        p = os.path.join(BASE, rel)
        b = p + '.bak'
        if not os.path.exists(p):
            print('%-18s 缺失' % rel); continue
        hc = hashlib.sha256(open(p, 'rb').read()).hexdigest()[:12]
        hb = hashlib.sha256(open(b, 'rb').read()).hexdigest()[:12] if os.path.exists(b) else 'NONE'
        print('%-18s %s (cur=%s bak=%s)' % (rel, '原版' if hc == hb else '已修改', hc, hb))
    print('EXE_MODE = %s' % EXE_MODE)
    for name in PROXY_FILES:
        print('%-18s %s (dll mode)' % (name, 'present' if os.path.exists(os.path.join(BASE, name)) else 'absent'))


# ---- v2.47：把 DLC01 刷新并入生产装机 ----
# 背景（2026-09-15 定位）：载体码 cmap 是**按字频排序分配**的 ⇒ 任何改动 text_v2.csv
#   都会让部分字符换到邻近的载体码。DLC01 的译文是【另一个独立装机器】（_work/dlc_apply.py）
#   在 2026-09-13 用当时的 cmap 写进 DLC01/LANG_*.s2a 的；之后主装机更新了字库，
#   DLC01 却没重装 ⇒ 同一个码指向了别的字形，DLC 文本全乱
#   （实测 3704 个 DLC 译文槽里 2914 个对不上；`女神像ワープ`→`神女像传族`）。
# 修法：生产装机（apply_menu）完成字库写入后，**自动重跑 DLC01 编码**。
#   失败绝不影响主装机（try/except 吞掉），且 DLC 装机器自己会在超容量时中止。
def refresh_dlc01(verbose=True):
    """把 DLC01 译文按当前 cmap 重新编码。任何异常都只打印，不抛出。"""
    dlc_dir = os.path.join(BASE, 'DLC01')
    ja = os.path.join(dlc_dir, 'LANG_JA.s2a')
    bak = ja + '.bak_dlc01_20260913'
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dlc_apply.py')
    if not (os.path.exists(bak) and os.path.exists(script)):
        if verbose:
            print('  [DLC01] 跳过：未找到 DLC01 原件备份或装机器')
        return
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import dlc_apply as DA
        plan, over, _L = DA.build_plan()
        if over:
            print('  [DLC01] !! 有 %d 处超容量，已跳过（未写入）' % len(over))
            return
        # 直接写入（不复用 cmd_apply，避免它再 build_plan 一遍）
        import time as _t, shutil as _sh
        ts = _t.strftime('%Y%m%d_%H%M%S')
        for pth in (DA.D.P_JA, DA.D.P_EN):
            _sh.copy2(pth, pth + '.bak_dlcapplyv2_' + ts)
        for pth in (DA.D.P_JA, DA.D.P_EN):
            a = DA.D.s2a.Archive(pth)
            blobs = [bytearray(bytes(b)) for b in a.blobs]
            for p in plan:
                DA._write_slots(blobs[p['blob']], p)
            DA.D.s2a.pack(pth, a.entries, blobs)
        print('  [DLC01] 已按当前字库重编码 %d 槽 / %d blob（备份后缀 .bak_dlcapplyv2_%s）'
              % (len(plan), len({p['blob'] for p in plan}), ts))
    except Exception as e:
        print('  [DLC01] 重编码失败（不影响主装机）：%r' % e)


# ================= ★ v2.65：Q16「勇者城」键名槽位保护（t111/t112 实锤） =================
# 背景
# ----
# 游戏读的是【当前语言的 LANG 文件】（res/LANG_JA.s2a 或 res/LANG_EN.s2a）。
# 「按名字查表」的键字段在 LANG_JA / LANG_EN 里【各有一份】：
#     288/28  档案/剧本标识符（同表其余值是 '1' 'SE_EXPLO_S' 'Enable' 这类标识）
#     292/32  场景标题     424/124 档案地名     40/8 ■城名     224/112 城名カスタマイズ
# 装机把这些槽写成【中文载体码】后键值就变了 ⇒ 游戏按名字找不到城/关卡资源
# ⇒ **「勇者城」消失**（EN / JP 两侧都会坏，因为两份都被改）。
#
# ★ 键值必须等于【该语言自己的原版字符串】：
#     日文侧原版 = '勇者城'（cp932 97 45 8e d2 8f e9）
#     英文侧原版 = 'Hero Castle'（官方 EN 就是翻成英文，且游戏正常）
#   ⇒ 给英文侧写回日文同样是错的。这正是当年 t17 实验
#     「日语能出城、英语出不来」的真正原因。
#
# 做法
# ----
# 装机全部写完后，把 t17 wave1 的 253 个槽（全库含「勇者城」的名字/标识串）
# 逐槽写回【该文件自己的 .bak 原版字节】—— 等于官方在该槽的取值，最保守。
# 控制开关：_work/q16_key_guard.json  {"enabled": true|false}
# 一键：汉化-Q16键名保护-开关.bat / _work/t113_q16keyguard.py
Q16_KEY_TSV = os.path.join(WORK, 't17_q16_candidates.tsv')
Q16_KEY_CFG = os.path.join(WORK, 'q16_key_guard.json')
Q16_KEY_LIVE = {
    'LANG_JA': os.path.join(BASE, 'res', 'LANG_JA.s2a'),
    'LANG_EN': os.path.join(BASE, 'res', 'LANG_EN.s2a'),
    'cscv':    os.path.join(BASE, 'res', 'cscv.s2a'),
    'DLC01':   os.path.join(BASE, 'DLC01', 'LANG_JA.s2a'),
}
Q16_KEY_ORIG = {
    'LANG_JA': os.path.join(BASE, 'res', 'LANG_JA.s2a.bak'),
    'LANG_EN': os.path.join(BASE, 'res', 'LANG_EN.s2a.bak'),
    'cscv':    os.path.join(BASE, 'res', 'cscv.s2a.bak'),
    'DLC01':   os.path.join(BASE, 'DLC01', 'LANG_JA.s2a.bak_dlc01_20260913'),
}


def q16_key_enabled():
    """默认开启；_work/q16_key_guard.json 里 enabled=false 可关闭。"""
    if not os.path.exists(Q16_KEY_CFG):
        return True
    try:
        return bool(json.load(open(Q16_KEY_CFG, encoding='utf-8')).get('enabled', True))
    except Exception:
        return True


def _q16_run_at(b, off):
    """取 off 所在的 \\0 分隔 run（run 头 → run 尾）。"""
    if off >= len(b):
        return b''
    s0 = off
    while s0 > 0 and b[s0 - 1] != 0:
        s0 -= 1
    e0 = off
    while e0 < len(b) and b[e0] != 0:
        e0 += 1
    return b[s0:e0]


def q16_translate_slots():
    """实验 A 用：允许被翻译（不从 .bak 回写）的槽位集合 {(file, blob, off)}。

    背景：Q16 章节标题串（`Q16．勇者城、起動`）的 4 个副本同时也是"含勇者城的名字串"，
    所以它们在 `restore_q16_keys()` 的还原清单里。实验 A 要把 Q16 章节名也翻成中文，
    就必须让键名还原**跳过**这几槽。
    配置来自 `_work/q16_key_guard.json` 的 "translate_slots"：
        {"translate_slots": [["LANG_JA", 814, 8720], ...]}
    """
    if not os.path.exists(Q16_KEY_CFG):
        return set()
    try:
        cfg = json.load(open(Q16_KEY_CFG, encoding='utf-8'))
    except Exception:
        return set()
    out = set()
    for it in (cfg.get('translate_slots') or []):
        try:
            out.add((str(it[0]), int(it[1]), int(it[2])))
        except Exception:
            continue
    return out


def restore_q16_keys(verbose=True):
    """把 Q16 键名槽位写回【各文件自己的原版字节】。装机末尾调用，幂等。"""
    if not q16_key_enabled():
        if verbose:
            print('  [Q16键名] 保护已关闭（q16_key_guard.json enabled=false），跳过')
        return 0
    if not os.path.exists(Q16_KEY_TSV):
        if verbose:
            print('  [Q16键名] 跳过：未找到 %s' % os.path.basename(Q16_KEY_TSV))
        return 0
    try:
        rows = list(csv.DictReader(open(Q16_KEY_TSV, encoding='utf-8-sig'), delimiter='\t'))
    except Exception as e:
        if verbose:
            print('  [Q16键名] 跳过：清单读取失败 %r' % e)
        return 0

    excl = q16_translate_slots()          # ★ 实验 A：刻意翻译、不要回写的槽
    cands = []
    n_excl = 0
    for r in rows:
        try:
            if int(r['wave']) != 1:
                continue
            key = (str(r['file']), int(r['blob']), int(r['off']))
        except Exception:
            continue
        if key in excl:
            n_excl += 1
            continue
        cands.append(dict(file=key[0], bi=key[1], off=key[2],
                          stride=int(r['stride']), rec=int(r['rec']), pos=int(r['pos'])))
    if verbose and n_excl:
        print('  [Q16键名] 实验A：%d 槽刻意翻译（不回写原版）' % n_excl)

    per = collections.defaultdict(list)
    n_same = n_doubt = 0
    for c in cands:
        name = c['file']
        if name not in Q16_KEY_LIVE or not os.path.exists(Q16_KEY_ORIG[name]):
            n_doubt += 1
            continue
        try:
            lb = bytes(s2a.Archive(Q16_KEY_LIVE[name]).blobs[c['bi']])
            ob = bytes(s2a.Archive(Q16_KEY_ORIG[name]).blobs[c['bi']])
        except Exception:
            n_doubt += 1
            continue
        live_run = _q16_run_at(lb, c['off'])
        own_run = _q16_run_at(ob, c['off'])
        if not own_run:
            n_doubt += 1
            continue
        if live_run == own_run:
            n_same += 1
            continue
        extent = max(len(live_run), len(own_run))
        nxt = lb.find(b'\x00', c['off'])
        if nxt < 0:
            nxt = len(lb)
        else:
            while nxt < len(lb) and lb[nxt] == 0:
                nxt += 1
        if c['off'] + extent > nxt:
            n_doubt += 1
            continue
        if c['stride'] > 0 and c['rec'] >= 0:
            if c['off'] + extent > 16 + (c['rec'] + 1) * c['stride']:
                n_doubt += 1
                continue
        per[name].append((c['bi'], c['off'], own_run, extent))

    done = 0
    for name, items in per.items():
        path = Q16_KEY_LIVE[name]
        arc = s2a.Archive(path)
        blobs = [bytearray(bytes(b)) for b in arc.blobs]
        for bi, off, own, ext in items:
            blobs[bi][off:off + ext] = own + b'\x00' * (ext - len(own))
        s2a.pack(path, arc.entries, blobs)
        done += len(items)
        if verbose:
            print('  [Q16键名] %-8s 写回该文件自己的原版字节 %d 处' % (name, len(items)))
    if verbose:
        print('  [Q16键名] 共 %d 处（已原样 %d，存疑 %d）— 城/关卡按键名查找恢复'
              % (done, n_same, n_doubt))
    return done


def do_apply_menu(exe_mode=None):
    """生产装机 = apply_menu + 自动刷新 DLC01。v2.51：+ 说明文槽位级放行。
    v2.65：末尾追加 Q16 键名槽位保护（否则「勇者城」会再次消失）。
    默认 exe_mode=dll（运行时代理 DLL，不改磁盘 exe）。"""
    stats = do_apply(text=True, sync_cscv=True, keep_collide=True,
                     skip_blobs=MECHANIC_BLOBS, menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True, exe_mode=exe_mode)
    print('== 同步 DLC01（防止字库变动后 DLC 文本错乱）==')
    refresh_dlc01()
    print('== Q16 键名槽位保护（「勇者城」城/关卡按键名查找）==')
    restore_q16_keys()
    return stats


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'plan'
    {'plan': do_plan, 'apply': do_apply, 'revert': do_revert, 'check': do_check,
     'apply_font': lambda: do_apply(text=False),
     'apply_nosync': lambda: do_apply(text=True, sync_cscv=False),
     'apply_nocollide': lambda: do_apply(text=True, sync_cscv=True, keep_collide=True),
     'apply_consistent': lambda: do_apply(text=True, sync_cscv=True, consistent=True),
     'apply_nomech': lambda: do_apply(text=True, sync_cscv=True, keep_collide=True,
                                      skip_blobs=MECHANIC_BLOBS),
     # v2.16（现默认装机版）：菜单豁免 + 跨 blob 纯 UI 标签词表（按键标签/章节标题/阵形）
     # v2.47：改为 do_apply_menu —— 末尾自动同步 DLC01
     'apply_menu': do_apply_menu,
     'apply_menu_exe': lambda: do_apply_menu(exe_mode='exe'),
     'apply_mainonly': lambda: do_apply(text=True, sync_cscv=True, keep_collide=True,
                                        skip_blobs=MECHANIC_BLOBS, menu_exempt=True,
                                        ui_always=True),
     'dlc_only': refresh_dlc01,
     'apply_menu2': lambda: do_apply(text=True, sync_cscv=True, keep_collide=True,
                                     skip_blobs=MECHANIC_BLOBS, menu_exempt=True,
                                     ui_always=True),
     # v2.21 回退：地名保留原文
    'apply_noplace': do_apply_noplace,
    # v2.15 保守版：UI 标签保持原文（菜单里 Select/Delete/章节名仍是英文）
     'apply_menu_safe': lambda: do_apply(text=True, sync_cscv=True, keep_collide=True,
                                         skip_blobs=MECHANIC_BLOBS, menu_exempt=True,
                                         ui_always=False),
     # v2.4 = v2.3 + 多行整字段写入（保留 \n）；apply_menu_noml = 退回 v2.3 行为
     'apply_menu_noml': lambda: do_apply(text=True, sync_cscv=True, keep_collide=True,
                                         skip_blobs=MECHANIC_BLOBS, menu_exempt=True,
                                         field_fix=False),
     'test_a': do_test_a, 'test_b': do_test_b, 'test_c': do_test_c, 'test_d': do_test_d}.get(cmd, do_plan)()
