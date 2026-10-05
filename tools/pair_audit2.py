# -*- coding: utf-8 -*-
"""定向审计：只在 CSCV 记录表的"字段槽"里，找部分翻译（有的翻有的没翻）的串。
这类最危险：游戏可能用字段文本做分组/匹配的键。"""
import sys, io, os, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import paths
B = paths.GAME_DIR
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2a

o = s2a.Archive(os.path.join(B, 'res/LANG_JA.s2a.bak'))
n = s2a.Archive(os.path.join(B, 'res/LANG_JA.s2a'))

def fields(d):
    """解析 CSCV 记录表 -> [(off, len, text)] 字段槽（每个 NUL run 去掉 FF 前缀后取文本；
    记录边界内的 run 才算）。"""
    if d[:4] != b'CSCV':
        return []
    stride = int.from_bytes(d[4:8], 'little'); cnt = int.from_bytes(d[8:12], 'little')
    if not (8 <= stride <= 4096 and 0 < cnt <= 5000 and 16 + stride * cnt <= len(d) + 8):
        return []
    out = []
    for k in range(cnt):
        base = 16 + k * stride
        p = base
        while p < base + stride and p < len(d):
            j = d.find(b'\x00', p, base + stride)
            if j < 0: j = base + stride
            seg = d[p:j]
            q = 0
            while q < len(seg) and seg[q] in (0xFF, 0x00): q += 1
            s = seg[q:]
            if 2 <= len(s) <= 64:
                try: t = s.decode('cp932')
                except Exception: t = None
                if t and t.strip() and not any(ord(c) < 32 for c in t):
                    out.append((p + q, len(s), t))
            p = j + 1
    return out

occ = collections.defaultdict(list)     # text -> [(blob, off, len)]
for bi, b in enumerate(o.blobs):
    for off, ln, t in fields(bytes(b)):
        occ[t].append((bi, off, ln))

print('CSCV 表字段串（去重）: %d' % len(occ))
partial = []
for t, lst in occ.items():
    if len(lst) < 2: continue
    if len({b for b, _, _ in lst}) < 2: continue
    ch = same = 0
    for bi, off, ln in lst:
        a = bytes(o.blobs[bi])[off:off+ln]; b = bytes(n.blobs[bi])[off:off+ln]
        if a != b: ch += 1
        else: same += 1
    if 0 < ch < len(lst):
        partial.append((t, lst, ch, same))

print('★ 表字段中部分翻译的串: %d 个' % len(partial))
print()
print('=== A) 出现次数 <= 20 的（键类风险，逐条列出）===')
small = [p for p in partial if len(p[1]) <= 20]
for t, lst, ch, same in sorted(small, key=lambda x: -len(x[1])):
    mark = ' '.join(('b%d@%d%s' % (b, off, '*' if bytes(o.blobs[b])[off:off+ln] != bytes(n.blobs[b])[off:off+ln] else '')) for b, off, ln in lst)
    print('  %-28r x%-2d 翻%d 未翻%d  %s' % (t, len(lst), ch, same, mark))
print()
print('=== B) 出现次数 > 20 的（仅列串名与计数）===')
for t, lst, ch, same in sorted(partial, key=lambda x: -len(x[1])):
    if len(lst) <= 20: continue
    print('  %-28r x%-4d 翻%d 未翻%d' % (t, len(lst), ch, same))
