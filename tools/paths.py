# -*- coding: utf-8 -*-
"""Shared path/config resolver for the localization toolchain.

Resolution order for each value:
  1) environment variable (explicit override, e.g. HMH2_GAME_DIR)
  2) config.local.json (or $HMH2_CONFIG) in the repository root
  3) a repository-relative default

config.local.json keys:
  game_dir   - path to the game install (contains HMH2.exe, res/, DLC01/)
  font_path  - font used to render glyphs (relative to repo root or absolute)
  locale     - e.g. "zh-CN"
  build_dir  - scratch/output dir (default: <repo>/build)
  dist_dir   - release output dir (default: <repo>/dist)
"""
import os
import json

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TOOLS_DIR)


def _load_cfg():
    path = os.environ.get('HMH2_CONFIG') or os.path.join(REPO_DIR, 'config.local.json')
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


_CFG = _load_cfg()


def _resolve(name, key, default):
    val = os.environ.get(name)
    if val:
        return val
    val = _CFG.get(key)
    if val:
        return val
    return default


LOCALE = _resolve('HMH2_LOCALE', 'locale', 'zh-CN')

GAME_DIR = _resolve('HMH2_GAME_DIR', 'game_dir', REPO_DIR)

DATA_DIR = _resolve('HMH2_DATA_DIR', 'data_dir',
                    os.path.join(REPO_DIR, 'locales', LOCALE))

_font = _resolve('HMH2_FONT_PATH', 'font_path',
                 os.path.join(REPO_DIR, 'assets', 'fonts', 'WenQuanYi Bitmap Song 13px.ttf'))
FONT_PATH = _font if os.path.isabs(_font) else os.path.join(REPO_DIR, _font)

BUILD_DIR = _resolve('HMH2_BUILD_DIR', 'build_dir', os.path.join(REPO_DIR, 'build'))
DIST_DIR = _resolve('HMH2_DIST_DIR', 'dist_dir', os.path.join(REPO_DIR, 'dist'))


def game(*parts):
    return os.path.join(GAME_DIR, *parts)


def data(*parts):
    return os.path.join(DATA_DIR, *parts)


def build(*parts):
    os.makedirs(BUILD_DIR, exist_ok=True)
    return os.path.join(BUILD_DIR, *parts)


def dist(*parts):
    os.makedirs(DIST_DIR, exist_ok=True)
    return os.path.join(DIST_DIR, *parts)
