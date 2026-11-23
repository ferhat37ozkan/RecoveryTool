"""Network > Network Inspector: every network adapter (cable, Wi-Fi, virtual, VPN, Bluetooth...) as a
card.  Opening the tool scans them one by one; the strip along the bottom of a card is its progress
bar while it is scanned and its verdict colour afterwards.  Clicking a card opens everything that
was found about that network in a panel on the right: addressing, DHCP, DNS, the router and what it
exposes, the path to the internet, the devices around, traffic counters, driver settings, and a
security review.

Every live test is sent from the adapter's own address (see ``benchwise.netscan.probe``), so each
network is tested on its own: a virtual adapter never answers for the Wi-Fi."""

from __future__ import annotations

import ipaddress
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor

import customtkinter as ctk

from recoverytool.i18n import t

from .. import art, ui
from ..netscan import collect, probe
from ..toolkit import ToolView, human, table, texts
from ..ui import BG, BORDER, CARD, CARD_HOVER, MUTED, TEXT

texts({
    "nx_scan": ("Scan all", "Tümünü tara"),
    "nx_rescan_one": ("Scan this again", "Bunu yeniden tara"),
    "nx_copy": ("Copy report", "Raporu kopyala"),
    "nx_copied": ("Copied", "Kopyalandı"),
    "nx_loading": ("Finding network adapters…", "Ağ kartları aranıyor…"),
    "nx_none": ("No network adapters were found.", "Hiç ağ kartı bulunamadı."),
    "nx_failed": ("Could not read the network adapters: {err}", "Ağ kartları okunamadı: {err}"),
    "nx_count": ("{n} adapters · {up} connected", "{n} kart · {up} bağlı"),
    "nx_scanning": ("Scanning {name}…", "{name} taranıyor…"),
    "nx_done": ("Scan finished · {n} adapters", "Tarama bitti · {n} kart"),
    "nx_hint": ("Click a card to see everything about that network.", "Ağın tüm ayrıntıları için bir karta tıklayın."),
    "nx_k_wifi": ("Wi-Fi", "Wi-Fi"),
    "nx_k_ethernet": ("Ethernet (cable)", "Ethernet (kablolu)"),
    "nx_k_virtual": ("Virtual adapter", "Sanal kart"),
    "nx_k_vpn": ("VPN / tunnel", "VPN / tünel"),
    "nx_k_bluetooth": ("Bluetooth network", "Bluetooth ağı"),
    "nx_k_cellular": ("Mobile broadband", "Mobil geniş bant"),
    "nx_k_other": ("Network adapter", "Ağ kartı"),
    "nx_st_Up": ("Connected", "Bağlı"),
    "nx_st_Disconnected": ("Not connected", "Bağlı değil"),
    "nx_st_Disabled": ("Turned off", "Devre dışı"),
    "nx_st_Not Present": ("Hardware not present", "Donanım takılı değil"),
    "nx_queued": ("Waiting to be scanned", "Taranmayı bekliyor"),
    "nx_step_config": ("Reading its settings", "Ayarları okunuyor"),
    "nx_step_gateway": ("Pinging the router", "Modem pingleniyor"),
    "nx_step_ports": ("Checking the router's open ports", "Modemin açık portlarına bakılıyor"),
    "nx_step_upnp": ("Asking the router (UPnP)", "Modeme soruluyor (UPnP)"),
    "nx_step_dns": ("Testing name lookup (DNS)", "Ad çözümleme (DNS) deneniyor"),
    "nx_step_internet": ("Testing the internet", "İnternet deneniyor"),
    "nx_step_public": ("Reading the public address", "Genel adres okunuyor"),
    "nx_step_path": ("Tracing the path, measuring MTU", "Yol izleniyor, MTU ölçülüyor"),
    "nx_step_security": ("Security review", "Güvenlik incelemesi"),
    "nx_v_ok": ("Internet works · {ms} ms", "İnternet çalışıyor · {ms} ms"),
    "nx_v_local": ("Local network only: no route to the internet", "Yalnız yerel ağ: internete yolu yok"),
    "nx_v_break": ("Breaks at: {step}", "Kopuyor: {step}"),
    "nx_v_portal": ("A login page sits in front of the internet", "İnternetin önünde bir giriş sayfası var"),
    "nx_v_issues": ("{bad} problems · {warn} warnings", "{bad} sorun · {warn} uyarı"),
    "nx_v_warns": ("{warn} warnings", "{warn} uyarı"),
    "nx_v_clean": ("No security problems found", "Güvenlik sorunu bulunmadı"),
    "nx_v_error": ("Could not be scanned: {err}", "Taranamadı: {err}"),
    "nx_why_Disconnected": ("Cable unplugged or not joined to a network", "Kablo takılı değil veya bir ağa katılmamış"),
    "nx_why_Disabled": ("Turned off in Windows", "Windows'ta kapatılmış"),
    "nx_why_Not Present": ("The device is unplugged or switched off", "Aygıt çıkarılmış veya kapalı"),
    "nx_s_adapter": ("Adapter", "Ağ kartı"),
    "nx_s_address": ("IP address", "IP adresi"),
    "nx_s_gateway": ("Router (gateway)", "Modem (ağ geçidi)"),
    "nx_s_dns": ("Name lookup (DNS)", "Ad çözümleme (DNS)"),
    "nx_s_internet": ("Internet", "İnternet"),
    "nx_c_apipa": ("No address came from the router (169.254.x.x). Restart the router; if it stays, use Network "
                   "Reset.", "Modemden adres alınamadı (169.254.x.x). Modemi yeniden başlatın; düzelmezse Ağ "
                   "Sıfırlama'yı kullanın."),
    "nx_c_noaddr": ("No IPv4 address.", "IPv4 adresi yok."),
    "nx_c_nogw": ("No gateway: this network does not lead to the internet (normal for virtual and host-only "
                  "networks).", "Ağ geçidi yok: bu ağ internete çıkmıyor (sanal ve yalnız-ana-makine ağlarında "
                  "normaldir)."),
    "nx_c_gwdown": ("The router does not answer. Check the cable / Wi-Fi signal and restart the router.",
                    "Modem yanıt vermiyor. Kabloyu / Wi-Fi sinyalini kontrol edin ve modemi yeniden başlatın."),
    "nx_c_dnsdown": ("Names cannot be looked up through this network's DNS servers. Try a public DNS server in "
                     "the adapter settings.", "Bu ağın DNS sunucularıyla adlar çözülemiyor. Kart ayarlarında genel "
                     "bir DNS sunucusu deneyin."),
    "nx_c_netdown": ("The internet cannot be reached past the router. The line may be down: check the router's "
                     "lights or call the provider.", "Modemin ötesine geçilemiyor. Hat kesik olabilir: modemin "
                     "ışıklarına bakın veya servis sağlayıcınızı arayın."),
    "nx_c_portal": ("A login page sits in front of the internet (hotel, café, guest Wi-Fi). Open a browser and sign "
                    "in.", "İnternetin önünde bir giriş sayfası var (otel, kafe, misafir Wi-Fi). Tarayıcıyı açıp "
                    "giriş yapın."),
    "nx_c_skipped": ("not checked (an earlier step failed)", "kontrol edilmedi (önceki adım başarısız)"),
    "nx_c_down": ("The adapter is not connected.", "Kart bağlı değil."),
    "nx_p_scanning": ("Scanning this network: {step}…", "Bu ağ taranıyor: {step}…"),
    "nx_p_waiting": ("This network has not been scanned yet.", "Bu ağ henüz taranmadı."),
    "nx_p_noprobe": ("Live tests are made only on a connected adapter with an IPv4 address.",
                     "Canlı testler yalnızca bağlı ve IPv4 adresi olan kartta yapılır."),
    "nx_sec_chain": ("Connection chain", "Bağlantı zinciri"),
    "nx_sec_security": ("Security review", "Güvenlik incelemesi"),
    "nx_sec_adapter": ("Adapter", "Ağ kartı"),
    "nx_sec_wifi": ("Wi-Fi link", "Wi-Fi bağlantısı"),
    "nx_sec_ipv4": ("IPv4 addressing", "IPv4 adresleme"),
    "nx_sec_ipv6": ("IPv6 addressing", "IPv6 adresleme"),
    "nx_sec_dns": ("Name lookup (DNS)", "Ad çözümleme (DNS)"),
    "nx_sec_router": ("Router (gateway)", "Modem / yönlendirici (ağ geçidi)"),
    "nx_sec_upnp": ("Port forwards opened through UPnP", "UPnP ile açılmış port yönlendirmeleri"),
    "nx_sec_internet": ("Internet", "İnternet"),
    "nx_sec_hops": ("Path to the internet (first hops)", "İnternete giden yol (ilk atlamalar)"),
    "nx_sec_profile": ("Windows network profile", "Windows ağ profili"),
    "nx_sec_traffic": ("Traffic since the adapter came up", "Kart açıldığından beri trafik"),
    "nx_sec_neighbors": ("Devices seen on this network", "Bu ağda görülen cihazlar"),
    "nx_sec_bindings": ("Protocols on this adapter", "Bu karttaki protokoller"),
    "nx_sec_advanced": ("Driver settings", "Sürücü ayarları"),
    "nx_f_fix": ("What to do: {fix}", "Ne yapmalı: {fix}"),
    "nx_r_name": ("Name", "Ad"),
    "nx_r_desc": ("Device", "Aygıt"),
    "nx_r_kind": ("Type", "Tür"),
    "nx_r_status": ("Status", "Durum"),
    "nx_r_mac": ("MAC address", "MAC adresi"),
    "nx_r_mac_random": ("{mac} (randomised / locally assigned)", "{mac} (rastgele / yerel atanmış)"),
    "nx_r_speed": ("Link speed", "Bağlantı hızı"),
    "nx_r_mtu": ("MTU", "MTU"),
    "nx_r_index": ("Interface index", "Arabirim numarası"),
    "nx_r_guid": ("Interface ID", "Arabirim kimliği"),
    "nx_r_driver": ("Driver", "Sürücü"),
    "nx_r_bus": ("Bus", "Veri yolu"),
    "nx_r_virtual": ("Hardware", "Donanım"),
    "nx_r_virtual_yes": ("Virtual (no physical device behind it)", "Sanal (arkasında fiziksel aygıt yok)"),
    "nx_r_virtual_no": ("Physical device", "Fiziksel aygıt"),
    "nx_r_ssid": ("Network name (SSID)", "Ağ adı (SSID)"),
    "nx_r_bssid": ("Access point (BSSID)", "Erişim noktası (BSSID)"),
    "nx_r_auth": ("Security", "Güvenlik"),
    "nx_r_cipher": ("Encryption", "Şifreleme"),
    "nx_r_phy": ("Standard", "Standart"),
    "nx_r_band": ("Band / channel", "Bant / kanal"),
    "nx_r_signal": ("Signal", "Sinyal"),
    "nx_r_rate": ("Link rate (down / up)", "Bağlantı hızı (indirme / yükleme)"),
    "nx_r_profile": ("Saved profile", "Kayıtlı profil"),
    "nx_r_addr": ("Address", "Adres"),
    "nx_r_mask": ("Subnet mask", "Alt ağ maskesi"),
    "nx_r_network": ("Network / broadcast", "Ağ / yayın adresi"),
    "nx_r_hosts": ("Addresses in the subnet", "Alt ağdaki adres sayısı"),
    "nx_r_origin": ("Assigned by", "Atayan"),
    "nx_r_gateway": ("Default gateway", "Varsayılan ağ geçidi"),
    "nx_r_dhcp_server": ("DHCP server", "DHCP sunucusu"),
    "nx_r_lease": ("Lease obtained / expires", "Kira alındı / bitiyor"),
    "nx_r_metric": ("Interface metric", "Arabirim ölçümü (metric)"),
    "nx_r_forwarding": ("Routing (forwarding)", "Yönlendirme (forwarding)"),
    "nx_r_netbios": ("NetBIOS over TCP/IP", "TCP/IP üzerinden NetBIOS"),
    "nx_r_netbios_0": ("From DHCP (usually on)", "DHCP'ye göre (genelde açık)"),
    "nx_r_netbios_1": ("On", "Açık"),
    "nx_r_netbios_2": ("Off", "Kapalı"),
    "nx_r_v6_internet": ("IPv6 internet", "IPv6 internet"),
    "nx_r_servers": ("DNS servers", "DNS sunucuları"),
    "nx_r_suffix": ("DNS suffix", "DNS soneki"),
    "nx_r_register": ("Registers its name in DNS", "Adını DNS'e kaydediyor"),
    "nx_r_hijack": ("Answers for names that do not exist", "Olmayan adlara yanıt"),
    "nx_r_hijack_yes": ("Yes: the resolver rewrites missing names (redirects or ads)", "Evet: sunucu olmayan adları başka yere yönlendiriyor"),
    "nx_r_hijack_no": ("No (correct)", "Hayır (doğru)"),
    "nx_r_ping": ("Response time (min / avg / max)", "Yanıt süresi (en az / ort / en çok)"),
    "nx_r_jitter": ("Jitter / packet loss", "Dalgalanma / paket kaybı"),
    "nx_r_ports": ("Open ports on the router", "Modemde açık portlar"),
    "nx_r_ports_none": ("None of the checked ports", "Bakılan portların hiçbiri açık değil"),
    "nx_r_web": ("Management page title", "Yönetim sayfası başlığı"),
    "nx_r_vendor": ("Manufacturer / model", "Üretici / model"),
    "nx_r_fw": ("Description", "Açıklama"),
    "nx_r_serial": ("Serial number", "Seri numarası"),
    "nx_r_upnp": ("UPnP", "UPnP"),
    "nx_r_upnp_on": ("On: programs can open ports on the router by themselves", "Açık: programlar modemde kendiliğinden port açabilir"),
    "nx_r_upnp_off": ("Does not answer (off or blocked)", "Yanıt vermiyor (kapalı veya engelli)"),
    "nx_r_wan": ("Router's internet-side address", "Modemin internet tarafı adresi"),
    "nx_r_connect": ("Connection test", "Bağlantı testi"),
    "nx_r_public": ("Public IP address", "Genel IP adresi"),
    "nx_r_country": ("Country (as seen from outside)", "Ülke (dışarıdan görünen)"),
    "nx_r_tls": ("Encrypted connection", "Şifreli bağlantı"),
    "nx_r_pmtu": ("Path MTU", "Yol MTU'su"),
    "nx_r_pmtu_pppoe": ("{n} bytes (typical of a PPPoE line)", "{n} bayt (PPPoE hattı için tipik)"),
    "nx_r_pmtu_small": ("{n} bytes (lower than usual: a tunnel or a misconfigured link)", "{n} bayt (normalden düşük: tünel veya yanlış ayar)"),
    "nx_r_bytes": ("{n} bytes", "{n} bayt"),
    "nx_r_cgnat": ("Carrier-grade NAT", "Operatör NAT'ı (CGNAT)"),
    "nx_r_cgnat_yes": ("Yes: the provider shares one public address among customers; incoming connections and port forwarding will not work",
                       "Evet: servis sağlayıcı bir genel adresi müşteriler arasında paylaştırıyor; dışarıdan bağlantı ve port yönlendirme çalışmaz"),
    "nx_r_dnat": ("NAT behind NAT", "NAT arkasında NAT"),
    "nx_r_dnat_yes": ("Yes: two routers translate addresses in a row", "Evet: art arda iki modem adres çeviriyor"),
    "nx_r_netname": ("Windows profile name", "Windows profil adı"),
    "nx_r_netname_why": ("{name} (Windows' own label for this connection; the Wi-Fi itself is \"{ssid}\". Windows "
                         "adds a number when it takes a network for a new one, for example the same router reached "
                         "over cable and Wi-Fi. Each profile keeps its own Public / Private setting.)",
                         "{name} (Windows'un bu bağlantıya verdiği ad; Wi-Fi'nin kendi adı \"{ssid}\". Windows bir "
                         "ağı yeni sandığında, örneğin aynı modeme hem kabloyla hem Wi-Fi ile bağlanınca, ada numara "
                         "ekler. Her profilin Ortak / Özel ayarı ayrıdır.)"),
    "nx_r_category": ("Category", "Kategori"),
    "nx_r_cat_Public": ("Public (others on the network cannot see this computer)", "Ortak (ağdakiler bu bilgisayarı göremez)"),
    "nx_r_cat_Private": ("Private (trusted: sharing and discovery can be on)", "Özel (güvenilir: paylaşım ve bulma açık olabilir)"),
    "nx_r_cat_DomainAuthenticated": ("Company domain", "Şirket etki alanı"),
    "nx_r_conn": ("Windows sees (IPv4 / IPv6)", "Windows'un gördüğü (IPv4 / IPv6)"),
    "nx_r_rx": ("Received", "Alınan"),
    "nx_r_tx": ("Sent", "Gönderilen"),
    "nx_r_errors": ("Errors (in / out)", "Hatalar (gelen / giden)"),
    "nx_r_discards": ("Dropped (in / out)", "Atılan (gelen / giden)"),
    "nx_r_pkts": ("{bytes} · {pkts} packets", "{bytes} · {pkts} paket"),
    "nx_yes": ("Yes", "Evet"),
    "nx_no": ("No", "Hayır"),
    "nx_ok": ("Works", "Çalışıyor"),
    "nx_fail": ("Does not work", "Çalışmıyor"),
    "nx_unknown": ("Unknown", "Bilinmiyor"),
    "nx_on": ("On", "Açık"),
    "nx_off": ("Off", "Kapalı"),
    "nx_col_ttl": ("Hop", "Atlama"),
    "nx_col_ip": ("Address", "Adres"),
    "nx_col_ms": ("Time", "Süre"),
    "nx_col_mac": ("MAC", "MAC"),
    "nx_col_state": ("State", "Durum"),
    "nx_col_note": ("Note", "Not"),
    "nx_col_proto": ("Protocol", "Protokol"),
    "nx_col_ext": ("Outside port", "Dış port"),
    "nx_col_to": ("Goes to", "Yönlendiği yer"),
    "nx_col_desc": ("Opened by", "Açan"),
    "nx_col_server": ("Server", "Sunucu"),
    "nx_n_router": ("router", "modem"),
    "nx_n_this": ("this computer", "bu bilgisayar"),
    "nx_n_private": ("private network address", "özel ağ adresi"),
    "nx_n_timeout": ("no answer", "yanıt yok"),
    "nx_o_Dhcp": ("DHCP (automatic)", "DHCP (otomatik)"),
    "nx_o_Manual": ("Set by hand (static)", "Elle girilmiş (sabit)"),
    "nx_o_WellKnown": ("Windows (link-local)", "Windows (yerel bağlantı)"),
    "nx_o_Link": ("Windows (link-local)", "Windows (yerel bağlantı)"),
    "nx_o_RouterAdvertisement": ("Router advertisement (SLAAC)", "Yönlendirici duyurusu (SLAAC)"),
    "nx_v6_link": ("link-local", "yerel bağlantı"),
    "nx_v6_global": ("global", "genel"),
    "nx_v6_temp": ("global, temporary (privacy)", "genel, geçici (gizlilik)"),
    "nx_v6_ula": ("unique local", "benzersiz yerel"),
    "nx_b_ms_server": ("File and Printer Sharing", "Dosya ve Yazıcı Paylaşımı"),
    "nx_b_ms_msclient": ("Client for Microsoft Networks", "Microsoft Ağları İstemcisi"),
    "nx_b_ms_tcpip": ("Internet Protocol version 4 (IPv4)", "İnternet Protokolü sürüm 4 (IPv4)"),
    "nx_b_ms_tcpip6": ("Internet Protocol version 6 (IPv6)", "İnternet Protokolü sürüm 6 (IPv6)"),
    "nx_b_ms_lltdio": ("Link-Layer Topology Discovery Mapper", "Bağlantı Katmanı Topoloji Bulma Eşleyicisi"),
    "nx_b_ms_rspndr": ("Link-Layer Topology Discovery Responder", "Bağlantı Katmanı Topoloji Bulma Yanıtlayıcısı"),
    "nx_b_ms_pacer": ("QoS Packet Scheduler", "QoS Paket Zamanlayıcısı"),
    "nx_b_ms_lldp": ("LLDP Protocol Driver", "LLDP Protokol Sürücüsü"),
    "nx_b_ms_implat": ("Multiplexor Protocol", "Çoğullayıcı Protokolü"),
    "nx_b_ms_l2bridge": ("Layer 2 bridge", "Katman 2 köprüsü"),
})

PORT_NAMES = {21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP", 139: "NetBIOS", 443: "HTTPS", 445: "SMB",
              1900: "UPnP", 2323: "Telnet", 5000: "UPnP / HTTP", 7547: "TR-069", 8080: "HTTP", 8443: "HTTPS",
              8291: "management", 49152: "UPnP"}
ICONS = {"wifi": "wifi", "ethernet": "ethernet", "bluetooth": "bluetooth", "vpn": "lock", "cellular": "bars",
         "virtual": "monitor", "other": "globe"}
PANEL_WIDTH = 500
CARD_MIN = 290
LEVEL_RANK = {"bad": 0, "warning": 1, "info": 2, "good": 3}

_images = {}


def icon(kind, on):
    key = (kind, on)
    if key not in _images:
        pil = art.tile(ICONS.get(kind, "globe"), "network", 72, on)
        _images[key] = ctk.CTkImage(light_image=pil, dark_image=pil, size=(36, 36))
    return _images[key]


def tr(prefix, value):
    """``t(prefix + value)``, or the value itself when no text is registered for it."""
    if value in (None, ""):
        return ""
    text = t(prefix + str(value))
    return str(value) if text == prefix + str(value) else text


def speed_text(bps):
    if not bps:
        return ""
    for div, unit in ((1e9, "Gbit/s"), (1e6, "Mbit/s"), (1e3, "kbit/s")):
        if bps >= div:
            v = bps / div
            return ("%d %s" % (v, unit)) if v == int(v) else ("%.1f %s" % (v, unit))
    return "%d bit/s" % bps


def ms_text(ms):
    if ms is None:
        return "–"
    return "<1 ms" if ms < 1 else "%s ms" % ms


def count(n):
    return "{:,}".format(int(n or 0)).replace(",", " ")


def mac_text(mac):
    if not mac:
        return ""
    try:
        if int(mac.replace(":", "-").split("-")[0], 16) & 0x02:
            return t("nx_r_mac_random", mac=mac)
    except ValueError:
        pass
    return mac


def yes_no(v):
    return "" if v is None else t("nx_yes") if v else t("nx_no")


def security_module():
    try:
        from ..netscan import security
        return security
    except Exception:          # the review is an extra: the rest of the tool works without it
        return None


# -- what the panel shows (also the copied report) ------------------------------------------------
def chain_rows(a):
    """[(step, ok, text)] for the connection chain, every step present."""
    p = a.get("probe") or {}
    cfg = a.get("config") or {}
    done = {}
    if p.get("chain"):
        done = {k: (ok, d) for k, ok, d in p["chain"]}
    elif cfg:
        done = {k: (ok, d) for k, ok, d in probe.chain(a, None)}
    rows = []
    for key in ("adapter", "address", "gateway", "dns", "internet"):
        if key not in done:
            rows.append((key, None, t("nx_c_skipped")))
            continue
        ok, d = done[key]
        if key == "gateway" and d == "none" and a.get("virtual"):
            ok = None                        # a host-only / internal virtual switch: no gateway is its normal state
        if key == "adapter":
            text = (a.get("name") + " · " + speed_text(a.get("speed_bps"))) if ok else t("nx_c_down")
        elif key == "address":
            text = d if ok else t("nx_c_apipa") if d == "apipa" else t("nx_c_noaddr")
        elif key == "gateway":
            g = p.get("gateway") or {}
            text = ("%s · %s" % (d, ms_text(g.get("avg")))) if ok else t("nx_c_nogw") if d == "none" else t("nx_c_gwdown")
        elif key == "dns":
            ok_ms = [x["ms"] for x in p.get("dns") or [] if x.get("ok")]
            text = ("%s · %s" % (d, ms_text(min(ok_ms)))) if ok and ok_ms else t("nx_c_dnsdown")
        else:
            net = p.get("internet") or {}
            text = t("nx_v_ok", ms=net.get("ms")) if ok else t("nx_c_portal") if d == "portal" else t("nx_c_netdown")
        rows.append((key, ok, text))
    return rows


def sections(a):
    """Everything known about the adapter, as [{"title", "rows": [(label, value, colour)], "table": ...}]."""
    cfg, p = a.get("config") or {}, a.get("probe") or {}
    out = []

    def sec(title, rows=(), tbl=None):
        rows = [r for r in rows if r[1] not in (None, "")]
        if rows or tbl:
            out.append({"title": t(title), "rows": rows, "table": tbl})

    drv = a.get("driver") or {}
    hw = cfg.get("hw") or {}
    sec("nx_sec_adapter", [
        (t("nx_r_name"), a.get("name"), None), (t("nx_r_desc"), a.get("desc"), None),
        (t("nx_r_kind"), t("nx_k_" + a.get("kind", "other")), None),
        (t("nx_r_status"), tr("nx_st_", a.get("status")), ui.GOOD if a.get("status") == "Up" else MUTED),
        (t("nx_r_speed"), speed_text(a.get("speed_bps")), None), (t("nx_r_mac"), mac_text(a.get("mac")), None),
        (t("nx_r_mtu"), a.get("mtu") or "", None),
        (t("nx_r_virtual"), t("nx_r_virtual_yes") if a.get("virtual") else t("nx_r_virtual_no"), None),
        (t("nx_r_driver"), " · ".join(x for x in (drv.get("provider"), drv.get("version"), drv.get("date")) if x), None),
        (t("nx_r_bus"), hw.get("pcie") and "PCIe " + hw["pcie"], None),
        (t("nx_r_index"), a.get("index"), None), (t("nx_r_guid"), a.get("guid"), None),
    ])

    wf = cfg.get("wifi")
    if wf:
        sig = wf.get("signal")
        sec("nx_sec_wifi", [
            (t("nx_r_ssid"), wf.get("ssid"), None), (t("nx_r_bssid"), wf.get("bssid"), None),
            (t("nx_r_auth"), wf.get("auth"), ui.BAD if wf.get("auth") in ("Open", "Shared key (WEP)", "WPA-Personal")
             else ui.GOOD if "WPA3" in (wf.get("auth") or "") else None),
            (t("nx_r_cipher"), wf.get("cipher"), ui.BAD if (wf.get("cipher") or "").startswith(("WEP", "TKIP", "None")) else None),
            (t("nx_r_phy"), wf.get("phy"), None),
            (t("nx_r_band"), " · ".join(str(x) for x in (wf.get("band"), wf.get("channel")) if x), None),
            (t("nx_r_signal"), sig is not None and ("%s%s" % (t("dh_pct", n=sig), " · %s dBm" % wf["rssi"] if wf.get("rssi") else "")),
             None if sig is None else ui.GOOD if sig >= 70 else ui.WARN if sig >= 40 else ui.BAD),
            (t("nx_r_rate"), "%s / %s Mbit/s" % (wf.get("rx_mbps"), wf.get("tx_mbps")), None),
            (t("nx_r_profile"), wf.get("profile"), None),
        ])

    rows = []
    for x in cfg.get("v4") or []:
        rows.append((t("nx_r_addr"), "%s/%s · %s%s" % (x["addr"], x.get("prefix"), tr("nx_o_", x.get("origin")),
                                                     "" if x.get("state") == "Preferred" else " · " + str(x.get("state"))),
                     ui.BAD if x.get("state") == "Duplicate" or (x["addr"] or "").startswith("169.254.") else None))
        try:
            net = ipaddress.ip_interface("%s/%s" % (x["addr"], x.get("prefix"))).network
            rows += [(t("nx_r_mask"), str(net.netmask), None),
                     (t("nx_r_network"), "%s / %s" % (net.network_address, net.broadcast_address), None),
                     (t("nx_r_hosts"), count(max(net.num_addresses - 2, 1)), None)]
        except ValueError:
            pass
    rows += [(t("nx_r_gateway"), ", ".join(cfg.get("gw4") or []), None)]
    if cfg.get("dhcp"):
        rows += [(t("nx_r_dhcp_server"), cfg.get("dhcp_server"), None),
                 (t("nx_r_lease"), "%s / %s" % ((cfg.get("lease_obtained") or "?").replace("T", " "),
                                                (cfg.get("lease_expires") or "?").replace("T", " ")), None)]
    rows += [(t("nx_r_metric"), cfg.get("metric"), None),
             (t("nx_r_forwarding"), None if cfg.get("forwarding") is None else t("nx_on") if cfg["forwarding"] else t("nx_off"),
              ui.WARN if cfg.get("forwarding") else None),
             (t("nx_r_netbios"), tr("nx_r_netbios_", cfg.get("netbios")), None)]
    if cfg:
        sec("nx_sec_ipv4", rows)

    rows = []
    for x in cfg.get("v6") or []:
        addr = x.get("addr") or ""
        kind = ("nx_v6_link" if addr.lower().startswith("fe80") else "nx_v6_ula" if addr.lower()[:2] in ("fc", "fd")
                else "nx_v6_temp" if x.get("suffix_origin") == "Random" else "nx_v6_global")
        rows.append((t("nx_r_addr"), "%s/%s · %s · %s" % (addr, x.get("prefix"), t(kind), tr("nx_o_", x.get("origin"))), None))
    rows += [(t("nx_r_gateway"), ", ".join(cfg.get("gw6") or []), None),
             (t("nx_r_v6_internet"), None if p.get("v6_internet") is None else t("nx_ok") if p["v6_internet"] else t("nx_fail"),
              None if p.get("v6_internet") is None else ui.GOOD if p["v6_internet"] else ui.WARN)]
    if cfg.get("v6"):
        sec("nx_sec_ipv6", rows)

    if cfg:
        answers = {d["server"]: d for d in p.get("dns") or []}
        srv = []
        for s in cfg.get("dns") or []:
            d = answers.get(s)
            note = "" if d is None else (" · " + ms_text(d["ms"])) if d["ok"] else " · " + t("nx_n_timeout")
            srv.append(s + note)
        sec("nx_sec_dns", [
            (t("nx_r_servers"), "\n".join(srv), None), (t("nx_r_suffix"), cfg.get("dns_suffix"), None),
            (t("nx_r_register"), yes_no(cfg.get("dns_register")), None),
            (t("nx_r_hijack"), None if p.get("nx_hijack") is None else t("nx_r_hijack_yes") if p["nx_hijack"] else t("nx_r_hijack_no"),
             ui.WARN if p.get("nx_hijack") else None),
        ])

    g = p.get("gateway")
    if g:
        opened = [port for port, ok in sorted((g.get("ports") or {}).items(), key=lambda kv: int(kv[0])) if ok]
        up = g.get("upnp")
        sec("nx_sec_router", [
            (t("nx_r_addr"), g.get("ip"), None), (t("nx_r_mac"), g.get("mac"), None),
            (t("nx_r_ping"), "%s / %s / %s" % (ms_text(g.get("min")), ms_text(g.get("avg")), ms_text(g.get("max"))), None),
            (t("nx_r_jitter"), "%s / %s" % (ms_text(g.get("jitter")), t("dh_pct", n=g.get("loss"))),
             ui.BAD if (g.get("loss") or 0) >= 25 else ui.WARN if (g.get("loss") or 0) > 0 else None),
            (t("nx_r_ports"), ", ".join("%s (%s)" % (port, PORT_NAMES.get(int(port), "?")) for port in opened)
             or t("nx_r_ports_none"), ui.WARN if any(int(x) in (21, 23, 2323) for x in opened) else None),
            (t("nx_r_web"), g.get("http_title"), None),
            (t("nx_r_upnp"), t("nx_r_upnp_on") if up else t("nx_r_upnp_off"), ui.WARN if up else None),
            (t("nx_r_vendor"), up and " · ".join(x for x in (up.get("manufacturer"), up.get("model"), up.get("model_number")) if x), None),
            (t("nx_r_fw"), up and (up.get("firmware") or up.get("friendly")), None),
            (t("nx_r_serial"), up and up.get("serial"), None),
            (t("nx_r_wan"), up and up.get("wan_ip"), None),
        ])
        maps = (up or {}).get("mappings") or []
        if maps:
            sec("nx_sec_upnp", tbl={
                "cols": [("proto", t("nx_col_proto"), 70), ("ext", t("nx_col_ext"), 80), ("to", t("nx_col_to"), 150),
                         ("desc", t("nx_col_desc"), 160)], "stretch": "desc",
                "rows": [((m.get("proto"), m.get("ext_port"), "%s:%s" % (m.get("client"), m.get("int_port")), m.get("desc") or ""),
                          "warn" if m.get("client") == p.get("src") else "") for m in maps]})

    if p:
        net, pub = p.get("internet") or {}, p.get("public") or {}
        pm = p.get("path_mtu")
        pm_text = (t("nx_r_pmtu_pppoe", n=pm) if pm == 1492 else t("nx_r_bytes", n=pm) if pm and pm >= 1500
                   else t("nx_r_pmtu_small", n=pm) if pm else None)
        sec("nx_sec_internet", [
            (t("nx_r_connect"), t("nx_v_ok", ms=net.get("ms")) if net.get("ok") else t("nx_c_portal") if net.get("portal")
             else t("nx_c_nogw") if net.get("no_gateway") else t("nx_c_netdown"),
             ui.GOOD if net.get("ok") else MUTED if net.get("no_gateway") else ui.BAD),
            (t("nx_r_public"), pub.get("ip"), None), (t("nx_r_country"), pub.get("country"), None),
            (t("nx_r_tls"), pub.get("tls"), None),
            (t("nx_r_pmtu"), pm_text, ui.WARN if pm and pm < 1492 else None),
            (t("nx_r_cgnat"), t("nx_r_cgnat_yes") if p.get("cgnat") else None, ui.WARN),
            (t("nx_r_dnat"), t("nx_r_dnat_yes") if p.get("double_nat") else None, ui.WARN),
        ])
        hops = p.get("hops") or []
        if hops:
            def hop_note(h):
                if not h["ip"]:
                    return t("nx_n_timeout")
                if h["ttl"] == 1:
                    return t("nx_n_router")
                return t("nx_n_private") if collect.is_private(h["ip"]) else ""
            sec("nx_sec_hops", tbl={
                "cols": [("ttl", t("nx_col_ttl"), 60), ("ip", t("nx_col_ip"), 150), ("ms", t("nx_col_ms"), 70),
                         ("note", t("nx_col_note"), 150)], "stretch": "note",
                "rows": [((h["ttl"], h["ip"] or "*", ms_text(h["ms"]) if h["ip"] else "", hop_note(h)),
                          "muted" if not h["ip"] else "") for h in hops]})

    prof = cfg.get("profile")
    if prof:
        sec("nx_sec_profile", [
            (t("nx_r_netname"), t("nx_r_netname_why", name=prof.get("name"), ssid=wf["ssid"])
             if wf and wf.get("ssid") and prof.get("name") and prof["name"] != wf["ssid"] else prof.get("name"), None),
            (t("nx_r_category"), tr("nx_r_cat_", prof.get("category")), None),
            (t("nx_r_conn"), "%s / %s" % (prof.get("v4"), prof.get("v6")), None),
        ])

    st = cfg.get("stats")
    if st:
        err_in, err_out = st.get("rx_errors") or 0, st.get("tx_errors") or 0
        dis_in, dis_out = st.get("rx_discards") or 0, st.get("tx_discards") or 0
        sec("nx_sec_traffic", [
            (t("nx_r_rx"), t("nx_r_pkts", bytes=human(st.get("rx_bytes")), pkts=count(st.get("rx_unicast"))), None),
            (t("nx_r_tx"), t("nx_r_pkts", bytes=human(st.get("tx_bytes")), pkts=count(st.get("tx_unicast"))), None),
            (t("nx_r_errors"), "%s / %s" % (count(err_in), count(err_out)), ui.WARN if err_in + err_out else None),
            (t("nx_r_discards"), "%s / %s" % (count(dis_in), count(dis_out)), None),
        ])

    nbs = cfg.get("neighbors") or []
    if nbs:
        gw = (cfg.get("gw4") or [None])[0]

        def ipkey(n):
            try:
                return int(ipaddress.ip_address(n["ip"]))
            except ValueError:
                return 0
        sec("nx_sec_neighbors", tbl={
            "cols": [("ip", t("nx_col_ip"), 130), ("mac", t("nx_col_mac"), 150), ("state", t("nx_col_state"), 90),
                     ("note", t("nx_col_note"), 100)], "stretch": "note",
            "rows": [((n["ip"], n["mac"], n.get("state"), t("nx_n_router") if n["ip"] == gw else ""), "")
                     for n in sorted(nbs, key=ipkey)]})

    b = cfg.get("bindings") or {}
    if b:
        sec("nx_sec_bindings", [(tr("nx_b_", k), t("nx_on") if v else t("nx_off"), None if v else MUTED)
                                for k, v in sorted(b.items(), key=lambda kv: (not kv[1], kv[0]))])
    adv = cfg.get("advanced") or {}
    if adv:
        sec("nx_sec_advanced", [(k, v, None) for k, v in adv.items()])
    return out


def report(a, findings):
    lines = ["%s — %s" % (a.get("name"), a.get("desc")), ""]
    lines.append("== " + t("nx_sec_chain"))
    for key, ok, text in chain_rows(a):
        lines.append("  [%s] %s: %s" % ("OK" if ok else "--" if ok is None else "XX", t("nx_s_" + key), text))
    if findings:
        lines += ["", "== " + t("nx_sec_security")]
        for f in findings:
            lines.append("  [%s] %s" % (f.get("level", "").upper(), f.get("title")))
            if f.get("detail"):
                lines.append("      " + f["detail"])
            if f.get("fix"):
                lines.append("      " + t("nx_f_fix", fix=f["fix"]))
    for s in sections(a):
        lines += ["", "== " + s["title"]]
        for label, value, _ in s["rows"]:
            lines.append("  %s: %s" % (label, str(value).replace("\n", ", ")))
        if s["table"]:
            lines.append("  " + " | ".join(c[1] for c in s["table"]["cols"]))
            for values, _tag in s["table"]["rows"]:
                lines.append("  " + " | ".join(str(v) for v in values))
    return "\n".join(lines)


# -- the screen -------------------------------------------------------------------------------------
class AdapterCard(ctk.CTkFrame):
    def __init__(self, master, view, a):
        super().__init__(master, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER, cursor="hand2")
        self.view, self.a = view, a
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))
        self.icon = ctk.CTkLabel(top, text="", image=icon(a["kind"], a.get("status") == "Up"))
        self.icon.pack(side="left", padx=(0, 10))
        self.state = ctk.CTkLabel(top, text="", font=("Segoe UI Semibold", 11), corner_radius=8, width=10, padx=8)
        self.state.pack(side="right", anchor="n", padx=(8, 0))
        names = ctk.CTkFrame(top, fg_color="transparent")
        names.pack(side="left", fill="x", expand=True)
        self.name = ctk.CTkLabel(names, text=a.get("name") or "?", font=("Segoe UI Semibold", 14), text_color=TEXT, anchor="w",
                                 justify="left", wraplength=CARD_MIN - 170)
        self.name.pack(fill="x")
        self.kind = ctk.CTkLabel(names, text=t("nx_k_" + a["kind"]), font=("Segoe UI", 11), text_color=MUTED, anchor="w")
        self.kind.pack(fill="x")
        self.desc = ctk.CTkLabel(self, text=a.get("desc") or "", font=("Segoe UI", 11), text_color=MUTED, anchor="w",
                                 justify="left", wraplength=CARD_MIN - 30)
        self.desc.pack(fill="x", padx=14)
        self.lines = ctk.CTkLabel(self, text="", font=("Consolas", 11), text_color=TEXT, anchor="w", justify="left")
        self.lines.pack(fill="x", padx=14, pady=(6, 0))
        # skeleton for the address lines until the adapter's settings are read
        self.ghosts = tk.Frame(self, bg=CARD, bd=0, highlightthickness=0)
        for w_ in (170, 140, 100):
            ui.ghost(self.ghosts, w_, 9, pady=4)
        self.verdict = ctk.CTkLabel(self, text="", font=("Segoe UI Semibold", 12), text_color=MUTED, anchor="w",
                                    justify="left", wraplength=CARD_MIN - 30)
        self.verdict.pack(fill="x", padx=14, pady=(4, 0))
        self.sub = ctk.CTkLabel(self, text="", font=("Segoe UI", 11), text_color=MUTED, anchor="w", justify="left",
                                wraplength=CARD_MIN - 30)
        self.sub.pack(fill="x", padx=14)
        self.bar = ctk.CTkProgressBar(self, height=6, corner_radius=3, fg_color=BORDER, progress_color=ui.ACCENT)
        self.bar.set(0)
        self.bar.pack(side="bottom", fill="x", padx=12, pady=(8, 10))
        self.bind_all_children(self)
        self.bind("<Configure>", self.on_resize)
        self.refresh()

    def bind_all_children(self, w):
        w.bind("<Button-1>", lambda e: self.view.select(self.a["index"]), add="+")
        w.bind("<Enter>", lambda e: self.hover(True), add="+")
        w.bind("<Leave>", lambda e: self.hover(False), add="+")
        for c in w.winfo_children():
            self.bind_all_children(c)

    def hover(self, on):
        self.configure(fg_color=CARD_HOVER if on else CARD)
        self.ghosts.configure(bg=CARD_HOVER if on else CARD)

    def on_resize(self, e):
        wrap = max(200, e.width - 40)
        self.name.configure(wraplength=max(110, e.width - 190))
        for lab in (self.desc, self.verdict, self.sub):
            lab.configure(wraplength=wrap)

    def selected(self, on):
        self.configure(border_color=ui.ACCENT if on else BORDER, border_width=2 if on else 1)

    def refresh(self):
        a, st = self.a, self.view.state.get(self.a["index"], {})
        up = a.get("status") == "Up"
        self.state.configure(text=tr("nx_st_", a.get("status")), fg_color="#173d2e" if up else BORDER,
                             text_color=ui.GOOD if up else MUTED)
        cfg = a.get("config") or {}
        lines = []
        wf = cfg.get("wifi")
        if wf:
            lines.append("%s · %s · %s" % (wf.get("ssid") or "?", t("dh_pct", n=wf.get("signal")), wf.get("phy") or ""))
        v4 = [x for x in cfg.get("v4") or [] if x.get("addr")]
        if v4 and up:
            lines.append("IPv4  %s/%s" % (v4[0]["addr"], v4[0].get("prefix")))
        if cfg.get("gw4"):
            lines.append("GW    %s" % cfg["gw4"][0])
        if up:
            lines.append("%s  %s" % ("Link ", speed_text(a.get("speed_bps"))))
        else:
            lines.append("MAC   %s" % (a.get("mac") or "–"))
        self.lines.configure(text="\n".join(lines))
        if not cfg and st.get("phase") in ("queued", "scanning"):
            self.lines.pack_forget()
            if not self.ghosts.winfo_manager():
                self.ghosts.pack(fill="x", padx=self.view.px(14), pady=(self.view.px(6), 0), before=self.verdict)
        elif self.ghosts.winfo_manager():
            self.ghosts.pack_forget()
            self.lines.pack(fill="x", padx=14, pady=(6, 0), before=self.verdict)

        phase = st.get("phase", "idle")
        if phase == "scanning":
            self.bar.configure(progress_color=ui.ACCENT)
            self.bar.set(st.get("frac", 0))
            self.verdict.configure(text=t("nx_step_" + st.get("step", "config")) + "…", text_color=ui.ACCENT)
            self.sub.configure(text="")
            return
        if phase == "queued":
            self.bar.configure(progress_color=BORDER)
            self.bar.set(0)
            self.verdict.configure(text=t("nx_queued"), text_color=MUTED)
            self.sub.configure(text="")
            return
        if phase == "error":
            self.bar.configure(progress_color=ui.BAD)
            self.bar.set(1)
            self.verdict.configure(text=t("nx_v_error", err=st.get("error")), text_color=ui.BAD)
            return
        if phase != "done":
            self.verdict.configure(text="")
            return
        text, color = self.view.verdict(a)
        self.verdict.configure(text=text, text_color=color)
        findings = st.get("findings") or []
        bad = sum(1 for f in findings if f.get("level") == "bad")
        warn = sum(1 for f in findings if f.get("level") == "warning")
        if not up:
            self.sub.configure(text=tr("nx_why_", a.get("status")) if t("nx_why_" + str(a.get("status"))) != "nx_why_" + str(a.get("status")) else "",
                               text_color=MUTED)
        elif bad:
            self.sub.configure(text=t("nx_v_issues", bad=bad, warn=warn), text_color=ui.BAD)
        elif warn:
            self.sub.configure(text=t("nx_v_warns", warn=warn), text_color=ui.WARN)
        elif findings:
            self.sub.configure(text=t("nx_v_clean"), text_color=ui.GOOD)
        else:
            self.sub.configure(text="")
        self.bar.configure(progress_color=self.view.bar_color(a))
        self.bar.set(1)


class View(ToolView):
    title_key = "tool_netdiag"

    def fill(self):
        if not hasattr(self, "adapters"):
            self.adapters, self.state, self.selected, self.posture = None, {}, None, None
            self.scanning, self.cards, self.columns = False, {}, 0
        self.scan_btn = ui.button(self.head, t("nx_scan"), self.scan_all, 140, primary=True)
        self.scan_btn.pack(side="right")
        self.info = ctk.CTkLabel(self.body, text=t("nx_loading"), font=("Segoe UI", 12), text_color=MUTED, anchor="w")
        self.info.pack(fill="x", pady=(0, 8))
        main = ctk.CTkFrame(self.body, fg_color=BG)
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self.panel = ctk.CTkFrame(main, fg_color=BG, width=PANEL_WIDTH)
        self.panel.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.panel.grid_propagate(False)
        self.panel.pack_propagate(False)
        self.panel.grid_remove()
        self.grid_area = ctk.CTkScrollableFrame(main, fg_color=BG, scrollbar_button_color=BORDER)
        self.grid_area.grid(row=0, column=0, sticky="nsew")
        self.grid_area.bind("<Configure>", lambda e: self.layout_cards())
        self.cards, self.columns = {}, 0
        if self.adapters is None:
            self.ghost_cards()
            self.run(collect.adapters, self.got_adapters, status=t("nx_loading"))
        else:
            self.render_cards()
            if self.selected is not None:
                self.select(self.selected, force=True)

    def busy(self):
        return self.jobs > 0 or self.scanning

    def ghost_cards(self, n=6, cols=3):
        """Card-shaped skeletons while the adapter list is read (replaced by render_cards)."""
        for c in range(cols):
            self.grid_area.grid_columnconfigure(c, weight=1, uniform="card")
        for i in range(n):
            g = ui.card(self.grid_area)
            g.grid(row=i // cols, column=i % cols, sticky="nsew", padx=(0, 12), pady=(0, 12))
            box = tk.Frame(g, bg=CARD, bd=0, highlightthickness=0)
            box.pack(fill="x", padx=self.px(14), pady=self.px(14))
            top = tk.Frame(box, bg=CARD, bd=0, highlightthickness=0)
            top.pack(fill="x", pady=(0, self.px(10)))
            ui.ghost(top, 36, 36, side="left", padx=(0, 10))
            col = tk.Frame(top, bg=CARD, bd=0, highlightthickness=0)
            col.pack(side="left")
            ui.ghost(col, 120, 13)
            ui.ghost(col, 80, 9)
            for w_ in (210, 160, 130, 100):
                ui.ghost(box, w_, 9, pady=4)
            ui.ghost(box, 260, 6, pady=(14, 0))

    # -- data --------------------------------------------------------------------------------------
    def got_adapters(self, result):
        if isinstance(result, Exception):
            self.adapters = []
            self.info.configure(text=t("nx_failed", err=result), text_color=ui.BAD)
            return
        self.adapters = result
        self.render_cards()
        self.scan_all()

    def adapter(self, index):
        return next((a for a in self.adapters or [] if a["index"] == index), None)

    def scan_all(self):
        if self.scanning or not self.adapters:
            if self.adapters == [] and not self.jobs:
                self.adapters = None
                self.run(collect.adapters, self.got_adapters, status=t("nx_loading"))
            return
        self.start_scan([a["index"] for a in self.adapters])

    def start_scan(self, indexes):
        self.scanning = True
        self.scan_btn.configure(state="disabled")
        for i in indexes:
            self.state[i] = {"phase": "queued"}
            self.update_card(i)
        sec = security_module()

        def posture():
            try:
                return sec.system_posture() if sec else {}
            except Exception:
                return {}

        def work():
            pool = ThreadPoolExecutor(1)
            fut = pool.submit(posture) if self.posture is None or len(indexes) > 1 else None
            for i in indexes:
                a = self.adapter(i)
                if a is None:
                    continue
                self.post(self.show_info, t("nx_scanning", name=a.get("name")))
                self.scan_one(a, sec, fut)
            pool.shutdown(wait=False)
            self.post(self.scan_finished)
        threading.Thread(target=work, daemon=True).start()

    def scan_one(self, a, sec, posture_future):
        i = a["index"]
        n = len(probe.STEPS) + 2

        def step(name, k=[0]):
            k[0] += 1
            self.state[i] = {"phase": "scanning", "step": name, "frac": min(0.97, k[0] / n)}
            self.post(self.update_card, i)
        try:
            step("config")
            fresh = {x["index"]: x for x in collect.adapters()}.get(i)
            if fresh:                          # status, speed... may have changed since the list was read
                for key in ("status", "speed_bps", "mtu", "mac"):
                    a[key] = fresh.get(key)
            a["config"] = collect.config(a)
            a["probe"] = probe.run(a, step=step)
            step("security")
            findings = []
            if sec:
                if posture_future is not None:
                    self.posture = posture_future.result()
                try:
                    findings = sec.assess(a, self.posture or {})
                except Exception:
                    findings = []
            self.state[i] = {"phase": "done", "findings": findings}
        except Exception as ex:
            self.state[i] = {"phase": "error", "error": str(ex).splitlines()[0] if str(ex) else type(ex).__name__}
        self.post(self.card_done, i)

    def show_info(self, text, color=MUTED):
        if self.info.winfo_exists():
            self.info.configure(text=text, text_color=color)

    def scan_finished(self):
        self.scanning = False
        self.scan_btn.configure(state="normal")
        self.info.configure(text=t("nx_done", n=len(self.adapters or [])) + " · " + t("nx_hint"), text_color=MUTED)

    def update_card(self, i):
        c = self.cards.get(i)
        if c is not None and c.winfo_exists():
            c.refresh()
        if self.selected == i and self.state.get(i, {}).get("phase") == "scanning":
            self.panel_status(i)

    def card_done(self, i):
        self.update_card(i)
        if self.selected == i:
            self.render_panel()

    def verdict(self, a):
        """The card's one-line verdict: (text, colour)."""
        if a.get("status") != "Up":
            return tr("nx_st_", a.get("status")), MUTED
        rows = chain_rows(a)
        if (a.get("config") or {}) and not (a["config"].get("gw4")) and collect.usable_v4(a["config"]):
            return t("nx_v_local"), MUTED
        broken = next(((k, text) for k, ok, text in rows if ok is False), None)
        if broken is None and any(ok is None for _, ok, _ in rows):
            return t("nx_queued"), MUTED          # not scanned far enough to say
        if broken is None:
            ms = ((a.get("probe") or {}).get("internet") or {}).get("ms")
            return t("nx_v_ok", ms=ms), ui.GOOD
        key = broken[0]
        if key == "gateway" and not (a.get("config") or {}).get("gw4"):
            return t("nx_v_local"), MUTED
        if key == "internet" and ((a.get("probe") or {}).get("internet") or {}).get("portal"):
            return t("nx_v_portal"), ui.WARN
        return t("nx_v_break", step=t("nx_s_" + key)), ui.BAD

    def bar_color(self, a):
        findings = self.state.get(a["index"], {}).get("findings") or []
        levels = {f.get("level") for f in findings}
        _, color = self.verdict(a)
        if color == ui.BAD or "bad" in levels:
            return ui.BAD
        if color == ui.WARN or "warning" in levels:
            return ui.WARN
        return ui.GOOD if a.get("status") == "Up" and color == ui.GOOD else MUTED

    # -- cards -------------------------------------------------------------------------------------
    def render_cards(self):
        for w_ in self.grid_area.winfo_children():
            w_.destroy()
        self.cards, self.columns = {}, 0
        if not self.adapters:
            self.info.configure(text=t("nx_none"), text_color=MUTED)
            return
        up = sum(1 for a in self.adapters if a.get("status") == "Up")
        if not self.scanning:
            self.info.configure(text=t("nx_count", n=len(self.adapters), up=up) + " · " + t("nx_hint"), text_color=MUTED)
        for a in self.adapters:
            self.cards[a["index"]] = AdapterCard(self.grid_area, self, a)
            if a["index"] == self.selected:
                self.cards[a["index"]].selected(True)
        self.layout_cards(force=True)

    def layout_cards(self, force=False):
        if not self.cards:
            return
        width = self.grid_area.winfo_width()
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        cols = max(1, int(width / scale) // (CARD_MIN + 12)) if width > 1 else 2
        if cols == self.columns and not force:
            return
        self.columns = cols
        for c in range(6):
            self.grid_area.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="card" if c < cols else "")
        for n, a in enumerate(self.adapters):
            card_ = self.cards[a["index"]]
            card_.grid(row=n // cols, column=n % cols, sticky="nsew", padx=(0, 12), pady=(0, 12))

    # -- right panel -------------------------------------------------------------------------------
    def select(self, index, force=False):
        if self.selected == index and not force and self.panel.winfo_manager():
            return
        for i, c in self.cards.items():
            c.selected(i == index)
        self.selected = index
        self.panel.grid()
        self.render_panel()
        self.after(50, self.layout_cards)

    def close_panel(self):
        self.selected = None
        for c in self.cards.values():
            c.selected(False)
        self.panel.grid_remove()
        self.after(50, self.layout_cards)

    def panel_status(self, i):
        lab = getattr(self, "panel_note", None)
        if lab is not None and lab.winfo_exists():
            st = self.state.get(i, {})
            lab.configure(text=t("nx_p_scanning", step=t("nx_step_" + st.get("step", "config"))), text_color=ui.ACCENT)

    def render_panel(self):
        # the old content is hidden at once and destroyed when Tk is idle (destroying ~300 widgets is slow)
        old = self.panel.winfo_children()
        for w_ in old:
            w_.pack_forget()
        self.after(300, lambda: [w_.destroy() for w_ in old if w_.winfo_exists()])
        self.panel_gen = getattr(self, "panel_gen", 0) + 1
        a = self.adapter(self.selected)
        if a is None:
            self.close_panel()
            return
        st = self.state.get(a["index"], {})
        findings = st.get("findings") or []
        head = ui.card(self.panel)
        head.pack(fill="x", pady=(0, 8))
        row = ctk.CTkFrame(head, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(row, text="", image=icon(a["kind"], a.get("status") == "Up")).pack(side="left", padx=(0, 10))
        box = ctk.CTkFrame(row, fg_color="transparent")
        box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(box, text=a.get("name"), font=("Segoe UI Semibold", 16), text_color=TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(box, text=a.get("desc"), font=("Segoe UI", 11), text_color=MUTED, anchor="w", justify="left",
                     wraplength=PANEL_WIDTH - 140).pack(fill="x")
        ctk.CTkButton(row, text="✕", width=30, height=30, fg_color="transparent", hover_color=BORDER, text_color=MUTED,
                      font=("Segoe UI", 14), command=self.close_panel).pack(side="right", anchor="n")
        text, color = self.verdict(a) if st.get("phase") == "done" else ("", MUTED)
        self.panel_note = ctk.CTkLabel(head, text=text, font=("Segoe UI Semibold", 13), text_color=color, anchor="w",
                                       justify="left", wraplength=PANEL_WIDTH - 40)
        self.panel_note.pack(fill="x", padx=14, pady=(8, 0))
        if st.get("phase") == "scanning":
            self.panel_status(a["index"])
        elif st.get("phase") in (None, "idle", "queued"):
            self.panel_note.configure(text=t("nx_p_waiting"), text_color=MUTED)
        btns = ctk.CTkFrame(head, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=(8, 12))
        rescan = ui.button(btns, t("nx_rescan_one"), lambda: self.start_scan([a["index"]]), 150)
        rescan.pack(side="left")
        if self.scanning:
            rescan.configure(state="disabled")
        copy = ui.button(btns, t("nx_copy"), None, 130)
        copy.configure(command=lambda: self.copy_report(a, findings, copy))
        copy.pack(side="left", padx=8)

        page = ctk.CTkScrollableFrame(self.panel, fg_color=BG, scrollbar_button_color=BORDER)
        page.pack(fill="both", expand=True)
        if not a.get("config") and st.get("phase") != "done":
            for rows in (5, 3, 6, 4):                 # not read yet: the shape of what is coming
                ui.ghost_card(page, rows)
            return

        # The page holds a few hundred lines of text.  A customtkinter label is a canvas plus a label that
        # redraws itself on every size change, so the text is plain Tk (one cheap widget each); only the
        # cards around it are customtkinter.  Plain Tk does not scale, hence px().
        px = self.px

        def body(card_):
            f = tk.Frame(card_, bg=CARD, bd=0, highlightthickness=0)
            f.pack(fill="x", padx=px(14), pady=(0, px(10)))
            return f

        # connection chain
        c = ui.card(page, t("nx_sec_chain"))
        c.pack(fill="x", pady=(0, 8))
        box = body(c)
        box.grid_columnconfigure(1, weight=1)
        for n, (key, ok, text) in enumerate(chain_rows(a)):
            mark, col = ("✓", ui.GOOD) if ok else ("✕", ui.BAD) if ok is False else ("–", MUTED)
            self.text(box, mark, 15, True, col).grid(row=2 * n, column=0, rowspan=2, sticky="nw", padx=(0, px(8)))
            self.text(box, t("nx_s_" + key), 12, True).grid(row=2 * n, column=1, sticky="w", pady=(px(3), 0))
            self.text(box, text, 11, color=col if ok is False else MUTED, wrap=PANEL_WIDTH - 110).grid(
                row=2 * n + 1, column=1, sticky="w")
        if a.get("status") == "Up" and st.get("phase") == "done" and not a.get("probe"):
            self.text(body(c), t("nx_p_noprobe"), 11, color=MUTED, wrap=PANEL_WIDTH - 60).pack(fill="x")

        # security review
        if findings:
            c = ui.card(page, t("nx_sec_security"))
            c.pack(fill="x", pady=(0, 8))
            box = body(c)
            for f in sorted(findings, key=lambda f: LEVEL_RANK.get(f.get("level"), 9)):
                col = ui.LEVEL.get(f.get("level"), MUTED)
                r = tk.Frame(box, bg=CARD, bd=0, highlightthickness=0)
                r.pack(fill="x", pady=px(3))
                tk.Frame(r, bg=col, width=px(4), bd=0, highlightthickness=0).pack(side="left", fill="y", padx=(0, px(10)))
                b = tk.Frame(r, bg=CARD, bd=0, highlightthickness=0)
                b.pack(side="left", fill="x", expand=True)
                self.text(b, f.get("title", ""), 12, True, col, wrap=PANEL_WIDTH - 90).pack(fill="x")
                if f.get("detail"):
                    self.text(b, f["detail"], 11, wrap=PANEL_WIDTH - 90).pack(fill="x")
                if f.get("fix"):
                    self.text(b, t("nx_f_fix", fix=f["fix"]), 11, color=MUTED, wrap=PANEL_WIDTH - 90).pack(fill="x")

        # The rest goes in one card at a time: the top of the panel is on screen at once and the cards
        # below it arrive while it is being read, instead of everything appearing after a pause.
        gen, todo = self.panel_gen, list(sections(a))

        def next_card():
            if gen != self.panel_gen or not page.winfo_exists() or not todo:
                return
            self.section_card(page, todo.pop(0))
            self.after(1, next_card)
        self.after(1, next_card)

    def section_card(self, page, s):
        px = self.px

        def body(card_):
            f = tk.Frame(card_, bg=CARD, bd=0, highlightthickness=0)
            f.pack(fill="x", padx=px(14), pady=(0, px(10)))
            return f
        c = ui.card(page, s["title"])
        c.pack(fill="x", pady=(0, 8))
        if s["rows"]:
            grid = body(c)
            grid.grid_columnconfigure(1, weight=1)
            for n, (label, value, col) in enumerate(s["rows"]):
                self.text(grid, label, 11, color=MUTED, wrap=170).grid(row=n, column=0, sticky="nw", padx=(0, px(12)), pady=px(1))
                self.text(grid, str(value), 11, True, col or TEXT, wrap=PANEL_WIDTH - 230).grid(
                    row=n, column=1, sticky="nw", pady=px(1))
        if s["table"]:
            tb = s["table"]
            holder, tree = table(c, tb["cols"], height=min(10, max(1, len(tb["rows"]))), stretch=tb.get("stretch"))
            holder.pack(fill="x", padx=12, pady=(0, 12))
            for values, tag in tb["rows"]:
                tree.insert("", "end", values=values, tags=(tag,) if tag else ())

    def px(self, n):
        return round(n * ctk.ScalingTracker.get_widget_scaling(self))

    def text(self, parent, text, size=11, bold=False, color=TEXT, wrap=0):
        """A plain Tk label sized like a customtkinter one (``size`` in unscaled pixels)."""
        return tk.Label(parent, text=text, font=("Segoe UI Semibold" if bold else "Segoe UI", -self.px(size)), fg=color,
                        bg=CARD, anchor="w", justify="left", wraplength=self.px(wrap) if wrap else 0, bd=0, padx=0,
                        pady=0, highlightthickness=0)

    def copy_report(self, a, findings, button):
        self.clipboard_clear()
        self.clipboard_append(report(a, findings))
        button.configure(text=t("nx_copied"))
        self.after(1500, lambda: button.winfo_exists() and button.configure(text=t("nx_copy")))
