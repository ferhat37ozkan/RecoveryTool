"""Texts of the Benchwise window, added to the shared translation table (``recoverytool.i18n``)."""

from recoverytool import i18n

i18n.STRINGS.update({
    # --- window ---
    "bw_home": ("Home", "Ana sayfa"),
    "bw_tagline": ("Tools for your disks, hardware and Windows", "Diskleriniz, donanımınız ve Windows için araçlar"),
    "bw_admin_mode": ("Administrator", "Yönetici modu"),
    "bw_user_mode": ("Standard mode", "Standart mod"),
    "bw_admin_tip": ("Tools marked with a shield need administrator rights.",
                     "Kalkan işaretli araçlar yönetici yetkisi ister."),
    "bw_soon": ("Coming soon", "Yakında"),
    "bw_admin_badge": ("Admin", "Yönetici"),
    "bw_tools_n": ("{n} tools", "{n} araç"),
    "bw_tools_ready": ("{ready} of {n} tools ready", "{n} araçtan {ready} tanesi hazır"),
    "bw_soon_title": ("Coming soon", "Yakında"),
    "bw_soon_body": ("{tool} is planned but not built yet.", "{tool} planlandı ama henüz hazır değil."),
    "bw_admin_title": ("Administrator rights needed", "Yönetici yetkisi gerekiyor"),
    "bw_admin_body": ("{tool} needs administrator rights to work with your hardware directly.\n\n"
                      "Restart Benchwise as administrator and open {tool}?",
                      "{tool}, donanımınıza doğrudan erişebilmek için yönetici yetkisine ihtiyaç duyar.\n\n"
                      "Benchwise yönetici olarak yeniden başlatılsın ve {tool} açılsın mı?"),
    "bw_admin_busy": ("A tool is still working. Restarting stops it.\n\nRestart anyway?",
                      "Bir araç hâlâ çalışıyor. Yeniden başlatmak onu durdurur.\n\nYine de yeniden başlatılsın mı?"),
    "bw_admin_failed": ("Benchwise was not restarted as administrator (the request was declined).",
                        "Benchwise yönetici olarak yeniden başlatılmadı (istek reddedildi)."),
    "bw_lang_busy": ("The language can be changed when no tool is working.",
                     "Dil, çalışan bir araç yokken değiştirilebilir."),

    # --- Disk Health ---
    "dh_refresh": ("Refresh", "Yenile"),
    "dh_loading": ("Reading what the disks report…", "Disklerin bildirdikleri okunuyor…"),
    "dh_failed": ("Could not read disk health: {err}", "Disk sağlığı okunamadı: {err}"),
    "dh_none": ("No disks found.", "Disk bulunamadı."),
    "dh_level_good": ("Healthy", "Sağlıklı"),
    "dh_level_warning": ("Watch it", "Dikkat"),
    "dh_level_bad": ("At risk", "Riskli"),
    "dh_level_unknown": ("No data", "Bilgi yok"),
    "dh_lead_good": ("Nothing worrying in what this disk reports.", "Bu diskin bildirdiklerinde endişe verici bir şey yok."),
    "dh_lead_warning": ("Early signs of trouble, or a condition worth fixing.",
                        "Erken sorun işaretleri ya da düzeltilmesi gereken bir durum var."),
    "dh_lead_bad": ("Copy what matters off this disk now, before anything else.",
                    "Bu diskteki önemli verileri her şeyden önce şimdi başka bir yere kopyalayın."),
    "dh_lead_unknown": ("This disk does not report its health, so no verdict can be given.",
                        "Bu disk sağlık bilgisini bildirmiyor, bu yüzden bir değerlendirme yapılamıyor."),
    "dh_t_temp": ("Temperature", "Sıcaklık"),
    "dh_t_hours": ("Powered on", "Çalışma süresi"),
    "dh_t_wear": ("Wear", "Yıpranma"),
    "dh_t_realloc": ("Reallocated sectors", "Yeniden atanan sektör"),
    "dh_t_pending": ("Pending sectors", "Bekleyen sektör"),
    "dh_t_errors": ("Uncorrected errors", "Düzeltilemeyen hata"),
    "dh_t_cycles": ("Power cycles", "Açılıp kapanma"),
    "dh_unknown": ("not reported", "bildirilmiyor"),
    "dh_pct": ("{n} %", "%{n}"),
    "dh_state_healthy": ("Healthy", "Sağlıklı"),
    "dh_state_warning": ("Warning", "Uyarı"),
    "dh_state_unhealthy": ("Unhealthy", "Sağlıksız"),
    "dh_state_unknown": ("Unknown", "Bilinmiyor"),
    "dh_state_ok": ("OK", "Çalışıyor"),
    "dh_state_degraded": ("Degraded", "Performansı düşmüş"),
    "dh_state_predictive_failure": ("Predictive failure", "Arıza öngörülüyor"),
    "dh_state_no_media": ("No media", "Ortam yok"),
    "dh_state_offline": ("Offline", "Çevrimdışı"),
    "dh_hours_fmt": ("{h} h  ({d})", "{h} sa  ({d})"),
    "dh_years": ("{n:.1f} years", "{n:.1f} yıl"),
    "dh_days": ("{n} days", "{n} gün"),
    "dh_info": ("Disk", "Disk"),
    "dh_model": ("Model", "Model"),
    "dh_serial": ("Serial number", "Seri numarası"),
    "dh_bus": ("Connection", "Bağlantı"),
    "dh_media": ("Type", "Tür"),
    "dh_capacity": ("Capacity", "Kapasite"),
    "dh_firmware": ("Firmware", "Yazılım sürümü"),
    "dh_status": ("Windows status", "Windows durumu"),
    "dh_hdd_rpm": ("Hard disk, {rpm} rpm", "Sabit disk, {rpm} dev/dk"),
    "dh_hdd": ("Hard disk", "Sabit disk"),
    "dh_ssd": ("SSD", "SSD"),
    "dh_smart": ("SMART attributes", "SMART öznitelikleri"),
    "dh_smart_none": ("This disk does not share its SMART table with Windows (normal for NVMe, RAID and most USB "
                      "enclosures).", "Bu disk SMART tablosunu Windows ile paylaşmıyor (NVMe, RAID ve çoğu USB "
                      "kutusu için normaldir)."),
    "dh_col_id": ("ID", "ID"),
    "dh_col_name": ("Attribute", "Öznitelik"),
    "dh_col_value": ("Value", "Değer"),
    "dh_col_worst": ("Worst", "En kötü"),
    "dh_col_thr": ("Threshold", "Eşik"),
    "dh_col_raw": ("Raw", "Ham"),
    "dh_findings": ("What it means", "Ne anlama geliyor"),
    "dh_recover": ("Recover files from this disk", "Bu diskten dosya kurtar"),
    "dh_system": ("system disk", "sistem diski"),
    "dh_r_predict_failure": ("The disk itself predicts that it will fail soon. Back it up now.",
                             "Disk yakında arızalanacağını kendisi bildiriyor. Hemen yedekleyin."),
    "dh_r_health_status": ("Windows reports the disk as \"{state}\".", "Windows diski \"{state}\" olarak bildiriyor."),
    "dh_r_below_threshold": ("{name} (#{id}) is at {value}, at or below its failure threshold {threshold}.",
                             "{name} (#{id}) değeri {value}; arıza eşiği olan {threshold} değerine inmiş."),
    "dh_r_pending": ("{n} sectors could not be read and are waiting to be replaced. Data in them may already be "
                     "lost, and more usually follow.",
                     "{n} sektör okunamadı ve değiştirilmeyi bekliyor. İçlerindeki veri kaybolmuş olabilir; "
                     "genellikle arkası gelir."),
    "dh_r_offline_uncorrectable": ("{n} sectors failed the disk's own surface check.",
                                   "{n} sektör diskin kendi yüzey kontrolünden geçemedi."),
    "dh_r_reported_uncorrectable": ("The disk reported {n} errors it could not correct.",
                                    "Disk düzeltemediği {n} hata bildirdi."),
    "dh_r_end_to_end": ("{n} data-path errors inside the disk's electronics.",
                        "Diskin elektroniğinde {n} veri yolu hatası var."),
    "dh_r_spin_retry": ("The motor needed {n} retries to spin up: a mechanical problem.",
                        "Motor dönmeye başlamak için {n} kez yeniden denedi: mekanik bir sorun."),
    "dh_r_reallocated": ("{n} damaged sectors were replaced with spares. The disk still works, but such numbers "
                         "tend to grow; keep a backup and check again in a few weeks.",
                         "{n} hasarlı sektör yedek sektörlerle değiştirildi. Disk hâlâ çalışıyor ama bu sayı "
                         "genellikle artar; yedek alın ve birkaç hafta sonra tekrar bakın."),
    "dh_r_crc": ("{n} transfer errors between disk and computer. Almost always the cable or the USB "
                 "enclosure, not the disk: try another cable or port.",
                 "Disk ile bilgisayar arasında {n} aktarım hatası. Neredeyse her zaman sorun kablo veya USB "
                 "kutusundadır, diskte değil: başka bir kablo ya da port deneyin."),
    "dh_r_io_errors": ("{n} read/write errors that could not be corrected.",
                       "Düzeltilemeyen {n} okuma/yazma hatası var."),
    "dh_r_worn": ("The flash is {wear}% worn: close to the end of its rated life.",
                  "Flash bellek %{wear} yıpranmış: öngörülen ömrünün sonuna yakın."),
    "dh_r_wearing": ("The flash is {wear}% worn. Fine for now; plan a replacement.",
                     "Flash bellek %{wear} yıpranmış. Şimdilik sorun yok; değişimi planlayın."),
    "dh_r_too_hot": ("{temp} °C is too hot and causes errors. Improve cooling now.",
                     "{temp} °C çok sıcak ve hatalara yol açar. Soğutmayı hemen iyileştirin."),
    "dh_r_hot": ("{temp} °C is warm. Long work at this temperature shortens its life.",
                 "{temp} °C sıcak. Bu sıcaklıkta uzun süre çalışmak ömrünü kısaltır."),
    "dh_r_all_good": ("No bad sectors, errors or warnings reported.", "Bozuk sektör, hata veya uyarı bildirilmedi."),
    "dh_r_no_smart_table": ("Only Windows' summary was available, not the detailed SMART table.",
                            "Yalnızca Windows'un özeti alınabildi, ayrıntılı SMART tablosu alınamadı."),
    "dh_r_no_data": ("The disk answered, but reported no health figures.",
                     "Disk yanıt verdi ama sağlık bilgisi bildirmedi."),
    "dh_r_no_data_usb": ("Most USB enclosures do not pass health data through. Connected directly (SATA), the "
                         "same disk usually reports everything.",
                         "Çoğu USB kutusu sağlık bilgisini geçirmez. Aynı disk doğrudan (SATA ile) bağlanınca "
                         "genellikle her şeyi bildirir."),
    "dh_r_no_data_amd_raid": ("This is an AMD RAID array: the driver hides the disks inside it from Windows. "
                              "Benchwise can show each of them (see below).",
                              "Bu bir AMD RAID dizisi: sürücü içindeki diskleri Windows'tan gizler. Benchwise her birini "
                              "ayrı ayrı gösterebilir (aşağıya bakın)."),
    "dh_r_no_data_raid": ("This is a RAID array. The controller hides the disks inside it; its own software shows "
                          "their health.", "Bu bir RAID dizisi. Denetleyici içindeki diskleri gizler; sağlıklarını "
                          "denetleyicinin kendi yazılımı gösterir."),

    "dh_r_nvme_spare_low": ("The SSD has used up its spare blocks (at or below the safe minimum). It may turn "
                            "read-only or fail. Back it up now.",
                            "SSD yedek bloklarını tüketmiş (güvenli alt sınırda veya altında). Salt okunur hale "
                            "gelebilir ya da arızalanabilir. Hemen yedekleyin."),
    "dh_r_nvme_temp_warn": ("The SSD reports that its temperature is out of its safe range.",
                            "SSD sıcaklığının güvenli aralığın dışına çıktığını bildiriyor."),
    "dh_r_nvme_degraded": ("The SSD reports that its reliability is degraded by media or internal errors.",
                           "SSD, ortam veya iç hatalar yüzünden güvenilirliğinin düştüğünü bildiriyor."),
    "dh_r_nvme_readonly": ("The SSD has switched itself to read-only to protect your data. Copy it off now.",
                           "SSD verilerinizi korumak için kendini salt okunur moda almış. Verileri hemen kopyalayın."),
    "dh_r_nvme_backup_failed": ("The SSD's power-loss protection has failed.",
                                "SSD'nin elektrik kesintisi koruması arızalanmış."),
    "dh_r_nvme_media_errors": ("{n} data integrity errors that the SSD could not correct.",
                               "SSD'nin düzeltemediği {n} veri bütünlüğü hatası var."),
    "dh_r_nvme_overheated": ("The SSD spent {n} minutes above its critical temperature.",
                             "SSD {n} dakika kritik sıcaklığının üstünde çalışmış."),
    "dh_r_nvme_unsafe": ("{n} of {of} shutdowns were unexpected (power cut, forced power-off). Each one is a small "
                         "risk for data being written at that moment.",
                         "{of} kapanışın {n} tanesi beklenmedik (elektrik kesintisi, zorla kapatma). Her biri o "
                         "anda yazılan veri için küçük bir risktir."),
    "dh_r_raid_members": ("This is a RAID array of {n} disks; each is listed separately below it.",
                          "Bu, {n} diskten oluşan bir RAID dizisi; her disk altında ayrıca listeleniyor."),
    "dh_r_raid_member_bad": ("Disk {n} in the array ({name}) is at risk.", "Dizideki {n}. disk ({name}) riskli."),
    "dh_r_raid_member_warning": ("Disk {n} in the array ({name}) needs watching.",
                                 "Dizideki {n}. disk ({name}) dikkat gerektiriyor."),
    "dh_t_spare": ("Spare blocks left", "Kalan yedek alan"),
    "dh_t_written": ("Data written", "Yazılan veri"),
    "dh_t_media": ("Media errors", "Medya hatası"),
    "dh_t_unsafe": ("Unexpected shutdowns", "Beklenmedik kapanma"),
    "dh_member_of": ("in Disk {n} · member {i}", "Disk {n} içinde · {i}. üye"),
    "dh_link": ("Link", "Bağlantı hızı"),
    "dh_used_by": ("Read through AMD_RC2t7 {v}, a third-party library by {by} ({site}). It is not part of Benchwise "
                   "and Benchwise is not responsible for it.",
                   "{by} tarafından geliştirilen üçüncü taraf kütüphane AMD_RC2t7 {v} ile okundu ({site}). Benchwise'ın "
                   "parçası değildir; Benchwise bu kütüphaneden sorumlu değildir."),
    "dh_raid_disclaimer": ("AMD_RC2t7 is not part of Benchwise. It is developed by {by} and downloaded from its official "
                           "site ({site}); its use is governed by its own license. Benchwise does not distribute or "
                           "modify it and is not responsible for it.",
                           "AMD_RC2t7, Benchwise'ın parçası değildir. {by} tarafından geliştirilir ve resmi sitesinden "
                           "({site}) indirilir; kullanımı kendi lisansına tabidir. Benchwise bu kütüphaneyi dağıtmaz, "
                           "değiştirmez ve ondan sorumlu değildir."),
    "dh_dl_download": ("Downloading from the official site: {done} of {total}", "Resmi siteden indiriliyor: {done} / {total}"),
    "dh_dl_verify": ("Checking the fingerprint (SHA-256)…", "Parmak izi (SHA-256) kontrol ediliyor…"),
    "dh_dl_signature": ("Checking the author's digital signature…", "Yazarın dijital imzası kontrol ediliyor…"),
    "dh_dl_install": ("Installing next to Benchwise…", "Benchwise'ın yanına kuruluyor…"),
    "dh_raid_title": ("Disks inside this RAID array", "Bu RAID dizisinin içindeki diskler"),
    "dh_raid_body": ("The AMD RAID driver hides the real disks from Windows. Benchwise can read each disk's health "
                     "(temperature, wear, errors) with AMD_RC2t7, a free library by Gakuto Matsumura that "
                     "CrystalDiskInfo also uses. It is downloaded once from its official site (about 200 KB), "
                     "checked against a fixed fingerprint and digital signature, and only reads.",
                     "AMD RAID sürücüsü gerçek diskleri Windows'tan gizler. Benchwise her diskin sağlığını (sıcaklık, "
                     "yıpranma, hatalar) Gakuto Matsumura'nın ücretsiz AMD_RC2t7 kütüphanesiyle okuyabilir; "
                     "CrystalDiskInfo da aynı kütüphaneyi kullanır. Kütüphane resmi sitesinden bir kez indirilir "
                     "(yaklaşık 200 KB), sabit parmak izi ve dijital imzayla doğrulanır ve yalnızca okuma yapar."),
    "dh_raid_get": ("Download and show the disks", "İndir ve diskleri göster"),
    "dh_raid_license": ("License", "Lisans"),
    "dh_raid_source_only": ("This works in Benchwise.exe only (the library must sit next to the running program).",
                            "Bu yalnızca Benchwise.exe'de çalışır (kütüphane çalışan programın yanında olmalı)."),
    "dh_raid_ask": ("Download AMD_RC2t7 {v} from its official site?\n\nSource: {url}\nDeveloper: Gakuto Matsumura\n"
                    "License: {lic}\n\nIt is checked against a fixed SHA-256 fingerprint and the author's digital "
                    "signature before it is used, and it only reads health data.\n\nThis library is not part of "
                    "Benchwise. Benchwise does not distribute or modify it and is not responsible for it; its use is "
                    "governed by its own license.",
                    "AMD_RC2t7 {v} resmi sitesinden indirilsin mi?\n\nKaynak: {url}\nGeliştirici: Gakuto Matsumura\n"
                    "Lisans: {lic}\n\nKullanılmadan önce sabit bir SHA-256 parmak iziyle ve yazarın dijital imzasıyla "
                    "doğrulanır; yalnızca sağlık bilgisini okur.\n\nBu kütüphane Benchwise'ın parçası değildir. "
                    "Benchwise onu dağıtmaz, değiştirmez ve ondan sorumlu değildir; kullanımı kendi lisansına tabidir."),
    "dh_raid_downloading": ("Downloading and checking AMD_RC2t7…", "AMD_RC2t7 indiriliyor ve doğrulanıyor…"),
    "dh_raid_failed": ("Could not set up AMD_RC2t7: {err}", "AMD_RC2t7 kurulamadı: {err}"),
    "dh_raid_read_failed": ("The disks inside the array could not be read ({err}).",
                            "Dizinin içindeki diskler okunamadı ({err})."),

    # --- next to the clock / live monitoring ---
    "dh_tray": ("By the clock", "Saatin yanında"),
    "dh_tray_raid_need": ("This RAID array reports no temperature itself. To watch the disks inside it next to "
                          "the clock, AMD_RC2t7 has to be set up first; then tick those disks one by one.",
                          "Bu RAID dizisi kendi sıcaklığını bildirmez. İçindeki diskleri saatin yanında izlemek için "
                          "önce AMD_RC2t7 kurulmalı; ardından o diskleri tek tek işaretleyin."),
    "dh_tray_no_temp_usb": ("This disk does not report its temperature: most USB enclosures do not pass it through "
                            "(connected directly by SATA, the same disk usually does).",
                            "Bu disk sıcaklığını bildirmiyor: USB kutularının çoğu bu bilgiyi geçirmez (aynı disk "
                            "doğrudan SATA ile bağlanınca genellikle bildirir)."),
    "dh_tray_no_temp": ("This disk does not report its temperature.", "Bu disk sıcaklığını bildirmiyor."),
    "dh_tray_no_temp_ask": ("Next to the clock it would show \"?\". Add it anyway?",
                            "Saatin yanında \"?\" olarak görünür. Yine de eklensin mi?"),
    "dh_tray_raid_members": ("The array itself reports no temperature. Tick the disks listed under it instead.",
                             "Dizinin kendisi sıcaklık bildirmez. Bunun yerine altında listelenen diskleri işaretleyin."),
    "dh_tray_raid_source": ("The disks inside an AMD RAID array can only be read by Benchwise.exe.",
                            "AMD RAID dizisinin içindeki diskler yalnızca Benchwise.exe ile okunabilir."),
    "tray_open": ("Open Benchwise", "Benchwise'ı aç"),
    "tray_quit": ("Quit", "Çıkış"),
    "tray_health_pct": ("Health: {pct} % · {level} · click to open", "Sağlık: %{pct} · {level} · açmak için tıklayın"),
    "dh_level_pct": ("{level} · {pct} %", "{level} · %{pct}"),
    "tc_button": ("Icon colours", "Simge renkleri"),
    "tc_title": ("Colours of the clock icons", "Saat simgelerinin renkleri"),
    "tc_hint": ("Pick a background and a digit colour for each level, so the temperature reads well on your "
                "taskbar. Changes show next to the clock at once.",
                "Her seviye için bir arka plan ve bir rakam rengi seçin; sıcaklık görev çubuğunuzda rahat okunsun. "
                "Değişiklikler saatin yanında hemen görünür."),
    "tc_good": ("Ideal", "İdeal"),
    "tc_warning": ("Warm", "Orta (sıcak)"),
    "tc_bad": ("Risky", "Riskli"),
    "tc_bg": ("Background", "Arka plan"),
    "tc_fg": ("Text", "Yazı"),
    "tc_reset": ("Back to defaults", "Varsayılana dön"),
    "tc_close": ("Done", "Tamam"),
    "live_interval": ("Temperatures by the clock every", "Saatin yanındaki sıcaklık yenilemesi"),
    "live_seconds": ("{n} s", "{n} sn"),
    "tray_health": ("Health: {level} · click to open", "Sağlık: {level} · açmak için tıklayın"),
    "tray_hidden_title": ("Benchwise keeps watching", "Benchwise izlemeye devam ediyor"),
    "tray_hidden_body": ("The disk temperatures stay next to the clock. Click one to open Benchwise; right-click "
                         "it to quit.", "Disk sıcaklıkları saatin yanında kalıyor. Benchwise'ı açmak için birine "
                         "tıklayın; kapatmak için sağ tıklayın."),
    "live_on": ("Live monitoring: on (always administrator)", "Canlı takip: açık (sürekli yönetici)"),
    "live_off": ("Live monitoring: off", "Canlı takip: kapalı"),
    "live_source_only": ("(only in Benchwise.exe)", "(yalnızca Benchwise.exe'de)"),
    "live_autostart": ("Start with Windows (next to the clock)", "Windows açılışında başlat (saatin yanında)"),
    "live_turn_on": ("Turn on live monitoring", "Canlı takibi aç"),
    "live_turn_off": ("Turn off", "Kapat"),
    "live_title": ("Live disk temperatures", "Canlı disk sıcaklıkları"),
    "live_body": ("Windows gives disk temperatures only to programs running as administrator. To show them next "
                  "to the clock all the time, Benchwise needs to always run as administrator.\n\n"
                  "Allow this once: Windows Task Scheduler will start Benchwise with administrator rights without "
                  "asking again, also when you open it yourself.",
                  "Windows disk sıcaklıklarını yalnızca yönetici olarak çalışan programlara verir. Sıcaklıkları "
                  "saatin yanında sürekli gösterebilmek için Benchwise'ın hep yönetici olarak çalışması gerekir.\n\n"
                  "Buna bir kez izin verin: Windows Görev Zamanlayıcı, Benchwise'ı bundan sonra (siz açtığınızda da) "
                  "tekrar sormadan yönetici olarak başlatır."),
    "live_autostart_long": ("Start Benchwise when Windows starts - in the background, only next to the clock",
                            "Windows açılınca Benchwise'ı başlat - arka planda, yalnızca saatin yanında"),
    "live_note": ("You can turn this off any time here in Disk Health. Benchwise does not open its window at "
                  "start; click a temperature next to the clock to bring it up.",
                  "Bunu istediğiniz zaman Disk Sağlığı'ndan kapatabilirsiniz. Benchwise açılışta penceresini "
                  "göstermez; açmak için saatin yanındaki bir sıcaklığa tıklayın."),
    "live_allow": ("Allow", "İzin ver"),
    "live_not_now": ("Not now", "Şimdilik hayır"),
    "live_failed": ("Could not change the Windows task: {err}", "Windows görevi değiştirilemedi: {err}"),
    "live_off_ask": ("Turn off live monitoring? Benchwise will no longer start with Windows and will ask for "
                     "administrator rights again when a tool needs them.",
                     "Canlı takip kapatılsın mı? Benchwise artık Windows ile başlamaz ve bir araç gerektirdiğinde "
                     "yönetici yetkisini yeniden sorar."),

    # --- update notice ---
    "up_card_title": ("New version available", "Yeni sürüm var"),
    "up_card_sub": ("Benchwise {v} · click for details", "Benchwise {v} · ayrıntılar için tıklayın"),
    "up_panel_title": ("Benchwise {v} is ready", "Benchwise {v} hazır"),
    "up_panel_sub": ("You have {cur} · released {date}", "Sizdeki sürüm {cur} · yayın tarihi {date}"),
    "up_recommend": ("We recommend updating: new versions bring fixes, safety improvements and new tools. "
                     "Your saved scans and settings are kept.",
                     "Güncellemenizi öneririz: yeni sürümler hata düzeltmeleri, güvenlik iyileştirmeleri ve yeni "
                     "araçlar getirir. Kayıtlı taramalarınız ve ayarlarınız korunur."),
    "up_notes": ("What's new", "Yenilikler"),
    "up_no_notes": ("No release notes were published for this version.", "Bu sürüm için not yayımlanmamış."),
    "up_download": ("Download the update", "Güncellemeyi indir"),
    "up_install": ("Download and install", "İndir ve yükle"),
    "up_cancel": ("Cancel", "Vazgeç"),
    "up_starting": ("Connecting to GitHub…", "GitHub'a bağlanılıyor…"),
    "up_downloading": ("Downloading: {done} of {total}", "İndiriliyor: {done} / {total}"),
    "up_installing": ("Checked (size and SHA-256 match the release). Installing…",
                      "Doğrulandı (boyut ve SHA-256 sürümle aynı). Yükleniyor…"),
    "up_restarting": ("Installed. Benchwise is restarting…", "Yüklendi. Benchwise yeniden başlatılıyor…"),
    "up_failed": ("The update was not installed: {err}. Nothing was changed.",
                  "Güncelleme yüklenmedi: {err}. Hiçbir şey değiştirilmedi."),
    "up_busy": ("A tool is still working. Installing the update restarts Benchwise and stops it.\n\nContinue?",
                "Bir araç hâlâ çalışıyor. Güncellemeyi yüklemek Benchwise'ı yeniden başlatır ve onu durdurur.\n\n"
                "Devam edilsin mi?"),
    "up_page": ("Release page", "Sürüm sayfası"),
    "up_later": ("Later", "Daha sonra"),

    # --- categories ---
    "cat_disk": ("Disk", "Disk"),
    "cat_disk_d": ("Recover, check, repair and copy disks", "Diskleri kurtarın, inceleyin, onarın ve kopyalayın"),
    "cat_system": ("System & Memory", "Sistem ve Bellek"),
    "cat_system_d": ("Hardware details, memory test, crash analysis", "Donanım bilgisi, bellek testi, çökme analizi"),
    "cat_power": ("Battery & Power", "Pil ve Güç"),
    "cat_power_d": ("Battery wear, sleep and wake problems", "Pil yıpranması, uyku ve uyanma sorunları"),
    "cat_display": ("Display & Input", "Ekran ve Giriş"),
    "cat_display_d": ("Screen, keyboard, mouse, sound and camera tests",
                      "Ekran, klavye, mouse, ses ve kamera testleri"),
    "cat_network": ("Network", "Ağ"),
    "cat_network_d": ("Find where the connection breaks, measure speed", "Bağlantının nerede koptuğunu bulun, hızı ölçün"),
    "cat_windows": ("Windows Repair", "Windows Onarımı"),
    "cat_windows_d": ("System files, updates, drivers, startup", "Sistem dosyaları, güncellemeler, sürücüler, başlangıç"),
    "cat_cleanup": ("Cleanup & Privacy", "Temizlik ve Gizlilik"),
    "cat_cleanup_d": ("Free space, duplicates, wipe what was deleted", "Yer açın, kopyaları bulun, silineni temizleyin"),

    # --- tools: disk ---
    "tool_recovery": ("File Recovery", "Dosya Kurtarma"),
    "tool_recovery_d": ("Get files back from formatted, deleted or invisible disks",
                        "Biçimlendirilmiş, silinmiş veya görünmeyen disklerden dosyaları geri getirin"),
    "tool_health": ("Disk Health", "Disk Sağlığı"),
    "tool_health_d": ("SMART values, temperature, wear and a plain verdict",
                      "SMART değerleri, sıcaklık, yıpranma ve anlaşılır bir sonuç"),
    "tool_surface": ("Surface Scan", "Yüzey Taraması"),
    "tool_surface_d": ("Read the whole disk and map slow or unreadable areas",
                       "Diskin tamamını okuyup yavaş ve okunamayan alanları haritalayın"),
    "tool_repair": ("Disk Repair", "Disk Onarımı"),
    "tool_repair_d": ("Filesystem check, boot sector and partition table repair",
                      "Dosya sistemi kontrolü, önyükleme sektörü ve bölüm tablosu onarımı"),
    "tool_image": ("Image & Clone", "İmaj ve Klonlama"),
    "tool_image_d": ("Copy a disk to an image file or to another disk", "Bir diski imaj dosyasına veya başka bir diske kopyalayın"),
    "tool_partitions": ("Partitions", "Bölümler"),
    "tool_partitions_d": ("Create, delete and format partitions; back up the table",
                          "Bölüm oluşturun, silin, biçimlendirin; tabloyu yedekleyin"),
    "tool_erase": ("Secure Erase", "Güvenli Silme"),
    "tool_erase_d": ("Wipe a disk so that nothing can be recovered", "Diski hiçbir şey kurtarılamayacak şekilde silin"),
    "tool_speed": ("Speed & Capacity Test", "Hız ve Kapasite Testi"),
    "tool_speed_d": ("Measure speed and catch fake-capacity USB sticks",
                     "Hızı ölçün ve sahte kapasiteli USB bellekleri yakalayın"),
    # --- tools: system ---
    "tool_sysinfo": ("System Information", "Sistem Bilgisi"),
    "tool_sysinfo_d": ("CPU, board, memory modules, graphics and serial numbers",
                       "İşlemci, anakart, bellek modülleri, ekran kartı ve seri numaraları"),
    "tool_memtest": ("Memory Test", "Bellek Testi"),
    "tool_memtest_d": ("Schedule the Windows memory test and read its result",
                       "Windows bellek testini planlayın ve sonucunu okuyun"),
    "tool_crash": ("Crash Analysis", "Çökme Analizi"),
    "tool_crash_d": ("Find which driver caused a blue screen", "Mavi ekrana hangi sürücünün yol açtığını bulun"),
    "tool_stress": ("CPU Stress Test", "İşlemci Stres Testi"),
    "tool_stress_d": ("Load every core and watch for errors", "Bütün çekirdekleri yükleyin ve hataları izleyin"),
    # --- tools: power ---
    "tool_battery": ("Battery Health", "Pil Sağlığı"),
    "tool_battery_d": ("Design vs. current capacity and charge cycles", "Tasarım ve mevcut kapasite, şarj döngüleri"),
    "tool_wake": ("Sleep & Wake", "Uyku ve Uyanma"),
    "tool_wake_d": ("What woke the computer, what keeps it awake", "Bilgisayarı ne uyandırdı, ne uyutmuyor"),
    # --- tools: display & input ---
    "tool_pixels": ("Dead Pixel Test", "Ölü Piksel Testi"),
    "tool_pixels_d": ("Full-screen colours to spot dead or stuck pixels", "Tam ekran renklerle ölü ve takılı pikselleri bulun"),
    "tool_keyboard": ("Keyboard Test", "Klavye Testi"),
    "tool_keyboard_d": ("Every key lights up when pressed", "Basılan her tuş ekranda yanar"),
    "tool_mouse": ("Mouse Test", "Mouse Testi"),
    "tool_mouse_d": ("Buttons, double-click faults and scrolling", "Tuşlar, çift tıklama arızası ve kaydırma"),
    "tool_audio": ("Sound Test", "Ses Testi"),
    "tool_audio_d": ("Left/right speakers and microphone", "Sol/sağ hoparlör ve mikrofon"),
    "tool_camera": ("Camera Test", "Kamera Testi"),
    "tool_camera_d": ("See what the webcam sees", "Kameranın gördüğünü izleyin"),
    # --- tools: network ---
    "tool_netdiag": ("Connection Check", "Bağlantı Kontrolü"),
    "tool_netdiag_d": ("Gateway, DNS, internet: find where it breaks", "Ağ geçidi, DNS, internet: nerede koptuğunu bulun"),
    "tool_netspeed": ("Speed & Ping", "Hız ve Ping"),
    "tool_netspeed_d": ("Download, upload, latency and route", "İndirme, yükleme, gecikme ve rota"),
    "tool_wifi": ("Wi-Fi", "Wi-Fi"),
    "tool_wifi_d": ("Nearby networks, channels and saved passwords", "Yakındaki ağlar, kanallar ve kayıtlı şifreler"),
    "tool_netreset": ("Network Reset", "Ağ Sıfırlama"),
    "tool_netreset_d": ("Flush DNS, reset Winsock and TCP/IP", "DNS önbelleği, Winsock ve TCP/IP sıfırlama"),
    # --- tools: windows ---
    "tool_sfc": ("System File Repair", "Sistem Dosyası Onarımı"),
    "tool_sfc_d": ("SFC and DISM with clear progress", "Anlaşılır ilerlemeyle SFC ve DISM"),
    "tool_update": ("Windows Update Repair", "Windows Update Onarımı"),
    "tool_update_d": ("Clear the update cache and reset its services", "Güncelleme önbelleğini temizleyip servisleri sıfırlayın"),
    "tool_drivers": ("Drivers", "Sürücüler"),
    "tool_drivers_d": ("Problem and outdated drivers, backup", "Sorunlu ve eski sürücüler, yedekleme"),
    "tool_startup": ("Startup & Services", "Başlangıç ve Servisler"),
    "tool_startup_d": ("What starts with Windows", "Windows ile birlikte neler açılıyor"),
    # --- tools: cleanup ---
    "tool_junk": ("Junk Files", "Gereksiz Dosyalar"),
    "tool_junk_d": ("Temporary files and caches", "Geçici dosyalar ve önbellekler"),
    "tool_dupes": ("Duplicate Finder", "Kopya Dosya Bulucu"),
    "tool_dupes_d": ("Files with identical content", "İçeriği aynı olan dosyalar"),
    "tool_wipefree": ("Wipe Free Space", "Boş Alanı Temizle"),
    "tool_wipefree_d": ("Make deleted files unrecoverable", "Silinmiş dosyaları kurtarılamaz hale getirin"),
    "tool_space": ("Space Analyzer", "Alan Analizi"),
    "tool_space_d": ("Which folders take up the room", "Hangi klasörler yer kaplıyor"),
})
