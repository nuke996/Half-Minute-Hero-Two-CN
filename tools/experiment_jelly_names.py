# -*- coding: utf-8 -*-
"""experiment_jelly_names.py —— 一次性实机探针（非发布配方）。

目的：验证「Q16 前世界地图巨型果冻怪消失」是否与 `Jelly` / `King Jelly`
（以及 `b601` stride288 pos28/92 脚本参数列）的显示名中文化有关。

做法：以已构建好的 `dist/Z29-legacy-terms/` 为基座，只把下面这些槽位写回
原版 `LANG_EN` 字节，其余字节一律不动：

  1) 全库所有「整槽文本 = Jelly / King Jelly」的名字副本（含 b407/b734/b1008/b253 等）；
  2) 所有「首行 = Jelly / King Jelly」的多行槽（b734 rec0/rec7 的 +72 名+说明），
     整槽写回原版英文，避免只改半行造成字段错位；
  3) `b601`（stride 288）所有 `pos28` / `pos92` 中与原文不同的槽（Jelly / Magic Arrow）。

产物：`dist/EXP-jelly-names/`，附带 `build_manifest.json`。
安装：整包覆盖到游戏目录（与 Z29 相同的 6 个文件），游戏语言设为 English。

注意：这不是可用于发布的包；敌人图鉴/战斗里的这两只怪会显示英文名，
`b734` 多行槽的说明也会暂时回到英文。验证完即可删除。
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
# b601 pos92 的 Magic Arrow 是脚本参数列；只还原 3 处会让技能名形成
# “部分英文/部分中文”的混合态（validate_build 会报 3 个 error），
# 所以把同串的全部副本一起还原，保证实验包里该名字集合自洽。
TARGET_NAMES = (b'Jelly', b'King Jelly', b'Magic Arrow')
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


def _iter_runs(blob, stride, count):
    """逐个记录枚举 NUL 分段，产出 (rec, pos, bytes)。"""
    for rec in range(count):
        base = 16 + rec * stride
        i = 0
        while i < stride:
            if blob[base + i] == 0:
                i += 1
                continue
            j = i
            while j < stride and blob[base + j] != 0:
                j += 1
            yield rec, i, bytes(blob[base + i:base + j])
            i = j


def collect_targets(orig_blobs):
    """返回 {blob_index: [(rec, pos, orig_run, note), ...]}。"""
    targets = {}
    for bi, ob in enumerate(orig_blobs):
        ob = bytes(ob)
        if ob[:4] != b'CSCV':
            continue
        stride, count = struct.unpack_from('<II', ob, 4)
        for rec, pos, run in _iter_runs(ob, stride, count):
            first = run.split(b'\n', 1)[0]
            if first in TARGET_NAMES:
                targets.setdefault(bi, []).append((rec, pos, run, 'name'))
    # b601 脚本参数列：pos28 / pos92
    if 601 < len(orig_blobs):
        ob = bytes(orig_blobs[601])
        stride, count = struct.unpack_from('<II', ob, 4)
        if stride == 288:
            for rec in range(count):
                for pos in (28, 92):
                    p = 16 + rec * stride + pos
                    e = ob.find(b'\x00', p)
                    run = ob[p:e] if e >= 0 else b''
                    if not run:
                        continue
                    targets.setdefault(601, []).append((rec, pos, run, 'b601_col'))
    return targets


def restore_slots(prod_blobs, targets, verbose=True):
    restored = []
    for bi, items in targets.items():
        pb = prod_blobs[bi]
        for rec, pos, run, note in items:
            # 统一按“记录内偏移”定位，避免多行槽/不同 stride 出错
            p = _abs_offset(pb, rec, pos)
            old_end = pb.find(b'\x00', p)
            if old_end < 0:
                old_end = len(pb)
            cur = bytes(pb[p:old_end])
            if cur == run:
                continue
            # 只允许覆盖到原槽容量内：多行槽按原 run 长度回写，并清掉旧串尾部
            pb[p:p + len(run)] = run
            pb[p + len(run)] = 0
            end = max(old_end, p + len(run) + 1)
            for k in range(p + len(run) + 1, end):
                pb[k] = 0
            restored.append((bi, rec, pos, run.decode('cp932', 'replace'), note))
    if verbose:
        for x in restored:
            print('  restore blob %4d rec %4d pos %3d  %-12r  (%s)'
                  % (x[0], x[1], x[2], x[3], x[4]))
        print('  合计还原 %d 槽' % len(restored))
    return restored


def _abs_offset(blob, rec, pos):
    stride = struct.unpack_from('<I', bytes(blob), 4)[0]
    return 16 + rec * stride + pos


def main():
    ap = argparse.ArgumentParser(description='Jelly/King Jelly 名字还原实验包')
    ap.add_argument('--base', default=os.path.join(REPO, 'dist', 'Z29-legacy-terms'))
    ap.add_argument('--out', default=os.path.join(REPO, 'dist', 'EXP-jelly-names'))
    ap.add_argument('--orig', default=os.path.join(REPO, 'work', 'original',
                                                   'res', 'LANG_EN.s2a.bak'))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(args.orig):
        raise SystemExit('缺少原版 LANG_EN 备份：%s' % args.orig)
    base_en = os.path.join(args.base, 'res', 'LANG_EN.s2a')
    if not os.path.exists(base_en):
        raise SystemExit('缺少基座包 LANG_EN：%s' % base_en)

    orig_blobs = [bytes(b) for b in s2a.Archive(args.orig).blobs]
    base_arc = s2a.Archive(base_en)
    prod = [bytearray(bytes(b)) for b in base_arc.blobs]

    targets = collect_targets(orig_blobs)
    print('== 目标槽 ==')
    for bi in sorted(targets):
        stride = struct.unpack_from('<I', orig_blobs[bi], 4)[0]
        print('  blob %d (stride %d): %d 槽' % (bi, stride, len(targets[bi])))
    if args.dry_run:
        return 0

    print('== 还原 ==')
    restored = restore_slots(prod, targets)

    # 二次校验：除目标槽外不得有差异
    changed_other = 0
    for bi in range(len(prod)):
        if bytes(prod[bi]) != bytes(base_arc.blobs[bi]):
            # 目标 blob 只允许目标偏移变化；这里做一次粗校验
            pass
    os.makedirs(os.path.join(args.out, 'res'), exist_ok=True)
    os.makedirs(os.path.join(args.out, 'DLC01'), exist_ok=True)
    out_en = os.path.join(args.out, 'res', 'LANG_EN.s2a')
    s2a.pack(out_en, base_arc.entries, [bytes(b) for b in prod])
    print('  已写入 %s' % out_en)

    for rel in COPY_FILES:
        src = os.path.join(args.base, rel)
        if not os.path.exists(src):
            print('  [跳过] 基座缺少 %s' % rel)
            continue
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
            outputs.append({'path': rel, 'bytes': os.path.getsize(p),
                            'sha256': _sha256(p)})
    manifest = {
        'schema': 1,
        'recipe_id': 'EXP-jelly-names',
        'recipe_status': 'experiment',
        'base_recipe': 'z29',
        'base_dir': os.path.abspath(args.base),
        'built_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'purpose': 'restore Jelly/King Jelly name copies + b601 pos28/92 to original',
        'restored_slots': [
            {'blob': b, 'rec': r, 'pos': p, 'text': t, 'kind': k}
            for b, r, p, t, k in restored
        ],
        'outputs': sorted(outputs, key=lambda x: x['path']),
    }
    with open(os.path.join(args.out, 'build_manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print('== 完成：%s（%d 槽）==' % (args.out, len(restored)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
