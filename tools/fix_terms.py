# -*- coding: utf-8 -*-
"""统一三组专名译法（只改 zh_new，不改句子结构）。

  ゴッドナイン    -> 九神      （第九神 / 九天神 / 神之九人 / 神耐因 归一）
  ヴィーナスセブン -> 七美神    （维纳斯七 / 维纳斯七子 / 维纳斯七人 / 金星七 归一）
  ヒーロークロス   -> 英雄十字  （英雄布 归一）

用法:
  python tools/fix_terms.py            # 预览
  python tools/fix_terms.py --apply    # 备份后写回 text_v2.csv
"""
import argparse
import csv
import datetime
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CSV_P = paths.data("text_v2.csv")
PREVIEW = paths.build("term_fix_preview.tsv")

GOD9 = ("神之九人", "神耐因", "第九神", "九天神")
VENUS = (
    ("维纳斯七人组", "七美神"),
    ("维纳斯七子", "七美神"),
    ("维纳斯七人", "七美神"),
    ("维纳斯七号", "七美神"),
    ("维纳斯七", "七美神"),
    ("金星七人", "七美神"),
    ("金星七号神殿", "七美神的神殿"),
    ("金星七号", "七美神"),
    ("金星七", "七美神"),
    ("维纳斯7", "七美神"),
    ("金星7", "七美神"),
)


def byte_len(s):
    return sum(1 if ord(ch) < 0x80 else 2 for ch in s)


def convert(row):
    """返回 (新译文, 命中说明) 或 (None, None)。"""
    ja = row.get("ja") or ""
    zh = row.get("zh_new") or ""
    if not zh:
        return None, None
    new = zh
    hits = []
    if "ゴッドナイン" in ja:
        for a in GOD9:
            if a in new:
                new = new.replace(a, "九神")
                hits.append(a)
    if "ヴィーナスセブン" in ja or "THE VENUS 7" in ja:
        for a, b in VENUS:
            if a in new:
                new = new.replace(a, b)
                hits.append(a)
    if "ヒーロークロス" in ja and "英雄布" in new:
        new = new.replace("英雄布", "英雄十字")
        hits.append("英雄布")
    if new == zh:
        return None, None
    return new, "+".join(hits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with open(CSV_P, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames
        rows = list(reader)

    changed = []
    problems = []
    stats = {}
    for r in rows:
        new, hit = convert(r)
        if new is None:
            continue
        slot = int(r["slot_bytes"])
        n = byte_len(new)
        if n > slot:
            problems.append((r["row_id"], "超长 %d > %d" % (n, slot), r["zh_new"], new))
            continue
        if (r["zh_new"].count("<") != new.count("<")
                or r["zh_new"].count(">") != new.count(">")):
            problems.append((r["row_id"], "占位符数量变化", r["zh_new"], new))
            continue
        changed.append((r, new, hit))
        r["zh_new"] = new
        stats[hit] = stats.get(hit, 0) + 1

    with open(PREVIEW, "w", encoding="utf-8", newline="") as fh:
        fh.write("row_id\tblob\toffset\thit\told\tnew\n")
        for r, new, hit in changed:
            fh.write("%s\t%s\t%s\t%s\t%s\t%s\n" % (
                r["row_id"], r["blob_index"], r["offset"], hit,
                r["zh_new"].replace("\t", " "), new.replace("\t", " ")))

    print("rows: %d  changed: %d  problems: %d" % (len(rows), len(changed), len(problems)))
    for k in sorted(stats, key=lambda x: -stats[x]):
        print("  %-24s %d" % (k, stats[k]))
    for p in problems:
        print("  [PROBLEM] %s %s\n    old=%r\n    new=%r" % p)
    print("preview ->", PREVIEW)
    if problems:
        print("有问题的条目未写入；请先处理。")
        return 1
    if not args.apply:
        print("（预览模式，未写回。加 --apply 写回）")
        return 0

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = CSV_P + ".bak_terms_" + ts
    shutil.copy2(CSV_P, bak)
    with open(CSV_P, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("backup ->", bak)
    print("written ->", CSV_P)
    return 0


if __name__ == "__main__":
    sys.exit(main())
