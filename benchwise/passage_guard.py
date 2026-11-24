"""Passage's guard: keeps Passage working without Benchwise running and without asking again.

When Passage is switched on (which needs one UAC prompt anyway) a Windows Task Scheduler task is
registered that runs as SYSTEM:

* at start-up (before anyone signs in), whenever a network connects (also after sleep), and every
  15 minutes;
* on demand from Benchwise next to the clock, when its own check finds a problem.  Every signed-in
  user may start the task (and only start it), so no UAC prompt interrupts a game.

The task does not run Benchwise.exe (which sits in a folder its user can write to, so running it as
SYSTEM would hand that user administrator rights).  It runs ``repair.ps1`` from
%ProgramData%\\Benchwise\\Passage, a folder only administrators and SYSTEM can change.  The script
only enforces what an administrator switched on: Cloudflare DNS on every connected adapter (an
adapter seen for the first time has its own settings saved first, so switching Passage off puts
them back) and the packet engine's service running.  It changes nothing when all is well.

Switching Passage off removes the task and the script.  Downloading the packet engine again is
left to Benchwise (one UAC prompt); the script only reports it.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from xml.sax.saxutils import escape

TASK = "Benchwise Passage"
SCRIPT = "repair.ps1"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ASCII only: Windows PowerShell 5.1 reads a file without BOM in the ANSI code page.
_SCRIPT = r"""# Benchwise Passage repair (written by Benchwise; runs as SYSTEM from the Task Scheduler).
# Enforces what an administrator switched on in Benchwise; changes nothing when all is well.
# -Check: only tell what would be done (JSON), change nothing.
param([switch]$Check)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$statePath = Join-Path $root 'state.json'
$progressPath = Join-Path $root 'progress.json'
$utf8 = New-Object System.Text.UTF8Encoding $false
$cf4 = @(%(cf4)s)
$cf6 = @(%(cf6)s)
$doh = '%(doh)s'
$service = '%(service)s'
$others = @(%(others)s)
$engine = Join-Path $root 'zapret'
$engineFiles = @(%(files)s)
$serviceArgs = '%(args)s'

function Now { [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 }
function Save($path, $obj) {
  $tmp = $path + '.tmp'
  [IO.File]::WriteAllText($tmp, (ConvertTo-Json -InputObject $obj -Depth 6 -Compress), $utf8)
  Move-Item -LiteralPath $tmp -Destination $path -Force
}
function UsesCloudflare($v4) { foreach ($s in $cf4) { if ("$v4".Contains($s)) { return $true } }; return $false }
function Adapters {
  foreach ($a in @(Get-NetAdapter -Physical | Where-Object Status -eq 'Up')) {
    $g = "$($a.InterfaceGuid)"
    $v4 = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces\$g" -Name NameServer -ErrorAction SilentlyContinue).NameServer
    $v6 = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters\Interfaces\$g" -Name NameServer -ErrorAction SilentlyContinue).NameServer
    [pscustomobject]@{ index = [int]$a.ifIndex; guid = $g; name = "$($a.Name)"; v4 = "$v4"; v6 = "$v6" }
  }
}
function ServiceState { $s = Get-Service -Name $service -ErrorAction SilentlyContinue; if ($s) { "$($s.Status)" } else { 'Missing' } }
function WaitRunning { for ($i = 0; $i -lt 20; $i++) { if ((ServiceState) -eq 'Running') { return $true }; Start-Sleep -Milliseconds 250 }; return $false }

try { $state = [IO.File]::ReadAllText($statePath) | ConvertFrom-Json } catch { exit 0 }
if (-not $state.enabled) { exit 0 }
$dpi = ($state.layer -eq 'dpi')
$encrypted = ($state.encrypted -ne $false)

# -- DNS: Cloudflare on every connected adapter; a new adapter's own settings are saved first -------
$saved = @($state.dns_saved | Where-Object { $_ })
$savedChanged = $false
$todo = @()
foreach ($a in @(Adapters)) {
  $old = $saved | Where-Object { $_.guid -eq $a.guid } | Select-Object -First 1
  if (-not $old) { $saved += $a; $savedChanged = $true }
  elseif ([int]$old.index -ne $a.index) { $old.index = $a.index; $savedChanged = $true }
  if (-not (UsesCloudflare $a.v4)) { $todo += $a }
}
$svcBefore = ServiceState
if ($Check) {
  ConvertTo-Json -Compress -InputObject @{ dns = @($todo | ForEach-Object { $_.name }); remember = $savedChanged;
    layer = "$($state.layer)"; service = $svcBefore }
  exit 0
}

try {
if ($savedChanged) {
  $state | Add-Member -NotePropertyName dns_saved -NotePropertyValue @($saved) -Force
  Save $statePath $state
}
if ($todo.Count -gt 0) {
  foreach ($s in $cf4 + $cf6) {
    try { Add-DnsClientDohServerAddress -ServerAddress $s -DohTemplate $doh -AllowFallbackToUdp $false -AutoUpgrade $true -ErrorAction Stop | Out-Null } catch {}
  }
  foreach ($a in $todo) {
    if ($encrypted) {
      foreach ($fam in @(@{ k = 'Doh'; v = $cf4 }, @{ k = 'Doh6'; v = $cf6 })) {
        foreach ($s in $fam.v) {
          $key = "HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\InterfaceSpecificParameters\$($a.guid)\DohInterfaceSettings\$($fam.k)\$s"
          New-Item -Path $key -Force | Out-Null
          New-ItemProperty -Path $key -Name DohFlags -PropertyType QWord -Value 1 -Force | Out-Null
          New-ItemProperty -Path $key -Name DohTemplate -PropertyType String -Value $doh -Force | Out-Null
        }
      }
    }
    try {
      Set-DnsClientServerAddress -InterfaceIndex $a.index -ResetServerAddresses
      Set-DnsClientServerAddress -InterfaceIndex $a.index -ServerAddresses ($cf4 + $cf6)
    } catch {}
  }
  Clear-DnsClientCache
}

# -- packet engine: its service running ------------------------------------------------------------
$problems = @()
if ($dpi -and $svcBefore -ne 'Running') {
  $missing = @($engineFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $engine $_)) })
  $other = @($others | Where-Object { (Get-Service -Name $_ -ErrorAction SilentlyContinue).Status -eq 'Running' })
  if ($missing.Count -gt 0) { $problems += 'engine' }
  elseif ($other.Count -gt 0) { $problems += 'other' }
  elseif (-not $serviceArgs) { $problems += 'service' }
  else {
    if ($svcBefore -ne 'Missing') { try { Start-Service -Name $service -ErrorAction Stop } catch {} }
    if (-not (WaitRunning)) {
      if ((ServiceState) -ne 'Missing') {
        & sc.exe stop $service | Out-Null
        & sc.exe delete $service | Out-Null
        for ($i = 0; $i -lt 20 -and (ServiceState) -ne 'Missing'; $i++) { Start-Sleep -Milliseconds 250 }
      }
      $bin = '"' + (Join-Path $engine 'winws.exe') + '" ' + $serviceArgs
      try {
        New-Service -Name $service -BinaryPathName $bin -StartupType Automatic -DisplayName 'Benchwise Passage' `
          -Description ('Benchwise Passage: opens sites blocked in T' + [char]0xFC + 'rkiye without a VPN (zapret winws). Switch it off in Benchwise.') | Out-Null
        & sc.exe failure $service reset= 86400 actions= restart/5000/restart/10000/restart/60000 | Out-Null
        Start-Service -Name $service
      } catch {}
      if (-not (WaitRunning)) { $problems += 'service' }
    }
  }
}

foreach ($a in @(Adapters)) { if (-not (UsesCloudflare $a.v4)) { $problems += 'dns'; break } }
$fixed = ($todo.Count -gt 0) -or ($dpi -and $svcBefore -ne 'Running')
if ($fixed -or $problems.Count -gt 0) { Clear-DnsClientCache }
Save $progressPath @{ time = (Now); done = $true; ok = ($problems.Count -eq 0); problems = @($problems);
  fixed = $fixed; text = ''; by = 'guard' }
} catch {
  try { Save $progressPath @{ time = (Now); done = $true; ok = $false; problems = @('error'); fixed = $false;
    text = "$($_.Exception.Message)"; by = 'guard' } } catch {}
  exit 1
}
if ($problems.Count -gt 0) { exit 1 }
exit 0
"""


def _ps_list(items):
    return ",".join("'%s'" % str(x).replace("'", "''") for x in items)


def script_text(state):
    """The script for this state (the packet engine's arguments come from its chosen preset)."""
    from . import passage
    args = next((a for p, n, a in passage.PRESETS if p == state.get("preset")), "")
    return _SCRIPT % {
        "cf4": _ps_list(passage.CLOUDFLARE_V4), "cf6": _ps_list(passage.CLOUDFLARE_V6),
        "doh": passage.DOH_TEMPLATE, "service": passage.SERVICE, "others": _ps_list(passage.OTHER_ENGINES),
        "files": _ps_list(passage.ZAPRET_FILES), "args": args.replace("'", "''"),
    }


def script_path():
    from . import passage
    return os.path.join(passage.root(), SCRIPT)


def _schtasks(*args, timeout=30):
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW)


def ready(state):
    """Is the guard set up for this state?  Readable without administrator rights (the script is;
    the task itself may not be visible to a standard user)."""
    try:
        with open(script_path(), encoding="ascii", newline="") as f:
            return f.read() == script_text(state)
    except (OSError, ValueError):
        return False


def _task_xml():
    ps = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows",
                      r"System32\WindowsPowerShell\v1.0\powershell.exe")
    args = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%s"' % script_path()
    network = ("<QueryList><Query Id=\"0\" Path=\"Microsoft-Windows-NetworkProfile/Operational\">"
               "<Select Path=\"Microsoft-Windows-NetworkProfile/Operational\">*[System[(EventID=10000)]]</Select>"
               "</Query></QueryList>")
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>Benchwise</Author>
    <Description>Benchwise Passage: keeps Passage working after a restart and on new networks, without asking. Removed when Passage is switched off in Benchwise.</Description>
    <SecurityDescriptor>D:(A;;FA;;;SY)(A;;FA;;;BA)(A;;FRFX;;;AU)</SecurityDescriptor></RegistrationInfo>
  <Triggers>
    <BootTrigger><Enabled>true</Enabled><Delay>PT30S</Delay></BootTrigger>
    <EventTrigger><Enabled>true</Enabled><Subscription>%(network)s</Subscription><Delay>PT10S</Delay></EventTrigger>
    <TimeTrigger><Enabled>true</Enabled><StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Repetition><Interval>PT15M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition></TimeTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled><Hidden>false</Hidden><ExecutionTimeLimit>PT5M</ExecutionTimeLimit><Priority>7</Priority></Settings>
  <Actions Context="Author"><Exec><Command>%(ps)s</Command><Arguments>%(args)s</Arguments></Exec></Actions>
</Task>
""" % {"network": escape(network), "ps": escape(ps), "args": escape(args)}


def install(state):
    """Write the script and register the task (needs administrator rights; the Passage folder must
    already be locked down).  Raises RuntimeError with the reason."""
    path = script_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii", newline="") as f:
        f.write(script_text(state))
    os.replace(tmp, path)
    fd, xml_path = tempfile.mkstemp(prefix="benchwise-passage-task-", suffix=".xml")
    os.close(fd)
    try:
        with open(xml_path, "w", encoding="utf-16") as f:
            f.write(_task_xml())
        p = _schtasks("/Create", "/TN", TASK, "/XML", xml_path, "/F")
        if p.returncode != 0:
            raise RuntimeError((p.stderr or p.stdout).strip() or "schtasks failed")
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass


def remove():
    """Delete the task and the script (needs administrator rights).  Nothing there is fine."""
    _schtasks("/Delete", "/TN", TASK, "/F")
    try:
        os.remove(script_path())
    except OSError:
        pass


def run():
    """Start the repair now, without a UAC prompt.  True when the task was started."""
    try:
        return _schtasks("/Run", "/TN", TASK).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check():
    """What the script would do now, without changing anything (dict), or None.  For tests."""
    import json
    from . import passage
    folder = tempfile.mkdtemp(prefix="benchwise-passage-check-")
    path = os.path.join(folder, SCRIPT)
    try:
        with open(path, "w", encoding="ascii", newline="") as f:
            f.write(script_text(passage.load_state()))
        with open(passage._state_path(), "rb") as src, open(os.path.join(folder, "state.json"), "wb") as dst:
            dst.write(src.read())
        p = passage._run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-File", path, "-Check"], timeout=60)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        return None
    finally:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)


def user_busy():
    """A full-screen game or film, presentation mode or a locked screen: no UAC prompt now."""
    import ctypes
    st = ctypes.c_int()
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(st)) != 0:
            return False
    except Exception:
        return False
    # 1 locked / screen saver, 2 full-screen app, 3 Direct3D full screen, 4 presentation mode
    return st.value in (1, 2, 3, 4)
