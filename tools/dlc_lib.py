# -*- coding: utf-8 -*-
"""DLC01 汉化公共库（只读工具集 + 编码/容量口径）。

DLC01/LANG_JA.s2a 与 LANG_EN.s2a 结构（实测）：
  - S2A 归档，102 个 blob，JA/EN 逐 blob 尺寸镜像（同 blob 同 offset 同字段）
  - 每个 blob = CSCV 定长记录表：头 16B = b'CSCV' + u32 stride + u32 n + 0xffffffff
  - 424-stride 家族字段位置（记录内相对偏移，实测）：
      24  = 脚本/标记字段（如 timestop=1，ASCII，不翻）
      92  = 短名 / 选项名
      124 = 名字 / 数值
      260 = 命令 / 动作名（村を出る / はなす）
      292 = 对话文本（槽长 132B）
    记录末 = 424
  - 其他 stride（152/196/288/292）家族另有布局，一律用"到同记录下一个占用字段"实测法算容量。

容量口径（保守）：cap = 同记录内"下一个被占用字段起点" − 本字段起点；无则到记录末。
  译文编码字节数必须 <= cap-1（留 1 字节 0x00 终止符）。
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import s2a

DLC = paths.game('DLC01')
P_JA = os.path.join(DLC, 'LANG_JA.s2a')
P_EN = os.path.join(DLC, 'LANG_EN.s2a')
P_RES = os.path.join(DLC, 'res.s2a')
BAK_SUFFIX = '.bak_dlc01_20260913'

# 名字键表嫌疑整表不翻（审计结论）
SKIP_BLOBS = {4, 36, 45, 76, 97}


def extract_strings(b, minlen=2):
    res = []
    pos = 0
    for part in bytes(b).split(b'\x00'):
        if len(part) >= minlen:
            try:
                s = part.decode('cp932')
            except Exception:
                s = None
            if s is not None:
                ok, kinds = True, 0
                for ch in s:
                    o = ord(ch)
                    if o < 0x20:
                        ok = False
                        break
                    if (('\u3040' <= ch <= '\u30ff') or ('\u4e00' <= ch <= '\u9fff')
                            or ('\uff61' <= ch <= '\uff9f')
                            or (ch.isascii() and ch.isalnum())):
                        kinds += 1
                if ok and kinds * 2 >= len(s):
                    res.append((pos, s))
        pos += len(part) + 1
    return res


def cscv_header(b):
    b = bytes(b)
    if b[:4] != b'CSCV':
        return None
    return int.from_bytes(b[4:8], 'little'), int.from_bytes(b[8:12], 'little')


def is_jp(s):
    for c in s:
        if ('\u3040' <= c <= '\u30ff') or ('\u4e00' <= c <= '\u9fff') or ('\uff61' <= c <= '\uff9f'):
            return True
    return False


def field_slots(b):
    """返回 [(off, pos, s, cap)]，cap=到同记录下一个占用字段(或记录末)的距离。

    ⭐ 前导 0xFF 标记（CP932 解出来是 \\uf8f3 串）：字段形如 ff ff ff ff | 文本 | 00，
    真正的文本从标记之后开始。这里统一剥掉标记并把 off/cap 前移，
    使 off 指向**文本起点**（与主译表 CSV 的偏移口径一致）。
    """
    h = cscv_header(b)
    if not h:
        return []
    stride, n = h
    strs = extract_strings(b)
    recs = {}
    for off, s in strs:
        recs.setdefault((off - 16) // stride, []).append(((off - 16) % stride, off, s))
    out = []
    for r, items in recs.items():
        items.sort()
        for k, (pos, off, s) in enumerate(items):
            nxt = items[k + 1][0] if k + 1 < len(items) else stride
            nff = 0
            while nff < len(s) and s[nff] == '\uf8f3':
                nff += 1
            out.append((off + nff, pos + nff, s[nff:], (nxt - pos) - nff))
    out.sort()
    return out


def enc_len(s):
    """按双字节口径估算编码字节数（实际写入用 encode_text）。"""
    return sum(1 if ord(c) < 0x80 else 2 for c in s)


def segs_lf(b, minlen=2):
    """所有 \\x00 分界段（允许 \\n 等多行控制符），返回 [(off, s)]。
    用于捞回被 extract_strings 的"控制符"判定漏掉的多行台词。"""
    out = []
    pos = 0
    for part in bytes(b).split(b'\x00'):
        off = pos
        pos += len(part) + 1
        if len(part) < minlen:
            continue
        try:
            s = part.decode('cp932')
        except Exception:
            continue
        ok = True
        for ch in s:
            if ord(ch) < 0x20 and ch not in ('\n', '\v', '\f'):
                ok = False
                break
        if ok:
            out.append((off, s))
    return out


def text_len(b, off):
    """从 off 起"像文本"的连续字节长度：ASCII 可见字符 / 换行 / CP932 双字节。
    与 build_cn.read_run 同口径（允许 \\n，用于多行台词）。"""
    j, n = off, len(b)
    while j < n:
        c = b[j]
        if 0x20 <= c <= 0x7E or c in (0x0A, 0x0B, 0x0C):
            j += 1
        elif 0x81 <= c <= 0xFE and j + 1 < n:
            try:
                b[j:j + 2].decode('cp932')
            except Exception:
                break
            j += 2
        else:
            break
    return j - off


def field_text_end(b, off):
    """本字段原文的结束位置（含那个 \\x00 终止符，若有）。无文本则返回 off。"""
    tl = text_len(b, off)
    if tl and off + tl < len(b) and b[off + tl] == 0:
        return off + tl + 1
    return off + tl


def field_limit(b, off, cap):
    """本字段在文件 b 里可安全写入的右端（不含）：
    原文结束之后遇到的第一个非零字节（记录 ID / 分隔标记 / 下一字段）。"""
    start = field_text_end(b, off)
    end = off + cap
    seg = b[start:end]
    k = next((i for i, x in enumerate(seg) if x != 0), len(seg))
    return start + k


def make_decoder(cmap, native):
    """建立 装机字节 -> 真实字符 的反查表。

    ⭐ 关键：中文是写进"载体码"的（cmap[char] = 专属 CP932 码），
    直接把装机字节按 cp932 解码会得到别的字 —— 必须用 cmap 反查。
    """
    rev = {}
    for ch, code in cmap.items():
        rev[bytes(code)] = ch
    for ch in native:
        try:
            rev[ch.encode('cp932')] = ch
        except Exception:
            pass
    return rev


def decode_installed(b, rev):
    """按 反查表 解码装机字节（回退 cp932）。"""
    out = []
    i, n = 0, len(b)
    while i < n:
        c = b[i]
        if c < 0x80:
            out.append(chr(c)); i += 1; continue
        if i + 1 < n and bytes(b[i:i + 2]) in rev:
            out.append(rev[bytes(b[i:i + 2])]); i += 2; continue
        try:
            out.append(b[i:i + 2].decode('cp932')); i += 2
        except Exception:
            out.append('?'); i += 1
    return ''.join(out)
