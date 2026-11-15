"""Row icons of the result browser, drawn here so that no image files or libraries are needed.

Each icon is a tick box (empty / ticked / partly) followed by a state mark (recovered = green
check, waiting = grey ring, ...).  They are rasterised with supersampling at the size the
display scaling asks for and handed to Tk as PNG data.
"""

from __future__ import annotations

import base64
import struct
import zlib

UNIT = 16                   # every shape below is described on a 16 x 16 grid
_SS = 4

ACCENT, MUTED, GOOD, WARN, BAD, WHITE, DARK = (
    (47, 124, 246), (139, 150, 173), (62, 207, 142), (245, 184, 75), (242, 109, 109), (255, 255, 255), (15, 20, 32))


def _circle(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _ring(cx, cy, r, w):
    return lambda x, y: (r - w) ** 2 <= (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _box(x0, y0, x1, y1, rad):
    def inside(x, y):
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False
        dx = x0 + rad - x if x < x0 + rad else x - (x1 - rad) if x > x1 - rad else 0
        dy = y0 + rad - y if y < y0 + rad else y - (y1 - rad) if y > y1 - rad else 0
        return dx * dx + dy * dy <= rad * rad
    return inside


def _frame(x0, y0, x1, y1, rad, w):
    outer, inner = _box(x0, y0, x1, y1, rad), _box(x0 + w, y0 + w, x1 - w, y1 - w, max(rad - w, 0.1))
    return lambda x, y: outer(x, y) and not inner(x, y)


def _line(x0, y0, x1, y1, w):
    dx, dy = x1 - x0, y1 - y0
    length = dx * dx + dy * dy

    def inside(x, y):
        k = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / length))
        return (x - x0 - k * dx) ** 2 + (y - y0 - k * dy) ** 2 <= w * w / 4
    return inside


def _either(*shapes):
    return lambda x, y: any(s(x, y) for s in shapes)


_CHECK = _either(_line(4.4, 8.4, 7.0, 11.0, 1.9), _line(7.0, 11.0, 11.8, 5.4, 1.9))

# painted in order; later shapes cover earlier ones
TICKS = {
    0: [(_frame(1.5, 1.5, 14.5, 14.5, 3, 1.4), MUTED)],
    1: [(_box(1.5, 1.5, 14.5, 14.5, 3), ACCENT), (_CHECK, WHITE)],
    2: [(_box(1.5, 1.5, 14.5, 14.5, 3), ACCENT), (_line(4.8, 8, 11.2, 8, 2), WHITE)],
}
MARKS = {
    "ok": [(_circle(8, 8, 7), GOOD), (_CHECK, DARK)],
    "warn": [(_circle(8, 8, 7), WARN), (_CHECK, DARK)],
    "bad": [(_circle(8, 8, 7), BAD), (_line(8, 4.2, 8, 8.8, 2), DARK), (_circle(8, 11.6, 1.15), DARK)],
    "fail": [(_ring(8, 8, 6.6, 1.4), BAD), (_line(5.6, 5.6, 10.4, 10.4, 1.6), BAD), (_line(10.4, 5.6, 5.6, 10.4, 1.6), BAD)],
    "pending": [(_ring(8, 8, 6.4, 1.5), MUTED)],
    "part": [(_ring(8, 8, 6.6, 1.5), GOOD), (_circle(8, 8, 2.6), GOOD)],
    "none": [],
}


def _render(shapes, size):
    """One icon as ``size`` rows of RGBA bytes."""
    rows, step = [], UNIT / (size * _SS)
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = hit = 0
            for sy in range(_SS):
                y = (py * _SS + sy + 0.5) * step
                for sx in range(_SS):
                    x = (px * _SS + sx + 0.5) * step
                    for inside, color in reversed(shapes):
                        if inside(x, y):
                            r, g, b, hit = r + color[0], g + color[1], b + color[2], hit + 1
                            break
            row += bytes((r // hit, g // hit, b // hit, 255 * hit // (_SS * _SS))) if hit else b"\0\0\0\0"
        rows.append(row)
    return rows


def _png(width, rows):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, len(rows), 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def build(scale=1.0):
    """{(tick, mark): base64 PNG} for every combination; pass each to ``tk.PhotoImage(data=...)``."""
    size = max(12, int(round(UNIT * scale)))
    gap = max(2, size // 4)
    ticks = {k: _render(v, size) for k, v in TICKS.items()}
    marks = {k: _render(v, size) for k, v in MARKS.items()}
    space = bytes(4 * gap)
    out = {}
    for tk_, trows in ticks.items():
        for mk, mrows in marks.items():
            rows = [a + space + b + space for a, b in zip(trows, mrows)]
            out[(tk_, mk)] = base64.b64encode(_png(2 * size + 2 * gap, rows))
    return out
