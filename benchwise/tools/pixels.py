"""Display & Input > Dead Pixel Test: full-screen plain colours, to spot dead or stuck pixels."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, note, texts

texts({
    "px_how": ("The screen is filled with one colour at a time. Look closely: a dead pixel stays black on every "
               "colour, a stuck pixel stays red, green or blue. Next colour: click, Space or arrow key. "
               "Leave: Esc.",
               "Ekran sırayla tek renkle doldurulur. Dikkatle bakın: ölü piksel her renkte siyah kalır, takılı "
               "piksel kırmızı, yeşil veya mavi kalır. Sonraki renk: tıklayın, Boşluk veya ok tuşu. Çıkmak: Esc."),
    "px_start": ("Start the test", "Testi başlat"),
    "px_colors": ("Colours: black, white, red, green, blue, grey, and a moving checker pattern.",
                  "Renkler: siyah, beyaz, kırmızı, yeşil, mavi, gri ve hareketli dama deseni."),
    "px_overlay": ("{n} / {total}  ·  click or Space: next  ·  Esc: leave", "{n} / {total}  ·  tıkla veya Boşluk: sonraki  ·  Esc: çık"),
    "px_tip": ("Tip: a stuck pixel sometimes recovers after the flashing pattern runs on it for a few minutes.",
               "İpucu: takılı bir piksel bazen yanıp sönen desen üzerinde birkaç dakika çalıştırılınca düzelir."),
})

COLORS = ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#808080", "checker"]


class View(ToolView):
    title_key = "tool_pixels"

    def fill(self):
        c = card(self.body, t("tool_pixels"))
        note(c, t("px_how"), color=ui.TEXT)
        note(c, t("px_colors"))
        note(c, t("px_tip"))
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 16))
        ui.button(row, t("px_start"), self.start, 180, primary=True).pack(side="left")
        swatches = ctk.CTkFrame(row, fg_color="transparent")
        swatches.pack(side="left", padx=16)
        for col in COLORS[:-1]:
            ctk.CTkFrame(swatches, width=26, height=26, fg_color=col, corner_radius=6, border_width=1,
                         border_color=ui.BORDER).pack(side="left", padx=3)

    def start(self):
        win = tk.Toplevel(self)
        win.attributes("-fullscreen", True)
        win.attributes("-topmost", True)
        win.configure(cursor="none", bg="black")
        canvas = tk.Canvas(win, highlightthickness=0, bd=0, bg="black")
        canvas.pack(fill="both", expand=True)
        state = {"i": 0, "tick": 0, "job": None}

        def draw():
            canvas.delete("all")
            col = COLORS[state["i"]]
            w, h = win.winfo_width(), win.winfo_height()
            if col == "checker":
                step = 2
                on = state["tick"] % 2
                for y in range(0, h, 64):
                    for x in range(0, w, 64):
                        fill = "#ffffff" if ((x // 64 + y // 64) % 2) == on else "#000000"
                        canvas.create_rectangle(x, y, x + 64, y + 64, fill=fill, width=0)
                state["tick"] += 1
                state["job"] = win.after(120, draw)
            else:
                canvas.configure(bg=col)
            label_color = "#000000" if col in ("#ffffff", "#00ff00") else "#ffffff"
            if state.get("show_help", True):
                canvas.create_text(w // 2, h - 40, fill=label_color, font=("Segoe UI", 14),
                                   text=t("px_overlay", n=state["i"] + 1, total=len(COLORS)))

        def step(delta):
            if state["job"]:
                win.after_cancel(state["job"])
                state["job"] = None
            state["i"] = (state["i"] + delta) % len(COLORS)
            state["show_help"] = state["i"] == 0     # the hint only on the first colour: it would hide pixels
            draw()

        def leave(_e=None):
            if state["job"]:
                win.after_cancel(state["job"])
            win.destroy()
        win.bind("<Escape>", leave)
        win.bind("<Button-1>", lambda e: step(1))
        win.bind("<Button-3>", lambda e: step(-1))
        for key in ("<space>", "<Right>", "<Down>", "<Return>"):
            win.bind(key, lambda e: step(1))
        for key in ("<Left>", "<Up>", "<BackSpace>"):
            win.bind(key, lambda e: step(-1))
        win.after(80, draw)
        win.focus_force()
