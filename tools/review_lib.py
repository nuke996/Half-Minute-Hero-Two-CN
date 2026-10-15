# -*- coding: utf-8 -*-
"""面向译者的校对文件（translator-view）导出/导入共用工具。

职责：
  - 原版文件定位：优先 `<rel>.bak`，缺失时退回同名当前文件（干净原版目录）
  - 隔离舞台：把原版 LANG/cscv 复制成 `*.bak` 到 `build/review_stage/`，
    供 build_cn 的 dry_run 判定与容量计算复用（只读，绝不写游戏目录）
  - 容量口径（与 build_cn / dlc_apply 一致）：
      单行槽   = text_v2.csv 的 slot_bytes（字节上限）
      多行字段 = 到字段结束/下一占用字节的距离 - 1（字节上限）
      DLC 字段 = field_limit - off（字节上限，JA/EN 取小）

单位约定：`cap_bytes` 为字节上限；`cap` 为折算的"汉字数"（仅给译者目测用）。
"""
import csv
import json
import os
import shutil
import sys

import paths

_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

RES_ORIG = ['res/LANG_JA.s2a', 'res/LANG_EN.s2a', 'res/cscv.s2a']
ML_MAP = 'ml_fin_map.tsv'
DLC_BAK = '.bak_dlc01_20260913'


def orig_path(rel):
    """配置目录里该相对路径的"原版"文件：优先 <rel>.bak，缺失退回 <rel> 本身。"""
    base = paths.GAME_DIR
    for cand in (rel + '.bak', rel):
        p = os.path.join(base, *cand.split('/'))
        if os.path.exists(p):
            return p
    return None


def dlc_orig_path(fname):
    p = os.path.join(paths.GAME_DIR, 'DLC01', fname)
    return p + DLC_BAK if os.path.exists(p + DLC_BAK) else (p if os.path.exists(p) else None)


def ensure_stage():
    """重建 build/review_stage（原版 LANG/cscv 的 *.bak 拷贝）。
    返回 (stage or None, missing[list])。缺原版文件时返回 None，调用方降级处理。"""
    stage = paths.build('review_stage')
    missing = []
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    for rel in RES_ORIG:
        src = orig_path(rel)
        if not src:
            missing.append(rel)
            continue
        dst = os.path.join(stage, *rel.split('/')) + '.bak'
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return (None if missing else stage), missing


def byte_est(s):
    """编码字节数估算（与 build_cn.encode_text 同口径）：ASCII=1，其余=2。
    未覆盖字实际编码成 '?'（1 字节），此处仍按 2 计 —— 偏保守（只会更严格）。"""
    return sum(1 if ord(c) < 0x80 else 2 for c in s)


def load_rows():
    """主译表全部行（顺序即 row_id 顺序）。"""
    p = paths.data('text_v2.csv')
    return list(csv.DictReader(open(p, encoding='utf-8', newline='')))


def row_caps(rows):
    """{row_id: (slot_bytes, max_cn)}"""
    out = {}
    for r in rows:
        try:
            out[r['row_id']] = (int(r['slot_bytes']), int(r['max_cn']))
        except Exception:
            pass
    return out


def _ml_key(tsv_en):
    """ml_fin_map.tsv 的 en 列用字面 `\\n` 转义；ml_zh_fields.json 的键用真实换行。"""
    return tsv_en.replace('\\n', '\n')


def ml_meta(stage):
    """{en键: {'blob','off','cap_bytes','ja'}} —— 多行整字段。
    需要 stage（原版 LANG_JA/LANG_EN *.bak）；否则返回 {}。"""
    import s2a
    import build_cn as B
    mp = paths.data(ML_MAP)
    if not os.path.exists(mp) or not stage:
        return {}
    ja_a = s2a.Archive(os.path.join(stage, 'res/LANG_JA.s2a.bak'))
    en_a = s2a.Archive(os.path.join(stage, 'res/LANG_EN.s2a.bak'))
    out = {}
    with open(mp, encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            try:
                bi, off = int(row['blob']), int(row['off'])
            except Exception:
                continue
            if bi >= len(ja_a.blobs) or bi >= len(en_a.blobs):
                continue
            jb = bytes(ja_a.blobs[bi])
            eb = bytes(en_a.blobs[bi])
            if off >= len(jb):
                continue
            cap = min(B.field_end(jb, off), B.field_end(eb, off)) - off - 1
            seg = jb[off:].split(b'\x00')[0]
            try:
                ja = seg.decode('cp932')
            except Exception:
                ja = ''
            out[_ml_key(row['en'])] = {'blob': bi, 'off': off,
                                       'cap_bytes': cap, 'ja': ja}
    return out


def dlc_caps():
    """{原文(JA): cap_bytes} —— DLC01 全部字段（含被 field_slots 漏掉的多行段）。
    需 DLC01 原版；否则返回 {}。"""
    import s2a
    import dlc_lib as D
    p_ja, p_en = dlc_orig_path('LANG_JA.s2a'), dlc_orig_path('LANG_EN.s2a')
    if not p_ja or not p_en:
        return {}
    ja_a, en_a = s2a.Archive(p_ja), s2a.Archive(p_en)

    def caps_for(blobs):
        out = {}
        for b in blobs:
            bb = bytes(b)
            cja = {off: cap for off, _p, _s, cap in D.field_slots(bb)}
            for off, _pos, s, capj in D.field_slots(bb):
                cap1 = min(cja.get(off, 10 ** 9), 10 ** 9)
                lim = D.field_limit(bb, off, cap1)
                if s:
                    out[s] = min(out.get(s, 10 ** 9), lim - off)
            for off, s in D.segs_lf(bb):
                if s:
                    lim = D.field_limit(bb, off, 10 ** 9)
                    out[s] = min(out.get(s, 10 ** 9), lim - off)
        return out

    cja = caps_for(ja_a.blobs)
    cen = caps_for(en_a.blobs)
    merged = {}
    for s in set(cja) | set(cen):
        merged[s] = min(cja.get(s, 10 ** 9), cen.get(s, 10 ** 9))
    return merged


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write('\n')


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)
