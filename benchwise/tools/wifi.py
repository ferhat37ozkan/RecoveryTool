"""Network > Wi-Fi: the current connection, networks around (signal, channel, band) with the least
crowded 2.4 GHz channel, and saved networks with their passwords on request.

Uses the Windows Native Wifi API (wlanapi.dll) directly: netsh prints in the Windows language and
would have to be parsed per language.  Windows 11 lets desktop apps see nearby networks only when
location access is allowed for them."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import re
import time
import webbrowser
from collections import Counter

import customtkinter as ctk

from recoverytool.i18n import t

from .. import elevate, ui
from ..toolkit import ToolView, card, kv_grid, note, scroll_body, table, texts

texts({
    "wf_none": ("This computer has no Wi-Fi adapter (or it is turned off).", "Bu bilgisayarda Wi-Fi kartı yok (veya kapalı)."),
    "wf_current": ("Current connection", "Mevcut bağlantı"),
    "wf_not_connected": ("Not connected to a Wi-Fi network.", "Bir Wi-Fi ağına bağlı değil."),
    "wf_ssid": ("Network", "Ağ"),
    "wf_signal": ("Signal", "Sinyal"),
    "wf_channel": ("Channel", "Kanal"),
    "wf_band": ("Band", "Bant"),
    "wf_rate": ("Link speed (down / up)", "Bağlantı hızı (indirme / yükleme)"),
    "wf_adapter": ("Adapter", "Kart"),
    "wf_nearby": ("Networks around", "Yakındaki ağlar"),
    "wf_scanning": ("Scanning…", "Taranıyor…"),
    "wf_rescan": ("Scan again", "Yeniden tara"),
    "wf_none_seen": ("No networks visible. Windows 11 shows nearby networks to desktop apps only when location "
                     "access is allowed for them.", "Görünen ağ yok. Windows 11 yakındaki ağları masaüstü "
                     "uygulamalarına yalnızca konum erişimine izin verilmişse gösterir."),
    "wf_location": ("Open location settings", "Konum ayarlarını aç"),
    "wf_col_ssid": ("Network", "Ağ"),
    "wf_col_signal": ("Signal", "Sinyal"),
    "wf_col_channel": ("Channel", "Kanal"),
    "wf_col_band": ("Band", "Bant"),
    "wf_hidden": ("(hidden)", "(gizli)"),
    "wf_best": ("Least crowded 2.4 GHz channel: {ch} (networks per channel: {counts}). Choose it in the router's "
                "settings if your network is slow.", "En boş 2,4 GHz kanalı: {ch} (kanal başına ağ: {counts}). Ağınız "
                "yavaşsa modem ayarlarında bunu seçin."),
    "wf_saved": ("Saved networks", "Kayıtlı ağlar"),
    "wf_saved_none": ("No saved Wi-Fi networks.", "Kayıtlı Wi-Fi ağı yok."),
    "wf_show": ("Show password", "Şifreyi göster"),
    "wf_password": ("Password: {pw}", "Şifre: {pw}"),
    "wf_no_password": ("No password stored (open network or company login).",
                       "Kayıtlı şifre yok (açık ağ veya kurumsal giriş)."),
    "wf_need_admin": ("Showing passwords needs administrator rights.", "Şifreleri göstermek yönetici yetkisi ister."),
    "wf_copy": ("Copy", "Kopyala"),
})

wlan = ctypes.WinDLL("wlanapi") if hasattr(ctypes, "WinDLL") else None


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [("InterfaceGuid", GUID), ("strInterfaceDescription", w.WCHAR * 256), ("isState", ctypes.c_int)]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", w.DWORD), ("dwIndex", w.DWORD), ("InterfaceInfo", WLAN_INTERFACE_INFO * 1)]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [("uSSIDLength", w.ULONG), ("ucSSID", ctypes.c_ubyte * 32)]


class WLAN_RATE_SET(ctypes.Structure):
    _fields_ = [("uRateSetLength", w.ULONG), ("usRateSet", w.USHORT * 126)]


class WLAN_BSS_ENTRY(ctypes.Structure):
    _fields_ = [("dot11Ssid", DOT11_SSID), ("uPhyId", w.ULONG), ("dot11Bssid", ctypes.c_ubyte * 6),
                ("dot11BssType", ctypes.c_int), ("dot11BssPhyType", ctypes.c_int), ("lRssi", w.LONG),
                ("uLinkQuality", w.ULONG), ("bInRegDomain", ctypes.c_ubyte), ("usBeaconPeriod", w.USHORT),
                ("ullTimestamp", ctypes.c_ulonglong), ("ullHostTimestamp", ctypes.c_ulonglong),
                ("usCapabilityInformation", w.USHORT), ("ulChCenterFrequency", w.ULONG),
                ("wlanRateSet", WLAN_RATE_SET), ("ulIeOffset", w.ULONG), ("ulIeSize", w.ULONG)]


class WLAN_BSS_LIST(ctypes.Structure):
    _fields_ = [("dwTotalSize", w.DWORD), ("dwNumberOfItems", w.DWORD), ("wlanBssEntries", WLAN_BSS_ENTRY * 1)]


class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("dot11Ssid", DOT11_SSID), ("dot11BssType", ctypes.c_int), ("dot11Bssid", ctypes.c_ubyte * 6),
                ("dot11PhyType", ctypes.c_int), ("uDot11PhyIndex", w.ULONG), ("wlanSignalQuality", w.ULONG),
                ("ulRxRate", w.ULONG), ("ulTxRate", w.ULONG)]


class WLAN_SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("bSecurityEnabled", w.BOOL), ("bOneXEnabled", w.BOOL), ("dot11AuthAlgorithm", ctypes.c_int),
                ("dot11CipherAlgorithm", ctypes.c_int)]


class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("isState", ctypes.c_int), ("wlanConnectionMode", ctypes.c_int), ("strProfileName", w.WCHAR * 256),
                ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
                ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES)]


class WLAN_PROFILE_INFO(ctypes.Structure):
    _fields_ = [("strProfileName", w.WCHAR * 256), ("dwFlags", w.DWORD)]


class WLAN_PROFILE_INFO_LIST(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", w.DWORD), ("dwIndex", w.DWORD), ("ProfileInfo", WLAN_PROFILE_INFO * 1)]


def _array(head, field, count):
    """The variable-length array at the end of a WLAN list structure."""
    entry = type(getattr(head, field))._type_
    addr = ctypes.addressof(head) + type(head).__dict__[field].offset
    return (entry * count).from_address(addr)


def ssid_text(s):
    return bytes(s.ucSSID[:s.uSSIDLength]).decode("utf-8", "replace")


def channel_of(khz):
    mhz = khz // 1000
    if 2412 <= mhz <= 2484:
        return (14 if mhz == 2484 else (mhz - 2407) // 5), "2.4 GHz"
    if 5150 <= mhz <= 5895:
        return (mhz - 5000) // 5, "5 GHz"
    if 5925 <= mhz <= 7125:
        return (mhz - 5950) // 5, "6 GHz"
    return None, "%d MHz" % mhz


def best_24_channel(channels):
    """Among 1, 6 and 11 (the ones that do not overlap), the one with the fewest networks on or near it."""
    load = {c: sum(1 for x in channels if x is not None and abs(x - c) < 5) for c in (1, 6, 11)}
    return min(load, key=lambda c: (load[c], c)), load


class Wlan:
    def __init__(self):
        self.h = w.HANDLE()
        ver = w.DWORD()
        if wlan is None or wlan.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(self.h)) != 0:
            raise OSError("wlan")

    def close(self):
        wlan.WlanCloseHandle(self.h, None)

    def interfaces(self):
        p = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
        if wlan.WlanEnumInterfaces(self.h, None, ctypes.byref(p)) != 0:
            return []
        # copy the GUID out: the list is freed below, and a ctypes field would keep pointing into it
        items = [(GUID.from_buffer_copy(bytes(i.InterfaceGuid)), i.strInterfaceDescription, i.isState)
                 for i in _array(p.contents, "InterfaceInfo", p.contents.dwNumberOfItems)]
        wlan.WlanFreeMemory(p)
        return items

    def scan(self, guid):
        wlan.WlanScan(self.h, ctypes.byref(guid), None, None, None)

    def bss(self, guid):
        p = ctypes.POINTER(WLAN_BSS_LIST)()
        if wlan.WlanGetNetworkBssList(self.h, ctypes.byref(guid), None, 3, False, None, ctypes.byref(p)) != 0:
            return []
        out = []
        for e in _array(p.contents, "wlanBssEntries", p.contents.dwNumberOfItems):
            ch, band = channel_of(e.ulChCenterFrequency)
            out.append({"ssid": ssid_text(e.dot11Ssid), "quality": e.uLinkQuality, "rssi": e.lRssi,
                        "channel": ch, "band": band, "bssid": ":".join("%02x" % b for b in e.dot11Bssid)})
        wlan.WlanFreeMemory(p)
        return out

    def current(self, guid):
        size, data, kind = w.DWORD(), ctypes.c_void_p(), ctypes.c_int()
        if wlan.WlanQueryInterface(self.h, ctypes.byref(guid), 7, None, ctypes.byref(size), ctypes.byref(data),
                                   ctypes.byref(kind)) != 0:
            return None
        a = ctypes.cast(data, ctypes.POINTER(WLAN_CONNECTION_ATTRIBUTES)).contents
        assoc = a.wlanAssociationAttributes
        res = {"profile": a.strProfileName, "ssid": ssid_text(assoc.dot11Ssid), "quality": assoc.wlanSignalQuality,
               "rx": assoc.ulRxRate // 1000, "tx": assoc.ulTxRate // 1000,
               "bssid": ":".join("%02x" % b for b in assoc.dot11Bssid)}
        wlan.WlanFreeMemory(data)
        return res

    def profiles(self, guid):
        p = ctypes.POINTER(WLAN_PROFILE_INFO_LIST)()
        if wlan.WlanGetProfileList(self.h, ctypes.byref(guid), None, ctypes.byref(p)) != 0:
            return []
        names = [i.strProfileName for i in _array(p.contents, "ProfileInfo", p.contents.dwNumberOfItems)]
        wlan.WlanFreeMemory(p)
        return names

    def password(self, guid, name):
        """The stored key in plain text (Windows gives it only to administrators), or "" when none."""
        xml, flags, access = w.LPWSTR(), w.DWORD(4), w.DWORD()          # WLAN_PROFILE_GET_PLAINTEXT_KEY
        if wlan.WlanGetProfile(self.h, ctypes.byref(guid), name, None, ctypes.byref(xml), ctypes.byref(flags),
                               ctypes.byref(access)) != 0:
            return None
        text = xml.value or ""
        wlan.WlanFreeMemory(xml)
        m = re.search(r"<keyMaterial>(.*?)</keyMaterial>", text)
        return m.group(1) if m else ""


def gather(scan=True):
    api = Wlan()
    try:
        faces = api.interfaces()
        if not faces:
            return None
        guid, desc, state = faces[0]
        if scan:
            api.scan(guid)
            time.sleep(4)                    # WlanScan is asynchronous; results settle within a few seconds
        nets = api.bss(guid)
        profiles = api.profiles(guid)
        if scan and (not nets or not profiles):
            time.sleep(2)                    # another scan was still running: the lists can come back empty once
            nets = nets or api.bss(guid)
            profiles = profiles or api.profiles(guid)
        cur = api.current(guid) if state == 1 else None
        if cur:
            mine = next((n for n in nets if n["bssid"] == cur["bssid"]), None)
            if mine:
                cur.update(channel=mine["channel"], band=mine["band"], rssi=mine["rssi"])
        return {"guid": guid, "adapter": desc, "networks": nets, "current": cur, "profiles": profiles}
    finally:
        api.close()


class View(ToolView):
    title_key = "tool_wifi"

    def fill(self):
        ui.button(self.head, t("wf_rescan"), self.load, 130).pack(side="right")
        self.page = scroll_body(self)
        note(self.page, t("wf_scanning"))
        self.load()

    def load(self):
        if self.busy():
            return
        self.run(gather, self.show, status=t("wf_scanning"))

    def show(self, data):
        for w_ in self.page.winfo_children():
            w_.destroy()
        if isinstance(data, Exception) or data is None:
            c = card(self.page, t("tool_wifi"))
            note(c, t("wf_none"), color=ui.MUTED)
            return
        self.guid = data["guid"]
        c = card(self.page, t("wf_current"))
        cur = data["current"]
        if cur:
            kv_grid(c, [(t("wf_ssid"), cur["ssid"] or cur["profile"]),
                        (t("wf_signal"), "%s · %s dBm" % (t("dh_pct", n=cur["quality"]), cur.get("rssi", "?"))),
                        (t("wf_channel"), cur.get("channel")), (t("wf_band"), cur.get("band")),
                        (t("wf_rate"), "%s / %s Mbit/s" % (cur["rx"], cur["tx"])), (t("wf_adapter"), data["adapter"])])
        else:
            note(c, t("wf_not_connected"))
            kv_grid(c, [(t("wf_adapter"), data["adapter"])])

        c = card(self.page, t("wf_nearby"))
        nets = sorted(data["networks"], key=lambda n: -n["quality"])
        if nets:
            ch24 = [n["channel"] for n in nets if n["band"] == "2.4 GHz"]
            if ch24:
                best, load = best_24_channel(ch24)
                note(c, t("wf_best", ch=best, counts=", ".join("%d: %d" % kv for kv in sorted(load.items()))))
            holder, tree = table(c, [("ssid", t("wf_col_ssid"), 300), ("signal", t("wf_col_signal"), 140),
                                     ("channel", t("wf_col_channel"), 80), ("band", t("wf_col_band"), 90)],
                                 height=min(12, len(nets)), stretch="ssid")
            holder.pack(fill="x", padx=16, pady=(0, 12))
            for n in nets:
                tag = "good" if n["quality"] >= 70 else "warn" if n["quality"] >= 40 else "bad"
                tree.insert("", "end", values=(n["ssid"] or t("wf_hidden"), "%s · %d dBm" % (t("dh_pct", n=n["quality"]), n["rssi"]),
                                               n["channel"] or "", n["band"]), tags=(tag,))
        else:
            note(c, t("wf_none_seen"), color=ui.WARN)
            ui.button(c, t("wf_location"), lambda: webbrowser.open("ms-settings:privacy-location"), 200).pack(
                anchor="w", padx=18, pady=(0, 12))

        c = card(self.page, t("wf_saved"))
        if not data["profiles"]:
            note(c, t("wf_saved_none"))
        if data["profiles"] and not elevate.is_admin():
            note(c, t("wf_need_admin"))
        for name in data["profiles"]:
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(row, text=name, font=("Segoe UI Semibold", 12), text_color=ui.TEXT, anchor="w").pack(side="left")
            out = ctk.CTkLabel(row, text=" ", font=("Consolas", 12), text_color=ui.MUTED)
            out.pack(side="left", padx=16)
            btn = ui.button(row, t("wf_show"), None, 140)
            btn.configure(command=lambda n=name, o=out, b=btn: self.reveal(n, o, b),
                          state="normal" if elevate.is_admin() else "disabled")
            btn.pack(side="right")
        ctk.CTkFrame(c, fg_color="transparent", height=8).pack()

    def reveal(self, name, label, button):
        try:
            api = Wlan()
            try:
                pw = api.password(self.guid, name)
            finally:
                api.close()
        except OSError:
            pw = None
        if pw:
            label.configure(text=t("wf_password", pw=pw), text_color=ui.TEXT)
            button.configure(text=t("wf_copy"), command=lambda: (self.clipboard_clear(), self.clipboard_append(pw)))
        else:
            label.configure(text=t("wf_no_password"), text_color=ui.MUTED)
