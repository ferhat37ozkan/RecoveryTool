"""Passage health check and repair, with the network and services faked (nothing is changed).

    python tests\\test_passage.py
"""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from benchwise import passage, passage_guard  # noqa: E402

FAILS = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def adapter(guid, index, v4=""):
    return {"index": index, "guid": guid, "name": guid, "v4": v4, "v6": ""}


CF = "1.1.1.1,1.0.0.1"
tmp = tempfile.mkdtemp(prefix="benchwise-passage-test-")
passage.root = lambda: tmp
service = {"state": "running"}
passage.service_state = lambda name=passage.SERVICE: service["state"] if name == passage.SERVICE else None
applied = []
passage._apply_dns = lambda adapters, encrypted=True: applied.append(([a["guid"] for a in adapters], encrypted))

real_ready = passage_guard.ready
passage_guard.ready = lambda state: True     # the guard is tested on its own below

# -- problems() --------------------------------------------------------------------------------------
passage._save_state({"enabled": False})
check("off: no problems", passage.problems([adapter("A", 1)]) == [])

passage._save_state({"enabled": True, "layer": "dns", "dns_saved": [adapter("A", 1)]})
check("dns layer, all on Cloudflare", passage.problems([adapter("A", 1, CF)]) == [])
check("new adapter without Cloudflare", passage.problems([adapter("A", 1, CF), adapter("B", 2)]) == ["dns"])
service["state"] = None
check("dns layer ignores the service", passage.problems([adapter("A", 1, CF)]) == [])

passage._save_state({"enabled": True, "layer": "dpi", "preset": "tt", "dns_saved": [adapter("A", 1)]})
check("dpi layer, service missing", passage.problems([adapter("A", 1, CF)]) == ["service"])
service["state"] = "stopped"
check("dpi layer, both", passage.problems([adapter("A", 1, CF), adapter("B", 2)]) == ["service", "dns"])
service["state"] = "start_pending"
check("starting service is fine", passage.problems([adapter("A", 1, CF)]) == [])

# -- _repair_dns() -------------------------------------------------------------------------------------
state = {"enabled": True, "layer": "dns", "encrypted": False,
         "dns_saved": [adapter("A", 1, "192.168.1.1")]}
passage._save_state(state)
passage._adapters = lambda: [adapter("A", 7, CF), adapter("B", 2, "8.8.8.8")]
applied.clear()
changed = passage._repair_dns(state)
saved = {a["guid"]: a for a in passage.load_state()["dns_saved"]}
check("only the adapter without Cloudflare is changed", changed and applied == [(["B"], False)])
check("new adapter's own settings remembered for switching off", saved["B"]["v4"] == "8.8.8.8")
check("known adapter keeps its original settings", saved["A"]["v4"] == "192.168.1.1")
check("known adapter's new index remembered", saved["A"]["index"] == 7)

passage._adapters = lambda: [adapter("A", 7, CF), adapter("B", 2, CF)]
applied.clear()
check("nothing to do: nothing touched", not passage._repair_dns(passage.load_state()) and applied == [])

# -- the guard (repair task): script, check mode, task definition ---------------------------------------
import subprocess as _sp  # noqa: E402
import xml.dom.minidom as _minidom  # noqa: E402

passage_guard.ready = real_ready

state = {"enabled": True, "layer": "dpi", "preset": "tt", "encrypted": True, "dns_saved": []}
passage._save_state(state)
text = passage_guard.script_text(state)
check("script is ASCII (PowerShell 5.1 reads it without BOM)", all(ord(c) < 128 for c in text))
check("script carries the preset's engine arguments", "--dpi-desync-ttl=4" in text)
check("guard not ready before install", not passage_guard.ready(state))
with open(passage_guard.script_path(), "w", encoding="ascii", newline="") as f:
    f.write(text)
check("guard ready when the script matches", passage_guard.ready(state))
check("guard out of date when the preset changes", not passage_guard.ready(dict(state, preset="vf")))
service["state"] = "running"
check("problems() is quiet with the guard in place", passage.problems([adapter("A", 1, CF)]) == [])
os.remove(passage_guard.script_path())
check("problems() reports a missing guard", passage.problems([adapter("A", 1, CF)]) == ["guard"])
with open(passage_guard.script_path(), "w", encoding="ascii", newline="") as f:
    f.write(text)

parse = _sp.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e); "
                 "$e | ForEach-Object { $_.Message }" % passage_guard.script_path()],
                capture_output=True, text=True)
check("script parses in PowerShell" + (": " + parse.stdout.strip() if parse.stdout.strip() else ""),
      parse.returncode == 0 and not parse.stdout.strip())

result = passage_guard.check()          # real adapters and services, read only
print("     check mode said:", result)
check("check mode runs and reports", isinstance(result, dict) and "dns" in result and "service" in result)

xml = passage_guard._task_xml()
try:
    doc = _minidom.parseString(xml.replace('encoding="UTF-16"', 'encoding="UTF-8"').encode("utf-8"))
    ok = doc.getElementsByTagName("UserId")[0].firstChild.data == "S-1-5-18"
except Exception as ex:
    print("     ", ex)
    ok = False
check("task XML is well formed and runs as SYSTEM", ok)
check("task runs the script, not Benchwise.exe", "repair.ps1" in xml and "Benchwise.exe" not in xml)

print()
print("FAILED: %s" % ", ".join(FAILS) if FAILS else "all passed")
sys.exit(1 if FAILS else 0)
