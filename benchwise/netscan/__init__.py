"""Network inspection: every network adapter (Wi-Fi, Ethernet, virtual, VPN, Bluetooth...), its
configuration, live probes made *from that adapter's own address*, and a security review.

Modules
-------
``collect``   PowerShell side: ``adapters()`` lists every adapter, ``config(adapter)`` reads one adapter's
              configuration, ``wifi_details(guid)`` adds the Wi-Fi link when the adapter is wireless.
``probe``     Live tests bound to the adapter's source address (ICMP through iphlpapi, raw DNS over UDP,
              TCP connects, HTTP, SSDP/UPnP), so a VMware or VPN adapter never answers for the Wi-Fi.
``security``  ``system_posture()`` (machine-wide, read once per scan) and ``assess(adapter, posture)``
              -> list of findings.

The adapter record (a plain dict, filled in stages; any key may be missing or None)
-------------------------------------------------------------------------------------
From ``collect.adapters()``::

    index       int       interface index (ifIndex)
    name        str       "Wi-Fi", "Ethernet 2"...
    desc        str       driver description: "Intel(R) Wi-Fi 6E AX211 160MHz"
    guid        str       "{xxxxxxxx-...}" (InterfaceGuid, upper case)
    mac         str       "AA-BB-CC-DD-EE-FF"
    status      str       "Up", "Disconnected", "Disabled", "Not Present"...
    kind        str       "wifi" | "ethernet" | "virtual" | "vpn" | "bluetooth" | "cellular" | "other"
    virtual     bool      no physical hardware behind it (Hyper-V, VMware, VirtualBox, TAP, WSL...)
    speed_bps   int       link speed in bit/s (0 when down)
    media       str       PhysicalMediaType: "802.3", "Native 802.11", "Unspecified"...
    driver      dict      {"provider", "version", "date" (YYYY-MM-DD)}
    mtu         int

Added by ``collect.config(adapter)`` under ``adapter["config"]``::

    v4          [ {"addr", "prefix", "origin" ("Dhcp"|"Manual"|"WellKnown"|"Link"...), "state"
                   ("Preferred"|"Duplicate"|"Tentative"...)} ]
    v6          same for IPv6 (origin may also be "RouterAdvertisement"; "suffix_origin" "Random" = privacy)
    gw4, gw6    [str]          default gateways
    dns         [str]          DNS servers (IPv4 and IPv6)
    dns_suffix  str
    dns_register bool          the adapter registers its name in DNS
    dhcp        bool           IPv4 address from DHCP
    dhcp_server str
    lease_obtained, lease_expires   str (ISO time) or None
    netbios     int            TcpipNetbiosOptions: 0 = from DHCP, 1 = enabled, 2 = disabled
    metric      int            IPv4 interface metric
    forwarding  bool           IPv4 forwarding on this interface
    profile     {"name", "category" ("Public"|"Private"|"DomainAuthenticated"), "v4", "v6"
                 (connectivity: "Internet"|"LocalNetwork"|"NoTraffic"|"Subnet"...)} or None
    bindings    {component_id: bool}   e.g. "ms_server" (File and Printer Sharing), "ms_msclient",
                                       "ms_tcpip6", "ms_lltdio", "ms_rspndr", "ms_pacer", "ms_implat"
    stats       {"rx_bytes", "tx_bytes", "rx_unicast", "tx_unicast", "rx_errors", "tx_errors",
                 "rx_discards", "tx_discards"}
    neighbors   [ {"ip", "mac", "state"} ]   IPv4 ARP table for this interface (reachable/stale/permanent)
    advanced    {display_name: display_value}  a few driver settings (Wake on LAN, jumbo frames...)
    hw          {"bus", "slot", "pcie_link"} or None
    wifi        (only kind == "wifi" and connected) {"ssid", "bssid", "profile", "auth"
                 ("Open"|"WEP"|"WPA-Personal"|"WPA2-Personal"|"WPA3-Personal"|"WPA2-Enterprise"|...),
                 "cipher" ("None"|"WEP"|"TKIP"|"CCMP"|"GCMP"...), "phy" ("802.11ax"...), "signal" (%),
                 "rssi" (dBm), "channel", "band", "rx_mbps", "tx_mbps", "onex" (bool)}

Added by the probes under ``adapter["probe"]`` (only for an adapter that is Up with an IPv4 address)::

    src         str     the IPv4 address the probes were sent from
    gateway     {"ip", "mac", "loss" (%), "min", "avg", "max", "jitter" (ms), "ports": {port: bool},
                 "http_title" str, "upnp": {...} or None}
                 upnp = {"location", "server", "friendly", "manufacturer", "model", "model_number",
                         "firmware" (modelDescription / version text), "serial", "wan_ip",
                         "mappings": [ {"proto", "ext_port", "client", "int_port", "desc", "enabled",
                                        "remote", "lease"} ]}
    gw_mac_shared [str]  other neighbour IPs answering with the gateway's MAC (ARP spoofing sign)
    dns         [ {"server", "ok", "ms", "rcode"} ]
    nx_hijack   bool or None   a made-up name got an answer (the resolver rewrites NXDOMAIN)
    internet    {"ok", "portal", "ms", "intercepted"}  HTTP connect-test through this adapter
    v6_internet bool or None
    public      {"ip", "country", "colo", "tls", "http"} or None   (Cloudflare /cdn-cgi/trace)
    hops        [ {"ttl", "ip", "ms"} ]  first hops towards 1.1.1.1
    cgnat       bool    a 100.64.0.0/10 hop or WAN address (carrier-grade NAT)
    double_nat  bool    more than one private hop before the internet
    path_mtu    int     largest IPv4 packet that passes without fragmenting
    chain       [ (step, ok, detail) ]  adapter -> address -> gateway -> dns -> internet

A finding (from ``security.assess``)::

    {"level": "bad" | "warning" | "info" | "good", "key": str (stable id), "title": str,
     "detail": str, "fix": str or ""}

Texts are bilingual (English, Turkish) through ``toolkit.texts``; "Türkiye" in English; never name a
third-party product or brand in a text the user reads.
"""
