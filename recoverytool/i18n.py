"""Minimal two-language (English / Turkish) string table."""

from __future__ import annotations

import locale

_LANG = "en"

STRINGS = {
    # --- window ---
    "subtitle": ("Recover files from formatted, deleted or invisible disks - names and folder structure preserved",
                 "Biçimlendirilmiş, silinmiş veya görünmeyen disklerden dosya kurtarma - adlar ve klasör yapısı korunur"),
    "step1": ("1  Select the disk to recover from", "1  Kurtarılacak diski seçin"),
    "step2": ("2  Select the folder to recover into", "2  Kurtarılan dosyaların yazılacağı klasörü seçin"),
    "step3": ("3  Options", "3  Seçenekler"),
    "refresh": ("Refresh", "Yenile"),
    "open_image": ("Open image file…", "İmaj dosyası aç…"),
    "browse": ("Browse…", "Gözat…"),
    "start": ("Start recovery", "Kurtarmayı başlat"),
    "cancel": ("Cancel", "İptal"),
    "cancelling": ("Cancelling…", "İptal ediliyor…"),
    "open_folder": ("Open folder", "Klasörü aç"),
    "open_report": ("Open report", "Raporu aç"),
    "col_disk": ("Disk", "Disk"),
    "col_name": ("Name / model", "Ad / model"),
    "col_bus": ("Bus", "Bağlantı"),
    "col_size": ("Size", "Boyut"),
    "col_style": ("Layout", "Düzen"),
    "col_volumes": ("Volumes", "Birimler"),
    "col_state": ("State", "Durum"),
    "state_online": ("Online", "Çevrimiçi"),
    "state_offline": ("Offline", "Çevrimdışı"),
    "state_readonly": ("Read-only", "Salt okunur"),
    "state_system": ("System disk", "Sistem diski"),
    "no_volume": ("no recognised volume", "tanınan birim yok"),
    "no_letter": ("no letter", "harf yok"),
    "image_file": ("Image file", "İmaj dosyası"),
    "dest_placeholder": ("Folder on a DIFFERENT disk", "BAŞKA bir diskteki klasör"),
    "free_space": ("Free: {free}   Disk size: {size}", "Boş alan: {free}   Disk boyutu: {size}"),
    "opt_lock": ("Write-protect the disk during recovery (released automatically when finished)",
                 "Kurtarma süresince diski yazmaya karşı kilitle (bitince otomatik açılır)"),
    "opt_deleted": ("Also recover deleted files (into a separate folder)",
                    "Silinmiş dosyaları da kurtar (ayrı bir klasöre)"),
    "opt_live": ("Also copy files that are still accessible normally",
                 "Hâlâ normal erişilebilen dosyaları da kopyala"),
    "opt_twin": ("Repair damaged files from identical copies found on the same disk",
                 "Hasarlı dosyaları aynı diskte bulunan özdeş kopyalarından onar"),
    "opt_image": ("Create a full disk image first and work on the copy (best for failing disks)",
                  "Önce diskin tam imajını al ve kopya üzerinde çalış (arızalı diskler için en güvenlisi)"),
    "lang": ("Türkçe", "English"),
    "ready": ("Ready", "Hazır"),
    "admin_needed": ("Administrator rights are required to read disks. Please restart the program as administrator.",
                     "Diskleri okumak için yönetici yetkisi gerekir. Lütfen programı yönetici olarak yeniden başlatın."),
    "pending_lock": ("Disk {n} ({name}) was left write-protected by an interrupted run. Remove the protection now?",
                     "Disk {n} ({name}) yarıda kalan bir işlem nedeniyle yazmaya karşı kilitli kalmış. Kilit şimdi kaldırılsın mı?"),
    "confirm_title": ("Start recovery?", "Kurtarma başlatılsın mı?"),
    "confirm_body": ("Source: {src}\nDestination: {dst}\n\nThe source is only read, never written to.",
                     "Kaynak: {src}\nHedef: {dst}\n\nKaynak yalnızca okunur, üzerine hiçbir şey yazılmaz."),
    "warn_system": ("This is the disk Windows is running from. It cannot be write-protected, and Windows keeps "
                    "writing to it, which can destroy recoverable data. For best results connect the disk to "
                    "another computer.\n\nContinue anyway?",
                    "Bu, Windows'un üzerinde çalıştığı disk. Yazmaya karşı kilitlenemez ve Windows üzerine yazmaya "
                    "devam ettiği için kurtarılabilir veriler zarar görebilir. En iyi sonuç için diski başka bir "
                    "bilgisayara takın.\n\nYine de devam edilsin mi?"),
    "err_select_disk": ("Select a disk first.", "Önce bir disk seçin."),
    "err_select_dest": ("Select a destination folder first.", "Önce bir hedef klasör seçin."),
    "err_same_disk": ("The destination folder is on the disk being recovered. Writing there would destroy the "
                      "data you want back. Choose a folder on a different disk.",
                      "Hedef klasör, kurtarılan diskin üzerinde. Oraya yazmak geri almak istediğiniz verileri yok "
                      "eder. Başka bir diskte bir klasör seçin."),
    "err_space": ("Not enough free space in the destination: {need} needed, {free} free.",
                  "Hedefte yeterli boş alan yok: {need} gerekli, {free} boş."),
    "err_source_lost": ("The disk stopped responding or was unplugged. Nothing was written to it. If it keeps "
                        "dropping out, the disk is failing: use the 'create a disk image first' option, or a "
                        "professional lab for irreplaceable data.",
                        "Disk yanıt vermeyi bıraktı ya da çıkarıldı. Üzerine hiçbir şey yazılmadı. Sürekli kopuyorsa "
                        "disk arızalanıyor demektir: 'önce disk imajı al' seçeneğini kullanın; yeri doldurulamaz "
                        "veriler için profesyonel laboratuvara başvurun."),
    "err_title": ("Error", "Hata"),
    "done_title": ("Recovery finished", "Kurtarma tamamlandı"),
    "cancelled": ("Cancelled by user.", "Kullanıcı tarafından iptal edildi."),
    "closing_busy": ("A recovery is running. Cancel it and exit?", "Kurtarma sürüyor. İptal edilip çıkılsın mı?"),
    # --- phases ---
    "ph_lock": ("Write-protecting the disk", "Disk yazmaya karşı kilitleniyor"),
    "ph_image": ("Creating disk image", "Disk imajı alınıyor"),
    "ph_scan": ("Scanning the disk", "Disk taranıyor"),
    "ph_analyze": ("Rebuilding folder structure", "Klasör yapısı yeniden kuruluyor"),
    "ph_recover": ("Recovering files", "Dosyalar kurtarılıyor"),
    "ph_verify": ("Verifying and repairing", "Doğrulanıyor ve onarılıyor"),
    "ph_report": ("Writing report", "Rapor yazılıyor"),
    "ph_unlock": ("Removing write protection", "Yazma koruması kaldırılıyor"),
    # --- log / summary ---
    "log_locked": ("Disk {n} is now write-protected.", "Disk {n} yazmaya karşı kilitlendi."),
    "log_lock_failed": ("Could not write-protect the disk: {err}", "Disk kilitlenemedi: {err}"),
    "log_unlocked": ("Write protection removed from disk {n}.", "Disk {n} üzerindeki yazma koruması kaldırıldı."),
    "log_unlock_failed": ("COULD NOT remove write protection from disk {n}: {err}",
                          "Disk {n} üzerindeki yazma koruması KALDIRILAMADI: {err}"),
    "log_no_lock_system": ("System disk: write protection skipped.", "Sistem diski: yazma koruması atlandı."),
    "log_scan_done": ("Scan complete: {mft} NTFS records, {fat} FAT folders, {exfat} exFAT entries, {boot} boot sectors.",
                      "Tarama bitti: {mft} NTFS kaydı, {fat} FAT klasörü, {exfat} exFAT girdisi, {boot} önyükleme sektörü."),
    "log_volume": ("Found {fs} volume: {files} files, {dirs} folders.", "{fs} birimi bulundu: {files} dosya, {dirs} klasör."),
    "log_nothing": ("No recoverable filesystem structures were found on this disk.",
                    "Bu diskte kurtarılabilir dosya sistemi yapısı bulunamadı."),
    "log_plan": ("{n} files ({size}) selected for recovery.", "{n} dosya ({size}) kurtarılmak üzere seçildi."),
    "log_bad": ("Unreadable data on the source: {size}", "Kaynakta okunamayan veri: {size}"),
    "sum_recovered": ("Files recovered", "Kurtarılan dosya"),
    "sum_ok": ("Intact", "Sorunsuz"),
    "sum_repaired": ("Repaired from identical copies", "Özdeş kopyadan onarılan"),
    "sum_uncertain": ("Recovered, integrity not provable", "Kurtarıldı, bütünlük kanıtlanamıyor"),
    "sum_damaged": ("Damaged", "Hasarlı"),
    "sum_skipped": ("Not recoverable / unsupported", "Kurtarılamayan / desteklenmeyen"),
    "sum_live_skipped": ("Still-accessible files left out", "Dışarıda bırakılan erişilebilir dosya"),
    "cat_main": ("Folder tree", "Klasör ağacı"),
    "cat_orphaned": ("Folders without a parent", "Üst klasörü bulunamayanlar"),
    "cat_deleted": ("Previously deleted files", "Önceden silinmiş dosyalar"),
    "col_ok": ("Intact", "Sorunsuz"),
    "col_repaired": ("Repaired", "Onarılan"),
    "col_uncertain": ("Unproven", "Belirsiz"),
    "col_damaged": ("Damaged", "Hasarlı"),
    "col_failed": ("Failed", "Başarısız"),
    "result_none": ("Nothing recoverable was found on this disk.", "Bu diskte kurtarılabilir bir şey bulunamadı."),
    "result_head": ("{n} files recovered ({size}) in {time}", "{n} dosya kurtarıldı ({size}), süre {time}"),
    "result_live": ("{n} files that are still normally accessible were left out (see options).",
                    "Hâlâ normal erişilebilen {n} dosya dışarıda bırakıldı (seçeneklere bakın)."),
    "result_bad": ("Warning: {size} of the source could not be read.", "Uyarı: kaynağın {size} kadarı okunamadı."),
    "loading_disks": ("Reading disk list…", "Disk listesi okunuyor…"),
    "eta": ("{pct:.1f}%   {speed}/s   about {eta} left", "%{pct:.1f}   {speed}/sn   yaklaşık {eta} kaldı"),
    "choose_dest": ("Select the folder to recover into", "Kurtarılan dosyaların yazılacağı klasörü seçin"),
    "choose_image": ("Select a disk image", "Bir disk imajı seçin"),
    "new_recovery": ("New recovery", "Yeni kurtarma"),
    "sum_size": ("Total size", "Toplam boyut"),
    "sum_time": ("Duration", "Süre"),
    "sum_dest": ("Destination", "Hedef"),
    "sum_report": ("Report", "Rapor"),
}


STRINGS.update({
    # --- disk tree ---
    "col_item": ("Disk / partition", "Disk / bölüm"),
    "col_label": ("Model / label", "Model / etiket"),
    "col_type": ("Type", "Tür"),
    "col_fs": ("Layout / FS", "Düzen / DS"),
    "partition_n": ("Partition {n}", "Bölüm {n}"),
    "unallocated": ("Unallocated", "Ayrılmamış alan"),
    "gap_hint": ("a lost partition may be here", "kayıp bölüm burada olabilir"),
    "raw_hint": ("filesystem not recognised", "dosya sistemi tanınmıyor"),
    "st_healthy": ("Healthy", "Sağlıklı"),
    "st_no_media": ("No media", "Ortam yok"),
    "st_free": ("{free} free", "{free} boş"),
    "troubleshoot": ("Troubleshoot", "Sorun giderici"),
    "sel_whole": ("whole disk", "diskin tamamı"),
    "err_demo": ("This is a demo disk list. Recovery and disk operations are disabled.",
                 "Bu bir örnek disk listesi. Kurtarma ve disk işlemleri devre dışı."),
    "busy_no_action": ("Not while a recovery is running.", "Kurtarma sürerken yapılamaz."),
    # --- context menu ---
    "m_recover_disk": ("Recover from the whole disk", "Diskin tamamından kurtar"),
    "m_recover_part": ("Recover only this partition", "Yalnızca bu bölümden kurtar"),
    "m_recover_gap": ("Search this space for a lost partition", "Bu alanda kayıp bölüm ara"),
    "m_online": ("Bring online", "Çevrimiçi yap"),
    "m_offline": ("Take offline", "Çevrimdışı yap"),
    "m_readonly_on": ("Make read-only", "Salt okunur yap"),
    "m_readonly_off": ("Remove read-only", "Salt okunuru kaldır"),
    "m_letter": ("Assign / change drive letter…", "Sürücü harfi ata / değiştir…"),
    "m_letter_remove": ("Remove drive letter", "Sürücü harfini kaldır"),
    "m_explore": ("Open in Explorer", "Gezgin'de aç"),
    "m_check": ("Check filesystem (read-only)", "Dosya sistemini denetle (salt okunur)"),
    "m_repair": ("Repair filesystem…", "Dosya sistemini onar…"),
    "m_props": ("Properties", "Özellikler"),
    "m_remove_image": ("Remove from list", "Listeden kaldır"),
    # --- dialogs ---
    "letter_title": ("Drive letter", "Sürücü harfi"),
    "letter_prompt": ("Drive letter for {name}:", "{name} için sürücü harfi:"),
    "letter_none": ("No free drive letter.", "Boş sürücü harfi yok."),
    "ok": ("OK", "Tamam"),
    "close": ("Close", "Kapat"),
    "c_offline": ("Take Disk {n} offline? Its volumes disappear from Windows until it is brought online again.",
                  "Disk {n} çevrimdışı yapılsın mı? Yeniden çevrimiçi yapılana kadar birimleri Windows'ta görünmez."),
    "c_readonly_on": ("Make Disk {n} read-only? Nothing can be written to it until this is removed.",
                      "Disk {n} salt okunur yapılsın mı? Bu kaldırılana kadar diske hiçbir şey yazılamaz."),
    "c_letter_remove": ("Remove the drive letter {letter}: from this partition? The data stays; the partition just "
                        "stops showing up in Explorer.",
                        "Bu bölümden {letter}: harfi kaldırılsın mı? Veriler yerinde kalır; bölüm yalnızca Gezgin'de "
                        "görünmez olur."),
    "c_repair": ("Repairing WRITES to the volume. Windows may delete or truncate damaged files while fixing the "
                 "filesystem, and what it changes cannot be recovered afterwards.\n\nIf there is anything on {name} "
                 "you want back, recover it first and repair afterwards.\n\nRepair now?",
                 "Onarım birime YAZAR. Windows dosya sistemini düzeltirken hasarlı dosyaları silebilir ya da "
                 "kırpabilir ve değiştirdiği şeyler sonradan kurtarılamaz.\n\n{name} üzerinde geri almak istediğiniz "
                 "bir şey varsa önce kurtarın, sonra onarın.\n\nŞimdi onarılsın mı?"),
    "act_working": ("{what}…", "{what}…"),
    "act_done": ("{what}: done.", "{what}: tamamlandı."),
    "act_failed": ("{what}: failed. {err}", "{what}: başarısız. {err}"),
    "check_clean": ("No filesystem errors found on {name}.", "{name} üzerinde dosya sistemi hatası bulunmadı."),
    "check_errors": ("Filesystem errors were found on {name}. Recover your files first, then use 'Repair filesystem'.",
                     "{name} üzerinde dosya sistemi hataları bulundu. Önce dosyalarınızı kurtarın, sonra 'Dosya "
                     "sistemini onar'ı kullanın."),
    "p_disk": ("Disk {n}\nModel: {name}\nSerial: {serial}\nConnection: {bus}\nSize: {size}\nSector size: {sector}\n"
               "Partition layout: {style}\nStatus: {status}\nHealth: {health}\nRead-only: {ro}\nOffline: {off}",
               "Disk {n}\nModel: {name}\nSeri no: {serial}\nBağlantı: {bus}\nBoyut: {size}\nSektör boyutu: {sector}\n"
               "Bölüm düzeni: {style}\nDurum: {status}\nSağlık: {health}\nSalt okunur: {ro}\nÇevrimdışı: {off}"),
    "p_part": ("Partition {n} on Disk {d}\nDrive letter: {letter}\nLabel: {label}\nFilesystem: {fs}\nType: {type}\n"
               "Size: {size}\nFree: {free}\nStarts at: {offset}\nHealth: {health}",
               "Disk {d} üzerinde Bölüm {n}\nSürücü harfi: {letter}\nEtiket: {label}\nDosya sistemi: {fs}\nTür: {type}\n"
               "Boyut: {size}\nBoş: {free}\nBaşlangıç: {offset}\nSağlık: {health}"),
    "yes": ("yes", "evet"),
    "no": ("no", "hayır"),
    # --- troubleshooter ---
    "ts_title": ("Troubleshooter - Disk {n}  {name}", "Sorun giderici - Disk {n}  {name}"),
    "ts_recheck": ("Check again", "Yeniden incele"),
    "ts_loading": ("Reading health counters…", "Sağlık sayaçları okunuyor…"),
    "ts_nothing": ("Select a disk first.", "Önce bir disk seçin."),
    "b_online": ("Bring online", "Çevrimiçi yap"),
    "b_clear_readonly": ("Remove read-only", "Salt okunuru kaldır"),
    "b_assign_letter": ("Assign a letter", "Harf ata"),
    "b_check": ("Check filesystem", "Dosya sistemini denetle"),
    "b_recover": ("Select for recovery", "Kurtarma için seç"),
    "b_recover_region": ("Select for recovery", "Kurtarma için seç"),
    "ts_healthy": ("No problems found", "Sorun bulunamadı"),
    "ts_healthy_d": ("Windows reports this disk and its volumes as healthy. If files are missing anyway, they were "
                     "probably deleted or the volume was formatted: select the disk or the partition and start a "
                     "recovery.",
                     "Windows bu diski ve birimlerini sağlıklı bildiriyor. Yine de dosyalar eksikse büyük olasılıkla "
                     "silinmiş ya da birim biçimlendirilmiştir: diski ya da bölümü seçip kurtarma başlatın."),
    "ts_no_media": ("The device answers but shows no storage", "Aygıt yanıt veriyor ama depolama alanı göstermiyor"),
    "ts_no_media_d": ("Size is 0 and Windows says 'No media'. For a card reader this just means no card is inserted. "
                      "For a USB stick or disk it means the controller cannot reach its memory: a hardware or firmware "
                      "fault. No software on this computer can fix it or read data from it. Try another port and "
                      "another computer; if it is the same there, only a recovery lab can help.",
                      "Boyut 0 ve Windows 'Ortam yok' diyor. Kart okuyucuda bu yalnızca kart takılı olmadığı anlamına "
                      "gelir. USB bellek ya da diskte ise denetleyicinin belleğine ulaşamadığını gösterir: donanım ya "
                      "da firmware arızası. Bu bilgisayardaki hiçbir yazılım bunu düzeltemez ya da veriyi okuyamaz. "
                      "Başka bir girişte ve başka bir bilgisayarda deneyin; orada da aynıysa yalnızca kurtarma "
                      "laboratuvarı yardımcı olabilir."),
    "ts_offline": ("The disk is offline", "Disk çevrimdışı"),
    "ts_offline_d": ("Windows knows the disk but keeps it offline, so its volumes are hidden. This is a setting, not "
                     "damage, and bringing it online does not change the data.",
                     "Windows diski tanıyor ama çevrimdışı tutuyor; bu yüzden birimleri gizli. Bu bir ayardır, hasar "
                     "değildir; çevrimiçi yapmak veriyi değiştirmez."),
    "ts_readonly": ("The disk is write-protected", "Disk yazmaya karşı korumalı"),
    "ts_readonly_d": ("Nothing can be written to this disk. RecoveryTool sets this during a recovery and removes it "
                      "afterwards; if a run was interrupted it can be left on. Remove it only when you are done "
                      "recovering from this disk.",
                      "Bu diske hiçbir şey yazılamaz. RecoveryTool kurtarma sırasında bunu açar ve sonunda kaldırır; "
                      "işlem yarıda kaldıysa açık kalmış olabilir. Yalnızca bu diskten kurtarma işiniz bittiyse "
                      "kaldırın."),
    "ts_unhealthy": ("Windows reports the disk as {state}", "Windows diski {state} olarak bildiriyor"),
    "ts_unhealthy_d": ("The disk itself is reporting trouble. Copy what you need off it now, before anything else. "
                       "Use the 'create a disk image first' option so the disk is read only once.",
                       "Diskin kendisi sorun bildiriyor. Başka bir şey yapmadan önce ihtiyacınız olanı hemen "
                       "kopyalayın. Disk yalnızca bir kez okunsun diye 'önce disk imajı al' seçeneğini kullanın."),
    "ts_io_errors": ("{n} uncorrectable read/write errors", "{n} düzeltilemeyen okuma/yazma hatası"),
    "ts_io_errors_d": ("The disk has sectors it can no longer read or write. This gets worse with use. Recover your "
                       "data with the image option and replace the disk.",
                       "Diskte artık okunamayan ya da yazılamayan sektörler var. Kullandıkça kötüleşir. Verinizi imaj "
                       "seçeneğiyle kurtarın ve diski değiştirin."),
    "ts_worn": ("The drive is {wear}% worn", "Sürücü %{wear} yıpranmış"),
    "ts_worn_d": ("Flash storage wears out with writes and this drive is close to its rated life. Back it up.",
                  "Flash bellek yazdıkça yıpranır ve bu sürücü ömrünün sonuna yakın. Yedeğini alın."),
    "ts_hot": ("The drive is at {temp} °C", "Sürücü {temp} °C sıcaklıkta"),
    "ts_hot_d": ("That is hot enough to cause errors. Improve cooling before a long scan.",
                 "Bu sıcaklık hatalara yol açabilir. Uzun bir taramadan önce soğutmayı iyileştirin."),
    "ts_no_partition_table": ("No partition table", "Bölüm tablosu yok"),
    "ts_no_partition_table_d": ("Windows sees the disk as empty (RAW) and will offer to initialise it. Do not: "
                                "initialising writes a new table over the old one. If the disk held data, the "
                                "filesystems are very likely still there; recover from the whole disk.",
                                "Windows diski boş (RAW) görüyor ve başlatmayı teklif edecek. Kabul etmeyin: başlatma "
                                "eski tablonun üzerine yenisini yazar. Diskte veri vardıysa dosya sistemleri büyük "
                                "olasılıkla hâlâ yerinde; diskin tamamından kurtarın."),
    "ts_partition_raw": ("Partition {n} ({name}) has no readable filesystem",
                         "Bölüm {n} ({name}) üzerinde okunabilir dosya sistemi yok"),
    "ts_partition_raw_d": ("Windows calls this RAW and asks to format it. Do not format. Usually only the boot "
                           "sector or part of the metadata is damaged and the files are still there. Select just "
                           "this partition and recover; it is much faster than scanning the whole disk.",
                           "Windows buna RAW der ve biçimlendirmek ister. Biçimlendirmeyin. Çoğu zaman yalnızca "
                           "önyükleme sektörü ya da meta verinin bir kısmı bozuktur ve dosyalar yerindedir. Yalnızca "
                           "bu bölümü seçip kurtarın; tüm diski taramaktan çok daha hızlıdır."),
    "ts_volume_unhealthy": ("Partition {n} ({name}) is reported as {state}",
                            "Bölüm {n} ({name}) {state} olarak bildiriliyor"),
    "ts_volume_unhealthy_d": ("The filesystem has errors. A read-only check tells you how bad it is without changing "
                              "anything. Recover important files before letting Windows repair it.",
                              "Dosya sisteminde hatalar var. Salt okunur denetim hiçbir şeyi değiştirmeden durumun "
                              "ciddiyetini gösterir. Windows'un onarmasına izin vermeden önce önemli dosyaları "
                              "kurtarın."),
    "ts_no_letter": ("Partition {n} ({name}, {fs}) has no drive letter", "Bölüm {n} ({name}, {fs}) için sürücü harfi yok"),
    "ts_no_letter_d": ("The filesystem is fine but without a letter it does not appear in Explorer. Assigning one "
                       "does not touch the data.",
                       "Dosya sistemi sağlam ama harfi olmadığı için Gezgin'de görünmüyor. Harf atamak veriye "
                       "dokunmaz."),
    "ts_unallocated": ("{size} of the disk is not assigned to any partition",
                       "Diskin {size} kadarı hiçbir bölüme ait değil"),
    "ts_unallocated_d": ("If a partition used to be here and vanished (deleted, or the table was overwritten), its "
                         "files are probably still in this space. Search just this space.",
                         "Burada daha önce bir bölüm vardıysa ve kaybolduysa (silindi ya da tablo ezildi), dosyaları "
                         "büyük olasılıkla hâlâ bu alandadır. Yalnızca bu alanı tarayın."),
})


def set_language(code):
    global _LANG
    _LANG = "tr" if str(code).lower().startswith("tr") else "en"


def language():
    return _LANG


def detect():
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        set_language("tr" if lang_id & 0x3FF == 0x1F else "en")
    except Exception:
        set_language((locale.getlocale()[0] or "en"))


def t(key, **kw):
    pair = STRINGS.get(key)
    if pair is None:
        return key
    text = pair[1] if _LANG == "tr" else pair[0]
    return text.format(**kw) if kw else text
