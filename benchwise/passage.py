"""Passage (Geçit): opens sites and apps that are blocked in Turkey, without a VPN.

Blocks in Turkey come in two layers, and Passage answers them one at a time, stopping at the first
that is enough (so most PCs never get a driver):

1. **DNS.**  The ISP's DNS answers a blocked name with the address of its warning page.  Passage
   points the active network adapters at Cloudflare DNS (1.1.1.1) and turns on Windows' own
   encrypted DNS (DNS over HTTPS) for them, so the ISP can neither read nor replace the answers.
   The previous settings are saved and put back exactly when Passage is switched off.
2. **DPI.**  Where the ISP also reads the site name in the first packet of a connection (SNI), Passage
   runs zapret's ``winws`` as a Windows service (``BenchwisePassage``).  winws reshapes only the
   packets of the listed sites (fake packets, split packets) so the ISP's filter cannot match them,
   and handles voice chat (UDP) too.  Presets for Turkish ISPs are tried in turn and the first
   one that gets through is kept.  zapret is downloaded once from its official GitHub release
   (SHA-256 checked) into %ProgramData%\\Benchwise\\Passage, readable but not writable for
   standard users, since the service runs as SYSTEM.

Both layers survive a restart on their own (adapter settings and an automatic service).  Changing
them needs administrator rights; reading the state does not.  This module has no window code, so
the command line (``Benchwise-cli --hideme``) uses it as well.

Approach from GoodbyeDPI (ValdikSS), GoodbyeDPI-Turkey and SplitWire-Turkey (cagritaskn), and
zapret (bol-van); see THIRD_PARTY in the README.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

from recoverytool import i18n
from recoverytool.i18n import t

SERVICE = "BenchwisePassage"
RUN_VALUE = "Benchwise Passage"            # HKCU\...\Run: Benchwise next to the clock at sign-in
DOMAINS = ["discord.com", "discord.gg", "discordapp.com", "discordapp.net", "discord.media", "discordcdn.com",
           "discord.co", "discord.dev", "discord.new", "discord.gift", "discordstatus.com", "dis.gd"]
PROBE_HOST = "discord.com"
CONTROL_HOST = "www.microsoft.com"         # must always work: tells "blocked" from "offline"
CLOUDFLARE_V4 = ["1.1.1.1", "1.0.0.1"]
CLOUDFLARE_V6 = ["2606:4700:4700::1111", "2606:4700:4700::1001"]
DOH_TEMPLATE = "https://cloudflare-dns.com/dns-query"

ZAPRET_VERSION = "v72.13"
ZAPRET_URL = "https://github.com/bol-van/zapret/releases/download/%s/zapret-%s.zip" % (ZAPRET_VERSION, ZAPRET_VERSION)
ZAPRET_SHA256 = "c493e33a0dc4eba23a8686efdaba55f59755ad6ade3564aebd9d13f4c65e2e0c"
ZAPRET_FILES = ["winws.exe", "cygwin1.dll", "WinDivert.dll", "WinDivert64.sys"]
OTHER_ENGINES = ["GoodbyeDPI", "zapret", "zapret2", "winws1", "winws2", "byedpi"]   # one packet engine at a time

_HOSTS = ",".join(DOMAINS)
_COMMON_HEAD = "--wf-tcp=80,443 --wf-udp=443,50000-50100"
_VOICE = ("--new --filter-udp=443 --hostlist-domains=%s --dpi-desync=fake --dpi-desync-repeats=6 "
          "--new --filter-udp=50000-50100 --filter-l7=discord,stun --dpi-desync=fake --dpi-desync-repeats=6" % _HOSTS)
# (id, name shown, winws arguments): tried in this order, the first that gets through is kept.
PRESETS = [
    ("tt", "Türk Telekom / TurkNet",
     "%s --filter-tcp=80,443 --hostlist-domains=%s --dpi-desync=fake,multisplit --dpi-desync-split-pos=1,midsld "
     "--dpi-desync-ttl=4 %s" % (_COMMON_HEAD, _HOSTS, _VOICE)),
    ("so", "Superonline",
     "%s --filter-tcp=80,443 --hostlist-domains=%s --dpi-desync=fake,multisplit --dpi-desync-split-pos=1,midsld "
     "--dpi-desync-fooling=md5sig %s" % (_COMMON_HEAD, _HOSTS, _VOICE)),
    ("vf", "Vodafone",
     "%s --filter-tcp=80,443 --hostlist-domains=%s --dpi-desync=multisplit --dpi-desync-split-pos=2 %s"
     % (_COMMON_HEAD, _HOSTS, _VOICE)),
    ("tt3", "Türk Telekom (TTL 3)",
     "%s --filter-tcp=80,443 --hostlist-domains=%s --dpi-desync=fake --dpi-desync-ttl=3 %s"
     % (_COMMON_HEAD, _HOSTS, _VOICE)),
    ("so3", "Superonline (TTL 3)",
     "%s --filter-tcp=80,443 --hostlist-domains=%s --dpi-desync=fake --dpi-desync-fooling=md5sig "
     "--dpi-desync-ttl=3 %s" % (_COMMON_HEAD, _HOSTS, _VOICE)),
]

i18n.STRINGS.update({
    "ps_name": ("Passage", "Geçit"),
    "ps_on": ("On", "Açık"),
    "ps_off": ("Off", "Kapalı"),
    "ps_busy": ("Working…", "Çalışıyor…"),
    "ps_need_admin": ("Passage needs administrator rights to change network settings.",
                      "Geçit, ağ ayarlarını değiştirmek için yönetici yetkisi ister."),
    "ps_step_check": ("Checking the connection…", "Bağlantı kontrol ediliyor…"),
    "ps_step_dns": ("Turning on encrypted DNS (Cloudflare)…", "Şifreli DNS açılıyor (Cloudflare)…"),
    "ps_step_download": ("Downloading the packet engine (zapret, once)…",
                         "Paket motoru indiriliyor (zapret, bir kez)…"),
    "ps_step_preset": ("Trying the {name} setting…", "{name} ayarı deneniyor…"),
    "ps_step_off": ("Putting the previous settings back…", "Önceki ayarlar geri yükleniyor…"),
    "ps_done_dns": ("Passage is on: encrypted DNS was enough, blocked sites open.",
                    "Geçit açık: şifreli DNS yetti, engellenen siteler açılıyor."),
    "ps_done_plain": ("Passage is on: Cloudflare DNS was enough, blocked sites open (this network refuses "
                      "encrypted DNS).", "Geçit açık: Cloudflare DNS yetti, engellenen siteler açılıyor (bu ağ "
                      "şifreli DNS'e izin vermiyor)."),
    "ps_done_dpi": ("Passage is on with the {name} setting: blocked sites open.",
                    "Geçit {name} ayarıyla açık: engellenen siteler açılıyor."),
    "ps_done_off": ("Passage is off; the previous network settings are back.",
                    "Geçit kapalı; önceki ağ ayarları geri yüklendi."),
    "ps_fail_offline": ("There is no internet connection, so Passage was not switched on.",
                        "İnternet bağlantısı yok; Geçit açılmadı."),
    "ps_fail_all": ("No setting got through the block on this connection. Everything was put back.",
                    "Bu bağlantıda hiçbir ayar engeli aşamadı. Her şey geri alındı."),
    "ps_fail_other": ("Another bypass tool is running ({name}). Switch it off first.",
                      "Başka bir engel aşma aracı çalışıyor ({name}). Önce onu kapatın."),
    "ps_fail_error": ("Passage could not be switched: {err}", "Geçit değiştirilemedi: {err}"),
    "ps_tray": ("Passage: {state}", "Geçit: {state}"),
    "ps_show_tray": ("Show the Passage icon next to the clock", "Geçit simgesini saatin yanında göster"),
    "ps_tray_hint": ("Right-click to switch", "Açıp kapatmak için sağ tıklayın"),
    "ps_now": ("Now: {state}", "Şu an: {state}"),
    "ps_info": ("Passage opens sites and apps blocked in Turkey, without a VPN and without slowing "
                "anything else down.\n\n"
                "1. It turns on encrypted DNS (Cloudflare), so your provider cannot redirect the site to its "
                "warning page.\n"
                "2. Only if that is not enough, it starts a small packet engine (zapret) that changes the shape of "
                "the packets going to those sites, so the provider's filter cannot recognise them; voice chat "
                "is covered too.\n\n"
                "It stays on after a restart. Switching it off puts your previous network settings back exactly.",
                "Geçit, Türkiye'de engellenen site ve uygulamaları VPN olmadan, başka hiçbir şeyi "
                "yavaşlatmadan açar.\n\n"
                "1. Şifreli DNS'i (Cloudflare) açar; böylece servis sağlayıcınız siteyi uyarı sayfasına "
                "yönlendiremez.\n"
                "2. Bu yetmezse küçük bir paket motorunu (zapret) başlatır: o sitelere giden paketlerin şeklini "
                "değiştirir, sağlayıcının filtresi onları tanıyamaz. Sesli sohbet de dahildir.\n\n"
                "Bilgisayar yeniden başlasa da açık kalır. Kapattığınızda önceki ağ ayarlarınız aynen geri gelir."),
    "ps_state_dns": ("Encrypted DNS", "Şifreli DNS"),
    "ps_state_plain": ("Cloudflare DNS (not encrypted)", "Cloudflare DNS (şifresiz)"),
    "ps_state_dpi": ("Encrypted DNS + packet engine ({name})", "Şifreli DNS + paket motoru ({name})"),
})


# -- where things live --------------------------------------------------------------------------
def root():
    return os.path.join(os.environ.get("ProgramData") or r"C:\ProgramData", "Benchwise", "Passage")


def _state_path():
    return os.path.join(root(), "state.json")


def _progress_path():
    return os.path.join(root(), "progress.json")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(args, timeout=60):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _ps(script, timeout=90):
    p = _run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
             timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip().splitlines()[-1] if (p.stderr or p.stdout).strip()
                           else "powershell %d" % p.returncode)
    return p.stdout


def load_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state):
    os.makedirs(root(), exist_ok=True)
    tmp = _state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, _state_path())


def _progress(report, key, **kw):
    """Tell the caller (and a window waiting on another process) what is happening."""
    text = t(key, **kw)
    try:
        os.makedirs(root(), exist_ok=True)
        with open(_progress_path(), "w", encoding="utf-8") as f:
            json.dump({"time": time.time(), "text": text, "done": False}, f)
    except OSError:
        pass
    if report:
        report(text)


def _finish(ok, message):
    try:                                # also in the state: readable even if the progress file is not
        st = load_state()
        st.update(finished=time.time(), last_ok=ok, last_message=message)
        _save_state(st)
    except OSError:
        pass
    try:
        with open(_progress_path(), "w", encoding="utf-8") as f:
            json.dump({"time": time.time(), "text": message, "done": True, "ok": ok}, f)
    except OSError:
        pass
    return ok, message


def read_progress():
    try:
        with open(_progress_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _harden_root():
    """SYSTEM and administrators may change the folder, everyone else only read: the service runs
    winws.exe from here as SYSTEM, so nobody else may swap it."""
    os.makedirs(root(), exist_ok=True)
    base = os.path.dirname(root())
    # the folder itself gets the rules; everything inside inherits them (a file cannot take the
    # (OI)(CI) inheritance flags, so the rules are not applied to files one by one)
    _run(["icacls", base, "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F",
          "*S-1-5-32-545:(OI)(CI)RX", "/C", "/Q"])
    _run(["icacls", os.path.join(base, "*"), "/reset", "/T", "/C", "/Q"])


# -- checks ---------------------------------------------------------------------------------------
def probe(host=PROBE_HOST, timeout=6):
    """Can a normal program reach ``host`` over HTTPS right now (system DNS, certificate checked)?"""
    try:
        addr = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        with socket.create_connection((addr, 443), timeout) as s:
            with ssl.create_default_context().wrap_socket(s, server_hostname=host) as tls:
                tls.do_handshake()
        return True
    except Exception:
        return False


def _probe_twice():
    """Right after a change the first attempt can still hit an old connection: give it a second go."""
    time.sleep(1.5)
    if probe():
        return True
    time.sleep(2.0)
    return probe()


def _wait_online(seconds):
    deadline = time.time() + seconds
    while True:
        if online():
            return True
        if time.time() >= deadline:
            return False
        time.sleep(1.0)


def online():
    return probe(CONTROL_HOST) or probe("www.cloudflare.com")


def _flush_dns():
    _run(["ipconfig", "/flushdns"], timeout=20)


def service_state(name=SERVICE):
    """"running", "stopped", ... or None when the service does not exist."""
    p = _run(["sc", "query", name], timeout=15)
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        if "STATE" in line:
            return line.split()[-1].lower()
    return "unknown"


def other_engine():
    for name in OTHER_ENGINES:
        if service_state(name) == "running":
            return name
    return None


def is_on():
    return bool(load_state().get("enabled"))


def summary():
    """One line for the window and the command line."""
    st = load_state()
    if not st.get("enabled"):
        return t("ps_off")
    if st.get("layer") == "dpi":
        return t("ps_state_dpi", name=st.get("preset_name", "?"))
    return t("ps_state_dns" if st.get("encrypted", True) else "ps_state_plain")


# -- layer 1: DNS -----------------------------------------------------------------------------------
_ADAPTERS_PS = r"""
$out = @()
foreach ($a in Get-NetAdapter -Physical | Where-Object Status -eq 'Up') {
  $g = $a.InterfaceGuid
  $v4 = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$g" -Name NameServer -ErrorAction SilentlyContinue).NameServer
  $v6 = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters\Interfaces\$g" -Name NameServer -ErrorAction SilentlyContinue).NameServer
  $out += [pscustomobject]@{ index = $a.ifIndex; guid = "$g"; name = $a.Name; v4 = "$v4"; v6 = "$v6" }
}
ConvertTo-Json -InputObject @($out) -Compress
"""


def _adapters():
    return json.loads(_ps(_ADAPTERS_PS).strip() or "[]")


def _doh_key(guid, family):
    return (r"HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\InterfaceSpecificParameters\%s\DohInterfaceSettings\%s"
            % (guid, "Doh" if family == 4 else "Doh6"))


def _apply_dns(adapters, encrypted=True):
    servers = ",".join("'%s'" % s for s in CLOUDFLARE_V4 + CLOUDFLARE_V6)
    lines = []
    for s in CLOUDFLARE_V4 + CLOUDFLARE_V6:            # Windows knows Cloudflare; make sure the template is there
        lines.append("try { Add-DnsClientDohServerAddress -ServerAddress '%s' -DohTemplate '%s' "
                     "-AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop | Out-Null } catch {}"
                     % (s, DOH_TEMPLATE))
    for a in adapters:
        # the DoH settings first: the DNS client reads them when the adapter's servers change, so the
        # servers are set afterwards (reset first, so the change is seen even when they were the same)
        for fam, lst in ((4, CLOUDFLARE_V4), (6, CLOUDFLARE_V6)):
            for s in lst:
                key = _doh_key(a["guid"], fam) + "\\" + s
                if encrypted:
                    lines.append("New-Item -Path '%s' -Force | Out-Null" % key)
                    lines.append("New-ItemProperty -Path '%s' -Name DohFlags -PropertyType QWord -Value 1 -Force | Out-Null"
                                 % key)
                    lines.append("New-ItemProperty -Path '%s' -Name DohTemplate -PropertyType String -Value '%s' -Force "
                                 "| Out-Null" % (key, DOH_TEMPLATE))
                else:
                    lines.append("Remove-Item -Path '%s' -Recurse -Force -ErrorAction SilentlyContinue" % key)
        lines.append("Set-DnsClientServerAddress -InterfaceIndex %d -ResetServerAddresses" % a["index"])
        lines.append("Set-DnsClientServerAddress -InterfaceIndex %d -ServerAddresses @(%s)" % (a["index"], servers))
    lines.append("Clear-DnsClientCache")
    _ps("\n".join(lines))


def _restore_dns(saved):
    lines = []
    for a in saved:
        for fam, lst in ((4, CLOUDFLARE_V4), (6, CLOUDFLARE_V6)):
            for s in lst:
                lines.append("Remove-Item -Path '%s\\%s' -Recurse -Force -ErrorAction SilentlyContinue"
                             % (_doh_key(a["guid"], fam), s))
        v4 = [x for x in a.get("v4", "").replace(" ", ",").split(",") if x]
        v6 = [x for x in a.get("v6", "").replace(" ", ",").split(",") if x]
        if v4 or v6:
            lines.append("Set-DnsClientServerAddress -InterfaceIndex %d -ServerAddresses @(%s) -ErrorAction SilentlyContinue"
                         % (a["index"], ",".join("'%s'" % x for x in v4 + v6)))
        else:                                           # it came from the router (DHCP)
            lines.append("Set-DnsClientServerAddress -InterfaceIndex %d -ResetServerAddresses -ErrorAction SilentlyContinue"
                         % a["index"])
    lines.append("Clear-DnsClientCache")
    _ps("\n".join(lines))


# -- layer 2: packet engine (zapret winws as a service) ----------------------------------------------
def engine_dir():
    return os.path.join(root(), "zapret")


def engine_ready():
    return all(os.path.isfile(os.path.join(engine_dir(), n)) for n in ZAPRET_FILES)


def _download_engine():
    fd, tmp = tempfile.mkstemp(prefix="benchwise-zapret-", suffix=".zip")
    os.close(fd)
    try:
        req = urllib.request.Request(ZAPRET_URL, headers={"User-Agent": "Benchwise"})
        h = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                h.update(chunk)
                f.write(chunk)
        if h.hexdigest() != ZAPRET_SHA256:
            raise RuntimeError("zapret download: SHA-256 mismatch")
        os.makedirs(engine_dir(), exist_ok=True)
        prefix = "zapret-%s/" % ZAPRET_VERSION
        with zipfile.ZipFile(tmp) as z:
            wanted = {prefix + "binaries/windows-x86_64/" + n: n for n in ZAPRET_FILES}
            wanted[prefix + "docs/LICENSE.txt"] = "LICENSE-zapret.txt"
            for member, name in wanted.items():
                with z.open(member) as src, open(os.path.join(engine_dir(), name), "wb") as dst:
                    dst.write(src.read())
        with open(os.path.join(engine_dir(), "SOURCE.txt"), "w", encoding="utf-8") as f:
            f.write("zapret %s by bol-van - https://github.com/bol-van/zapret (MIT)\n"
                    "WinDivert by basil00 - https://github.com/basil00/WinDivert (LGPL-3.0)\n"
                    "cygwin1.dll - https://cygwin.com (LGPL-3.0)\n"
                    "Downloaded unchanged by Benchwise from %s\nSHA-256 of the archive: %s\n"
                    % (ZAPRET_VERSION, ZAPRET_URL, ZAPRET_SHA256))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def _remove_service():
    if service_state() is not None:
        _run(["sc", "stop", SERVICE], timeout=30)
        for _ in range(20):
            if service_state() in (None, "stopped"):
                break
            time.sleep(0.25)
        _run(["sc", "delete", SERVICE], timeout=30)
    # the WinDivert driver stays loaded until nobody uses it; stop it so the files can be replaced
    if service_state("WinDivert") is not None and not any(service_state(n) == "running" for n in OTHER_ENGINES):
        _run(["sc", "stop", "WinDivert"], timeout=30)


def _install_service(args):
    _remove_service()
    exe = os.path.join(engine_dir(), "winws.exe")
    bin_path = '"%s" %s' % (exe, args)
    p = _run(["sc", "create", SERVICE, "binPath=", bin_path, "start=", "auto", "DisplayName=", "Benchwise Passage"])
    if p.returncode != 0:
        raise RuntimeError((p.stdout or p.stderr).strip() or "sc create failed")
    _run(["sc", "description", SERVICE, "Benchwise Passage: opens sites blocked in Turkey "
          "without a VPN (zapret winws). Switch it off in Benchwise."])
    _run(["sc", "failure", SERVICE, "reset=", "86400", "actions=", "restart/5000/restart/10000/restart/60000"])
    p = _run(["sc", "start", SERVICE])
    for _ in range(20):
        if service_state() == "running":
            return
        time.sleep(0.25)
    raise RuntimeError((p.stdout or p.stderr).strip().splitlines()[-1] if (p.stdout or p.stderr).strip()
                       else "service did not start")


# -- start with Windows, next to the clock ----------------------------------------------------------
def exe_for_tray():
    return os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else None


def set_tray_autostart(on, exe=None):
    """HKCU Run entry that starts Benchwise hidden, next to the clock (no administrator rights needed)."""
    import winreg
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
        if on and exe:
            value = '"%s" --tray' % exe
            try:
                if winreg.QueryValueEx(k, RUN_VALUE)[0] == value:
                    return
            except OSError:
                pass
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, value)
        elif not on:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except OSError:
                pass


# -- switching --------------------------------------------------------------------------------------
def enable(report=None):
    """Switch Passage on.  Returns ``(ok, message)``.  Needs administrator rights."""
    if not is_admin():
        return _finish(False, t("ps_need_admin"))
    state = load_state()
    try:
        _progress(report, "ps_step_check")
        other = other_engine()
        if other:
            return _finish(False, t("ps_fail_other", name=other))
        _harden_root()
        if not state.get("enabled"):
            _flush_dns()
            if not online():
                return _finish(False, t("ps_fail_offline"))
            state = {"enabled": False, "dns_saved": _adapters()}
            _save_state(state)
        # layer 1: encrypted DNS
        _progress(report, "ps_step_dns")
        _apply_dns(state["dns_saved"], encrypted=True)
        encrypted = _wait_online(10)                    # Windows needs a moment for its first DoH connection
        if not encrypted:                               # encrypted DNS refused on this network: plain Cloudflare
            _apply_dns(state["dns_saved"], encrypted=False)
            _wait_online(6)
        state.update(enabled=True, layer="dns", encrypted=encrypted, since=time.time())
        _save_state(state)
        if _probe_twice():
            _remove_service()
            state.pop("preset", None)
            state.pop("preset_name", None)
            _save_state(state)
            return _finish(True, t("ps_done_dns" if encrypted else "ps_done_plain"))
        # layer 2: packet engine, presets in turn
        if not engine_ready():
            _progress(report, "ps_step_download")
            _download_engine()
            _harden_root()
        order = sorted(PRESETS, key=lambda p: p[0] != state.get("preset"))    # last good one first
        for pid, name, args in order:
            _progress(report, "ps_step_preset", name=name)
            _install_service(args)
            if _probe_twice():
                state.update(layer="dpi", preset=pid, preset_name=name)
                _save_state(state)
                return _finish(True, t("ps_done_dpi", name=name))
        _remove_service()
        disable(report=None, quiet=True)
        return _finish(False, t("ps_fail_all"))
    except Exception as ex:
        try:
            disable(report=None, quiet=True)
        except Exception:
            pass
        return _finish(False, t("ps_fail_error", err=ex))


def disable(report=None, quiet=False):
    """Switch Passage off and put every setting back.  Returns ``(ok, message)``."""
    if not is_admin():
        return _finish(False, t("ps_need_admin"))
    try:
        if not quiet:
            _progress(report, "ps_step_off")
        _remove_service()
        state = load_state()
        if state.get("dns_saved"):
            _restore_dns(state["dns_saved"])
        _save_state({"enabled": False, "preset": state.get("preset")})    # _finish adds "finished"
        _flush_dns()
        return (True, t("ps_done_off")) if quiet else _finish(True, t("ps_done_off"))
    except Exception as ex:
        return (False, str(ex)) if quiet else _finish(False, t("ps_fail_error", err=ex))


def ensure_running():
    """At start (elevated): an enabled DPI layer whose service was removed from outside comes back."""
    st = load_state()
    if st.get("enabled") and st.get("layer") == "dpi" and service_state() is None and is_admin() and engine_ready():
        args = next((a for p, n, a in PRESETS if p == st.get("preset")), None)
        if args:
            _install_service(args)
