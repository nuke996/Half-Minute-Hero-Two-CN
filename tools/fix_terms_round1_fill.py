# -*- coding: utf-8 -*-
"""补完第一批术语的残留：第九神/九天神 -> 九神；维纳斯七 -> 七美神。"""
import csv, datetime, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

CSV_P = paths.data("text_v2.csv")
IDS = {
    "944": ("第九神", "九神"),
    "54374": ("第九神", "九神"),
    "54395": ("第九神", "九神"),
    "54428": ("第九神", "九神"),
    "59881": ("九天神", "九神"),
    "11730": ("维纳斯七", "七美神"),
    "12003": ("维纳斯七", "七美神"),
    "17485": ("维纳斯七", "七美神"),
    "17531": ("维纳斯七", "七美神"),
    "27479": ("维纳斯七", "七美神"),
    "28612": ("维纳斯七", "七美神"),
}

with open(CSV_P, encoding="utf-8-sig", newline="") as fh:
    reader = csv.DictReader(fh)
    fields = reader.fieldnames
    rows = list(reader)

n = 0
for r in rows:
    if r["row_id"] in IDS:
        old, new = IDS[r["row_id"]]
        if old in (r.get("zh_new") or ""):
            r["zh_new"] = r["zh_new"].replace(old, new)
            n += 1
            print(r["row_id"], old, "->", new, "|", r["zh_new"][:50])

if "--apply" not in sys.argv:
    print("changed:", n, "(preview)")
    sys.exit(0)

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = CSV_P + ".bak_terms1fill_" + ts
shutil.copy2(CSV_P, bak)
with open(CSV_P, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
print("changed:", n, "backup ->", bak)
