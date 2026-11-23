"""Network > security review: what the machine exposes and how the network it is on is protected.

``system_posture()`` reads the machine-wide settings once per scan (one PowerShell call, works without
administrator rights; whatever cannot be read is left out).  ``assess(adapter, posture)`` turns one
adapter record (see ``benchwise.netscan``) plus that posture into findings.  It does no I/O, so it can
be tested with made-up adapters.

The tone is that of a careful security officer: a NAT'd home network with a web admin page on the
router is normal; an open Wi-Fi with file sharing on is not.
"""

from __future__ import annotations

import base64
import datetime
import ipaddress
import struct

from recoverytool.i18n import t

from ..toolkit import as_list, powershell_json, texts

LEVEL_ORDER = {"bad": 0, "warning": 1, "info": 2, "good": 3}

texts({
    # -- Wi-Fi ---------------------------------------------------------------------------------------
    "sec_wifi_open": ("Open Wi-Fi: no encryption", "Açık Wi-Fi: şifreleme yok"),
    "sec_wifi_open_d": ("Everything sent over \"{ssid}\" that is not encrypted by the site itself can be read by "
                        "anyone nearby, and anyone can join the network.", "\"{ssid}\" üzerinden giden ve sitenin "
                        "kendisinin şifrelemediği her şey yakındaki herkes tarafından okunabilir; ağa herkes katılabilir."),
    "sec_wifi_open_f": ("Use a password-protected network, or a VPN while you are on this one.",
                        "Şifreli bir ağ kullanın veya bu ağdayken VPN açın."),
    "sec_wifi_wep": ("WEP encryption: broken", "WEP şifreleme: kırılmış"),
    "sec_wifi_wep_d": ("WEP can be cracked in minutes; \"{ssid}\" is effectively open.",
                       "WEP dakikalar içinde kırılabilir; \"{ssid}\" fiilen açık bir ağdır."),
    "sec_wifi_wep_f": ("Switch the router to WPA2 or WPA3 (AES) and set a new password.",
                       "Modemi WPA2 veya WPA3 (AES) olarak ayarlayın ve yeni bir şifre belirleyin."),
    "sec_wifi_wpa1": ("Outdated WPA / TKIP encryption", "Eski WPA / TKIP şifreleme"),
    "sec_wifi_wpa1_d": ("\"{ssid}\" uses {auth} with {cipher}. TKIP has known weaknesses and also limits speed.",
                        "\"{ssid}\" {auth} ve {cipher} kullanıyor. TKIP'in bilinen zayıflıkları var ve hızı da "
                        "düşürür."),
    "sec_wifi_wpa1_f": ("In the router's Wi-Fi settings choose WPA2-AES or WPA3.",
                        "Modemin Wi-Fi ayarlarında WPA2-AES veya WPA3 seçin."),
    "sec_wifi_wpa2": ("WPA2 encryption", "WPA2 şifreleme"),
    "sec_wifi_wpa2_d": ("\"{ssid}\" is protected with {auth} / {cipher}. Safe with a long password; WPA3 is "
                        "better if every device supports it.", "\"{ssid}\" {auth} / {cipher} ile korunuyor. Uzun "
                        "bir şifreyle güvenlidir; tüm cihazlar destekliyorsa WPA3 daha iyidir."),
    "sec_wifi_wpa3": ("WPA3 encryption", "WPA3 şifreleme"),
    "sec_wifi_wpa3_d": ("\"{ssid}\" uses {auth} / {cipher}, the current standard: the password cannot be "
                        "guessed offline.", "\"{ssid}\" güncel standart olan {auth} / {cipher} kullanıyor: şifre "
                        "çevrim dışı tahmin edilemez."),
    "sec_wifi_enterprise": ("Enterprise Wi-Fi login", "Kurumsal Wi-Fi girişi"),
    "sec_wifi_enterprise_d": ("\"{ssid}\" uses {auth}: each user signs in with their own account.",
                              "\"{ssid}\" {auth} kullanıyor: her kullanıcı kendi hesabıyla giriş yapar."),
    "sec_wifi_weak": ("Weak Wi-Fi signal", "Zayıf Wi-Fi sinyali"),
    "sec_wifi_weak_d": ("Signal {signal}% ({rssi} dBm). Expect drops and low speed.",
                        "Sinyal %{signal} ({rssi} dBm). Kopmalar ve düşük hız beklenir."),
    "sec_wifi_weak_f": ("Move closer to the router or add an access point / mesh unit.",
                        "Modeme yaklaşın veya bir erişim noktası / mesh cihazı ekleyin."),
    "sec_wifi_auto_open": ("Joins open networks automatically", "Açık ağlara kendiliğinden bağlanıyor"),
    "sec_wifi_auto_open_d": ("Saved open networks set to connect automatically: {names}. Anyone can create a "
                             "network with the same name and this computer will join it.",
                             "Otomatik bağlanacak şekilde kaydedilmiş açık ağlar: {names}. Herkes aynı adla bir ağ "
                             "kurabilir ve bu bilgisayar ona bağlanır."),
    "sec_wifi_auto_open_f": ("In Wi-Fi settings, Manage known networks, forget them or turn off \"Connect "
                             "automatically\".", "Wi-Fi ayarlarında Bilinen ağları yönet'ten bunları unutun veya "
                             "\"Otomatik bağlan\"ı kapatın."),
    # -- network category, firewall, sharing --------------------------------------------------------
    "sec_private_untrusted": ("Unprotected network marked as private", "Korumasız ağ özel olarak işaretli"),
    "sec_private_untrusted_d": ("\"{name}\" has no proper encryption but Windows treats it as a trusted private "
                                "network: this computer is visible and shares are reachable to others on it.",
                                "\"{name}\" düzgün şifrelenmemiş ama Windows onu güvenilir özel ağ sayıyor: bu "
                                "bilgisayar görünür ve paylaşımlara ağdaki diğerleri erişebilir."),
    "sec_private_untrusted_f": ("Settings > Network > this network > set the profile to Public.",
                                "Ayarlar > Ağ > bu ağ > profili Ortak olarak ayarlayın."),
    "sec_public_sharing": ("File sharing is open on a public network", "Ortak ağda dosya paylaşımı açık"),
    "sec_public_sharing_d": ("The firewall lets file and printer sharing in on public networks, and \"{name}\" "
                             "is public. Others on this network can try to reach shared folders.",
                             "Güvenlik duvarı ortak ağlarda dosya ve yazıcı paylaşımına izin veriyor ve \"{name}\" "
                             "ortak ağ. Bu ağdaki başkaları paylaşılan klasörlere erişmeyi deneyebilir."),
    "sec_public_sharing_f": ("Turn off file and printer sharing for public networks in Advanced sharing settings.",
                             "Gelişmiş paylaşım ayarlarında ortak ağlar için dosya ve yazıcı paylaşımını kapatın."),
    "sec_public_profile": ("Public network profile", "Ortak ağ profili"),
    "sec_public_profile_d": ("\"{name}\" is marked public: this computer is hidden from other devices on it.",
                             "\"{name}\" ortak olarak işaretli: bu bilgisayar ağdaki diğer cihazlardan gizli."),
    "sec_private_visible": ("Visible on this network", "Bu ağda görünür"),
    "sec_private_visible_d": ("\"{name}\" is a private network with {what} on: other devices here can see this "
                              "computer. Fine at home or at work, not on a shared network.",
                              "\"{name}\" özel ağ ve {what} açık: buradaki diğer cihazlar bu bilgisayarı görebilir. "
                              "Evde veya işte sorun değil, ortak kullanılan bir ağda olmamalı."),
    "sec_what_sharing": ("file sharing", "dosya paylaşımı"),
    "sec_what_discovery": ("network discovery", "ağ bulma"),
    "sec_what_and": (" and ", " ve "),
    "sec_firewall_off": ("Firewall is off", "Güvenlik duvarı kapalı"),
    "sec_firewall_off_d": ("The firewall is turned off for {profile} networks, which this adapter is on. Every "
                           "listening program is reachable from the network.", "Güvenlik duvarı bu kartın bağlı "
                           "olduğu {profile} ağlar için kapalı. Dinleyen her programa ağdan ulaşılabilir."),
    "sec_firewall_off_f": ("Turn the firewall on in Windows Security > Firewall & network protection.",
                           "Windows Güvenliği > Güvenlik duvarı ve ağ koruması'ndan güvenlik duvarını açın."),
    "sec_firewall_allow": ("Firewall lets everything in", "Güvenlik duvarı gelen her şeye izin veriyor"),
    "sec_firewall_allow_d": ("For {profile} networks the firewall's default for incoming connections is Allow.",
                             "{profile} ağlar için güvenlik duvarının gelen bağlantılardaki varsayılanı İzin Ver."),
    "sec_firewall_allow_f": ("Set inbound connections back to Block in the firewall's advanced settings.",
                             "Güvenlik duvarının gelişmiş ayarlarında gelen bağlantıları yeniden Engelle yapın."),
    "sec_firewall_on": ("Firewall is on", "Güvenlik duvarı açık"),
    "sec_firewall_on_d": ("The firewall protects {profile} networks and blocks unsolicited incoming connections.",
                          "Güvenlik duvarı {profile} ağları koruyor ve istenmeyen gelen bağlantıları engelliyor."),
    "sec_profile_Domain": ("domain", "etki alanı"),
    "sec_profile_Private": ("private", "özel"),
    "sec_profile_Public": ("public", "ortak"),
    # -- exposure ------------------------------------------------------------------------------------
    "sec_public_ip": ("Directly on the internet (no NAT)", "Doğrudan internette (NAT yok)"),
    "sec_public_ip_d": ("This adapter holds the public address {ip}: there is no router in between, so the whole "
                        "internet can reach this computer; only the firewall protects it.",
                        "Bu kart {ip} genel adresini taşıyor: arada modem yok, tüm internet bu bilgisayara "
                        "ulaşabilir; onu yalnızca güvenlik duvarı korur."),
    "sec_public_ip_f": ("Put the computer behind a router, or keep the firewall on and close services you do not use.",
                        "Bilgisayarı bir modemin arkasına alın veya güvenlik duvarını açık tutup kullanmadığınız "
                        "hizmetleri kapatın."),
    "sec_exposed": ("Services open to the internet", "İnternete açık hizmetler"),
    "sec_exposed_d": ("Listening on the public address: {list}. These are common attack targets.",
                      "Genel adreste dinleyen hizmetler: {list}. Bunlar sık saldırı hedefidir."),
    "sec_exposed_f": ("Stop these services or allow them only from trusted addresses in the firewall.",
                      "Bu hizmetleri durdurun veya güvenlik duvarında yalnızca güvenilir adreslere izin verin."),
    "sec_rdp_no_nla": ("Remote Desktop without sign-in protection", "Oturum korumasız Uzak Masaüstü"),
    "sec_rdp_no_nla_d": ("Remote Desktop is on and Network Level Authentication is off: the login screen is "
                         "offered to anyone before they prove who they are.", "Uzak Masaüstü açık ve Ağ Düzeyinde "
                         "Kimlik Doğrulama kapalı: giriş ekranı kim olduğunu kanıtlamadan herkese sunuluyor."),
    "sec_rdp_no_nla_f": ("Settings > System > Remote Desktop > Advanced: require Network Level Authentication.",
                         "Ayarlar > Sistem > Uzak Masaüstü > Gelişmiş: Ağ Düzeyinde Kimlik Doğrulama'yı zorunlu kılın."),
    "sec_rdp_public": ("Remote Desktop on an untrusted network", "Güvenilmeyen ağda Uzak Masaüstü"),
    "sec_rdp_public_d": ("Remote Desktop is on while connected to \"{name}\". Password guessing against it is "
                         "common.", "\"{name}\" ağına bağlıyken Uzak Masaüstü açık. Buna karşı şifre denemeleri "
                         "yaygındır."),
    "sec_rdp_public_f": ("Turn Remote Desktop off when you do not need it.",
                         "Gerekmediğinde Uzak Masaüstü'nü kapatın."),
    "sec_smb1": ("SMB1 file sharing protocol is on", "SMB1 dosya paylaşım protokolü açık"),
    "sec_smb1_d": ("SMB1 is decades old and was used by large worm outbreaks. Nothing current needs it.",
                   "SMB1 onlarca yıllık bir protokol ve büyük solucan salgınlarında kullanıldı. Güncel hiçbir şey "
                   "ona ihtiyaç duymaz."),
    "sec_smb1_f": ("Windows Features: untick \"SMB 1.0/CIFS File Sharing Support\".",
                   "Windows Özellikleri: \"SMB 1.0/CIFS Dosya Paylaşımı Desteği\"nin işaretini kaldırın."),
    "sec_poisoning": ("Old name lookups are on (NetBIOS, LLMNR)", "Eski ad çözümleme yöntemleri açık (NetBIOS, LLMNR)"),
    "sec_poisoning_d": ("When a name is not found, Windows asks the whole local network. Another device on "
                        "\"{name}\" can answer falsely and capture sign-in hashes.", "Bir ad bulunamadığında "
                        "Windows bütün yerel ağa sorar. \"{name}\" ağındaki başka bir cihaz sahte yanıt verip "
                        "oturum açma özetlerini ele geçirebilir."),
    "sec_poisoning_f": ("Disable NetBIOS over TCP/IP in the adapter's IPv4 > Advanced > WINS settings.",
                        "Kartın IPv4 > Gelişmiş > WINS ayarlarında TCP/IP üzerinden NetBIOS'u devre dışı bırakın."),
    "sec_wpad": ("Automatic proxy discovery is on", "Otomatik proxy bulma açık"),
    "sec_wpad_d": ("On an untrusted network another device can offer itself as the proxy and see web traffic.",
                   "Güvenilmeyen bir ağda başka bir cihaz kendini proxy olarak sunup web trafiğini görebilir."),
    "sec_wpad_f": ("Settings > Network > Proxy: turn off \"Automatically detect settings\" if you do not need it.",
                   "Ayarlar > Ağ > Proxy: gerekmiyorsa \"Ayarları otomatik olarak algıla\"yı kapatın."),
    "sec_proxy": ("Web traffic goes through a proxy", "Web trafiği bir proxy üzerinden gidiyor"),
    "sec_proxy_d": ("Proxy set for this user: {addr}. Legitimate at work; if you did not set it, it can read and "
                    "change your browsing.", "Bu kullanıcı için ayarlı proxy: {addr}. İş yerinde olağandır; siz "
                    "ayarlamadıysanız gezintinizi okuyup değiştirebilir."),
    "sec_proxy_f": ("If you do not recognise it, remove it in Settings > Network > Proxy and scan for malware.",
                    "Tanımıyorsanız Ayarlar > Ağ > Proxy'den kaldırın ve zararlı yazılım taraması yapın."),
    "sec_proxy_system": ("System-wide proxy", "Sistem geneli proxy"),
    "sec_proxy_system_d": ("Windows services use the proxy {addr}.", "Windows hizmetleri {addr} proxy'sini kullanıyor."),
    "sec_proxy_system_f": ("If you did not set it, reset it (netsh winhttp reset proxy) from an administrator prompt.",
                           "Siz ayarlamadıysanız yönetici komut isteminden sıfırlayın (netsh winhttp reset proxy)."),
    "sec_hosts": ("Names redirected in the hosts file", "Hosts dosyasında yönlendirilen adlar"),
    "sec_hosts_d": ("These names do not go to their real address: {list}.",
                    "Bu adlar gerçek adreslerine gitmiyor: {list}."),
    "sec_hosts_f": ("If you did not add them, remove them from C:\\Windows\\System32\\drivers\\etc\\hosts.",
                    "Siz eklemediyseniz C:\\Windows\\System32\\drivers\\etc\\hosts dosyasından silin."),
    # -- router ---------------------------------------------------------------------------------------
    "sec_gw_telnet": ("Router accepts Telnet", "Modem Telnet kabul ediyor"),
    "sec_gw_telnet_d": ("Port 23 is open on {gw}. Telnet sends the password in plain text and is a favourite "
                        "target of botnets.", "{gw} üzerinde 23 numaralı port açık. Telnet şifreyi düz metin "
                        "gönderir ve botnetlerin gözde hedefidir."),
    "sec_gw_telnet_f": ("Turn Telnet off in the router's administration settings.",
                        "Modemin yönetim ayarlarında Telnet'i kapatın."),
    "sec_gw_ftp": ("Router runs an FTP server", "Modemde FTP sunucusu çalışıyor"),
    "sec_gw_ftp_d": ("Port 21 is open on {gw}; FTP sends passwords unencrypted.",
                     "{gw} üzerinde 21 numaralı port açık; FTP şifreleri şifrelemeden gönderir."),
    "sec_gw_ftp_f": ("Turn off the router's FTP / USB storage sharing if unused.",
                     "Kullanılmıyorsa modemin FTP / USB depolama paylaşımını kapatın."),
    "sec_gw_smb": ("Router shares files (SMB)", "Modem dosya paylaşıyor (SMB)"),
    "sec_gw_smb_d": ("{gw} answers on the file sharing port. Router file sharing is often outdated and unencrypted.",
                     "{gw} dosya paylaşım portunda yanıt veriyor. Modem dosya paylaşımı çoğunlukla eski ve şifresizdir."),
    "sec_gw_smb_f": ("Turn off the router's USB / network storage sharing if you do not use it.",
                     "Kullanmıyorsanız modemin USB / ağ depolama paylaşımını kapatın."),
    "sec_gw_http": ("Router admin page is unencrypted", "Modem yönetim sayfası şifresiz"),
    "sec_gw_http_d": ("{gw} offers its admin page over plain HTTP only: the admin password crosses the network "
                      "unencrypted.", "{gw} yönetim sayfasını yalnızca düz HTTP ile sunuyor: yönetici şifresi ağda "
                      "şifrelenmeden gider."),
    "sec_gw_http_f": ("Use a cable when you sign in to the router, and change its default password.",
                      "Modeme girerken kablo kullanın ve varsayılan şifresini değiştirin."),
    "sec_gw_ssh": ("Router accepts SSH", "Modem SSH kabul ediyor"),
    "sec_gw_ssh_d": ("Port 22 is open on {gw}. Fine if you use it; make sure its password is not the default.",
                     "{gw} üzerinde 22 numaralı port açık. Kullanıyorsanız sorun değil; şifresinin varsayılan "
                     "olmadığından emin olun."),
    "sec_gw_tr069": ("Provider remote management port", "Servis sağlayıcı uzaktan yönetim portu"),
    "sec_gw_tr069_d": ("Port 7547 is open on {gw}: the provider can manage the router remotely. Normal for "
                       "provider-supplied routers; it is a reason to keep its firmware up to date.",
                       "{gw} üzerinde 7547 numaralı port açık: servis sağlayıcı modemi uzaktan yönetebilir. "
                       "Sağlayıcının verdiği modemlerde olağandır; yazılımını güncel tutmak için bir nedendir."),
    "sec_gw_clean": ("No risky router services", "Modemde riskli hizmet yok"),
    "sec_gw_clean_d": ("{gw} does not answer on Telnet, FTP or file sharing ports.",
                       "{gw} Telnet, FTP ve dosya paylaşım portlarında yanıt vermiyor."),
    "sec_upnp": ("UPnP is on in the router", "Modemde UPnP açık"),
    "sec_upnp_d": ("{device} lets any program on the network open ports to the internet without asking. Handy "
                   "for games and calls, but malware uses it too.", "{device} ağdaki her programın sormadan internete "
                   "port açmasına izin veriyor. Oyunlar ve görüşmeler için pratik, ama zararlı yazılımlar da kullanır."),
    "sec_upnp_f": ("Turn UPnP off in the router if nothing you use needs it.",
                   "Kullandığınız hiçbir şey ihtiyaç duymuyorsa modemde UPnP'yi kapatın."),
    "sec_upnp_off": ("UPnP is not offered", "UPnP sunulmuyor"),
    "sec_upnp_off_d": ("The router does not let programs open internet ports on their own.",
                       "Modem programların kendi başına internet portu açmasına izin vermiyor."),
    "sec_upnp_risky": ("Risky port forwarded to the internet", "Riskli port internete yönlendirilmiş"),
    "sec_upnp_risky_d": ("Forwarded by UPnP: {list}. These services should never face the internet.",
                         "UPnP ile yönlendirilmiş: {list}. Bu hizmetler asla internete açık olmamalı."),
    "sec_upnp_risky_f": ("Delete the forwarding in the router and find the program that created it.",
                         "Yönlendirmeyi modemden silin ve onu oluşturan programı bulun."),
    "sec_upnp_self": ("Ports forwarded to this computer", "Bu bilgisayara yönlendirilmiş portlar"),
    "sec_upnp_self_d": ("Open from the internet to this computer: {list}.",
                        "İnternetten bu bilgisayara açık: {list}."),
    "sec_upnp_self_f": ("Check you recognise each program; close the ones you do not.",
                        "Her programı tanıdığınızdan emin olun; tanımadıklarınızı kapatın."),
    "sec_upnp_maps": ("Ports forwarded by UPnP", "UPnP ile yönlendirilmiş portlar"),
    "sec_upnp_maps_d": ("Open from the internet to other devices: {list}.",
                        "İnternetten diğer cihazlara açık: {list}."),
    # -- local network integrity ---------------------------------------------------------------------
    "sec_arp_spoof": ("Possible traffic interception (ARP)", "Olası trafik dinleme (ARP)"),
    "sec_arp_spoof_d": ("The router's hardware address {mac} is also claimed by {list}. A device on the network "
                        "may be posing as the router to read traffic.", "Modemin donanım adresi {mac} aynı zamanda "
                        "{list} tarafından da kullanılıyor. Ağdaki bir cihaz trafiği okumak için kendini modem gibi "
                        "gösteriyor olabilir."),
    "sec_arp_spoof_f": ("Disconnect from this network and check the devices on it; at home restart the router.",
                        "Bu ağdan çıkın ve ağdaki cihazları kontrol edin; evdeyseniz modemi yeniden başlatın."),
    "sec_ip_duplicate": ("Address conflict", "Adres çakışması"),
    "sec_ip_duplicate_d": ("Another device on the network uses {ip}.", "Ağdaki başka bir cihaz {ip} adresini kullanıyor."),
    "sec_ip_duplicate_f": ("Set the address to automatic (DHCP) or pick a free one.",
                           "Adresi otomatik (DHCP) yapın veya boş bir adres seçin."),
    "sec_apipa": ("No address from the router", "Modemden adres alınamadı"),
    "sec_apipa_d": ("{ip} is a fallback address: the DHCP server did not answer.",
                    "{ip} yedek bir adres: DHCP sunucusu yanıt vermedi."),
    "sec_apipa_f": ("Restart the router; check the cable or Wi-Fi password.",
                    "Modemi yeniden başlatın; kabloyu veya Wi-Fi şifresini kontrol edin."),
    "sec_dns_hijack": ("DNS rewrites answers", "DNS yanıtları değiştiriyor"),
    "sec_dns_hijack_d": ("A made-up name got an address instead of \"not found\". The resolver redirects mistyped "
                         "addresses, and could redirect real ones too.", "Uydurma bir ad \"bulunamadı\" yerine bir "
                         "adres aldı. Çözümleyici yanlış yazılan adresleri yönlendiriyor, gerçek adresleri de "
                         "yönlendirebilir."),
    "sec_dns_hijack_f": ("Use a public DNS server you trust in the adapter or router settings.",
                         "Kart veya modem ayarlarında güvendiğiniz genel bir DNS sunucusu kullanın."),
    "sec_dns_external": ("DNS servers outside the local network", "Yerel ağ dışındaki DNS sunucuları"),
    "sec_dns_external_d": ("Names are looked up at {list}. Make sure these are the ones you or your provider set.",
                           "Adlar {list} adresinde çözülüyor. Bunların sizin veya servis sağlayıcınızın ayarladığı "
                           "sunucular olduğundan emin olun."),
    "sec_dns_fail": ("A DNS server does not answer", "Bir DNS sunucusu yanıt vermiyor"),
    "sec_dns_fail_d": ("No answer from {list}. Lookups slow down while Windows waits for it.",
                       "{list} yanıt vermiyor. Windows onu beklerken ad çözümleme yavaşlar."),
    "sec_dns_fail_f": ("Remove or replace that server in the adapter's DNS settings.",
                       "Bu sunucuyu kartın DNS ayarlarından kaldırın veya değiştirin."),
    "sec_portal": ("Login page in front of the internet", "İnternetin önünde giriş sayfası"),
    "sec_portal_d": ("Web requests are answered by a sign-in page (hotel, café, guest network). Treat the network "
                     "as untrusted.", "Web istekleri bir giriş sayfasıyla yanıtlanıyor (otel, kafe, misafir ağı). "
                     "Ağı güvenilmez sayın."),
    "sec_portal_f": ("Sign in through the browser; prefer encrypted (HTTPS) sites or a VPN here.",
                     "Tarayıcıdan giriş yapın; burada şifreli (HTTPS) siteleri veya VPN'i tercih edin."),
    "sec_intercepted": ("Web traffic is being altered", "Web trafiği değiştiriliyor"),
    "sec_intercepted_d": ("A known test page came back different from the original: something between this "
                          "computer and the internet changes unencrypted traffic.", "Bilinen bir test sayfası "
                          "aslından farklı geldi: bu bilgisayarla internet arasındaki bir şey şifresiz trafiği "
                          "değiştiriyor."),
    "sec_intercepted_f": ("Avoid unencrypted sites on this network; check the router and proxy settings.",
                          "Bu ağda şifresiz sitelerden kaçının; modem ve proxy ayarlarını kontrol edin."),
    "sec_cgnat": ("Shared provider address (CGNAT)", "Paylaşımlı sağlayıcı adresi (CGNAT)"),
    "sec_cgnat_d": ("The provider shares one public address among many customers. Incoming connections and port "
                    "forwarding will not work; it also hides this network from the internet.",
                    "Servis sağlayıcı tek bir genel adresi birçok müşteriyle paylaşıyor. Gelen bağlantılar ve port "
                    "yönlendirme çalışmaz; bu aynı zamanda ağı internetten gizler."),
    "sec_double_nat": ("Double NAT", "Çift NAT"),
    "sec_double_nat_d": ("Two routers translate addresses one after the other ({list}). Port forwarding and some "
                         "games or calls may fail.", "İki modem art arda adres çeviriyor ({list}). Port yönlendirme "
                         "ve bazı oyunlar ya da görüşmeler sorun çıkarabilir."),
    "sec_double_nat_f": ("Put the provider's modem in bridge mode, or use only one router.",
                         "Sağlayıcının modemini köprü moduna alın veya tek bir modem kullanın."),
    "sec_v6_privacy": ("IPv6 address without privacy extension", "Gizlilik uzantısız IPv6 adresi"),
    "sec_v6_privacy_d": ("The public IPv6 address {ip} stays the same everywhere, so sites can follow this "
                         "computer across networks.", "Genel IPv6 adresi {ip} her yerde aynı kalıyor; siteler bu "
                         "bilgisayarı ağdan ağa izleyebilir."),
    "sec_v6_privacy_f": ("Enable temporary addresses: netsh interface ipv6 set privacy state=enabled (as administrator).",
                         "Geçici adresleri açın: netsh interface ipv6 set privacy state=enabled (yönetici olarak)."),
    "sec_driver_old": ("Old network driver", "Eski ağ sürücüsü"),
    "sec_driver_old_d": ("The driver is from {date} ({years} years old). Newer drivers fix security and stability "
                         "issues.", "Sürücü {date} tarihli ({years} yıllık). Yeni sürücüler güvenlik ve kararlılık "
                         "sorunlarını giderir."),
    "sec_driver_old_f": ("Get the latest driver from the computer or adapter maker's website.",
                         "En güncel sürücüyü bilgisayarın veya kartın üreticisinin sitesinden indirin."),
    "sec_errors": ("Many damaged or dropped packets", "Çok sayıda bozuk veya atılan paket"),
    "sec_errors_d": ("{pct}% of packets had errors or were dropped ({n} of {total}). Usually a bad cable, port "
                     "or interference.", "Paketlerin %{pct}'i hatalı veya atılmış ({total} içinde {n}). Genelde "
                     "kötü kablo, port veya parazit kaynaklıdır."),
    "sec_errors_f": ("Try another cable or port; on Wi-Fi, another channel.",
                     "Başka bir kablo veya port deneyin; Wi-Fi'de başka bir kanal."),
})

# services an attacker looks for first, with a plain label (port names, no product names)
RISKY_PORTS = {21: "FTP", 22: "SSH", 23: "Telnet", 135: "RPC", 139: "NetBIOS", 445: "SMB", 1433: "SQL",
               1521: "SQL", 3306: "SQL", 3389: "RDP", 5432: "SQL", 5900: "VNC", 5985: "WinRM", 5986: "WinRM",
               6379: "Redis", 9200: "Search", 27017: "NoSQL", 11211: "Cache"}

POSTURE = r"""
$r = [ordered]@{}
try { $r.firewall = @(Get-NetFirewallProfile -PolicyStore ActiveStore | ForEach-Object {
  [pscustomobject]@{ name = [string]$_.Name; enabled = [string]$_.Enabled; inbound = [string]$_.DefaultInboundAction } }) } catch {}
try { $s = Get-SmbServerConfiguration; $r.smb1 = [bool]$s.EnableSMB1Protocol; $r.smb_signing = [bool]$s.RequireSecuritySignature } catch {}
try { $r.smb1_feature = [string](Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol).State } catch {}
try { $p = Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient'; if ($p.PSObject.Properties['EnableMulticast']) { $r.llmnr = [int]$p.EnableMulticast } } catch {}
try { $p = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\Dnscache\Parameters'; if ($p.PSObject.Properties['EnableMDNS']) { $r.mdns = [int]$p.EnableMDNS } } catch {}
try { $p = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
  $r.proxy = [pscustomobject]@{ enabled = [int]$p.ProxyEnable; server = [string]$p.ProxyServer; pac = [string]$p.AutoConfigURL } } catch {}
try { $b = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings\Connections').DefaultConnectionSettings
  if ($b) { $r.conn_settings = [Convert]::ToBase64String($b) } } catch {}
try { $b = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings\Connections').WinHttpSettings
  if ($b) { $r.winhttp = [Convert]::ToBase64String($b) } } catch {}
try { $p = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'; $r.rdp = ([int]$p.fDenyTSConnections -eq 0)
  $q = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp'; $r.rdp_nla = ([int]$q.UserAuthentication -eq 1) } catch {}
$names = @{}; try { Get-Process | ForEach-Object { $names[[int]$_.Id] = $_.ProcessName } } catch {}
try { $r.listen_tcp = @(Get-NetTCPConnection -State Listen | ForEach-Object {
  [pscustomobject]@{ addr = [string]$_.LocalAddress; port = [int]$_.LocalPort; process = $names[[int]$_.OwningProcess] } }) } catch {}
try { $r.listen_udp = @(Get-NetUDPEndpoint | Where-Object { $_.LocalPort -in 137,138,1900,5353,5355 } | ForEach-Object {
  [pscustomobject]@{ addr = [string]$_.LocalAddress; port = [int]$_.LocalPort; process = $names[[int]$_.OwningProcess] } }) } catch {}
try { $r.hosts = @(Get-Content "$env:SystemRoot\System32\drivers\etc\hosts" | ForEach-Object { ($_ -split '#')[0].Trim() } | Where-Object { $_ }) } catch {}
try { $groups = @{ sharing = '@FirewallAPI.dll,-28502'; discovery = '@FirewallAPI.dll,-32752' }
  foreach ($k in $groups.Keys) { $r[$k] = @(Get-NetFirewallRule -Group $groups[$k] -Direction Inbound | Where-Object { $_.Enabled -eq 'True' } | ForEach-Object { [string]$_.Profile } | Sort-Object -Unique) } } catch {}
try { if (Get-Service WlanSvc | Where-Object { $_.Status -eq 'Running' }) {
  $dir = Join-Path $env:TEMP ('bw-wlan-' + [guid]::NewGuid().ToString('N')); New-Item -ItemType Directory $dir | Out-Null
  try { netsh wlan export profile folder="$dir" | Out-Null
    $r.wifi_profiles = @(Get-ChildItem $dir -Filter *.xml | ForEach-Object { $x = [xml](Get-Content -Raw -LiteralPath $_.FullName -Encoding UTF8)
      $p = $x.WLANProfile; [pscustomobject]@{ name = [string]$p.name; mode = [string]$p.connectionMode
        auth = [string]$p.MSM.security.authEncryption.authentication; enc = [string]$p.MSM.security.authEncryption.encryption } })
  } finally { Remove-Item -Recurse -Force -LiteralPath $dir } } } catch {}
[pscustomobject]$r | ConvertTo-Json -Depth 4 -Compress
"""


def _conn_flags(b64):
    """Flags DWORD of an Internet Settings connection blob (0x08 = automatically detect settings)."""
    try:
        raw = base64.b64decode(b64)
        return struct.unpack_from("<I", raw, 8)[0]
    except Exception:
        return None


def _winhttp_proxy(b64):
    """The WinHTTP proxy server from its registry blob, or None for a direct connection."""
    try:
        raw = base64.b64decode(b64)
        flags, n = struct.unpack_from("<II", raw, 8)
        if not flags & 0x02 or not n:
            return None
        return raw[16:16 + n].decode("ascii", "replace")
    except Exception:
        return None


def _profiles_of(values):
    """Firewall rule profile strings ("Private, Public", "Any") -> set of profile names."""
    out = set()
    for v in as_list(values):
        for part in str(v).replace(" ", "").split(","):
            if part == "Any":
                out |= {"Domain", "Private", "Public"}
            elif part:
                out.add(part)
    return out


def _parse_posture(raw):
    p = {}
    fw = {}
    for f in as_list(raw.get("firewall")):
        if f.get("name"):
            fw[f["name"]] = {"enabled": str(f.get("enabled")).lower() == "true", "inbound": f.get("inbound") or ""}
    if fw:
        p["firewall"] = fw
    for k in ("smb1", "smb_signing", "rdp", "rdp_nla"):
        if raw.get(k) is not None:
            p[k] = bool(raw[k])
    if raw.get("smb1_feature"):
        p["smb1_feature"] = raw["smb1_feature"]
    # LLMNR and mDNS are on unless a policy / setting turns them off
    p["llmnr"] = raw.get("llmnr", 1) != 0
    p["mdns"] = raw.get("mdns", 1) != 0
    px = raw.get("proxy") or {}
    p["proxy"] = {"enabled": bool(px.get("enabled")), "server": px.get("server") or "", "pac": px.get("pac") or ""}
    if raw.get("conn_settings"):
        flags = _conn_flags(raw["conn_settings"])
        if flags is not None:
            p["wpad"] = bool(flags & 0x08)
    if raw.get("winhttp"):
        p["winhttp_proxy"] = _winhttp_proxy(raw["winhttp"])
    p["listen_tcp"] = [x for x in as_list(raw.get("listen_tcp")) if isinstance(x, dict)]
    p["listen_udp"] = [x for x in as_list(raw.get("listen_udp")) if isinstance(x, dict)]
    hosts = []
    for line in as_list(raw.get("hosts")):
        parts = str(line).split()
        if len(parts) < 2:
            continue
        for name in parts[1:]:
            if name.lower() != "localhost":
                hosts.append({"ip": parts[0], "name": name})
    p["hosts"] = hosts
    for k in ("sharing", "discovery"):
        if k in raw:
            p[k] = sorted(_profiles_of(raw.get(k)))
    if "wifi_profiles" in raw:
        profs = [x for x in as_list(raw["wifi_profiles"]) if isinstance(x, dict)]
        p["wifi_profiles"] = profs
        p["wifi_auto_open"] = [x.get("name") for x in profs
                               if (x.get("mode") or "").lower() == "auto" and (x.get("auth") or "").lower() == "open"
                               and (x.get("enc") or "").lower() == "none"]
    return p


def system_posture():
    """Machine-wide security settings (dict; missing keys = could not be read).  Never raises."""
    try:
        raw = powershell_json(POSTURE, timeout=90)
        if not isinstance(raw, dict):
            return {}
        return _parse_posture(raw)
    except Exception:
        return {}


# -- assessment ---------------------------------------------------------------------------------
def _ip(text):
    try:
        return ipaddress.ip_address(str(text).split("%")[0])
    except ValueError:
        return None


def _is_public_v4(addr):
    a = _ip(addr)
    return bool(a and a.version == 4 and a.is_global and a not in ipaddress.ip_network("100.64.0.0/10"))


def _finding(level, key, fix=True, **kw):
    fkey = "sec_%s_f" % key
    return {"level": level, "key": key, "title": t("sec_" + key, **kw), "detail": t("sec_%s_d" % key, **kw),
            "fix": t(fkey, **kw) if fix and fkey in _strings() else ""}


def _strings():
    from recoverytool import i18n
    return i18n.STRINGS


def _ports(d):
    """Router port results with int keys (JSON round trips turn them into strings)."""
    out = {}
    for k, v in (d or {}).items():
        try:
            out[int(k)] = bool(v)
        except (TypeError, ValueError):
            pass
    return out


def _years_old(date_text, today):
    try:
        d = datetime.date.fromisoformat(str(date_text)[:10])
    except ValueError:
        return None
    return (today - d).days / 365.25


def _join(items, limit=6):
    items = list(items)
    more = len(items) - limit
    return ", ".join(items[:limit]) + (" …(+%d)" % more if more > 0 else "")


def assess(adapter, posture=None, today=None):
    """Findings for one adapter, most serious first."""
    posture = posture or {}
    today = today or datetime.date.today()
    cfg = adapter.get("config") or {}
    probe = adapter.get("probe") or {}
    wifi = cfg.get("wifi") or {}
    out = []
    add = out.append
    up = adapter.get("status") == "Up"
    v4 = [a for a in as_list(cfg.get("v4")) if isinstance(a, dict) and a.get("addr")]
    gw4 = [g for g in as_list(cfg.get("gw4")) if g and g != "0.0.0.0"]
    internet_facing = bool(gw4) or not adapter.get("virtual")
    profile = cfg.get("profile") or {}
    category = profile.get("category") or ""
    fw_name = "Domain" if category.startswith("Domain") else category
    # the Wi-Fi name the user knows first: Windows' profile name may be "Home 2" for the network "Home"
    net_name = wifi.get("ssid") or profile.get("name") or adapter.get("name") or ""
    untrusted = category == "Public"

    # -- Wi-Fi link ----------------------------------------------------------------------------
    open_wifi = False
    if adapter.get("kind") == "wifi" and wifi:
        auth, cipher = (wifi.get("auth") or ""), (wifi.get("cipher") or "")
        ssid = wifi.get("ssid") or net_name
        au = auth.upper()
        kw = {"ssid": ssid, "auth": auth, "cipher": cipher}
        if au in ("OPEN", "") and cipher.upper() in ("NONE", ""):
            open_wifi = True
            add(_finding("bad", "wifi_open", **kw))
        elif "WEP" in au or cipher.upper().startswith("WEP"):
            open_wifi = True
            add(_finding("bad", "wifi_wep", **kw))
        elif au.startswith("WPA-") or au == "WPA" or (cipher.upper() == "TKIP"):
            add(_finding("bad" if not au.startswith(("WPA2", "WPA3")) else "warning", "wifi_wpa1", **kw))
        elif "ENTERPRISE" in au or wifi.get("onex"):
            add(_finding("good", "wifi_enterprise", fix=False, **kw))
        elif au.startswith("WPA3") or "SAE" in au or "OWE" in au:
            add(_finding("good", "wifi_wpa3", fix=False, **kw))
        elif au.startswith("WPA2"):
            add(_finding("good", "wifi_wpa2", fix=False, **kw))
        sig, rssi = wifi.get("signal"), wifi.get("rssi")
        if (isinstance(sig, (int, float)) and sig < 40) or (isinstance(rssi, (int, float)) and rssi <= -75):
            add(_finding("warning", "wifi_weak", signal=sig if sig is not None else "?", rssi=rssi if rssi is not None else "?"))
    if adapter.get("kind") == "wifi" and posture.get("wifi_auto_open"):
        add(_finding("warning", "wifi_auto_open", names=_join('"%s"' % n for n in posture["wifi_auto_open"])))
    if open_wifi:
        untrusted = True

    # -- category, firewall, sharing (only when Windows has a profile for it) -------------------
    if up and category:
        sharing = set(posture.get("sharing") or [])
        discovery = set(posture.get("discovery") or [])
        bound = (cfg.get("bindings") or {}).get("ms_server", True)
        if category == "Private" and open_wifi:
            add(_finding("bad", "private_untrusted", name=net_name))
        elif category == "Public":
            if bound and "Public" in sharing:
                add(_finding("bad", "public_sharing", name=net_name))
            else:
                add(_finding("good", "public_profile", fix=False, name=net_name))
        elif category == "Private" and ((bound and "Private" in sharing) or "Private" in discovery):
            what = [t("sec_what_sharing")] if bound and "Private" in sharing else []
            if "Private" in discovery:
                what.append(t("sec_what_discovery"))
            add(_finding("info", "private_visible", fix=False, name=net_name, what=t("sec_what_and").join(what)))
        fw = (posture.get("firewall") or {}).get(fw_name)
        if fw is not None:
            pname = t("sec_profile_" + fw_name) if ("sec_profile_" + fw_name) in _strings() else fw_name
            if not fw.get("enabled"):
                add(_finding("bad", "firewall_off", profile=pname))
            elif str(fw.get("inbound")).lower() == "allow":
                add(_finding("bad", "firewall_allow", profile=pname))
            else:
                add(_finding("good", "firewall_on", fix=False, profile=pname))

    # -- addresses ------------------------------------------------------------------------------
    for a in v4:
        if str(a.get("state")) == "Duplicate":
            add(_finding("bad", "ip_duplicate", ip=a["addr"]))
        elif str(a["addr"]).startswith("169.254.") and up:
            add(_finding("warning", "apipa", ip=a["addr"]))
    public_addrs = [a["addr"] for a in v4 if _is_public_v4(a["addr"])]
    my_addrs = {a["addr"] for a in v4}
    if up and public_addrs:
        add(_finding("warning", "public_ip", ip=public_addrs[0]))
        exposed = sorted({(x.get("port"), x.get("process") or "") for x in posture.get("listen_tcp") or []
                          if x.get("port") in RISKY_PORTS and (x.get("addr") in ("0.0.0.0", "::") or x.get("addr") in my_addrs)})
        if exposed:
            add(_finding("bad", "exposed", list=_join("%s %d%s" % (RISKY_PORTS[p], p, (" (%s)" % n) if n else "")
                                                       for p, n in exposed)))
        if public_addrs:
            untrusted = True

    # -- machine services judged against this network ------------------------------------------
    if up and v4:
        if posture.get("rdp"):
            if posture.get("rdp_nla") is False:
                add(_finding("bad", "rdp_no_nla"))
            elif untrusted:
                add(_finding("warning", "rdp_public", name=net_name))
        if posture.get("smb1") or str(posture.get("smb1_feature")) == "Enabled":
            add(_finding("bad", "smb1"))
        nb = cfg.get("netbios")
        if nb in (0, 1) and posture.get("llmnr", True) and untrusted:
            add(_finding("warning", "poisoning", name=net_name))
        if posture.get("wpad") and untrusted:
            add(_finding("info", "wpad"))

    # -- proxy and hosts are per user / machine; show them on every connected adapter ----------
    if up:
        px = posture.get("proxy") or {}
        if px.get("enabled") and px.get("server"):
            add(_finding("warning", "proxy", addr=px["server"]))
        elif px.get("pac"):
            add(_finding("warning", "proxy", addr=px["pac"]))
        if posture.get("winhttp_proxy"):
            add(_finding("info", "proxy_system", addr=posture["winhttp_proxy"]))
        hosts = [h for h in posture.get("hosts") or [] if h.get("ip") not in ("127.0.0.1", "::1", "0.0.0.0")]
        if hosts:
            add(_finding("info", "hosts", list=_join("%s → %s" % (h["name"], h["ip"]) for h in hosts)))

    # -- router and the way out (only when the probes ran) --------------------------------------
    gw = probe.get("gateway") or {}
    gwip = gw.get("ip") or (gw4[0] if gw4 else "")
    if probe and internet_facing:
        ports = _ports(gw.get("ports"))
        if ports:
            risky = False
            if ports.get(23):
                add(_finding("bad", "gw_telnet", gw=gwip))
                risky = True
            if ports.get(21):
                add(_finding("warning", "gw_ftp", gw=gwip))
                risky = True
            if ports.get(445) or ports.get(139):
                add(_finding("warning", "gw_smb", gw=gwip))
                risky = True
            if ports.get(80) and 443 in ports and not ports.get(443) and not ports.get(8443):
                add(_finding("warning" if untrusted else "info", "gw_http", gw=gwip))
            if ports.get(22):
                add(_finding("info", "gw_ssh", fix=False, gw=gwip))
            if ports.get(7547):
                add(_finding("info", "gw_tr069", fix=False, gw=gwip))
            if not risky:
                add(_finding("good", "gw_clean", fix=False, gw=gwip))
        if "upnp" in gw:
            upnp = gw.get("upnp")
            if upnp:
                device = " ".join(x for x in (upnp.get("manufacturer"), upnp.get("model") or upnp.get("friendly")) if x) or gwip
                add(_finding("warning", "upnp", device=device))
                maps = [m for m in as_list(upnp.get("mappings")) if isinstance(m, dict) and m.get("enabled", True)]

                def label(m):
                    return "%s %s → %s:%s%s" % (m.get("proto") or "", m.get("ext_port"), m.get("client"),
                                                m.get("int_port"), (" (%s)" % m["desc"]) if m.get("desc") else "")

                def port(m, k):
                    try:
                        return int(m.get(k))
                    except (TypeError, ValueError):
                        return None
                risky = [m for m in maps if port(m, "ext_port") in RISKY_PORTS or port(m, "int_port") in RISKY_PORTS]
                mine = [m for m in maps if m not in risky and m.get("client") in my_addrs]
                rest = [m for m in maps if m not in risky and m not in mine]
                if risky:
                    add(_finding("bad", "upnp_risky", list=_join(label(m) for m in risky)))
                if mine:
                    add(_finding("warning", "upnp_self", list=_join(label(m) for m in mine)))
                if rest:
                    add(_finding("info", "upnp_maps", fix=False, list=_join(label(m) for m in rest)))
            else:
                add(_finding("good", "upnp_off", fix=False))
        shared = [x for x in as_list(probe.get("gw_mac_shared")) if x]
        if shared:
            add(_finding("bad", "arp_spoof", mac=gw.get("mac") or "?", list=_join(shared)))
        if probe.get("nx_hijack"):
            add(_finding("warning", "dns_hijack"))
        dead = [d.get("server") for d in as_list(probe.get("dns")) if isinstance(d, dict) and d.get("ok") is False]
        if dead:
            add(_finding("warning", "dns_fail", list=_join(dead)))
        inet = probe.get("internet") or {}
        if inet.get("portal"):
            add(_finding("warning", "portal"))
        elif inet.get("intercepted"):
            add(_finding("bad", "intercepted"))
        if probe.get("cgnat"):
            add(_finding("info", "cgnat", fix=False))
        if probe.get("double_nat"):
            # the router's own internet-side address is private: that is what proves the second NAT
            add(_finding("info", "double_nat", list=" → ".join(x for x in (gwip, probe.get("wan_ip")) if x)))

    if up and internet_facing:
        ext = []
        # the router's own global IPv6 address sits in the same delegated prefix as ours: that is local
        own_nets = []
        for x in as_list(cfg.get("v6")) + as_list(cfg.get("v4")):
            try:
                n = ipaddress.ip_interface("%s/%s" % (x.get("addr"), min(int(x.get("prefix") or 64), 64)
                                                      if ":" in str(x.get("addr")) else x.get("prefix"))).network
            except (ValueError, TypeError, AttributeError):
                continue
            if not n.is_link_local:
                own_nets.append(n)
        for s in as_list(cfg.get("dns")):
            a = _ip(s)
            if a is None or s in gw4 or a.is_private or a.is_link_local or a.is_loopback or \
                    (a.version == 6 and a in ipaddress.ip_network("fec0::/10")) or \
                    any(a.version == n.version and a in n for n in own_nets):
                continue
            ext.append(str(s))
        if ext:
            add(_finding("info", "dns_external", fix=False, list=_join(ext)))
        v6 = [a for a in as_list(cfg.get("v6")) if isinstance(a, dict) and a.get("addr")]
        glob = [a for a in v6 if _ip(a["addr"]) and _ip(a["addr"]) in ipaddress.ip_network("2000::/3")]
        if glob and not any(str(a.get("suffix_origin")) == "Random" for a in glob):
            add(_finding("info", "v6_privacy", ip=glob[0]["addr"]))

    # -- hardware / quality --------------------------------------------------------------------
    drv = adapter.get("driver") or {}
    years = _years_old(drv.get("date"), today) if drv.get("date") else None
    if years is not None and years > 3 and not adapter.get("virtual"):
        add(_finding("info", "driver_old", date=str(drv["date"])[:10], years=int(years)))
    st = cfg.get("stats") or {}
    total = (st.get("rx_unicast") or 0) + (st.get("tx_unicast") or 0)
    bad = sum(st.get(k) or 0 for k in ("rx_errors", "tx_errors", "rx_discards", "tx_discards"))
    if total >= 1000 and bad / total > 0.01:
        add(_finding("warning", "errors", pct="%.1f" % (100.0 * bad / total), n=bad, total=total))

    out.sort(key=lambda f: LEVEL_ORDER.get(f["level"], 9))
    return out


def score(findings):
    """The card colour: "bad", "warning" or "good" (info findings do not count)."""
    levels = {f.get("level") for f in findings or []}
    if "bad" in levels:
        return "bad"
    if "warning" in levels:
        return "warning"
    return "good"
