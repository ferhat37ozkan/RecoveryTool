"""Display & Input > Sound Test: left/right speakers, a sweep for rattles, the microphone level and a
record-and-play-back check.  Tones are generated here; the microphone is read through winmm (waveIn)."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import io
import math
import struct
import threading
import time
import wave
import winsound

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, kv_grid, note, powershell_json, texts

texts({
    "au_speakers": ("Speakers", "Hoparlörler"),
    "au_speakers_how": ("Each button plays a short tone. Left must come only from the left, right only from the "
                        "right. The sweep goes from deep to high: listen for rattles or a range that disappears.",
                        "Her düğme kısa bir ses çalar. Sol yalnızca soldan, sağ yalnızca sağdan gelmeli. Tarama "
                        "kalından inceye gider: cızırtıya veya kaybolan bir aralığa kulak verin."),
    "au_left": ("Left", "Sol"),
    "au_right": ("Right", "Sağ"),
    "au_both": ("Both", "İkisi"),
    "au_sweep": ("Sweep 100 Hz - 10 kHz", "Tarama 100 Hz - 10 kHz"),
    "au_mic": ("Microphone", "Mikrofon"),
    "au_mic_how": ("Speak: the bar shows the level the default microphone hears. \"Record\" keeps 4 seconds and "
                   "plays them back.", "Konuşun: çubuk varsayılan mikrofonun duyduğu seviyeyi gösterir. "
                   "\"Kaydet\" 4 saniye kaydeder ve geri çalar."),
    "au_listen": ("Show level", "Seviyeyi göster"),
    "au_stop": ("Stop", "Durdur"),
    "au_record": ("Record 4 s and play back", "4 sn kaydet ve dinlet"),
    "au_recording": ("Recording… {n}", "Kaydediliyor… {n}"),
    "au_playing": ("Playing back…", "Geri çalınıyor…"),
    "au_no_mic": ("No microphone could be opened. Check that one is connected and that Windows allows apps to "
                  "use it (Settings > Privacy > Microphone).",
                  "Mikrofon açılamadı. Bağlı olduğundan ve Windows'un uygulamaların kullanmasına izin verdiğinden "
                  "emin olun (Ayarlar > Gizlilik > Mikrofon)."),
    "au_privacy": ("Open microphone privacy settings", "Mikrofon gizlilik ayarlarını aç"),
    "au_devices": ("Sound devices", "Ses aygıtları"),
    "au_none": ("Windows lists no sound devices.", "Windows hiç ses aygıtı listelemiyor."),
    "au_level": ("Level {pct} %", "Seviye %{pct}"),
})

RATE = 44100


def tone(seconds=1.2, freq=440.0, left=1.0, right=1.0, sweep=None):
    """A stereo 16-bit WAV (bytes): a sine tone, or a logarithmic sweep (f0, f1), with soft edges."""
    n = int(seconds * RATE)
    frames = bytearray()
    phase = 0.0
    for i in range(n):
        x = i / RATE
        f = sweep[0] * (sweep[1] / sweep[0]) ** (i / n) if sweep else freq
        phase += 2 * math.pi * f / RATE
        edge = min(1.0, i / 2000, (n - i) / 2000)
        v = math.sin(phase) * 0.5 * edge
        frames += struct.pack("<hh", int(v * left * 32767), int(v * right * 32767))
    return wav_bytes(bytes(frames), channels=2, rate=RATE)


def wav_bytes(pcm, channels=1, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm)
    return buf.getvalue()


# -- microphone through winmm ------------------------------------------------------------------
winmm = ctypes.WinDLL("winmm")


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", w.WORD), ("nChannels", w.WORD), ("nSamplesPerSec", w.DWORD),
                ("nAvgBytesPerSec", w.DWORD), ("nBlockAlign", w.WORD), ("wBitsPerSample", w.WORD), ("cbSize", w.WORD)]


class WAVEHDR(ctypes.Structure):
    pass


WAVEHDR._fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", w.DWORD), ("dwBytesRecorded", w.DWORD),
                    ("dwUser", ctypes.c_size_t), ("dwFlags", w.DWORD), ("dwLoops", w.DWORD),
                    ("lpNext", ctypes.POINTER(WAVEHDR)), ("reserved", ctypes.c_size_t)]

MIC_RATE, CHUNK = 16000, 1600          # 0.1 s per buffer
WHDR_DONE = 1


class Mic:
    """Reads the default microphone on a thread; ``on_chunk(pcm_bytes)`` is called for every 0.1 s."""

    def __init__(self, on_chunk):
        self.on_chunk, self.stop_flag, self.error = on_chunk, False, None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag = True
        self.thread.join(2)

    def _run(self):
        fmt = WAVEFORMATEX(1, 1, MIC_RATE, MIC_RATE * 2, 2, 16, 0)
        h = w.HANDLE()
        if winmm.waveInOpen(ctypes.byref(h), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0) != 0:
            self.error = "open"
            return
        bufs, hdrs = [], []
        try:
            for _ in range(4):
                b = ctypes.create_string_buffer(CHUNK * 2)
                hdr = WAVEHDR(ctypes.cast(b, ctypes.c_void_p), CHUNK * 2, 0, 0, 0, 0, None, 0)
                winmm.waveInPrepareHeader(h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
                winmm.waveInAddBuffer(h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
                bufs.append(b)
                hdrs.append(hdr)
            winmm.waveInStart(h)
            i = 0
            while not self.stop_flag:
                hdr = hdrs[i]
                if hdr.dwFlags & WHDR_DONE:
                    self.on_chunk(ctypes.string_at(hdr.lpData, hdr.dwBytesRecorded))
                    hdr.dwFlags &= ~WHDR_DONE
                    winmm.waveInAddBuffer(h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
                    i = (i + 1) % len(hdrs)
                else:
                    time.sleep(0.01)
        finally:
            winmm.waveInReset(h)
            for hdr in hdrs:
                winmm.waveInUnprepareHeader(h, ctypes.byref(hdr), ctypes.sizeof(WAVEHDR))
            winmm.waveInClose(h)


def rms_percent(pcm):
    if not pcm:
        return 0
    count = len(pcm) // 2
    samples = struct.unpack("<%dh" % count, pcm[:count * 2])
    rms = math.sqrt(sum(s * s for s in samples) / count)
    # a speaking voice is around -30..-10 dBFS: show it in the upper half of the bar
    db = 20 * math.log10(max(rms, 1) / 32768)
    return max(0, min(100, int((db + 60) / 60 * 100)))


class View(ToolView):
    title_key = "tool_audio"

    def fill(self):
        self.mic = None
        self.recording = None
        c = card(self.body, t("au_speakers"))
        note(c, t("au_speakers_how"), color=ui.TEXT)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 14))
        for key, args in (("au_left", dict(left=1, right=0)), ("au_right", dict(left=0, right=1)),
                          ("au_both", dict(left=1, right=1))):
            ui.button(row, t(key), lambda a=args: self.play(tone(**a)), 110).pack(side="left", padx=(0, 8))
        ui.button(row, t("au_sweep"), lambda: self.play(tone(6.0, sweep=(100, 10000))), 200).pack(side="left", padx=(8, 0))

        m = card(self.body, t("au_mic"))
        note(m, t("au_mic_how"), color=ui.TEXT)
        row = ctk.CTkFrame(m, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))
        self.listen_btn = ui.button(row, t("au_listen"), self.toggle_listen, 150)
        self.listen_btn.pack(side="left")
        self.record_btn = ui.button(row, t("au_record"), self.record, 200)
        self.record_btn.pack(side="left", padx=8)
        self.level = ctk.CTkProgressBar(m, height=14, fg_color=ui.BORDER, progress_color=ui.GOOD, corner_radius=7)
        self.level.set(0)
        self.level.pack(fill="x", padx=18, pady=(6, 2))
        self.mic_note = ctk.CTkLabel(m, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED, anchor="w",
                                     justify="left", wraplength=720)
        self.mic_note.pack(fill="x", padx=18, pady=(2, 12))

        self.devices = card(self.body, t("au_devices"))
        note(self.devices, "…")
        self.run(lambda: as_list(powershell_json(
            "Get-CimInstance Win32_SoundDevice | Select-Object Name, Manufacturer, Status | ConvertTo-Json -Compress")),
            self.show_devices)

    def show_devices(self, result):
        for w_ in self.devices.winfo_children()[1:]:
            w_.destroy()
        if isinstance(result, Exception) or not result:
            note(self.devices, t("au_none"))
            return
        kv_grid(self.devices, [(d.get("Name") or "?", " · ".join(x for x in (d.get("Manufacturer"), d.get("Status")) if x))
                               for d in result])

    def play(self, data):
        threading.Thread(target=lambda: winsound.PlaySound(data, winsound.SND_MEMORY), daemon=True).start()

    # -- microphone -----------------------------------------------------------------------------
    def toggle_listen(self):
        if self.mic:
            return self.stop_mic()
        self.start_mic()

    def start_mic(self, keep=False):
        self.recording = [] if keep else None

        def chunk(pcm):
            if self.recording is not None:
                self.recording.append(pcm)
            self.post(self.show_level, rms_percent(pcm))
        self.mic = Mic(chunk)
        self.after(400, self.check_mic)
        self.listen_btn.configure(text=t("au_stop"))

    def check_mic(self):
        if self.mic and self.mic.error:
            self.mic = None
            self.listen_btn.configure(text=t("au_listen"))
            self.mic_note.configure(text=t("au_no_mic"), text_color=ui.WARN)
            import webbrowser
            ui.button(self.mic_note.master, t("au_privacy"), lambda: webbrowser.open("ms-settings:privacy-microphone"),
                      260).pack(anchor="w", padx=18, pady=(0, 12))

    def show_level(self, pct):
        self.level.set(pct / 100)
        self.level.configure(progress_color=ui.GOOD if pct < 85 else ui.WARN)
        if self.recording is None:
            self.mic_note.configure(text=t("au_level", pct=pct), text_color=ui.MUTED)

    def stop_mic(self):
        if self.mic:
            self.mic.stop()
            self.mic = None
        self.level.set(0)
        self.listen_btn.configure(text=t("au_listen"))

    def record(self):
        self.stop_mic()
        self.start_mic(keep=True)
        self.record_btn.configure(state="disabled")
        self.countdown(4)

    def countdown(self, n):
        if self.mic is None:                      # could not open
            self.record_btn.configure(state="normal")
            return
        if n > 0:
            self.mic_note.configure(text=t("au_recording", n=n), text_color=ui.ACCENT)
            self.after(1000, lambda: self.countdown(n - 1))
            return
        pcm = b"".join(self.recording or [])
        self.stop_mic()
        self.recording = None
        self.mic_note.configure(text=t("au_playing"), text_color=ui.TEXT)
        data = wav_bytes(pcm, 1, MIC_RATE)

        def play():
            winsound.PlaySound(data, winsound.SND_MEMORY)
            self.post(lambda: (self.record_btn.configure(state="normal"), self.mic_note.configure(text=" ")))
        threading.Thread(target=play, daemon=True).start()

    def busy(self):
        return False

    def destroy(self):
        self.stop_mic()
        super().destroy()
