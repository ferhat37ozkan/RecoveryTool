"""Card icons, drawn with Pillow so that no image files are needed.

Every icon is a white line drawing on a 24 x 24 grid, placed on a rounded tile in its category's
colour.  Drawn four times larger and scaled down, so the edges stay smooth at any display scale.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

GRID = 24
_SS = 4
WHITE = (255, 255, 255, 255)

COLORS = {
    "disk": (47, 124, 246), "system": (139, 92, 246), "power": (34, 170, 110), "display": (235, 130, 50),
    "network": (20, 164, 196), "windows": (58, 110, 220), "cleanup": (214, 76, 140),
}
MUTED = (70, 82, 108)


class _Pen:
    def __init__(self, draw, scale, width=1.8):
        self.d, self.k, self.w = draw, scale, width

    def p(self, x, y):
        return (x * self.k, y * self.k)

    def _cap(self, x, y, w):
        r = w * self.k / 2
        cx, cy = self.p(x, y)
        self.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE)

    def line(self, *pts, w=None):
        w = w or self.w
        self.d.line([self.p(x, y) for x, y in pts], fill=WHITE, width=max(1, round(w * self.k)), joint="curve")
        for x, y in pts:
            self._cap(x, y, w)

    def rect(self, x0, y0, x1, y1, r=2, w=None, fill=False):
        w = w or self.w
        box = (*self.p(x0, y0), *self.p(x1, y1))
        if fill:
            self.d.rounded_rectangle(box, radius=r * self.k, fill=WHITE)
        else:
            self.d.rounded_rectangle(box, radius=r * self.k, outline=WHITE, width=max(1, round(w * self.k)))

    def circle(self, cx, cy, r, w=None, fill=False):
        w = w or self.w
        box = (*self.p(cx - r, cy - r), *self.p(cx + r, cy + r))
        if fill:
            self.d.ellipse(box, fill=WHITE)
        else:
            self.d.ellipse(box, outline=WHITE, width=max(1, round(w * self.k)))

    def arc(self, cx, cy, r, start, end, w=None):
        """Degrees, 0 = east, clockwise (as Pillow)."""
        w = w or self.w
        box = (*self.p(cx - r, cy - r), *self.p(cx + r, cy + r))
        self.d.arc(box, start, end, fill=WHITE, width=max(1, round(w * self.k)))
        for a in (start, end):
            self._cap(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)), w)

    def poly(self, *pts, fill=True):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=WHITE if fill else None,
                       outline=None if fill else WHITE)


# -- drawings ------------------------------------------------------------------------------------
def _disk(p):
    p.rect(3, 6, 21, 18, 3)
    p.line((3, 13.5), (21, 13.5))
    p.circle(17, 16, 0.9, fill=True)
    p.line((6.5, 16), (11, 16))


def _recover(p):
    _disk_small(p)
    p.arc(12, 9, 5, 200, 340)
    p.poly((16.6, 4.6), (17.9, 8.8), (13.8, 8.0))


def _disk_small(p):
    p.rect(4, 13, 20, 20, 2.5)
    p.circle(16.5, 16.5, 0.9, fill=True)


def _pulse(p):
    p.rect(3, 4, 21, 20, 3)
    p.line((5.5, 12.5), (9, 12.5), (10.5, 8.5), (13.5, 16), (15, 12.5), (18.5, 12.5))


def _grid(p):
    for i in range(3):
        for j in range(3):
            x, y = 4.5 + i * 5.5, 4.5 + j * 5.5
            p.rect(x, y, x + 4, y + 4, 1, fill=(i, j) != (1, 1) and (i, j) != (2, 0), w=1.5)


def _wrench(p):
    p.line((5, 19), (13, 11), w=3)
    p.arc(15.5, 8.5, 4.2, 120, 400, w=2)


def _copy(p):
    p.rect(8, 8, 19, 19, 2)
    p.line((5, 15), (5, 7), (7, 5), (15, 5))


def _pie(p):
    p.arc(12, 12, 8, 270, 540)
    p.poly((12, 12), (12, 3.2), (14.9, 3.7), (17.3, 5.0), (19.2, 7.1), (20.4, 9.8), (20.8, 12))


def _shred(p):
    p.rect(5, 3.5, 19, 11, 1.5)
    p.line((3.5, 12.5), (20.5, 12.5))
    for x in (7, 10, 13, 16):
        p.line((x + 0.5, 15), (x + 0.5, 20.5), w=1.6)


def _gauge(p):
    p.arc(12, 14, 8, 180, 360)
    p.line((12, 14), (16.5, 9), w=2)
    p.circle(12, 14, 1.4, fill=True)
    p.line((4, 18.5), (20, 18.5))


def _chip(p):
    p.rect(6.5, 6.5, 17.5, 17.5, 2)
    p.rect(9.5, 9.5, 14.5, 14.5, 1, fill=True)
    for v in (9.5, 12, 14.5):
        p.line((v, 3), (v, 5.5), w=1.5)
        p.line((v, 18.5), (v, 21), w=1.5)
        p.line((3, v), (5.5, v), w=1.5)
        p.line((18.5, v), (21, v), w=1.5)


def _info(p):
    p.circle(12, 12, 8.5)
    p.circle(12, 8, 1.1, fill=True)
    p.line((12, 11), (12, 16.5), w=2)


def _memory(p):
    p.rect(3, 7, 21, 15, 1.5)
    for x in (6.5, 10.5, 14.5):
        p.rect(x, 9.5, x + 2.5, 12.5, 0.5, fill=True)
    for x in (5, 8, 11, 14, 17, 19.5):
        p.line((x, 15), (x, 18), w=1.4)


def _bolt(p):
    p.poly((13.5, 2.5), (5.5, 13.5), (11, 13.5), (9.5, 21.5), (18.5, 10), (12.8, 10), (14.5, 2.5))


def _flame(p):
    p.line((12, 3), (16.5, 9), (17.5, 14), (15.5, 18.5), (12, 20.5), (8.5, 18.5), (6.5, 14), (8, 10), (10, 12),
           (12, 3))


def _battery(p):
    p.rect(3, 7, 19, 17, 2.5)
    p.rect(19.5, 10, 21.5, 14, 0.8, fill=True)
    p.rect(5.5, 9.5, 11.5, 14.5, 1, fill=True)


def _moon(p):
    p.circle(11, 13, 8, fill=True)
    p.d.ellipse((*p.p(9.5, 1.5), *p.p(23, 15)), fill=(0, 0, 0, 0))     # cut out: a crescent remains
    p.circle(18, 18, 0.9, fill=True)
    p.circle(20.5, 13.5, 0.7, fill=True)


def _monitor(p):
    p.rect(3, 4, 21, 16, 2)
    p.line((12, 16), (12, 19.5))
    p.line((8, 20), (16, 20))


def _pixels(p):
    p.rect(3, 4, 21, 16, 2)
    for x, y in ((7, 8), (11, 11), (15, 8)):
        p.rect(x, y, x + 2, y + 2, 0.4, fill=True)
    p.line((8, 20), (16, 20))


def _keyboard(p):
    p.rect(2.5, 6.5, 21.5, 17.5, 2)
    for y in (9.5, 12.5):
        for x in range(5, 20, 3):
            p.rect(x, y, x + 1.6, y + 1.4, 0.3, fill=True)
    p.line((8, 15.5), (16, 15.5), w=1.5)


def _mouse(p):
    p.rect(7, 3, 17, 21, 5)
    p.line((12, 5.5), (12, 9.5), w=1.6)


def _speaker(p):
    p.poly((4, 9.5), (8, 9.5), (13, 5), (13, 19), (8, 14.5), (4, 14.5))
    p.arc(13, 12, 4, 300, 420)
    p.arc(13, 12, 7.5, 305, 415)


def _camera(p):
    p.rect(3, 7, 21, 19, 2.5)
    p.line((8.5, 7), (10, 4.5), (14, 4.5), (15.5, 7))
    p.circle(12, 13, 3.6)


def _globe(p):
    p.circle(12, 12, 8.5)
    p.line((3.5, 12), (20.5, 12))
    p.arc(12, 12, 8.5, 0, 0.01)
    p.d.ellipse((*p.p(8, 3.5), *p.p(16, 20.5)), outline=WHITE, width=round(1.6 * p.k))


def _route(p):
    p.circle(6, 18, 2.2)
    p.circle(18, 6, 2.2)
    p.line((8, 17), (13, 15), (11, 9.5), (16, 7.2))


def _wifi(p):
    p.arc(12, 18, 13, 225, 315)
    p.arc(12, 18, 8.5, 225, 315)
    p.arc(12, 18, 4, 225, 315)
    p.circle(12, 18.5, 1.3, fill=True)


def _ethernet(p):
    p.rect(5, 4, 19, 15, 1.5)
    p.line((9, 7), (9, 9))
    p.line((12, 7), (12, 9))
    p.line((15, 7), (15, 9))
    p.line((9, 15), (9, 18), (15, 18), (15, 15))
    p.line((12, 18), (12, 21))


def _bluetooth(p):
    p.line((7, 7.5), (16.5, 16), (12, 20.5), (12, 3.5), (16.5, 8), (7, 16.5))


def _lock(p):
    p.rect(5, 11, 19, 20.5, 2)
    p.arc(12, 11, 4.5, 180, 360)
    p.line((7.5, 11), (7.5, 10.8))
    p.line((16.5, 11), (16.5, 10.8))
    p.circle(12, 15.5, 1.3, fill=True)


def _bars(p):
    for i, h in enumerate((5, 9, 13, 17)):
        x = 5 + i * 4.3
        p.line((x, 20), (x, 20 - h), w=2.4)


def _refresh(p):
    p.arc(12, 12, 7.5, 30, 300)
    p.poly((16.5, 2.8), (19.5, 6.8), (14.6, 7.8))


def _windows(p):
    for x, y in ((4, 4), (12.6, 4), (4, 12.6), (12.6, 12.6)):
        p.rect(x, y, x + 7.4, y + 7.4, 1, fill=True)


def _shield(p):
    p.line((12, 3), (19.5, 6), (19.5, 11.5), (17.5, 16.5), (12, 21), (6.5, 16.5), (4.5, 11.5), (4.5, 6), (12, 3))
    p.line((8.5, 12), (11, 14.5), (15.5, 9.5), w=2)


def _rocket(p):
    p.line((12, 2.5), (15.5, 7), (15.5, 15), (8.5, 15), (8.5, 7), (12, 2.5))
    p.circle(12, 9.5, 1.5)
    p.line((8.5, 12), (5.5, 16), (8.5, 16))
    p.line((15.5, 12), (18.5, 16), (15.5, 16))
    p.line((10.5, 18), (10.5, 20.5), w=1.5)
    p.line((13.5, 18), (13.5, 20.5), w=1.5)


def _broom(p):
    p.line((19.5, 3.5), (12, 11), w=2)
    p.poly((9.5, 9.5), (14.5, 14.5), (10, 21), (3, 14))
    p.d.line([p.p(6, 17), p.p(8.5, 14.5)], fill=COLORS_CURRENT[0], width=round(1.2 * p.k))


COLORS_CURRENT = [(0, 0, 0)]          # tile colour, for the few drawings that cut lines into a fill

DRAWINGS = {name[1:]: fn for name, fn in globals().items() if name.startswith("_") and callable(fn)
            and name not in ("_Pen", "_disk_small")}


def tile(name, color_key, size, enabled=True):
    """A ``size`` x ``size`` RGBA image: the drawing on a rounded tile."""
    big = size * _SS
    color = COLORS.get(color_key, MUTED) if enabled else MUTED
    COLORS_CURRENT[0] = color
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.26, fill=color + (255,))
    inset = big * 0.2
    pen = _Pen(d, (big - 2 * inset) / GRID)
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pen.d = ImageDraw.Draw(layer)
    pen.k = (big - 2 * inset) / GRID
    DRAWINGS.get(name, _info)(pen)
    img.alpha_composite(layer, (round(inset), round(inset)))
    return img.resize((size, size), Image.LANCZOS)


def badge(name, size, color):
    """A small plain drawing in ``color`` (for the shield on admin tools)."""
    big = size * _SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    pen = _Pen(ImageDraw.Draw(img), big / GRID, width=2.2)
    DRAWINGS[name](pen)
    r, g, b = color
    px = img.load()
    for y in range(big):
        for x in range(big):
            a = px[x, y][3]
            if a:
                px[x, y] = (r, g, b, a)
    return img.resize((size, size), Image.LANCZOS)


# -- temperature icons for the notification area --------------------------------------------------
# default tile / digit colours of the clock icons: chosen for contrast on light and dark taskbars
TEMP_COLORS = {"good": ("#17804a", "#ffffff"), "warning": ("#f0a020", "#111111"), "bad": ("#c62828", "#ffffff"),
               "unknown": ("#5a647d", "#ffffff")}


def _rgb(value, fallback):
    try:
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except (AttributeError, ValueError, IndexError):
        return _rgb(fallback, "#808080") if fallback != value else (128, 128, 128)
_FONTS = ("segoeuib.ttf", "arialbd.ttf")


def _font(size):
    from PIL import ImageFont
    import os
    for name in _FONTS:
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def temp_icon(temp, level="good", size=32, colors=None):
    """The number of degrees on a rounded tile coloured by ``level`` ("?" when not reported).
    ``colors``: {level: (tile "#rrggbb", digits "#rrggbb")}, the user's choice; defaults otherwise."""
    big = size * _SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    default_bg, default_fg = TEMP_COLORS.get(level, TEMP_COLORS["unknown"])
    bg, fg = (colors or {}).get(level, (default_bg, default_fg))
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=_rgb(bg, default_bg) + (255,))
    text = "?" if temp is None else str(int(round(temp)))
    fsize = int(big * (0.80 if len(text) <= 2 else 0.58))
    font = _font(fsize)
    box = d.textbbox((0, 0), text, font=font)
    x = (big - (box[2] - box[0])) / 2 - box[0]
    y = (big - (box[3] - box[1])) / 2 - box[1]
    d.text((x, y), text, font=font, fill=_rgb(fg, default_fg) + (255,))
    return img.resize((size, size), Image.LANCZOS)
