# -*- coding: utf-8 -*-
"""locate_text_row.py —— 按 CSV 行号/偏移定位到游戏中的表与上下文。

用途：审计/实机测试时，把 `text_v2.csv` 的一行（或任意 blob:offset）
还原成“哪个文件、哪条记录、哪个字段、前后文是什么”，便于判断它在
游戏里的位置（世界地图/某 Boss/某 UI/某关卡）。

示例：
  python tools/locate_text_row.py --row 10494
  python tools/locate_text_row.py --blob 974 --offset 134632
  python tools/locate_text_row.py --row 56515 --csv locales/zh-CN/text_v2.csv
"""
import argparse
import csv
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = ['', 'jud/', 'ove/', 'rgn/', 'evo/', 'mgn/', 'dst/', 'adh/', 'res/',
        'data/', 'map/', 'mapdata/', 'memap/', 'list/', 'act/']


def _names():
    names = set()
    for rel in ('work/original/res/LANG_EN.s2a', 'work/original/res/cscv.s2a'):
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            continue
        for b in s2a.Archive(p).blobs:
            for m in re.finditer(rb'[A-Za-z0-9_\-]{2,}\.(?:dat|s2mp)', bytes(b)):
                names.add(m.group().decode())
    exe = os.path.join(REPO, 'work', 'original', 'HMH2.exe')
    if os.path.exists(exe):
        for m in re.finditer(rb'[A-Za-z0-9_\-]{3,}\.(?:dat|s2mp)', open(exe, 'rb').read()):
            names.add(m.group().decode())
    return names


def _find_name(hv, names):
    hits = []
    for n in names:
        for d in DIRS:
            k = (d + n).lower()
            if zlib.crc32(k.encode()) == hv:
                hits.append(k)
    return sorted(set(hits))[:5]


def _runs(blob, stride, rec):
    r = bytes(blob[16 + rec * stride:16 + (rec + 1) * stride])
    out = []
    i = 0
    while i < len(r):
        if r[i] == 0:
            i += 1
            continue
        j = i
        while j < len(r) and r[j] != 0:
            j += 1
        seg = r[i:j]
        try:
            t = seg.decode('cp932')
        except Exception:
            t = repr(seg)
        if len(seg) >= 2:
            out.append((i, t))
        i = j
    return out


def main():
    ap = argparse.ArgumentParser(description='定位 CSV 行到游戏表/上下文')
    ap.add_argument('--row')
    ap.add_argument('--blob', type=int)
    ap.add_argument('--offset', type=int)
    ap.add_argument('--csv', default=os.path.join(REPO, 'locales', 'zh-CN', 'text_v2.csv'))
    ap.add_argument('--orig', default=os.path.join(REPO, 'work', 'original',
                                                   'res', 'LANG_JA.s2a.bak'))
    args = ap.parse_args()

    bi, off, sb, info = args.blob, args.offset, None, ''
    if args.row:
        for r in csv.DictReader(open(args.csv, encoding='utf-8')):
            if r['row_id'] == args.row:
                bi, off, sb = int(r['blob_index']), int(r['offset']), int(r['slot_bytes'])
                info = 'en=%r zh=%r' % (r['en'], r['zh_new'])
                break
        else:
            raise SystemExit('CSV 中找不到 row %s' % args.row)
    if bi is None or off is None:
        raise SystemExit('需要 --row 或 --blob/--offset')

    arc = s2a.Archive(args.orig)
    blob = bytes(arc.blobs[bi])
    magic = blob[:4]
    stride = count = None
    if magic == b'CSCV':
        stride, count = struct.unpack_from('<II', blob, 4)
    rec = (off - 16) // stride if stride else None
    pos = (off - 16) % stride if stride else None
    print('blob %d  size %d  magic %r  stride %s  count %s  entry 0x%08x'
          % (bi, len(blob), magic, stride, count, arc.entries[bi][0]))
    print('offset %d -> rec %s  pos %s  slot_bytes %s  %s' % (off, rec, pos, sb, info))
    hits = _find_name(arc.entries[bi][0], _names())
    print('name candidates:', hits or '(none; content-only blob)')
    if stride:
        for rr in range(max(0, rec - 1), min(count, rec + 3)):
            print('  rec %4d %s' % (rr, _runs(blob, stride, rr)[:12]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
