# -*- coding: utf-8 -*-
"""t190_g5_apply.py —— G5 技能名 写入口（薄包装 t175 的通用流水线）

用法
====
  python _work/t190_g5_apply.py check
  python _work/t190_g5_apply.py apply

规格
====
  技能表 b666：stride 376 / n 87 / pos 0（名字在 pos0）
  译名表 _work/t189_g5_eq.json（87 条，来源：已装机批次 + 主汉化 + 人工 2 条）
  ★ 全库 EXACT 副本同改（含武器表 147/357/736 的 pos168/204/236、b666/pos292 等）——铁律 44
  ★ cscv 硬闸：只写 LANG，写前/写后断言 cscv md5 不变 + 孪生名字字段仍日文原版
"""
import os
import sys

import paths
BASE = paths.GAME_DIR
W = paths.DATA_DIR
os.chdir(W)
sys.path.insert(0, W)

import t175_g3_apply as A   # noqa: E402

A.LABEL = 'G5 技能名'
A.CAT = '技能名'
A.BATCH = '技能名-G5'
A.STRIDE = 376
A.POS = 0
A.SRC = [(666, 87)]
A.EQ = os.path.join(W, 't189_g5_eq.json')
A.OUT = paths.build('t190_g5.txt')
A.PRE = paths.build('_pre_t190')
A.TSV = paths.build('t190_g5_slots.tsv')

if __name__ == '__main__':
    A.main()
