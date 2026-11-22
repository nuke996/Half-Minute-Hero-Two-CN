# -*- coding: utf-8 -*-
"""experiment_place_names.py —— 区域/地名还原实验包（非发布配方）。

背景：`dist/EXP-jelly-names/` 已排除 Jelly/King Jelly 显示名与 b601 参数列；
日语下果冻怪正常 ⇒ 问题在 `LANG_EN` 的其它文本。本工具以 Z29 为基座，只还原
“地名/区域名/任务名”相关槽位，用来验证“世界地图按区域名选表/选道具”的假设：

  1) 所有 stride 1116 表（b34 等）的 pos4（关卡/任务名）与 pos104（村庄/港口名）；
  2) 所有 stride 580 表（b814 章节表）的 pos4（章节名）与 pos372（大陆/世界组名）；
  3) 所有 stride 424 表的 rec0 pos124（城镇名，如 Brave Castle Suburbs）；
  4) 所有 stride 292 表中“Q<数字>. …”形式的 pos32 槽（世界地图任务列表名，如 b176）；
  5) b358 rec818 pos112 的菜单标签 `Hero Castle`。

产物：`dist/EXP-place-names/`。安装与 Z29 相同，游戏语言 English。
预期副作用：选关/世界地图/城镇名显示英文；其余文本保持中文。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COPY_FILES = (
    'dinput8.dll',
    'hm2zh_patch.bin',
    os.path.join('res', 'cscv.s2a'),
    os.path.join('res', 'texture.s2a'),
    os.path.join('res', 'MOV.s2a'),
    os.path.join('DLC01', 'LANG_EN.s2a'),
    '补丁说明和卸载说明.txt',
)
# 半角 '.' 或 CP932 全角 '．'（0x81 0x6C）开头
QNAME_RE = re.compile(rb'^Q\d+[.\x81]')


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _run_at(blob, p, limit):
    e = blob.find(b'\x00', p, limit)
    if e < 0:
        e = limit
    return bytes(blob[p:e])


def _restore(prod, orig, bi, rec, pos, cap, note, out):
    st = struct.unpack_from('<I', orig, 4)[0]
    p = 16 + rec * st + pos
    if p + cap > len(orig):
        return
    run = _run_at(orig, p, p + cap)
    if not run:
        return
    old = _run_at(prod, p, p + cap)
    if old == run:
        return
    prod[p:p + len(run)] = run
    prod[p + len(run)] = 0
    end = max(p + len(run) + 1, p + len(old))
    for k in range(p + len(run) + 1, end):
        prod[k] = 0
    out.append((bi, st, rec, pos, run.decode('cp932', 'replace'), note))


def main():
    ap = argparse.ArgumentParser(description='区域/地名还原实验包')
    ap.add_argument('--base', default=os.path.join(REPO, 'dist', 'Z29-legacy-terms'))
    ap.add_argument('--out', default=os.path.join(REPO, 'dist', 'EXP-place-names'))
    ap.add_argument('--orig', default=os.path.join(REPO, 'work', 'original',
                                                   'res', 'LANG_EN.s2a.bak'))
    args = ap.parse_args()

    base_en = os.path.join(args.base, 'res', 'LANG_EN.s2a')
    if not (os.path.exists(args.orig) and os.path.exists(base_en)):
        raise SystemExit('缺少原版备份或基座 LANG_EN')
    orig_blobs = [bytes(b) for b in s2a.Archive(args.orig).blobs]
    base_arc = s2a.Archive(base_en)
    prod = [bytearray(bytes(b)) for b in base_arc.blobs]

    out = []
    for bi, ob in enumerate(orig_blobs):
        if ob[:4] != b'CSCV':
            continue
        st, n = struct.unpack_from('<II', ob, 4)
        if st == 1116:
            for rec in range(n):
                _restore(prod[bi], ob, bi, rec, 4, 64, 'quest_name', out)
                # 地名槽实测容量 32 或 40；按 40 读取原版 run，遇 NUL 自然截断
                _restore(prod[bi], ob, bi, rec, 104, 40, 'place_name', out)
        elif st == 580 and bi == 814:
            # 只处理章节表 b814；其它 stride580 表（如 b291 地图编辑器）不动
            for rec in range(n):
                _restore(prod[bi], ob, bi, rec, 4, 64, 'chapter_name', out)
                _restore(prod[bi], ob, bi, rec, 372, 208, 'continent_name', out)
        elif st == 424:
            # 只还原真正的城镇名；`Castle`/`Cave` 是地图编辑器类别标签，跳过
            p = 16 + 124
            run = _run_at(ob, p, p + 128)
            if run.endswith((b'Village', b'Port', b'Suburbs')) or b' ' in run:
                _restore(prod[bi], ob, bi, 0, 124, 128, 'town_name', out)
        elif st == 292:
            for rec in range(n):
                p = 16 + rec * st + 32
                run = _run_at(ob, p, p + 64)
                if QNAME_RE.match(run):
                    _restore(prod[bi], ob, bi, rec, 32, 64, 'quest_list_name', out)

    # b358 菜单标签 Hero Castle
    if 358 < len(orig_blobs):
        _restore(prod[358], orig_blobs[358], 358, 818, 112, 96, 'menu_label', out)

    print('== 还原 %d 槽 ==' % len(out))
    for x in out[:80]:
        print('  blob %4d stride %4d rec %4d pos %3d  %-24r  (%s)' % x)
    if len(out) > 80:
        print('  ... 其余 %d 槽省略' % (len(out) - 80))

    os.makedirs(os.path.join(args.out, 'res'), exist_ok=True)
    os.makedirs(os.path.join(args.out, 'DLC01'), exist_ok=True)
    out_en = os.path.join(args.out, 'res', 'LANG_EN.s2a')
    s2a.pack(out_en, base_arc.entries, [bytes(b) for b in prod])

    for rel in COPY_FILES:
        src = os.path.join(args.base, rel)
        if os.path.exists(src):
            dst = os.path.join(args.out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    outputs = []
    for root, _dirs, files in os.walk(args.out):
        for name in files:
            if name == 'build_manifest.json':
                continue
            p = os.path.join(root, name)
            rel = os.path.relpath(p, args.out).replace(os.sep, '/')
            outputs.append({'path': rel, 'bytes': os.path.getsize(p), 'sha256': _sha256(p)})
    manifest = {
        'schema': 1,
        'recipe_id': 'EXP-place-names',
        'recipe_status': 'experiment',
        'base_recipe': 'z29',
        'base_dir': os.path.abspath(args.base),
        'built_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'purpose': 'restore quest/place/chapter/town names in LANG_EN',
        'restored_slots': [
            {'blob': b, 'stride': s, 'rec': r, 'pos': p, 'text': t, 'kind': k}
            for b, s, r, p, t, k in out
        ],
        'outputs': sorted(outputs, key=lambda x: x['path']),
    }
    with open(os.path.join(args.out, 'build_manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print('== 完成：%s ==' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
