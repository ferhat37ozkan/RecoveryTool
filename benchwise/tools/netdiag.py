"""Network > Connection Check: walks the chain adapter -> address -> gateway -> DNS -> internet and
says where it breaks, with what to do about it."""

from __future__ import annotations

import socket
import time
import urllib.request

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, as_list, card, note, powershell_json, run_command, texts

texts({
    "nd_run": ("Check again", "Tekrar kontrol et"),
    "nd_running": ("Checking…", "Kontrol ediliyor…"),
    "nd_ok_all": ("The connection works end to end.", "Bağlantı baştan sona çalışıyor."),
    "nd_broken": ("The connection breaks at: {step}", "Bağlantı şu adımda kopuyor: {step}"),
    "nd_s_adapter": ("Network adapter", "Ağ kartı"),
    "nd_s_address": ("IP address", "IP adresi"),
    "nd_s_gateway": ("Modem / router (gateway)", "Modem / yönlendirici (ağ geçidi)"),
    "nd_s_dns": ("Name lookup (DNS)", "Ad çözümleme (DNS)"),
    "nd_s_internet": ("Internet", "İnternet"),
    "nd_adapter_ok": ("{name} connected · {speed}", "{name} bağlı · {speed}"),
    "nd_adapter_bad": ("No network adapter is connected. Plug in the cable or connect to Wi-Fi; check that "
                       "airplane mode is off.", "Bağlı ağ kartı yok. Kabloyu takın veya Wi-Fi'ye bağlanın; uçak "
                       "modunun kapalı olduğundan emin olun."),
    "nd_address_ok": ("{ip}", "{ip}"),
    "nd_address_apipa": ("{ip}: no address came from the modem (169.254.x.x). Restart the modem; if it stays, "
                         "use Network Reset.", "{ip}: modemden adres alınamadı (169.254.x.x). Modemi yeniden "
                         "başlatın; düzelmezse Ağ Sıfırlama'yı kullanın."),
    "nd_address_none": ("No IPv4 address.", "IPv4 adresi yok."),
    "nd_gateway_ok": ("{gw} answers in {ms} ms", "{gw} {ms} ms'de yanıt veriyor"),
    "nd_gateway_bad": ("{gw} does not answer. Check the cable / Wi-Fi signal and restart the modem.",
                       "{gw} yanıt vermiyor. Kabloyu / Wi-Fi sinyalini kontrol edin ve modemi yeniden başlatın."),
    "nd_gateway_none": ("No gateway is set.", "Ağ geçidi tanımlı değil."),
    "nd_dns_ok": ("Names resolve in {ms} ms (DNS: {servers})", "Adlar {ms} ms'de çözülüyor (DNS: {servers})"),
    "nd_dns_bad": ("Names cannot be looked up. The modem's DNS may be down: try a public DNS such as 1.1.1.1 "
                   "or 8.8.8.8 in the adapter settings.", "Adlar çözülemiyor. Modemin DNS'i çalışmıyor olabilir: "
                   "ağ kartı ayarlarında 1.1.1.1 veya 8.8.8.8 gibi genel bir DNS deneyin."),
    "nd_internet_ok": ("Internet reachable ({ms} ms)", "İnternete erişiliyor ({ms} ms)"),
    "nd_internet_portal": ("A login page sits in front of the internet (hotel, café, guest Wi-Fi). Open a browser "
                           "and sign in.", "İnternetin önünde bir giriş sayfası var (otel, kafe, misafir Wi-Fi). "
                           "Tarayıcıyı açıp giriş yapın."),
    "nd_internet_bad": ("The internet cannot be reached past the modem. The line may be down: check the modem's "
                        "lights or call the provider.", "Modemin ötesindeki internete ulaşılamıyor. Hat kesik "
                        "olabilir: modemin ışıklarına bakın veya servis sağlayıcınızı arayın."),
    "nd_skipped": ("not checked (an earlier step failed)", "kontrol edilmedi (önceki bir adım başarısız)"),
})

ADAPTER = r"""
$c = Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.NetAdapter.Status -eq 'Up' }
@($c | ForEach-Object { [pscustomobject]@{ name = $_.InterfaceAlias; desc = $_.InterfaceDescription;
  speed = [string]$_.NetAdapter.LinkSpeed; ipv4 = @($_.IPv4Address | ForEach-Object { $_.IPAddress });
  gateway = @($_.IPv4DefaultGateway | ForEach-Object { $_.NextHop }); dns = @($_.DNSServer | Where-Object { $_.AddressFamily -eq 2 } | ForEach-Object { $_.ServerAddresses }) } }) |
  ConvertTo-Json -Depth 4 -Compress
"""


def ping(host, count=2):
    """Average reply time in ms, or None."""
    code, out = run_command(["ping", "-n", str(count), "-w", "1000", host], timeout=15)
    import re
    times = [int(x) for x in re.findall(r"[=<](\d+)\s*ms", out)]
    return (sum(times) // len(times)) if code == 0 and times else None


def check():
    steps = []                                   # (key, ok, text)
    adapters = [a for a in as_list(powershell_json(ADAPTER)) if a.get("ipv4") or a.get("gateway")]
    with_gw = [a for a in adapters if as_list(a.get("gateway"))] or adapters
    if not with_gw:
        steps.append(("adapter", False, t("nd_adapter_bad")))
        return steps
    a = with_gw[0]
    steps.append(("adapter", True, t("nd_adapter_ok", name=a.get("name") or a.get("desc"), speed=a.get("speed") or "")))
    ips = [ip for ip in as_list(a.get("ipv4")) if ip]
    if not ips:
        steps.append(("address", False, t("nd_address_none")))
        return steps
    if ips[0].startswith("169.254."):
        steps.append(("address", False, t("nd_address_apipa", ip=ips[0])))
        return steps
    steps.append(("address", True, t("nd_address_ok", ip=", ".join(ips))))
    gws = [g for g in as_list(a.get("gateway")) if g and g != "0.0.0.0"]
    if not gws:
        steps.append(("gateway", False, t("nd_gateway_none")))
        return steps
    ms = ping(gws[0])
    steps.append(("gateway", ms is not None, t("nd_gateway_ok", gw=gws[0], ms=ms) if ms is not None
                  else t("nd_gateway_bad", gw=gws[0])))
    if ms is None:
        return steps
    t0 = time.time()
    try:
        socket.getaddrinfo("www.msftconnecttest.com", 80)
        dns_ms = int((time.time() - t0) * 1000)
        steps.append(("dns", True, t("nd_dns_ok", ms=dns_ms, servers=", ".join(as_list(a.get("dns"))) or "?")))
    except OSError:
        steps.append(("dns", False, t("nd_dns_bad")))
        return steps
    t0 = time.time()
    try:
        req = urllib.request.Request("http://www.msftconnecttest.com/connecttest.txt", headers={"User-Agent": "Benchwise"})
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read(200).decode("ascii", "replace")
        web_ms = int((time.time() - t0) * 1000)
        if "Microsoft Connect Test" in body:
            steps.append(("internet", True, t("nd_internet_ok", ms=web_ms)))
        else:
            steps.append(("internet", False, t("nd_internet_portal")))
    except Exception:
        steps.append(("internet", False, t("nd_internet_bad")))
    return steps


ORDER = ("adapter", "address", "gateway", "dns", "internet")


class View(ToolView):
    title_key = "tool_netdiag"

    def fill(self):
        ui.button(self.head, t("nd_run"), self.start, 150, primary=True).pack(side="right")
        self.verdict = ctk.CTkLabel(self.body, text=" ", font=("Segoe UI Semibold", 16), text_color=ui.TEXT,
                                    anchor="w", justify="left", wraplength=900)
        self.verdict.pack(fill="x", pady=(0, 10))
        self.steps = card(self.body)
        self.start()

    def start(self):
        if self.busy():
            return
        self.verdict.configure(text=t("nd_running"), text_color=ui.MUTED)
        self.run(check, self.show, status=t("nd_running"))

    def show(self, steps):
        for w_ in self.steps.winfo_children():
            w_.destroy()
        if isinstance(steps, Exception):
            self.verdict.configure(text=str(steps), text_color=ui.BAD)
            return
        done = {k: (ok, text) for k, ok, text in steps}
        failed = next((k for k in ORDER if k in done and not done[k][0]), None)
        if failed:
            self.verdict.configure(text=t("nd_broken", step=t("nd_s_" + failed)), text_color=ui.BAD)
        else:
            self.verdict.configure(text=t("nd_ok_all"), text_color=ui.GOOD)
        for key in ORDER:
            row = ctk.CTkFrame(self.steps, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=(10 if key == ORDER[0] else 4, 10 if key == ORDER[-1] else 4))
            ok, text = done.get(key, (None, t("nd_skipped")))
            mark, color = ("✓", ui.GOOD) if ok else ("✕", ui.BAD) if ok is False else ("–", ui.MUTED)
            ctk.CTkLabel(row, text=mark, font=("Segoe UI Semibold", 18), text_color=color, width=30).pack(side="left", anchor="n")
            box = ctk.CTkFrame(row, fg_color="transparent")
            box.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(box, text=t("nd_s_" + key), font=("Segoe UI Semibold", 13), text_color=ui.TEXT, anchor="w").pack(fill="x")
            ctk.CTkLabel(box, text=text, font=("Segoe UI", 12), text_color=color if ok is False else ui.MUTED, anchor="w",
                         justify="left", wraplength=820).pack(fill="x")
