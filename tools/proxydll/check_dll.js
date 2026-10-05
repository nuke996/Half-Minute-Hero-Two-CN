// check_dll.js — verify built dinput8.dll: machine, exports, imports
const fs = require('fs');
const d = fs.readFileSync(process.argv[2] || 'dinput8.dll');
const e = d.readUInt32LE(0x3C);
const machine = d.readUInt16LE(e + 4);
const nsec = d.readUInt16LE(e + 6);
const optsz = d.readUInt16LE(e + 20);
const opt = e + 24;
const magic = d.readUInt16LE(opt);
const imgbase = d.readUInt32LE(opt + 28);
const secTab = opt + optsz;
const secs = [];
for (let i = 0; i < nsec; i++) {
  const s = secTab + i * 40;
  secs.push({
    name: d.toString('ascii', s, s + 8).replace(/\0+$/, ''),
    va: d.readUInt32LE(s + 12), vs: d.readUInt32LE(s + 8),
    raw: d.readUInt32LE(s + 20), rs: d.readUInt32LE(s + 16),
  });
}
function rva2off(rva) {
  for (const s of secs) if (rva >= s.va && rva < s.va + Math.max(s.vs, s.rs)) return s.raw + (rva - s.va);
  return null;
}
console.log('machine = 0x' + machine.toString(16), machine === 0x14c ? '(i386/x86 32-bit OK)' : '(WRONG!)');
console.log('magic = 0x' + magic.toString(16), magic === 0x10b ? '(PE32 OK)' : '(WRONG!)');

// exports
const ddir = magic === 0x10b ? opt + 96 : opt + 112;
const expRVA = d.readUInt32LE(ddir), expSize = d.readUInt32LE(ddir + 4);
if (expRVA === 0) {
  console.log('EXPORTS: NONE (BAD!)');
} else {
  const eo = rva2off(expRVA);
  const nNames = d.readUInt32LE(eo + 24);
  const namesRVA = d.readUInt32LE(eo + 32);
  const namesOff = rva2off(namesRVA);
  console.log('EXPORTS (' + nNames + '):');
  let allOk = true;
  const want = ['DirectInput8Create', 'DllCanUnloadNow', 'DllGetClassObject', 'DllRegisterServer', 'DllUnregisterServer'];
  for (let i = 0; i < nNames; i++) {
    const nRva = d.readUInt32LE(namesOff + i * 4);
    const nOff = rva2off(nRva);
    let name = '';
    while (d[nOff + name.length] !== 0) name += String.fromCharCode(d[nOff + name.length]);
    const ok = want.includes(name);
    if (!ok) allOk = false;
    console.log('  ' + name + (ok ? '  OK' : '  DECORATED/UNEXPECTED!'));
  }
  console.log(allOk ? '=> 导出名全部正确 (undecorated)' : '=> 需要修正导出名!');
}
// imports
const impRVA = d.readUInt32LE(ddir + 8);
if (impRVA) {
  const io = rva2off(impRVA);
  const dlls = [];
  let idx = 0;
  while (true) {
    const desc = io + idx * 20;
    const nameRva = d.readUInt32LE(desc + 12);
    if (!nameRva) break;
    const nOff = rva2off(nameRva);
    let name = '';
    while (d[nOff + name.length] !== 0) name += String.fromCharCode(d[nOff + name.length]);
    dlls.push(name);
    idx++;
  }
  console.log('IMPORTS: ' + dlls.join(', '));
}
