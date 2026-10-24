# -*- coding: utf-8 -*-
"""Build isolated video-only test packages (video-only dist folders).

These test packages reuse one existing text/name package's archives verbatim
and only replace the video blobs, so a video regression cannot be confused with
a text/name regression.  Nothing is installed into work/original or the Steam
game directory.

Modes:
  remux   : ffmpeg -c copy (original Theora packets, new Ogg pages)
  plain   : ffmpeg libtheora re-encode, no subtitle overlay
  hardsub : Pillow overlay + ffmpeg libtheora (current Chinese video)

Usage:
  python tools/package_video_test.py --mode hardsub --base dist/Z17-display-fill
  python tools/package_video_test.py --mode hardsub --only overture --out-dir dist/Z17-video

--base 指定文字/机制名的底包（默认 dist/Z17-display-fill）。底包重建后请用
--base 指向新目录，避免测试到旧译文。--only 只重渲染指定视频（逗号分隔）；
未选中的视频沿用底包里的现有版本。--out-dir 指定输出目录。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import s2a
import build_video

DEFAULT_BASE = os.path.join(paths.DIST_DIR, 'Z17-display-fill')
ORIG_MOV = os.path.join(paths.GAME_DIR, 'res', 'MOV.s2a')


def _ffmpeg():
    return build_video._ffmpeg()


def _extract(archive_path, h):
    arc = s2a.Archive(archive_path)
    idx = arc.hash_map().get(h)
    if idx is None:
        raise SystemExit('blob %08x not found in %s' % (h, archive_path))
    return bytes(arc.blobs[idx])


def _check(in_path, out_path):
    a = build_video._probe_bytes(open(in_path, 'rb').read())
    b = build_video._probe_bytes(open(out_path, 'rb').read())
    va, vb = a['video'], b['video']
    if (va['width'], va['height']) != (vb['width'], vb['height']):
        raise SystemExit('resolution changed %s -> %s' % (in_path, out_path))
    if abs(float(a['duration']) - float(b['duration'])) > 0.25:
        raise SystemExit('duration changed %s -> %s' % (in_path, out_path))
    print('   %s -> %.2fs %dx%d %.1fMB'
          % (os.path.basename(out_path), b['duration'], vb['width'], vb['height'],
             os.path.getsize(out_path) / 1048576.0))


def _transcode(src_blob, work, mode):
    ff = _ffmpeg()
    inp = os.path.join(work, 'in.ogv')
    out = os.path.join(work, 'out.ogv')
    with open(inp, 'wb') as fh:
        fh.write(src_blob)
    if mode == 'remux':
        args = [ff, '-hide_banner', '-loglevel', 'error', '-y', '-i', inp,
                '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', out]
    elif mode == 'plain':
        args = [ff, '-hide_banner', '-loglevel', 'error', '-y', '-i', inp,
                '-map', '0:v:0', '-map', '0:a:0',
                '-c:v', 'libtheora', '-q:v', '7', '-pix_fmt', 'yuv420p', '-c:a', 'copy', out]
    else:
        raise SystemExit('bad transcode mode: %s' % mode)
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit('ffmpeg %s failed for %s:\n%s'
                         % (mode, inp, proc.stderr.decode('utf-8', 'replace')[-3000:]))
    _check(inp, out)
    return open(out, 'rb').read()


def _render_hardsub(video, segments, src_blob, work):
    out = os.path.join(work, 'out.ogv')
    build_video.render_video(video, segments, src_blob, out, force=True, verbose=True)
    return open(out, 'rb').read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['remux', 'plain', 'hardsub'], required=True)
    ap.add_argument('--base', default=DEFAULT_BASE,
                    help='文字/机制名底包目录（默认 dist/Z17-display-fill）')
    ap.add_argument('--only', default='',
                    help='只处理这些视频（逗号分隔，如 overture）')
    ap.add_argument('--out-dir', default='',
                    help='输出目录（默认 dist/<底包名>-video-<mode>）')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    base = os.path.abspath(args.base)
    base_lang = os.path.join(base, 'res', 'LANG_EN.s2a')
    if not os.path.exists(base_lang):
        raise SystemExit('text/name base package not found: %s' % base_lang)
    out_dir = os.path.abspath(args.out_dir) if args.out_dir else os.path.join(
        paths.DIST_DIR, '%s-video-%s' % (os.path.basename(base), args.mode))
    if os.path.normcase(out_dir) == os.path.normcase(base):
        raise SystemExit('输出目录不能与底包相同: %s' % out_dir)
    out_lang = os.path.join(out_dir, 'res', 'LANG_EN.s2a')
    out_mov = os.path.join(out_dir, 'res', 'MOV.s2a')
    if os.path.isdir(out_dir) and args.force:
        shutil.rmtree(out_dir)
    os.makedirs(os.path.dirname(out_lang), exist_ok=True)
    os.makedirs(os.path.dirname(out_mov), exist_ok=True)

    only = set(x.strip() for x in args.only.split(',') if x.strip()) or None
    print('== %s ==' % os.path.basename(out_dir))
    print('  base text/names: %s' % base_lang)
    print('  original MOV   : %s' % ORIG_MOV)

    specs = build_video.load_specs()
    rows = build_video.load_csv_rows()
    lang = s2a.Archive(base_lang)
    lang_blobs = [bytes(b) for b in lang.blobs]
    replacements = {}

    lang_kinds = [k for k, v in specs.items()
                  if k != 'opening' and v.get('enabled') is not False
                  and (only is None or k in only)]
    for kind in lang_kinds:
        video = dict(specs[kind]); video['_kind'] = kind
        h = int(video['blob'], 16)
        idx = lang.hash_map().get(h)
        if idx is None:
            raise SystemExit('%s: blob %08x missing in base LANG_EN' % (kind, h))
        src = lang_blobs[idx]
        work = paths.build('video_test', '%s_%s' % (args.mode, kind))
        if os.path.isdir(work):
            shutil.rmtree(work)
        os.makedirs(work, exist_ok=True)
        if args.mode == 'hardsub':
            segs = build_video.resolve_segments(video, rows)
            data = _render_hardsub(video, segs, src, work)
        else:
            data = _transcode(src, work, args.mode)
        replacements[h] = data

    # LANG_EN: same text/names as the base package, only video blobs changed.
    if replacements:
        tmp_lang = out_lang + '.tmp'
        shutil.copy2(base_lang, tmp_lang)
        build_video._replace_blobs(tmp_lang, replacements)
        os.replace(tmp_lang, out_lang)
    else:
        shutil.copy2(base_lang, out_lang)

    # MOV: the opening is already translated in the base package; only rebuild
    # it when requested, otherwise carry the base version over unchanged.
    if only is None or 'opening' in only:
        mov = s2a.Archive(ORIG_MOV)
        h = int(specs['opening']['blob'], 16)
        idx = mov.hash_map()[h]
        src = bytes(mov.blobs[idx])
        work = paths.build('video_test', '%s_opening' % args.mode)
        if os.path.isdir(work):
            shutil.rmtree(work)
        os.makedirs(work, exist_ok=True)
        if args.mode == 'hardsub':
            v = dict(specs['opening']); v['_kind'] = 'opening'
            segs = build_video.resolve_segments(v, rows)
            data = _render_hardsub(v, segs, src, work)
        else:
            data = _transcode(src, work, args.mode)
        shutil.copy2(ORIG_MOV, out_mov)
        build_video._replace_blobs(out_mov, {h: data})
    else:
        base_mov = os.path.join(base, 'res', 'MOV.s2a')
        shutil.copy2(base_mov if os.path.exists(base_mov) else ORIG_MOV, out_mov)

    note = os.path.join(out_dir, '测试说明.txt')
    with open(note, 'w', encoding='utf-8') as fh:
        fh.write('%s\n\n' % os.path.basename(out_dir))
        fh.write('这是只替换视频的测试包，文字/机制名取自：%s\n' % base)
        fh.write('把本目录 res\\LANG_EN.s2a 覆盖到游戏 res\\LANG_EN.s2a；\n')
        fh.write('把本目录 res\\MOV.s2a 覆盖到游戏 res\\MOV.s2a。\n')
        fh.write('先备份游戏原文件。底包中的其他文件不要动。\n')
        if args.mode == 'remux':
            fh.write('本包只把原视频重新封装为新的 Ogg 页结构，不重编码；用于判断容器/页结构是否被游戏接受。\n')
        elif args.mode == 'plain':
            fh.write('本包用 ffmpeg libtheora 重编码但不加字幕；用于判断编码器/码流是否被游戏接受。\n')
        else:
            fh.write('本包是当前中文硬字幕版本；用于判断遮盖/合成是否影响播放。\n')
        if only:
            fh.write('本轮重渲染的视频：%s；其余视频沿用底包。\n' % ', '.join(sorted(only)))
    print('done: %s' % out_dir)
    print('  %s' % out_lang)
    print('  %s' % out_mov)


if __name__ == '__main__':
    raise SystemExit(main())
