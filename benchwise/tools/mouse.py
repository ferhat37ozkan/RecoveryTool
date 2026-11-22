"""Display & Input > Mouse Test: buttons, double-click faults, the wheel, and a drawing area."""

from __future__ import annotations

import time
import tkinter as tk

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, note, texts

texts({
    "ms_how": ("Click each button and turn the wheel inside the area below; move the mouse to draw. A worn "
               "switch often registers one click as two: Benchwise counts presses that come faster than a "
               "finger can (under {ms} ms) as faults.",
               "Aşağıdaki alanda her tuşa tıklayın ve tekerleği çevirin; çizmek için fareyi hareket ettirin. "
               "Yıpranmış bir tuş çoğu zaman tek tıklamayı iki sayar: Benchwise parmağın yapamayacağı kadar hızlı "
               "(%s ms altı) gelen basışları arıza olarak sayar." % "{ms}"),
    "ms_left": ("Left", "Sol"),
    "ms_middle": ("Middle", "Orta"),
    "ms_right": ("Right", "Sağ"),
    "ms_clicks": ("{n} clicks", "{n} tıklama"),
    "ms_faults": ("{n} double-click faults", "{n} çift tıklama arızası"),
    "ms_wheel": ("Wheel: {up} up · {down} down", "Tekerlek: {up} yukarı · {down} aşağı"),
    "ms_clear": ("Clear", "Temizle"),
    "ms_ok": ("No double-click faults so far.", "Şimdiye kadar çift tıklama arızası yok."),
    "ms_bad": ("The {button} button sends double clicks by itself: its switch is worn.",
               "{button} tuşu kendiliğinden çift tıklama gönderiyor: anahtarı yıpranmış."),
})

FAULT_MS = 80
BUTTONS = {1: "left", 2: "middle", 3: "right"}


class View(ToolView):
    title_key = "tool_mouse"

    def fill(self):
        self.stats = {b: {"clicks": 0, "faults": 0, "last": 0.0, "down": False} for b in BUTTONS.values()}
        self.wheel = {"up": 0, "down": 0}
        self.prev = None
        c = card(self.body, t("tool_mouse"))
        note(c, t("ms_how", ms=FAULT_MS), color=ui.TEXT)
        top = ctk.CTkFrame(c, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(0, 8))
        self.tiles = {}
        for b in ("left", "middle", "right"):
            tile = ui.card(top)
            tile.pack(side="left", padx=(0, 10))
            name = ctk.CTkLabel(tile, text=t("ms_" + b), font=("Segoe UI Semibold", 14), text_color=ui.TEXT, width=150)
            name.pack(padx=14, pady=(10, 0))
            clicks = ctk.CTkLabel(tile, text=" ", font=("Segoe UI", 12), text_color=ui.TEXT)
            clicks.pack(padx=14)
            faults = ctk.CTkLabel(tile, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED)
            faults.pack(padx=14, pady=(0, 10))
            self.tiles[b] = (tile, clicks, faults)
        side = ctk.CTkFrame(top, fg_color="transparent")
        side.pack(side="left", padx=10, fill="y")
        self.wheel_label = ctk.CTkLabel(side, text=" ", font=("Segoe UI Semibold", 13), text_color=ui.TEXT)
        self.wheel_label.pack(anchor="w", pady=(10, 4))
        self.verdict = ctk.CTkLabel(side, text=" ", font=("Segoe UI", 12), text_color=ui.GOOD, wraplength=360,
                                    justify="left")
        self.verdict.pack(anchor="w")
        ui.button(side, t("ms_clear"), self.clear, 110).pack(anchor="w", pady=(8, 0))
        self.area = tk.Canvas(c, height=300, bg="#0b101a", highlightthickness=1, highlightbackground=ui.BORDER,
                              cursor="crosshair")
        self.area.pack(fill="x", padx=18, pady=(0, 16))
        for num in BUTTONS:
            self.area.bind("<ButtonPress-%d>" % num, lambda e, n=num: self.press(n, e))
            self.area.bind("<ButtonRelease-%d>" % num, lambda e, n=num: self.release(n))
        self.area.bind("<MouseWheel>", self.on_wheel)
        self.area.bind("<Motion>", self.on_move)
        self.area.bind("<Leave>", lambda e: setattr(self, "prev", None))
        self.refresh()

    def press(self, num, e):
        b = BUTTONS[num]
        s = self.stats[b]
        now = time.perf_counter()
        if s["last"] and (now - s["last"]) * 1000 < FAULT_MS:
            s["faults"] += 1                     # faster than any finger: the switch bounced
        s["last"], s["down"] = now, True
        s["clicks"] += 1
        color = {"left": ui.ACCENT, "middle": ui.WARN, "right": ui.GOOD}[b]
        self.area.create_oval(e.x - 6, e.y - 6, e.x + 6, e.y + 6, outline=color, width=2)
        self.refresh()

    def release(self, num):
        self.stats[BUTTONS[num]]["down"] = False
        self.refresh()

    def on_wheel(self, e):
        self.wheel["up" if e.delta > 0 else "down"] += 1
        self.refresh()

    def on_move(self, e):
        if self.prev:
            self.area.create_line(self.prev[0], self.prev[1], e.x, e.y, fill="#3a4a6b", width=2)
        self.prev = (e.x, e.y)

    def refresh(self):
        bad = []
        for b, (tile, clicks, faults) in self.tiles.items():
            s = self.stats[b]
            tile.configure(fg_color=ui.CARD_HOVER if s["down"] else ui.CARD,
                           border_color=ui.ACCENT if s["down"] else ui.BORDER)
            clicks.configure(text=t("ms_clicks", n=s["clicks"]))
            faults.configure(text=t("ms_faults", n=s["faults"]), text_color=ui.BAD if s["faults"] else ui.MUTED)
            if s["faults"]:
                bad.append(t("ms_" + b))
        self.wheel_label.configure(text=t("ms_wheel", **self.wheel))
        if bad:
            self.verdict.configure(text="\n".join(t("ms_bad", button=b) for b in bad), text_color=ui.BAD)
        else:
            self.verdict.configure(text=t("ms_ok"), text_color=ui.GOOD)

    def clear(self):
        self.area.delete("all")
        for s in self.stats.values():
            s.update(clicks=0, faults=0, last=0.0, down=False)
        self.wheel.update(up=0, down=0)
        self.refresh()
