// gen_patch_bin.js — 生成外置补丁数据 hm2zh_patch.bin（供 dinput8 代理 DLL 运行时应用）
// 补丁内容 = build_cn.py patch_exe_unlock() (v2.11/v2.14, EXPAND_4096=True) 的运行时等价物
// 自测：将补丁虚拟应用到 HMH2.exe.bak，与当前装机 HMH2.exe 的 .text 区逐字节比对，必须完全一致
//
// bin 格式（小端）：
//   Header 16B: 'H2ZP' | u16 ver=1 | u16 flags=0 | u32 imagebase=0x400000 | u32 count
//   Type1 记录: u8 type=1 | u8 len | u8 window=0 | u8 rsv | u32 va | u32 expect=0 | u32 delta=0 | orig[len] | new[len]
//   Type2 记录: u8 type=2 | u8 len=0 | u8 window | u8 rsv | u32 va | u32 expect | u32 delta (相对 atbl 基址)
const fs = require('fs');
const path = require('path');
const REPO = path.resolve(__dirname, '..', '..');
function gameDir() {
  if (process.env.HMH2_GAME_DIR) return process.env.HMH2_GAME_DIR;
  const cfg = path.join(REPO, 'config.local.json');
  if (fs.existsSync(cfg)) {
    try { const j = JSON.parse(fs.readFileSync(cfg, 'utf8')); if (j.game_dir) return j.game_dir; } catch (e) {}
  }
  return REPO;
}
const ROOT = gameDir();
const BAK = path.join(ROOT, 'HMH2.exe.bak');
const CUR = path.join(ROOT, 'HMH2.exe');
const OUT = path.join(REPO, 'build', 'hm2zh_patch.bin');
fs.mkdirSync(path.dirname(OUT), { recursive: true });

const IMG_BASE = 0x400000;
const A_TBL_VA = 0x5F4000;      // 运行时 VirtualAlloc 目标（坐标表 16KB + 排序表 16KB）
const A_TBL_VA_SORT = 0x5F8000;

// ---- 文件偏移转换（无 ASLR，VA==内存地址；fileoff = 0x400 + (VA - 0x401000)） ----
function va2off(d, va) {
  const e = d.readUInt32LE(0x3C);
  const nsec = d.readUInt16LE(e + 6);
  const optsz = d.readUInt16LE(e + 20);
  const opt = e + 24;
  const imgbase = d.readUInt32LE(opt + 28);
  const secTab = opt + optsz;
  const rva = va - imgbase;
  for (let i = 0; i < nsec; i++) {
    const s = secTab + i * 40;
    const sva = d.readUInt32LE(s + 12), svs = d.readUInt32LE(s + 8);
    const raw = d.readUInt32LE(s + 20), rsz = d.readUInt32LE(s + 16);
    if (rva >= sva && rva < sva + Math.max(svs, rsz)) return raw + (rva - sva);
  }
  throw new Error('VA 0x' + va.toString(16) + ' 无节映射');
}

const bak = fs.readFileSync(BAK);
const cur = fs.readFileSync(CUR);

function expectBytes(va, hex) {
  const p = va2off(bak, va);
  const want = Buffer.from(hex, 'hex');
  const got = bak.slice(p, p + want.length);
  if (!got.equals(want)) {
    throw new Error(`0x${va.toString(16)} 处原字节不匹配\n  期望: ${want.toString('hex')}\n  实际: ${got.toString('hex')}`);
  }
  return { va, orig: got };
}

// ---- Type1 记录：orig 必须逐字节匹配，new 为写入值 ----
const T1 = [
  // [va, origHex, newHex, 说明]
  [0x4D895B, '81FFFC130000', '81FFFC3F0000', 'cmp edi,0x13FC -> cmp edi,0x3FFC (4N-4, 解 1280 上限)'],
  [0x4D861F, 'BBFF040000',   'BBFF0F0000',   'mov ebx,0x4FF -> mov ebx,0xFFF (二分 hi=N-1)'],
  [0x4D8624, 'B980040000',   'B900080000',   'mov ecx,0x480 -> mov ecx,0x800 (二分 mid=N/2)'],
  [0x4D88D9, 'C1E909',       'C1E90B',       'shr ecx,9 -> shr ecx,11 (建表 x 移位)'],
  [0x4D8E36, '251F000080',   '253F000080',   'and eax,0x8000001F -> and eax,0x8000003F (V 掩码 &63)'],
  [0x4D8DE6, '0FBE4102',     '0FB64102',     'movsx -> movzx (坐标字节1)'],
  [0x4D8DF6, '0FBE4903',     '0FB64903',     'movsx -> movzx (坐标字节2)'],
  [0x4D8E13, '0FBE4102',     '0FB64102',     'movsx -> movzx (坐标字节3)'],
  [0x4D8E2A, '0FBE4103',     '0FB64103',     'movsx -> movzx (坐标字节4)'],
  [0x4D8E02, '9981E2FF030000 03C2 C1F80A 83C03E'.replace(/ /g, ''),
             'C1E80A 83E001 83C83E 909090909090'.replace(/ /g, ''),
             '页号公式: 62+i/1024 -> 62+((i>>10)&1) + 6x nop'],
].map(([va, origHex, newHex, desc]) => {
  const { orig } = expectBytes(va, origHex);
  const nw = Buffer.from(newHex, 'hex');
  if (orig.length !== nw.length) throw new Error(`记录 0x${va.toString(16)} orig/new 长度不等`);
  return { type: 1, va, window: 0, expect: 0, delta: 0, orig, new: nw, desc };
});

// ---- Type2 记录：在 va 起 window 字节内搜索 u32 expect，替换为 atbl_base + delta ----
const T2 = [
  [0x4D88E9, 0x5D36E6, 6,      '坐标表基址1 (0x5D36E6 -> atbl+6)'],
  [0x4D88EF, 0x5D36E7, 7,      '坐标表基址2 (0x5D36E7 -> atbl+7)'],
  [0x4D88F5, 0x5D36E4, 4,      '坐标表基址3 (0x5D36E4 -> atbl+4)'],
  [0x4D891A, 0x5D36E5, 5,      '坐标表基址4 (0x5D36E5 -> atbl+5)'],
  [0x4D8630, 0x5D4AE0, 0x4000, '排序表基址1 (0x5D4AE0 -> sort)'],
  [0x4D868C, 0x5D4AE0, 0x4000, '排序表基址2'],
  [0x4D8932, 0x5D4AE0, 0x4000, '排序表基址3'],
  [0x4D8920, 0x5D4AE4, 0x4004, '排序表基址4 (0x5D4AE4 -> sort+4)'],
].map(([va, expect, delta, desc]) => {
  // 校验 .bak 中 window 内确实存在 expect
  const p = va2off(bak, va);
  const win = bak.slice(p, p + 12);
  const needle = Buffer.from([expect & 0xFF, (expect >>> 8) & 0xFF, (expect >>> 16) & 0xFF, (expect >>> 24) & 0xFF]);
  const idx = win.indexOf(needle);
  if (idx < 0) throw new Error(`Type2 0x${va.toString(16)} 窗口内未找到 expect=0x${expect.toString(16)}`);
  return { type: 2, va, window: 12, expect, delta, orig: null, new: null, desc };
});

const records = [...T1, ...T2];

// ---- 写 bin ----
const hdr = Buffer.alloc(16);
hdr.write('H2ZP', 0, 'ascii');
hdr.writeUInt16LE(1, 4);
hdr.writeUInt16LE(0, 6);
hdr.writeUInt32LE(IMG_BASE, 8);
hdr.writeUInt32LE(records.length, 12);
const chunks = [hdr];
for (const r of records) {
  const h = Buffer.alloc(16);
  h.writeUInt8(r.type, 0);
  h.writeUInt8(r.orig ? r.orig.length : 0, 1);
  h.writeUInt8(r.window, 2);
  h.writeUInt8(0, 3);
  h.writeUInt32LE(r.va, 4);
  h.writeUInt32LE(r.expect, 8);
  h.writeUInt32LE(r.delta, 12);
  chunks.push(h);
  if (r.orig) { chunks.push(r.orig); chunks.push(r.new); }
}
fs.writeFileSync(OUT, Buffer.concat(chunks));
console.log(`已生成 ${OUT} (${records.length} 条记录, ${Buffer.concat(chunks).length} 字节)`);

// ---- 自测：虚拟应用到 .bak 副本，与当前装机 exe 比对 ----
function applyPatch(d, atblBase) {
  const dd = Buffer.from(d); // copy
  const w32 = (off, v) => { dd[off] = v & 0xFF; dd[off + 1] = (v >>> 8) & 0xFF; dd[off + 2] = (v >>> 16) & 0xFF; dd[off + 3] = (v >>> 24) & 0xFF; };
  for (const r of records) {
    const p = va2off(dd, r.va);
    if (r.type === 1) {
      const got = dd.slice(p, p + r.orig.length);
      if (!got.equals(r.orig)) throw new Error(`应用时校验失败 0x${r.va.toString(16)}: ${got.toString('hex')}`);
      r.new.copy(dd, p);
    } else {
      const win = dd.slice(p, p + r.window);
      const needle = Buffer.from([r.expect & 0xFF, (r.expect >>> 8) & 0xFF, (r.expect >>> 16) & 0xFF, (r.expect >>> 24) & 0xFF]);
      const idx = win.indexOf(needle);
      if (idx < 0 || idx > r.window - 4) throw new Error(`应用时未找到 0x${r.va.toString(16)} expect=0x${r.expect.toString(16)}`);
      w32(p + idx, atblBase + r.delta);
    }
  }
  return dd;
}

// 固定基址 0x5F4000 场景
const sameExe = bak.equals(cur);
const sim = applyPatch(bak, A_TBL_VA);
// .text 节范围 = rawoff 0x400..0x17FE00；比对该区间
const tOff = 0x400, tSize = 0x17FA00;
let diffs = 0, firstDiffs = [];
for (let i = tOff; i < tOff + tSize; i++) {
  if (sim[i] !== cur[i]) { diffs++; if (firstDiffs.length < 10) firstDiffs.push(i); }
}
console.log(`自测(固定基址): .text 区差异字节数 = ${diffs}`);
if (sameExe) {
  console.log('（HMH2.exe 为原版 / DLL 模式，跳过与装机 exe 的逐字节比对）');
} else if (diffs === 0) {
  console.log('✅ 虚拟应用结果与当前装机 HMH2.exe 的 .text 完全一致');
} else {
  for (const o of firstDiffs) console.log(`  首个差异 off=0x${o.toString(16)} VA=0x${(0x401000 + o - 0x400).toString(16)} sim=${sim[o].toString(16)} cur=${cur[o].toString(16)}`);
  process.exitCode = 1;
}
// 回退基址场景只做烟雾测试（类型2 全部可应用、无异常）
const sim2 = applyPatch(bak, 0x710000);
console.log('自测(回退基址 0x710000): 应用成功, 记录数=' + records.length);
