// fix_exports.js — 去除 dinput8.dll 导出名的 @N stdcall 装饰（原位截断字符串）
// 原理：导出名字符串按 NUL 终止读取；把 '@' 处改写为 0x00 即等效改名为 undecorated，
//       名字指针表 RVA 不动，地址表不动。改写前后均重新校验。
const fs = require('fs');
const FILE = process.argv[2] || 'dinput8.dll';
const d = fs.readFileSync(FILE);
const e = d.readUInt32LE(0x3C);
const nsec = d.readUInt16LE(e + 6);
const optsz = d.readUInt16LE(e + 20);
const opt = e + 24;
const magic = d.readUInt16LE(opt);
const secTab = opt + optsz;
const secs = [];
for (let i = 0; i < nsec; i++) {
  const s = secTab + i * 40;
  secs.push({
    va: d.readUInt32LE(s + 12), vs: d.readUInt32LE(s + 8),
    raw: d.readUInt32LE(s + 20), rs: d.readUInt32LE(s + 16),
  });
}
function rva2off(rva) {
  for (const s of secs) if (rva >= s.va && rva < s.va + Math.max(s.vs, s.rs)) return s.raw + (rva - s.va);
  return null;
}
const ddir = magic === 0x10b ? opt + 96 : opt + 112;
const expRVA = d.readUInt32LE(ddir);
const eo = rva2off(expRVA);
const nNames = d.readUInt32LE(eo + 24);
const namesOff = rva2off(d.readUInt32LE(eo + 32));
let fixed = 0;
const before = [];
for (let i = 0; i < nNames; i++) {
  const nOff = rva2off(d.readUInt32LE(namesOff + i * 4));
  let name = '';
  while (d[nOff + name.length] !== 0) name += String.fromCharCode(d[nOff + name.length]);
  before.push(name);
  const at = name.indexOf('@');
  if (at >= 0) {
    d[nOff + at] = 0; // 截断
    fixed++;
  }
}
if (fixed > 0) fs.writeFileSync(FILE, d);
console.log('before: ' + before.join(', '));
console.log('fixed ' + fixed + ' names -> ' + FILE);
