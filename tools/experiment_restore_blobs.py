# -*- coding: utf-8 -*-
"""experiment_restore_blobs.py —— 通用“整表还原”实验包工具。

把指定的 LANG_EN blob 整表写回原版英文，用于 LANG_EN 文本问题的 blob 二分。
非发布配方；产物带 build_manifest。

示例：
  python tools/experiment_restore_blobs.py --blobs 981 --out dist/EXP-b981
  python tools/experiment_restore_blobs.py --blobs 176,981,166 --out dist/EXP-worldmap
"""
import argparse
import hashlib
import json
import os
import shutil
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


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description='LANG_EN 整表/单槽还原实验包')
    ap.add_argument('--blobs', default='', help='逗号分隔的 blob 索引（整表还原）')
    ap.add_argument('--slots', default='',
                    help='逗号分隔的 blob:offset:length（单槽还原，优先于整表）')
    ap.add_argument('--out', required=True)
    ap.add_argument('--base', default=os.path.join(REPO, 'dist', 'Z29-legacy-terms'))
    ap.add_argument('--orig', default=os.path.join(REPO, 'work', 'original',
                                                   'res', 'LANG_EN.s2a.bak'))
    args = ap.parse_args()

    ids = [int(x) for x in args.blobs.split(',') if x.strip()]
    slots = []
    for part in args.slots.split(','):
        part = part.strip()
        if not part:
            continue
        bi, off, ln = (int(x) for x in part.split(':'))
        slots.append((bi, off, ln))
    base_en = os.path.join(args.base, 'res', 'LANG_EN.s2a')
    if not (os.path.exists(args.orig) and os.path.exists(base_en)):
        raise SystemExit('缺少原版备份或基座 LANG_EN')
    orig = [bytes(b) for b in s2a.Archive(args.orig).blobs]
    base_arc = s2a.Archive(base_en)
    prod = [bytearray(bytes(b)) for b in base_arc.blobs]
    for bi in ids:
        if bi >= len(prod):
            raise SystemExit('blob 越界: %d' % bi)
        prod[bi] = bytearray(orig[bi])
    for bi, off, ln in slots:
        if bi >= len(prod) or off + ln > len(orig[bi]):
            raise SystemExit('槽越界: %d:%d:%d' % (bi, off, ln))
        prod[bi][off:off + ln] = orig[bi][off:off + ln]

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
        'recipe_id': 'EXP-restore-blobs',
        'recipe_status': 'experiment',
        'base_recipe': 'z29',
        'base_dir': os.path.abspath(args.base),
        'built_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'restored_blobs': ids,
        'restored_slots': [{'blob': b, 'offset': o, 'length': l} for b, o, l in slots],
        'outputs': sorted(outputs, key=lambda x: x['path']),
    }
    with open(os.path.join(args.out, 'build_manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print('== 完成：%s，还原 blob %s ==' % (args.out, ids))
    return 0


if __name__ == '__main__':
    sys.exit(main())
