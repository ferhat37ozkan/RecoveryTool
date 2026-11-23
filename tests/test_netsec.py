"""Unit tests for the network security review. Made-up adapters; nothing is queried.

    python tests\\test_netsec.py      (or: python -m pytest tests/test_netsec.py -q)
"""

from __future__ import annotations

import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from recoverytool import i18n  # noqa: E402
from benchwise.netscan import security  # noqa: E402

TODAY = datetime.date(2026, 11, 23)

POSTURE_SAFE = {
    "firewall": {n: {"enabled": True, "inbound": "Block"} for n in ("Domain", "Private", "Public")},
    "smb1": False, "llmnr": True, "proxy": {"enabled": False, "server": "", "pac": ""}, "wpad": True,
    "rdp": False, "listen_tcp": [{"addr": "0.0.0.0", "port": 135, "process": "svchost"}],
    "hosts": [], "sharing": ["Private"], "discovery": ["Private"], "wifi_auto_open": [],
}


def adapter(kind="ethernet", category="Private", wifi=None, v4="192.168.1.20", probe=None, **extra):
    a = {"index": 5, "name": "Ethernet", "kind": kind, "status": "Up", "virtual": False,
         "driver": {"date": "2025-06-01"},
         "config": {"v4": [{"addr": v4, "prefix": 24, "origin": "Dhcp", "state": "Preferred"}],
                    "gw4": ["192.168.1.1"], "dns": ["192.168.1.1"], "netbios": 0,
                    "profile": {"name": "Home", "category": category}, "bindings": {"ms_server": True},
                    "stats": {"rx_unicast": 100000, "tx_unicast": 50000}}}
    if wifi:
        a["config"]["wifi"] = wifi
    if probe is not None:
        a["probe"] = probe
    for k, v in extra.items():
        a["config"][k] = v
    return a


def keys(findings):
    return {(f["level"], f["key"]) for f in findings}


def test_home_network_is_calm():
    probe = {"gateway": {"ip": "192.168.1.1", "ports": {"80": True, "443": True, "53": True}, "upnp": None},
             "internet": {"ok": True}}
    f = security.assess(adapter(probe=probe), POSTURE_SAFE, TODAY)
    assert security.score(f) == "good", f
    k = keys(f)
    assert ("good", "firewall_on") in k and ("good", "upnp_off") in k and ("good", "gw_clean") in k, k
    assert ("info", "private_visible") in k, k


def test_open_wifi_marked_private():
    wifi = {"ssid": "Cafe", "auth": "Open", "cipher": "None", "signal": 30, "rssi": -80}
    f = security.assess(adapter("wifi", wifi=wifi), POSTURE_SAFE, TODAY)
    k = keys(f)
    assert ("bad", "wifi_open") in k and ("bad", "private_untrusted") in k and ("warning", "wifi_weak") in k, k
    assert ("warning", "poisoning") in k, k               # NetBIOS from DHCP + LLMNR on an untrusted network
    assert ("info", "wpad") in k, k
    assert f[0]["level"] == "bad" and security.score(f) == "bad"


def test_wifi_ciphers():
    def one(auth, cipher):
        return keys(security.assess(adapter("wifi", wifi={"ssid": "X", "auth": auth, "cipher": cipher,
                                                          "signal": 90}), {}, TODAY))
    assert ("bad", "wifi_wep") in one("Open", "WEP")
    assert ("bad", "wifi_wpa1") in one("WPA-Personal", "TKIP")
    assert ("warning", "wifi_wpa1") in one("WPA2-Personal", "TKIP")
    assert ("good", "wifi_wpa2") in one("WPA2-Personal", "CCMP")
    assert ("good", "wifi_wpa3") in one("WPA3-Personal", "GCMP")
    assert ("good", "wifi_enterprise") in one("WPA2-Enterprise", "CCMP")


def test_public_sharing_firewall_rdp():
    posture = dict(POSTURE_SAFE, sharing=["Private", "Public"], rdp=True, rdp_nla=True,
                   firewall={"Public": {"enabled": False, "inbound": "Block"}})
    k = keys(security.assess(adapter(category="Public"), posture, TODAY))
    assert ("bad", "public_sharing") in k and ("bad", "firewall_off") in k and ("warning", "rdp_public") in k, k
    posture = dict(POSTURE_SAFE, rdp=True, rdp_nla=False, smb1=True,
                   firewall={"Private": {"enabled": True, "inbound": "Allow"}})
    k = keys(security.assess(adapter(), posture, TODAY))
    assert ("bad", "rdp_no_nla") in k and ("bad", "smb1") in k and ("bad", "firewall_allow") in k, k


def test_public_address_exposes_services():
    posture = dict(POSTURE_SAFE, listen_tcp=[{"addr": "0.0.0.0", "port": 3389, "process": "svchost"},
                                             {"addr": "127.0.0.1", "port": 5432, "process": "db"},
                                             {"addr": "0.0.0.0", "port": 445, "process": "System"}])
    f = security.assess(adapter(v4="85.10.20.30", category="Public"), posture, TODAY)
    k = keys(f)
    assert ("warning", "public_ip") in k and ("bad", "exposed") in k, k
    detail = next(x["detail"] for x in f if x["key"] == "exposed")
    assert "3389" in detail and "445" in detail and "5432" not in detail, detail
    # a CGNAT address is not "public"
    assert ("warning", "public_ip") not in keys(security.assess(adapter(v4="100.70.1.2"), POSTURE_SAFE, TODAY))


def test_router_and_path():
    probe = {"gateway": {"ip": "192.168.1.1", "mac": "AA-BB-CC-00-11-22",
                         "ports": {"23": True, "21": True, "80": True, "443": False, "7547": True, "445": True},
                         "upnp": {"manufacturer": "Maker", "model": "R1", "mappings": [
                             {"proto": "TCP", "ext_port": 3389, "client": "192.168.1.50", "int_port": 3389, "desc": "x"},
                             {"proto": "UDP", "ext_port": 50000, "client": "192.168.1.20", "int_port": 50000, "desc": "call"},
                             {"proto": "TCP", "ext_port": 8080, "client": "192.168.1.60", "int_port": 80}]}},
             "gw_mac_shared": ["192.168.1.77"], "nx_hijack": True, "cgnat": True, "double_nat": True,
             "hops": [{"ttl": 1, "ip": "192.168.1.1"}, {"ttl": 2, "ip": "10.0.0.1"}],
             "dns": [{"server": "192.168.1.1", "ok": True}, {"server": "9.9.9.9", "ok": False}],
             "internet": {"ok": True, "portal": True}}
    k = keys(security.assess(adapter(probe=probe), POSTURE_SAFE, TODAY))
    for want in [("bad", "gw_telnet"), ("warning", "gw_ftp"), ("warning", "gw_smb"), ("info", "gw_http"),
                 ("info", "gw_tr069"), ("warning", "upnp"), ("bad", "upnp_risky"), ("warning", "upnp_self"),
                 ("info", "upnp_maps"), ("bad", "arp_spoof"), ("warning", "dns_hijack"), ("warning", "dns_fail"),
                 ("warning", "portal"), ("info", "cgnat"), ("info", "double_nat")]:
        assert want in k, (want, k)
    assert ("good", "gw_clean") not in k


def test_misc_addresses_proxy_driver_errors():
    posture = dict(POSTURE_SAFE, proxy={"enabled": True, "server": "10.9.9.9:8080", "pac": ""},
                   winhttp_proxy="10.9.9.9:8080", hosts=[{"ip": "1.2.3.4", "name": "bank.example"}],
                   wifi_auto_open=["Free"])
    a = adapter("wifi", wifi={"ssid": "Home", "auth": "WPA2-Personal", "cipher": "CCMP", "signal": 80},
                v6=[{"addr": "2a02:1:2::5", "suffix_origin": "Link"}], dns=["192.168.1.1", "84.200.69.80"],
                stats={"rx_unicast": 10000, "tx_unicast": 0, "rx_errors": 300})
    a["driver"] = {"date": "2019-01-01"}
    a["config"]["v4"].append({"addr": "192.168.1.21", "state": "Duplicate"})
    k = keys(security.assess(a, posture, TODAY))
    for want in [("warning", "proxy"), ("info", "proxy_system"), ("info", "hosts"), ("warning", "wifi_auto_open"),
                 ("info", "v6_privacy"), ("info", "dns_external"), ("info", "driver_old"), ("warning", "errors"),
                 ("bad", "ip_duplicate")]:
        assert want in k, (want, k)
    a = adapter(v4="169.254.3.4")
    assert ("warning", "apipa") in keys(security.assess(a, {}, TODAY))


def test_virtual_host_only_is_quiet():
    a = adapter(v4="192.168.56.1", category="")
    a["virtual"], a["config"]["gw4"], a["config"]["dns"] = True, [], ["8.8.8.8"]
    a["probe"] = {"gateway": {}, "nx_hijack": None}
    f = security.assess(a, POSTURE_SAFE, TODAY)
    assert not [x for x in f if x["key"] in ("dns_external", "gw_clean", "upnp_off")], f


def test_disconnected_and_empty():
    assert security.assess({"status": "Disconnected", "kind": "ethernet"}, {}, TODAY) == []
    assert security.score([]) == "good"


def test_texts_both_languages():
    try:
        for lang in ("en", "tr"):
            i18n.set_language(lang)
            posture = dict(POSTURE_SAFE, smb1=True, rdp=True, rdp_nla=False)
            for f in security.assess(adapter("wifi", wifi={"ssid": "S", "auth": "Open", "cipher": "None", "signal": 10},
                                             probe={"gateway": {"ports": {"23": 1}, "upnp": {"mappings": []}}}),
                                     posture, TODAY):
                assert not f["title"].startswith("sec_") and not f["detail"].startswith("sec_"), f
                assert f["level"] in security.LEVEL_ORDER
    finally:
        i18n.set_language("en")


def test_posture_parsing():
    import base64
    import struct
    conn = base64.b64encode(struct.pack("<III", 0x46, 1, 0x09) + b"\0" * 16).decode()
    proxy = b"10.0.0.5:3128"
    wh = base64.b64encode(struct.pack("<IIII", 0x28, 0, 3, len(proxy)) + proxy + struct.pack("<I", 0)).decode()
    p = security._parse_posture({
        "firewall": [{"name": "Public", "enabled": "True", "inbound": "NotConfigured"}],
        "llmnr": 0, "conn_settings": conn, "winhttp": wh, "hosts": ["127.0.0.1 localhost", "1.2.3.4 a.example b.example"],
        "sharing": ["Private, Public"], "discovery": "Any",
        "wifi_profiles": [{"name": "Free", "mode": "auto", "auth": "open", "enc": "none"},
                          {"name": "Home", "mode": "auto", "auth": "WPA2PSK", "enc": "AES"}]})
    assert p["firewall"]["Public"]["enabled"] is True
    assert p["llmnr"] is False and p["wpad"] is True and p["winhttp_proxy"] == "10.0.0.5:3128"
    assert [h["name"] for h in p["hosts"]] == ["a.example", "b.example"]
    assert p["sharing"] == ["Private", "Public"] and p["discovery"] == ["Domain", "Private", "Public"]
    assert p["wifi_auto_open"] == ["Free"]


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("network security tests passed")


if __name__ == "__main__":
    main()
