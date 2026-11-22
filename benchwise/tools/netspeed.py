"""Network > Speed & Ping: download, upload and latency against Cloudflare's public speed test
endpoints (speed.cloudflare.com), and the route to the internet (tracert)."""

from __future__ import annotations

import statistics
import threading
import time
import urllib.request

import customtkinter as ctk

from recoverytool.i18n import t

from .. import __version__, ui
from ..toolkit import ToolView, card, note, run_command, texts

texts({
    "ns_how": ("Measures against Cloudflare's speed test servers (speed.cloudflare.com) for about 20 seconds. "
               "Close downloads and video for an honest result. No personal data is sent; the test data is random.",
               "Yaklaşık 20 saniye boyunca Cloudflare'in hız testi sunucularına karşı ölçer. Doğru sonuç için "
               "indirmeleri ve videoları kapatın. Kişisel veri gönderilmez; test verisi rastgeledir."),
    "ns_start": ("Start the test", "Testi başlat"),
    "ns_down": ("Download", "İndirme"),
    "ns_up": ("Upload", "Yükleme"),
    "ns_ping": ("Latency", "Gecikme"),
    "ns_jitter": ("Jitter", "Dalgalanma"),
    "ns_mbps": ("{v} Mbit/s", "{v} Mbit/sn"),
    "ns_ms": ("{v} ms", "{v} ms"),
    "ns_phase_ping": ("Measuring latency…", "Gecikme ölçülüyor…"),
    "ns_phase_down": ("Measuring download…", "İndirme ölçülüyor…"),
    "ns_phase_up": ("Measuring upload…", "Yükleme ölçülüyor…"),
    "ns_done": ("Done · server: {where}", "Bitti · sunucu: {where}"),
    "ns_failed": ("The test could not reach the server: {err}", "Test sunucuya ulaşamadı: {err}"),
    "ns_route": ("Route to the internet", "İnternete giden yol"),
    "ns_route_how": ("Each line is one hop between you and Cloudflare (1.1.1.1). A hop with * only means it does "
                     "not answer pings; a big jump in ms shows where the delay starts.",
                     "Her satır sizinle Cloudflare (1.1.1.1) arasındaki bir adımdır. * olan adım yalnızca ping'e "
                     "yanıt vermiyor demektir; ms değerindeki büyük sıçrama gecikmenin nerede başladığını gösterir."),
    "ns_route_start": ("Trace the route", "Yolu izle"),
    "ns_route_running": ("Tracing (up to a minute)…", "İzleniyor (bir dakikaya kadar)…"),
})

BASE = "https://speed.cloudflare.com"
STREAMS = 4
SECONDS = 8


def _req(url, data=None):
    return urllib.request.Request(url, data=data, headers={"User-Agent": "Benchwise/%s" % __version__})


def latency(samples=10):
    """Round trip to the speed test server: the time a TCP connection takes (like ping, but through
    firewalls that drop pings).  Returns (median ms, jitter ms, server place)."""
    import socket
    host = BASE.split("//", 1)[1]
    times = []
    for _ in range(samples):
        t0 = time.perf_counter()
        with socket.create_connection((host, 443), timeout=5):
            times.append((time.perf_counter() - t0) * 1000)
        time.sleep(0.05)
    where = ""
    try:
        with urllib.request.urlopen(_req(BASE + "/__down?bytes=0"), timeout=10) as r:
            r.read()
            where = ", ".join(x for x in (r.headers.get("cf-meta-city"), r.headers.get("cf-meta-colo"),
                                          r.headers.get("cf-meta-country")) if x)
    except Exception:
        pass
    jitter = statistics.mean(abs(a - b) for a, b in zip(times, times[1:])) if len(times) > 1 else 0
    return statistics.median(times), jitter, where


def throughput(kind, report, seconds=SECONDS):
    """Bits per second over ``seconds`` with STREAMS parallel connections; ``report(mbps)`` while running."""
    moved = [0] * STREAMS
    stop = time.perf_counter() + seconds
    body = bytes(4 << 20)

    def down(i):
        while time.perf_counter() < stop:
            with urllib.request.urlopen(_req(BASE + "/__down?bytes=%d" % (25 << 20)), timeout=15) as r:
                while time.perf_counter() < stop:
                    chunk = r.read(64 * 1024)
                    if not chunk:
                        break
                    moved[i] += len(chunk)

    def up(i):
        while time.perf_counter() < stop:
            with urllib.request.urlopen(_req(BASE + "/__up", data=body), timeout=15) as r:
                r.read()
            moved[i] += len(body)

    threads = [threading.Thread(target=down if kind == "down" else up, args=(i,), daemon=True) for i in range(STREAMS)]
    t0 = time.perf_counter()
    for th in threads:
        th.start()
    last = (t0, 0)
    while any(th.is_alive() for th in threads) and time.perf_counter() < stop + 2:
        time.sleep(0.25)
        now, total = time.perf_counter(), sum(moved)
        if now - last[0] >= 0.5:
            report((total - last[1]) * 8 / (now - last[0]) / 1e6)
            last = (now, total)
    elapsed = max(time.perf_counter() - t0, 0.001)
    return sum(moved) * 8 / min(elapsed, seconds + 0.5) / 1e6


class View(ToolView):
    title_key = "tool_netspeed"

    def fill(self):
        c = card(self.body, t("tool_netspeed"))
        note(c, t("ns_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 10))
        self.start_btn = ui.button(row, t("ns_start"), self.start, 170, primary=True)
        self.start_btn.pack(side="left")
        self.phase = ctk.CTkLabel(row, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED)
        self.phase.pack(side="left", padx=14)
        tiles = ctk.CTkFrame(c, fg_color="transparent")
        tiles.pack(fill="x", padx=18, pady=(0, 16))
        self.values = {}
        for i, key in enumerate(("ns_down", "ns_up", "ns_ping", "ns_jitter")):
            tile = ui.card(tiles)
            tile.grid(row=0, column=i, sticky="nsew", padx=(0, 10))
            tiles.grid_columnconfigure(i, weight=1, uniform="t")
            ctk.CTkLabel(tile, text=t(key), font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w").pack(fill="x", padx=14, pady=(10, 0))
            self.values[key] = ctk.CTkLabel(tile, text="–", font=("Segoe UI Semibold", 26), text_color=ui.TEXT, anchor="w")
            self.values[key].pack(fill="x", padx=14, pady=(0, 12))
        r = card(self.body, t("ns_route"))
        note(r, t("ns_route_how"))
        self.route_btn = ui.button(r, t("ns_route_start"), self.route, 150)
        self.route_btn.pack(anchor="w", padx=18, pady=(0, 8))
        self.route_box = ctk.CTkTextbox(r, fg_color=ui.BG, text_color=ui.TEXT, font=("Consolas", 11), height=180,
                                        corner_radius=8, border_width=0)
        self.route_box.pack(fill="x", padx=16, pady=(0, 12))

    def set_value(self, key, text, color=None):
        self.values[key].configure(text=text, text_color=color or ui.TEXT)

    def start(self):
        self.start_btn.configure(state="disabled")
        for key in self.values:
            self.set_value(key, "–")

        def fmt(v):
            return t("ns_mbps", v=("%.0f" % v) if v >= 100 else ("%.1f" % v))

        def work():
            self.post(self.phase.configure, {"text": t("ns_phase_ping")})
            ms, jitter, where = latency()
            self.post(self.set_value, "ns_ping", t("ns_ms", v=int(round(ms))))
            self.post(self.set_value, "ns_jitter", t("ns_ms", v=int(round(jitter))))
            self.post(self.phase.configure, {"text": t("ns_phase_down")})
            down = throughput("down", lambda v: self.post(self.set_value, "ns_down", fmt(v), ui.MUTED))
            self.post(self.set_value, "ns_down", fmt(down))
            self.post(self.phase.configure, {"text": t("ns_phase_up")})
            up = throughput("up", lambda v: self.post(self.set_value, "ns_up", fmt(v), ui.MUTED))
            self.post(self.set_value, "ns_up", fmt(up))
            return where

        def done(res):
            self.start_btn.configure(state="normal")
            if isinstance(res, Exception):
                self.phase.configure(text=t("ns_failed", err=res), text_color=ui.BAD)
            else:
                self.phase.configure(text=t("ns_done", where=res or "Cloudflare"), text_color=ui.GOOD)
        self.run(work, done)

    def route(self):
        self.route_btn.configure(state="disabled")
        self.route_box.delete("1.0", "end")
        self.route_box.insert("1.0", t("ns_route_running"))

        def done(res):
            self.route_btn.configure(state="normal")
            self.route_box.delete("1.0", "end")
            self.route_box.insert("1.0", str(res) if isinstance(res, Exception) else res[1].strip())
        self.run(lambda: run_command(["tracert", "-d", "-h", "20", "-w", "800", "1.1.1.1"], timeout=120), done)
