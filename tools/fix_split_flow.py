# -*- coding: utf-8 -*-
"""跨槽对话断句规范化（问题 1：分开存放的多行文本拼接不通顺）。

游戏把一条对话拆成同一记录内的多个定长槽（如 stride 288/292 的
pos156+pos220、pos160+pos224，或 stride 424 的相邻记录）。翻译时逐槽
单独处理，常出现：

  槽1「我明白了。  +  槽2　那我跟你走！！！」

拼起来后句中断开。本工具只做“结构性”修复，不改变语义：

  * 日文在槽1尚未结束时，去掉中文槽1末尾多出来的句号/叹号，改为逗号
  * 日文引号尚未闭合时，去掉中文槽1末尾多出来的 」
  * 日文下一槽没有开引号时，去掉中文下一槽多出来的 「
  * 日文下一槽以 全角空格 续行时，保留其缩进

不处理的：
  * 语义本身译错（属于“日文源重译”范畴，另行处理）
  * 受保护行（protected/ 下的 collide/mech 等）

用法：
  python tools/fix_split_flow.py            # 只出预览与统计
  python tools/fix_split_flow.py --apply    # 写入 text_v2.csv（自动备份）
"""
import argparse
import collections
import csv
import datetime
import glob
import json
import os
import re
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import s2a

END = "。！？!?…」』"
CSV_P = paths.data("text_v2.csv")
LANG_JA = paths.game("res", "LANG_JA.s2a")
VIEW_PROT = paths.data("translator-view", "protected", "*.json")
PREVIEW = paths.build("split_flow_preview.tsv")


def byte_len(s):
    return sum(1 if ord(ch) < 0x80 else 2 for ch in s)


def load_rows():
    with open(CSV_P, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_protected():
    ids = set()
    for p in glob.glob(VIEW_PROT):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for e in d.get("entries", []):
            ids.add(str(e.get("id", "")))
    return ids


def load_stride(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[int(r["blob_index"])].append(r)
    ar = s2a.Archive(LANG_JA)
    stride = {}
    for bi in by:
        b = bytes(ar.blobs[bi])
        if b[:4] == b"CSCV":
            stride[bi] = struct.unpack_from("<I", b, 4)[0]
    return by, stride


def build_chains(by, stride):
    """返回 [[row,...], ...]，每个 chain 是一句被拆开的连续文本槽。"""
    chains = []
    for bi, rs in by.items():
        st = stride.get(bi)
        if not st:
            continue
        recs = collections.defaultdict(list)
        for r in rs:
            recs[(int(r["offset"]) - 16) // st].append(r)
        for rec in sorted(recs):
            g = sorted(recs[rec], key=lambda r: int(r["offset"]))
            i = 0
            while i < len(g):
                run = [g[i]]
                while i + len(run) < len(g):
                    a = run[-1]
                    b = g[i + len(run)]
                    ja = a["ja"].rstrip()
                    jb = b["ja"]
                    if ja and ja[-1] not in END and (
                        jb.startswith("\u3000")
                        or ("「" in ja and "」" not in ja and "「" not in jb)
                    ):
                        run.append(b)
                    else:
                        break
                if len(run) > 1:
                    chains.append(run)
                i += len(run)
    # 注意：stride 424 的每条记录是独立的对话框（按键翻页），
    # 不是同一框内的两行，跨记录改写句末标点会让单框以逗号结尾，故不处理。
    return chains


def plan(rows, chains, protected):
    by_id = {r["row_id"]: r for r in rows}
    new = {}
    stats = collections.Counter()
    flagged = []
    preview = []

    def set_zh(r, val, rule):
        old = new.get(r["row_id"], r["zh_new"])
        if val == old:
            return
        new[r["row_id"]] = val
        stats[rule] += 1
        preview.append((r["row_id"], r["blob_index"], r["offset"], rule,
                        old, val, r["ja"]))

    for run in chains:
        for i in range(len(run) - 1):
            r, n = run[i], run[i + 1]
            if r["row_id"] in protected or n["row_id"] in protected:
                stats["skip_protected"] += 1
                continue
            z = new.get(r["row_id"], r["zh_new"])
            if not z.strip():
                continue
            core = z.rstrip()
            tail = z[len(core):]
            ja = r["ja"]
            if core.endswith("」") and ja.count("「") > ja.count("」"):
                core = core[:-1]
                stats["strip_close_quote"] += 1
            if core.endswith("。"):
                core = core[:-1] + "，"
                stats["period_to_comma"] += 1
            else:
                m = re.search(r"！+$", core)
                if m:
                    core = core[:m.start()] + "，"
                    stats["excl_to_comma"] += 1
            if core != z.rstrip():
                set_zh(r, core + tail, "fix_tail")

            nz = new.get(n["row_id"], n["zh_new"])
            stripped = nz.lstrip("\u3000 ")
            prefix = nz[:len(nz) - len(stripped)]
            nja = n["ja"].lstrip("\u3000 ")
            if stripped.startswith("「") and not nja.startswith("「"):
                nz2 = prefix + stripped[1:]
                set_zh(n, nz2, "strip_open_quote")
                stripped = nz2.lstrip("\u3000 ")

            # 记录“疑似语义不连贯”，只报告不改
            z2 = new.get(r["row_id"], r["zh_new"]).rstrip()
            if z2 and stripped:
                for k in (3, 2):
                    if len(z2) >= k and stripped.startswith(z2[-k:]):
                        flagged.append((r["row_id"], r["blob_index"], r["offset"],
                                        "repeat%d" % k, z2[-20:], stripped[:20]))
                        break

    # 容量与占位符校验
    over = []
    ph = re.compile(r"<[^<>]{1,40}>")
    for rid, val in new.items():
        r = by_id[rid]
        cap = int(r["slot_bytes"])
        if byte_len(val) > cap:
            over.append((rid, r["blob_index"], r["offset"], byte_len(val), cap))
        if ph.findall(r["zh_new"]) != ph.findall(val):
            stats["placeholder_mismatch"] += 1
    return new, stats, flagged, preview, over


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = load_rows()
    protected = load_protected()
    by, stride = load_stride(rows)
    chains = build_chains(by, stride)
    new, stats, flagged, preview, over = plan(rows, chains, protected)

    print("chains: %d  fields: %d" % (len(chains), sum(len(c) for c in chains)))
    print("protected ids: %d" % len(protected))
    print("changed rows: %d" % len(new))
    for k, v in sorted(stats.items()):
        print("  %-20s %d" % (k, v))
    print("over capacity: %d  placeholder mismatches: %d"
          % (len(over), stats.get("placeholder_mismatch", 0)))
    print("flagged (semantic, not changed): %d" % len(flagged))

    with open(PREVIEW, "w", encoding="utf-8", newline="\n") as f:
        f.write("row_id\tblob\toffset\trule\told\tnew\tja\n")
        for row in preview:
            f.write("\t".join(str(x).replace("\t", " ").replace("\n", "\\n")
                              for x in row) + "\n")
        f.write("\n# flagged\n")
        for row in flagged:
            f.write("\t".join(str(x) for x in row) + "\n")
    print("preview: %s" % PREVIEW)

    if over or stats.get("placeholder_mismatch"):
        print("ABORT: 校验失败，未写入")
        return 1

    if args.apply:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = CSV_P + ".bak_splitflow_" + ts
        shutil.copy2(CSV_P, bak)
        for r in rows:
            if r["row_id"] in new:
                r["zh_new"] = new[r["row_id"]]
        with open(CSV_P, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("written: %s" % CSV_P)
        print("backup:  %s" % bak)

    return 0


if __name__ == "__main__":
    sys.exit(main())
