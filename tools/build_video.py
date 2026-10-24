# -*- coding: utf-8 -*-
"""Build Chinese hardsub videos for Half Minute Hero Two.

The story text in these videos is burned into the pixels, so it cannot be
changed through text_v2.csv.  This tool renders an RGBA overlay for every
subtitle segment, composites it with ffmpeg, and replaces the target Ogg
Theora blob inside the S2AR archive.

Targets (see locales/<locale>/video/videos.json):
  res/LANG_EN.s2a  4229ebe4  prologue story cards
  res/LANG_EN.s2a  1297f874  RAGNAROK staff roll + dialogue boxes
  res/MOV.s2a      2afe07ce  opening five lines

The Japanese source videos live in res/LANG_JA.s2a under the same hashes.
This tool reads the *current* text_v2.csv for CSV-backed dialogue rows, so a
package build always uses the latest translation/review data.

Usage:
  python tools/build_video.py --check
  python tools/build_video.py --apply --game-dir "D:\\Games\\Half Minute Hero Two"
  python tools/build_video.py --apply --game-dir <游戏目录> --only prologue,ragnarok
  python tools/build_video.py --apply --game-dir <游戏目录> --only opening

注意：--apply 会原地改写目标目录的归档。`work/original` 是所有打包的母本，
本工具会拒绝写入该目录；请指向游戏安装目录或它的副本。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import s2a

VIDEO_JSON = os.path.join(paths.DATA_DIR, 'video', 'videos.json')
CSV_PATH = os.path.join(paths.DATA_DIR, 'text_v2.csv')
DEFAULT_ARCHIVE = 'res/LANG_EN.s2a'
PRISTINE_DIR = os.path.join(paths.REPO_DIR, 'work', 'original')


def _assert_not_pristine(base_dir: str) -> None:
    """拒绝把视频写进母本目录：母本被改动会污染后续所有打包。"""
    target = os.path.normcase(os.path.abspath(base_dir))
    master = os.path.normcase(os.path.abspath(PRISTINE_DIR))
    if target == master:
        raise SystemExit('拒绝写入母本目录 %s；请用 --game-dir 指向游戏安装目录或其副本'
                         % master)

# ---------------------------------------------------------------- basic utils

def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rgba(value: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    value = (value or '#000000').lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


SERIF_FALLBACKS = ('C:\\Windows\\Fonts\\屏显臻宋.ttf', 'C:\\Windows\\Fonts\\simsun.ttc')


def _font_path(kind: str) -> str:
    """serif = prologue / cinematic text, pixel = game dialogue / opening."""
    if kind == 'serif':
        candidates = (os.environ.get('HMH2_VIDEO_FONT_SERIF'),) + SERIF_FALLBACKS
        for p in candidates:
            if p and os.path.exists(p):
                return p
    p = os.environ.get('HMH2_VIDEO_FONT_PIXEL') or paths.FONT_PATH
    if not os.path.exists(p):
        raise SystemExit('video font not found: %s' % p)
    return p


def _font_family(path: str) -> str:
    """Return the family name libass/fontconfig matches inside `fontsdir`.

    Pillow's getname() returns '????' when a font only ships a localized
    Windows family record, so parse the sfnt name table directly.
    """
    with open(path, 'rb') as fh:
        data = fh.read()
    base = struct.unpack_from('>I', data, 12)[0] if data[:4] == b'ttcf' else 0
    name_off = None
    for i in range(struct.unpack_from('>H', data, base + 4)[0]):
        rec = base + 12 + i * 16
        if data[rec:rec + 4] == b'name':
            name_off = struct.unpack_from('>I', data, rec + 8)[0]
            break
    if name_off is None:
        raise SystemExit('font has no name table: %s' % path)
    count, str_off = struct.unpack_from('>HH', data, name_off + 2)
    tbl = name_off + str_off
    fallback = ''
    for i in range(count):
        r = name_off + 6 + i * 12
        pid, _eid, lid, nid, ln, off = struct.unpack_from('>HHHHHH', data, r)
        if nid != 1:
            continue
        raw = data[tbl + off:tbl + off + ln]
        try:
            fam = raw.decode('utf-16-be') if pid == 3 else raw.decode('mac-roman')
        except Exception:
            continue
        if not fam:
            continue
        if pid == 3 and lid == 0x409:
            return fam
        fallback = fallback or fam
    if fallback:
        return fallback
    raise SystemExit('cannot read font family: %s' % path)


def _ffmpeg() -> str:
    env = os.environ.get('HMH2_FFMPEG')
    if env and os.path.exists(env):
        return env
    for name in ('ffmpeg', 'ffmpeg.exe'):
        p = shutil.which(name)
        if p:
            return p
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit('ffmpeg not found; install imageio-ffmpeg or set HMH2_FFMPEG')


# ---------------------------------------------------------------- ogg probing

def _ogg_info(data: bytes) -> Dict[str, object]:
    """Return codec/resolution/fps/audio-rate/duration from an Ogg blob."""
    if not data.startswith(b'OggS'):
        raise ValueError('not an Ogg stream')
    off = 0
    headers: Dict[int, bytes] = {}
    last: Dict[int, int] = {}
    while off + 27 <= len(data):
        if data[off:off + 4] != b'OggS':
            break
        nseg = data[off + 26]
        segs = data[off + 27:off + 27 + nseg]
        dlen = sum(segs)
        ser = struct.unpack_from('<I', data, off + 14)[0]
        seq = struct.unpack_from('<I', data, off + 18)[0]
        gp = struct.unpack_from('<q', data, off + 6)[0]
        if seq == 0:
            headers[ser] = data[off + 27 + nseg:off + 27 + nseg + min(dlen, 96)]
        last[ser] = gp
        off += 27 + nseg + dlen

    out: Dict[str, object] = {}
    for ser, head in headers.items():
        if head.startswith(b'\x80theora'):
            # Theora identification header: PICW/PICH are 24-bit big-endian.
            picw = int.from_bytes(head[14:17], 'big')
            pich = int.from_bytes(head[17:20], 'big')
            frn = int.from_bytes(head[22:25], 'big')
            frd = int.from_bytes(head[25:28], 'big')
            # Some encoders leave FRN=0 or write the pair in the other order.
            if frn <= 0 or frd <= 0:
                frn, frd = 30, 1
            out['video'] = {
                'codec': 'theora', 'width': picw, 'height': pich,
                'fps_num': frn, 'fps_den': frd,
                'last_granule': last.get(ser, 0),
            }
        elif head.startswith(b'\x01vorbis'):
            rate = int.from_bytes(head[12:16], 'little')
            out['audio'] = {
                'codec': 'vorbis', 'rate': rate,
                'channels': head[11],
                'last_granule': last.get(ser, 0),
            }
    if 'video' not in out:
        raise ValueError('no Theora stream')
    if 'audio' in out:
        a = out['audio']  # type: ignore
        out['duration'] = float(a['last_granule']) / float(a['rate'])
    else:
        out['duration'] = 0.0
    return out


def _probe_bytes(data: bytes) -> Dict[str, object]:
    return _ogg_info(data)


def _video_packet_count(data: bytes) -> int:
    """Count Theora data packets (excluding the 3 header packets).

    libtheora collapses runs of identical frames into fewer packets and jumps
    the granule instead.  The game advances one packet per 1/30s tick, so the
    packet count must cover the whole timeline; counting packets (not decoded
    frames) is the only reliable check.
    """
    off = 0
    serial = None
    count = 0
    headers = 0
    while off + 27 <= len(data):
        if data[off:off + 4] != b'OggS':
            break
        nseg = data[off + 26]
        segs = data[off + 27:off + 27 + nseg]
        dlen = sum(segs)
        ser = struct.unpack_from('<I', data, off + 14)[0]
        payload = data[off + 27 + nseg:off + 27 + nseg + dlen]
        if serial is None and payload.startswith(b'\x80theora'):
            serial = ser
        if ser == serial:
            n = sum(1 for s in segs if s < 255)
            count += n
            if payload[:1] in (b'\x80', b'\x81', b'\x82'):
                headers += 1
        off += 27 + nseg + dlen
    return max(0, count - headers)


# ---------------------------------------------------------------- spec / csv

def load_specs() -> Dict[str, dict]:
    if not os.path.exists(VIDEO_JSON):
        raise SystemExit('video spec not found: %s' % VIDEO_JSON)
    with open(VIDEO_JSON, encoding='utf-8') as fh:
        doc = json.load(fh)
    videos = doc.get('videos') or {}
    if not videos:
        raise SystemExit('video spec has no videos: %s' % VIDEO_JSON)
    return videos


def load_csv_rows() -> Dict[int, dict]:
    rows: Dict[int, dict] = {}
    if not os.path.exists(CSV_PATH):
        return rows
    with open(CSV_PATH, encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            try:
                rows[int(r['row_id'])] = r
            except Exception:
                continue
    return rows


def _csv_zh(row: dict) -> str:
    for key in ('zh_new', 'zh_3dm', 'zh'):
        v = (row.get(key) or '').strip()
        if v:
            return v
    return ''


def resolve_segments(video: dict, csv_rows: Dict[int, dict]) -> List[dict]:
    out: List[dict] = []
    for seg in video.get('segments') or []:
        item = dict(seg)
        if 'csv_row' in seg:
            rid = int(seg['csv_row'])
            row = csv_rows.get(rid)
            if not row:
                raise SystemExit('%s: csv row %s not found' % (seg.get('id'), rid))
            item['zh'] = _csv_zh(row)
            item.setdefault('en', row.get('en') or '')
            item.setdefault('ja', row.get('ja') or '')
            item['source'] = 'text_v2.csv'
        elif 'csv_rows' in seg:
            parts, ens, jas = [], [], []
            for rid in seg['csv_rows']:
                row = csv_rows.get(int(rid))
                if not row:
                    raise SystemExit('%s: csv row %s not found' % (seg.get('id'), rid))
                parts.append(_csv_zh(row))
                ens.append(row.get('en') or '')
                jas.append(row.get('ja') or '')
            join = seg.get('join') or '\n'
            item['zh'] = join.join(parts)
            item.setdefault('en', join.join(ens))
            item.setdefault('ja', join.join(jas))
            item['source'] = 'text_v2.csv'
        else:
            item['source'] = 'video'
        if not (item.get('zh') or '').strip():
            if not seg.get('cover_only'):
                raise SystemExit('%s: empty zh translation' % seg.get('id'))
        try:
            start = float(item['start'])
            end = float(item['end'])
        except Exception:
            raise SystemExit('%s: start/end must be numeric' % seg.get('id'))
        if end <= start:
            raise SystemExit('%s: end <= start' % seg.get('id'))
        item['start'], item['end'] = start, end
        out.append(item)
    if not out:
        raise SystemExit('video %s has no segments' % video.get('blob'))
    return out


# ---------------------------------------------------------------- rendering

def _text_image(text: str, font_path: str, size: int, color: Tuple[int, int, int, int],
                align: str, spacing: int, outline: int, outline_color=(0, 0, 0, 255)) -> Image.Image:
    font = ImageFont.truetype(font_path, size)
    dummy = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(dummy)
    bbox = d.multiline_textbbox((0, 0), text, font=font, spacing=spacing,
                                align=align, stroke_width=outline)
    w = max(1, int(round(bbox[2] - bbox[0])))
    h = max(1, int(round(bbox[3] - bbox[1])))
    pad = int(outline) + 4
    img = Image.new('RGBA', (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.multiline_text((pad - bbox[0], pad - bbox[1]), text, font=font,
                     fill=color, spacing=spacing, align=align,
                     stroke_width=outline,
                     stroke_fill=outline_color if outline else None)
    return img


def _paste_text(canvas: Image.Image, text: str, font_path: str, size: int,
                color: Tuple[int, int, int, int], align: str, x: int, y: int,
                spacing: int, outline: int) -> None:
    img = _text_image(text, font_path, size, color, align, spacing, outline)
    if align == 'center':
        px = int(x - img.width / 2)
    else:
        px = int(x)
    canvas.alpha_composite(img, (px, int(y)))


def _cover(canvas: Image.Image, rect, color: Tuple[int, int, int, int]) -> None:
    x, y, w, h = [int(v) for v in rect[:4]]
    alpha = int(rect[4]) if len(rect) > 4 else color[3]
    patch = Image.new('RGBA', (max(1, w), max(1, h)), (color[0], color[1], color[2], alpha))
    canvas.alpha_composite(patch, (x, y))


def render_overlay(video: dict, seg: dict, out_path: str) -> None:
    width = int(video.get('width') or 1280)
    height = int(video.get('height') or 720)
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    kind = video.get('_kind') or ''

    if kind == 'ragnarok':
        rect = video.get('cover') or [120, 460, width - 240, 190]
        _cover(canvas, rect, _rgba(video.get('box_color') or '#0F0E2D'))
        font = _font_path(video.get('font') or 'pixel')
        x = int(video.get('x') or 150)
        speaker_y = int(video.get('speaker_y') or 485)
        text_y = int(video.get('text_y') or 525)
        speaker = seg.get('speaker') or ''
        if speaker:
            _paste_text(canvas, speaker, font, int(video.get('speaker_size') or 24),
                        (255, 255, 255, 255), 'left', x, speaker_y, 0, 0)
        _paste_text(canvas, seg['zh'], font, int(video.get('line_size') or 26),
                    (255, 255, 255, 255), 'left', x, text_y,
                    int(video.get('line_spacing') or 6), 0)
    else:
        rect = seg.get('cover') or video.get('cover') or [0, 0, width, height]
        color = _rgba(seg.get('cover_color') or video.get('cover_color') or '#000000',
                      int(video.get('cover_alpha') or 255))
        _cover(canvas, rect, color)
        if seg.get('cover_only'):
            pass
        else:
            font = _font_path(seg.get('font') or video.get('font') or 'serif')
            size = int(seg.get('size') or video.get('size') or 44)
            color = _rgba(seg.get('color') or video.get('color') or '#FFFFFF')
            align = seg.get('align') or video.get('align') or 'center'
            x = int(seg.get('x') or video.get('x') or width // 2)
            y = int(seg.get('y') or video.get('y') or height // 2)
            spacing = int(seg.get('line_spacing') or video.get('line_spacing') or 8)
            outline = int(seg.get('outline') or video.get('outline') or 0)
            _paste_text(canvas, seg['zh'], font, size, color, align, x, y, spacing, outline)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path)


def _render_key(video: dict, segments: List[dict], src_blob: bytes, ffmpeg: str) -> str:
    payload = {
        'video': {k: v for k, v in video.items() if k not in ('segments', 'note')},
        'segments': [{k: v for k, v in s.items() if k not in ('source',)} for s in segments],
        'src': _sha256_bytes(src_blob),
        'ffmpeg': ffmpeg,
        'pix_fmt': 'yuv420p',
        'pipeline': 'cfr-dupfix-v6',
        'font_serif': _sha256_file(_font_path('serif')) if os.path.exists(_font_path('serif')) else '',
        'font_pixel': _sha256_file(_font_path('pixel')),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return '%d:%02d:%05.2f' % (h, m, s)


def _ass_text(text: str) -> str:
    return (text or '').replace('\r', '').replace('\n', '\\N')


def _ass_color(value: str, alpha: int = 0) -> str:
    """Convert '#RRGGBB' to ASS '&HAABBGGRR'."""
    value = (value or '#FFFFFF').lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    return '&H%02X%02X%02X%02X' % (alpha, int(value[4:6], 16), int(value[2:4], 16), int(value[0:2], 16))


def _build_ass(video: dict, segments: List[dict], path: str) -> None:
    """Generate an ASS script for scrolling cinematic text / dialogue / opening."""
    kind = video.get('_kind') or ''
    serif_path = _font_path('serif')
    serif_name = _font_family(serif_path)
    pixel_name = 'WenQuanYi Bitmap Song 13px'
    subtitle_size = int(video.get('subtitle_size') or 32)
    # Bottom-centre overlay (opening / Overture staff-roll monologue): no box,
    # just coloured text with a black outline over the original picture.
    center_font = serif_name if (video.get('font') or 'pixel') == 'serif' else pixel_name
    center_size = int(video.get('size') or 34)
    center_color = _ass_color(video.get('color') or '#FFFFFF')
    center_outline = int(video.get('outline') or 2)
    head = [
        '[Script Info]',
        'ScriptType: v4.00+',
        'PlayResX: 1280',
        'PlayResY: 720',
        'WrapStyle: 2',
        'ScaledBorderAndShadow: yes',
        '',
        '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        'Style: Prologue,%s,46,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,0,0,0,1' % serif_name,
        'Style: Title,%s,44,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,5,0,0,0,1' % serif_name,
        'Style: Cover,%s,10,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1' % serif_name,
        'Style: DialogSpeaker,%s,30,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1' % pixel_name,
        'Style: Dialog,%s,32,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1' % pixel_name,
        'Style: Opening,%s,%d,%s,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,%d,0,5,0,0,0,1'
        % (center_font, center_size, center_color, center_outline),
        'Style: Bottom,%s,%d,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1' % (serif_name, subtitle_size),
        '',
        '[Events]',
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
    ]
    lines = list(head)
    for seg in segments:
        start = _ass_time(seg['start'])
        end = _ass_time(seg['end'])
        if kind == 'ragnarok':
            speaker = seg.get('speaker') or ''
            if speaker:
                lines.append('Dialogue: 0,%s,%s,DialogSpeaker,,0,0,0,,{\\an7\\pos(100,482)}%s' % (start, end, _ass_text(speaker)))
            lines.append('Dialogue: 0,%s,%s,Dialog,,0,0,0,,{\\an7\\pos(100,522)}%s' % (start, end, _ass_text(seg['zh'])))
        elif kind in ('opening', 'overture'):
            y = int(seg.get('y') or video.get('y') or 650)
            lines.append('Dialogue: 0,%s,%s,Opening,,0,0,0,,{\\an5\\pos(640,%d)\\fad(100,100)}%s'
                         % (start, end, y, _ass_text(seg['zh'])))
        else:
            # Prologue: do not replace the original scrolling text.  Add one
            # extra bottom subtitle for the whole text block, like the opening.
            lines.append('Dialogue: 0,%s,%s,Bottom,,0,0,0,,{\\an7\\pos(20,80)\\fad(200,200)}%s'
                         % (start, end, _ass_text(seg['zh'])))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
        fh.write('\n')


def _decoded_frames(ffmpeg: str, work: str, name: str) -> int:
    probe = subprocess.run([ffmpeg, '-hide_banner', '-i', name, '-map', '0:v:0', '-f', 'null', '-'],
                           cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    txt = probe.stderr.decode('utf-8', 'replace')
    frames = 0
    for line in txt.splitlines():
        if 'frame=' in line:
            try:
                frames = int(line.split('frame=')[1].split()[0])
            except Exception:
                pass
    return frames


def _last_video_pts(ffmpeg: str, work: str, name: str) -> float:
    probe = subprocess.run([ffmpeg, '-hide_banner', '-i', name, '-vf', 'showinfo', '-f', 'null', '-'],
                           cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    txt = probe.stderr.decode('utf-8', 'replace')
    last = 0.0
    for line in txt.splitlines():
        if 'pts_time:' in line:
            try:
                last = float(line.split('pts_time:')[1].split()[0])
            except Exception:
                pass
    return last


def render_video(video: dict, segments: List[dict], src_blob: bytes, out_path: str,
                 force: bool = False, verbose: bool = True) -> str:
    """Render one video; returns the output path (cache-aware)."""
    ffmpeg = _ffmpeg()
    key = _render_key(video, segments, src_blob, ffmpeg)
    cache_dir = paths.build('video_cache')
    os.makedirs(cache_dir, exist_ok=True)
    blob = video.get('blob') or 'video'
    cache = os.path.join(cache_dir, '%s_%s.ogv' % (blob, key[:20]))
    if os.path.exists(cache) and not force:
        if verbose:
            print('  [video] %s 缓存命中: %s' % (video.get('_kind') or blob, os.path.basename(cache)))
        shutil.copy2(cache, out_path)
        return out_path

    src_info = _probe_bytes(src_blob)
    duration = float(src_info.get('duration') or 0)
    work = paths.build('video_work', '%s_%s' % (blob, key[:12]))
    os.makedirs(work, exist_ok=True)
    src_path = os.path.join(work, 'source.ogv')
    with open(src_path, 'wb') as fh:
        fh.write(src_blob)

    fonts = os.path.join(work, 'fonts')
    os.makedirs(fonts, exist_ok=True)
    serif_src = _font_path('serif')
    serif_dst = 'video_serif' + os.path.splitext(serif_src)[1].lower()
    shutil.copy2(serif_src, os.path.join(fonts, serif_dst))
    shutil.copy2(_font_path('pixel'), os.path.join(fonts, 'wqy.ttf'))
    ass_path = os.path.join(work, 'sub.ass')
    _build_ass(video, segments, ass_path)
    if verbose:
        print('  [video] %s ASS 渲染 %d 段 -> %s' % (video.get('_kind') or blob, len(segments), out_path))
        print('  [video]   字幕字体 %s (%s)' % (_font_family(serif_src), os.path.basename(serif_src)))

    kind = video.get('_kind') or ''
    vf_parts = []
    # Prologue: no cover.  Keep the original (including its English text) and
    # add extra Chinese subtitles, exactly like the opening.  This avoids any
    # frame-timeline modification from covers/conversion.
    if kind == 'ragnarok':
        # The dialogue box already has a fixed position; cover its burned-in
        # English text with the box colour.  Static drawbox does not change
        # frame timing.
        for seg in segments:
            vf_parts.append("drawbox=x=86:y=471:w=1109:h=185:color=0x0F0E2D:t=fill:enable='between(t,%.3f,%.3f)'"
                            % (seg['start'], seg['end']))
    vf_parts.append('ass=sub.ass:fontsdir=fonts')
    # The source is CFR 30fps: static holds are encoded as duplicate packets,
    # so every 1/30s tick has a packet and the last granule equals the packet
    # count (frame index).  A plain re-encode turns those holds into VFR
    # timestamp gaps (fewer packets than ticks); the game advances one packet
    # per 1/30s, so held frames get skipped and the cutscene plays short.
    # Force CFR again so every tick has a real frame, exactly like the source.
    src_frn = int(src_info['video'].get('fps_num') or 30)
    src_frd = int(src_info['video'].get('fps_den') or 1)
    vf_parts.append('fps=%d/%d' % (src_frn, src_frd))
    # The source's last video frame can end well before its audio/container
    # (Overture: 138.73s vs 140.07s).  The game stops the cutscene at the video
    # EOS, which cuts the BGM tail and feels "shortened / out of sync".  Clone
    # the last frame long enough for the video stream to outlive the audio.
    src_last = _last_video_pts(ffmpeg, work, 'source.ogv')
    if src_last and duration:
        # Pad generously then trim to an exact end: the fps filter already
        # extends the last source frame by its own frame interval, so a fixed
        # pad can overshoot the audio (prologue: 93.1s vs 91.7s).
        pad = min(3.0, max(0.7, duration - src_last + 0.8))
        vf_parts.append('tpad=stop_mode=clone:stop_duration=%.2f' % pad)
        vf_parts.append('trim=duration=%.2f' % (duration + 0.35))
    else:
        vf_parts.append('tpad=stop_mode=clone:stop_duration=%.2f'
                        % (0.4 if kind == 'opening' else 0.7))
    # libtheora collapses runs of identical frames into a single packet plus a
    # granule jump.  The game advances one packet per 1/30s tick, so those
    # static holds would be skipped (cutscene plays short).  A 2x2, very dark
    # pixel block that alternates every frame defeats the duplicate detection;
    # it is invisible at 720p and costs almost no bitrate.  (1x1 0x404040 is
    # not reliable: on a fully static card it still collapsed to 97/120.)
    # It must come AFTER tpad/trim, otherwise every cloned tail frame is
    # identical and collapses again.
    vf_parts.append("drawbox=x=1278:y=0:w=2:h=2:color=0x202020:t=fill:"
                    "enable='eq(mod(n,2),0)'")
    vf = ','.join(vf_parts)

    # Single pass only.  `fps=30` is required: it restores the source's CFR
    # duplicate-frame holds (see above).  Do NOT add -t / -shortest: they
    # truncate to the last input frame and drop the cloned tail.
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', 'source.ogv',
           '-map', '0:v:0', '-map', '0:a:0?',
           '-vf', vf,
           '-c:v', 'libtheora', '-q:v', '7', '-pix_fmt', 'yuv420p',
           '-c:a', 'copy', 'out.ogv']
    proc = subprocess.run(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        err = proc.stderr.decode('utf-8', 'replace')[-4000:]
        raise SystemExit('ffmpeg ASS render failed for %s:\n%s' % (blob, err))
    produced = os.path.join(work, 'out.ogv')
    if not os.path.exists(produced) or os.path.getsize(produced) == 0:
        raise SystemExit('ffmpeg produced no output for %s' % blob)
    shutil.copy2(produced, out_path)

    # validate container/codecs/timeline against the source
    with open(out_path, 'rb') as fh:
        out_blob = fh.read()
    out_info = _probe_bytes(out_blob)
    if (src_info['video']['width'], src_info['video']['height']) != (out_info['video']['width'], out_info['video']['height']):
        raise SystemExit('%s: output resolution changed: %r -> %r' % (blob, src_info['video'], out_info['video']))
    if abs(duration - float(out_info['duration'])) > 0.5:
        raise SystemExit('%s: output duration %.2f != source %.2f' % (blob, out_info['duration'], duration))
    out_last = _last_video_pts(ffmpeg, work, 'out.ogv')
    if src_last and out_last and out_last < src_last - 0.15:
        raise SystemExit('%s: output video ends at %.2fs, source at %.2fs (timeline shortened)'
                         % (blob, out_last, src_last))
    if out_last and duration and out_last < duration - 0.4:
        raise SystemExit('%s: video ends at %.2fs, audio %.2fs (game will cut BGM at EOS)'
                         % (blob, out_last, duration))
    if out_last and duration and out_last > duration + 0.9:
        raise SystemExit('%s: output video ends at %.2fs, container %.2fs (padding too long)'
                         % (blob, out_last, duration))
    out_packets = _video_packet_count(out_blob)
    min_packets = int((duration - 0.3) * src_frn / src_frd)
    if out_packets < min_packets:
        raise SystemExit('%s: %d video packets for %.2fs at %d/%d fps - static holds '
                         'were collapsed (game will skip them)'
                         % (blob, out_packets, duration, src_frn, src_frd))
    if verbose:
        print('  [video]   末帧 %.2fs/源 %.2fs/容器 %.2fs  包数 %d'
              % (out_last, src_last, duration, out_packets))
    if verbose:
        v = out_info['video']  # type: ignore
        print('  [video]   %dx%d %.2fs %.1fMB'
              % (v['width'], v['height'], out_info['duration'], len(out_blob) / 1048576.0))
    shutil.copy2(out_path, cache)
    return out_path


# ---------------------------------------------------------------- archive apply

def _load_archive(path: str) -> s2a.Archive:
    if not os.path.exists(path):
        raise SystemExit('archive not found: %s' % path)
    return s2a.Archive(path)


def _replace_blobs(path: str, replacements: Dict[int, bytes]) -> None:
    arc = _load_archive(path)
    originals = [bytes(b) for b in arc.blobs]
    blobs = list(originals)
    changed = set()
    for h, data in replacements.items():
        idx = arc.hash_map().get(h)
        if idx is None:
            raise SystemExit('blob %08x not found in %s' % (h, path))
        blobs[idx] = data
        changed.add(idx)
    s2a.pack(path, arc.entries, blobs)
    # verify every untouched blob is byte-identical
    new = _load_archive(path)
    for i, (a, b) in enumerate(zip(originals, new.blobs)):
        if i not in changed and a != b:
            raise SystemExit('archive %s: untouched blob %d changed unexpectedly' % (path, i))
    for h in replacements:
        idx = new.hash_map()[h]
        if new.blobs[idx] != replacements[h]:
            raise SystemExit('archive %s: replacement %08x not written' % (path, h))


def apply_videos(base_dir: str, only: Optional[Iterable[str]] = None,
                 force: bool = False, verbose: bool = True) -> None:
    """Render and replace all enabled video specs in base_dir."""
    _assert_not_pristine(base_dir)
    specs = load_specs()
    csv_rows = load_csv_rows()
    wanted = set(only) if only else None

    groups: Dict[str, List[Tuple[str, dict, List[dict]]]] = {}
    for kind, video in specs.items():
        if video.get('enabled') is False:
            continue
        if wanted is not None and kind not in wanted:
            continue
        video = dict(video)
        video['_kind'] = kind
        segments = resolve_segments(video, csv_rows)
        archive = os.path.join(base_dir, *video.get('archive', DEFAULT_ARCHIVE).split('/'))
        groups.setdefault(archive, []).append((kind, video, segments))

    if not groups:
        print('  [video] 没有匹配的视频')
        return

    for archive, items in groups.items():
        arc = _load_archive(archive)
        replacements: Dict[int, bytes] = {}
        for kind, video, segments in items:
            h = int(video['blob'], 16)
            idx = arc.hash_map().get(h)
            if idx is None:
                raise SystemExit('%s: blob %08x not found' % (archive, h))
            src_blob = bytes(arc.blobs[idx])
            if verbose:
                print('== video %s (%s / %08x, %.2fs) ==' % (kind, video.get('archive'), h,
                                                              _probe_bytes(src_blob)['duration']))
                for s in segments:
                    print('   %-7s %6.2f-%6.2f  %s' % (s.get('id'), s['start'], s['end'],
                                                        (s.get('zh') or '').replace('\n', ' / ')[:80]))
            out = paths.build('video_out', '%s_%08x.ogv' % (kind, h))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            render_video(video, segments, src_blob, out, force=force, verbose=verbose)
            replacements[h] = open(out, 'rb').read()
        _replace_blobs(archive, replacements)
        if verbose:
            print('  [video] 已重打包 %s（替换 %d 个 blob）' % (archive, len(replacements)))


def check_videos(base_dir: str, only: Optional[Iterable[str]] = None) -> int:
    specs = load_specs()
    csv_rows = load_csv_rows()
    wanted = set(only) if only else None
    errors = 0
    for kind, video in specs.items():
        if video.get('enabled') is False:
            continue
        if wanted is not None and kind not in wanted:
            continue
        try:
            segments = resolve_segments(video, csv_rows)
        except SystemExit as ex:
            print('!! %s: %s' % (kind, ex)); errors += 1; continue
        archive = os.path.join(base_dir, *video.get('archive', DEFAULT_ARCHIVE).split('/'))
        try:
            arc = _load_archive(archive)
            h = int(video['blob'], 16)
            idx = arc.hash_map().get(h)
            if idx is None:
                print('!! %s: blob %08x missing in %s' % (kind, h, archive)); errors += 1; continue
            info = _probe_bytes(bytes(arc.blobs[idx]))
            v = info['video']  # type: ignore
            print('%-10s %-28s %08x  %dx%d  %.2fs  %d 段'
                  % (kind, video.get('archive'), h, v['width'], v['height'],
                     info['duration'], len(segments)))
        except Exception as ex:
            print('!! %s: %r' % (kind, ex)); errors += 1
    print('check: %d error(s)' % errors)
    return errors


# ---------------------------------------------------------------- review view

def export_view(out_path: str) -> None:
    specs = load_specs()
    rows = load_csv_rows()
    entries = []
    for kind, video in specs.items():
        if video.get('enabled') is False:
            continue
        segments = resolve_segments(video, rows)
        for s in segments:
            if s.get('cover_only'):
                continue
            entries.append({
                'id': '%s::%s' % (kind, s.get('id')),
                'video': kind,
                'start': s['start'],
                'end': s['end'],
                'ja': s.get('ja', ''),
                'en': s.get('en', ''),
                'zh': s.get('zh', ''),
                'source': s.get('source', 'video'),
                'note': ('来自 text_v2.csv，改这里不会写回 CSV；请在对应译表行修改'
                         if s.get('source') == 'text_v2.csv' else '视频专用条目；改 zh 后导入会写回 videos.json'),
            })
    doc = {
        '_kind': 'video',
        '_note': '视频硬字幕校对。source=video 的条目可直接改 zh；source=text_v2.csv 的条目请到主译表修改。',
        '_count': len(entries),
        'entries': entries,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    print('video review exported: %s (%d entries)' % (out_path, len(entries)))


def import_view(path: str, write: bool = True) -> int:
    if not os.path.exists(path):
        print('video review not found: %s' % path)
        return 0
    with open(path, encoding='utf-8') as fh:
        doc = json.load(fh)
    with open(VIDEO_JSON, encoding='utf-8') as fh:
        spec_doc = json.load(fh)
    changed = 0
    by_id = {}
    for kind, video in (spec_doc.get('videos') or {}).items():
        for s in video.get('segments') or []:
            by_id['%s::%s' % (kind, s.get('id'))] = (video, s)
    for e in doc.get('entries') or []:
        if e.get('source') == 'text_v2.csv':
            continue
        item = by_id.get(e.get('id'))
        if not item:
            continue
        video, seg = item
        if seg.get('csv_row') or seg.get('csv_rows'):
            continue
        zh = (e.get('zh') or '').strip()
        if not zh:
            continue
        if seg.get('zh') != zh:
            seg['zh'] = zh
            changed += 1
    if changed and write:
        with open(VIDEO_JSON, 'w', encoding='utf-8') as fh:
            json.dump(spec_doc, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
    if write:
        print('video review imported: %d change(s)' % changed)
    return changed


# ---------------------------------------------------------------- CLI

def _split_only(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [x.strip() for x in value.split(',') if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description='Build video hardsubs for HMH2.')
    ap.add_argument('--game-dir', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--only', default=None, help='comma list: prologue,ragnarok,opening')
    ap.add_argument('--force', action='store_true', help='ignore render cache')
    ap.add_argument('--export-review', default=None)
    ap.add_argument('--import-review', default=None)
    args = ap.parse_args()

    if args.game_dir:
        os.environ['HMH2_GAME_DIR'] = args.game_dir
    base = os.environ.get('HMH2_GAME_DIR') or paths.GAME_DIR

    if args.export_review:
        export_view(args.export_review)
        return 0
    if args.import_review:
        import_view(args.import_review)
        return 0
    if args.check or not args.apply:
        return check_videos(base, _split_only(args.only))
    apply_videos(base, _split_only(args.only), force=args.force)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
