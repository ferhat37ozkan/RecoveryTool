"""Minimal two-language (English / Turkish) string table."""

from __future__ import annotations

import locale

_LANG = "en"

STRINGS = {
    # --- window ---
    "subtitle": ("Recover files from formatted, deleted or invisible disks - names and folder structure preserved",
                 "Biçimlendirilmiş, silinmiş veya görünmeyen disklerden dosya kurtarma - adlar ve klasör yapısı korunur"),
    "step1": ("1  Select the disk to recover from", "1  Kurtarılacak diski seçin"),
    "step2": ("2  Folder and options (the folder can also be chosen after the scan)", "2  Klasör ve seçenekler (klasör taramadan sonra da seçilebilir)"),
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


STRINGS.update({
    # --- scan first, recover what you choose ---
    "ph_save": ("Saving the scan", "Tarama kaydediliyor"),
    "log_hopeless": ("{n} entries have no readable data left and are not counted.",
                     "{n} kaydın okunabilir verisi kalmamış; hesaba katılmadı."),
    "log_oversize": ("Note: the files found add up to {total}, more than the source itself ({src}). On the disk "
                     "they occupy {unique}; {shared} of disk space is claimed by more than one entry (a deleted "
                     "file whose space was reused, older copies of the same file). Deleted entries alone are "
                     "{deleted}. You do not need that much room: untick what you do not want.",
                     "Not: bulunan dosyaların toplamı {total}; bu, kaynağın kendisinden ({src}) büyük. Diskte "
                     "kapladıkları alan {unique}; {shared} kadar disk alanını birden çok kayıt sahipleniyor "
                     "(yeri yeniden kullanılmış silinmiş dosya, aynı dosyanın eski kopyaları). Yalnızca silinmiş "
                     "kayıtlar {deleted}. Bu kadar boş yere ihtiyacınız yok: istemediklerinizin işaretini kaldırın."),
    "log_no_space": ("{n} files ({size}) did not fit into the destination. They are still waiting: free some "
                     "space or choose another folder, then recover again.",
                     "{n} dosya ({size}) hedefe sığmadı. Bekliyorlar: yer açın ya da başka bir klasör seçin, "
                     "sonra yeniden kurtarın."),
    "log_resume_scan": ("Continuing the interrupted scan from {pos}.", "Yarıda kalan tarama {pos} noktasından sürdürülüyor."),
    "log_not_saved": ("The scan could not be saved ({err}); it is kept until the program is closed.",
                      "Tarama kaydedilemedi ({err}); program kapanana kadar bellekte tutulacak."),
    "sum_no_space": ("Waiting: no room in the destination", "Bekleyen: hedefte yer kalmadı"),
    "sum_pending": ("Not recovered yet (whole scan)", "Henüz kurtarılmayan (tüm tarama)"),
    "sum_stopped": ("Stopped by the user before the end.", "Bitmeden kullanıcı tarafından durduruldu."),
    "ph_list": ("Listing the files", "Dosyalar listeleniyor"),
    "start_scan": ("Start scan", "Taramayı başlat"),
    "recover_selected": ("Recover ticked files", "Seçilenleri kurtar"),
    "pause": ("Pause", "Duraklat"),
    "resume": ("Continue", "Devam et"),
    "stop": ("Stop", "Durdur"),
    "stopping": ("Stopping…", "Durduruluyor…"),
    "new_scan": ("New scan", "Yeni tarama"),
    "scans": ("Saved scans", "Kayıtlı taramalar"),
    "panel_show": ("Live panel  ▸", "Canlı panel  ▸"),
    "panel_hide": ("Live panel  ◂", "Canlı panel  ◂"),
    "paused": ("Paused. Nothing is read or written until you continue.",
               "Duraklatıldı. Devam edene kadar hiçbir şey okunmaz ve yazılmaz."),
    "resumed": ("Continuing.", "Devam ediliyor."),
    "err_dest_for_image": ("Creating a disk image first needs a folder: choose one before starting.",
                           "Önce disk imajı almak için bir klasör gerekir: başlamadan önce bir klasör seçin."),
    "ask_resume": ("A scan of this source was stopped at {pct:.0f}% ({when}).\n\nContinue from there?\n\n"
                   "Yes: continue    No: scan again from the start",
                   "Bu kaynağın taraması %{pct:.0f} noktasında durdurulmuş ({when}).\n\nKaldığı yerden devam "
                   "edilsin mi?\n\nEvet: devam et    Hayır: baştan tara"),
    "scan_stopped": ("Scan stopped", "Tarama durduruldu"),
    "scan_stopped_note": ("The scan was stopped. Its position is saved: start a scan of the same disk again to "
                          "continue from there.",
                          "Tarama durduruldu. Kaldığı yer kaydedildi: aynı diski yeniden taramaya başlayınca "
                          "oradan devam edebilirsiniz."),
    "done_scan": ("Scan finished", "Tarama tamamlandı"),
    "scan_opened": ("Saved scan opened", "Kayıtlı tarama açıldı"),
    "loading_scan": ("Opening the saved scan…", "Kayıtlı tarama açılıyor…"),
    "err_scan_file": ("This scan file cannot be opened: {err}", "Bu tarama dosyası açılamıyor: {err}"),
    "scan_result": ("{n} recoverable files found ({size}).", "Kurtarılabilir {n} dosya bulundu ({size})."),
    "scan_progress": ("Already recovered: {done} files ({size}). Still waiting: {left}.",
                      "Daha önce kurtarılan: {done} dosya ({size}). Bekleyen: {left}."),
    "scan_saved": ("The scan is saved; you can close the program and come back to it under 'Saved scans'.",
                   "Tarama kaydedildi; programı kapatıp 'Kayıtlı taramalar'dan geri dönebilirsiniz."),
    "scan_unsaved": ("This scan could not be saved to a safe place and is lost when the program is closed.",
                     "Bu tarama güvenli bir yere kaydedilemedi; program kapanınca kaybolur."),
    "scan_next": ("Tick what you want, choose a folder and press 'Recover ticked files'. It does not have to "
                  "fit all at once.",
                  "İstediklerinizi işaretleyin, bir klasör seçin ve 'Seçilenleri kurtar'a basın. Hepsinin bir "
                  "seferde sığması gerekmez."),
    "ask_drop_scan": ("This scan is not saved. If you leave it, the disk has to be scanned again. Leave?",
                      "Bu tarama kayıtlı değil. Çıkarsanız diskin yeniden taranması gerekir. Çıkılsın mı?"),
    # --- result browser ---
    "found_title": ("Files found - tick what to recover", "Bulunan dosyalar - kurtarılacakları işaretleyin"),
    "find_label": ("Search name:", "Adda ara:"),
    "find_none": ("No file name contains this.", "Bu metni içeren dosya adı yok."),
    "select_all": ("Tick all not recovered", "Kurtarılmayanları seç"),
    "select_none": ("Untick all", "Seçimi kaldır"),
    "legend": ("green ✓ recovered    grey ○ not yet", "yeşil ✓ kurtarıldı    gri ○ henüz değil"),
    "col_file": ("Name", "Ad"),
    "col_modified": ("Modified", "Değiştirilme"),
    "recover_into": ("Recover into:", "Kurtarılacak klasör:"),
    "more_rows": ("… {n} more here; use the search box to reach them",
                  "… burada {n} tane daha var; ulaşmak için arama kutusunu kullanın"),
    "fs_folder": ("{done} / {files} recovered", "{done} / {files} kurtarıldı"),
    "fs_pending": ("Not recovered yet", "Henüz kurtarılmadı"),
    "fs_ok": ("Recovered", "Kurtarıldı"),
    "fs_warn": ("Recovered, unproven", "Kurtarıldı, kanıtlanamıyor"),
    "fs_bad": ("Recovered, damaged", "Kurtarıldı, hasarlı"),
    "fs_fail": ("Cannot be recovered", "Kurtarılamaz"),
    "m_tick": ("Tick", "İşaretle"),
    "m_untick": ("Untick", "İşareti kaldır"),
    "m_open_file": ("Open the recovered file", "Kurtarılan dosyayı aç"),
    "m_show_file": ("Show in folder", "Klasörde göster"),
    "m_details": ("Details…", "Ayrıntılar…"),
    "sel_info": ("Ticked: {n} files, {size}      Scan: {total} files, {done} recovered, {left} waiting",
                 "Seçili: {n} dosya, {size}      Tarama: {total} dosya, {done} kurtarıldı, {left} bekliyor"),
    "fit_no_dest": ("Choose the folder to recover into (on a different disk).",
                    "Kurtarılacak klasörü seçin (başka bir diskte)."),
    "fit_ok": ("Free there: {free} - everything ticked fits.", "Orada boş: {free} - seçilenlerin hepsi sığıyor."),
    "fit_partial": ("Free there: {free}, ticked: {size}. That is fine: as much as fits is recovered, the rest stays "
                    "grey and can be recovered later.",
                    "Orada boş: {free}, seçili: {size}. Sorun değil: sığdığı kadarı kurtarılır, kalanı gri kalır ve "
                    "sonra kurtarılabilir."),
    "err_nothing_ticked": ("Nothing is ticked. Tick the files or folders to recover first.",
                           "Hiçbir şey işaretli değil. Önce kurtarılacak dosya ya da klasörleri işaretleyin."),
    "space_title": ("Not everything fits", "Hepsi sığmıyor"),
    "space_body": ("Ticked: {need}. Free in the destination: {free}.\n\nRecovery goes on until the space is used "
                   "up. Finished files are marked green; what did not fit stays ticked. Move the recovered files "
                   "elsewhere (or choose another folder) and press 'Recover ticked files' again - no new scan is "
                   "needed.\n\nStart now?",
                   "Seçili: {need}. Hedefte boş: {free}.\n\nKurtarma yer bitene kadar sürer. Biten dosyalar yeşil "
                   "işaretlenir; sığmayanlar seçili kalır. Kurtarılanları başka bir yere taşıyın (ya da başka bir "
                   "klasör seçin) ve yeniden 'Seçilenleri kurtar'a basın - yeniden tarama gerekmez.\n\n"
                   "Şimdi başlansın mı?"),
    "space_after": ("{n} files ({size}) did not fit and are still ticked.\n\nMove the recovered files elsewhere or "
                    "choose another folder, then press 'Recover ticked files' again.",
                    "{n} dosya ({size}) sığmadı ve seçili duruyor.\n\nKurtarılanları başka bir yere taşıyın ya da "
                    "başka bir klasör seçin, sonra yeniden 'Seçilenleri kurtar'a basın."),
    "recover_start": ("Recovering {n} files ({size}) into {dst}", "{n} dosya ({size}) kurtarılıyor: {dst}"),
    "run_stopped": ("Recovery stopped", "Kurtarma durduruldu"),
    "run_none": ("No file was recovered in this run.", "Bu çalışmada hiçbir dosya kurtarılamadı."),
    "result_no_space": ("{n} files ({size}) did not fit into the destination and are still waiting.",
                        "{n} dosya ({size}) hedefe sığmadı; bekliyor."),
    "result_pending": ("Not recovered yet in this scan: {n} files ({size}).",
                       "Bu taramada henüz kurtarılmayan: {n} dosya ({size})."),
    "result_all_done": ("Everything recoverable in this scan has been recovered.",
                        "Bu taramadaki kurtarılabilir her şey kurtarıldı."),
    # --- live panel ---
    "panel_title": ("Live panel", "Canlı panel"),
    "ps_idle": ("Idle", "Boşta"),
    "ps_running": ("Running", "Çalışıyor"),
    "ps_paused": ("Paused", "Duraklatıldı"),
    "ps_done": ("Finished", "Tamamlandı"),
    "ps_stopped": ("Stopped", "Durduruldu"),
    "pg_progress": ("Progress", "İlerleme"),
    "pg_source": ("Source", "Kaynak"),
    "pg_scan": ("Scan findings", "Tarama bulguları"),
    "pg_recover": ("This recovery run", "Bu kurtarma"),
    "pg_catalog": ("Whole scan", "Taramanın tamamı"),
    "pg_recent": ("Last files", "Son dosyalar"),
    "pl_elapsed": ("Elapsed", "Geçen süre"),
    "pl_eta": ("Remaining (estimate)", "Kalan (tahmini)"),
    "pl_speed": ("Speed now", "Anlık hız"),
    "pl_avg": ("Average speed", "Ortalama hız"),
    "pl_data": ("Data processed", "İşlenen veri"),
    "pl_bad": ("Unreadable on source", "Kaynakta okunamayan"),
    "pl_mft": ("NTFS file records", "NTFS dosya kaydı"),
    "pl_fat": ("FAT folders", "FAT klasörü"),
    "pl_exfat": ("exFAT entries", "exFAT girdisi"),
    "pl_boot": ("Boot sectors", "Önyükleme sektörü"),
    "pl_files": ("Files handled", "İşlenen dosya"),
    "pl_ok": ("Intact", "Sorunsuz"),
    "pl_repaired": ("Repaired", "Onarılan"),
    "pl_uncertain": ("Unproven", "Belirsiz"),
    "pl_damaged": ("Damaged", "Hasarlı"),
    "pl_failed": ("Failed", "Başarısız"),
    "pl_waiting": ("Waiting for space", "Yer bekleyen"),
    "pl_free": ("Free in destination", "Hedefte boş alan"),
    "pl_total": ("Recoverable", "Kurtarılabilir"),
    "pl_done": ("Recovered", "Kurtarılan"),
    "pl_left": ("Not yet", "Bekleyen"),
    "per_s": ("/s", "/sn"),
    "pct": ("{pct:.1f}%", "%{pct:.1f}"),
    "graph_empty": ("speed", "hız"),
    "graph_peak": ("peak {speed}/s", "en yüksek {speed}/sn"),
    "vol_line": ("{fs}{label}: {files} files, {dirs} folders", "{fs}{label}: {files} dosya, {dirs} klasör"),
    "vol_none": ("no filesystem found", "dosya sistemi bulunamadı"),
    # --- saved scans ---
    "scans_title": ("Saved scans", "Kayıtlı taramalar"),
    "scans_hint": ("Every finished scan is kept here with the state of each file. Open one to recover more "
                   "from it without scanning the disk again; the disk has to be connected.",
                   "Biten her tarama, her dosyanın durumuyla birlikte burada saklanır. Diski yeniden taramadan "
                   "kurtarmaya devam etmek için birini açın; diskin bağlı olması gerekir."),
    "col_when": ("Scanned", "Tarama zamanı"),
    "col_scan_source": ("Source", "Kaynak"),
    "col_scan_files": ("Recoverable", "Kurtarılabilir"),
    "col_scan_done": ("Recovered so far", "Şimdiye dek kurtarılan"),
    "scans_none": ("No saved scan yet.", "Henüz kayıtlı tarama yok."),
    "scans_open": ("Open", "Aç"),
    "scans_delete": ("Delete", "Sil"),
    "scans_file": ("Open a scan file", "Tarama dosyası aç"),
    "scans_type": ("RecoveryTool scans", "RecoveryTool taramaları"),
    "ask_delete_scan": ("Delete this saved scan? Recovered files are not touched; only the list is removed.",
                        "Bu kayıtlı tarama silinsin mi? Kurtarılan dosyalara dokunulmaz; yalnızca liste silinir."),
    "cli_resume": ("Some files are still waiting. To recover them later without scanning again:\n"
                   "    recoverytool --resume \"{path}\" --dest <folder>",
                   "Bazı dosyalar hâlâ bekliyor. Yeniden taramadan sonra kurtarmak için:\n"
                   "    recoverytool --resume \"{path}\" --dest <klasör>"),
    "err_image_missing": ("The image file of this scan is no longer there: {path}",
                          "Bu taramanın imaj dosyası artık yerinde değil: {path}"),
    "err_disk_missing": ("The disk of this scan is not connected: {name} ({size}). Plug it in and try again.",
                         "Bu taramanın diski bağlı değil: {name} ({size}). Takıp yeniden deneyin."),
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
