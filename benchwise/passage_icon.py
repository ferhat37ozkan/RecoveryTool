"""The Passage icon next to the clock: the shape of the active connection (Wi-Fi waves or an
Ethernet port, like Windows' own network icon), coloured by state - grey off, orange while
switching, green on.  Drawn with Pillow (Windows' own icons are not ours to copy or recolour)."""

from __future__ import annotations

import subprocess

from PIL import Image, ImageDraw

COLORS = {"off": (139, 150, 173, 255), "busy": (245, 160, 50, 255), "on": (62, 207, 142, 255)}
_SS = 4                         # drawn 4x larger, then scaled down: smooth edges


def connection_kind():
    """"wifi" or "ethernet": the medium of the first connected physical adapter."""
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Select-Object -First 1)"
                            ".NdisPhysicalMedium"], capture_output=True, text=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "wifi" if p.stdout.strip() in ("1", "9") else "ethernet"     # 9 = Native 802.11
    except Exception:
        return "ethernet"


def icon(state="off", kind="ethernet", size=32):
    s = size * _SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = COLORS.get(state, COLORS["off"])
    w = max(1, s // 11)                                     # stroke width
    if kind == "wifi":
        cx, base = s / 2, s * 0.86
        for i, r in enumerate((0.80, 0.56, 0.32)):
            rad = s * r
            d.arc([cx - rad, base - rad, cx + rad, base + rad], 225, 315, fill=c, width=w)
        dot = s * 0.09
        d.ellipse([cx - dot, base - dot * 2.2, cx + dot, base - dot * 0.2], fill=c)
    else:                                                   # Ethernet port: a jack with its notch
        m = s * 0.12
        d.rounded_rectangle([m, m * 1.4, s - m, s - m * 1.2], radius=s * 0.12, outline=c, width=w)
        x0, x1 = s * 0.30, s * 0.70
        y0, y1 = s * 0.38, s * 0.72
        d.polygon([(x0, y1), (x0, y0 + s * 0.08), (x0 + s * 0.08, y0 + s * 0.08), (x0 + s * 0.08, y0),
                   (x1 - s * 0.08, y0), (x1 - s * 0.08, y0 + s * 0.08), (x1, y0 + s * 0.08), (x1, y1)], fill=c)
        for i in range(3):                                  # contacts
            x = x0 + s * 0.09 + i * s * 0.11
            d.rectangle([x, y1 - s * 0.10, x + s * 0.05, y1 - s * 0.02], fill=(0, 0, 0, 0))
    return img.resize((size, size), Image.LANCZOS)
