# Building and running from source

Türkçesi [aşağıda](#kaynaktan-çalıştırma-ve-derleme).

If you only want to use the program, grab `Benchwise.exe` from the Releases page. You don't
need anything on this page.

## What you need

- Windows 10 or 11, 64-bit
- Python 3.12 (that is what the project is developed and built with)
- Git, if you want to clone instead of downloading the zip

The recovery engine has no third-party dependencies. The only package the app needs is
`customtkinter`, for the window. PyInstaller and Pillow are build-time only.

## Run from source

```powershell
git clone https://github.com/ferhat37ozkan/RecoveryTool.git
cd RecoveryTool
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

Start PowerShell as administrator before you run it. Windows does not let a normal process read
a raw disk, so without elevation the disk list still shows up but recovery will refuse to start.
Opening an image file works without elevation.

The same engine is available from the command line:

```powershell
.\.venv\Scripts\python -m benchwise --list
.\.venv\Scripts\python -m benchwise --disk 1 --dest E:\Recovered
.\.venv\Scripts\python -m benchwise --disk 1 --partition 2 --dest E:\Recovered
.\.venv\Scripts\python -m benchwise --image stick.img --dest E:\Recovered
.\.venv\Scripts\python -m benchwise --help
```

`--list` prints every disk with its partitions and unallocated space. `--partition` limits the
work to one partition, which is a lot faster than the whole disk; `--offset` and `--length` (in
bytes) do the same for any region, for example the unallocated space `--list` shows.

`--dest` has to be on a different disk than the one you are recovering. The tool checks this and
stops if it is not.

## Working on the interface without touching a disk

```powershell
$env:RECOVERYTOOL_FAKE_DISKS = "docs\demo-disks.json"
.\.venv\Scripts\python run.py
```

With that variable set the app shows the made-up disks from the JSON file, does not query any
real disk, and refuses every disk operation. It does not need an elevated prompt. Opening an
image file still works, so the whole recovery flow can be exercised this way.
`RECOVERYTOOL_LANG` (`en` or `tr`) forces the interface language.

## Build the exe

```powershell
.\build.ps1
```

If PowerShell refuses to run the script because of the execution policy:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The script creates `.venv` if it is missing, installs the requirements plus PyInstaller, and
writes `dist\Benchwise.exe` and `dist\Benchwise-cli.exe`. It prints their sizes and SHA-256
at the end. Expect about 19 MB and 8 MB and a build time of a minute or two.

Both are single files with Python and all libraries inside.

- `Benchwise.exe` is the window. It is a window application (no console window flashes up) and
  starts without administrator rights. Opening a tool marked with a shield asks to restart it as
  administrator; the elevated copy opens that tool straight away (`--open=disk.recovery`).
- `Benchwise-cli.exe` is the command line. It runs inside the terminal it is started from:
  output appears there, the terminal waits for it and Ctrl+C stops it. It does not demand
  administrator rights up front, because Windows would then run it in a new window that closes
  when it ends. `--list`, `--scans`, `--image` and `help` work in any terminal; reading a disk
  (`--disk`, `--resume` of a disk scan, `--unlock-pending`) needs an **administrator** terminal
  and says so otherwise.

```powershell
.\Benchwise-cli.exe help
.\Benchwise-cli.exe --list
.\Benchwise-cli.exe --disk 1 --partition 2 --dest E:\Recovered --debug > scan.log
```

`help` (also `-h`, `--help`, `/?`, or no arguments at all) prints every option with what it
does and examples, in Turkish or English (`--lang tr|en`, default: the Windows language).
Started with arguments, `Benchwise.exe` only shows a message pointing to the cli exe.

Two things to know before you hand the exe to someone:

- It is not code-signed. SmartScreen will show "Windows protected your PC" the first time; the
  user has to click "More info" and "Run anyway". Signing needs a certificate, which this project
  does not have.
- Some antivirus products flag PyInstaller one-file executables on principle. If that happens,
  publish the SHA-256 next to the download so people can check they have the real file.

## Tests

```powershell
.\.venv\Scripts\python tests\test_source.py        # no admin needed
.\.venv\Scripts\python tests\test_troubleshoot.py  # no admin needed
.\.venv\Scripts\python tests\test_layouts.py       # no admin needed
.\.venv\Scripts\python tests\test_scenarios.py     # needs admin, uses diskpart
```

The first three work on files and a made-up disk list. `test_layouts.py` does more if you give it
a disk image of your own (any image with a partition Windows can read):

```powershell
$env:RECOVERYTOOL_TEST_IMAGE = "D:\images\stick.img"
.\.venv\Scripts\python tests\test_layouts.py
```

It opens the image read-only and damages it in memory only: wipes the partition table, pretends
an ISO was written over it, and so on.

`test_scenarios.py` creates small virtual disks, formats them, fills them with files, wrecks
them and checks what comes back against the original hashes. It attaches and detaches virtual
disks a few dozen times. Run it on a machine you don't mind rebooting: we had one blue screen
from a RAID driver while this suite and a physical disk scan were running at the same time.

To see what the scanner finds in an image without recovering anything:

```powershell
.\.venv\Scripts\python tests\inspect_image.py stick.img
```

## Where things are when you change something

- Version number: `recoverytool\__init__.py` and `tools\version_info.txt`. Keep them in sync.
- Interface texts, English and Turkish: `recoverytool\i18n.py`. Each entry is an
  `(english, turkish)` pair.
- Icon: `tools\make_icon.py` draws it and writes `assets\icon.ico`.
- Filesystem support: one module per filesystem (`fat32.py`, `exfat.py`, `ntfs.py`). Each
  exposes `find_volumes(src, scan, log)` and returns `Volume` objects; `engine.py` does not care
  which filesystem they came from.

## Making a release

1. Bump the version in `benchwise/__init__.py` and `tools/version_info.txt`.
2. Write the release notes in `docs/release-notes/<version>.md`, in both languages (format below).
3. Run `.\build.ps1`.
4. Start the exe once and recover something from an image to make sure the build works.
5. Tag and upload:

```powershell
git tag v1.1.0
git push origin v1.1.0
gh release create v1.1.0 dist\Benchwise.exe dist\Benchwise-cli.exe --title "Benchwise 1.1.0" --notes-file docs\release-notes\1.1.0.md
```

`dist\` is in `.gitignore` on purpose. The exe goes into the release, not into the repository.

**Update notice.** A running Benchwise asks GitHub for the latest release of `REPO`
(`benchwise/__init__.py`) a few seconds after start. If its tag is newer than the running version
(not a draft or pre-release), a card with a blinking amber frame appears at the bottom right; it
opens a panel with the release notes and a download button (the release's `Benchwise.exe`). Only a
`Benchwise/<version>` user agent is sent. `BENCHWISE_NO_UPDATE_CHECK=1` turns the check off.

**Release notes format.** The panel shows the part in the user's language, tool by tool:

```markdown
<!-- tr -->
### Disk Sağlığı
- AMD RAID içindeki diskler ayrı ayrı gösteriliyor
<!-- en -->
### Disk Health
- Disks inside AMD RAID arrays are listed one by one
```

`## Türkçe` / `## English` headings work as section markers too. Notes without sections are shown
as they are.

---

# Kaynaktan çalıştırma ve derleme

Programı sadece kullanmak istiyorsanız Releases sayfasından `Benchwise.exe` dosyasını indirin.
Bu sayfadakilere ihtiyacınız yok.

## Gerekenler

- Windows 10 veya 11, 64 bit
- Python 3.12 (proje bununla geliştirilip derleniyor)
- Depoyu zip yerine klonlayacaksanız Git

Kurtarma motorunun dış bağımlılığı yok. Uygulamanın ihtiyaç duyduğu tek paket pencere için
`customtkinter`. PyInstaller ve Pillow yalnızca derleme sırasında kullanılıyor.

## Kaynaktan çalıştırma

```powershell
git clone https://github.com/ferhat37ozkan/RecoveryTool.git
cd RecoveryTool
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python run.py
```

Çalıştırmadan önce PowerShell'i yönetici olarak açın. Windows normal bir işlemin ham diski
okumasına izin vermez; yönetici değilseniz disk listesi yine görünür ama kurtarma başlamaz.
İmaj dosyası açmak için yönetici olmak gerekmez.

Aynı motor komut satırından da kullanılabilir:

```powershell
.\.venv\Scripts\python -m benchwise --list
.\.venv\Scripts\python -m benchwise --disk 1 --dest E:\Kurtarilan
.\.venv\Scripts\python -m benchwise --disk 1 --partition 2 --dest E:\Kurtarilan
.\.venv\Scripts\python -m benchwise --image bellek.img --dest E:\Kurtarilan
.\.venv\Scripts\python -m benchwise --help
```

`--list` her diski bölümleri ve ayrılmamış alanlarıyla yazar. `--partition` işi tek bir bölümle
sınırlar; tüm diske göre çok daha hızlıdır. `--offset` ve `--length` (bayt cinsinden) aynı şeyi
herhangi bir alan için yapar, örneğin `--list` çıktısındaki ayrılmamış alan için.

`--dest` kurtarılan diskten farklı bir diskte olmalı. Araç bunu kontrol eder, değilse durur.

## Hiçbir diske dokunmadan arayüz üzerinde çalışmak

```powershell
$env:RECOVERYTOOL_FAKE_DISKS = "docs\demo-disks.json"
.\.venv\Scripts\python run.py
```

Bu değişken ayarlıyken uygulama JSON dosyasındaki örnek diskleri gösterir, gerçek hiçbir diski
sorgulamaz ve bütün disk işlemlerini reddeder. Yönetici olmak gerekmez. İmaj dosyası açmak yine
çalışır; kurtarma akışının tamamı bu şekilde denenebilir. `RECOVERYTOOL_LANG` (`en` ya da `tr`)
arayüz dilini zorlar.

## Exe derleme

```powershell
.\build.ps1
```

PowerShell çalıştırma ilkesi yüzünden betiği reddederse:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Betik `.venv` yoksa oluşturur, gereksinimleri ve PyInstaller'ı kurar, `dist\Benchwise.exe`
ve `dist\Benchwise-cli.exe` dosyalarını üretir. Sonunda boyutlarını ve SHA-256 özetlerini yazar.
Yaklaşık 19 MB ve 8 MB'lık dosyalar ve bir iki dakikalık derleme süresi bekleyin.

Exe tek dosyadır; Python ve bütün kitaplıklar içindedir. Yönetici izni istemeden açılır. Kalkan
işaretli bir araç açılınca Benchwise'ı yönetici olarak yeniden başlatmayı önerir; yetkili kopya
doğrudan o araçla açılır (`--open=disk.recovery`). Komut satırı için `dist\Benchwise-cli.exe`
kullanılır.

Exe'yi birine vermeden önce bilmeniz gereken iki şey:

- Kod imzalı değil. İlk çalıştırmada SmartScreen "Windows kişisel bilgisayarınızı korudu" der;
  kullanıcının "Ek bilgi" ve "Yine de çalıştır"a basması gerekir. İmzalamak için sertifika
  lazım, projede yok.
- Bazı antivirüsler PyInstaller ile yapılmış tek dosyalık exe'leri ilke olarak işaretler. Böyle
  olursa indirme bağlantısının yanına SHA-256 özetini koyun ki insanlar doğru dosyayı
  indirdiklerini kontrol edebilsin.

## Testler

```powershell
.\.venv\Scripts\python tests\test_source.py        # yönetici gerekmez
.\.venv\Scripts\python tests\test_troubleshoot.py  # yönetici gerekmez
.\.venv\Scripts\python tests\test_layouts.py       # yönetici gerekmez
.\.venv\Scripts\python tests\test_scenarios.py     # yönetici ister, diskpart kullanır
```

İlk üçü dosyalar ve örnek disk listesi üzerinde çalışır. `test_layouts.py`, kendi disk imajınızı
verirseniz (Windows'un okuyabildiği bir bölüm içeren herhangi bir imaj) daha fazlasını sınar:

```powershell
$env:RECOVERYTOOL_TEST_IMAGE = "D:\imajlar\bellek.img"
.\.venv\Scripts\python tests\test_layouts.py
```

İmajı salt okunur açar ve yalnızca bellekte bozar: bölüm tablosunu siler, üzerine ISO yazılmış
gibi davranır vb.

`test_scenarios.py` küçük sanal diskler oluşturur, biçimlendirir, dosyalarla doldurur, bozar ve
geri gelenleri özgün özetlerle karşılaştırır. Bu sırada sanal diskleri onlarca kez takıp çıkarır.
Yeniden başlatmayı göze alabileceğiniz bir makinede çalıştırın: bu paket ile fiziksel disk
taraması aynı anda çalışırken bir RAID sürücüsü yüzünden bir kez mavi ekran aldık.

Kurtarma yapmadan, tarayıcının bir imajda ne bulduğunu görmek için:

```powershell
.\.venv\Scripts\python tests\inspect_image.py bellek.img
```

## Değişiklik yaparken neyin nerede olduğu

- Sürüm numarası: `recoverytool\__init__.py` ve `tools\version_info.txt`. İkisi aynı olmalı.
- Arayüz metinleri (İngilizce ve Türkçe): `recoverytool\i18n.py`. Her satır
  `(ingilizce, türkçe)` çiftidir.
- Simge: `tools\make_icon.py` çizer ve `assets\icon.ico` dosyasını yazar.
- Dosya sistemi desteği: her dosya sistemi için bir modül var (`fat32.py`, `exfat.py`,
  `ntfs.py`). Her biri `find_volumes(src, scan, log)` işlevini sunar ve `Volume` nesneleri
  döndürür; `engine.py` bunların hangi dosya sisteminden geldiğiyle ilgilenmez.

## Sürüm yayınlama

1. Sürüm numarasını `benchwise/__init__.py` ve `tools/version_info.txt` içinde artırın.
2. Sürüm notlarını iki dilde `docs/release-notes/<sürüm>.md` dosyasına yazın (biçim aşağıda).
3. `.\build.ps1` çalıştırın.
4. Exe'yi bir kez açıp bir imajdan kurtarma yaparak derlemenin çalıştığını görün.
5. Etiketleyip yükleyin:

```powershell
git tag v1.1.0
git push origin v1.1.0
gh release create v1.1.0 dist\Benchwise.exe dist\Benchwise-cli.exe --title "Benchwise 1.1.0" --notes-file docs\release-notes\1.1.0.md
```

`dist\` bilerek `.gitignore` içinde. Exe depoya değil, sürüme (release) eklenir.

**Güncelleme bildirimi.** Çalışan Benchwise, açıldıktan birkaç saniye sonra GitHub'dan `REPO`'nun
(`benchwise/__init__.py`) son sürümünü sorar. Etiket çalışan sürümden yeniyse (taslak veya ön sürüm
değilse) sağ altta sarı-turuncu çerçevesi yanıp sönen bir kart çıkar; kart, sürüm notlarını ve
indirme düğmesini (sürümdeki `Benchwise.exe`) gösteren bir panel açar. Yalnızca `Benchwise/<sürüm>`
tanıtıcısı gönderilir. `BENCHWISE_NO_UPDATE_CHECK=1` kontrolü kapatır.

**Sürüm notu biçimi.** Panel, kullanıcının dilindeki bölümü araç araç gösterir: her dil `<!-- tr -->`
/ `<!-- en -->` (ya da `## Türkçe` / `## English`) ile başlar, içinde `### Araç` başlıkları ve `- `
maddeleri olur. Örnek: `docs/release-notes/1.1.0.md`. Bölümsüz notlar olduğu gibi gösterilir.
