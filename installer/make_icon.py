"""Draws installer/icon.ico (a gold-edged shield on burgundy) with the standard library only. Run: python installer/make_icon.py"""
import math
import struct
import zlib
from pathlib import Path

BG1, BG2, GOLD, DARK = (140, 58, 88), (80, 28, 52), (212, 184, 131), (30, 21, 25)


def shield(x, y, k):
    """Inside a shield of relative size k? x, y in -1..1."""
    x, y = x / k, y / k
    if y < -0.85 or y > 1.0:
        return False
    half = 0.74 if y <= 0.05 else 0.74 * math.sqrt(max(0.0, 1 - ((y - 0.05) / 0.95) ** 2))
    return abs(x) <= half


def pixel(x, y):
    if not (-1 <= x <= 1 and -1 <= y <= 1):
        return None
    r = 0.22  # rounded square
    cx, cy = max(abs(x) - (1 - r), 0), max(abs(y) - (1 - r), 0)
    if cx * cx + cy * cy > r * r:
        return None
    t = (y + 1) / 2
    col = tuple(int(BG1[i] * (1 - t) + BG2[i] * t) for i in range(3))
    if shield(x, y, 0.78):
        col = GOLD
        if shield(x, y, 0.66):
            col = DARK
            if abs(x) + abs(y + 0.05) < 0.27:
                col = GOLD
    return col


def png(size):
    rows, ss = [], 3
    for j in range(size):
        row = bytearray([0])
        for i in range(size):
            acc, a = [0, 0, 0], 0
            for sj in range(ss):
                for si in range(ss):
                    c = pixel((i + (si + .5) / ss) / size * 2 - 1, (j + (sj + .5) / ss) / size * 2 - 1)
                    if c:
                        a += 1
                        acc = [acc[n] + c[n] for n in range(3)]
            n = max(a, 1)
            row += bytes([acc[0] // n, acc[1] // n, acc[2] // n, a * 255 // (ss * ss)])
        rows.append(bytes(row))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def main():
    sizes = [256, 64, 48, 32, 16]
    imgs = [png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    entries = b""
    for s, d in zip(sizes, imgs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(d), off)
        off += len(d)
    out = Path(__file__).with_name("icon.ico")
    out.write_bytes(head + entries + b"".join(imgs))
    print("wrote", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
