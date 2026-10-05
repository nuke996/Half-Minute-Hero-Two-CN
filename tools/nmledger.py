# -*- coding: utf-8 -*-
"""nmledger.py —— 名字类翻译「账本」（G1~G5 批次脚本 与 t140 回滚 共用）

为什么要账本
============
字段级回滚（"把某类的字段整列还原成原版"）会**误伤主汉化**：
例：`おじさま`、`マオウメダル５１`、`Geezer` 这些名字，主汉化本来就在部分字段翻过，
且游戏正常；若按字段回滚，会把它们退回日文 = 回归。
⇒ 因此只回滚「**我们名字批次真正写过的槽**」，逐字节记账，精确、幂等、零误伤。

账本文件：`_work/name_ledger.json`
    {"batches": [
        {"id": "技能名-实验DE", "class": "技能名", "ts": "20260918_...", "note": "...",
         "edits": [
            {"f": "LANG_JA", "b": 147, "off": 22696, "old": "<hex>", "new": "<hex>"},
            ...]}]}

· `off`   = 该槽 run 在原版里的起始**字节偏移**（写回 old 时写这里）
· `old`   = 原版 run 的 hex；`new` = 我们写入的 run 的 hex
· 回滚 = 把 `old` 写回 `off`（并把 [len(old), max(len(old),len(new))) 补 0）
"""
import os
import json
import datetime

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
LEDGER = os.path.join(W, 'name_ledger.json')


def load():
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding='utf-8') as fh:
            return json.load(fh)
    return {'batches': []}


def save(d):
    with open(LEDGER, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)


def record(batch_id, klass, edits, note=''):
    """登记/覆盖一个批次"""
    d = load()
    d['batches'] = [b for b in d['batches'] if b['id'] != batch_id]
    d['batches'].append({
        'id': batch_id,
        'class': klass,
        'ts': datetime.datetime.now().strftime('%Y%m%d_%H%M%S'),
        'note': note,
        'edits': edits,
    })
    save(d)
    return len(edits)


def batches():
    return load()['batches']
