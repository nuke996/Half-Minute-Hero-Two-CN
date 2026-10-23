# -*- coding: utf-8 -*-
"""构建后自检：拦截会导致恶性机制 bug 的翻译/词典改动。

检查项（本篇 + DLC01）：
  1. 名字副本混合态：规范名已中文化，但仍有整槽/嵌入副本停留在英文；
  2. 名字哈希操作数：操作数指向的哈希在最终名字集合中不存在（过期操作数）；
  3. 译名重名 / 哈希碰撞：同一类别内两个不同原名译成同一终串（按名查找歧义）；
  4. 占位符 / 脚本 token：`%s`、`{0}`、`$X`、`#RG`、`SE...`、`<...>` 等未保留；
  5. DLC01：载具/道具名未同步、结构字段被改、文本未按当前 cmap 重编码。

用法：
  python tools/validate_build.py <dist_dir> [stage_dir]

返回码：0 = 通过（可能带 warning）；1 = 存在 error。
"""
import bisect
import collections
import csv
import os
import re
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import paths          # noqa: E402
import review_lib as R  # noqa: E402
import s2a            # noqa: E402
import build_cn as B  # noqa: E402
import dlc_apply as DA  # noqa: E402

# 规范名来源（与 audit_mechanic_replicas.py 保持一致）
NAME_SOURCES = {
    'skill': [(666, 376, 0)],
    'item': [(147, 268, 4), (357, 268, 4), (736, 268, 4), (998, 268, 4)],
    'partner_entity': [(954, 236, 4)],
    'partner_actor': [(1034, 104, 4)],
    'partner_composite': [(954, 236, 136), (954, 236, 168)],
    'class': [(128, 212, 4)],
    'formation': [(136, 272, 0)],
    'title': [(931, 292, 0)],
    'enemy': [(407, 236, 4)],
    'boss_speaker': [(4, 288, 92), (30, 288, 92), (408, 288, 92),
                     (445, 288, 92), (528, 288, 92), (748, 288, 92),
                     (609, 288, 92), (483, 288, 92),
                     (555, 660, 92), (734, 660, 92)],
    'chest_label': [(777, 236, 4), (1008, 236, 4)],
    'music': [(320, 492, 228), (320, 492, 292)],
    'map_ui': [(715, 224, 112)],
}
OPERAND_BLOBS = tuple(B.NAME_OPERAND_BLOBS)
UNRESOLVED_OK = {(756, 0), (756, 3), (756, 91), (756, 94)}

# 只保护“引擎会解析”的 token；普通 <高亮词> 属于显示文本（HL 会主动翻译），不在此列。
TOKEN_RES = [re.compile(p) for p in (
    rb'%[0-9]*\$?[sd]', rb'\{[0-9]+\}',
    rb'<(?:YUSHA_NAME|EVO_NAME__|RGN_NAME__|SERIESHERO|Nanako|Revan)>',
    rb'\$[A-Za-z0-9_]+', rb'#[A-Z0-9]{2}', rb'SE[0-9]*_[A-Z0-9_]+',
)]


def _nt(b, f):
    q = b.find(b'\x00', f)
    return b[f:q] if q >= 0 else b[f:]


def _text_like(run):
    """可打印 CP932 文本（数字 ID/二进制/控制字符不算；允许换行/制表与 NUL 截断）。"""
    if not run:
        return False
    core = run.split(b'\x00', 1)[0]
    if not core:
        return False
    try:
        s = core.decode('cp932')
    except UnicodeDecodeError:
        return False
    return all(ord(ch) >= 0x20 or ch in '\n\t' for ch in s)


def _load(path):
    return [bytes(x) for x in s2a.Archive(path).blobs]


def _canon(orig, prod):
    """{类别: {EN原串: 终串}}；顺带记录规范源自身的冲突。"""
    out = {c: {} for c in NAME_SOURCES}
    conflicts = []
    for cat, slots in NAME_SOURCES.items():
        for bi, st, pos in slots:
            if bi >= len(orig) or bi >= len(prod):
                continue
            ob, pb = orig[bi], prod[bi]
            if ob[:4] != b'CSCV':
                continue
            n = struct.unpack_from('<I', ob, 8)[0]
            for r in range(n):
                f = 16 + r * st + pos
                if f >= len(ob):
                    break
                en = _nt(ob, f)
                fin = _nt(pb, f)
                if len(en) < 2 or len(en) > 64 or b'\n' in en:
                    continue
                if b'<' in en and b'>' in en:
                    continue
                if not fin or fin == en:
                    continue
                if en in out[cat] and out[cat][en] != fin:
                    conflicts.append((cat, bi, r, pos, en, out[cat][en], fin))
                out[cat].setdefault(en, fin)
    return out, conflicts


def _check_replicas(orig, prod, canon, label, foreign=False):
    """残留英文的整槽 / 嵌入副本 = 混合态。"""
    errs = []
    en_all = set()
    for m in canon.values():
        en_all |= set(m)
    q16 = None if foreign else B._q16_lang_en_offsets('LANG_EN')
    ct_whole, ct_recs, _v = B.load_chap_title_guard()

    for bi, ob in enumerate(orig):
        if bi >= len(prod) or ob[:4] != b'CSCV':
            continue
        pb = prod[bi]
        st = struct.unpack_from('<I', ob, 4)[0]
        for pos, f, e in B._iter_slots(ob):
            en = ob[f:e]
            if en not in en_all:
                continue
            if not foreign and bi == 317:   # 连携技表：按配方保持原版
                continue
            if not foreign and st and B.chap_title_hit(
                    ct_whole, ct_recs, bi, st, (f - 16) % st, (f - 16) // st):
                continue
            if not foreign and B._q16_hit(q16, bi, pos, e):
                continue
            ce = pb.find(b'\x00', f)
            cur = pb[f:ce] if ce >= 0 else pb[f:]
            if cur == en:
                errs.append('[%s 混合态] b%d off%d (stride %s pos %s) 仍为英文 %r'
                            % (label, bi, f, st or '-', (f - 16) % st if st else '-',
                               en[:40]))

    # 嵌入：stride152 pos24（仅道具规范名）
    suf3 = {}
    for en in canon['item']:
        if len(en) >= 3:
            suf3.setdefault(en[-3:], []).append(en)
    for bi, ob in enumerate(orig):
        if bi >= len(prod) or ob[:4] != b'CSCV':
            continue
        st = struct.unpack_from('<I', ob, 4)[0]
        if st != 152:
            continue
        pb = prod[bi]
        for _pos, f, e in B._iter_slots(ob):
            run = ob[f:e]
            if len(run) < 4 or run[-3:] not in suf3:
                continue
            en = next((c for c in suf3[run[-3:]] if run.endswith(c)), None)
            if en is None or run == en:
                continue
            pre = run[:-len(en)]
            if not pre or pre[-1] < 0x80:
                continue
            i = e - len(en)
            if (i - 16) % st != 24:
                continue
            q = pb.find(b'\x00', i)
            if pb[i:q] == en:
                errs.append('[%s 嵌入混合态] b%d off%d 仍为英文 %r'
                            % (label, bi, i, en[:40]))
    return errs


def _check_operands(orig, prod, canon):
    """用“原哈希 -> 原串副本 -> 终串哈希”核对每个操作数。

    与 recompute_name_operands 同口径：原哈希能解析出副本时，产物操作数必须
    等于这些副本最终字节的哈希；解析不到的原哈希（已知 b756 例外）保持原值。
    """
    errs = []
    idx = B._name_hash_index(orig)   # hash -> [(blob, field, text)]
    for bi in OPERAND_BLOBS:
        if bi >= len(orig) or bi >= len(prod):
            continue
        ob, pb = orig[bi], prod[bi]
        if ob[:4] != b'CSCV':
            continue
        st, n = struct.unpack_from('<II', ob, 4)
        for r in range(n):
            off = 16 + r * st + 4
            if off + 4 > len(pb) or off + 4 > len(ob):
                break
            v_old = struct.unpack_from('<I', ob, off)[0]
            v_new = struct.unpack_from('<I', pb, off)[0]
            if (bi, r) in UNRESOLVED_OK or v_old in (0, 0xFFFFFFFF):
                continue
            cands = idx.get(v_old)
            if not cands:
                continue            # 源串未解析：保持原值（已知例外）
            finals = set()
            for cb, cf, _ct in cands:
                if cb >= len(prod):
                    continue
                q = prod[cb].find(b'\x00', cf)
                finals.add(prod[cb][cf:q] if q >= 0 else prod[cb][cf:])
            if not finals:
                continue
            if len(finals) > 1:
                errs.append('[操作数副本冲突] b%d rec%d 原哈希 %08X 对应 %d 个不同终串'
                            % (bi, r, v_old, len(finals)))
                continue
            exp = B.eng_name_hash(next(iter(finals)))
            if v_new != exp:
                errs.append('[操作数过期] b%d rec%d 原 %08X -> 现值 %08X，应为 %08X'
                            % (bi, r, v_old, v_new, exp))
    return errs


def _check_collisions(orig, prod, canon):
    errs, warns = [], []
    # 操作数引用到的哈希
    ref = set()
    for bi in OPERAND_BLOBS:
        if bi >= len(prod) or prod[bi][:4] != b'CSCV':
            continue
        st, n = struct.unpack_from('<II', prod[bi], 4)
        for r in range(n):
            off = 16 + r * st + 4
            if off + 4 > len(prod[bi]):
                break
            v = struct.unpack_from('<I', prod[bi], off)[0]
            if v not in (0, 0xFFFFFFFF):
                ref.add(v)
    # 同类内重名：按名查表的关键类别 -> error；纯显示类别 -> warning
    KEYED = {'skill', 'item', 'partner_entity', 'partner_actor',
             'partner_composite', 'class', 'formation', 'title'}
    for cat, m in canon.items():
        by_fin = collections.defaultdict(set)
        for en, fin in m.items():
            by_fin[fin].add(en)
        for fin, ens in by_fin.items():
            if len(ens) <= 1:
                continue
            msg = ('[重名] %s: %s -> 同一终串 %r'
                   % (cat, ' / '.join(sorted(x.decode('cp932', 'replace')
                                             for x in ens)[:5]), fin[:30]))
            (errs if cat in KEYED else warns).append(msg)
    # 哈希碰撞
    by_hash = collections.defaultdict(list)
    for cat, m in canon.items():
        for en, fin in m.items():
            by_hash[B.eng_name_hash(fin)].append((cat, en, fin))
    for h, items in by_hash.items():
        if h not in ref:
            continue
        fins = {x[2] for x in items}
        cats = {x[0] for x in items}
        if len(fins) > 1:
            errs.append('[哈希碰撞] %08X 被操作数引用，却对应多个不同终串: %s'
                        % (h, [(c, f[:20]) for c, _e, f in items][:4]))
        elif len(fins) == 1 and len(cats) > 1:
            warns.append('[跨表同名] %08X %r 同时用于类别 %s（日文母本亦有同例，静态安全）'
                         % (h, next(iter(fins))[:20], sorted(cats)))
    return errs, warns


def _check_tokens(orig, ja, prod, label):
    """只检查“原文（EN 或 JA）中真实存在的 token”。

    中译以 JA 为源；EN 本地化额外插入的 <YUSHA_NAME>/<EVO_NAME__>/<RGN_NAME__>
    在 JA 中不存在，缺失属显示取舍，不作为错误。JA 中存在的 <ナナコ> 等键必须保留
    （输出到 EN 侧时对应 <Nanako>）。
    """
    errs = []
    for bi, ob in enumerate(orig):
        if bi >= len(prod) or ob[:4] != b'CSCV':
            continue
        pb = prod[bi]
        jb = ja[bi] if bi < len(ja) else b''
        for _pos, f, e in B._iter_slots(ob):
            src = ob[f:e]
            if not _text_like(src):
                continue
            ce = pb.find(b'\x00', f)
            dst = pb[f:ce] if ce >= 0 else pb[f:]
            if dst == src:
                continue
            ja_src = b''
            if jb:
                jq = jb.find(b'\x00', f)
                ja_src = jb[f:jq] if jq >= 0 else jb[f:]
            toks = set()
            for rx in TOKEN_RES:
                toks |= {m.group(0) for m in rx.finditer(src)}
            ja_toks = set()
            for rx in TOKEN_RES:
                ja_toks |= {m.group(0) for m in rx.finditer(ja_src)}
            # EN 额外插入、JA 没有的 token：跳过
            toks = {t for t in toks if not ja_src or t in ja_toks}
            for t in toks:
                s = t.decode('cp932', 'replace')
                if s in B.HL_RAW:
                    val = B.HL_RAW[s]
                    need = val.encode('cp932', 'replace')
                    need2 = B.apply_repl(val).encode('cp932', 'replace')
                    if need not in dst and need2 not in dst:
                        errs.append('[token] %s b%d off%d 高亮译 %r 未出现'
                                    % (label, bi, f, s))
                    continue
                if t not in dst:
                    errs.append('[token] %s b%d off%d 丢失 %r（原文 %r）'
                                % (label, bi, f, s, src[:40]))
    return errs


def _text_spans(stage_dir):
    """已登记文本槽的 [start, end) 区间（单行 CSV + 代码内额外行 + 多行整字段）。"""
    spans = collections.defaultdict(list)
    try:
        for r in csv.DictReader(open(paths.data('text_v2.csv'), encoding='utf-8')):
            try:
                bi = int(r['blob_index']); off = int(r['offset']); sb = int(r['slot_bytes'])
            except Exception:
                continue
            spans[bi].append((off, off + sb))
    except Exception:
        pass
    try:
        for r in (B._z11_partner_rows() + B._z13_rows() + B._z14_rows()):
            try:
                bi = int(r['blob_index']); off = int(r['offset']); sb = int(r['slot_bytes'])
            except Exception:
                continue
            spans[bi].append((off, off + sb))
    except Exception:
        pass
    try:
        for _k, v in R.ml_meta(stage_dir).items():
            spans[v['blob']].append((v['off'], v['off'] + v['cap_bytes']))
    except Exception:
        pass
    for bi in spans:
        spans[bi].sort()
    return spans


def _check_structure(orig, prod, label, operand_ok=False, spans=None):
    errs = []
    starts = {bi: [a for a, _b in lst] for bi, lst in (spans or {}).items()}
    for bi, ob in enumerate(orig):
        if bi >= len(prod) or ob[:4] != b'CSCV':
            continue
        pb = prod[bi]
        st, n = struct.unpack_from('<II', ob, 4)
        if st <= 0:
            continue
        for r in range(n):
            base = 16 + r * st
            if base + st > len(ob) or base + st > len(pb):
                break
            for k in range(st):
                if ob[base + k] == pb[base + k]:
                    continue
                # 已登记文本槽内的写入（含原字段为单字节高位/控制符的情况）
                lst = (spans or {}).get(bi)
                if lst:
                    j = bisect.bisect_right(starts[bi], base + k) - 1
                    if j >= 0 and lst[j][0] <= base + k < lst[j][1]:
                        continue
                s = k
                while s > 0 and ob[base + s - 1] != 0:
                    s -= 1
                e = k
                while e < st and ob[base + e] != 0:
                    e += 1
                run = ob[base + s:base + e]
                pos = k - (k % 4)
                field = ob[base + pos:base + pos + 4]
                if _text_like(run):
                    continue
                # 向空 padding 写文本（原 4 字节全 0）属正常
                if not any(field) and any(pb[base + pos:base + pos + 4]):
                    continue
                # 字段本身是可打印 CP932（含从 pos292 等中间位置开始的文本槽）
                if field and _text_like(field):
                    continue
                if operand_ok and bi in OPERAND_BLOBS and pos == 4:
                    continue
                errs.append('[结构] %s b%d rec%d pos%d %s -> %s'
                            % (label, bi, r, pos,
                               ob[base + pos:base + pos + 4].hex(),
                               pb[base + pos:base + pos + 4].hex()))
                break
    return errs


def _check_dlc_encoding(dist_dir, stage_dir):
    """DLC 文本必须与“用当前 cmap 重新编码”的期望字节一致。"""
    errs, warns = [], []
    dp = os.path.join(dist_dir, 'DLC01', 'LANG_EN.s2a')
    if not os.path.exists(dp):
        return errs, warns
    op = R.dlc_orig_path('LANG_EN.s2a')
    if not op:
        warns.append('[DLC] 缺少原件备份，跳过编码校验')
        return errs, warns
    old_base = B.BASE
    B.BASE = stage_dir
    B._EXTRA_ROWS = B._z11_partner_rows() + B._z13_rows() + B._z14_rows()
    try:
        mp = B.build_plan()
        cmap, st = mp[7], mp[8]
    finally:
        B._EXTRA_ROWS = None
        B.BASE = old_base
    p_ja = DA.D.P_JA + DA.D.BAK_SUFFIX
    p_en = DA.D.P_EN + DA.D.BAK_SUFFIX
    if not (os.path.exists(p_ja) and os.path.exists(p_en)):
        warns.append('[DLC] 缺少原件备份，跳过编码一致性校验')
        return errs, warns
    try:
        plan, over, _L = DA.build_plan(cmap=cmap, native=st['native_set'])
    except Exception as ex:
        warns.append('[DLC] 编码校验跳过：%r' % ex)
        return errs, warns
    if over:
        errs.append('[DLC] 有 %d 处超容量，DLC 文本可能不完整' % len(over))
    prod = _load(dp)
    bad = 0
    for p in plan:
        bi, off, enc = p['blob'], p['off'], p['enc']
        if bi >= len(prod):
            continue
        if prod[bi][off:off + len(enc)] != enc:
            bad += 1
            if bad <= 20:
                errs.append('[DLC 编码] b%d off%d 未按当前 cmap 写入（期望 %r）'
                            % (bi, off, enc[:24]))
    if bad > 20:
        errs.append('[DLC 编码] 共 %d 处不一致' % bad)
    return errs, warns


def validate(dist_dir, stage_dir=None):
    """返回 (errors, warnings)。dist_dir 为打包输出目录（含 res/ 与 DLC01/）。"""
    errors, warns = [], []
    main_o_p = os.path.join(stage_dir or '', 'res', 'LANG_EN.s2a.bak')
    main_p_p = os.path.join(dist_dir, 'res', 'LANG_EN.s2a')
    if not (os.path.exists(main_o_p) and os.path.exists(main_p_p)):
        return ['[环境] 缺少主 LANG 原件（%s）或产物（%s），无法自检'
                % (main_o_p, main_p_p)], warns
    orig = _load(main_o_p)
    prod = _load(main_p_p)
    canon, conflicts = _canon(orig, prod)
    for cat, bi, r, pos, en, a, b in conflicts[:20]:
        errors.append('[规范源冲突] %s b%d rec%d pos%d %r: %r / %r'
                      % (cat, bi, r, pos, en[:30], a[:20], b[:20]))

    errors += _check_replicas(orig, prod, canon, '本篇')
    errors += _check_operands(orig, prod, canon)
    e2, w2 = _check_collisions(orig, prod, canon)
    errors += e2
    warns += w2
    ja = _load(os.path.join(stage_dir or '', 'res', 'LANG_JA.s2a.bak'))
    spans = _text_spans(stage_dir)
    errors += _check_tokens(orig, ja, prod, '本篇')
    errors += _check_structure(orig, prod, '本篇', operand_ok=True, spans=spans)

    # DLC01
    dlc_p = os.path.join(dist_dir, 'DLC01', 'LANG_EN.s2a')
    if os.path.exists(dlc_p):
        do = R.dlc_orig_path('LANG_EN.s2a')
        if do:
            do_b = _load(do)
            dp_b = _load(dlc_p)
            dja_p = R.dlc_orig_path('LANG_JA.s2a')
            dja_b = _load(dja_p) if dja_p else []
            item_canon = canon['item']
            d_canon = {'item': item_canon}
            errors += _check_replicas(do_b, dp_b, d_canon, 'DLC01', foreign=True)
            errors += _check_tokens(do_b, dja_b, dp_b, 'DLC01')
            errors += _check_structure(do_b, dp_b, 'DLC01', operand_ok=False)
        e3, w3 = _check_dlc_encoding(dist_dir, stage_dir)
        errors += e3
        warns += w3
    return errors, warns


def main():
    if len(sys.argv) < 2:
        print('usage: python tools/validate_build.py <dist_dir> [stage_dir]')
        return 2
    dist_dir = sys.argv[1]
    stage_dir = sys.argv[2] if len(sys.argv) > 2 else None
    if stage_dir is None:
        stage, missing = R.ensure_stage()
        stage_dir = stage
        if missing:
            print('[警告] 缺少原版文件: %s' % ', '.join(missing))
    errs, warns = validate(dist_dir, stage_dir)
    for w in warns[:40]:
        print('WARN ' + w)
    for e in errs[:80]:
        print('ERROR ' + e)
    print('== 自检结果: error %d / warning %d ==' % (len(errs), len(warns)))
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
