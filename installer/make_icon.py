"""Draws installer/icon.ico: three glowing layers (a load order) stacked on a deep indigo tile.
Standard library only. Run: python installer/make_icon.py   (add --preview to also write icon-preview.png)"""
import struct
import sys
import zlib
from pathlib import Path

BG_TOP, BG_BOTTOM = (52, 36, 118), (16, 14, 44)
# (top face, side) from the bottom layer to the top one
LAYERS = [((30, 140, 150), (16, 86, 104)), ((72, 200, 178), (36, 128, 128)), ((255, 205, 84), (205, 135, 40))]
A, B, T = 0.64, 0.30, 0.13      # half width, half height and thickness of a layer
CENTERS = [0.30, 0.04, -0.22]   # vertical centres, bottom layer first


def mix(c1, c2, t):
    return tuple(c1[i] + (c2[i] - c1[i]) * t for i in range(3))


def layer_hit(x, y, cy):
    """-> 'top', 'side' or None for a slab whose top face is a diamond centred at (0, cy)."""
    w = 1 - abs(x) / A
    if w < 0:
        return None
    lo, hi = cy - B * w, cy + B * w
    if lo <= y <= hi:
        return "top"
    if hi < y <= hi + T:
        return "side"
    return None


def pixel(x, y):
    r = 0.24  # rounded tile
    cx, cy = max(abs(x) - (1 - r), 0), max(abs(y) - (1 - r), 0)
    if abs(x) > 1 or abs(y) > 1 or cx * cx + cy * cy > r * r:
        return None
    col = mix(BG_TOP, BG_BOTTOM, (y + 1) / 2)
    glow = max(0.0, 1 - ((x * x) / 0.9 + ((y + 0.05) ** 2) / 0.9)) ** 2
    col = mix(col, (96, 78, 190), glow * 0.55)
    for (top, side), c in zip(LAYERS, CENTERS):
        hit = layer_hit(x, y, c)
        if hit == "top":
            shade = 1 + 0.10 * (1 - (y - c + B) / (2 * B))  # lighter towards the back edge
            col = tuple(min(255, v * shade) for v in top)
            if abs(x) + abs(y - c) * (A / B) > A * 0.93:    # thin lighter rim along the diamond edge
                col = mix(col, (255, 255, 255), 0.28)
        elif hit == "side":
            col = side
    return tuple(int(v) for v in col)


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
    if "--preview" in sys.argv:
        Path(__file__).with_name("icon-preview.png").write_bytes(imgs[0])


if __name__ == "__main__":
    main()
