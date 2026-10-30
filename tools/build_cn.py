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
  python build_cn.py plan            # 统计覆盖率，不改文件
  python build_cn.py apply           # 构建并安装（自动 .bak 备份）
  python build_cn.py revert          # 还原
  python build_cn.py package         # 完整补丁打包（默认·隔离）：只出 dist，不动游戏目录
  python build_cn.py package_install # 完整补丁打包（就地装机版）：装机 + 出 dist
建议经由 tools/build.py 调用（它提供 --game-dir，避免误打目标目录）:
  python tools/build.py --game-dir "<游戏目录>" package
游戏目录的取值优先级（不硬编码任何 Steam 路径）:
  build.py --game-dir  >  HMH2_GAME_DIR 环境变量  >  config.local.json 的 game_dir
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
import dlc_lib
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

# ==== 2026-10-22：同字复用原版汉字槽位（方案 B）====
# 原版 256-1023 是日文汉字区。若简体译文用到**同一个 Unicode 字**（如 勇/者/的/我），
# 其 CP932 码与原版表项完全相同，因此可以直接沿用原版码：
#   · 字符表条目**不改**（改条目会破坏原版日文/旧存档/按键名查表）；
#   · 文本直接写原版 CP932 字节，游戏查表命中原来的 index；
#   · 再把该 index 的图集格用文泉驿简体字形重画，保证中文观感统一（方案 B）。
# 效果：这些字不再占用 1248+ 的新格，直接释放容量。
REUSE_ORIGINAL_CJK = True
REUSE_CJK_RANGE = (256, 1023)

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
#   * 不再回收假名格(162)/STAFF区(1024-1119) —— 全部保留原版。
#   * 简体字**新分配**用 **index 1248..4095**（其中 1408='ED' 标记保留）
#     = 1248-1279(32) + 1280-2047(768) + 2048-3071(1024) + 3072-4095(1024) = **2847 格**
#   * 2026-10-22（方案 B）：256-1023 中与译文**同码位**的 523 字直接复用原版槽位，
#     原格重画为文泉驿简体字形，不再占新格（Z15 实装：2296 新格 + 523 复用）。
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
DLC_EXTRA_CHARS = '鸭苹橘掀糯鲑蚝朗乳鼬樱坂潟讼哲'

# ---- 关闭 REPL 时 DLC 文本重新出现的字（2026-10-22）----
# char_freq 不扫 DLC；关掉 REPL 后 DLC 的 洞窟→洞穴 失效，会重新用到「窟」。
NO_REPL_EXTRA_CHARS = '窟'


# 技能/职业机制表：游戏会按内容读取，翻译会导致技能无动画无效果（2026-09-12 测试D 实锤）
#   666 = 技能升级链表（技能名→下一级→说明→思いつき率）
#   128/136 = 职业表（职业名/能力值/说明）
#   317 = 连携技表
MECHANIC_BLOBS = (666, 128, 136, 317)

# ★★ v2.67（E1b）：技能表 b666 的**内部键名列**（记录内 pos288~375，含 pos292）必须保持原版。
#    docs/PITFALLS.md §6「G5 事故」/ §8「测试 E 全量一致翻译失败」：脚本执行时按【键名】查技能，
#    键名一旦被换成载体码中文（含"同一原文全副本统一译成中文"的 consistent 路线）⇒ 查不到 ⇒
#    主角技能"只有名字、无动画无效果"。这正是 E1 首/二轮实机失败的根因。
#    记录基址 = 16 + rec*376（与 tools/t34_health.py 的 v2.67 守卫同一约定）。
SKILL_KEY_BLOB = 666
SKILL_STRIDE = 376
SKILL_KEY_LO, SKILL_KEY_HI = 288, 376


def in_skill_key_col(bi, off):
    """该 (blob, 槽偏移) 是否落在技能表 b666 的内部键名列内（判据同 t34_health v2.67 守卫）。"""
    if bi != SKILL_KEY_BLOB:
        return False
    r = (off - 16) % SKILL_STRIDE
    return SKILL_KEY_LO <= r < SKILL_KEY_HI


# Z17：逐槽放行的纯显示文本（collide 假命中）。
# 只放行明确确认是菜单标签/对话/选项的槽位；同名副本与机制表不受影响。
DISPLAY_RELEASE_OFFS = {
    # b280 Change Clothes 菜单（The Usual / Robe / Swimsuit / Dress / Music Player）
    (280, 48), (280, 456), (280, 864), (280, 1068), (280, 1476),
    # b534 Music Player
    (534, 240), (534, 280),
    # b642 合成界面 Specialty
    (642, 16),
    # 合成界面 Class Change / Craft Weapons
    (265, 3500), (265, 3924), (265, 4348),
    (353, 3500), (353, 3924),
    (370, 3924), (370, 4348),
    (469, 4348), (469, 4772),
    (688, 3076), (688, 3500),
    # 战斗菜单 Bring Allies Back to Life
    (624, 2396), (624, 7060),
    (718, 2396), (718, 7060),
    # 对话选项（无「」/括号）
    (757, 41056), (757, 149680),
    (298, 88652), (298, 88716), (298, 90696), (298, 90760),
    (365, 33236), (365, 57472),
    (366, 131868),
    # b291 地图编辑器 UI 标签
    (291, 20320), (291, 20900), (291, 21480), (291, 22060), (291, 22640),
    (291, 23220), (291, 23800), (291, 24380), (291, 24960), (291, 27860),
    # b291 其余说明/半句（按整条记录重译）
    (291, 600), (291, 1180), (291, 1420), (291, 1468), (291, 1760),
    (291, 2000), (291, 2048), (291, 2340), (291, 2920), (291, 3500),
    (291, 3596), (291, 4080), (291, 4660), (291, 4804), (291, 7608),
    (291, 11088), (291, 12828), (291, 13408), (291, 13988), (291, 14568),
    (291, 25540), (291, 25636), (291, 25684), (291, 26120), (291, 26700),
    # b804 萨莎日记 / 魔王勋章 / 魔人迷宫标题 / 检查选项
    (804, 297140), (804, 297432), (804, 304732), (804, 305024),
    (804, 307944), (804, 308236), (804, 317872), (804, 318164),
    (804, 321084), (804, 321376), (804, 328676), (804, 328968),
    (804, 331888), (804, 332180), (804, 339772), (804, 340064),
    (804, 342984), (804, 343276), (804, 353496),
    (804, 419652), (804, 420236),
    (804, 639364), (804, 639428),
    # b153 战斗行动提示（普通对话）
    (153, 7184), (153, 7248), (153, 10980), (153, 11044), (153, 12440),
    (153, 12504), (153, 13900), (153, 13964), (153, 15360), (153, 15424),
    (153, 16884), (153, 18344), (153, 19804), (153, 21264), (153, 23308),
    # 其他普通对话/事件提示
    (668, 376564), (756, 28268), (109, 828), (867, 16),
    # PITFALLS §9 同类：菜单项名与分组标签必须同串，补齐遗漏副本
    (280, 1444),          # Music Player 分组标签（b534/240/280 与 b280/1476 已译）
    (410, 956),           # Craft Weapons 分组标签（其余 5 份已译）
    (280, 3484), (280, 3688), (280, 3892), (280, 4096),  # Gallery 分组标签
    (186, 94656),         # Normal Mode（b354 对应副本已译）
    (763, 9872),          # Best Time（b358 对应副本已译）
}

# b804 魔人迷宫标题：30 个记录，步长 584
DISPLAY_RELEASE_OFFS.update((804, o) for o in range(467832, 484769, 584))


# Z17：已知字体查表问题（描述渲染器把“神”0x905F 解析成“挑”0x9091）。
# 这三份“便携女神像”描述暂不上屏，保留原文；译文仍留在 CSV / protected JSON 供以后修复。
PROTECTED_DISPLAY_OFFS = {
    (147, 1400), (357, 1400), (736, 1400),
}


def display_release_hit(bi, off, ja_cmp):
    """Z17：纯显示文本的 collide 假命中放行（按槽位或括号台词）。"""
    if (bi, off) in DISPLAY_RELEASE_OFFS:
        return True
    # 括号内心独白/选项：与「」台词同理，不是机制名；Q16 勇者城键仍保护。
    if ja_cmp.startswith('（') and '勇者城' not in ja_cmp:
        return True
    return False


# 实验用按列黑名单（默认 None = 不启用）。由二分实验的 apply 函数临时设置/复原。
_SLOT_BLOCK = None
# 实验用「collide 额外放行」回调（默认 None = 不启用）。
# 签名 (bi, off, ja_cmp) -> True；仅在 keep_collide=True 且命中 collide 时调用，
# 返回 True 表示该槽照常翻译（用于 Z10b/Z11：只放行指定名字/复合键）。
_EXTRA_RELEASE = None
# 实验用「额外译表行」（默认 None）。由 Z11 等配方注入，参与字库统计与文本写入，
# 但不落盘到 text_v2.csv（避免污染译表/误登记）。
_EXTRA_ROWS = None
# Z14 用：明确允许翻译的称号名槽 {(blob, offset)}，用于绕过 chap_title_guard 的整表保护。
# 只放行 b931 pos0 的称号名本体；pos36（章节标题副本）与 Q16 rec_rules 仍受保护。
_TITLE_RELEASE = None
# 最近一次 build_plan() 的 (cmap, statistics)。DLC01 重编码必须复用主装机的
# 同一套 cmap，否则 DLC 文本会按另一套载体码写入而整段乱码（2026-10-22 实机确认）。
_LAST_BUILD_PLAN = None
# Z11–Z14 的“代码内额外译表行”的人工校对覆盖：{"<blob>:<offset>": "中文"}。
# 导出到 translator-view/50_extra.json，导入时写回本文件；构建时优先使用这里的译文。
EXTRA_REVIEW_FILE = os.path.join(WORK, 'extra_review.json')


def _apply_extra_overrides(rows):
    if not os.path.exists(EXTRA_REVIEW_FILE):
        return rows
    try:
        import json as _json
        m = _json.load(open(EXTRA_REVIEW_FILE, encoding='utf-8'))
    except Exception:
        return rows
    for r in rows:
        k = '%s:%s' % (r.get('blob_index'), r.get('offset'))
        z = (m.get(k) or '').strip()
        if z:
            r['zh_new'] = z
    return rows
EQUIP_BLOBS = (147, 357, 736, 998)
EQUIP_STRIDE = 268

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


REPL_RAW = {}
HL_RAW = {}
_rm = os.path.join(WORK, 'replace_map.py')
if os.path.exists(_rm):
    _ns = {}
    exec(compile(open(_rm, encoding='utf-8').read(), _rm, 'exec'), _ns)
    REPL_RAW = _ns.get('REPL', {})

# ---- 高亮标记 <...> 补译表（2026-09-12 补全未翻译文本）----
_hlm = os.path.join(WORK, 'hl_map.py')
if os.path.exists(_hlm):
    _ns2 = {}
    exec(compile(open(_hlm, encoding='utf-8').read(), _hlm, 'exec'), _ns2)
    HL_RAW = _ns2.get('HL', {})

# ---- 词典开关（2026-10-22）----
# HMH2_APPLY_REPL=0 / --no-repl：只保留 HL（高亮补译），不套用 REPL（术语/近义替换）。
# 默认开启，保持现有生产行为。
APPLY_REPL = os.environ.get('HMH2_APPLY_REPL', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')


def _refresh_repl():
    """重建 apply_repl 用的合并表：REPL（可关）+ HL（始终保留）。"""
    global REPL, _repl_items
    table = dict(REPL_RAW) if APPLY_REPL else {}
    table.update(HL_RAW)
    REPL = table
    _repl_items = sorted(table.items(), key=lambda kv: -len(kv[0]))


def set_apply_repl(enabled):
    """运行时切换词典开关（同进程内生效）。"""
    global APPLY_REPL
    APPLY_REPL = bool(enabled)
    _refresh_repl()


def reload_replace_maps():
    """重新读取 locales/<locale>/replace_map.py 与 hl_map.py。

    校对导入把 dict/替换词典.json 写回这两个 .py 后必须调用，
    否则本进程仍使用启动时加载的旧表。
    """
    global REPL_RAW, HL_RAW
    REPL_RAW = {}
    HL_RAW = {}
    if os.path.exists(_rm):
        _ns = {}
        exec(compile(open(_rm, encoding='utf-8').read(), _rm, 'exec'), _ns)
        REPL_RAW = _ns.get('REPL', {})
    if os.path.exists(_hlm):
        _ns2 = {}
        exec(compile(open(_hlm, encoding='utf-8').read(), _hlm, 'exec'), _ns2)
        HL_RAW = _ns2.get('HL', {})
    _refresh_repl()


_refresh_repl()


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
    if _EXTRA_ROWS:
        # 额外行放在最前：同名槽位去重时以额外行为准（CSV 里可能是空译文占位行）。
        rows = list(_EXTRA_ROWS) + rows
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
    # ⭐ v2.14：非汉字（标点/符号/假名/全角字母数字）视为"原版已有、免占格"，直接写原版码。
    # ⭐ 2026-10-22 方案 B：日文汉字区 256-1023 中与简体译文**同码位**的字也免占格，
    #   沿用原版表项/码值；区别只是图集格会被重画为简体字形（见 rewrite_atlas_cscv）。
    overwrite_set = set(slots)
    native_chars = {ents[i] for i in range(len(ents))
                    if i not in overwrite_set and ents[i] and len(ents[i]) == 1
                    and ord(ents[i]) >= 0x80 and not is_cjk(ents[i])}

    # 原版汉字区：字 -> 全部索引（少数汉字有重复表项，如 名/矢/切/連/御）
    reuse_map = {}
    if REUSE_ORIGINAL_CJK:
        _lo, _hi = REUSE_CJK_RANGE
        for i in range(_lo, _hi + 1):
            c = ents[i]
            if c and len(c) == 1 and is_cjk(c):
                reuse_map.setdefault(c, []).append(i)
        native_chars |= set(reuse_map)

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
    if not APPLY_REPL:
        _nr_add = [c for c in NO_REPL_EXTRA_CHARS
                   if c not in candidates and c not in native_chars]
        candidates = candidates + _nr_add
    if len(candidates) > n_slot:
        print('  !! 候选字 %d > 可用格 %d —— 尾部 %d 字将被挤出（DLC 追加字在末尾，先被挤）'
              % (len(candidates), n_slot, len(candidates) - n_slot))
    chosen = candidates[:n_slot]

    # 只对**译文实际用到**的复用字建 cmap（并记录要重画的索引）。
    # 未用到的日文汉字槽位保持原样，避免无谓改动。
    reuse_used = {c: v for c, v in reuse_map.items()
                  if c in cnt or c in DLC_EXTRA_CHARS}
    cmap = {}
    for c, ids in reuse_used.items():
        cmap[c] = ents[ids[0]].encode('cp932')
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
                      reuse_map=reuse_used,
                      reuse_n=len(reuse_used),
                      reuse_slots=sum(len(v) for v in reuse_used.values()),
                      coverage=covered / tot if tot else 0)
    global _LAST_BUILD_PLAN
    _LAST_BUILD_PLAN = (cmap, statistics)
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
    print('同字复用原版格      : %d 字 (重画 %d 格, 含重复表项)'
          % (st['reuse_n'], st['reuse_slots']))
    print('实际新占图集格      : %d / %d, 余量 %d'
          % (st['chosen'], st['slots'], st['slots'] - st['chosen']))
    print('含复用可显示汉字    : %d  (新格 %d + 复用 %d)'
          % (st['chosen'] + st['reuse_n'], st['chosen'], st['reuse_n']))
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


def build_canonical(rows, lang_a, collide, cmap, native, relax_fields=False):
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
        # ★ mirror（照抄官方 EN）：该约束只为"cscv 文本层会被同步写入"服务。
        #   官方 EN 完全不写 cscv（analyze_en_ja §3：抽样 1500 仅 5 偶然命中），
        #   本变体同样 sync_cscv=False ⇒ 约束无意义，relax_fields=True 时跳过。
        if not relax_fields:
            fl = fields.get(ja)
            if not fl or any(len(enc) > sl for sl in fl):
                canonical[ja] = None
                continue
        canonical[ja] = enc
    return canonical, fields


def propagate_canonical_dups(edits, canonical, lang_a, en_a, registered, skip_blobs=(), mirror=False):
    """一致译名收尾：把 canonical 里【已定译】的原文串按"内容"传播到**未登记**的重复副本槽。

    背景（2026-10-18 E1 实机诊断）：武器表 b147/b357/b736 的"该武器附带的技能名"列既不在
    text_v2.csv（无对应行），也不是任何清单里的槽位，于是技能表 b666 被翻成中文、这些引用列
    却仍是 'Drain Axe' ⇒ 按名链断，技能"只有名字没有效果/动画"、连名字都弹不出来。
    本函数按内容把所有副本统一到同一译文（= TRANSLATING.md §10「所有副本一起翻」铁律）。

    安全闸（只改 NUL 结尾的完整字段，绝不越界、绝不触碰 FF FF FF FF 前缀）：
      · JA/EN 两侧 run 起点必须一致，且 run 起点→名字起点之间的字节两侧完全相同；
      · 容量 = EN 侧【名字起点 → 下一个非 NUL 字节】的整段（即允许吃掉紧随其后的 NUL 填充，
        但绝不吃到下一段真实内容），并强制保留 1 字节 NUL 终止符。

    v2.66b（2026-10-18 残留个案）：早先容量只取 EN 当前值长（如 EN='Iai' 仅 3 字节），
    导致 4 字节译文被拒 —— 实测该槽后有 64 字节纯 NUL 填充，真实容量远大于 3。
    改为 padding-aware 容量后不再丢副本。该区间按定义全为 NUL，清零/写入都不会伤到相邻字段。
    """
    kanon = {}
    for ja, enc in canonical.items():
        if enc:
            try:
                kanon[ja.encode('cp932')] = enc
            except Exception:
                pass
    if not kanon:
        return 0
    n = 0
    relax_n = 0        # 用到 NUL 填充区的（旧闸会拒的）
    relax_max = 0
    for bi, jblob in enumerate(lang_a.blobs):
        if bi in skip_blobs or bi >= len(en_a.blobs):
            continue
        jb = bytes(jblob)
        eb = bytes(en_a.blobs[bi])
        if not eb:
            continue
        pos, L = 0, len(jb)
        while pos < L:
            e = jb.find(b'\x00', pos)
            if e < 0:
                e = L
            f = pos
            while f < e and jb[f] == 0xFF:      # 跳过 ff ff ff ff 前缀，绝不写入前缀
                f += 1
            if f < e and (bi, pos) not in registered and (bi, f) not in registered \
                    and (mirror or not in_skill_key_col(bi, f)):
                enc = kanon.get(jb[f:e])
                if enc is not None and len(enc) >= 2:
                    es = eb.rfind(b'\x00', 0, f) + 1
                    if es == pos and eb[pos:f] == jb[pos:f]:
                        ee = eb.find(b'\x00', f)
                        if ee < 0:
                            ee = len(eb)
                        # 容量 = 名字起点 → 下一个非 NUL 字节（含 NUL 填充区）；再留 1 字节做终止符
                        nx = ee
                        while nx < len(eb) and eb[nx] == 0x00:
                            nx += 1
                        cap = nx - f
                        sb2 = max(ee - f, len(enc) + 1)
                        if 0 < cap and sb2 <= cap:
                            if sb2 > ee - f:
                                relax_n += 1
                                relax_max = max(relax_max, sb2)
                            edits[bi].append((f, sb2, 0, enc))
                            n += 1
            pos = e + 1
    if relax_n:
        print('    （其中 %d 处借用了 NUL 填充区，最大写入槽 %d 字节）' % (relax_n, relax_max))
    return n


def rewrite_text(rows, cmap, native, sync_cscv=True, keep_collide=False, skip_blobs=(), consistent=False,
                 menu_exempt=False, field_fix=True, ui_always=False, slot_release=False,
                 desc_release=False, dry_run=False, classify=None, lang_files=None,
                 propagate_dups=False, mirror=False, title_guard=True):
    """把译文写进 LANG_JA / LANG_EN / cscv(与 LANG 重复的部分)。

    cscv.s2a 里有大量与 LANG 逐字节相同的 blob（实测 681 个），游戏可能从它读文本，
    所以按【内容相同 -> 同一套 offset 编辑】的方式一并改写，保证两边一致。

    field_fix=True 时，多行字段按【整字段】写入（保留 \\n），修复"只显示第一行"。

    lang_files（可选，list）：限制写入哪些 LANG 文件，默认 TEXT_FILES（JA+EN）。
    E1 隔离实验只传 ['res/LANG_EN.s2a']，此时 LANG_JA 侧一个字节都不写。

    dry_run=True（只判定、不落盘）：只跑第 1 步"计算编辑清单"，写完 classify 后直接返回，
    不触碰任何游戏文件。供导出器复用生产装机口径、判定"哪些槽位注释被保留原文"。
    classify（可选，dict）：dry_run 时填充 {(blob_index, offset): 保留原因}，
    原因取值 'collide'（疑似名字键）/ 'mech'（机制表整表）/ 'chaptitle'（章节/称号守卫）。
    非 dry_run 时该参数无副作用（仍会填，便于调用方观察）。
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
        canonical, fields = build_canonical(rows, lang_a, collide, cmap, native,
                                            relax_fields=mirror)
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
        # ★ 实验用「按列黑名单」：由调用方设置 SLOT_BLOCK(bi, off) -> True 即跳过该槽。
        #   仅用于二分实验（Z6/Z7），默认 None 不影响任何现有配方。
        if _SLOT_BLOCK is not None and _SLOT_BLOCK(bi, off):
            stats['slotblock'] += 1
            if classify is not None:
                classify[(bi, off)] = 'slotblock'
            continue
        # ★★ v2.67（E1b）：技能表 b666 的内部键名列 pos288~375 一律保留原文（不翻）
        #    ★ mirror（E2，照抄官方 EN）：官方把该键名列也一并英文化（86/86，analyze_en_ja §4）
        #    且技能可用 ⇒ mirror=True 时不设此护栏。
        if not mirror and in_skill_key_col(bi, off):
            stats['skillkey'] += 1
            if classify is not None:
                classify[(bi, off)] = 'skillkey'
            continue
        # v2.58 章节名/称号保护：命中 (blob, stride, pos) 的槽位一律保留原文
        # v2.62 扩展：支持"按记录号"保护（Q16 单条例外），见 chap_title_hit()
        # v2.63 扩展：支持"按值"保护 —— 先解出该槽日文原文再判定（value_rules）
        # ★ 2026-10-21 修复：mirror 只应放行 b666 键名列（in_skill_key_col），
        #   不能连带关闭称号/Q16 保护（Z10b/Z11/Z12 曾因此把称号翻中文 -> 称号无法获得）。
        if (title_guard or not mirror) and (ct_guard or ct_recs or _CT_VALUE_CACHE):
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
                if _TITLE_RELEASE is not None and (bi, off) in _TITLE_RELEASE:
                    pass  # Z14：显式允许的称号名本体（已验证同语言副本一致）
                else:
                    stats['chaptitle'] += 1
                    if classify is not None:
                        classify[(bi, off)] = 'chaptitle'
                    continue
        # Z17：已知查表问题的显示槽强制保留原文（不上屏翻译）。
        if (bi, off) in PROTECTED_DISPLAY_OFFS:
            stats['protected_display'] += 1
            if classify is not None:
                classify[(bi, off)] = 'protected-display'
            continue
        # v2.51 说明文放行：命中 (blob, stride, pos) 规则的说明字段，即使本表在 skip_blobs 里也照常翻译
        desc_ok = bool(desc_rel) and desc_release_hit(desc_rel, lang_a, bi, off)
        if bi in skip_blobs and not desc_ok:
            stats['skipblob'] += 1
            if classify is not None:
                classify[(bi, off)] = 'mech'
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
                elif _EXTRA_RELEASE is not None and _EXTRA_RELEASE(bi, off, ja_cmp):
                    # 实验用（Z10b）：只额外放行机制名/装备名与章节 loadout，
                    # 其余 collide 字符串仍按 stable 配方保留原文。
                    stats['extrarel'] += 1
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
                elif display_release_hit(bi, off, ja_cmp):
                    # Z17：括号内心独白、选项与逐槽确认的 UI 标签（collide 假命中）。
                    stats['displayrel'] += 1
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
                    if classify is not None:
                        classify[(bi, off)] = 'collide'
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
    # ★★ v2.66(E1)：一致译名收尾 —— 把已定译原文串按内容传播到**未登记**的重复副本槽
    #    （武器表"该武器附带技能名"列等；否则 b666 中文 / b147 英文 ⇒ 按名链断）。
    if propagate_dups and consistent and canonical and classify is None:
        n_prop = propagate_canonical_dups(edits, canonical, lang_a, en_a, seen, skip_blobs,
                                          mirror=mirror)
        stats['prop'] = n_prop
        if n_prop:
            print('  ★未登记副本按内容统一译文: %d 处' % n_prop)
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

    # dry_run：只判定不落盘 —— 编辑清单已算好、classify 已填，直接返回，不触碰任何游戏文件
    if dry_run:
        return stats

    # 内容 -> LANG blob 索引
    lang_hash = {}
    for i, b in enumerate(lang_a.blobs):
        if edits.get(i):
            lang_hash.setdefault(hashlib.md5(bytes(b)).hexdigest(), i)

    # ---- 2) LANG_JA / LANG_EN（lang_files 可限制只写其中一侧，E1 只写 EN）----
    for rel in (lang_files or TEXT_FILES):
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

    # ---- 同字复用（方案 B）：cmap 中沿用原版汉字的字，重画其原版索引格 ----
    # 注意：只重画**译文实际用到**的复用字；未用到的日文汉字格保持原样。
    import struct as _st
    ac = s2a.Archive(os.path.join(BASE, 'res/cscv.s2a.bak'))
    ahm = ac.hash_map()
    blob = ac.blobs[ahm[TBL_HASH]]
    ents, types, end = parse_entries(blob)
    if len(ents) < 1409:
        raise SystemExit('!! 字符表解析异常: 仅 %d 项 (<1409)，中止' % len(ents))
    reuse_pairs = []
    if REUSE_ORIGINAL_CJK:
        _lo, _hi = REUSE_CJK_RANGE
        for i in range(_lo, _hi + 1):
            c = ents[i]
            if c and len(c) == 1 and is_cjk(c) and c in cmap:
                reuse_pairs.append((i, c))      # 重复表项也一并重画，保证查表命中哪格都一致

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
        aset = set(slots) | {i for i, _ in reuse_pairs}
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

        for idx, ch in list(zip(slots, chosen)) + reuse_pairs:
            page, u, v = game_cell(idx)
            put(pxb if page == 62 else pxA, u, v, glyph3(ch, page), page)
        print('  图集搬迁: 原版字形移动 %d 格, 跳过 %d (图集外/空位)' % (n_moved, n_skip))
        print('  同字复用: 重画原版汉字格 %d 格（%d 字）'
              % (len(reuse_pairs), len({c for _, c in reuse_pairs})))
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

        for idx, ch in list(zip(slots, chosen)) + reuse_pairs:
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
    # 复用字的条目在上面解析后保持原样，这里只写 1248+ 的新分配格。
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

# collide 放行清单：歌词行的日文原文。全部为【假命中】——同串也出现在 cscv 独有
#   blob355（女神房间歌曲表），而歌词是纯显示文本，不参与任何按名/按键比对。
#   · 主线剧情 LANG b1025（两副本同串，text_v2.csv row 58913-58915 / 58939-58941）；
#   · 各章节关底歌词浮层：每条原串在 LANG 全库只落在【本关 stage blob 的 1 个槽位】
#     （少数条形如 `どんな場所でも私は歌う` 另有两副本除外），在 cscv 全库只出现在
#     blob355（歌曲表）⇒ collide 命中纯属假命中，可放行。
#   ⚠ 不放行【名字键】同型槽：`聖なる者`（b34 村落/关卡表，stride1116）与 `いのち`
#     （b998 装备表，stride268）——它们同串也出现在 cscv 脚本层，属真键，必须保留原文。
#   实测枚举（lyric_report.py，2026-10-20）逐关列出：
SONG_OK = frozenset([
    # 主线剧情歌词（b1025 两副本）
    'おさなき日々の　あのせんりつは', '宝石よりも', 'まぶしくかがやいている',
    # 关底歌词浮层：按 stage blob 分组
    'さずけし悲しみ受け入れ',                                    # b29
    '心をこめた歌声だけが', 'ふるわせている',                        # b205
    'ありったけの',                                            # b221
    'さあここから', '旅を始めよう', 'あらしの中　私は歌う', 'どこまでも',    # b249
    'わずらいを消し去る', 'ととのえられた', '音色たちよ',              # b327
    'きせきの美しさ',                                          # b502
    'この歌', 'たずさえて', '旅に出よう',                         # b526
    '過去と未来の', '時をつないだ',                               # b705
    'どんな場所でも私は歌う', 'さあ今こそ', '船出の時よ',              # b730（PITFALLS §21 第四章关底）
    'その先に',                                               # b778
    '恐れず', '選んだ', '道だから',                              # b796
    '記憶の底に眠りつづけていた', '熱い思いが', 'むねの奥　ほとばしるの',    # b863
    '迷わせる鏡に', '負けない心を反射して',                         # b1013
    'おびえながらも', '激しく鳴らす調べは希望のあかし',                # b1045
])

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


def do_apply(text=True, sync_cscv=True, keep_collide=True, skip_blobs=None,
             consistent=False, menu_exempt=False, field_fix=True, ui_always=False,
             place=True, chap=True, song=True, slot_release=False, desc_release=False,
             exe_mode=None, lang_files=None, propagate_dups=False, mirror=False,
             title_guard=True):
    """生产安装 = 同名不翻(keep_collide) + 机制表不翻(skip_blobs)。
    这是 2026-09-12 测试C/D 验证过的"技能全可用"组合。
    v2.2/2.3: menu_exempt=True 额外豁免 UI blob(186/354/358/440/516/715/763) 的
    148 个纯 UI 串（v2.2 blob358 131 串已实测安全 + v2.3 词表 17 串）。
    v2.21: place=True 额外把村落地名显式写进 cscv blob28（见 apply_cscv_place）。"""
    em = (exe_mode or EXE_MODE).lower()
    rows, ents, types, end, tb, slots, chosen, cmap, st = build_plan()
    print('== 安装简体字模补丁%s ==' % ('' if text else '（测试包A：仅字模，不翻文本）'))
    print('覆盖 %.2f%% (新格 %d/%d, 同字复用 %d 字/重画 %d 格; 原版 0-1247 表项不变)'
          % (st['coverage'] * 100, st['chosen'], st['slots'],
             st['reuse_n'], st['reuse_slots']))
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
        # ★ v2.68：skip_blobs 以 None 作"调用方未指定"哨兵。原先 consistent=True 会**无条件清空**
        #   skip_blobs=()，把调用方显式传入的"机制表不翻"（如 E1 的 (128,136,317)）静默丢弃 ——
        #   结果 128/136/317（职业/阵形/连携技）仍被翻译，与已验证稳定配方（测试C/D）不符。
        #   现在：未指定时保持旧行为（consistent→()，否则 MECHANIC_BLOBS）；显式指定则一律生效。
        if skip_blobs is None:
            skip_blobs = () if consistent else MECHANIC_BLOBS
        if consistent:
            keep_collide = False
        rewrite_text(rows, cmap, st['native_set'], sync_cscv, keep_collide, skip_blobs,
                     consistent, menu_exempt, field_fix, ui_always, slot_release, desc_release,
                     lang_files=lang_files, propagate_dups=propagate_dups, mirror=mirror,
                     title_guard=title_guard)
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
def refresh_dlc01(verbose=True, en_only=False, ja_only=False):
    """把 DLC01 译文按当前 cmap 重新编码。任何异常都只打印，不抛出。

    en_only=True（E1 隔离实验）：只写 DLC01/LANG_EN.s2a，DLC01/LANG_JA.s2a 保持原版。
    ja_only=True（E3-JA 镜像实验）：只写 DLC01/LANG_JA.s2a，DLC01/LANG_EN.s2a 保持原版。
    """
    dlc_dir = os.path.join(BASE, 'DLC01')
    ja = os.path.join(dlc_dir, 'LANG_JA.s2a')
    en = os.path.join(dlc_dir, 'LANG_EN.s2a')
    bak = ja + dlc_lib.BAK_SUFFIX
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dlc_apply.py')
    # v2.67：仅在【确实存在 DLC01 原件】时自动生成原件备份。
    #   · 玩家未持有 DLC → DLC01/LANG_JA|EN.s2a 不存在 → 不创建任何文件，保持目录干净。
    #   · 持有 DLC 且首次构建 → 由当前文件复制出 .bak_dlc01_20260913（作为原件母本）。
    #   ⚠️ 原件备份取自"当前文件"，故应在【原版状态】下首次运行；若对已装机的目录运行，
    #      会把已改内容误当原件（届时 package 的逐文件校验会拒绝该文件并中止）。
    if os.path.exists(ja) and os.path.exists(en):
        for p in (ja, en):
            b = p + dlc_lib.BAK_SUFFIX
            if not os.path.exists(b):
                try:
                    shutil.copy2(p, b)
                    if verbose:
                        print('  [DLC01] 自动生成原件备份 %s' % os.path.basename(b))
                except Exception as e:
                    if verbose:
                        print('  [DLC01] 原件备份生成失败 %s：%r' % (os.path.basename(b), e))
    if not (os.path.exists(bak) and os.path.exists(script)):
        if verbose:
            print('  [DLC01] 跳过：未找到 DLC01 原件备份或装机器')
        return
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import dlc_apply as DA
        # ★ 必须复用主装机的 cmap：主装机用到 _EXTRA_ROWS，而调用本函数前
        #   _EXTRA_ROWS 已被清空；重算 build_plan() 会得到不同码表 ⇒ DLC 整段乱码。
        _cp = _LAST_BUILD_PLAN
        plan, over, _L = DA.build_plan(
            cmap=_cp[0] if _cp else None,
            native=_cp[1].get('native_set') if _cp else None)
        if over:
            print('  [DLC01] !! 有 %d 处超容量，已跳过（未写入）' % len(over))
            return
        # 直接写入（不复用 cmd_apply，避免它再 build_plan 一遍）
        import time as _t, shutil as _sh
        ts = _t.strftime('%Y%m%d_%H%M%S')
        targets = ((DA.D.P_EN,) if en_only else
                   (DA.D.P_JA,) if ja_only else
                   (DA.D.P_JA, DA.D.P_EN))
        for pth in targets:
            _sh.copy2(pth, pth + '.bak_dlcapplyv2_' + ts)
        for pth in targets:
            a = DA.D.s2a.Archive(pth)
            blobs = [bytearray(bytes(b)) for b in a.blobs]
            for p in plan:
                DA._write_slots(blobs[p['blob']], p)
            DA.D.s2a.pack(pth, a.entries, blobs)
        side = ' [仅 EN 侧]' if en_only else (' [仅 JA 侧]' if ja_only else '')
        print('  [DLC01] 已按当前字库重编码 %d 槽 / %d blob%s（备份后缀 .bak_dlcapplyv2_%s）'
              % (len(plan), len({p['blob'] for p in plan}), side, ts))
        # DLC 的关卡实体表同样按载具名查找（Q78「船」），必须与主道具表同串。
        if not ja_only:
            try:
                fill_dlc_item_name_copies(verbose=verbose)
            except Exception as e:
                print('  [DLC 道具名副本] 失败（不影响主装机）：%r' % e)
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
        if not live_run:
            # 槽头（FF FF FF FF 前缀 + 文本）被其它步骤整体清空：
            # Q16 键必须原样恢复；只要长度不越过记录边界就直接写回。
            if (c['stride'] <= 0 or c['rec'] < 0 or
                    c['off'] + len(own_run) <= 16 + (c['rec'] + 1) * c['stride']):
                per[name].append((c['bi'], c['off'], own_run, len(own_run)))
            else:
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


# ================= ★ E1 隔离实验：只写 LANG_EN（名字层整批中文化） =================
# 动机（2026-10-18，官方 EN/JA 对比实测）：官方 EN 版把 61,048/61,162 个文本槽（含
#   **全部名字列**：技能/职业/阵形/装备/称号/章节/伙伴）翻成英文，且 LANG_JA 与 cscv
#   官方一字未动 —— 证明"名字层写进 LANG_EN"本身不会破坏机制。本项目的机制损坏来自
#   （a）把中文载体码同步进 cscv 的脚本层、（b）改写 LANG_JA 的按键名槽位。
# E1 做法：**只写 res/LANG_EN.s2a**，cscv 文本层一个字节都不动（仅按新字库重写字符表，
#   CJK 必需），LANG_JA 保持原版。测试时须把游戏语言设为 English。
def verify_e1_isolation(verbose=True, expect_skill_key=True, target='en'):
    """断言隔离前提（不通过即返回 False）：
       · 未参与装机的另一侧 LANG 文件与母本逐字节相同
         （target='en' 校验 LANG_JA；target='ja' 校验 LANG_EN）
       · res/cscv.s2a 除【字符表 blob】外与母本逐字节相同（未做文本同步）
       · 目标文件 b666 的 pos288~375 键名列与原版一致（expect_skill_key=True 时）
    """
    import hashlib
    if verbose:
        print('== 隔离断言（目标=%s）==' % target.upper())
    ok = True
    # ① 另一侧 LANG 文件：整文件逐字节相同
    untouched = (('res/LANG_EN.s2a', 'DLC01/LANG_EN.s2a') if target == 'ja'
                 else ('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))
    for rel in untouched:
        cur = os.path.join(BASE, *rel.split('/'))
        bak = cur + (dlc_lib.BAK_SUFFIX if rel.startswith('DLC01/') else '.bak')
        if not (os.path.exists(cur) and os.path.exists(bak)):
            if verbose:
                print('  [E1] 跳过 %s（缺当前文件或原件备份）' % rel)
            continue
        hc = hashlib.md5(open(cur, 'rb').read()).hexdigest()
        hb = hashlib.md5(open(bak, 'rb').read()).hexdigest()
        if hc != hb:
            ok = False
        if verbose:
            print('  [E1] %-20s md5(cur)=%s md5(bak)=%s  %s'
                  % (rel, hc[:12], hb[:12], '相同' if hc == hb else '!! 不同'))
    # ② cscv：只允许字符表 blob 不同
    cur = os.path.join(BASE, 'res/cscv.s2a')
    bak = cur + '.bak'
    if os.path.exists(bak):
        arc = s2a.Archive(bak)
        tbl = arc.hash_map()[TBL_HASH]
        hb = [hashlib.md5(bytes(b)).hexdigest() for b in arc.blobs]
        hc = [hashlib.md5(bytes(b)).hexdigest() for b in s2a.Archive(cur).blobs]
        diff = [i for i in range(len(hb)) if i >= len(hc) or hc[i] != hb[i]]
        if diff != [tbl]:
            ok = False
        if verbose:
            print('  [E1] cscv.s2a 有差异的 blob=%s（字符表 blob=%d）%s'
                  % (diff, tbl, '仅字符表 OK' if diff == [tbl] else '!! 期望仅字符表'))
    # ③ ★ v2.67（E1b 守卫）：目标 LANG 文件 b666 的键名列 pos288~375 必须与原版逐字节一致
    cur = os.path.join(BASE, 'res/LANG_JA.s2a' if target == 'ja' else 'res/LANG_EN.s2a')
    bak = cur + '.bak'
    if expect_skill_key and os.path.exists(bak):
        lb = bytes(s2a.Archive(cur).blobs[SKILL_KEY_BLOB])
        ob = bytes(s2a.Archive(bak).blobs[SKILL_KEY_BLOB])
        n = bad = 0
        while 16 + n * SKILL_STRIDE + SKILL_KEY_HI <= min(len(lb), len(ob)):
            lo = 16 + n * SKILL_STRIDE + SKILL_KEY_LO
            hi = 16 + n * SKILL_STRIDE + SKILL_KEY_HI
            if lb[lo:hi] != ob[lo:hi]:
                bad += 1
            n += 1
        if bad:
            ok = False
        if verbose:
            print('  [E1] LANG_%s[666] 键名列 pos%d~%d 与原版一致：%d/%d %s'
                  % (target.upper(), SKILL_KEY_LO, SKILL_KEY_HI - 1, n - bad, n,
                     'OK' if not bad else '!! %d 条被改（技能会失效，中止）' % bad))
    return ok


def do_apply_lang_en_only(exe_mode=None):
    """E1 隔离实验装机：**只写 res/LANG_EN.s2a**（+ 常规字体/图集 + DLL/exe）。

    参数照批准方案：consistent=True（同一原文→同一译文，全副本一致）、
    keep_collide=False、skip_blobs=()、sync_cscv=False；不写 cscv 孪生表
    （place/chap/song=False）。DLC01 同样只写 LANG_EN。装机末尾断言隔离前提，失败则中止。

    v2.66（2026-10-18 首轮实机结果后的修正）：
      · propagate_dups=True —— 把已定译原文串按内容补齐到**未登记**的重复副本槽
        （武器表"该武器附带技能名"列等）。首轮失败的直接原因就是 b666 中文 / b147 英文
        ⇒ 按名链断，技能无效果/无动画、名字都弹不出来。
      · restore_q16_keys() —— 首轮跳过它导致「勇者城」等按键名查找的键槽被翻成
        中文；该函数把【各文件自己的】原版字节写回，LANG_JA/cscv 因未被改写而原样跳过，
        不破坏隔离前提。

    v2.67（E1b，2026-10-18 二轮实机结果后的修正）：
      · **b666 键名列 pos288~375 保持原版**——E1 首/二轮用 consistent 全副本统一，
        把内部键名也翻成载体码中文 ⇒ 脚本按名查技能失败 ⇒「只有名字、无动画无效果」。
        与 docs/PITFALLS.md §6/§8 记载完全同因（测试 E 全量一致翻译失败）。
      · **机制表 128/136/317（职业/阵形/连携技）整表不翻**——首轮把职业表也翻了，
        疑为「大章节开头角色装备消失」之因（职业表的初始装备亦按名解析）。
      · cscv 依旧不写（脚本层孪生名字键保持日版），隔离前提不变。
    """
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=(128, 136, 317),   # 机制表不翻；b666 不整表跳过，只跳键名列
                     consistent=True, menu_exempt=False, ui_always=False,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=True, exe_mode=exe_mode)
    print('== 同步 DLC01（E1：只写 DLC01/LANG_EN，LANG_JA 保持原版）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护（「勇者城」城/关卡按键名查找）==')
    restore_q16_keys()
    if not verify_e1_isolation():
        raise SystemExit('!! E1 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


# ================= ★ E2 镜像实验：照抄官方 EN 的改动集合 =================
# 依据（build/en_ja_report.txt、build/_e3_missing_out.txt、build/_e4_gapzh_out.txt、
#       build/_e5_out.txt，2026-10-18 全程只读实测）：
#   · 官方 EN 把 text_v2.csv 里 **全部 61,048 个 JA≠EN 槽**都改成英文，
#     含技能表 b666 键名列 pos288~375（86/86）、称号表 b931、职业/阵形表 b128/b136/b317、
#     装备表各引用列；官方 cscv 一字未动、LANG_JA 一字未动。
#   · 本项目 E1b 只改了 95.4%（61,048 中的 58,241），遗留 2,807 槽仍是英文：
#       2,105 = consistent"全有或全无"闸拒绝（cscv 字段可容纳约束，sync_cscv=False 时无意义）
#         418 = 章节/称号护栏     86 = Q16 键名回写     84 = b666 键名列护栏
#          41 = 无中文译文       6 = 机制表 skip_blobs
#     ⇒ 90% 的缺口是【我们自己的护栏】造成，官方没有这些护栏。
#   · 结论：E1b 失败的模式是"半中半英"（同一原文的副本一部分中文一部分英文）
#     导致按名链断裂；官方是"整条链同语言"。本变体即照此对齐。
def do_apply_lang_en_mirror(exe_mode=None):
    """E2 镜像装机：**只写 res/LANG_EN.s2a**（cscv/LANG_JA 与母本逐字节相同）。

    与 E1b 的差别（即与官方的第 1 步对齐）：
      · skip_blobs=()          —— 官方把 b128/b136/b317 也翻了
      · mirror=True            —— 去掉 b666 键名列护栏 + 章节/称号守卫，
                                 并放宽 consistent 闸的"cscv 字段可容纳"约束
      · 不调用 restore_q16_keys() —— 官方没有回写勇者城
    仍保留：只写 LANG_EN、不写 cscv、不写 LANG_JA；propagate_dups + padding-aware 容量。
    """
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=(), consistent=True, menu_exempt=False, ui_always=False,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=True,
                     mirror=True, title_guard=False, exe_mode=exe_mode)
    print('== 同步 DLC01（E2：只写 DLC01/LANG_EN，LANG_JA 保持原版）==')
    refresh_dlc01(en_only=True)
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! E2 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_lang_en_mirror(exe_mode=None):
    """E2 镜像实验打包：staging 里只写 LANG_EN 装机 → 输出 dist/E2-lang-en-mirror/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_lang_en_mirror',
                      stage_name='package_stage_e2',
                      out_dir=paths.dist('E2-lang-en-mirror'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= ★ E3 可用包：LANG_EN 隔离 + 机制名保持该文件原版英文 =================
# 依据（2026-10-18 全程只读实测 + 实机验证）：
#   · E1b（consistent 全副本统一）失败：技能「只有名字、无动画无效果」，因把 b666 的
#     【显示名 pos0】也翻成载体码中文 ⇒ 脚本按名查技能失败。
#   · E1c（只把装备名一列回退英文）→ 装备恢复；E1b（Q16 槽写回各文件原版字节）→ 勇者城恢复。
#   · E2（照抄官方 EN 改动集合，99.4%）失败模式与 E1b 完全相同：技能无效果 / 装备消失 / 勇者城消失。
#     E6 反证：官方 EN 自身有 9.25% 同原文多副本不一致、E2 只有 5.01%（比官方更自洽）却全坏 ⇒
#     决定性变量不是"一致性/覆盖率"，而是【机制按名解析时期待的是"该文件自己的原版语言串"】。
#   ⇒ 结论：纯数据层无法让"参与机制解析的名字"上屏中文。本包即路线 (A) 的可用包——
#     机制名/引用槽保持 LANG_EN 原版英文，其余（对话/说明/UI）中文化，机制应全部正常。
#
# 配方 = 生产装机 apply_menu 已验证稳定的护栏集合（测试 C/D"技能全可用"）：
#   · skip_blobs=MECHANIC_BLOBS(666/128/136/317) + 装备/道具表(147/357/736/998) 整表不翻
#     （技能/职业/阵形/连携技/装备的【名字与引用】列一律保持原版英文）
#   · keep_collide=True  —— 在 cscv 独有 blob 里作为按名比对键出现的串（称号/章节/伙伴名等）保留原版英文
#   · desc_release=True  —— 仅放行机制表内的【说明文字段】（b666 pos32/160、b128 pos84、b136 pos64、
#                            b147/357/736/998 pos44），名字/引用列不放行
#   · menu_exempt/ui_always/slot_release —— 生产已验证的 UI/说话人纯显示放行
#   · restore_q16_keys() —— Q16「勇者城」键槽写回各文件自己的原版字节
# 与生产装机的差别：sync_cscv=False（不写 cscv 文本层）、lang_files=['res/LANG_EN.s2a']
#   （不写 LANG_JA，隔离前提：LANG_JA/cscv 与母本逐字节相同）、不写 cscv 孪生表
#   （place/chap/song=False）。测试时须把游戏语言设为 English。
def do_apply_lang_en_names_en(exe_mode=None):
    """E3 可用包装机：只写 res/LANG_EN.s2a，机制名字/引用槽保持原版英文，其余中文。"""
    # 装备/道具表(147/357/736/998)也整表跳过：实测其【名字列 pos4】里夹着技能名引用
    #   （'Change Back!' / 'Gold Rush!' / 'Puny' / 附带技能名列 'Gold♪'），keep_collide 抓不全
    #   ⇒ 一并跳过，改由 desc_release 放行其【说明列 pos44】上中文。
    skip = tuple(MECHANIC_BLOBS) + (147, 357, 736, 998)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=True,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=False, mirror=False,
                     exe_mode=exe_mode)
    print('== 同步 DLC01（E3：只写 DLC01/LANG_EN，LANG_JA 保持原版）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护（「勇者城」城/关卡按键名查找）==')
    restore_q16_keys()
    if not verify_e1_isolation():
        raise SystemExit('!! E3 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_lang_en_names_en(exe_mode=None):
    """E3 可用包打包：staging 里只写 LANG_EN 装机 → 输出 dist/E3-lang-en-names-en/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_lang_en_names_en',
                      stage_name='package_stage_e3',
                      out_dir=paths.dist('E3-lang-en-names-en'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def do_package_stable_names(exe_mode=None):
    """稳定版备份包：机制名受保护（不上屏中文），只写 LANG_EN，输出到独立目录。

    配方与 E3 完全相同，只是固定写入 dist/stable-names-en/，便于随时回到稳定状态；
    译表/字库取当前版本，因此不会回退后续新增的译文。
    """
    return do_package(exe_mode=exe_mode, apply_cmd='apply_lang_en_names_en',
                      stage_name='package_stage_stable_names',
                      out_dir=paths.dist('stable-names-en'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= ★ Z1 names-cn 实验：翻技能表 b666 + 装备表，靠 propagate_dups 保链 =================
# 与 E3 的差别：E3 整表跳过技能表 b666 与装备/道具表(147/357/736/998)，机制名保持原版英文；
#   本变体只跳过 (128,136,317)（职业/阵形/连携技），放行 b666 与装备表让名字上中，
#   依靠 propagate_dups=True（同一原文字符串在各副本译成同一中文）+ mirror=False
#   （b666 内部键名列 pos288~375 自动保留原版，见 in_skill_key_col）维持"按名链"一致性。
# ================= ★ Z1 名称副本一致性补全（byte-level，2026-10-18）=================
# 依据（引擎 0x46C070 按名 CRC32 查表，无 strcmp；本文件按名链实测）：
#   同一名称串在【所有副本】必须字节一致 —— 技能表 b666 显示名 / 武器表"附带技能"引用列 /
#   脚本 loadout 行（`head=<装备名>`）等。只翻一部分 ⇒ 按名查表失败
#   （技能无效无动画 / 章节初始装备不发 / 勇者城不出现）。
# 做法：以【母本 vs 已装机产物】逐槽对比得规范表 canon（已翻槽的 原字节→译文字节），
#   再把 canon 应用到"内容仍等于母本（未被装机翻译）"的副本槽：
#     · 单槽整体：槽文本恰为 canon 键 → 整槽替换
#     · 多行 `key=value`：只把 value 恰为 canon 键的段替换，保留 `key=` 与 `\n`
#   容量以【母本】相邻内容为准：可吃掉尾部 NUL 填充，但保留 1 字节 NUL 终止符。
#   跳过 b666 内部键名列（in_skill_key_col，脚本按名查技能）与 Q16 键名槽
#   （与 restore_q16_keys 同一份 t17 清单；且 restore_q16_keys 在本补全之后还会回写一次）。
NAME_MAX_LEN = 64


def _iter_slots(blob):
    """按母本 0x00 分界枚举槽位：yield (run_start, text_start, run_end)。
    text_start = 跳过前导 0xFF 后的文本起点；纯 0xFF / 纯空 run 不产出。"""
    n = len(blob)
    pos = 0
    while pos < n:
        e = blob.find(b'\x00', pos)
        if e < 0:
            e = n
        f = pos
        while f < e and blob[f] == 0xFF:
            f += 1
        if f < e:
            yield pos, f, e
        pos = e + 1


def _slot_text_at(data, f):
    """从文本起点 f 读到下一个 0x00（无则到 blob 末尾），返回 (text, nul_pos)。"""
    e = data.find(b'\x00', f)
    if e < 0:
        e = len(data)
    return data[f:e], e


def _next_content(data, start):
    """start 起第一个既非 0x00 也非 0xFF 的字节位置（无则 len）。"""
    n = len(data)
    nx = start
    while nx < n and (data[nx] == 0x00 or data[nx] == 0xFF):
        nx += 1
    return nx


def _is_name_like(t):
    """短名称串判据：<=64 字节、无 \\n、且必须是【合法的 CP932 文本】。

    ★ 2026-10-22 修复：旧版只看“含 0x41..0x7A 或 >=0x81 的字节”，
      于是道具表里的 1~2 字节数字 ID（b'\\xd6'、b'\\x90\\x01'、b'\\xa1\\x01'）
      被当成“名字”。sync_name_replicas 会把某个被清空的副本当作翻译 b''，
      再把这个空值传播到全库同字节 run ⇒ 所有对应道具 ID 被清零，
      装备从列表消失（DLC 泳装 セクシーみずぎ 即此例）。
      数字 ID/二进制字段通常不是合法 CP932（前导字节缺少合法尾字节），
      严格解码即可排除。
    """
    if not t or len(t) > NAME_MAX_LEN or b'\n' in t:
        return False
    try:
        s = t.decode('cp932')
    except UnicodeDecodeError:
        return False
    return any(ch.isalnum() or ord(ch) >= 0x2E80 for ch in s)


def _q16_lang_en_offsets(lang='LANG_EN'):
    """t17 清单中 file==<lang> 且 wave==1 的槽位偏移 {blob: [off, ...]}（Q16 键名保护用）。"""
    out = collections.defaultdict(list)
    if not os.path.exists(Q16_KEY_TSV):
        return out
    try:
        rows = list(csv.DictReader(open(Q16_KEY_TSV, encoding='utf-8-sig'), delimiter='\t'))
    except Exception:
        return out
    for r in rows:
        try:
            if str(r['file']) != lang or int(r['wave']) != 1:
                continue
            out[int(r['blob'])].append(int(r['off']))
        except Exception:
            continue
    return out


def _q16_hit(q16, bi, lo, hi):
    """blob bi 是否有 Q16 键槽偏移落在 [lo, hi) 内。"""
    for o in q16.get(bi, ()):
        if lo <= o < hi:
            return True
    return False


def sync_name_replicas(orig_blobs, prod_path, verbose=True,
                       single_slot_blob_allow=None, multiline=True, q16_lang='LANG_EN'):
    """名称副本一致性补全（见上方说明）。orig_blobs = 装机前捕获的母本 blob 列表。
    只就地改写槽内字节（blob 长度不变），有改动才回写。返回统计 dict。
    两条规则可独立开关（bisect 用）：
      · R1（单槽整体替换）: 仅当 single_slot_blob_allow is None（不限，Z1 原行为）
        或当前 blob 索引 ∈ single_slot_blob_allow 时生效。
      · R2（多行 key=value 只替换 value）: multiline=False 时完全不做。
    安全跳过（b666 in_skill_key_col / Q16 键名槽）不受这两个开关影响。"""
    import re
    if not orig_blobs or not os.path.exists(prod_path):
        if verbose:
            print('  [名称副本] 跳过：缺少母本 blob 或产物文件')
        return {}
    arc = s2a.Archive(prod_path)
    prod = [bytes(b) for b in arc.blobs]
    q16 = _q16_lang_en_offsets(q16_lang)
    kv_re = re.compile(rb'^[A-Za-z][A-Za-z0-9_]*=')

    # ---- 1) 采集规范表 canon：母本槽文本(未翻) -> 产物槽文本(已翻) ----
    cands = collections.defaultdict(collections.Counter)
    for bi, ob in enumerate(orig_blobs):
        if bi >= len(prod) or bytes(ob)[:4] != b'CSCV':
            continue    # 只扫 CSCV 文本表：音频/图片里的巧合短串不能当归范名
        pb = prod[bi]
        for pos, f, e in _iter_slots(ob):
            if in_skill_key_col(bi, f) or _q16_hit(q16, bi, pos, e):
                continue
            ot = ob[f:e]
            pt, _ = _slot_text_at(pb, f)
            if ot != pt and _is_name_like(ot):
                cands[ot][pt] += 1
    canon, conflicts = {}, 0
    for ot, ctr in cands.items():
        if len(ctr) > 1:
            conflicts += 1
        canon[ot] = ctr.most_common(1)[0][0]

    # ---- 2) 把 canon 应用到"仍未翻译"的副本槽 ----
    n_single = n_multi = n_skip = 0
    used = set()
    changed_any = False
    for bi, ob in enumerate(orig_blobs):
        if bi >= len(prod):
            continue
        ob = bytes(ob)
        if ob[:4] != b'CSCV':
            continue    # 非文本表（Ogg/PNG 等）：绝不改写
        pb = bytearray(prod[bi])
        dirty = False
        for pos, f, e in _iter_slots(ob):
            if in_skill_key_col(bi, f) or _q16_hit(q16, bi, pos, e):
                continue
            ot = ob[f:e]
            pt, _ = _slot_text_at(pb, f)        # 直接读 bytearray（勿每次都 bytes(pb)）
            if pt != ot:
                continue                        # 该槽已被装机翻译，无需补
            new, kind = None, 0
            if ot in canon and (single_slot_blob_allow is None or bi in single_slot_blob_allow):
                new, kind = canon[ot], 1
            elif multiline and b'\n' in ot:
                out, ch = [], False
                for seg in ot.split(b'\n'):
                    m = kv_re.match(seg)
                    if m:
                        val = seg[m.end():]
                        if val in canon:
                            out.append(seg[:m.end()] + canon[val])
                            used.add(val)
                            ch = True
                            continue
                    out.append(seg)
                if ch:
                    new, kind = b'\n'.join(out), 2
            if new is None or not new:
                continue        # 空译文不能当“名字副本”传播（会清掉 ID/键字段）
            room = _next_content(ob, e) - f - 1
            if len(new) > room:
                n_skip += 1
                continue
            nb = new + b'\x00'
            pb[f:f + len(nb)] = nb
            if e > f + len(nb):
                # 清掉原槽残留的旧串尾巴（同装机约定：先清零再写）⇒ 槽仍是"单字段 + NUL 填充"
                pb[f + len(nb):e] = b'\x00' * (e - (f + len(nb)))
            dirty = True
            if kind == 1:
                n_single += 1
                used.add(ot)
            else:
                n_multi += 1
        if dirty:
            prod[bi] = bytes(pb)
            changed_any = True

    if changed_any:
        s2a.pack(prod_path, arc.entries, prod)
    if verbose:
        print('  [名称副本] 单槽填充 %d / 多行值填充 %d / 容量不足跳过 %d / '
              '规范条目使用 %d（canon %d，冲突 %d）%s'
              % (n_single, n_multi, n_skip, len(used), len(canon), conflicts,
                 '' if changed_any else ' [无改动]'))
    return dict(single=n_single, multi=n_multi, skip=n_skip, used=len(used),
                canon=len(canon), conflicts=conflicts)


def do_apply_names_cn(exe_mode=None):
    """Z1 names-cn 装机：只写 res/LANG_EN.s2a，翻 b666 技能名 + 装备表名，保留机制键名列。
    keep_collide=False —— 关键：collide 白名单里全是"疑似名字键"（技能/装备/称号/章节/伙伴名），
      第一版用了 True，结果这些名字槽一个都没被写（实测 b666 rec17 pos0 仍是 'Drain Axe'）。
      本实验要测的正是"显示层名字中文化"，故必须放行 collide。
      cscv 脚本层不受影响：sync_cscv=False，cscv 文本层不写。
    v2.69（2026-10-18）：do_apply 之后追加【名称副本一致性补全】——把已翻名字按内容补到
      未翻的重复副本槽（武器表"附带技能"引用列 / 脚本 loadout 行），随后 refresh_dlc01。"""
    # ★ 母本 = staging 里【未被 do_apply 触碰过】的 res/LANG_EN.s2a：在装机前捕获其 blob
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    skip = (128, 136, 317)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=False,
                     exe_mode=exe_mode)
    print('== 名称副本一致性补全（byte-level：武器表引用列 / 脚本 loadout 行）==')
    sync_name_replicas(orig_blobs, en_path)
    print('== 同步 DLC01（Z1：只写 DLC01/LANG_EN，LANG_JA 保持原版）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护（「勇者城」城/关卡按键名查找）==')
    restore_q16_keys()
    if not verify_e1_isolation():
        raise SystemExit('!! Z1 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn(exe_mode=None):
    """Z1 names-cn 打包：staging 里只写 LANG_EN 装机 → 输出 dist/Z1-names-cn/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn',
                      stage_name='package_stage_names_cn',
                      out_dir=paths.dist('Z1-names-cn'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= ★ Z3/Z4 二分实验（2026-10-18）：把 Z1 的两条补全规则拆开验证 =================
# 目的：Z1（两条规则全开）在开场 CG 结束时崩溃（exe VA 0x4714CA，按名遍历容器取到 0 而空指针）。
#   Z3 = 只留 R1 且限定在装备/武器引用表 {147,357,736,998}（R2 关闭）；
#   Z4 = Z3 + 打开 R2（多行 `key=value` 只替换 value）。二者对比即可定位是哪条规则打断了结构串。
#   例：blob 34 的 OVERTURE 结构定义 `head=…\nbody=…\nhandR=Lumberjack Axe\n…` 只有 R2 会动它。
def do_apply_names_cn_skill_only(exe_mode=None):
    """Z3 装机：与 do_apply_names_cn 同配方，但 R1 仅限 {147,357,736,998}、R2 关闭。"""
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    skip = (128, 136, 317)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=False,
                     exe_mode=exe_mode)
    print('== 名称副本一致性补全 [Z3 skill-only：R1 限装备表 / R2 关闭] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998}, multiline=False)
    print('== 同步 DLC01（Z3：只写 DLC01/LANG_EN，LANG_JA 保持原版）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护（「勇者城」城/关卡按键名查找）==')
    restore_q16_keys()
    if not verify_e1_isolation():
        raise SystemExit('!! Z3 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_apply_names_cn_skill_loadout(exe_mode=None):
    """Z4 装机：与 Z3 同，但打开 R2（多行 `key=value` 值替换），即 R1 限装备表 + R2 全开。"""
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    skip = (128, 136, 317)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=False,
                     exe_mode=exe_mode)
    print('== 名称副本一致性补全 [Z4 skill-loadout：R1 限装备表 / R2 开启] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998}, multiline=True)
    print('== 同步 DLC01（Z4：只写 DLC01/LANG_EN，LANG_JA 保持原版）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护（「勇者城」城/关卡按键名查找）==')
    restore_q16_keys()
    if not verify_e1_isolation():
        raise SystemExit('!! Z4 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_head(exe_mode=None):
    """HEAD（提交 9d8299b）生产配方复现包：apply_menu 原样 + 双侧写入 + cscv 同步 + place/chap/song。

    仅改变输出目录（dist/HEAD-package/）与 staging 名，装机配方与 HEAD 的 `package` 完全一致。
    用途：实机对照 HEAD 配方与 E3 隔离配方的差异。
    """
    return do_package(exe_mode=exe_mode, apply_cmd='apply_menu',
                      stage_name='package_stage_head',
                      out_dir=paths.dist('HEAD-package'))


def do_package_names_cn_skill_only(exe_mode=None):
    """Z3 二分包：staging 装机 → 输出 dist/Z3-skill-only/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_skill_only',
                      stage_name='package_stage_names_cn_skill_only',
                      out_dir=paths.dist('Z3-skill-only'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def do_package_names_cn_skill_loadout(exe_mode=None):
    """Z4 二分包：staging 装机 → 输出 dist/Z4-skill-loadout/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_skill_loadout',
                      stage_name='package_stage_names_cn_skill_loadout',
                      out_dir=paths.dist('Z4-skill-loadout'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def do_apply_names_cn_skill_loadout_ja(exe_mode=None):
    """Z4-JA：Z4 配方（技能/装备名中文 + loadout 同步 + 副本补齐）的**日语镜像**。

    与 Z4 的唯一区别：写 res/LANG_JA.s2a（而不是 LANG_EN），未参与侧 LANG_EN 保持原版。
    动机：日语文件与 cscv 是"孪生"关系，语言路径可能与 EN 不同，
          用来检验能否修复 Z4 遗留的两个演出瑕疵。
    注意：b666 +292 键名仍保持**该文件自己的原版**（日语），不参与翻译。
    """
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    orig_blobs = None
    if os.path.exists(ja_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    skip = (128, 136, 317)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_JA.s2a'], propagate_dups=True, mirror=False,
                     exe_mode=exe_mode)
    print('== 名称副本一致性补全 [Z4-JA：R1 限装备表 / R2 开启] ==')
    sync_name_replicas(orig_blobs, ja_path,
                       single_slot_blob_allow={147, 357, 736, 998}, multiline=True,
                       q16_lang='LANG_JA')
    print('== 同步 DLC01（Z4-JA：只写 DLC01/LANG_JA）==')
    refresh_dlc01(ja_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    if not verify_e1_isolation(target='ja'):
        raise SystemExit('!! Z4-JA 隔离断言失败：LANG_EN/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_skill_loadout_ja(exe_mode=None):
    """Z4-JA 包：staging 装机 → 输出 dist/Z4-ja-skill-loadout/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_skill_loadout_ja',
                      stage_name='package_stage_names_cn_skill_loadout_ja',
                      out_dir=paths.dist('Z4-ja-skill-loadout'),
                      expect_same=('res/LANG_EN.s2a', 'DLC01/LANG_EN.s2a'))


def align_skill_keycol(orig_blobs, en_path):
    """把技能表 b666 的键名（+292）写成与显示名（+0）相同的文本。

    记录内 pos288~375 的真实结构（实测 EN/JA 对照）：
        +288  u32 **语言无关的数字 ID**（EN 与 JA 87/87 完全相同，如 rec17=15）
              ⇒ 绝对不可修改！
        +292  字符串本体（NUL 填充）
        尾部  0xFF*8 + 3 个 u32 元数据   ⇒ 必须逐字节保留

    官方 EN='Hero Slash' / JA='ヒーロースラッシュ' 都随语言本地化，且与 pos0 相同。
    本函数只替换 +292 的字符串与中间填充，+288 与尾部元数据一律不动。
    """
    try:
        a = s2a.Archive(en_path)
    except Exception as e:
        print('  [键列对齐] 读取失败：%r' % e)
        return 0
    blobs = [bytearray(b) for b in a.blobs]
    if 666 >= len(blobs) or 666 >= len(orig_blobs):
        return 0
    ob = orig_blobs[666]
    zb = blobs[666]
    done = skipped = 0
    for rec in range((len(zb) - 16) // SKILL_STRIDE):
        b = 16 + rec * SKILL_STRIDE
        if b + SKILL_STRIDE > len(zb) or b + SKILL_STRIDE > len(ob):
            break
        o0 = ob[b:].split(b'\x00')[0]
        o292 = ob[b + 292:b + SKILL_STRIDE].split(b'\x00')[0]
        if not o292 or o0 != o292:
            continue                       # 母本本来就不同 -> 不动
        target = bytes(zb[b:].split(b'\x00')[0])
        if not target:
            continue
        seg = ob[b + 292:b + SKILL_STRIDE]
        tail_rel = seg.find(b'\xff', len(o292))
        if tail_rel < 0 or len(target) + 1 > tail_rel:
            skipped += 1
            continue
        zb[b + 292:b + SKILL_STRIDE] = (target + b'\x00' * (tail_rel - len(target))
                                        + bytes(zb[b + 292 + tail_rel:b + SKILL_STRIDE]))
        done += 1
    print('  [键列对齐] 写入 %d 条（+288 与尾部元数据未动），跳过 %d 条' % (done, skipped))
    if done:
        s2a.pack(en_path, a.entries, [bytes(x) for x in blobs])
    return done


def do_apply_lang_ja_names_ja(exe_mode=None):
    """E3-JA：E3 的日语镜像包 —— 只写 res/LANG_JA.s2a，机制名保持该文件原版。

    配方与 E3 完全对称：
      · lang_files=['res/LANG_JA.s2a']（LANG_EN / DLC01 LANG_EN 逐字节不动）
      · skip_blobs = 机制表(666/128/136/317) + 装备/道具表(147/357/736/998)
      · keep_collide=True（疑似名字键保留原文）、desc_release 放行说明列
      · restore_q16_keys() 按 TSV 里的 file 字段自动分文件处理
    游戏内需把语言设为 **日语**。
    """
    skip = tuple(MECHANIC_BLOBS) + (147, 357, 736, 998)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=True,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_JA.s2a'], propagate_dups=False, mirror=False,
                     exe_mode=exe_mode)
    print('== 同步 DLC01（E3-JA：只写 DLC01/LANG_JA，LANG_EN 保持原版）==')
    refresh_dlc01(ja_only=True)
    print('== Q16 键名槽位保护（「勇者城」城/关卡按键名查找）==')
    restore_q16_keys()
    if not verify_e1_isolation(target='ja'):
        raise SystemExit('!! E3-JA 隔离断言失败：LANG_EN/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_lang_ja_names_ja(exe_mode=None):
    """E3-JA 打包：staging 里只写 LANG_JA 装机 → 输出 dist/E3-ja-lang-ja-names-ja/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_lang_ja_names_ja',
                      stage_name='package_stage_ja_names_ja',
                      out_dir=paths.dist('E3-ja-lang-ja-names-ja'),
                      expect_same=('res/LANG_EN.s2a', 'DLC01/LANG_EN.s2a'))


def do_apply_names_cn_keycol(exe_mode=None):
    """Z9：与 Z4 相同，但把技能表 b666 的 pos288~375「键名列」也翻成中文（mirror=True）。

    依据（官方原版实测）：
      · LANG_EN b666 pos292 = 'Hero Slash'（英文）
      · LANG_JA b666 pos292 = 'ヒーロースラッシュ'（日文）
      ⇒ 键名列是**随语言本地化**的，官方两种语言都保持"pos0 == pos292"完全自洽。
      ⇒ v2.67 的"键列必须保持原版"是根据语言内自洽现象做的错误外推。
    本变体让中文包结构与官方一致：整张表全部中文、副本互相对应。
    """
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    skip = (128, 136, 317)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=True,
                     exe_mode=exe_mode)
    print('== 名称副本一致性补全 [Z9 keycol：R1 限装备表 / R2 开启] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998}, multiline=True)
    print('== 键名列对齐（pos292 := pos0，复刻官方 EN/JA 的逐字节相同结构）==')
    align_skill_keycol(orig_blobs, en_path)
    print('== 同步 DLC01（Z9：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    # Z9 的实验目的就是让键列随语言本地化（与官方 JA/EN 一致），故关闭该条断言；
    # 其余隔离前提（LANG_JA/cscv 文本层未动）仍然强制校验。
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! Z9 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_keycol(exe_mode=None):
    """Z9 包：staging 装机 → 输出 dist/Z9-keycol/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_keycol',
                      stage_name='package_stage_names_cn_keycol',
                      out_dir=paths.dist('Z9-keycol'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ============================================================================
# 方案A：名字哈希操作数重算（TECHNICAL.md §10.3.7）
# ----------------------------------------------------------------------------
# 引擎按名查找 = 名称字节 -> CRC-32 -> 与 32 位操作数比较（exe 0x46C070 / 0x46C0C0）。
# LANG 的 b83/b394/b417/b654/b756（stride 288）记录内 +4 处就是这种【名字哈希操作数】。
# 官方 EN 随译名同步更新了它们；只改名字不改操作数 ⇒ 按名链断（技能无动画/无效果等）。
# ============================================================================
NAME_OPERAND_BLOBS = (83, 394, 417, 654, 756)
NAME_OPERAND_REC_OFF = 4          # 记录内偏移：16 + rec*288 + 4
_CRC32_ENG_TABLE = None


def _crc32_eng_table():
    global _CRC32_ENG_TABLE
    if _CRC32_ENG_TABLE is None:
        t = []
        for i in range(256):
            c = i
            for _ in range(8):
                c = (0xEDB88320 ^ (c >> 1)) if (c & 1) else (c >> 1)
            t.append(c)
        _CRC32_ENG_TABLE = t
    return _CRC32_ENG_TABLE


def eng_name_hash(b):
    """引擎的按名哈希（exe 0x46C070）的 Python 等价实现。

    与标准 CRC-32 的唯一区别：**高位字节按符号扩展**参与运算
    （实测 JA 操作数 = 本函数结果；zlib.crc32 对 CP932 高字节给出不同值）。
    纯 ASCII 时与 zlib.crc32 完全一致。
    """
    table = _crc32_eng_table()
    crc = 0xFFFFFFFF
    for x in b:
        edx = (((x - 256) if x >= 0x80 else x) ^ crc) & 0xFFFFFFFF
        crc = ((edx >> 8) ^ table[edx & 0xFF]) & 0xFFFFFFFF
    return (~crc) & 0xFFFFFFFF


def _eng_name_hash_fast(b):
    """纯 ASCII 快路径（zlib.crc32 与引擎哈希逐位相同）；含高字节时走慢路径。"""
    import zlib
    if b and max(b) < 0x80:
        return zlib.crc32(b) & 0xFFFFFFFF
    return eng_name_hash(b)


def _name_hash_index(blobs):
    """{名字哈希: [(blob, 文本起点, 原文串)]}，只收 2..NAME_MAX_LEN 字节、无换行的槽。"""
    idx = {}
    for bi, blob in enumerate(blobs):
        b = bytes(blob)
        for _pos, f, e in _iter_slots(b):
            t = b[f:e]
            if not (2 <= len(t) <= NAME_MAX_LEN) or b'\n' in t:
                continue
            idx.setdefault(_eng_name_hash_fast(t), []).append((bi, f, t))
    return idx


def recompute_name_operands(orig_blobs, path, ja_blobs=None, strict=True, verbose=True):
    """方案A：按【最终写入字节】重算 LANG 中的名字哈希操作数。

    必须在所有写名步骤之后调用（副本补齐 / 键列对齐 / Q16 还原 / DLC 刷新）。
    规则：
      · 只处理 b83/394/417/654/756 的 16+rec*stride+4；原值为 0/0xFFFFFFFF 的跳过；
      · 与母本 JA 同位置的取值相同 ⇒ 语言无关内部键，**不重算**（官方 JA/EN 一致）；
      · 用【母本 EN】建立 名字哈希 -> 全部副本位置 的索引；
      · 读出每个副本的【当前最终字节】：全部一致才重算；仍为原文 ⇒ 视为"名字未翻译"，不改；
      · 副本之间不一致（部分翻译 / 译文不同）⇒ 按名链必断，strict 时中止并列出明细。
    """
    if not orig_blobs or not os.path.exists(path):
        if verbose:
            print('  [操作数] 跳过：缺少母本 blob 或产物文件')
        return {}
    arc = s2a.Archive(path)
    prod = [bytearray(b) for b in arc.blobs]
    idx = _name_hash_index(orig_blobs)
    stats = dict(updated=0, kept=0, internal=0, unresolved=0, conflict=0, repaired=0)
    bad = []
    per_blob = collections.Counter()
    for bi in NAME_OPERAND_BLOBS:
        if bi >= len(orig_blobs) or bi >= len(prod):
            continue
        ob = bytes(orig_blobs[bi])
        if ob[:4] != b'CSCV':
            continue
        stride, count = struct.unpack_from('<II', ob, 4)
        if stride <= 0 or 16 + stride * count > len(ob):
            continue
        jb = bytes(ja_blobs[bi]) if ja_blobs is not None and bi < len(ja_blobs) else None
        pb = prod[bi]
        for rec in range(count):
            off = 16 + rec * stride + NAME_OPERAND_REC_OFF
            if off + 4 > len(ob):
                break
            old = struct.unpack_from('<I', ob, off)[0]
            if old in (0, 0xFFFFFFFF):
                continue
            if jb is not None and off + 4 <= len(jb) \
                    and struct.unpack_from('<I', jb, off)[0] == old:
                stats['internal'] += 1      # 语言无关内部键（JA/EN 同值）
                continue
            occ = idx.get(old)
            if not occ:
                stats['unresolved'] += 1
                if verbose:
                    print('  [操作数] b%d rec%d 源串未解析（%08X），保持原值'
                          % (bi, rec, old))
                continue
            finals = set()
            for sbi, f, _t in occ:
                if sbi >= len(prod):
                    continue
                dst = prod[sbi]
                e = dst.find(b'\x00', f)
                if e < 0:
                    e = len(dst)
                finals.add(bytes(dst[f:e]))
            if not finals:
                stats['unresolved'] += 1
                continue
            if len(finals) > 1:
                stats['conflict'] += 1
                bad.append((bi, rec, old, sorted(finals)))
                continue
            new_text = finals.pop()
            if new_text == occ[0][2]:
                want = old                # 名字保持原文（未翻译）：应还原为原操作数
                kind = 'kept'
            else:
                want = eng_name_hash(new_text)
                kind = 'kept' if want == old else 'updated'
            cur = struct.unpack_from('<I', pb, off)[0]
            if cur == want:
                stats[kind] += 1
                continue
            struct.pack_into('<I', pb, off, want)
            if kind == 'updated':
                stats['updated'] += 1
                per_blob[bi] += 1
            else:
                # 名字未翻译但操作数字节被其它步骤（如误登记为文本槽）覆盖 ⇒ 回填修复
                stats['repaired'] += 1
    if stats['updated'] or stats['repaired']:
        s2a.pack(path, arc.entries, [bytes(x) for x in prod])
    if verbose:
        print('  [操作数] 重算 %d / 回填修复 %d / 名字未变 %d / 内部键跳过 %d / '
              '源串未解析 %d / 副本不一致 %d%s'
              % (stats['updated'], stats['repaired'], stats['kept'],
                 stats['internal'], stats['unresolved'], stats['conflict'],
                 '' if (stats['updated'] or stats['repaired']) else ' [无改动]'))
        if stats['updated']:
            print('           按 blob 分布：%s'
                  % ', '.join('b%d=%d' % (k, per_blob[k]) for k in sorted(per_blob)))
        for bi, rec, old, fs in bad[:30]:
            print('    !! b%d rec%d 原哈希 %08X 的副本终串不一致：%r'
                  % (bi, rec, old,
                     [x.decode('cp932', 'replace') for x in fs[:4]]))
    if stats['conflict'] and strict:
        print('!! 名字副本不一致：按名链必然断裂，先修副本同步再谈操作数（中止）')
        raise SystemExit(1)
    return stats


def do_apply_names_cn_keycol_hash(exe_mode=None):
    """Z10 = Z9（键列中文）+ 方案A（重算名字哈希操作数）。

    Z9 实机表现：技能"有名字、无动画/无效果"，根因是名字改了而操作数没改
    （TECHNICAL.md §10.3.7 / PITFALLS.md §25.9）。本配方在全部写名步骤之后，
    按最终写入字节重算 b83/394/417/654/756 的 +4 操作数，并断言副本一致。
    """
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    skip = (128, 136, 317)
    stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                     skip_blobs=skip, consistent=False,
                     menu_exempt=True, ui_always=True,
                     slot_release=True, desc_release=True,
                     place=False, chap=False, song=False,
                     lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=True,
                     exe_mode=exe_mode)
    print('== 名称副本一致性补全 [Z10：R1 限装备表+连携技名表(b391) / R2 开启] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998, 391}, multiline=True)
    print('== 键名列对齐（pos292 := pos0）==')
    align_skill_keycol(orig_blobs, en_path)
    print('== 同步 DLC01（Z10：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    print('== 方案A：重算名字哈希操作数（按最终写入字节）==')
    ja_blobs = None
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if os.path.exists(ja_path):
        try:
            ja_blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
        except Exception as e:
            print('  [操作数] 母本 LANG_JA 读取失败：%r' % e)
    recompute_name_operands(orig_blobs, en_path, ja_blobs=ja_blobs)
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! Z10 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_keycol_hash(exe_mode=None):
    """Z10 包：staging 装机 → 输出 dist/Z10-keycol-hash/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_keycol_hash',
                      stage_name='package_stage_names_cn_keycol_hash',
                      out_dir=paths.dist('Z10-keycol-hash'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def _mech_ja_names():
    """从母本 LANG_JA 收集机制名（技能 b666 pos0 + 装备/道具表名字列）的日文原串。"""
    out = set()
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if not os.path.exists(ja_path):
        return out

    def add(t):
        if not t:
            return
        try:
            out.add(strip_f8f3(t.decode('cp932').strip()))
        except Exception:
            pass

    try:
        blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
    except Exception as e:
        print('  [Z10b] 母本 LANG_JA 读取失败：%r' % e)
        return out
    b = blobs[666]
    n = struct.unpack_from('<I', b, 8)[0] if b[:4] == b'CSCV' else 0
    for rec in range(n):
        add(b[16 + rec * SKILL_STRIDE:16 + rec * SKILL_STRIDE + 64].split(b'\x00')[0])
    for bi in EQUIP_BLOBS:
        b = blobs[bi]
        n = struct.unpack_from('<I', b, 8)[0] if b[:4] == b'CSCV' else 0
        for rec in range(n):
            add(b[16 + rec * EQUIP_STRIDE + 4:16 + rec * EQUIP_STRIDE + 36].split(b'\x00')[0])
    return out


def _partner_ja_names():
    """母本 LANG_JA 中伙伴名（b954 伙伴数据表 + b1034 伙伴演员表）的日文原串。"""
    out = set()
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if not os.path.exists(ja_path):
        return out
    try:
        blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
    except Exception:
        return out

    def add(t):
        if t:
            try:
                out.add(strip_f8f3(t.decode('cp932').strip()))
            except Exception:
                pass

    for rec in range(44):
        add(blobs[954][16 + rec * 236 + 4:16 + rec * 236 + 236].split(b'\x00')[0])
    for rec in range(54):
        add(blobs[1034][16 + rec * 104 + 4:16 + rec * 104 + 36].split(b'\x00')[0])
    return out


def _mech_release_factory(mech_ja):
    """Z10b 的 collide 额外放行：机制名整槽 / 章节 loadout 行里的装备名。"""
    keys = ('head', 'body', 'handR', 'handL', 'foot')

    def extra(bi, off, ja_cmp):
        if ja_cmp in mech_ja:
            return True
        if '\n' in ja_cmp and '=' in ja_cmp:
            for line in ja_cmp.split('\n'):
                k, sep, v = line.partition('=')
                if sep and k in keys and v in mech_ja:
                    return True
        return False

    return extra


def _partner_en_names(orig_blobs):
    """母本 LANG_EN 中伙伴名（b954 + b1034）的英文原串。"""
    out = set()
    for rec in range(44):
        t = orig_blobs[954][16 + rec * 236 + 4:16 + rec * 236 + 236].split(b'\x00')[0]
        if t:
            out.add(t)
    for rec in range(54):
        t = orig_blobs[1034][16 + rec * 104 + 4:16 + rec * 104 + 36].split(b'\x00')[0]
        if t:
            out.add(t)
    return out


def restore_partner_names(orig_blobs, en_path, verbose=True):
    """Z10b 收尾：把所有伙伴名整槽写回母本字节，保证伙伴名不进入混合态。

    例外：对话表 stride292/pos96 的说话人名（stable 的 slot_release 本就翻译），保持现状。
    """
    arc = s2a.Archive(en_path)
    prod = [bytearray(bytes(b)) for b in arc.blobs]
    pset = _partner_en_names(orig_blobs)
    n = skip = 0
    for bi, ob in enumerate(orig_blobs):
        pb = prod[bi]
        st = struct.unpack_from('<I', ob, 4)[0] if ob[:4] == b'CSCV' else 0
        for _pos, f, e in _iter_slots(ob):
            t = ob[f:e]
            if t not in pset:
                continue
            if st == 292 and (f - 16) % 292 == 96:
                continue
            oe = pb.find(b'\x00', f)
            if oe < 0:
                oe = len(pb) - 1
            # 母本该槽原本就容纳 len(t) 字节，回写同长度一定安全；
            # 若产物译文更短（常见：中文 2 字 vs 英文 6 字节），按母本长度写回并补 NUL。
            pb[f:f + len(t)] = t
            pb[f + len(t)] = 0
            end = max(oe, f + len(t))
            if end > f + len(t):
                pb[f + len(t) + 1:end + 1] = b'\x00' * (end - f - len(t))
            n += 1
    if n:
        s2a.pack(en_path, arc.entries, [bytes(x) for x in prod])
    if verbose:
        print('  [伙伴名] 回写原版 %d 处%s' % (n, '（容量不足跳过 %d）' % skip if skip else ''))
    return n


def do_apply_names_cn_mech_hash(exe_mode=None):
    """Z10b 判别实验：stable（其余 collide 全保留）+ 仅机制名中文化 + 操作数重算。

    与 Z10 的唯一差异：keep_collide=True，并通过 _EXTRA_RELEASE 只放行
    技能/装备名（含全部副本）与章节 loadout；伙伴名/说话人名/其它受保护串保持原版。
    """
    global _EXTRA_RELEASE
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    mech_ja = _mech_ja_names()
    partner_ja = _partner_ja_names()
    # 装备表 b147/357/736/998 里夹着伙伴角色自身条目（rec235=Knight 等），
    # 名字列与伙伴名同串 ⇒ 必须从机制名集合剔除，否则会被当装备名一起翻掉。
    overlap = mech_ja & partner_ja
    mech_ja -= partner_ja
    print('  [Z10b] 机制名原文 %d 条；伙伴名 %d 条保持原版（剔除同名 %d）'
          % (len(mech_ja), len(partner_ja), len(overlap)))
    _EXTRA_RELEASE = _mech_release_factory(mech_ja)
    try:
        stats = do_apply(text=True, sync_cscv=False, keep_collide=True,
                         skip_blobs=(128, 136, 317), consistent=False,
                         menu_exempt=True, ui_always=True,
                         slot_release=True, desc_release=True,
                         place=False, chap=False, song=False,
                         lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=True,
                         exe_mode=exe_mode)
    finally:
        _EXTRA_RELEASE = None
    print('== 名称副本一致性补全 [Z10b：R1 装备表+b391 / R2 开启] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998, 391}, multiline=True)
    print('== 键名列对齐（pos292 := pos0）==')
    align_skill_keycol(orig_blobs, en_path)
    print('== 同步 DLC01（Z10b：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    print('== 伙伴名保持原版（回写母本字节）==')
    restore_partner_names(orig_blobs, en_path)
    print('== 方案A：重算名字哈希操作数（按最终写入字节）==')
    ja_blobs = None
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if os.path.exists(ja_path):
        try:
            ja_blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
        except Exception as e:
            print('  [操作数] 母本 LANG_JA 读取失败：%r' % e)
    recompute_name_operands(orig_blobs, en_path, ja_blobs=ja_blobs)
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! Z10b 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_mech_hash(exe_mode=None):
    """Z10b 判别包：staging 装机 → 输出 dist/Z10b-mech-names/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_mech_hash',
                      stage_name='package_stage_names_cn_mech_hash',
                      out_dir=paths.dist('Z10b-mech-names'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= Z11：伙伴名 + 复合键（2026-10-21） =================
# 设计：Z10b（其余 collide 保留）只额外加入伙伴名与 b954 复合键。
#   · b954/b1034 的译文由 _z11_partner_rows() 注入 build_plan（不写回 CSV）；
#   · _EXTRA_RELEASE 放行：伙伴名（b954/b1034/全部副本）+ b954 +136/+168 复合键；
#   · 不做 restore_partner_names（Z11 就是要让伙伴名上屏）；
#   · 最后按终串重算操作数（76 个复合键引用会被更新）。
_PARTNER_NAME_OVERRIDE = {
    # 'Wise Man' 的日文是 ケンジャ（与 'Sage'=賢者 不同名），不可同译，避免哈希串味。
    'Wise Man': '智者',
}
_PARTNER_COMP_SPECIAL = {
    'Oron (Demon) Skill': '恶魔奥隆技能',
    'Oron (Angel) Skill': '天使奥隆技能',
}


def _csv_name_map():
    """当前译表：英文原串 -> 唯一中文译文（多译/缺译返回 None）。"""
    m = collections.defaultdict(set)
    for r in csv.DictReader(open(CSV, encoding='utf-8-sig')):
        en = (r.get('en') or '').strip()
        zh = (r.get('zh_new') or r.get('zh_3dm') or '').strip()
        if en and zh:
            m[en].add(zh)
    return {k: next(iter(v)) for k, v in m.items() if len(v) == 1}


def _z11_partner_rows():
    """生成 b954/b1034 伙伴名与复合键的额外译表行（不落盘）。"""
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if not (os.path.exists(en_path) and os.path.exists(ja_path)):
        return []
    E = [bytes(b) for b in s2a.Archive(en_path).blobs]
    J = [bytes(b) for b in s2a.Archive(ja_path).blobs]
    nm = _csv_name_map()

    def z_of(en_s):
        if en_s in _PARTNER_NAME_OVERRIDE:
            return _PARTNER_NAME_OVERRIDE[en_s]
        return nm.get(en_s)

    def dec(t):
        try:
            return t.decode('cp932').strip()
        except Exception:
            return ''

    out = []
    rid = 900000
    missing = []

    def add(bi, off, sb, en_b, ja_b, zh):
        nonlocal rid
        if not zh:
            missing.append(dec(en_b))
            return
        rid += 1
        out.append(dict(
            row_id=str(rid), blob_index=str(bi), offset=str(off),
            slot_bytes=str(sb), max_cn=str(sb // 2), len_en=str(len(en_b)),
            en=dec(en_b), ja=dec(ja_b), zh_3dm='', zh_new=zh,
        ))

    # b954 +4 伙伴实体名
    for rec in range(44):
        base = 16 + rec * 236
        en_b = E[954][base + 4:base + 36].split(b'\x00')[0]
        ja_b = J[954][base + 4:base + 36].split(b'\x00')[0]
        if not en_b or b'<' in en_b:
            continue
        add(954, base + 4, 32, en_b, ja_b, z_of(dec(en_b)))
    # b1034 +4 伙伴演员名
    for rec in range(54):
        base = 16 + rec * 104
        en_b = E[1034][base + 4:base + 36].split(b'\x00')[0]
        ja_b = J[1034][base + 4:base + 36].split(b'\x00')[0]
        if not en_b or b'<' in en_b:
            continue
        add(1034, base + 4, 32, en_b, ja_b, z_of(dec(en_b)))
    # b954 +136/+168 复合键（Yushia/Yuja 为运行时动态名，保持英文）
    for rec in range(44):
        base = 16 + rec * 236
        for off, sb in ((136, 32), (168, 64)):
            en_b = E[954][base + off:base + off + sb].split(b'\x00')[0]
            ja_b = J[954][base + off:base + off + sb].split(b'\x00')[0]
            if not en_b:
                continue
            en_s = dec(en_b)
            if 'Yushia' in en_s or 'Yuja' in en_s:
                continue
            zh = _PARTNER_COMP_SPECIAL.get(en_s)
            if not zh:
                if en_s.endswith(' Skill'):
                    base_zh = z_of(en_s[:-6])
                    zh = (base_zh + '技能') if base_zh else None
                elif en_s.endswith(' Resident'):
                    base_zh = z_of(en_s[:-9])
                    zh = (base_zh + '常驻') if base_zh else None
            add(954, base + off, sb, en_b, ja_b, zh)
    if missing:
        print('  [Z11] 无译名跳过 %d：%r' % (len(missing), missing[:10]))
    return _apply_extra_overrides(out)


def _z11_release_factory(mech_ja, partner_ja):
    """Z11 放行：机制名 + 伙伴名 + b954 复合键。"""
    base = _mech_release_factory(mech_ja)

    def extra(bi, off, ja_cmp):
        if ja_cmp in partner_ja:
            return True
        if bi == 954 and (off - 16) % 236 in (136, 168):
            return True
        return base(bi, off, ja_cmp)

    return extra


def fill_name_copies(orig_blobs, en_path, names_en, verbose=True,
                     skip_blobs=(128, 136, 317), title_ok=None):
    """Z11/Z12 收尾：把仍未翻译的名字整槽按已译副本补齐（全 blob）。

    只处理“原串恰好是给定名字集合中的整槽”；不碰其它字符串/命令 token。
    skip_blobs 内的表（职业/阵型/连携技）视为键表，**绝不补齐**；
    title_ok 内的 (blob, offset) 允许作为称号名参与 canon（Z14 专用）。
    """
    if not orig_blobs or not os.path.exists(en_path):
        return 0
    arc = s2a.Archive(en_path)
    prod = [bytearray(bytes(b)) for b in arc.blobs]
    names_en = {x for x in names_en if x}
    canon = {}
    conflicts = 0
    cnt = collections.defaultdict(collections.Counter)
    ct_whole, ct_recs, _ct_vals = load_chap_title_guard()
    q16 = _q16_lang_en_offsets('LANG_EN')

    def blocked(bi, ob, pos, f, e):
        """称号/Q16/技能键名列一律不参与“按内容补齐”。"""
        st = struct.unpack_from('<I', ob, 4)[0] if ob[:4] == b'CSCV' else 0
        if st and not (title_ok and (bi, f) in title_ok):
            rec = (f - 16) // st
            p = (f - 16) % st
            if chap_title_hit(ct_whole, ct_recs, bi, st, p, rec):
                return True
        if in_skill_key_col(bi, f):
            return True
        if _q16_hit(q16, bi, pos, e):
            return True
        return False

    for bi, ob in enumerate(orig_blobs):
        if bi >= len(prod) or bi in skip_blobs or bytes(ob)[:4] != b'CSCV':
            continue    # 资料型 blob（音频/图片）不参与名字副本补齐
        pb = prod[bi]
        for pos, f, e in _iter_slots(ob):
            ot = ob[f:e]
            if ot not in names_en or blocked(bi, ob, pos, f, e):
                continue
            pt, _ = _slot_text_at(bytes(pb), f)
            if pt != ot:
                cnt[ot][bytes(pt)] += 1
    for ot, ctr in cnt.items():
        if len(ctr) > 1:
            conflicts += 1
        canon[ot] = ctr.most_common(1)[0][0]
    n = skip = 0
    for bi, ob in enumerate(orig_blobs):
        if bi >= len(prod) or bi in skip_blobs or bytes(ob)[:4] != b'CSCV':
            continue    # 同上：只写 CSCV 文本表
        pb = prod[bi]
        for pos, f, e in _iter_slots(ob):
            ot = ob[f:e]
            if ot not in canon or blocked(bi, ob, pos, f, e):
                continue
            pt, _ = _slot_text_at(bytes(pb), f)
            if pt != ot:
                continue
            enc = canon[ot]
            oe = pb.find(b'\x00', f)
            if oe < 0:
                continue
            nx = oe
            while nx < len(pb) and pb[nx] == 0:
                nx += 1
            if len(enc) + 1 > nx - f:
                skip += 1
                continue
            pb[f:f + len(enc)] = enc
            pb[f + len(enc)] = 0
            for i in range(f + len(enc) + 1, nx):
                pb[i] = 0
            n += 1
    if n:
        s2a.pack(en_path, arc.entries, [bytes(x) for x in prod])
    if verbose:
        print('  [伙伴名] 副本补齐 %d 处%s%s'
              % (n, '（容量不足 %d）' % skip if skip else '',
                 '（终串冲突 %d）' % conflicts if conflicts else ''))
    return n


def do_apply_names_cn_partner_hash(exe_mode=None):
    """Z11：Z10b + 伙伴名（b954/b1034 及全部副本）+ b954 复合键 + 操作数重算。"""
    global _EXTRA_RELEASE, _EXTRA_ROWS
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    mech_ja = _mech_ja_names()
    partner_ja = _partner_ja_names()
    mech_ja -= partner_ja
    rows = _z11_partner_rows()
    print('  [Z11] 伙伴名 %d 条 / 新增译表行 %d（机制名 %d，其余 collide 保留）'
          % (len(partner_ja), len(rows), len(mech_ja)))
    _EXTRA_ROWS = rows
    _EXTRA_RELEASE = _z11_release_factory(mech_ja, partner_ja)
    try:
        stats = do_apply(text=True, sync_cscv=False, keep_collide=True,
                         skip_blobs=(128, 136, 317), consistent=False,
                         menu_exempt=True, ui_always=True,
                         slot_release=True, desc_release=True,
                         place=False, chap=False, song=False,
                         lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=True,
                         exe_mode=exe_mode)
    finally:
        _EXTRA_RELEASE = None
        _EXTRA_ROWS = None
    print('== 名称副本一致性补全 [Z11：R1 装备表+b391 / R2 开启] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998, 391}, multiline=True)
    print('== 键名列对齐（pos292 := pos0）==')
    align_skill_keycol(orig_blobs, en_path)
    print('== 同步 DLC01（Z11：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    print('== 伙伴名副本补齐（含 skip 表，仅整槽名字）==')
    fill_name_copies(orig_blobs, en_path, _partner_en_names(orig_blobs))
    print('== 方案A：重算名字哈希操作数（按最终写入字节）==')
    ja_blobs = None
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if os.path.exists(ja_path):
        try:
            ja_blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
        except Exception as e:
            print('  [操作数] 母本 LANG_JA 读取失败：%r' % e)
    recompute_name_operands(orig_blobs, en_path, ja_blobs=ja_blobs)
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! Z11 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_partner_hash(exe_mode=None):
    """Z11 包：staging 装机 → 输出 dist/Z11-partner-names/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_partner_hash',
                      stage_name='package_stage_names_cn_partner_hash',
                      out_dir=paths.dist('Z11-partner-names'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= Z12：批次 A 显示名（2026-10-21） =================
# 只放行“已有译文、且已确认是显示列”的表；称号表不在内（chap_title_guard 明确是键）。
# 几何：(stride, 允许的 record 内偏移集合)
Z12_RELEASE_COLS = {
    407: (236, (4,)),        # 敌人/怪物/伙伴数据名
    4: (288, (92,)),         # Boss/敌人台词表 说话人名
    30: (288, (92,)),
    408: (288, (92,)),
    445: (288, (92,)),
    528: (288, (92,)),
    748: (288, (92,)),
    609: (288, (92,)),
    483: (288, (92,)),
    555: (660, (92,)),
    734: (660, (92,)),
    777: (236, (4,)),        # 宝箱显示名
    1008: (236, (4,)),
    320: (492, (228, 292)),  # 音乐表：曲名 / 艺术家
    715: (224, (112,)),      # 地图编辑器 UI 标签
}


def _z12_names_en(orig_blobs):
    """Z12 表内“已有现成译文”的 EN 原串（用于全库副本补齐）。"""
    nm = _csv_name_map()
    out = set()
    for bi, (st, poss) in Z12_RELEASE_COLS.items():
        if bi >= len(orig_blobs):
            continue
        b = orig_blobs[bi]
        n = struct.unpack_from('<I', b, 8)[0]
        for r in range(n):
            base = 16 + r * st
            for pos in poss:
                t = b[base + pos:base + pos + 64].split(b'\x00')[0]
                if not t:
                    continue
                try:
                    s = t.decode('cp932').strip()
                except Exception:
                    continue
                if s in nm:
                    out.add(t)
    return out


def _z12_release_factory(mech_ja, partner_ja):
    base = _z11_release_factory(mech_ja, partner_ja)

    def extra(bi, off, ja_cmp):
        cfg = Z12_RELEASE_COLS.get(bi)
        if cfg and (off - 16) % cfg[0] in cfg[1]:
            return True
        return base(bi, off, ja_cmp)

    return extra


def do_apply_names_cn_display_hash(exe_mode=None):
    """Z12：Z11 + 批次 A 显示名（敌名/Boss 名/宝箱/音乐/地图 UI）。"""
    global _EXTRA_RELEASE, _EXTRA_ROWS
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    mech_ja = _mech_ja_names()
    partner_ja = _partner_ja_names()
    mech_ja -= partner_ja
    rows = _z11_partner_rows()
    extra_en = _z12_names_en(orig_blobs or [])
    print('  [Z12] 批次 A 名字 %d 条 / 新增译表行 %d（机制名 %d，伙伴 %d）'
          % (len(extra_en), len(rows), len(mech_ja), len(partner_ja)))
    _EXTRA_ROWS = rows
    _EXTRA_RELEASE = _z12_release_factory(mech_ja, partner_ja)
    try:
        stats = do_apply(text=True, sync_cscv=False, keep_collide=True,
                         skip_blobs=(128, 136, 317), consistent=False,
                         menu_exempt=True, ui_always=True,
                         slot_release=True, desc_release=True,
                         place=False, chap=False, song=False,
                         lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=True,
                         exe_mode=exe_mode)
    finally:
        _EXTRA_RELEASE = None
        _EXTRA_ROWS = None
    print('== 名称副本一致性补全 [Z12：R1 装备表+b391 / R2 开启] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998, 391}, multiline=True)
    print('== 键名列对齐（pos292 := pos0）==')
    align_skill_keycol(orig_blobs, en_path)
    print('== 同步 DLC01（Z12：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    print('== 名字副本补齐（伙伴名 + 批次 A 名字，含 skip 表）==')
    names = _partner_en_names(orig_blobs) | extra_en
    fill_name_copies(orig_blobs, en_path, names)
    print('== 方案A：重算名字哈希操作数（按最终写入字节）==')
    ja_blobs = None
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if os.path.exists(ja_path):
        try:
            ja_blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
        except Exception as e:
            print('  [操作数] 母本 LANG_JA 读取失败：%r' % e)
    recompute_name_operands(orig_blobs, en_path, ja_blobs=ja_blobs)
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! Z12 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_display_hash(exe_mode=None):
    """Z12 包：staging 装机 → 输出 dist/Z12-display-names/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_display_hash',
                      stage_name='package_stage_names_cn_display_hash',
                      out_dir=paths.dist('Z12-display-names'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= Z13：批次 B（2026-10-21） =================
# 内容：Z12 + 武器合成/UI 缺译行 + 伙伴/敌人技能名（脚本参数列）。
# 设计：译文用 _EXTRA_ROWS 注入（不写回 CSV）；只挑“人类可读名字”，
#       Disable/Enable/Utau/Title01 等 token 与说话人名一律不碰。
Z13_TRANSLATIONS = {
    'Wave Shout': '波动怒吼',
    'Heavy Flame': '重炎',
    'Earth Eject': '大地喷发',
    'Storm Out': '风暴爆发',
    'Judge of Dark': '暗之审判',
    'Idiot Brothers': '笨蛋兄弟',
    'Hero Chain!': '勇者连击！',
    'Brave Triangle': '勇者三角',
    'Goddess Academy Theme Song': '女神学园主题曲',
    'Brave Triangle 2': '勇者三角2',
    'All Star': '全明星',
    'Magic Storm': '魔法风暴',
    'Knight Dynamite': '骑士炸药',
    'Prison Break': '破狱',
    'Come on everyone!': '大家上！',
    'Sonic Boom Attack': '音爆攻击',
    'Hellfang': '地狱獠牙',
    'Spot Burst Shot': '定点爆破射击',
    'Satellite Laser': '卫星激光',
    'Beast Fang': '野兽獠牙',
    'Nanako Love Punch': '奈奈子爱心拳',
    'Oh-ho-ho-ho!': '哦呵呵呵！',
    'Immovable Sword': '不动剑',
    'Natural Born Devil': '天生恶魔',
    'Destruction Blow': '破坏重击',
    'Shadow Braver': '暗影勇者',
    'Backside of Period': '终焉之背',
    'Ultimate Karma Devil Slash': '究极业魔斩',
    'Liar!': '骗子！',
    'Legend of Hedgehog': '刺猬传说',
    'Ultimate Twist': '究极扭转',
    'Pink Hurricane': '粉色旋风',
    'Time Hole Burst': '时空洞爆发',
    'Devil Slash': '恶魔斩',
    'Soldier Reppa': '士兵连破',
    'Twin Spear': '双枪',
    'Tsubame Gaeshi': '燕返',
    'Crushing Strike of the War God': '战神碎击',
    'You should feel ashamed!': '你该感到羞耻！',
    'Evil Lord Wink Obliteration': '魔王眨眼歼灭',
    'Infinite Weapon Fall': '无限武器坠落',
    'Immovable Bright Divine Sword': '不动明王剑',
    'New Meteor': '新流星',
    'Swallow Reverse': '逆燕斩',
    'War God Chain Assault': '战神连袭',
    'Feel Shame!': '羞耻吧！',
    'Evil Lord Blink Obliteration': '魔王瞬灭',
    'Infinite Weapon Drop': '无限武器落下',
    'Immovable Myojin Sword': '不动明神剑',
    'Super New Meteor': '超新流星',
}
# 已有译文、只需同步副本的名字（不新增行）
Z13_SYNC_NAMES = (
    'Angel Ring', 'Gunshot', 'Summon Monster',
    'Water Stone', 'Fire Stone', 'Earth Stone', 'Wind Stone',
    'Golem Stone', 'Demon Stone', 'Nothing happened…',
)
# UI 缺译行（无可复用译文）：(blob, off, zh)
Z13_UI_ROWS = (
    (99, 16, '木剑+1'),
    (99, 56, '兼具'),
    (25, 62384, '材料：%s　＋　%s'),
    (25, 63056, '材料：%s　＋　%s'),
)
Z13_SCRIPT_COLS = {83: 288, 394: 288, 417: 288, 654: 288,
                   408: 288, 445: 288, 748: 288}
Z13_UI_OFFS = frozenset((bi, off) for bi, off, _z in Z13_UI_ROWS)


def _slot_span(starts, ob, f):
    import bisect
    i = bisect.bisect_right(starts, f)
    return (starts[i] - f) if i < len(starts) else (len(ob) - f)


def _z13_rows():
    """生成批次 B 的额外译表行（技能名全部副本 + UI 行）。"""
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if not (os.path.exists(en_path) and os.path.exists(ja_path)):
        return []
    E = [bytes(b) for b in s2a.Archive(en_path).blobs]
    J = [bytes(b) for b in s2a.Archive(ja_path).blobs]
    nm = _csv_name_map()
    mapping = dict(Z13_TRANSLATIONS)
    for s in Z13_SYNC_NAMES:
        if nm.get(s):
            mapping[s] = nm[s]
    starts = {}
    for bi, ob in enumerate(E):
        starts[bi] = [pos for pos, _f, _e in _iter_slots(ob)]
    out = []
    seen = set()
    rid = 910000

    def dec(t):
        try:
            return t.decode('cp932').strip()
        except Exception:
            return ''

    def add(bi, f, en_b, ja_b, zh):
        nonlocal rid
        if not zh or (bi, f) in seen:
            return False
        ob = E[bi]
        span = _slot_span(starts[bi], ob, f)
        # 只覆盖原字段本身（文本 + 终止符），绝不按“到下一槽”的整段清零，
        # 以免把定长记录里的二进制字段一起抹掉。
        sb = min(span, max(2, len(en_b) + 1))
        if sb <= 0:
            return False
        seen.add((bi, f))
        rid += 1
        out.append(dict(
            row_id=str(rid), blob_index=str(bi), offset=str(f),
            slot_bytes=str(sb), max_cn=str(sb // 2), len_en=str(len(en_b)),
            en=dec(en_b), ja=dec(ja_b), zh_3dm='', zh_new=zh,
        ))
        return True

    for en, zh in mapping.items():
        try:
            eb = en.encode('cp932')
        except Exception:
            continue
        for bi, ob in enumerate(E):
            # 只在该串真正出现的 blob 上扫
            if eb not in ob:
                continue
            for _pos, f, e in _iter_slots(ob):
                if ob[f:e] == eb:
                    jf = f
                    je = J[bi].find(b'\x00', jf)
                    add(bi, f, eb, J[bi][jf:je], zh)
    for bi, off, zh in Z13_UI_ROWS:
        ob = E[bi]
        f = off
        e = ob.find(b'\x00', f)
        if e < 0:
            continue
        je = J[bi].find(b'\x00', f)
        add(bi, f, ob[f:e], J[bi][f:je], zh)
    return _apply_extra_overrides(out)


def _z13_release_factory(mech_ja, partner_ja):
    base = _z12_release_factory(mech_ja, partner_ja)

    def extra(bi, off, ja_cmp):
        if (bi, off) in Z13_UI_OFFS:
            return True
        st = Z13_SCRIPT_COLS.get(bi)
        if st and (off - 16) % st == 28:
            return True
        return base(bi, off, ja_cmp)

    return extra


def do_apply_names_cn_batch_b_hash(exe_mode=None):
    """Z13：Z12 + 批次 B（武器合成/UI 缺译 + 伙伴/敌人技能名）。"""
    global _EXTRA_RELEASE, _EXTRA_ROWS
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    orig_blobs = None
    if os.path.exists(en_path):
        try:
            orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs]
        except Exception as e:
            print('  [名称副本] 母本读取失败：%r' % e)
    mech_ja = _mech_ja_names()
    partner_ja = _partner_ja_names()
    mech_ja -= partner_ja
    rows = _z11_partner_rows() + _z13_rows()
    extra_en = _z12_names_en(orig_blobs or [])
    names = _partner_en_names(orig_blobs) | extra_en | {
        s.encode('cp932') for s in list(Z13_TRANSLATIONS) + list(Z13_SYNC_NAMES)
    }
    print('  [Z13] 新增译表行 %d / 名字集合 %d（UI 行 %d）'
          % (len(rows), len(names), len(Z13_UI_ROWS)))
    _EXTRA_ROWS = rows
    _EXTRA_RELEASE = _z13_release_factory(mech_ja, partner_ja)
    try:
        stats = do_apply(text=True, sync_cscv=False, keep_collide=True,
                         skip_blobs=(128, 136, 317), consistent=False,
                         menu_exempt=True, ui_always=True,
                         slot_release=True, desc_release=True,
                         place=False, chap=False, song=False,
                         lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=True,
                         exe_mode=exe_mode)
    finally:
        _EXTRA_RELEASE = None
        _EXTRA_ROWS = None
    print('== 名称副本一致性补全 [Z13：R1 装备表+b391 / R2 开启] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998, 391}, multiline=True)
    print('== 键名列对齐（pos292 := pos0）==')
    align_skill_keycol(orig_blobs, en_path)
    print('== 同步 DLC01（Z13：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    print('== 名字副本补齐（伙伴 + 批次 A/B 名字，跳过键表）==')
    fill_name_copies(orig_blobs, en_path, names)
    print('== 方案A：重算名字哈希操作数（按最终写入字节）==')
    ja_blobs = None
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if os.path.exists(ja_path):
        try:
            ja_blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs]
        except Exception as e:
            print('  [操作数] 母本 LANG_JA 读取失败：%r' % e)
    recompute_name_operands(orig_blobs, en_path, ja_blobs=ja_blobs)
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! Z13 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_batch_b_hash(exe_mode=None):
    """Z13 包：staging 装机 → 输出 dist/Z13-batchB/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_batch_b_hash',
                      stage_name='package_stage_names_cn_batch_b_hash',
                      out_dir=paths.dist('Z13-batchB'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= Z14：职业/阵型/称号（2026-10-21） =================
# 关键发现：称号名在 b931 pos0 之外，还在多个 stride292 表的 pos32 有副本；
# 此前只翻 b931 导致“按名不可获得”。Z14 同时翻 b931 pos0 + 全部 pos32 副本。
# 职业 b128 pos4 / 阵型 b136 pos0 无哈希操作数，按普通名字处理（skip 仅剩 317）。
Z14_ENEMY_TRANSLATIONS = {
    'Chaos Wing': '混沌之翼',
    'No World': '无之世界',
    'Rejection of Fate': '拒绝命运',
    'Test Skill': '测试技能',
    'True Emperor of Destruction': '真·破坏皇帝',
    'Ultimate Karma Devil Slice Reversed!': '究极业魔斩·逆！',
    'Zero Dimension': '零之次元',
    'Curse Spell': '诅咒术',
    'Extreme Evil Slash': '极恶斩',
    'Jar Throw': '掷罐',
    'Magic Flare': '魔法闪光',
    'Physic Holy': '物理圣光',
    'Turning Swallow Slash': '转身燕斩',
    'Emperor of Destruction': '破坏皇帝',
    'Galactic Cannon': '银河炮',
    'Gustaf Launcher': '古斯塔夫发射器',
}
Z14_TITLE_FIX = {
    'Narrowly Averted': '千钧一发',
    'No!!': '不要！！',
    'Geezer!': '大叔！',
    'THE 3D': '三维',
}
Z14_SCRIPT_COLS = dict(Z13_SCRIPT_COLS)
Z14_SCRIPT_COLS.update({483: 288, 528: 288, 609: 288})


def _z14_rows():
    """生成职业/阵型/称号/新敌技名的额外译表行。"""
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    if not (os.path.exists(en_path) and os.path.exists(ja_path)):
        return []
    E = [bytes(b) for b in s2a.Archive(en_path).blobs]
    J = [bytes(b) for b in s2a.Archive(ja_path).blobs]
    nm = _csv_name_map()
    starts = {bi: [pos for pos, _f, _e in _iter_slots(ob)] for bi, ob in enumerate(E)}
    out, seen = [], set()
    rid = 920000

    def dec(t):
        try:
            return t.decode('cp932').strip()
        except Exception:
            return ''

    def add(bi, f, en_b, ja_b, zh, force_sb=None):
        nonlocal rid
        if not zh or (bi, f) in seen:
            return
        span = _slot_span(starts[bi], E[bi], f)
        sb = force_sb if force_sb else min(span, max(2, len(en_b) + 1))
        if sb <= 0:
            return
        seen.add((bi, f))
        rid += 1
        out.append(dict(
            row_id=str(rid), blob_index=str(bi), offset=str(f),
            slot_bytes=str(sb), max_cn=str(sb // 2), len_en=str(len(en_b)),
            en=dec(en_b), ja=dec(ja_b), zh_3dm='', zh_new=zh,
        ))

    # 职业 / 阵型 / 称号：只登记“源表本体”一行，副本由 fill_name_copies 补齐。
    # 这些表的名字字段容量是固定的，不能用 len(en)+1（否则“魔法师”会被裁成“魔法”）。
    # ★ 2026-10-22 修复：b128 名字容量必须 32（pos4→下一字段 pos36）；旧 64 会清零职业成长数值。
    #   b931 称号名容量必须 32（pos0→pos32）；旧 36 会清零称号条件/ID 字段。b136 的 64 正确。
    for bi, st, pos, cap_sb in ((128, 212, 4, 32), (136, 272, 0, 64), (931, 292, 0, 32)):
        n = struct.unpack_from('<I', E[bi], 8)[0]
        for r in range(n):
            base = 16 + r * st
            eb = E[bi][base + pos:base + pos + 64].split(b'\x00')[0]
            if not eb:
                continue
            s = dec(eb)
            zh = Z14_TITLE_FIX.get(s) or nm.get(s)
            if not zh:
                continue
            jb = J[bi][base + pos:base + pos + 64].split(b'\x00')[0]
            add(bi, base + pos, eb, jb, zh, force_sb=cap_sb)
    # 新增敌技名：所有整槽副本（脚本参数列）
    for s, zh in Z14_ENEMY_TRANSLATIONS.items():
        try:
            eb = s.encode('cp932')
        except Exception:
            continue
        for bi, ob in enumerate(E):
            if eb not in ob:
                continue
            for _p, f, e in _iter_slots(ob):
                if ob[f:e] == eb:
                    jf = f
                    je = J[bi].find(b'\x00', jf)
                    add(bi, f, eb, J[bi][jf:je], zh)
    return _apply_extra_overrides(out)


def _z14_release_factory(mech_ja, partner_ja, name_ja):
    base = _z13_release_factory(mech_ja, partner_ja)

    def extra(bi, off, ja_cmp):
        if display_release_hit(bi, off, ja_cmp):
            return True
        if bi == 128 and (off - 16) % 212 == 4:
            return True
        if bi == 136 and (off - 16) % 272 == 0:
            return True
        if bi == 931 and (off - 16) % 292 == 0:
            return True
        st = Z14_SCRIPT_COLS.get(bi)
        if st and (off - 16) % st == 28:
            return True
        if ja_cmp in name_ja:
            return True
        return base(bi, off, ja_cmp)

    return extra


def _equip_name_canon(orig_blobs, prod):
    """道具表规范名：EN 原串 -> 最终写入字节（优先 b147/357/736/998）。"""
    canon = {}
    for bi in EQUIP_BLOBS:
        ob = bytes(orig_blobs[bi])
        pb = prod[bi]
        st = struct.unpack_from('<I', ob, 4)[0]
        for r in range(struct.unpack_from('<I', ob, 8)[0]):
            base = 16 + r * st + 4
            oe = ob.find(b'\x00', base)
            if oe < 0:
                continue
            en = ob[base:oe]
            if not en or en in canon:
                continue
            pe = pb.find(b'\x00', base)
            fin = bytes(pb[base:pe])
            if not fin or fin == en:
                continue
            if b'<' in en and b'>' in en:
                continue
            if not en.strip(b'?'):
                continue
            if len(en) < 2:
                continue
            canon[en] = fin
    return canon


def _sync_item_copies(orig_blobs, prod, canon, foreign=False):
    """把 canon 里的道具名同步到 orig_blobs 对应 prod 的全部副本。

    foreign=True 用于 DLC01/LANG_EN：DLC 是独立档案，blob 编号与主 LANG 无关，
    因此不做称号/Q16/技能键列等“主 LANG 专用”守卫。
    返回 (整槽数, 嵌入数, 整槽容量不足, 嵌入容量不足)。
    """
    ct_whole, ct_recs, _ct_vals = load_chap_title_guard()
    q16 = None if foreign else _q16_lang_en_offsets('LANG_EN')
    skip_blobs = () if foreign else (128, 136, 317)
    n = skip = 0
    for bi, ob in enumerate(orig_blobs):
        if bi in skip_blobs or bytes(ob)[:4] != b'CSCV':
            continue    # 音频/图片等非文本资料不参与名字同步（2 字节名字易撞巧合字节）
        pb = prod[bi]
        for pos, f, e in _iter_slots(bytes(ob)):
            en = bytes(ob)[f:e]
            fin = canon.get(en)
            if not fin:
                continue
            if not foreign:
                st = struct.unpack_from('<I', ob, 4)[0] if ob[:4] == b'CSCV' else 0
                if st and chap_title_hit(ct_whole, ct_recs, bi, st,
                                         (f - 16) % st, (f - 16) // st):
                    continue
                if in_skill_key_col(bi, f):
                    continue
                if _q16_hit(q16, bi, pos, e):
                    continue
            ce = pb.find(b'\x00', f)
            if ce < 0:
                continue
            cur = bytes(pb[f:ce])
            if cur == fin:
                continue
            nx = ce
            while nx < len(pb) and pb[nx] == 0:
                nx += 1
            if len(fin) + 1 > nx - f:
                skip += 1
                continue
            pb[f:f + len(fin)] = fin
            pb[f + len(fin)] = 0
            for i in range(f + len(fin) + 1, max(ce, f + len(fin) + 1)):
                pb[i] = 0
            n += 1
    # ---- 嵌入副本：stride 152 关卡实体表 pos24 ----
    # 载具/坐骑名（Horse/Bike/Buggy/Boat/Dragon/Bamboo Stilts）位于若干 float 之后，
    # 前面没有 0x00 分隔（float -1.0 的尾字节 80 BF 与名字连成一个 run），
    # _iter_slots 会把前缀并入字符串，整槽匹配因此漏掉。引擎按 pos24 固定读取，
    # 名字必须与道具表终串一致，否则载具/NPC 不出现（龙、DLC Q78 船）。
    suf3 = {}
    for en in canon:
        if len(en) >= 3:
            suf3.setdefault(en[-3:], []).append(en)
    n_emb = skip_emb = 0
    for bi, ob in enumerate(orig_blobs):
        obv = bytes(ob)
        if bi in skip_blobs or obv[:4] != b'CSCV':
            continue
        st = struct.unpack_from('<I', obv, 4)[0]
        if st != 152:
            continue
        pb = prod[bi]
        for pos, f, e in _iter_slots(obv):
            run = obv[f:e]
            if len(run) < 4 or run[-3:] not in suf3:
                continue
            en = next((c for c in suf3[run[-3:]] if run.endswith(c)), None)
            if en is None or run == en:
                continue
            pre = run[:-len(en)]
            if not pre or pre[-1] < 0x80:
                continue
            i = e - len(en)
            if (i - 16) % st != 24:
                continue
            if pb[i:e] != en:
                continue
            fin = canon[en]
            nx = e
            while nx < len(pb) and pb[nx] == 0:
                nx += 1
            if len(fin) + 1 > nx - i:
                skip_emb += 1
                continue
            pb[i:i + len(fin)] = fin
            pb[i + len(fin)] = 0
            for j in range(i + len(fin) + 1, max(e, i + len(fin) + 1)):
                pb[j] = 0
            n_emb += 1
    return n, n_emb, skip, skip_emb


def fill_item_name_copies(orig_blobs, en_path, verbose=True, canon=None):
    """把装备/道具表（b147/357/736/998 pos4）的中文名同步到全库同名副本。

    宝箱/事件发放道具时按名字匹配；只翻道具表而不同步脚本参数列会导致“提示获得但
    背包没有”。本函数以道具表的最终字节为准，补齐所有整槽同名副本与
    stride152/pos24 嵌入副本。跳过：b128/b136/b317、称号/Q16、技能键列。
    返回 canon（EN 原串 -> 终串），供 DLC01 同步复用。
    """
    if not orig_blobs or not os.path.exists(en_path):
        return canon or {}
    arc = s2a.Archive(en_path)
    prod = [bytearray(bytes(b)) for b in arc.blobs]
    if canon is None:
        canon = _equip_name_canon(orig_blobs, prod)
    n, n_emb, skip, skip_emb = _sync_item_copies(orig_blobs, prod, canon)
    if n or n_emb:
        s2a.pack(en_path, arc.entries, [bytes(x) for x in prod])
    if verbose:
        print('  [道具名副本] 同步 %d 处%s%s'
              % (n, ('，嵌入副本 %d 处' % n_emb) if n_emb else '',
                 ('（容量不足 %d）' % (skip + skip_emb)) if (skip or skip_emb) else ''))
    return canon


def fill_dlc_item_name_copies(canon=None, verbose=True):
    """把主道具表的中文名同步到 DLC01/LANG_EN.s2a。

    DLC01 是独立档案，但关卡实体表（stride 152 pos24）同样按载具名查找
    （Q78「船」即此例）。主同步器只处理 res/LANG_EN.s2a，DLC 会被漏掉。
    以主 LANG 的道具表终串为准，同步 DLC 的整槽副本与 stride152/pos24 嵌入副本。
    """
    dlc_dir = os.path.join(BASE, 'DLC01')
    en = os.path.join(dlc_dir, 'LANG_EN.s2a')
    if not os.path.exists(en):
        return 0
    orig = en + dlc_lib.BAK_SUFFIX
    if not os.path.exists(orig):
        orig = en + '.bak'
    if not os.path.exists(orig):
        if verbose:
            print('  [DLC 道具名副本] 跳过：缺少 DLC01 原件备份')
        return 0
    if canon is None:
        mo = os.path.join(BASE, 'res', 'LANG_EN.s2a.bak')
        mp = os.path.join(BASE, 'res', 'LANG_EN.s2a')
        if not (os.path.exists(mo) and os.path.exists(mp)):
            if verbose:
                print('  [DLC 道具名副本] 跳过：缺少主 LANG_EN 原件/产物')
            return 0
        m_o = [bytes(x) for x in s2a.Archive(mo).blobs]
        m_p = [bytearray(bytes(x)) for x in s2a.Archive(mp).blobs]
        canon = _equip_name_canon(m_o, m_p)
    if not canon:
        return 0
    d_o = [bytes(x) for x in s2a.Archive(orig).blobs]
    arc = s2a.Archive(en)
    d_p = [bytearray(bytes(x)) for x in arc.blobs]
    n, n_emb, skip, skip_emb = _sync_item_copies(d_o, d_p, canon, foreign=True)
    if n or n_emb:
        s2a.pack(en, arc.entries, [bytes(x) for x in d_p])
    if verbose:
        print('  [DLC 道具名副本] 同步 %d 处%s%s'
              % (n, ('，嵌入副本 %d 处' % n_emb) if n_emb else '',
                 ('（容量不足 %d）' % (skip + skip_emb)) if (skip or skip_emb) else ''))
    return n + n_emb


def fill_enemy_name_copies(orig_blobs, en_path, verbose=True):
    """把 b407 敌名/Boss 表的终串同步到其余敌名/宝箱/Boss 名副本列。

    目标列（静态审计发现的残留英文副本）：
      b601 stride288 pos28；b734 stride660 pos4/40；
      b54 stride660 pos4；b555 stride660 pos4。
    只写“整槽仍等于英文原名”的槽，跳过容量不足者。
    """
    if not orig_blobs or not os.path.exists(en_path):
        return 0
    targets = {601: (288, {28}), 734: (660, {4, 40}),
               54: (660, {4}), 555: (660, {4})}
    arc = s2a.Archive(en_path)
    prod = [bytearray(bytes(b)) for b in arc.blobs]
    canon = {}
    ob = bytes(orig_blobs[407])
    pb = prod[407]
    st = struct.unpack_from('<I', ob, 4)[0]
    for r in range(struct.unpack_from('<I', ob, 8)[0]):
        base = 16 + r * st + 4
        oe = ob.find(b'\x00', base)
        if oe < 0:
            continue
        en = ob[base:oe]
        if not en or en in canon:
            continue
        pe = pb.find(b'\x00', base)
        fin = bytes(pb[base:pe])
        if fin and fin != en and not (b'<' in en and b'>' in en):
            canon[en] = fin
    n = skip = 0
    for bi, (tst, poss) in targets.items():
        if bi >= len(orig_blobs):
            continue
        ob = bytes(orig_blobs[bi])
        pb = prod[bi]
        for pos in poss:
            for r in range(struct.unpack_from('<I', ob, 8)[0]):
                f = 16 + r * tst + pos
                oe = ob.find(b'\x00', f)
                if oe < 0:
                    continue
                en = ob[f:oe]
                fin = canon.get(en)
                if not fin:
                    continue
                ce = pb.find(b'\x00', f)
                cur = bytes(pb[f:ce])
                if cur != en:
                    continue
                nx = ce
                while nx < len(pb) and pb[nx] == 0:
                    nx += 1
                if len(fin) + 1 > nx - f:
                    skip += 1
                    continue
                pb[f:f + len(fin)] = fin
                pb[f + len(fin)] = 0
                for i in range(f + len(fin) + 1, max(ce, f + len(fin) + 1)):
                    pb[i] = 0
                n += 1
    if n:
        s2a.pack(en_path, arc.entries, [bytes(x) for x in prod])
    if verbose:
        print('  [敌名副本] 同步 %d 处%s' % (n, '（容量不足 %d）' % skip if skip else ''))
    return n


def force_title_key_copies(orig_blobs, en_path, title_ok, verbose=True):
    """Z14：把称号名的 stride292/pos32 条件副本强制统一为 b931 pos0 的终串。

    只处理 (stride==292 且 pos==32) 的槽（称号取得条件/进度表），不碰台词与 pos160。
    """
    if not orig_blobs or not os.path.exists(en_path):
        return 0
    arc = s2a.Archive(en_path)
    prod = [bytearray(bytes(b)) for b in arc.blobs]
    q16 = _q16_lang_en_offsets('LANG_EN')
    canon = {}
    ob = bytes(orig_blobs[931])
    pb = prod[931]
    for _p, f, e in _iter_slots(ob):
        if (f - 16) % 292 != 0:
            continue
        pt, _ = _slot_text_at(bytes(pb), f)
        canon[ob[f:e]] = bytes(pt)
    n = skip = 0
    for bi, obb in enumerate(orig_blobs):
        st = struct.unpack_from('<I', obb, 4)[0] if obb[:4] == b'CSCV' else 0
        if st != 292:
            continue
        pbb = prod[bi]
        for pos, f, e in _iter_slots(obb):
            if (f - 16) % 292 != 32:
                continue
            ot = obb[f:e]
            enc = canon.get(ot)
            if not enc or _q16_hit(q16, bi, pos, e):
                continue
            pt, _ = _slot_text_at(bytes(pbb), f)
            if pt == enc:
                continue
            oe = pbb.find(b'\x00', f)
            if oe < 0:
                continue
            nx = oe
            while nx < len(pbb) and pbb[nx] == 0:
                nx += 1
            if len(enc) + 1 > nx - f:
                skip += 1
                continue
            pbb[f:f + len(enc)] = enc
            pbb[f + len(enc)] = 0
            for i in range(f + len(enc) + 1, nx):
                pbb[i] = 0
            n += 1
    if n:
        s2a.pack(en_path, arc.entries, [bytes(x) for x in prod])
    if verbose:
        print('  [称号条件] 统一 pos32 副本 %d 处%s'
              % (n, '（容量不足 %d）' % skip if skip else ''))
    return n


# 主角默认可编辑名字：b391 rec2/3/4 pos40（Yusha/Yushia/Yuja）与 b715 的示例名。
# 这些是存档名字的默认值；为保证旧存档在补丁更新后仍按原版 EN/JA 解码，强制保留原文。
PROTAGONIST_DEFAULT_SLOTS = (
    (391, 16 + 2 * 168 + 40),
    (391, 16 + 3 * 168 + 40),
    (391, 16 + 4 * 168 + 40),
    (715, 18272),
)


def restore_protagonist_defaults(orig_blobs, en_path, verbose=True):
    """把主角默认名槽位写回该文件自己的原版字节（不参与翻译/副本补齐）。"""
    if not orig_blobs or not os.path.exists(en_path):
        return 0
    arc = s2a.Archive(en_path)
    prod = [bytearray(bytes(b)) for b in arc.blobs]
    n = skip = 0
    for bi, off in PROTAGONIST_DEFAULT_SLOTS:
        ob = bytes(orig_blobs[bi])
        oe = ob.find(b'\x00', off)
        if oe < 0:
            skip += 1
            continue
        own = ob[off:oe]
        if not own:
            skip += 1
            continue
        pb = prod[bi]
        ce = pb.find(b'\x00', off)
        if ce < 0:
            skip += 1
            continue
        nx = ce
        while nx < len(pb) and pb[nx] == 0:
            nx += 1
        if off + len(own) + 1 > nx:
            skip += 1
            continue
        pb[off:off + len(own)] = own
        pb[off + len(own)] = 0
        for i in range(off + len(own) + 1, max(ce, off + len(own) + 1)):
            pb[i] = 0
        n += 1
    if n:
        s2a.pack(en_path, arc.entries, [bytes(x) for x in prod])
    if verbose:
        print('  [主角默认名] 还原原文 %d 处%s'
              % (n, '（跳过 %d）' % skip if skip else ''))
    return n


def do_apply_names_cn_jobs_titles_hash(exe_mode=None):
    """Z14：Z13 + 职业名/阵型名/称号名 + 新敌技名（同语言全副本一致）。"""
    global _EXTRA_RELEASE, _EXTRA_ROWS, _TITLE_RELEASE
    en_path = os.path.join(BASE, 'res', 'LANG_EN.s2a')
    ja_path = os.path.join(BASE, 'res', 'LANG_JA.s2a')
    orig_blobs = [bytes(b) for b in s2a.Archive(en_path).blobs] if os.path.exists(en_path) else None
    ja_blobs = [bytes(b) for b in s2a.Archive(ja_path).blobs] if os.path.exists(ja_path) else None
    mech_ja = _mech_ja_names()
    partner_ja = _partner_ja_names()
    mech_ja -= partner_ja
    # 职业/阵型/称号的日文名集合（用于 collide 放行）
    name_ja = set()
    if ja_blobs:
        for bi, st, pos in ((128, 212, 4), (136, 272, 0), (931, 292, 0)):
            n = struct.unpack_from('<I', ja_blobs[bi], 8)[0]
            for r in range(n):
                base = 16 + r * st
                t = ja_blobs[bi][base + pos:base + pos + 64].split(b'\x00')[0]
                try:
                    name_ja.add(t.decode('cp932').strip())
                except Exception:
                    pass
    rows = _z11_partner_rows() + _z13_rows() + _z14_rows()
    extra_en = _z12_names_en(orig_blobs or [])
    en_names = set(_partner_en_names(orig_blobs or [])) | extra_en
    en_names |= {s.encode('cp932') for s in list(Z13_TRANSLATIONS) + list(Z13_SYNC_NAMES)}
    en_names |= {s.encode('cp932') for s in Z14_ENEMY_TRANSLATIONS}
    en_names |= {s.encode('cp932') for s in Z14_TITLE_FIX}
    if orig_blobs:
        for bi, st, pos in ((128, 212, 4), (136, 272, 0), (931, 292, 0)):
            n = struct.unpack_from('<I', orig_blobs[bi], 8)[0]
            for r in range(n):
                base = 16 + r * st
                t = orig_blobs[bi][base + pos:base + pos + 64].split(b'\x00')[0]
                if t:
                    en_names.add(t)
    # 称号名本体放行（绕过 chap_title_guard）
    title_rel = set()
    if orig_blobs:
        n = struct.unpack_from('<I', orig_blobs[931], 8)[0]
        for r in range(n):
            title_rel.add((931, 16 + r * 292))
    print('  [Z14] 新增译表行 %d / 名字集合 %d / 称号放行 %d'
          % (len(rows), len(en_names), len(title_rel)))
    _EXTRA_ROWS = rows
    _EXTRA_RELEASE = _z14_release_factory(mech_ja, partner_ja, name_ja)
    _TITLE_RELEASE = title_rel
    try:
        stats = do_apply(text=True, sync_cscv=False, keep_collide=True,
                         skip_blobs=(317,), consistent=False,
                         menu_exempt=True, ui_always=True,
                         slot_release=True, desc_release=True,
                         place=False, chap=False, song=False,
                         lang_files=['res/LANG_EN.s2a'], propagate_dups=True, mirror=True,
                         exe_mode=exe_mode)
    finally:
        _EXTRA_RELEASE = None
        _EXTRA_ROWS = None
        _TITLE_RELEASE = None
    print('== 名称副本一致性补全 [Z14] ==')
    sync_name_replicas(orig_blobs, en_path,
                       single_slot_blob_allow={147, 357, 736, 998, 391}, multiline=True)
    print('== 键名列对齐（pos292 := pos0）==')
    align_skill_keycol(orig_blobs, en_path)
    print('== 同步 DLC01（Z14：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    print('== 名字副本补齐（职业/阵型/称号/伙伴/批次 A-B，跳过 b317）==')
    fill_name_copies(orig_blobs, en_path, en_names, skip_blobs=(317,), title_ok=title_rel)
    print('== 道具名副本同步（宝箱/事件按名发放）==')
    fill_item_name_copies(orig_blobs, en_path)
    print('== 敌名/Boss 名副本同步 ==')
    fill_enemy_name_copies(orig_blobs, en_path)
    print('== 称号条件副本统一（stride292 pos32）==')
    force_title_key_copies(orig_blobs, en_path, title_rel)
    print('== 主角默认名还原（Yusha/Yushia/Yuja 保持原版）==')
    restore_protagonist_defaults(orig_blobs, en_path)
    print('== 方案A：重算名字哈希操作数（按最终写入字节）==')
    recompute_name_operands(orig_blobs, en_path, ja_blobs=ja_blobs)
    if not verify_e1_isolation(expect_skill_key=False):
        raise SystemExit('!! Z14 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_jobs_titles_hash(exe_mode=None):
    """Z14 包：staging 装机 → 输出 dist/Z14-jobs-titles/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_jobs_titles_hash',
                      stage_name='package_stage_names_cn_jobs_titles_hash',
                      out_dir=paths.dist('Z14-jobs-titles'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def do_package_names_cn_reuse(exe_mode=None):
    """Z15 包：Z14 配方 + 同字复用原版日文汉字槽位（方案 B，重画简中字形）。

    复用字不再占用 1248+ 的新格；单字输出 dist/Z15-reuse-kanji/，不改 Z14。
    """
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_jobs_titles_hash',
                      stage_name='package_stage_names_cn_reuse',
                      out_dir=paths.dist('Z15-reuse-kanji'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def do_apply_names_cn_jobs_titles_norepl(exe_mode=None):
    """Z15 无词典实验：Z14 配方相同，但不套用 REPL（仍保留 HL 高亮补译）。"""
    set_apply_repl(False)
    try:
        return do_apply_names_cn_jobs_titles_hash(exe_mode=exe_mode)
    finally:
        set_apply_repl(True)


def do_package_names_cn_reuse_norepl(exe_mode=None):
    """Z15-norepl 包：不套用 replace_map REPL，输出 dist/Z15-reuse-kanji-norepl/。

    与 Z15 并存；用于对比“关掉术语/近义替换”后的实际文本与字库占用。
    """
    return do_package(exe_mode=exe_mode,
                      apply_cmd='apply_names_cn_jobs_titles_norepl',
                      stage_name='package_stage_names_cn_reuse_norepl',
                      out_dir=paths.dist('Z15-reuse-kanji-norepl'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'),
                      apply_repl=False)


def _apply_z17_video(out_dir):
    """把 Z17-video 中已翻译的 4 个视频合入 Z17（prologue/ragnarok/overture + MOV opening）。"""
    src_dir = paths.dist('Z17-video')
    src_lang = os.path.join(src_dir, 'res', 'LANG_EN.s2a')
    src_mov = os.path.join(src_dir, 'res', 'MOV.s2a')
    dst_lang = os.path.join(out_dir, 'res', 'LANG_EN.s2a')
    if not (os.path.exists(src_lang) and os.path.exists(dst_lang)):
        print('  [视频] 未找到 Z17-video 视频包或 Z17 LANG_EN，跳过视频合入')
        return
    import build_video
    specs = build_video.load_specs()
    src = s2a.Archive(src_lang)
    repl = {}
    kinds = []
    for kind, spec in specs.items():
        if spec.get('archive') != 'res/LANG_EN.s2a':
            continue
        h = int(spec['blob'], 16)
        i = src.hash_map().get(h)
        if i is None:
            print('  [视频] Z17-video 缺少 %s blob %08x，跳过' % (kind, h))
            continue
        repl[h] = bytes(src.blobs[i])
        kinds.append(kind)
    if repl:
        build_video._replace_blobs(dst_lang, repl)
    if os.path.exists(src_mov):
        shutil.copy2(src_mov, os.path.join(out_dir, 'res', 'MOV.s2a'))
        kinds.append('opening')
    print('  [视频] 已合入 Z17-video 视频：%s%s'
          % (' '.join('%s/%08x' % (k, int(specs[k]['blob'], 16)) for k in kinds),
             ' + res/MOV.s2a' if os.path.exists(src_mov) else ''))


def do_package_names_cn_reuse_z17(exe_mode=None):
    """Z17：Z14 配方 + 显示文本补全；并合入 Z17-video 的 4 个已翻译视频。"""
    out = paths.dist('Z17-display-fill')
    rc = do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_jobs_titles_hash',
                    stage_name='package_stage_names_cn_reuse_z17',
                    out_dir=out,
                    expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))
    _apply_z17_video(out)
    return rc


def do_package_names_cn_reuse_z18(exe_mode=None):
    """Z18：Z17 配方 + DLC01 战国大陆地名汉字化；并合入 4 个已翻译视频。"""
    out = paths.dist('Z18-dlc-place-names')
    rc = do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_jobs_titles_hash',
                    stage_name='package_stage_names_cn_reuse_z18',
                    out_dir=out,
                    expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))
    _apply_z17_video(out)
    return rc


def do_package_names_cn_reuse_z19(exe_mode=None):
    """Z19：Z18 配方 + proofread 分支的对话文本日文基准校对修订。"""
    out = paths.dist('Z19-proofread')
    rc = do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_jobs_titles_hash',
                    stage_name='package_stage_names_cn_reuse_z19',
                    out_dir=out,
                    expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))
    _apply_z17_video(out)
    return rc


def do_package_names_cn_reuse_z20(exe_mode=None):
    """Z20（试验）：Z19 配方 + 道具说明“避字”改写（避开描述渲染器错字：神/奇/饮）。

    仅用于实机验证“描述渲染器按码错位”的假设：改写后的说明若显示正常，
    说明避开坏字即可规避；若仍异常，说明问题不在具体字符而在槽位/渲染路径。
    """
    out = paths.dist('Z20-desc-dodge')
    rc = do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_jobs_titles_hash',
                    stage_name='package_stage_names_cn_reuse_z20',
                    out_dir=out,
                    expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))
    _apply_z17_video(out)
    return rc


def do_apply_names_cn_equip_only(exe_mode=None):
    """Z7 二分：只翻装备/道具表的【名字+说明】，技能表 b666 与武器表技能名副本保持英文。

    单变量设计（对照 E3）：
      · skip 掉 b666 → 技能显示名保持英文
      · 装备表不跳过 → 名字列（+4）翻中文
      · 但用 SLOT_BLOCK 封掉装备表的技能名副本列（记录内 168..268），
        使它们与 b666 pos0 的英文保持一致（避免制造新的不一致）
    """
    global _SLOT_BLOCK

    def block(bi, off):
        if bi not in EQUIP_BLOBS:
            return False
        r = (off - 16) % EQUIP_STRIDE
        return 168 <= r < 268

    _SLOT_BLOCK = block
    try:
        stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                         skip_blobs=(666, 128, 136, 317), consistent=False,
                         menu_exempt=True, ui_always=True,
                         slot_release=True, desc_release=True,
                         place=False, chap=False, song=False,
                         lang_files=['res/LANG_EN.s2a'], propagate_dups=False, mirror=False,
                         exe_mode=exe_mode)
    finally:
        _SLOT_BLOCK = None
    print('== 同步 DLC01（Z7：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    if not verify_e1_isolation():
        raise SystemExit('!! Z7 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_apply_names_cn_skill_only2(exe_mode=None):
    """Z6 二分：只翻技能表 b666 显示名 + 武器表里的技能名副本；装备/道具名保持英文。

    单变量设计（对照 E3）：
      · b666 不跳过 → 技能显示名翻中文（pos288~375 键列仍由 in_skill_key_col 保护）
      · 装备表名字列（+4..+36）用 SLOT_BLOCK 封掉 → 装备名保持英文
      · 装备表的技能名副本列（168..268）照常翻 → 与 b666 pos0 一致
    """
    global _SLOT_BLOCK

    def block(bi, off):
        if bi not in EQUIP_BLOBS:
            return False
        r = (off - 16) % EQUIP_STRIDE
        return 4 <= r < 36

    _SLOT_BLOCK = block
    try:
        stats = do_apply(text=True, sync_cscv=False, keep_collide=False,
                         skip_blobs=(128, 136, 317), consistent=False,
                         menu_exempt=True, ui_always=True,
                         slot_release=True, desc_release=True,
                         place=False, chap=False, song=False,
                         lang_files=['res/LANG_EN.s2a'], propagate_dups=False, mirror=False,
                         exe_mode=exe_mode)
    finally:
        _SLOT_BLOCK = None
    print('== 同步 DLC01（Z6：只写 DLC01/LANG_EN）==')
    refresh_dlc01(en_only=True)
    print('== Q16 键名槽位保护 ==')
    restore_q16_keys()
    if not verify_e1_isolation():
        raise SystemExit('!! Z6 隔离断言失败：LANG_JA/cscv 文本层出现非预期改动，中止')
    return stats


def do_package_names_cn_equip_only(exe_mode=None):
    """Z7 二分包：staging 装机 → 输出 dist/Z7-equip-only/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_equip_only',
                      stage_name='package_stage_names_cn_equip_only',
                      out_dir=paths.dist('Z7-equip-only'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def do_package_names_cn_skill_only2(exe_mode=None):
    """Z6 二分包：staging 装机 → 输出 dist/Z6-skill-only/。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_names_cn_skill_only2',
                      stage_name='package_stage_names_cn_skill_only2',
                      out_dir=paths.dist('Z6-skill-only2'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


# ================= ★ v2.68：完整补丁打包（package / package_install） =================
# 目标：以配置游戏目录里的【原版文件（优先 .bak，缺失时用同名当前文件）】为输入，
#   产出一份可直接覆盖游戏目录的完整补丁到 dist/。
#   dll 模式（默认）：dinput8.dll + hm2zh_patch.bin + res/*.s2a + DLC01/*.s2a
#   exe 模式：        HMH2.exe      + res/*.s2a + DLC01/*.s2a
# DLC01 仅在【配置目录里存在 DLC01 文件】时才纳入（未持有 DLC 的玩家没有） 。
#
# 【默认】package = 隔离打包：只读配置目录里的原版文件（优先 .bak，缺失时退回同名当前文件，
#   如干净原版目录 work/original），在 build/package_stage/ 里装机，
#   校验通过后复制到 dist/；**配置游戏目录逐字节不变**（不装机）。
# 【另】package_install = 旧的"就地装机"行为：直接对配置目录跑 apply_menu 再复制到 dist/
#   （会把游戏目录留在已汉化态）。exe 模式对应 package_exe / package_install_exe。
# 流程：① 校验母本依赖 ② 生成 staging（或就地装机）③ 逐文件确认「确实与原件不同」
#      （防止装机没生效时静默产出一份原版/半份补丁）④ 按相对路径复制进 dist/（不打 zip）
# 游戏目录取自 --game-dir / HMH2_GAME_DIR / config.local.json 的 game_dir。
PACKAGE_RES = ['res/LANG_JA.s2a', 'res/LANG_EN.s2a', 'res/texture.s2a', 'res/cscv.s2a']
PACKAGE_DLC = ['DLC01/LANG_JA.s2a', 'DLC01/LANG_EN.s2a']
PKG_STAGE_NAME = 'package_stage'   # 隔离打包的临时装机目录（落在 build/ 下）


def _sha(path, n=12):
    import hashlib
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()[:n]


def _orig_bak_name(rel):
    """该相对路径对应的"母本备份"文件名（DLC01 用独立后缀，其余用 .bak）。"""
    return rel + (dlc_lib.BAK_SUFFIX if rel.startswith('DLC01/') else '.bak')


def _pkg_origin_sources():
    """只在配置目录里读取的原版源：优先 `<rel>.bak`，缺失时退回同名当前文件。
    适用于"干净原版目录"（如 work/original，只有原版文件、没有 .bak，且本命令不写它）。
    返回 (src, missing, uses_current, has_dlc)。"""
    has_dlc = all(os.path.exists(os.path.join(BASE, _orig_bak_name(rel))) or
                  os.path.exists(os.path.join(BASE, rel)) for rel in PACKAGE_DLC)
    rels = ['HMH2.exe'] + PACKAGE_RES + (PACKAGE_DLC if has_dlc else [])
    src, missing, uses_current = {}, [], []
    for rel in rels:
        bak = os.path.join(BASE, _orig_bak_name(rel))
        cur = os.path.join(BASE, rel)
        if os.path.exists(bak):
            src[rel] = bak
        elif os.path.exists(cur):
            src[rel] = cur
            uses_current.append(rel)
        else:
            missing.append(rel)
    return src, missing, uses_current, has_dlc


def export_review_view(apply_repl=True):
    """打包后刷新译者校对视图（translator-view/）。

    【强制规则】译表或汉化脚本有任何改动，打包完成后必须导出一次最新译文；
    否则 translator-view 仍是旧快照，下次「导入校对」会把旧文本整体回写译表。
    （2026-10-20 事故：旧视图回写导致 1,607 行术语/断句修复被覆盖。）

    apply_repl=False：导出“不套用 REPL”的视图，与 Z15-norepl 包保持一致。
    """
    import subprocess
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'export_review.py')
    print('== 刷新译者校对视图（translator-view）==')
    sys.stdout.flush()
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['HMH2_APPLY_REPL'] = '1' if apply_repl else '0'
    rc = subprocess.call([sys.executable, script], env=env)
    if rc != 0:
        print('!! 校对视图导出失败（退出码 %s）：dist/ 已生成，但视图仍是旧快照' % rc)
        print('   请立即手动运行: python tools/export_review.py')
        print('   在导出成功之前，不要运行「汉化-导入校对.bat」，否则旧视图会回写译表。')
        raise SystemExit(1)
    print('校对视图已刷新：%s' % os.path.join(WORK, 'translator-view'))


def do_package(exe_mode=None, apply_cmd=None, stage_name=None, out_dir=None,
               expect_same=(), apply_repl=True):
    """完整补丁打包（默认·隔离模式）：只读配置目录母本 → 在 staging 装机 → 复制到 dist/。
    配置游戏目录逐字节不变（不装机）。就地装机版见 do_package_install。

    可选参数（供 E1 等变体复用）：
      apply_cmd  : staging 里要跑的装机子命令（默认 apply_menu / apply_menu_exe）
      stage_name : staging 目录名（默认 package_stage）
      out_dir    : 打包输出目录（默认 dist/；E1 用 dist/E1-lang-en-only/）
      expect_same: 必须与母本【逐字节相同】的相对路径集合（默认空 = 全部必须不同）
    """
    em = (exe_mode or EXE_MODE).lower()
    out_dir = out_dir or paths.DIST_DIR
    expect_same = set(expect_same)
    print('== 完整补丁打包·隔离模式（%s 模式，不装机）==' % em)
    print('  母本来源    : %s（只读，不改）' % BASE)
    print('  输出目录    : %s' % out_dir)

    # ① 前置校验：缺原版文件就明确失败，绝不静默产出半份补丁
    src, missing, uses_current, has_dlc = _pkg_origin_sources()
    if missing:
        print('!! 打包中止：配置游戏目录缺少原版文件（既无 .bak 也无同名当前文件）')
        for rel in missing:
            print('   - %s' % rel)
        print('   请确认 game_dir 指向含原版文件的目录，或先运行 revert 生成 .bak')
        raise SystemExit(1)
    if uses_current:
        print('  [母本] 以下文件无 .bak 备份，改用当前文件作为原版源（只读，不写入）:')
        for rel in uses_current:
            print('   - %s' % rel)
    if has_dlc:
        print('  [DLC01] 检出 DLC01 原版文件，纳入补丁')
    else:
        print('  [DLC01] 未检出 DLC01 原版文件，本次补丁不含 DLC01')

    # ② 用母本备份重建 staging（同时充当"当前文件"与"原件备份"）
    stage = paths.build(stage_name or PKG_STAGE_NAME)
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    for rel, p in src.items():
        dst = os.path.join(stage, *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
        shutil.copy2(p, os.path.join(stage, *_orig_bak_name(rel).split('/')))
    print('  staging     : %s（已由母本重建）' % stage)

    # ③ 在 staging 里跑生产装机（子进程 + HMH2_GAME_DIR 覆盖，绝不影响配置目录）
    import subprocess
    env = os.environ.copy()
    env['HMH2_GAME_DIR'] = stage
    env['HMH2_EXE_MODE'] = em
    env['PYTHONIOENCODING'] = 'utf-8'
    env['HMH2_APPLY_REPL'] = '1' if apply_repl else '0'
    sys.stdout.flush()
    rc = subprocess.call([sys.executable, os.path.abspath(__file__),
                          apply_cmd or ('apply_menu' if em == 'dll' else 'apply_menu_exe')], env=env)
    if rc != 0:
        print('!! 打包中止：staging 装机失败（退出码 %s），dist/ 未写入' % rc)
        raise SystemExit(1)

    # ④ 校验：默认每个文件必须与 staging 里的母本不同（防装机未生效）；
    #    expect_same 里的文件反过来必须【逐字节相同】（E1：LANG_JA 保持原版）
    manifest = (['HMH2.exe'] if em == 'exe' else list(PROXY_FILES)) + PACKAGE_RES
    if has_dlc:
        manifest += PACKAGE_DLC
    bad, table = [], []
    for rel in manifest:
        p = os.path.join(stage, *rel.split('/'))
        if not os.path.exists(p):
            bad.append('%s 不存在（未生成）' % rel)
            continue
        bak = os.path.join(stage, *_orig_bak_name(rel).split('/'))
        tag = '生成物'
        if os.path.exists(bak):
            same = _sha(p, 64) == _sha(bak, 64)
            if rel in expect_same:
                if not same:
                    bad.append('%s 应保持原版（逐字节相同）却已被改动' % rel)
                    continue
                tag = '与原版一致(%s)' % _sha(bak)
            else:
                if same:
                    bad.append('%s 与原版完全相同（装机未生效）' % rel)
                    continue
                tag = '已改(原版 %s)' % _sha(bak)
        table.append((rel, os.path.getsize(p), _sha(p), tag))
    if bad:
        print('!! 打包中止：以下文件不合格，dist/ 未写入')
        for b in bad:
            print('   - %s' % b)
        raise SystemExit(1)

    # ⑤ 复制到输出目录（按相对路径建目录）
    print('== 写入输出目录 ==')
    for rel, sz, h, tag in table:
        dst = os.path.join(out_dir, *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(stage, *rel.split('/')), dst)
        print('  %-20s %9d B  sha256:%s  %s' % (rel, sz, h, tag))
    print('打包完成：%d 个文件已放入 %s（未打 zip；配置游戏目录未改动）'
          % (len(table), out_dir))
    print('提示：staging 暂存于 %s（可删）；输出目录中不属于本次补丁的旧文件不会被删除。' % stage)

    # ⑥ 强制刷新译者校对视图：避免 translator-view 停留在旧快照，下次导入时整体回写译表
    export_review_view(apply_repl=apply_repl)


def do_package_lang_en_only(exe_mode=None):
    """E1 隔离实验打包：staging 里只写 LANG_EN 装机 → 输出 dist/E1-lang-en-only/。
    LANG_JA（含 DLC01 的）必须与母本逐字节相同，故列入 expect_same。"""
    return do_package(exe_mode=exe_mode, apply_cmd='apply_lang_en_only',
                      stage_name='package_stage_e1',
                      out_dir=paths.dist('E1-lang-en-only'),
                      expect_same=('res/LANG_JA.s2a', 'DLC01/LANG_JA.s2a'))


def do_package_install(exe_mode=None):
    """完整补丁打包（就地装机版）：对配置目录装机 → 校验「已改」→ 复制到 dist/。"""
    em = (exe_mode or EXE_MODE).lower()
    # DLC01 仅在【确实存在原件】时才纳入补丁（未持有 DLC 的玩家没有 DLC01/LANG_*.s2a）
    has_dlc = all(os.path.exists(os.path.join(BASE, rel)) for rel in PACKAGE_DLC)
    manifest = (['HMH2.exe'] if em == 'exe' else list(PROXY_FILES)) + PACKAGE_RES
    if has_dlc:
        manifest += PACKAGE_DLC
    # 文件 -> 其原件备份（用于证明"确实被改了"）；dinput8.dll / hm2zh_patch.bin 是生成物，无原件
    orig = dict((rel, rel + '.bak') for rel in PACKAGE_RES)
    if has_dlc:
        orig.update(dict((rel, rel + dlc_lib.BAK_SUFFIX) for rel in PACKAGE_DLC))

    print('== 完整补丁打包（%s 模式）==' % em)
    print('  输入游戏目录: %s' % BASE)
    print('  输出目录    : %s' % paths.DIST_DIR)

    # ① 前置校验：缺原版输入就明确失败，绝不静默产出半份补丁
    #   注：res/*.s2a 与 HMH2.exe 的 .bak 由 do_apply 自动建（从当前文件）；
    #       DLC01 的原件备份由 refresh_dlc01 在【确实存在 DLC01 原件】时自动生成，故均不预检。
    missing = []
    if not os.path.exists(EXE):
        missing.append('HMH2.exe（缺失）')
    for rel in PACKAGE_RES + (PACKAGE_DLC if has_dlc else []):
        if not os.path.exists(os.path.join(BASE, rel)):
            missing.append('%s（缺失）' % rel)
    if missing:
        print('!! 打包中止：游戏目录缺少下列文件')
        for m in missing:
            print('   - %s' % m)
        print('   请先确认游戏为原版（Steam「验证游戏文件完整性」）')
        raise SystemExit(1)
    if has_dlc:
        print('  [DLC01] 检出 DLC01 原件，纳入补丁（原件备份缺失时将自动生成）')
    else:
        print('  [DLC01] 未检出 DLC01 原件（%s），本次补丁不含 DLC01' % '、'.join(PACKAGE_DLC))

    # ② 生产装机（装机 + 同步 DLC01 + Q16 键名保护）；refresh_dlc01 会自动补出 DLC01 原件备份
    do_apply_menu(exe_mode=em)

    # ③ 校验：除生成物外，每个文件必须与原版不同，否则装机未生效
    bad, table = [], []
    for rel in manifest:
        p = os.path.join(BASE, rel)
        if not os.path.exists(p):
            bad.append('%s 不存在（未生成）' % rel)
            continue
        tag = '生成物'
        if rel in orig:
            op = os.path.join(BASE, orig[rel])
            if not os.path.exists(op):
                bad.append('%s 缺少原件备份（%s），无法校验' % (rel, orig[rel]))
                continue
            if _sha(p, 64) == _sha(op, 64):
                bad.append('%s 与原版完全相同（装机未生效）' % rel)
                continue
            tag = '已改(原版 %s)' % _sha(op)
        table.append((rel, os.path.getsize(p), _sha(p), tag))
    if bad:
        print('!! 打包中止：以下文件不合格，dist/ 未写入')
        for b in bad:
            print('   - %s' % b)
        raise SystemExit(1)

    # ④ 复制到 dist/（按相对路径建目录）
    print('== 写入 dist ==')
    for rel, sz, h, tag in table:
        dst = paths.dist(*rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(BASE, rel), dst)
        print('  %-20s %9d B  sha256:%s  %s' % (rel, sz, h, tag))
    print('打包完成：%d 个文件已放入 %s（未打 zip）' % (len(table), paths.DIST_DIR))
    print('提示：dist 中不属于本次补丁的旧文件（如历史 zip）不会被删除。')

    # ⑤ 强制刷新译者校对视图（规则同 do_package）
    export_review_view()


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
     # v2.68：完整补丁打包。默认 package = 隔离打包（不装机，只出 dist）；
     #   package_install / package_install_exe = 旧的就地装机版。
     'package': do_package,
     'package_exe': lambda: do_package(exe_mode='exe'),
     # E1 隔离实验：只写 LANG_EN 装机 / 打包到 dist/E1-lang-en-only/
     'apply_lang_en_only': do_apply_lang_en_only,
     'package_lang_en_only': do_package_lang_en_only,
     # E2 镜像实验：照抄官方 EN 的改动集合（去掉护栏，仍只写 LANG_EN）
     'apply_lang_en_mirror': do_apply_lang_en_mirror,
     'package_lang_en_mirror': do_package_lang_en_mirror,
     # E3 可用包：LANG_EN 隔离 + 机制名保持该文件原版英文，其余中文（生产护栏配方）
     'apply_lang_en_names_en': do_apply_lang_en_names_en,
     'package_lang_en_names_en': do_package_lang_en_names_en,
     # 稳定版备份包：E3 配方，独立输出 dist/stable-names-en/（不影响默认 dist）
     'package_stable_names': do_package_stable_names,
     'apply_lang_ja_names_ja': do_apply_lang_ja_names_ja,
     'package_lang_ja_names_ja': do_package_lang_ja_names_ja,
     # HEAD(9d8299b) 生产配方复现包（双侧写入 + cscv 同步 + place/chap/song）
     'package_head': do_package_head,
     # Z1 names-cn 实验：翻 b666 技能名 + 装备表名（propagate_dups 保链），隔离只写 LANG_EN
     'apply_names_cn': do_apply_names_cn,
     'package_names_cn': do_package_names_cn,
     # Z3/Z4 二分实验：拆分 Z1 的两条名称副本补全规则（R1 限装备表 / R2 开关）
     'apply_names_cn_skill_only': do_apply_names_cn_skill_only,
     'package_names_cn_skill_only': do_package_names_cn_skill_only,
     'apply_names_cn_skill_loadout': do_apply_names_cn_skill_loadout,
     'package_names_cn_skill_loadout': do_package_names_cn_skill_loadout,
     'apply_names_cn_skill_loadout_ja': do_apply_names_cn_skill_loadout_ja,
     'package_names_cn_skill_loadout_ja': do_package_names_cn_skill_loadout_ja,
     'apply_names_cn_equip_only': do_apply_names_cn_equip_only,
     'package_names_cn_equip_only': do_package_names_cn_equip_only,
     'apply_names_cn_keycol': do_apply_names_cn_keycol,
     'package_names_cn_keycol': do_package_names_cn_keycol,
     # Z10 方案A：Z9（键列中文）+ 重算名字哈希操作数
     'apply_names_cn_keycol_hash': do_apply_names_cn_keycol_hash,
     'package_names_cn_keycol_hash': do_package_names_cn_keycol_hash,
     # Z10b 判别：stable 其余 collide 保留 + 仅机制名中文 + 操作数重算
     'apply_names_cn_mech_hash': do_apply_names_cn_mech_hash,
     'package_names_cn_mech_hash': do_package_names_cn_mech_hash,
     # Z11：Z10b + 伙伴名/复合键 + 操作数重算
     'apply_names_cn_partner_hash': do_apply_names_cn_partner_hash,
     'package_names_cn_partner_hash': do_package_names_cn_partner_hash,
     # Z12：Z11 + 批次 A 显示名（敌名/Boss/宝箱/音乐/地图 UI）
     'apply_names_cn_display_hash': do_apply_names_cn_display_hash,
     'package_names_cn_display_hash': do_package_names_cn_display_hash,
     # Z13：Z12 + 批次 B（UI 缺译 + 伙伴/敌人技能名）
     'apply_names_cn_batch_b_hash': do_apply_names_cn_batch_b_hash,
     'package_names_cn_batch_b_hash': do_package_names_cn_batch_b_hash,
     # Z14：Z13 + 职业/阵型/称号 + 新敌技名
     'apply_names_cn_jobs_titles_hash': do_apply_names_cn_jobs_titles_hash,
     'package_names_cn_jobs_titles_hash': do_package_names_cn_jobs_titles_hash,
     # Z15：同字复用原版日文汉字槽位（方案 B）
     'package_names_cn_reuse': do_package_names_cn_reuse,
     # Z15 无词典实验（只保留 HL；用于对比）
     'apply_names_cn_jobs_titles_norepl': do_apply_names_cn_jobs_titles_norepl,
     'package_names_cn_reuse_norepl': do_package_names_cn_reuse_norepl,
     # Z17：显示文本补全 + 合入 Z17-video 的 4 个视频
     'package_names_cn_reuse_z17': do_package_names_cn_reuse_z17,
     # Z18：Z17 + DLC01 战国大陆地名汉字化
     'package_names_cn_reuse_z18': do_package_names_cn_reuse_z18,
     # Z19：Z18 + 对话文本日文基准校对修订
     'package_names_cn_reuse_z19': do_package_names_cn_reuse_z19,
     # Z20（试验）：Z19 + 道具说明避字改写（避开神/奇/饮），输出 dist/Z20-desc-dodge
     'package_names_cn_reuse_z20': do_package_names_cn_reuse_z20,
     'apply_names_cn_skill_only2': do_apply_names_cn_skill_only2,
     'package_names_cn_skill_only2': do_package_names_cn_skill_only2,
     'package_install': do_package_install,
     'package_install_exe': lambda: do_package_install(exe_mode='exe'),
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
