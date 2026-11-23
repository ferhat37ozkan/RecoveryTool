"""The PowerShell side of the network inspection: which adapters there are and how each is set up.
See the package docstring for the record layout."""

from __future__ import annotations

import ipaddress

from ..toolkit import as_list, powershell_json

ADAPTERS = r"""
@(Get-NetAdapter | ForEach-Object { [pscustomobject]@{
  index = [int]$_.ifIndex; name = $_.Name; desc = $_.InterfaceDescription; guid = [string]$_.InterfaceGuid
  mac = $_.MacAddress; status = [string]$_.Status; media = [string]$_.PhysicalMediaType
  ndis = [int]$_.NdisPhysicalMedium; virtual = [bool]$_.Virtual; hardware = [bool]$_.HardwareInterface
  speed_bps = [int64]$_.Speed; mtu = [int]$_.MtuSize
  provider = $_.DriverProvider; version = $_.DriverVersionString; date = [string]$_.DriverDate } }) |
  ConvertTo-Json -Depth 3 -Compress
"""

CONFIG = r"""
$i = __INDEX__
$a = Get-NetAdapter -InterfaceIndex $i
$ips = @(Get-NetIPAddress -InterfaceIndex $i | ForEach-Object { [pscustomobject]@{ addr = $_.IPAddress -replace '%\d+$', '';
  prefix = [int]$_.PrefixLength; origin = [string]$_.PrefixOrigin; suffix_origin = [string]$_.SuffixOrigin;
  state = [string]$_.AddressState; family = [string]$_.AddressFamily } })
$routes = @(Get-NetRoute -InterfaceIndex $i | Where-Object { $_.DestinationPrefix -in '0.0.0.0/0', '::/0' } |
  Sort-Object RouteMetric | ForEach-Object { [pscustomobject]@{ hop = $_.NextHop; v6 = ($_.AddressFamily -eq 23) } })
$dns = @(Get-DnsClientServerAddress -InterfaceIndex $i | ForEach-Object { $_.ServerAddresses })
$dc = Get-DnsClient -InterfaceIndex $i
$if4 = Get-NetIPInterface -InterfaceIndex $i -AddressFamily IPv4
$cfg = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "InterfaceIndex=$i"
$prof = Get-NetConnectionProfile -InterfaceIndex $i | Select-Object -First 1
$bind = @{}; Get-NetAdapterBinding -Name $a.Name | ForEach-Object { $bind[$_.ComponentID] = [bool]$_.Enabled }
$st = Get-NetAdapterStatistics -Name $a.Name
$adv = [ordered]@{}; Get-NetAdapterAdvancedProperty -Name $a.Name | Where-Object { $_.DisplayValue -ne $null -and $_.DisplayValue -ne '' } |
  ForEach-Object { $adv[$_.DisplayName] = [string]$_.DisplayValue }
$hw = Get-NetAdapterHardwareInfo -Name $a.Name
$nb = @(Get-NetNeighbor -InterfaceIndex $i -AddressFamily IPv4 | Where-Object { $_.State -in 'Reachable','Stale','Delay','Probe','Permanent' -and
  $_.LinkLayerAddress -and $_.LinkLayerAddress -notmatch '^(00-00-00-00-00-00|FF-FF-FF-FF-FF-FF|01-00-5E)' } |
  ForEach-Object { [pscustomobject]@{ ip = $_.IPAddress; mac = $_.LinkLayerAddress; state = [string]$_.State } })
function iso($d) { if ($d) { ([datetime]$d).ToString('s') } else { $null } }
[pscustomobject]@{
  ips = $ips; routes = $routes; dns = $dns; dns_suffix = $dc.ConnectionSpecificSuffix
  dns_register = [bool]$dc.RegisterThisConnectionsAddress
  dhcp = [bool]$cfg.DHCPEnabled; dhcp_server = $cfg.DHCPServer
  lease_obtained = (iso $cfg.DHCPLeaseObtained); lease_expires = (iso $cfg.DHCPLeaseExpires)
  netbios = $cfg.TcpipNetbiosOptions; metric = $if4.InterfaceMetric; forwarding = ([string]$if4.Forwarding -eq 'Enabled')
  mtu4 = $if4.NlMtu
  profile = $(if ($prof) { [pscustomobject]@{ name = $prof.Name; category = [string]$prof.NetworkCategory;
    v4 = [string]$prof.IPv4Connectivity; v6 = [string]$prof.IPv6Connectivity } } else { $null })
  bindings = $bind
  stats = $(if ($st) { [pscustomobject]@{ rx_bytes = [int64]$st.ReceivedBytes; tx_bytes = [int64]$st.SentBytes;
    rx_unicast = [int64]$st.ReceivedUnicastPackets; tx_unicast = [int64]$st.SentUnicastPackets;
    rx_errors = [int64]$st.ReceivedPacketErrors; tx_errors = [int64]$st.OutboundPacketErrors;
    rx_discards = [int64]$st.ReceivedDiscardedPackets; tx_discards = [int64]$st.OutboundDiscardedPackets } } else { $null })
  advanced = $adv
  hw = $(if ($hw) { [pscustomobject]@{ bus = $hw.BusNumber; slot = $hw.SlotNumber;
    pcie = $(if ($hw.PciExpressCurrentLinkWidth) { 'Gen{0} x{1} (max Gen{2} x{3})' -f $hw.PciExpressCurrentLinkSpeedEncoded,
      $hw.PciExpressCurrentLinkWidth, $hw.PciExpressMaxLinkSpeedEncoded, $hw.PciExpressMaxLinkWidth } else { $null }) } } else { $null })
  neighbors = $nb
} | ConvertTo-Json -Depth 4 -Compress
"""

VIRTUAL_WORDS = ("hyper-v", "vmware", "virtualbox", "virtual", "vethernet", "wsl", "docker", "loopback",
                 "npcap", "kernel debug", "parallels", "qemu", "virtio")
VPN_WORDS = ("vpn", "tap-", "tap ", "tun", "wireguard", "wintun", "anyconnect", "fortinet", "openvpn", "zerotier",
             "tailscale", "pangp", "juniper", "sonicwall", "nordlynx", "ppp", "wan miniport")


def classify(a):
    text = ("%s %s" % (a.get("desc") or "", a.get("name") or "")).lower()
    media, ndis = (a.get("media") or "").lower(), a.get("ndis") or 0
    if ndis == 10 or "bluetooth" in media or "bluetooth" in text:
        return "bluetooth"
    if ndis == 9 or "802.11" in media or "wi-fi" in text or "wireless" in text or "wlan" in text:
        return "wifi"
    if ndis in (8, 12) or "wwan" in text or "mobile broadband" in text or "cellular" in text:
        return "cellular"
    if any(w in text for w in VPN_WORDS):
        return "vpn"
    if a.get("virtual") or not a.get("hardware", True) or any(w in text for w in VIRTUAL_WORDS):
        return "virtual"
    if ndis == 14 or "802.3" in media or "ethernet" in text or "gbe" in text:
        return "ethernet"
    return "other"


def adapters():
    out = []
    for a in as_list(powershell_json(ADAPTERS, timeout=60)):
        a["kind"] = classify(a)
        a["virtual"] = a["kind"] in ("virtual", "vpn") or bool(a.get("virtual"))
        a["driver"] = {"provider": a.pop("provider", None), "version": a.pop("version", None),
                       "date": _date(a.pop("date", None))}
        a["guid"] = (a.get("guid") or "").upper()
        out.append(a)
    order = {"Up": 0, "Disconnected": 1, "Disabled": 2}
    kinds = ("ethernet", "wifi", "cellular", "vpn", "bluetooth", "virtual", "other")
    out.sort(key=lambda a: (order.get(a.get("status"), 3), kinds.index(a["kind"]), a.get("name") or ""))
    return out


def _date(text):
    """'2025-01-27' from Windows' driver date in any of its shapes."""
    if not text:
        return None
    import re
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2)))
    return None


def config(adapter):
    raw = powershell_json(CONFIG.replace("__INDEX__", str(int(adapter["index"]))), timeout=60) or {}
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    ips = as_list(raw.get("ips"))
    v4 = [_ip(x) for x in ips if x.get("family") == "IPv4"]
    v6 = [_ip(x) for x in ips if x.get("family") == "IPv6"]
    routes = as_list(raw.get("routes"))
    cfg = {
        "v4": v4, "v6": v6,
        "gw4": _uniq(r["hop"] for r in routes if not r.get("v6") and r.get("hop") not in (None, "0.0.0.0")),
        "gw6": _uniq(r["hop"] for r in routes if r.get("v6") and r.get("hop") not in (None, "::")),
        "dns": _uniq(as_list(raw.get("dns"))),
        "dns_suffix": raw.get("dns_suffix") or "", "dns_register": raw.get("dns_register"),
        "dhcp": raw.get("dhcp"), "dhcp_server": raw.get("dhcp_server"),
        "lease_obtained": raw.get("lease_obtained"), "lease_expires": raw.get("lease_expires"),
        "netbios": raw.get("netbios"), "metric": raw.get("metric"), "forwarding": raw.get("forwarding"),
        "profile": raw.get("profile"), "bindings": raw.get("bindings") or {}, "stats": raw.get("stats"),
        "neighbors": as_list(raw.get("neighbors")), "advanced": raw.get("advanced") or {}, "hw": raw.get("hw"),
    }
    if raw.get("mtu4"):
        adapter["mtu"] = raw["mtu4"]
    if adapter.get("kind") == "wifi" and adapter.get("status") == "Up":
        try:
            cfg["wifi"] = wifi_details(adapter.get("guid"))
        except Exception:
            cfg["wifi"] = None
    return cfg


def _ip(x):
    return {"addr": x.get("addr"), "prefix": x.get("prefix"), "origin": x.get("origin"),
            "suffix_origin": x.get("suffix_origin"), "state": x.get("state")}


def _uniq(items):
    seen = []
    for i in items:
        if i and i not in seen:
            seen.append(i)
    return seen


# -- Wi-Fi link ---------------------------------------------------------------------------------
AUTH = {1: "Open", 2: "Shared key (WEP)", 3: "WPA-Enterprise", 4: "WPA-Personal", 5: "WPA-None",
        6: "WPA2-Enterprise", 7: "WPA2-Personal", 8: "WPA3-Enterprise (192-bit)", 9: "WPA3-Personal",
        10: "OWE (Enhanced Open)", 11: "WPA3-Enterprise"}
CIPHER = {0: "None", 1: "WEP-40", 2: "TKIP", 4: "CCMP (AES)", 5: "WEP-104", 6: "BIP", 8: "GCMP (AES)",
          9: "GCMP-256", 10: "CCMP-256", 0x100: "WPA-group", 0x101: "WEP"}
PHY = {1: "802.11 FHSS", 2: "802.11 DSSS", 3: "802.11 IR", 4: "802.11a", 5: "802.11b", 6: "802.11g",
       7: "802.11n", 8: "802.11ac", 9: "802.11ad", 10: "802.11ax", 11: "802.11be"}


def wifi_details(guid_text):
    """The connected Wi-Fi link of the adapter whose InterfaceGuid is ``guid_text``."""
    import ctypes
    from ..tools import wifi as W
    api = W.Wlan()
    try:
        for guid, desc, state in api.interfaces():
            g = "{%08X-%04X-%04X-%s-%s}" % (guid.Data1, guid.Data2, guid.Data3, bytes(guid.Data4[:2]).hex().upper(),
                                            bytes(guid.Data4[2:]).hex().upper())
            if g != guid_text or state != 1:
                continue
            size, data, kind = W.w.DWORD(), ctypes.c_void_p(), ctypes.c_int()
            if W.wlan.WlanQueryInterface(api.h, ctypes.byref(guid), 7, None, ctypes.byref(size), ctypes.byref(data),
                                         ctypes.byref(kind)) != 0:
                return None
            a = ctypes.cast(data, ctypes.POINTER(W.WLAN_CONNECTION_ATTRIBUTES)).contents
            assoc, sec = a.wlanAssociationAttributes, a.wlanSecurityAttributes
            res = {"profile": a.strProfileName, "ssid": W.ssid_text(assoc.dot11Ssid),
                   "bssid": ":".join("%02x" % b for b in assoc.dot11Bssid), "signal": assoc.wlanSignalQuality,
                   "rx_mbps": assoc.ulRxRate // 1000, "tx_mbps": assoc.ulTxRate // 1000,
                   "phy": PHY.get(assoc.dot11PhyType, str(assoc.dot11PhyType)),
                   "auth": AUTH.get(sec.dot11AuthAlgorithm, "#%d" % sec.dot11AuthAlgorithm),
                   "cipher": CIPHER.get(sec.dot11CipherAlgorithm, "#%d" % sec.dot11CipherAlgorithm),
                   "secured": bool(sec.bSecurityEnabled), "onex": bool(sec.bOneXEnabled)}
            W.wlan.WlanFreeMemory(data)
            mine = next((n for n in api.bss(guid) if n["bssid"] == res["bssid"]), None)
            if mine:
                res.update(channel=mine["channel"], band=mine["band"], rssi=mine["rssi"])
            return res
    finally:
        api.close()
    return None


# -- address helpers used by the probes and the security review ---------------------------------
def usable_v4(cfg):
    """The adapter's first usable IPv4 address (not APIPA, not duplicate)."""
    for x in cfg.get("v4") or []:
        a = x.get("addr") or ""
        if a and not a.startswith("169.254.") and x.get("state") not in ("Duplicate", "Invalid", "Tentative"):
            return a
    return None


def is_private(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private or a.is_link_local or a in ipaddress.ip_network("100.64.0.0/10")


def is_cgnat(ip):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False
