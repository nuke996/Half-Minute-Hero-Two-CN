// dump PE import table of HMH2.exe (original .bak) + check loaded-DLL proxy candidates
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const d = fs.readFileSync(path.join(ROOT, 'HMH2.exe.bak'));

const e = d.readUInt32LE(0x3C);
const nsec = d.readUInt16LE(e + 6);
const optsz = d.readUInt16LE(e + 20);
const opt = e + 24;
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
const magic = d.readUInt16LE(opt);
const ddirOff = magic === 0x10b ? opt + 96 : opt + 112;
const impRVA = d.readUInt32LE(ddirOff + 8);   // DataDirectory[1] = Import Table
const impOff = rva2off(impRVA);
console.log('ImageBase=0x' + imgbase.toString(16), 'ImportDir RVA=0x' + impRVA.toString(16));

let out = [];
let idx = 0;
while (true) {
  const desc = impOff + idx * 20;
  const oft = d.readUInt32LE(desc), nameRVA = d.readUInt32LE(desc + 12), ft = d.readUInt32LE(desc + 16);
  if (!nameRVA) break;
  const nOff = rva2off(nameRVA);
  let dll = '';
  while (d[nOff + dll.length] !== 0) dll += String.fromCharCode(d[nOff + dll.length]);
  // count functions (via FirstThunk / OriginalFirstThunk)
  let thunk = rva2off(oft || ft), fcount = 0;
  while (thunk && d.readUInt32LE(thunk + fcount * 4) !== 0) fcount++;
  out.push(`${dll}  (${fcount} functions)`);
  idx++;
}
console.log('--- Imports (' + idx + ' DLLs) ---');
console.log(out.join('\n'));

// proxy candidates check: which of the common proxy targets exist in imports?
const common = ['version.dll', 'winmm.dll', 'dinput8.dll', 'dinput.dll', 'dsound.dll', 'd3d9.dll', 'xinput1_3.dll', 'xinput9_1_0.dll', 'winhttp.dll', 'dbghelp.dll', 'msvcr90.dll', 'kernel32.dll', 'user32.dll', 'd3d8.dll', 'opengl32.dll', 'shell32.dll', 'shlwapi.dll', 'uxtheme.dll', 'iphlpapi.dll', 'ws2_32.dll'];
const lower = out.map(s => s.toLowerCase());
console.log('\n--- Proxy candidate check ---');
for (const c of common) {
  const hit = lower.find(s => s.startsWith(c));
  console.log(`${c.padEnd(18)} ${hit ? 'IMPORTED ' + hit : '-'}`);
}
