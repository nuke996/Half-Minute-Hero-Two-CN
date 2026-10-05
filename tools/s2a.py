# -*- coding: utf-8 -*-
"""
S2A archive tool for Half Minute Hero Two (勇者30: 再次降临)

Archive format (verified):
    magic  : b'S2AR'              (4 bytes)
    count  : uint32 LE            number of entries
    index  : count * ( uint32 hash, uint32 size )   -- sorted ascending by hash
    data   : blobs concatenated in index order (no padding)

Files inside an archive are addressed ONLY by hash (no filenames).
"""

import os
import struct

MAGIC = b"S2AR"


class Archive:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            magic, count = struct.unpack("<4sI", fh.read(8))
            if magic != MAGIC:
                raise ValueError("not an S2AR file: %s" % path)
            raw = fh.read(count * 8)
            self.entries = [
                struct.unpack_from("<II", raw, i * 8) for i in range(count)
            ]
            self.data_start = 8 + count * 8
            self.blobs = []
            for _h, s in self.entries:
                self.blobs.append(fh.read(s))

    @property
    def count(self):
        return len(self.entries)

    def hashes(self):
        return [h for h, _s in self.entries]

    def hash_map(self):
        return {h: i for i, (h, _s) in enumerate(self.entries)}


def extract(archive_path, out_dir, prefix=""):
    """Dump every blob to out_dir as <hash:08x>.bin"""
    os.makedirs(out_dir, exist_ok=True)
    a = Archive(archive_path)
    for (h, s), blob in zip(a.entries, a.blobs):
        with open(os.path.join(out_dir, "%s%08x.bin" % (prefix, h)), "wb") as fh:
            fh.write(blob)
    return a


def pack(archive_path, entries, blobs):
    """entries: list of (hash, size) - size is recalculated from blobs."""
    entries = [(h, len(b)) for (h, _s), b in zip(entries, blobs)]
    with open(archive_path, "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<I", len(entries)))
        for h, s in entries:
            fh.write(struct.pack("<II", h, s))
        for b in blobs:
            fh.write(b)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: s2a.py <archive.s2a> <outdir>")
        raise SystemExit(1)
    a = extract(sys.argv[1], sys.argv[2])
    print("%s: %d entries" % (sys.argv[1], a.count))
