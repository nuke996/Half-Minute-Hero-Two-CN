# -*- coding: utf-8 -*-
"""统一 runner：已设 cwd 为 _work，参数只传脚本名（可选再传该脚本的参数）。"""
import os, sys, subprocess
import paths
W = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
args = sys.argv[1:]
if not args:
    raise SystemExit('用法: runner.py <脚本名> [参数...]')
script = args[0]
out = os.path.join(paths.build(), os.path.splitext(os.path.basename(script))[0] + '_run.txt')
p = subprocess.run([PY, script] + args[1:], cwd=W, capture_output=True)
buf = []
buf.append('=== returncode %d ===' % p.returncode)
buf.append('--- stdout ---')
buf.append(p.stdout.decode('utf-8', 'replace'))
buf.append('--- stderr ---')
buf.append(p.stderr.decode('utf-8', 'replace'))
open(out, 'w', encoding='utf-8').write('\n'.join(buf))
print('->', out, 'rc=%d' % p.returncode)
