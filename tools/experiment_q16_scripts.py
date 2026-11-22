# -*- coding: utf-8 -*-
"""experiment_q16_scripts.py —— Q16/世界地图脚本整表还原实验包（非发布配方）。

语言对照已确认：同一补丁日语下果冻怪正常 ⇒ 问题在 `LANG_EN` 文本。
前两轮已排除 Jelly/King Jelly 名称副本、b601 参数列、任务/地名/章节/城镇名。
本工具把“Q16 / 世界地图脚本表”整表写回原版英文，做第三轮分组验证：

  1) 所有 stride 288 表中任意记录 pos28 整槽 == `Hero Castle` 的 blob
     （b20/38/40/63/160/194/200/231/239/262/297/300/319/449/477/587/615/
      616/694/747/769/786/793/837/840/858/876/1002/1039/1042 等）；
  2) 所有 stride 292 表中任意记录 pos32 整槽 == `Hero Castle` 的 blob
     （b166/b212/b336/b366/b458/b493/b497/b510/b532/b620/b647/b795/b804/
       b911/b913/b941/b970/b1043 等）；
  3) 固定补充：b176（urtt 世界地图菜单/演员）、b355（关卡演员表）、
     b954/b1034（伙伴数据/演员名键表）、b981（jud_eve 事件表）。

产物：`dist/EXP-q16-scripts/`。安装与 Z29 相同，游戏语言 English。
预期副作用：Q16/世界地图相关台词、伙伴名会显示英文；其余文本保持中文。
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXED = (166, 176, 355, 954, 981, 1034)
COPY_FILES = (
    'dinput8.dll',
    'hm2zh_patch.bin',
    os.path.join('res', 'cscv.s2a'),
    os.path.join('res', 'texture.s2a'),
    os.path.join('res', 'MOV.s2a'),
    os.path.join('DLC01', 'LANG_EN.s2a'),
    '补丁说明和卸载说明.txt',
)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _run(blob, p, limit):
    e = blob.find(b'\x00', p, limit)
    if e < 0:
        e = limit
    return bytes(blob[p:e])


def select_blobs(orig_blobs):
    sel = set(x for x in FIXED if x < len(orig_blobs))
    for bi, ob in enumerate(orig_blobs):
        if ob[:4] != b'CSCV':
            continue
        st, n = struct.unpack_from('<II', ob, 4)
        if st not in (288, 292):
            continue
        pos = 28 if st == 288 else 32
        for rec in range(n):
            p = 16 + rec * st + pos
            if _run(ob, p, p + 64) == b'Hero Castle':
                sel.add(bi)
                break
    return sorted(sel)


def main():
    ap = argparse.ArgumentParser(description='Q16/世界地图脚本整表还原实验包')
    ap.add_argument('--base', default=os.path.join(REPO, 'dist', 'Z29-legacy-terms'))
    ap.add_argument('--out', default=os.path.join(REPO, 'dist', 'EXP-q16-scripts'))
    ap.add_argument('--orig', default=os.path.join(REPO, 'work', 'original',
                                                   'res', 'LANG_EN.s2a.bak'))
    args = ap.parse_args()

    base_en = os.path.join(args.base, 'res', 'LANG_EN.s2a')
    if not (os.path.exists(args.orig) and os.path.exists(base_en)):
        raise SystemExit('缺少原版备份或基座 LANG_EN')
    orig_blobs = [bytes(b) for b in s2a.Archive(args.orig).blobs]
    base_arc = s2a.Archive(base_en)
    prod = [bytearray(bytes(b)) for b in base_arc.blobs]

    sel = select_blobs(orig_blobs)
    print('== 选中 %d 个 blob：%s ==' % (len(sel), sel))
    changed = []
    for bi in sel:
        if bytes(prod[bi]) != orig_blobs[bi]:
            changed.append(bi)
            prod[bi] = bytearray(orig_blobs[bi])
    print('== 实际还原 %d 个 blob：%s ==' % (len(changed), changed))

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
        'recipe_id': 'EXP-q16-scripts',
        'recipe_status': 'experiment',
        'base_recipe': 'z29',
        'base_dir': os.path.abspath(args.base),
        'built_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'purpose': 'restore Q16/world-map script blobs in LANG_EN',
        'selected_blobs': sel,
        'restored_blobs': changed,
        'outputs': sorted(outputs, key=lambda x: x['path']),
    }
    with open(os.path.join(args.out, 'build_manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print('== 完成：%s ==' % args.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
