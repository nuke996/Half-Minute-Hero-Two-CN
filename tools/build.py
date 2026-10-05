# -*- coding: utf-8 -*-
"""Unified build entry point for the Half Minute Hero Two zh-CN localization.

Usage
-----
  python tools/build.py --game-dir "D:\\Games\\Half Minute Hero Two" plan
  python tools/build.py --game-dir "D:\\Games\\Half Minute Hero Two" apply_menu
  python tools/build.py --game-dir "D:\\Games\\Half Minute Hero Two" revert

The command is forwarded to tools/build_cn.py. See BUILDING.md for the full
command list (plan / apply / apply_menu / revert / check / dlc_only / ...).

The game directory may also be set through config.local.json ("game_dir") or
the HMH2_GAME_DIR environment variable; --game-dir has the highest priority.
"""
import os
import sys
import argparse
import subprocess

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description='Half Minute Hero Two zh-CN build entry point.')
    ap.add_argument('--game-dir', default=None, help='game install directory (overrides config)')
    ap.add_argument('--locale', default=None, help='locale code, e.g. zh-CN')
    ap.add_argument('--config', default=None, help='path to config.local.json')
    ap.add_argument('--exe-mode', choices=['dll', 'exe'], default=None,
                    help="exe patch mode: 'dll' (runtime proxy, default) or 'exe' (offline rewrite)")
    ap.add_argument('cmd', nargs='?', default='plan',
                    help='plan | apply | apply_menu | revert | check | dlc_only | ...')
    ap.add_argument('rest', nargs=argparse.REMAINDER)
    args = ap.parse_args()

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    if args.game_dir:
        env['HMH2_GAME_DIR'] = args.game_dir
    if args.locale:
        env['HMH2_LOCALE'] = args.locale
    if args.config:
        env['HMH2_CONFIG'] = args.config
    if args.exe_mode:
        env['HMH2_EXE_MODE'] = args.exe_mode

    cmd = [sys.executable, os.path.join(TOOLS_DIR, 'build_cn.py'), args.cmd] + list(args.rest)
    return subprocess.call(cmd, env=env)


if __name__ == '__main__':
    sys.exit(main())
