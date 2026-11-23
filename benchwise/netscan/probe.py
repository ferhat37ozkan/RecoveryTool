"""Live tests sent from one adapter's own IPv4 address.

Everything is bound to the source address, so Windows sends it out of that adapter (strong host
model): a VMware or VPN adapter can never answer for the Wi-Fi.  ICMP goes through iphlpapi
(IcmpSendEcho2Ex), which reports TTL-expired and too-big replies as numbers, so nothing depends on
the language Windows prints ``ping`` in."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import http.client
import os
import random
import re
import socket
import ssl
import statistics
import string
import struct
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

from . import collect

# -- ICMP ---------------------------------------------------------------------------------------
IP_SUCCESS, IP_TTL_EXPIRED_TRANSIT, IP_PACKET_TOO_BIG, IP_REQ_TIMED_OUT = 0, 11013, 11009, 11010
IP_DEST_NET_UNREACHABLE, IP_DEST_HOST_UNREACHABLE = 11002, 11003


class IP_OPTION_INFORMATION(ctypes.Structure):
    _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]


class ICMP_ECHO_REPLY(ctypes.Structure):
    _fields_ = [("Address", ctypes.c_ulong), ("Status", ctypes.c_ulong), ("RoundTripTime", ctypes.c_ulong),
                ("DataSize", ctypes.c_ushort), ("Reserved", ctypes.c_ushort), ("Data", ctypes.c_void_p),
                ("Options", IP_OPTION_INFORMATION)]


try:
    _icmp = ctypes.WinDLL("iphlpapi")
    _icmp.IcmpCreateFile.restype = w.HANDLE
    _icmp.IcmpCloseHandle.argtypes = [w.HANDLE]
    _icmp.IcmpSendEcho2Ex.argtypes = [w.HANDLE, w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong,
                                      ctypes.c_ulong, ctypes.c_void_p, w.WORD, ctypes.POINTER(IP_OPTION_INFORMATION),
                                      ctypes.c_void_p, w.DWORD, w.DWORD]
    _icmp.IcmpSendEcho2Ex.restype = w.DWORD
except (AttributeError, OSError):          # not Windows
    _icmp = None


def _addr(ip):
    return int.from_bytes(socket.inet_aton(ip), "little")


def _ip_text(n):
    return socket.inet_ntoa(int(n).to_bytes(4, "little"))


def echo(src, dst, ttl=128, size=32, df=False, timeout=1000):
    """One ICMP echo from ``src`` to ``dst``: (status, reply_ip, ms).  status None = could not send."""
    if _icmp is None:
        return None, None, None
    h = _icmp.IcmpCreateFile()
    if not h or h == w.HANDLE(-1).value:
        return None, None, None
    try:
        data = (ctypes.c_ubyte * size)(*([0x61] * size)) if size else None
        opts = IP_OPTION_INFORMATION(ttl, 0, 2 if df else 0, 0, None)
        buf_len = ctypes.sizeof(ICMP_ECHO_REPLY) + size + 8 + 64
        buf = ctypes.create_string_buffer(buf_len)
        n = _icmp.IcmpSendEcho2Ex(h, None, None, None, _addr(src), _addr(dst), data, size, ctypes.byref(opts),
                                  buf, buf_len, timeout)
        reply = ICMP_ECHO_REPLY.from_buffer(buf)
        if n == 0:
            err = ctypes.GetLastError()
            if err in (IP_PACKET_TOO_BIG, IP_REQ_TIMED_OUT, IP_TTL_EXPIRED_TRANSIT):
                return err, (_ip_text(reply.Address) if reply.Address else None), None
            return reply.Status or err or IP_REQ_TIMED_OUT, (_ip_text(reply.Address) if reply.Address else None), None
        return reply.Status, _ip_text(reply.Address), reply.RoundTripTime
    finally:
        _icmp.IcmpCloseHandle(h)


def ping_stats(src, dst, count=8, interval=0.15):
    times, lost = [], 0
    for _ in range(count):
        status, _, ms = echo(src, dst)
        if status == IP_SUCCESS and ms is not None:
            times.append(ms)
        else:
            lost += 1
        time.sleep(interval)
    if not times:
        return {"loss": 100, "min": None, "avg": None, "max": None, "jitter": None}
    jitter = statistics.mean(abs(a - b) for a, b in zip(times, times[1:])) if len(times) > 1 else 0
    return {"loss": round(100 * lost / count), "min": min(times), "avg": round(statistics.mean(times), 1),
            "max": max(times), "jitter": round(jitter, 1)}


def trace(src, dst="1.1.1.1", max_hops=8):
    """The first hops towards ``dst``; stops at the destination."""
    def one(ttl):
        for _ in range(2):
            status, ip, ms = echo(src, dst, ttl=ttl, timeout=1200)
            if ip and status in (IP_SUCCESS, IP_TTL_EXPIRED_TRANSIT):
                return {"ttl": ttl, "ip": ip, "ms": ms, "end": status == IP_SUCCESS}
        return {"ttl": ttl, "ip": None, "ms": None, "end": False}
    with ThreadPoolExecutor(max_hops) as ex:
        hops = list(ex.map(one, range(1, max_hops + 1)))
    out = []
    for h in hops:
        out.append(h)
        if h["end"]:
            break
    return out


def path_mtu(src, dst="1.1.1.1"):
    """Largest IPv4 packet (header included) that reaches ``dst`` with Don't Fragment set."""
    def passes(payload):
        for _ in range(2):
            status, _, _ = echo(src, dst, size=payload, df=True, timeout=1200)
            if status == IP_SUCCESS:
                return True
            if status == IP_PACKET_TOO_BIG:
                return False
        return False
    if not passes(64):
        return None
    if passes(1472):
        return 1500
    lo, hi = 64, 1472
    while hi - lo > 1:
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if passes(mid) else (lo, mid)
    return lo + 28


# -- TCP / HTTP ---------------------------------------------------------------------------------
ROUTER_PORTS = (21, 22, 23, 53, 80, 139, 443, 445, 1900, 5000, 7547, 8080, 8443, 8291, 2323, 49152)


def tcp_open(src, host, port, timeout=1.5):
    try:
        with socket.create_connection((host, port), timeout=timeout, source_address=(src, 0)):
            return True
    except OSError:
        return False


def port_scan(src, host, ports=ROUTER_PORTS):
    with ThreadPoolExecutor(16) as ex:
        return dict(zip(ports, ex.map(lambda p: tcp_open(src, host, p), ports)))


def http_get(src, host, path="/", https=False, timeout=6, port=None, headers=None, verify=True):
    """(status, headers dict, body bytes up to 64 KB, ms, tls version)."""
    t0 = time.time()
    if https:
        ctx = ssl.create_default_context() if verify else ssl._create_unverified_context()
        conn = http.client.HTTPSConnection(host, port or 443, timeout=timeout, source_address=(src, 0), context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port or 80, timeout=timeout, source_address=(src, 0))
    try:
        conn.request("GET", path, headers={"User-Agent": "Benchwise", "Connection": "close", **(headers or {})})
        r = conn.getresponse()
        body = r.read(65536)
        tls = conn.sock.version() if https and conn.sock else None
        return r.status, {k.lower(): v for k, v in r.getheaders()}, body, int((time.time() - t0) * 1000), tls
    finally:
        conn.close()


def router_title(src, gw, ports):
    """The <title> of the router's web page (its brand/model, usually)."""
    for https, port in ((False, 80), (True, 443), (False, 8080)):
        if not ports.get(port):
            continue
        try:
            status, hdr, body, _, _ = http_get(src, gw, https=https, port=port, timeout=4, verify=False)
        except Exception:
            continue
        m = re.search(rb"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        text = (m.group(1).decode("utf-8", "replace").strip() if m else "") or hdr.get("server", "")
        if text:
            return re.sub(r"\s+", " ", text)[:120]
    return None


CONNECT_HOST, CONNECT_PATH, CONNECT_BODY = "www.msftconnecttest.com", "/connecttest.txt", b"Microsoft Connect Test"


def internet(src, connect_ip):
    """HTTP connect test through this adapter (to an address resolved by its own DNS server)."""
    try:
        t0 = time.time()
        conn = http.client.HTTPConnection(connect_ip, 80, timeout=8, source_address=(src, 0))
        conn.request("GET", CONNECT_PATH, headers={"Host": CONNECT_HOST, "User-Agent": "Benchwise", "Connection": "close"})
        r = conn.getresponse()
        body = r.read(400)
        conn.close()
        ms = int((time.time() - t0) * 1000)
        if r.status == 200 and body.startswith(CONNECT_BODY):
            return {"ok": True, "portal": False, "ms": ms, "intercepted": False}
        # a redirect or a page with a form is a login page; any other 200 with a different body means
        # something on the way rewrites plain web traffic
        portal = r.status in (301, 302, 303, 307, 308, 511) or (r.status == 200 and b"<form" in body.lower())
        return {"ok": False, "portal": portal, "ms": ms, "intercepted": r.status == 200 and not portal}
    except Exception:
        return {"ok": False, "portal": False, "ms": None, "intercepted": False}


def public_info(src):
    """Public address as the internet sees it through this adapter (a plain trace page on 1.1.1.1)."""
    try:
        status, _, body, ms, tls = http_get(src, "1.1.1.1", "/cdn-cgi/trace", https=True, timeout=6)
    except Exception:
        try:
            status, _, body, ms, tls = http_get(src, "1.1.1.1", "/cdn-cgi/trace", https=False, timeout=6)
        except Exception:
            return None
    kv = dict(line.split("=", 1) for line in body.decode("ascii", "replace").splitlines() if "=" in line)
    if "ip" not in kv:
        return None
    return {"ip": kv.get("ip"), "country": kv.get("loc"), "colo": kv.get("colo"), "tls": tls or kv.get("tls"),
            "http": kv.get("http"), "ms": ms}


def v6_internet(addr):
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(3)
        try:
            s.bind((addr, 0))
            s.connect(("2606:4700:4700::1111", 443))
            return True
        finally:
            s.close()
    except OSError:
        return False


# -- DNS ----------------------------------------------------------------------------------------
def _dns_query(name, qtype=1):
    tid = random.randint(0, 0xFFFF)
    q = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.split(".")) + b"\0"
    return tid, struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0) + q + struct.pack(">HH", qtype, 1)


def _skip_name(msg, i):
    while True:
        n = msg[i]
        if n == 0:
            return i + 1
        if n & 0xC0 == 0xC0:
            return i + 2
        i += n + 1


def dns_ask(src, server, name, qtype=1, timeout=2.0):
    """Ask ``server`` directly from ``src``: (rcode, [IPv4 answers], ms) or (None, [], None)."""
    fam = socket.AF_INET6 if ":" in server else socket.AF_INET
    if fam == socket.AF_INET6:
        return None, [], None              # the probes are IPv4-bound; IPv6 resolvers are listed, not asked
    tid, pkt = _dns_query(name, qtype)
    s = socket.socket(fam, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.bind((src, 0))
        t0 = time.time()
        s.sendto(pkt, (server, 53))
        while True:
            msg, _ = s.recvfrom(2048)
            if len(msg) >= 12 and struct.unpack(">H", msg[:2])[0] == tid:
                break
        ms = int((time.time() - t0) * 1000)
    except OSError:
        return None, [], None
    finally:
        s.close()
    flags, qd, an = struct.unpack(">HHH", msg[2:8])
    i = 12
    for _ in range(qd):
        i = _skip_name(msg, i) + 4
    ips = []
    try:
        for _ in range(an):
            i = _skip_name(msg, i)
            typ, _cls, _ttl, ln = struct.unpack(">HHIH", msg[i:i + 10])
            i += 10
            if typ == 1 and ln == 4:
                ips.append(socket.inet_ntoa(msg[i:i + 4]))
            i += ln
    except (struct.error, IndexError):
        pass
    return flags & 0xF, ips, ms


def random_name():
    return "".join(random.choice(string.ascii_lowercase) for _ in range(18)) + ".com"


# -- UPnP ---------------------------------------------------------------------------------------
SSDP = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
        "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n")
WAN_SERVICES = ("urn:schemas-upnp-org:service:WANIPConnection:2", "urn:schemas-upnp-org:service:WANIPConnection:1",
                "urn:schemas-upnp-org:service:WANPPPConnection:1")


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def upnp(src, gw):
    """The router's UPnP description and its port mappings (None when UPnP does not answer)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.settimeout(2.5)
    location = server = None
    try:
        s.bind((src, 0))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(src))
        s.sendto(SSDP.encode(), ("239.255.255.250", 1900))
        s.sendto(SSDP.replace("device:InternetGatewayDevice:1", "service:WANIPConnection:1").encode(),
                 ("239.255.255.250", 1900))
        end = time.time() + 2.5
        while time.time() < end:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except socket.timeout:
                break
            hdr = {k.strip().lower(): v.strip() for k, _, v in
                   (l.partition(":") for l in data.decode("utf-8", "replace").split("\r\n")[1:]) if k}
            if hdr.get("location") and (ip == gw or location is None):
                location, server = hdr["location"], hdr.get("server")
                if ip == gw:
                    break
    except OSError:
        return None
    finally:
        s.close()
    if not location:
        return None
    res = {"location": location, "server": server, "mappings": []}
    try:
        u = urllib.parse.urlsplit(location)
        status, _, body, _, _ = http_get(src, u.hostname, u.path or "/", https=u.scheme == "https",
                                         port=u.port, timeout=4, verify=False)
        root = ET.fromstring(body)
    except Exception:
        return res
    dev = next((e for e in root.iter() if _local(e.tag) == "device"), None)
    if dev is not None:
        f = {_local(c.tag): (c.text or "").strip() for c in dev}
        res.update(friendly=f.get("friendlyName"), manufacturer=f.get("manufacturer"), model=f.get("modelName"),
                   model_number=f.get("modelNumber"), firmware=f.get("modelDescription"), serial=f.get("serialNumber"))
    control = stype = None
    for svc in root.iter():
        if _local(svc.tag) != "service":
            continue
        f = {_local(c.tag): (c.text or "").strip() for c in svc}
        if f.get("serviceType") in WAN_SERVICES:
            control, stype = urllib.parse.urljoin(location, f.get("controlURL", "")), f["serviceType"]
            break
    if not control:
        return res
    ext = _soap(src, control, stype, "GetExternalIPAddress")
    res["wan_ip"] = (ext or {}).get("NewExternalIPAddress")
    for i in range(64):
        m = _soap(src, control, stype, "GetGenericPortMappingEntry", {"NewPortMappingIndex": str(i)})
        if not m or "NewExternalPort" not in m:
            break
        res["mappings"].append({"proto": m.get("NewProtocol"), "ext_port": m.get("NewExternalPort"),
                                "client": m.get("NewInternalClient"), "int_port": m.get("NewInternalPort"),
                                "desc": m.get("NewPortMappingDescription"), "enabled": m.get("NewEnabled") in ("1", "true"),
                                "remote": m.get("NewRemoteHost") or "", "lease": m.get("NewLeaseDuration")})
    return res


def _soap(src, url, stype, action, args=None):
    body = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:%s xmlns:u="%s">%s</u:%s>'
            '</s:Body></s:Envelope>') % (action, stype, "".join("<%s>%s</%s>" % (k, v, k) for k, v in (args or {}).items()), action)
    u = urllib.parse.urlsplit(url)
    try:
        conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=3, source_address=(src, 0))
        conn.request("POST", u.path or "/", body.encode(), {"Content-Type": 'text/xml; charset="utf-8"',
                                                            "SOAPAction": '"%s#%s"' % (stype, action)})
        r = conn.getresponse()
        data = r.read(65536)
        conn.close()
        if r.status != 200:
            return None
        root = ET.fromstring(data)
    except Exception:
        return None
    out = {}
    for e in root.iter():
        if not list(e) and _local(e.tag).startswith("New"):
            out[_local(e.tag)] = (e.text or "").strip()
    return out


# -- the whole run ------------------------------------------------------------------------------
STEPS = ("gateway", "ports", "upnp", "dns", "internet", "public", "path")


def run(adapter, step=lambda name: None):
    """All probes for one adapter that is Up with an IPv4 address; ``step(name)`` is called before
    each stage (for a progress bar).  Returns the ``probe`` dict, or None when there is nothing to test."""
    cfg = adapter.get("config") or {}
    src = collect.usable_v4(cfg)
    if adapter.get("status") != "Up" or not src:
        return None
    p = {"src": src}
    gws = [g for g in cfg.get("gw4") or [] if ":" not in g]
    gw = gws[0] if gws else None

    step("gateway")
    if gw:
        g = {"ip": gw, **ping_stats(src, gw)}
        nb = {n["ip"]: n["mac"] for n in cfg.get("neighbors") or []}
        g["mac"] = nb.get(gw)
        if g["mac"]:
            p["gw_mac_shared"] = [ip for ip, mac in nb.items() if mac == g["mac"] and ip != gw]
        p["gateway"] = g
        step("ports")
        g["ports"] = port_scan(src, gw)
        g["http_title"] = router_title(src, gw, g["ports"])
        step("upnp")
        g["upnp"] = upnp(src, gw)

    step("dns")
    servers = [d for d in cfg.get("dns") or [] if ":" not in d]
    p["dns"], connect_ip = [], None
    for server in servers[:4]:
        rcode, ips, ms = dns_ask(src, server, CONNECT_HOST)
        p["dns"].append({"server": server, "ok": rcode == 0 and bool(ips), "ms": ms, "rcode": rcode})
        if rcode == 0 and ips and not connect_ip:
            connect_ip = ips[0]
    if servers and any(d["ok"] for d in p["dns"]):
        good = next(d["server"] for d in p["dns"] if d["ok"])
        rcode, ips, _ = dns_ask(src, good, random_name())
        p["nx_hijack"] = bool(rcode == 0 and ips)
    else:
        p["nx_hijack"] = None

    step("internet")
    if not gw:
        p["internet"] = {"ok": False, "portal": False, "ms": None, "intercepted": False, "no_gateway": True}
    elif connect_ip:
        p["internet"] = internet(src, connect_ip)
    else:
        p["internet"] = {"ok": False, "portal": False, "ms": None, "intercepted": False}
    globals6 = [x["addr"] for x in cfg.get("v6") or [] if x.get("origin") in ("RouterAdvertisement", "Dhcp", "Manual")
                and not (x.get("addr") or "").lower().startswith("fe80") and x.get("state") == "Preferred"]
    p["v6_internet"] = v6_internet(globals6[-1]) if globals6 and cfg.get("gw6") else None

    step("public")
    p["public"] = public_info(src) if gw else None

    step("path")
    if gw:
        with ThreadPoolExecutor(2) as ex:
            hops_f = ex.submit(trace, src)
            mtu_f = ex.submit(path_mtu, src)
            p["hops"], p["path_mtu"] = hops_f.result(), mtu_f.result()
        # Only the router's own WAN address (UPnP) proves NAT behind NAT: providers route through private
        # addresses inside their network too, so private hops further out prove nothing.
        wan = ((p["gateway"].get("upnp") or {}).get("wan_ip")) if p.get("gateway") else None
        p["wan_ip"] = wan
        p["cgnat"] = bool(wan and collect.is_cgnat(wan)) or any(
            h["ip"] and collect.is_cgnat(h["ip"]) for h in p["hops"][1:3])
        p["double_nat"] = bool(wan and collect.is_private(wan) and not collect.is_cgnat(wan))
    p["chain"] = chain(adapter, p)
    return p


def chain(adapter, p):
    """adapter -> address -> gateway -> dns -> internet, each (step, ok, detail); stops at the first break."""
    cfg = adapter.get("config") or {}
    out = [("adapter", adapter.get("status") == "Up", adapter.get("status"))]
    if not out[-1][1]:
        return out
    src = collect.usable_v4(cfg)
    v4 = [x["addr"] for x in cfg.get("v4") or []]
    if not src:
        out.append(("address", False, "apipa" if any(a.startswith("169.254.") for a in v4) else "none"))
        return out
    out.append(("address", True, src))
    g = (p or {}).get("gateway")
    if not g:
        out.append(("gateway", False, "none"))
        return out
    out.append(("gateway", g.get("loss", 100) < 100, g["ip"]))
    if not out[-1][1]:
        return out
    dns = (p or {}).get("dns") or []
    out.append(("dns", any(d["ok"] for d in dns), ", ".join(d["server"] for d in dns)))
    if not out[-1][1]:
        return out
    net = (p or {}).get("internet") or {}
    out.append(("internet", bool(net.get("ok")), "portal" if net.get("portal") else ""))
    return out
