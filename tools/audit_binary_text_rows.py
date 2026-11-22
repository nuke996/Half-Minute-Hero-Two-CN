# -*- coding: utf-8 -*-
"""audit_binary_text_rows.py —— 检查 text_v2.csv 是否把二进制 run 当成文本。

判据（与 PITFALLS §48 的写入守卫一致）：
  1) 原版槽位 [off, off+slot_bytes) 内没有 NUL 终止符；
  2) 从 off 到下一个 NUL 的 run（去掉开头 4 字节 FF 前缀后）含 0xFF，
     或无法用 CP932 解码。

命中即说明该 CSV 行把资源/二进制字段误当文本；写入短译文会用 NUL
清零字段内部字节（例：b176 off441816 的 `F㊤` → `F`）。

用法：
  python tools/audit_binary_text_rows.py
退出码：0 = 干净；1 = 有命中。
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_binary_run(run):
    if run.startswith(b'\xff\xff\xff\xff'):
        run = run[4:]
    if b'\xff' in run:
        return True
    try:
        run.decode('cp932')
        return False
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser(description='text_v2.csv 二进制误判审计')
    ap.add_argument('--csv', default=os.path.join(REPO, 'locales', 'zh-CN', 'text_v2.csv'))
    ap.add_argument('--orig', default=os.path.join(REPO, 'work', 'original',
                                                   'res', 'LANG_JA.s2a.bak'))
    args = ap.parse_args()

    arc = s2a.Archive(args.orig)
    rows = list(csv.DictReader(open(args.csv, encoding='utf-8')))
    hits = []
    for r in rows:
        try:
            bi = int(r['blob_index'])
            off = int(r['offset'])
            sb = int(r['slot_bytes'])
        except Exception:
            continue
        if bi >= len(arc.blobs) or off + sb > len(arc.blobs[bi]):
            continue
        blob = bytes(arc.blobs[bi])
        slot = blob[off:off + sb]
        if b'\x00' in slot:
            continue
        e = blob.find(b'\x00', off)
        run = blob[off:e] if e >= 0 else b''
        if is_binary_run(run):
            hits.append((r['row_id'], bi, off, sb, r['en'], r['zh_new'],
                         run[:48].hex(' ')))
    print('== 二进制误判行：%d ==' % len(hits))
    for x in hits:
        print('  row %-6s blob %-4d off %-7d sb %-3d en=%-12r zh=%-12r run=%s'
              % x)
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main())
