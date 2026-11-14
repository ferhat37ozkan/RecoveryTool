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
