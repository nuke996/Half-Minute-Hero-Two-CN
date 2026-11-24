# -*- coding: utf-8 -*-
"""脚本“按名查表”穷举审计（T-18，2026-11-24）。

背景
----
名字表被翻译后，**所有引用该名字的脚本参数/结构字段**必须同步为同一最终字节，
否则引擎按名查表失败：伙伴不生成（Q19/Q63/Q73）、城堡战初始化失败（Q73 闪退）、
载具消失、初始装备丢失等（见 docs/PITFALLS.md §54 / §25.3 / §29）。

已发生过的形态：
  · `#PARTY(NAME)` / `#HERO_CATSLEPARTSn(NAME)`          —— 命令参数
  · `stride152 pos24` 载具名                              —— 固定结构字段
  · `head=/body=/handR=/handL=/foot=` loadout             —— key=value
  · Q16 `b358 rec818 pos112` 菜单键                       —— 必须等于本语言原版串

本工具**不按“已知命令/已知偏移”枚举**，而按数据形态穷举：
  1. 名字 canon：从权威名字表（validate_build.NAME_SOURCES + 城堡零件表 b86）
     建立 `EN 原串 -> 产物最终字节`；
  2. 结构信号：任意 `#CMD(...)` 参数、任意 `key=value`、整槽同名、运行内嵌名；
  3. 语言差分：同位置的 JA 母本是否为该名字的日文原串（辅助判定“这是键不是正文”）；
  4. 显示白名单：text_v2.csv 登记的显示槽不参与“未知候选”报警；
  5. 哈希操作数 / Q16 键单独校验。

输出
----
`build/audit/script_name_refs.tsv`：每个非同步候选一行；
stdout：按类别/状态汇总，以及问题明细。
退出码：0 = 没有机制性不同步；1 = 存在 stale / divergent / missing / changed。
（`--strict-loose` 可把“未解释的松散候选”也判为失败。）

用法
----
  python tools/audit_script_name_refs.py                 # 审计当前校对目标包
  python tools/audit_script_name_refs.py --dist dist/Z30-script-names
  python tools/audit_script_name_refs.py --archive main --no-dlc
"""
import argparse
import collections
import csv
import json
import os
import re
import struct
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import paths          # noqa: E402
import s2a            # noqa: E402
import build_cn as B  # noqa: E402
import validate_build as V  # noqa: E402

NAME_MAX = B.NAME_MAX_LEN

# 权威名字表：(blob, stride, 记录内偏移)。
# 主表来自 validate_build.NAME_SOURCES，保证与构建自检同源；城堡零件表单独补入。
TABLE_SOURCES = collections.OrderedDict()
for _cat, _srcs in V.NAME_SOURCES.items():
    TABLE_SOURCES[_cat] = list(_srcs)
TABLE_SOURCES['castle_part'] = [(86, 288, 28)]

CMD_RE = re.compile(rb'#([A-Z0-9_]{2,40})\(([^()\x00]*)\)')
WORD = set(b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_')

# 允许在非显示槽里做“松散子串”扫描的名字类别（正文类名字不参与，降低噪声）。
LOOSE_CATS = {
    'skill', 'item', 'partner_entity', 'partner_actor', 'partner_composite',
    'class', 'formation', 'title', 'enemy', 'castle_part',
}
LOOSE_MIN_LEN = 4


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def load_blobs(path):
    if not path or not os.path.exists(path):
        return None
    try:
        return [bytes(b) for b in s2a.Archive(path).blobs]
    except Exception as exc:
        print('  [读取失败] %s: %r' % (path, exc))
        return None


def cstr(b, f, lim):
    if f < 0 or f >= len(b):
        return b''
    e = b.find(b'\x00', f)
    if e < 0 or e > f + lim:
        e = min(len(b), f + lim)
    return b[f:e]


def safe(t, limit=80):
    """把字节转成可读预览（英文/CP932 直接解，失败用 latin-1）。"""
    t = bytes(t)[:limit]
    try:
        return t.decode('cp932')
    except Exception:
        return t.decode('latin-1', 'replace')


class CarrierDecode(object):
    """用 cmap.json 把“载体码”还原成真正的中文，便于报告阅读。"""

    def __init__(self):
        self.rev = {}
        try:
            with open(paths.data('cmap.json'), encoding='utf-8') as fh:
                codes = json.load(fh).get('codes', {})
            for ch, hx in codes.items():
                self.rev[int(hx, 16)] = ch
        except Exception:
            pass

    def __call__(self, t, limit=80):
        out = []
        i = 0
        while i < len(t) and len(out) < limit:
            b = t[i]
            if b < 0x80:
                out.append(chr(b))
                i += 1
                continue
            if b >= 0x81 and i + 1 < len(t):
                code = (b << 8) | t[i + 1]
                if code in self.rev:
                    out.append(self.rev[code])
                    i += 2
                    continue
                try:
                    out.append(bytes((b, t[i + 1])).decode('cp932'))
                    i += 2
                    continue
                except Exception:
                    pass
            out.append('\\x%02x' % b)
            i += 1
        return ''.join(out)


# --------------------------------------------------------------------------
# 名字 canon
# --------------------------------------------------------------------------
def build_canons(E, P, J):
    """返回 (canon, ja_names, src_positions, conflicts)。

    canon[cat][en_bytes] = final_bytes；只收“已翻译”的名字。
    ja_names[cat][en_bytes] = 日文原串（用于语言差分）。
    src_positions = 权威表自身的 (blob, offset)，整槽检查时跳过。
    """
    canon = collections.defaultdict(dict)
    ja_names = collections.defaultdict(dict)
    src = set()
    conflicts = []
    for cat, entries in TABLE_SOURCES.items():
        for bi, st, pos in entries:
            if bi >= len(E) or E[bi][:4] != b'CSCV':
                continue
            ob = E[bi]
            n = struct.unpack_from('<I', ob, 8)[0]
            if st <= 0 or pos < 0 or 16 + st * n > len(ob):
                continue
            lim = min(NAME_MAX, st - pos - 1)
            if lim < 2:
                continue
            pb = P[bi] if bi < len(P) else b''
            jb = J[bi] if (J and bi < len(J)) else b''
            for r in range(n):
                f = 16 + r * st + pos
                src.add((bi, f))
                en = cstr(ob, f, lim)
                if not en or len(en) < 2:
                    continue
                if any(c in en for c in (b'<', b'>', b'(', b')', b'\n', b'\r')):
                    continue
                fin = cstr(pb, f, lim) if pb else b''
                if not fin or fin == en:
                    continue
                old = canon[cat].get(en)
                if old is not None and old != fin:
                    conflicts.append((cat, en, old, fin, bi, r))
                    continue
                canon[cat][en] = fin
                if jb:
                    jt = cstr(jb, f, lim)
                    if jt:
                        ja_names[cat].setdefault(en, jt)
    return canon, ja_names, src, conflicts


def build_union(canon):
    """en -> [(cat, final)]，同一 EN 可能跨类别。"""
    union = collections.defaultdict(list)
    for cat, m in canon.items():
        for en, fin in m.items():
            union[en].append((cat, fin))
    return union


# --------------------------------------------------------------------------
# 显示白名单 / Q16 / 守卫
# --------------------------------------------------------------------------
def load_display():
    out = set()
    path = paths.data('text_v2.csv')
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh):
            try:
                out.add((int(r['blob_index']), int(r['offset'])))
            except Exception:
                continue
    return out


def load_q16_rows():
    rows = []
    if not os.path.exists(B.Q16_KEY_TSV):
        return rows
    with open(B.Q16_KEY_TSV, encoding='utf-8-sig', newline='') as fh:
        for r in csv.DictReader(fh, delimiter='\t'):
            if str(r.get('wave')) == '1':
                rows.append(r)
    return rows


class Guards(object):
    def __init__(self):
        try:
            self.ct_whole, self.ct_recs, self.ct_vals = B.load_chap_title_guard()
        except Exception:
            self.ct_whole, self.ct_recs, self.ct_vals = set(), [], []
        try:
            self.desc = B.load_desc_release()
        except Exception:
            self.desc = None
        self.q16 = set()
        for r in load_q16_rows():
            try:
                self.q16.add((int(r['blob']), int(r['off'])))
            except Exception:
                continue

    def desc_hit(self, stride, bi, off):
        """说明文字段（纯显示，不参与按名查表）。语义同 build_cn.desc_release_hit。"""
        rel = self.desc
        if not rel or not stride:
            return False
        pos = (off - 16) % stride
        for r in rel.get('rules', ()):
            if r.get('enabled') is False:
                continue
            try:
                if int(r.get('stride', -1)) != stride:
                    continue
            except Exception:
                continue
            bl = r.get('blobs')
            if bl is not None and bi not in [int(x) for x in bl]:
                continue
            want = r.get('pos')
            wants = ([int(x) for x in want] if isinstance(want, (list, tuple))
                     else [int(want)])
            if any(pos == w or pos == w + k for w in wants for k in (0, 1, 2, 3)):
                return True
        return False

    def reason(self, bi, stride, off_abs):
        """返回保护原因；None 表示需要正常审计。"""
        if bi == 317:
            return 'design:b317(主角默认名保留英文)'
        if (bi, off_abs) in self.q16:
            return 'q16-key'
        try:
            if B.in_skill_key_col(bi, off_abs):
                return 'skill-keycol'
        except Exception:
            pass
        if stride and self.desc_hit(stride, bi, off_abs):
            return 'desc'
        if self.ct_whole and stride:
            try:
                if B.chap_title_hit(self.ct_whole, self.ct_recs, bi, stride,
                                    (off_abs - 16) % stride,
                                    (off_abs - 16) // stride):
                    return 'chaptitle'
            except Exception:
                pass
        return None


# --------------------------------------------------------------------------
# 产物取值
# --------------------------------------------------------------------------
def prod_run(pb, pos):
    f = pos
    while f < len(pb) and pb[f] == 0xFF:
        f += 1
    e = pb.find(b'\x00', f)
    if e < 0:
        e = len(pb)
    return f, e, pb[f:e]


def run_pairs(run):
    """解析多行 run 里的 key=value，返回 [(key, value, value_rel_start)]。

    ★ 实测 b34/b1010 的 Ad Hoc 预设存在 `foot2=` 换行后下一行才写值的数据形态，
      按换行续读一次（下一行没有 `=` 且非空），否则会漏掉这些装备名引用。
    """
    out = []
    lines = run.split(b'\n')
    off = 0
    for idx, line in enumerate(lines):
        if b'=' in line:
            k, v = line.split(b'=', 1)
            lead = len(v) - len(v.lstrip(b' \t\x81@'))
            val = strip_pad(v)
            vs = off + len(k) + 1 + lead
            if not val and idx + 1 < len(lines) and b'=' not in lines[idx + 1]:
                nxt = lines[idx + 1]
                nlead = len(nxt) - len(nxt.lstrip(b' \t\x81@'))
                nval = strip_pad(nxt)
                if nval:
                    val = nval
                    vs = off + len(line) + 1 + nlead
            out.append((k.strip(), val, vs))
        off += len(line) + 1
    return out


def strip_pad(v):
    """只去掉行首/行尾的 ASCII 空格与制表。

    ★ 不要剥全角空格（0x81 0x40）：`Brave Vest　` 是**另一个道具**（终极背心 →
    勇敢背心），`Brave Vest` 才是勇者背心；剥掉会制造假阳性并串错道具
    （2026-11-24 Z31 事故，见 PITFALLS §54.2）。
    """
    return v.strip(b' \t')


def is_name_like(v):
    """像名字的载荷：>=3 字节、含字母、不含格式占位符。"""
    if not v or len(v) < 3 or b'%' in v or b'=' in v:
        return False
    return any(0x41 <= c <= 0x5A or 0x61 <= c <= 0x7A for c in v)


def run_cmds(run):
    return [(m.group(1), m.group(2), m.start(2), m.end(2))
            for m in CMD_RE.finditer(run)]


def boundary(run, i, j):
    # 名字必须是一个独立 token：左右不能紧贴 ASCII 字母/数字/下划线，也不能紧贴空格
    # （避免把 "Knight Dynamite"、"Hero Castle" 这类复合专名里的单词当成名字引用）。
    if i > 0:
        p = run[i - 1]
        if p in WORD or p == 0x20:
            return False
    if j < len(run):
        n = run[j]
        if n in WORD or n == 0x20:
            return False
    return True


def covered(span, spans):
    s, e = span
    for cs, ce in spans:
        if s < ce and cs < e:
            return True
    return False


# --------------------------------------------------------------------------
# 单个档案扫描
# --------------------------------------------------------------------------
class Auditor(object):
    def __init__(self, archive, E, P, J, canon, ja_names, src, display, guards):
        self.archive = archive
        self.E, self.P, self.J = E, P, J
        self.canon = canon
        self.ja = ja_names
        self.src = src
        self.display = display
        self.guards = guards
        self.union = build_union(canon)
        self.dec = CarrierDecode()
        self.rows = []
        self.stats = collections.Counter()
        self.prefix = collections.defaultdict(list)
        for en, lst in self.union.items():
            cats = {c for c, _f in lst}
            if len(en) >= LOOSE_MIN_LEN and cats & LOOSE_CATS:
                self.prefix[en[:4]].append(en)

    # ---- 记录一个候选 -----------------------------------------------------
    def add(self, bi, stride, run_pos, kind, en, expected, actual, status,
            context, note=''):
        rec = (run_pos - 16) // stride if stride else 0
        pin = (run_pos - 16) % stride if stride else 0
        cats = sorted({c for c, _f in self.union.get(en, [])})
        self.stats[(kind, status)] += 1
        self.rows.append(dict(
            archive=self.archive, category=','.join(cats), blob=bi,
            stride=stride, rec=rec, pos=pin, run_off=run_pos, kind=kind,
            en=safe(en), en_hex=bytes(en).hex(),
            expected=self.dec(expected), expected_hex=bytes(expected).hex(),
            actual=self.dec(actual), actual_hex=bytes(actual).hex(),
            status=status, context=context, note=note,
        ))

    def expected_of(self, en):
        lst = self.union.get(en, [])
        finals = {f for _c, f in lst}
        if not finals:
            return None, 'no-canon'
        if len(finals) > 1:
            return None, 'ambiguous'
        return next(iter(finals)), ''

    def ctx(self, run, s, e, pad=36):
        a = max(0, s - pad)
        b = min(len(run), e + pad)
        pre = safe(run[a:s], 80)
        hit = safe(run[s:e], 80)
        post = safe(run[e:b], 80)
        return ('%s[%s]%s' % (pre, hit, post)).replace('\t', ' ')

    # ---- 主扫描 -----------------------------------------------------------
    def scan(self, verbose=True):
        for bi, ob in enumerate(self.E):
            if ob[:4] != b'CSCV' or bi >= len(self.P):
                continue
            pb = self.P[bi]
            stride, count = struct.unpack_from('<II', ob, 4)
            if stride <= 0 or 16 + stride * count > len(ob):
                continue
            for run_pos, f, e in B._iter_slots(ob):
                run = ob[f:e]
                if not run:
                    continue
                pf, pe, prun = prod_run(pb, run_pos)
                is_disp = (bi, f) in self.display
                spans = []
                self._scan_cmds(bi, stride, run_pos, f, run, prun, spans)
                self._scan_pairs(bi, stride, run_pos, f, run, prun, spans)
                whole = self._scan_slot(bi, stride, run_pos, f, run, prun, is_disp)
                # 松散子串扫描只用于主 LANG：DLC 没有 text_v2 式的显示白名单，
                # 对话正文噪声过大；DLC 的关键信号由 cmd/loadout/slot 结构覆盖。
                if not is_disp and not whole and self.archive == 'main':
                    self._scan_loose(bi, stride, run_pos, f, run, prun, spans)
        if verbose:
            print('  [%s] 扫描完成：%d 条候选明细'
                  % (self.archive, len(self.rows)))

    def _scan_cmds(self, bi, stride, run_pos, f, run, prun, spans):
        en_cmds = run_cmds(run)
        if not en_cmds:
            return
        pr_cmds = run_cmds(prun)
        for idx, (cmd, param, s, e) in enumerate(en_cmds):
            spans.append((s, e))
            if not param or b'<' in param or b'>' in param:
                continue
            actual = pr_cmds[idx][1] if idx < len(pr_cmds) and pr_cmds[idx][0] == cmd else b''
            exp, why = self.expected_of(param)
            off_abs = f + s
            if why == 'ambiguous':
                self.add(bi, stride, run_pos, 'cmd', param, b'', actual,
                         'ambiguous', self.ctx(run, s, e),
                         '同一名字跨类别终串不同')
                continue
            if exp is None:
                if actual != param:
                    self.add(bi, stride, run_pos, 'cmd-changed', param, param,
                             actual, 'changed', self.ctx(run, s, e),
                             '参数不在名字 canon 中，却被改动')
                continue
            if actual == exp:
                st = 'synced'
            elif actual == param:
                st = 'stale'
            elif not actual:
                st = 'missing'
            else:
                st = 'divergent'
            self.add(bi, stride, run_pos, 'cmd', param, exp, actual, st,
                     self.ctx(run, s, e), '#' + cmd.decode('latin-1'))

    def _scan_pairs(self, bi, stride, run_pos, f, run, prun, spans):
        if b'=' not in run:
            return
        en_pairs = run_pairs(run)
        if not en_pairs:
            return
        pr = {k: v for k, v, _o in run_pairs(prun)}
        for key, val, s in en_pairs:
            e = s + len(val)
            spans.append((s, e))
            if not val or b'<' in val or b'>' in val:
                continue
            actual = pr.get(key, b'')
            exp, why = self.expected_of(val)
            off_abs = f + s
            if why == 'ambiguous':
                self.add(bi, stride, run_pos, 'loadout', val, b'', actual,
                         'ambiguous', self.ctx(run, s, e), 'key=%s' % safe(key, 24))
                continue
            if exp is None:
                if actual != val and is_name_like(val):
                    self.add(bi, stride, run_pos, 'loadout-changed', val, val,
                             actual, 'changed', self.ctx(run, s, e),
                             'key=%s' % safe(key, 24))
                continue
            if actual == exp:
                st = 'synced'
            elif actual == val:
                st = 'stale'
            elif not actual:
                st = 'missing'
            else:
                st = 'divergent'
            self.add(bi, stride, run_pos, 'loadout', val, exp, actual, st,
                     self.ctx(run, s, e), 'key=%s' % safe(key, 24))

    def _scan_slot(self, bi, stride, run_pos, f, run, prun, is_disp):
        """整槽同名副本。返回 True 表示这个 run 是一个完整名字（松散扫描应跳过）。"""
        val = run.strip(b'\xff')
        if not val or val not in self.union:
            return False
        if (bi, f) in self.src:
            return True            # 权威表自身
        if is_disp:
            return True            # 显示文本
        if self.guards.reason(bi, stride, f):
            return True
        exp, why = self.expected_of(val)
        if exp is None:
            return True
        actual = prun.strip(b'\xff')
        if actual == exp:
            st = 'synced'
        elif actual == val:
            st = 'stale'
        elif not actual:
            st = 'missing'
        else:
            st = 'divergent'
        if self.archive != 'main' and st == 'divergent':
            cats = {c for c, _f in self.union.get(val, [])}
            if 'title' not in cats:
                # DLC 有自己的一套译名（同一英文名在主 LANG/DLC 可以译法不同），
                # 跨档案 canon 不能判死；标为待人工确认。
                # 例外：称号是明确的按名键——DLC `stride292 pos32` 是称号取得条件副本，
                # 原版 JA 两侧逐字节相同，译文不同会让称号无法取得（PITFALLS §25.17）。
                st = 'review-cross'
        self.add(bi, stride, run_pos, 'slot', val, exp, actual, st,
                 self.ctx(run, 0, len(val)), '整槽同名副本')
        return True

    def ja_of(self, en):
        for m in self.ja.values():
            if en in m:
                return m[en]
        return b''

    def _scan_loose(self, bi, stride, run_pos, f, run, prun, spans):
        L = len(run)
        i = 0
        while i <= L - LOOSE_MIN_LEN:
            lst = self.prefix.get(run[i:i + 4])
            if lst:
                for en in lst:
                    j = i + len(en)
                    if j > L or not run.startswith(en, i):
                        continue
                    if covered((i, j), spans) or not boundary(run, i, j):
                        continue
                    off_abs = f + i
                    if self.guards.reason(bi, stride, off_abs):
                        continue
                    # 嵌入名：stride152/pos24 且名前最后一字节是二进制（>=0x80），
                    # 与 _sync_item_copies 的判定一致；其余都是普通松散子串。
                    kind = 'embedded' if (stride == 152 and
                                          (off_abs - 16) % stride == 24 and
                                          i > 0 and run[i - 1] >= 0x80) else 'loose'
                    exp, why = self.expected_of(en)
                    if exp is None:
                        continue
                    if prun == run:
                        st = 'kept'      # 产物整段未动：受保护/复合专名，不算不同步
                    elif kind == 'embedded':
                        st = 'synced' if prun.endswith(exp) else (
                            'stale' if prun.endswith(en) else 'divergent')
                    else:
                        st = 'synced' if exp in prun else (
                            'stale' if en in prun else 'divergent')
                    self.add(bi, stride, run_pos, kind, en, exp, prun, st,
                             self.ctx(run, i, j),
                             'JA=%s' % safe(self.ja_of(en), 24))
            i += 1


# --------------------------------------------------------------------------
# 操作数 / Q16
# --------------------------------------------------------------------------
def check_operands(archive, E, P, canon):
    problems = []
    old = {}
    for cat, m in canon.items():
        for en, fin in m.items():
            old.setdefault(B._eng_name_hash_fast(en), (cat, en, fin))
    for bi in B.NAME_OPERAND_BLOBS:
        if bi >= len(E) or bi >= len(P) or E[bi][:4] != b'CSCV':
            continue
        ob, pb = E[bi], P[bi]
        stride, count = struct.unpack_from('<II', ob, 4)
        if stride <= 0:
            continue
        for r in range(count):
            off = 16 + r * stride + B.NAME_OPERAND_REC_OFF
            if off + 4 > len(ob):
                break
            cur = struct.unpack_from('<I', pb, off)[0]
            ov = struct.unpack_from('<I', ob, off)[0]
            ent = old.get(ov)
            if not ent:
                continue
            cat, en, fin = ent
            want = B._eng_name_hash_fast(fin)
            if cur != want:
                problems.append(dict(
                    archive=archive, category=cat, blob=bi, stride=stride,
                    rec=r, pos=B.NAME_OPERAND_REC_OFF, run_off=off,
                    kind='operand', en=safe(en), en_hex=en.hex(),
                    expected='%08X' % want, expected_hex='',
                    actual='%08X' % cur, actual_hex='',
                    status='stale', context='',
                    note='名字哈希操作数未随终串更新',
                ))
    return problems


def check_q16(archive, rows, En, Pn, Ja, Pja, guards):
    """Q16/菜单键必须等于**该文件自己的原版串**（EN 写英文、JA 写日文）。

    说明文字段（desc_release 命中的 b147/357/736 pos40 等）是纯显示文本，
    不是键名，跳过（与 build_cn.restore_q16_keys 的处理一致）。
    """
    problems = []
    for r in rows:
        fname = str(r.get('file', ''))
        if fname == 'LANG_EN':
            orig, prod = En, Pn
        elif fname == 'LANG_JA':
            orig, prod = Ja, (Pja or Ja)
        else:
            continue
        if not orig or not prod:
            continue
        try:
            bi = int(r['blob'])
            off = int(r['off'])
            stride = int(r.get('stride') or 0)
        except Exception:
            continue
        if bi >= len(orig) or bi >= len(prod):
            continue
        if any(guards.desc_hit(stride, bi, off + k) for k in range(5)):
            continue
        want = cstr(orig[bi], off, 96)
        cur = cstr(prod[bi], off, 96)
        if cur == want:
            continue
        problems.append(dict(
            archive=archive, category='q16-key', blob=bi,
            stride=stride, rec=int(r.get('rec') or 0),
            pos=int(r.get('pos') or 0), run_off=off, kind='q16',
            en=safe(want), en_hex=want.hex(),
            expected=safe(want), expected_hex=want.hex(),
            actual=safe(cur), actual_hex=cur.hex(),
            status='stale', context='',
            note='Q16/菜单键必须等于本语言原版串',
        ))
    return problems


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description='脚本按名查表穷举审计（T-18）')
    ap.add_argument('--dist', help='产物目录（默认=当前校对目标）')
    ap.add_argument('--out', help='TSV 输出路径（默认 build/audit/script_name_refs.tsv）')
    ap.add_argument('--archive', choices=['main', 'dlc', 'both'], default='both')
    ap.add_argument('--strict-loose', action='store_true',
                    help='把松散候选（loose/embedded 未同步）也判为失败')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args(argv)

    dist = args.dist
    if not dist:
        meta = B.current_recipe_meta()
        dist = paths.dist(meta['out'])
    if not os.path.isdir(dist):
        print('!! 产物目录不存在：%s' % dist)
        return 2
    print('== 脚本按名查表审计 ==')
    print('产物：%s' % dist)

    out_path = args.out or paths.build('audit', 'script_name_refs.tsv')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    display = load_display()
    guards = Guards()
    q16_rows = load_q16_rows()

    archives = []
    en_main = load_blobs(paths.game('res', 'LANG_EN.s2a'))
    pr_main = load_blobs(os.path.join(dist, 'res', 'LANG_EN.s2a'))
    ja_main = load_blobs(paths.game('res', 'LANG_JA.s2a'))
    if en_main and pr_main:
        archives.append(('main', en_main, pr_main, ja_main))
    else:
        print('  [跳过] 主 LANG 缺失（EN 原版或产物）')

    if args.archive in ('dlc', 'both'):
        en_dlc = load_blobs(paths.game('DLC01', 'LANG_EN.s2a'))
        pr_dlc = load_blobs(os.path.join(dist, 'DLC01', 'LANG_EN.s2a'))
        if en_dlc and pr_dlc:
            archives.append(('dlc', en_dlc, pr_dlc, None))
        elif args.archive == 'dlc':
            print('  [跳过] DLC01 缺失（EN 原版或产物）')

    if not archives:
        print('!! 没有可审计的档案')
        return 2

    # canon 以主 LANG 为准（DLC 复用同一套游戏内名字）
    canon, ja_names, src, conflicts = build_canons(en_main, pr_main, ja_main)
    n_names = sum(len(m) for m in canon.values())
    print('  名字 canon：%d 条（%d 类），来源槽位 %d 个'
          % (n_names, len(canon), len(src)))

    rows = []
    stats = collections.Counter()
    for name, E, P, J in archives:
        au = Auditor(name, E, P, J, canon, ja_names, src, display, guards)
        au.scan(verbose=True)
        if name == 'main':
            rows += check_operands(name, E, P, canon)
            rows += check_q16('main', q16_rows, E, P, J, None, guards)
        rows += au.rows
        stats.update(au.stats)

    # ---- 输出 TSV（只写需要复核的行；synced/kept 不写） ----
    fields = ['archive', 'category', 'blob', 'stride', 'rec', 'pos', 'run_off',
              'kind', 'en', 'en_hex', 'expected', 'expected_hex', 'actual',
              'actual_hex', 'status', 'context', 'note']
    write = [r for r in rows if r['status'] not in ('synced', 'kept')]

    def clean(x):
        return str(x).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')

    with open(out_path, 'w', encoding='utf-8', newline='') as fh:
        fh.write('\t'.join(fields) + '\n')
        for r in write:
            fh.write('\t'.join(clean(r.get(k, '')) for k in fields) + '\n')

    # ---- 摘要 ----
    print('\n== 候选统计（按结构形态 / 状态）==')
    kinds = ['cmd', 'cmd-changed', 'loadout', 'loadout-changed', 'slot',
             'embedded', 'loose', 'operand', 'q16']
    for kind in kinds:
        items = [(s, v) for (k, s), v in stats.items() if k == kind]
        if not items:
            continue
        detail = ', '.join('%s=%d' % (s, v) for s, v in sorted(items))
        print('  %-16s %5d  (%s)' % (kind, sum(v for _s, v in items), detail))

    bad = [r for r in write if r['status'] in
           ('stale', 'divergent', 'missing', 'changed', 'ambiguous')]
    loose = [r for r in write if r['kind'] in ('loose', 'embedded')
             and r['status'] == 'divergent']
    review = [r for r in write if r['status'] == 'review-cross']
    print('\n== 问题条目 ==')
    print('  机制性不同步（stale/divergent/missing/changed/ambiguous）：%d' % len(bad))
    print('  未解释的松散候选（loose/embedded divergent）：%d' % len(loose))
    print('  DLC 跨档案译名差异（待人工确认）：%d' % len(review))

    def show(label, items, limit=60):
        if not items:
            return
        print('\n  -- %s --' % label)
        for r in items[:limit]:
            print('   %s b%s rec%s pos%s %-14s %-10s %r -> %r (期望 %r)'
                  % (r['archive'], r['blob'], r['rec'], r['pos'], r['kind'],
                     r['status'], r['en'], r['actual'], r['expected']))
            if r.get('context'):
                print('        %s' % r['context'][:150])
        if len(items) > limit:
            print('   ... 其余 %d 条见 TSV' % (len(items) - limit))

    show('机制性不同步', bad)
    show('未解释的松散候选', loose)
    show('DLC 跨档案译名差异（待人工确认）', review)

    if conflicts:
        print('\n== canon 冲突（同表同名不同终串）==')
        for cat, en, a, b2, bi, r in conflicts[:30]:
            print('   %s b%d rec%d %r -> %r / %r'
                  % (cat, bi, r, safe(en), safe(a), safe(b2)))

    print('\n明细：%s（%d 行）' % (out_path, len(write)))
    fail = bool(bad) or (args.strict_loose and bool(loose))
    print('结论：%s' % ('存在需要处理的问题' if fail else '未发现机制性不同步'))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
