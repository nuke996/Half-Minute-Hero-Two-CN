# -*- coding: utf-8 -*-
"""第二轮术语统一（只改 zh，不改句子结构）。

主线:
  神殿/時の神殿 -> 神殿 / 时之神殿
  リングドラゴン -> 指环龙
  戦いのヴァーチ -> 战争的瓦奇
  オメガ -> 欧米伽（EN 槽位过短时回退为 欧米）
  かわをはって作った盾 -> 用皮革绷制的盾
  戦士団ごようたしのくつ -> 战士团御用的靴子
  船乗り -> 水手
  ガーバリンG10 -> 加巴林
  ローリー -> 洛瑞
  悪魔 -> 恶魔
  ジェリー -> 果冻怪（EN 槽位过短时回退为 果冻）
  ビヨージェリー -> 美容果冻怪（怪物名；DLC 道具为 美容果冻）

DLC01:
  トクガ -> 德川
  シャマル -> 夏马尔
  ジェリー -> 果冻怪
  ビヨージェリー / ジェリーパック / セクシーネイル / 全めくり 保持现状

用法:
  python tools/fix_terms_round2.py            # 预览
  python tools/fix_terms_round2.py --apply    # 备份后写回
"""
import argparse
import csv
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CSV_P = paths.data("text_v2.csv")
DLC_DIR = paths.data("dlc")
PREVIEW = paths.build("term_fix_round2_preview.tsv")


def byte_len(s):
    return sum(1 if ord(ch) < 0x80 else 2 for ch in s)


def convert_main(ja, zh):
    new = zh
    hits = []
    if "神殿" in ja:
        for a, b in (("时光神庙", "时之神殿"), ("时之殿", "时之神殿"), ("神庙", "神殿")):
            if a in new:
                new = new.replace(a, b)
                hits.append(a)
    if "リングドラゴン" in ja:
        if "环龙" in new:
            new = new.replace("指环龙", "\x00").replace("环龙", "指环龙").replace("\x00", "指环龙")
            hits.append("环龙")
    if "戦いのヴァーチ" in ja and "战事的瓦奇" in new:
        new = new.replace("战事的瓦奇", "战争的瓦奇")
        hits.append("战事的瓦奇")
    if "オメガ" in ja:
        n0 = new
        new = new.replace("荆棘宝藏2", "欧米伽2").replace("奥米伽", "欧米伽")
        new = new.replace("欧米茄", "欧米伽").replace("奥米加", "欧米伽").replace("欧米加", "欧米伽")
        new = re.sub(r"欧米(?!伽)", "欧米伽", new)
        if new != n0:
            hits.append("オメガ")
    if "かわをはって作った盾" in ja:
        for a in ("兽皮制成的盾", "皮革制成的盾"):
            if a in new:
                new = new.replace(a, "用皮革绷制的盾")
                hits.append(a)
    if "戦士団ごようたしのくつ" in ja:
        for a in ("战士们爱用的鞋", "战士团爱用的靴子"):
            if a in new:
                new = new.replace(a, "战士团御用的靴子")
                hits.append(a)
    if "船乗り" in ja:
        for a in ("船夫", "船员"):
            if a in new:
                new = new.replace(a, "水手")
                hits.append(a)
    if "ガーバリン" in ja and "加瓦林" in new:
        new = new.replace("加瓦林", "加巴林")
        hits.append("加瓦林")
    if "ローリー" in ja and "劳里" in new:
        new = new.replace("劳里", "洛瑞")
        hits.append("劳里")
    if ja == "悪魔" and "魔族" in new:
        new = new.replace("魔族", "恶魔")
        hits.append("魔族")
    if ja == "ジェリー" and "胶怪" in new:
        new = new.replace("胶怪", "果冻怪")
        hits.append("胶怪")
    if "ビヨージェリー" in ja and "美丽果冻怪" in new:
        new = new.replace("美丽果冻怪", "美容果冻怪")
        hits.append("美丽果冻怪")
    return new, hits


def fit(new, slot):
    """超长时使用约定好的短形式；返回 (值, 说明)。"""
    if byte_len(new) <= slot:
        return new, ""
    for full, short in (("欧米伽", "欧米"), ("果冻怪", "果冻")):
        if full in new:
            cand = new.replace(full, short)
            if byte_len(cand) <= slot:
                return cand, "短槽回退 %s->%s" % (full, short)
    return None, "超长无法回退"


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
    fallbacks = []
    for r in rows:
        ja = r.get("ja") or ""
        zh = r.get("zh_new") or ""
        if not zh:
            continue
        new, hits = convert_main(ja, zh)
        if new == zh:
            continue
        slot = int(r["slot_bytes"])
        val, note = fit(new, slot)
        if val is None:
            problems.append((r["row_id"], note, zh, new))
            continue
        if zh.count("<") != val.count("<") or zh.count(">") != val.count(">"):
            problems.append((r["row_id"], "占位符数量变化", zh, val))
            continue
        if note:
            fallbacks.append((r["row_id"], note, val))
        changed.append((r, zh, val, "+".join(hits)))
        r["zh_new"] = val
        for h in hits:
            stats[h] = stats.get(h, 0) + 1

    # ---- DLC01 ----
    dlc_changes = []
    for fn in ("zh_01", "zh_02", "zh_03", "zh_04", "zh_05", "zh_06"):
        p = os.path.join(DLC_DIR, fn + ".tsv")
        if not os.path.exists(p):
            continue
        lines = open(p, encoding="utf-8-sig").read().splitlines()
        for i, line in enumerate(lines):
            ja, sep, zh = line.partition("\t")
            if not sep:
                continue
            new = zh
            hits = []
            if "トクガ" in ja and "托加" in new:
                new = new.replace("托加", "德川")
                hits.append("托加")
            if ("ジェリー" in ja and "ビヨージェリー" not in ja
                    and "ジェリーパック" not in ja and "果冻怪" not in new and "果冻" in new):
                new = new.replace("果冻", "果冻怪")
                hits.append("果冻")
            if new != zh:
                dlc_changes.append((fn, i + 1, zh, new, "+".join(hits)))
                lines[i] = ja + "\t" + new
        if args.apply and any(c[0] == fn for c in dlc_changes):
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(p, p + ".bak_terms2_" + ts)
            open(p, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")

    p7 = os.path.join(DLC_DIR, "zh_07.json")
    d7 = json.load(open(p7, encoding="utf-8"))
    d7_changes = []
    for k in list(d7):
        v = d7[k]
        new = v
        hits = []
        if "シャマル" in k and "夏玛尔" in new:
            new = new.replace("夏玛尔", "夏马尔")
            hits.append("夏玛尔")
        if "トクガ" in k and "托加" in new:
            new = new.replace("托加", "德川")
            hits.append("托加")
        if new != v:
            d7_changes.append((k, v, new, "+".join(hits)))
            d7[k] = new
    if args.apply and d7_changes:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(p7, p7 + ".bak_terms2_" + ts)
        json.dump(d7, open(p7, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    with open(PREVIEW, "w", encoding="utf-8", newline="") as fh:
        fh.write("scope\tid\thit\told\tnew\n")
        for r, old, new, hits in changed:
            fh.write("main\t%s\t%s\t%s\t%s\n" % (r["row_id"], hits,
                                                old.replace("\t", " "), new.replace("\t", " ")))
        for fn, ln, old, new, hits in dlc_changes:
            fh.write("dlc\t%s#%d\t%s\t%s\t%s\n" % (fn, ln, hits,
                                                   old.replace("\t", " "), new.replace("\t", " ")))
        for k, old, new, hits in d7_changes:
            fh.write("dlc\tzh_07\t%s\t%s\t%s\n" % (hits, old.replace("\t", " ").replace("\n", "¶"),
                                                   new.replace("\t", " ").replace("\n", "¶")))

    print("main changed: %d  problems: %d  fallbacks: %d" % (len(changed), len(problems), len(fallbacks)))
    for k in sorted(stats, key=lambda x: -stats[x]):
        print("  %-16s %d" % (k, stats[k]))
    for x in fallbacks:
        print("  [fallback] %s %s -> %r" % x)
    for p in problems:
        print("  [PROBLEM] %s %s\n    old=%r\n    new=%r" % p)
    print("DLC tsv changed: %d  zh_07 changed: %d" % (len(dlc_changes), len(d7_changes)))
    for fn, ln, old, new, hits in dlc_changes:
        print("  %s#%d %s: %r -> %r" % (fn, ln, hits, old, new))
    for k, old, new, hits in d7_changes:
        print("  zh_07 %s: %r -> %r" % (hits, old[:50], new[:50]))
    print("preview ->", PREVIEW)
    if problems:
        print("有问题的条目未写入；请先处理。")
        return 1
    if not args.apply:
        print("（预览模式，未写回。加 --apply 写回）")
        return 0

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = CSV_P + ".bak_terms2_" + ts
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
