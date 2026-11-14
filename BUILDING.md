# Building and running from source

Türkçesi [aşağıda](#kaynaktan-çalıştırma-ve-derleme).

If you only want to use the program, grab `RecoveryTool.exe` from the Releases page. You don't
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
.\.venv\Scripts\python -m recoverytool.cli --list
.\.venv\Scripts\python -m recoverytool.cli --disk 1 --dest E:\Recovered
.\.venv\Scripts\python -m recoverytool.cli --image stick.img --dest E:\Recovered
.\.venv\Scripts\python -m recoverytool.cli --help
```

`--dest` has to be on a different disk than the one you are recovering. The tool checks this and
stops if it is not.

## Build the exe

```powershell
.\build.ps1
```

If PowerShell refuses to run the script because of the execution policy:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The script creates `.venv` if it is missing, installs the requirements plus PyInstaller, and
writes `dist\RecoveryTool.exe`. It prints the file size and SHA-256 at the end. Expect about
17 MB and a build time of a minute or so.

The exe is a single file with Python and all libraries inside. It asks for administrator rights
on start (that is the `--uac-admin` flag in the build script).

Two things to know before you hand the exe to someone:

- It is not code-signed. SmartScreen will show "Windows protected your PC" the first time; the
  user has to click "More info" and "Run anyway". Signing needs a certificate, which this project
  does not have.
- Some antivirus products flag PyInstaller one-file executables on principle. If that happens,
  publish the SHA-256 next to the download so people can check they have the real file.

## Tests

```powershell
.\.venv\Scripts\python tests\test_source.py       # no admin needed
.\.venv\Scripts\python tests\test_scenarios.py    # needs admin, uses diskpart
```

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

1. Bump the version in both places.
2. Run `.\build.ps1`.
3. Start the exe once and recover something from an image to make sure the build works.
4. Tag and upload:

```powershell
git tag v1.0.1
git push origin v1.0.1
gh release create v1.0.1 dist\RecoveryTool.exe --title "v1.0.1" --notes "what changed"
```

`dist\` is in `.gitignore` on purpose. The exe goes into the release, not into the repository.

---

# Kaynaktan çalıştırma ve derleme

Programı sadece kullanmak istiyorsanız Releases sayfasından `RecoveryTool.exe` dosyasını indirin.
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
.\.venv\Scripts\python -m recoverytool.cli --list
.\.venv\Scripts\python -m recoverytool.cli --disk 1 --dest E:\Kurtarilan
.\.venv\Scripts\python -m recoverytool.cli --image bellek.img --dest E:\Kurtarilan
.\.venv\Scripts\python -m recoverytool.cli --help
```

`--dest` kurtarılan diskten farklı bir diskte olmalı. Araç bunu kontrol eder, değilse durur.

## Exe derleme

```powershell
.\build.ps1
```

PowerShell çalıştırma ilkesi yüzünden betiği reddederse:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Betik `.venv` yoksa oluşturur, gereksinimleri ve PyInstaller'ı kurar, `dist\RecoveryTool.exe`
dosyasını üretir. Sonunda dosya boyutunu ve SHA-256 özetini yazar. Yaklaşık 17 MB'lık bir dosya
ve bir dakika civarı derleme süresi bekleyin.

Exe tek dosyadır; Python ve bütün kitaplıklar içindedir. Açılışta yönetici izni ister (derleme
betiğindeki `--uac-admin` bunu sağlıyor).

Exe'yi birine vermeden önce bilmeniz gereken iki şey:

- Kod imzalı değil. İlk çalıştırmada SmartScreen "Windows kişisel bilgisayarınızı korudu" der;
  kullanıcının "Ek bilgi" ve "Yine de çalıştır"a basması gerekir. İmzalamak için sertifika
  lazım, projede yok.
- Bazı antivirüsler PyInstaller ile yapılmış tek dosyalık exe'leri ilke olarak işaretler. Böyle
  olursa indirme bağlantısının yanına SHA-256 özetini koyun ki insanlar doğru dosyayı
  indirdiklerini kontrol edebilsin.

## Testler

```powershell
.\.venv\Scripts\python tests\test_source.py       # yönetici gerekmez
.\.venv\Scripts\python tests\test_scenarios.py    # yönetici ister, diskpart kullanır
```

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

1. Sürüm numarasını iki yerde de artırın.
2. `.\build.ps1` çalıştırın.
3. Exe'yi bir kez açıp bir imajdan kurtarma yaparak derlemenin çalıştığını görün.
4. Etiketleyip yükleyin:

```powershell
git tag v1.0.1
git push origin v1.0.1
gh release create v1.0.1 dist\RecoveryTool.exe --title "v1.0.1" --notes "neler değişti"
```

`dist\` bilerek `.gitignore` içinde. Exe depoya değil, sürüme (release) eklenir.
