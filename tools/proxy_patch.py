# -*- coding: utf-8 -*-
"""Generate hm2zh_patch.bin - runtime patch data for the dinput8 proxy DLL.

The records are the exact equivalents of build_cn.patch_exe_unlock(): they unlock
the character-table 1280 limit up to 4096 (new .atbl data area + immediates).

Binary format (little-endian):
  Header 16B : b'H2ZP' | u16 ver=1 | u16 flags=0 | u32 imagebase=0x400000 | u32 count
  Type1 rec  : u8 type=1 | u8 len | u8 window=0 | u8 rsv=0 | u32 va | u32 expect=0 | u32 delta=0 | orig[len] | new[len]
  Type2 rec  : u8 type=2 | u8 len=0 | u8 window    | u8 rsv=0 | u32 va | u32 expect  | u32 delta

Each Type1 record is verified byte-for-byte against HMH2.exe.bak before being
emitted; each Type2 expect value must be present in its window.  This mirrors
proxydll/gen_patch_bin.js (kept as reference) but avoids the Node dependency.
"""
import os
import struct

IMG_BASE = 0x400000

# type1: (va, orig_hex, new_hex)
T1 = [
    (0x4D895B, '81FFFC130000', '81FFFC3F0000'),   # cmp edi,0x13FC -> 0x3FFC (4N-4)
    (0x4D861F, 'BBFF040000', 'BBFF0F0000'),       # mov ebx,0x4FF -> 0xFFF (hi=N-1)
    (0x4D8624, 'B980040000', 'B900080000'),       # mov ecx,0x480 -> 0x800 (mid=N/2)
    (0x4D88D9, 'C1E909', 'C1E90B'),               # shr ecx,9 -> shr ecx,11
    (0x4D8E36, '251F000080', '253F000080'),       # and eax,&31 -> &63 (V mask)
    (0x4D8DE6, '0FBE4102', '0FB64102'),           # movsx -> movzx (1)
    (0x4D8DF6, '0FBE4903', '0FB64903'),           # movsx -> movzx (2)
    (0x4D8E13, '0FBE4102', '0FB64102'),           # movsx -> movzx (3)
    (0x4D8E2A, '0FBE4103', '0FB64103'),           # movsx -> movzx (4)
    (0x4D8E02, '9981E2FF03000003C2C1F80A83C03E',
               'C1E80A83E00183C83E909090909090'),  # page = 62+((i>>10)&1)
]

# type2: (va, expect_u32, delta_rel_atbl)
T2 = [
    (0x4D88E9, 0x5D36E6, 6),
    (0x4D88EF, 0x5D36E7, 7),
    (0x4D88F5, 0x5D36E4, 4),
    (0x4D891A, 0x5D36E5, 5),
    (0x4D8630, 0x5D4AE0, 0x4000),
    (0x4D868C, 0x5D4AE0, 0x4000),
    (0x4D8932, 0x5D4AE0, 0x4000),
    (0x4D8920, 0x5D4AE4, 0x4004),
]


def _sections(d):
    pe = struct.unpack_from('<I', d, 0x3C)[0]
    if d[pe:pe + 4] != b'PE\0\0':
        raise ValueError('不是 PE 文件')
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    optsz = struct.unpack_from('<H', d, pe + 20)[0]
    sec_tab = pe + 24 + optsz
    out = []
    for i in range(nsec):
        o = sec_tab + i * 40
        vsize, vaddr, rawsz, rawptr = struct.unpack_from('<IIII', d, o + 8)
        out.append((vaddr, vsize, rawptr, rawsz))
    return out


def va2off(d, va):
    rva = va - IMG_BASE
    for vaddr, vsize, rawptr, rawsz in _sections(d):
        if vaddr <= rva < vaddr + max(vsize, rawsz):
            return rawptr + (rva - vaddr)
    raise ValueError('VA 0x%X 无节映射' % va)


def build(bak_path, out_path):
    """Write hm2zh_patch.bin from an original HMH2.exe.bak. Returns out_path."""
    d = open(bak_path, 'rb').read()
    buf = bytearray()
    buf += b'H2ZP' + struct.pack('<HHII', 1, 0, IMG_BASE, len(T1) + len(T2))
    for va, oh, nh in T1:
        orig = bytes.fromhex(oh)
        new = bytes.fromhex(nh)
        if len(orig) != len(new):
            raise ValueError('T1 长度不等 @0x%X' % va)
        p = va2off(d, va)
        got = d[p:p + len(orig)]
        if got != orig:
            raise ValueError('原字节不符 @0x%X: 期望 %s 实际 %s' % (va, orig.hex(), got.hex()))
        buf += struct.pack('<BBBBIII', 1, len(orig), 0, 0, va, 0, 0) + orig + new
    for va, exp, delta in T2:
        p = va2off(d, va)
        if struct.pack('<I', exp) not in d[p:p + 12]:
            raise ValueError('窗口内未找到 expect=0x%X @0x%X' % (exp, va))
        buf += struct.pack('<BBBBIII', 2, 0, 12, 0, va, exp, delta)
    d_out = os.path.dirname(out_path)
    if d_out:
        os.makedirs(d_out, exist_ok=True)
    with open(out_path, 'wb') as fh:
        fh.write(buf)
    return out_path


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        raise SystemExit('用法: python proxy_patch.py <HMH2.exe.bak> <out.hm2zh_patch.bin>')
    print(build(sys.argv[1], sys.argv[2]))
