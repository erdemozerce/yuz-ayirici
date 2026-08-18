# Yüz Ayırıcı — teknik notlar (senin için)

Kardeşinin kullanacağı kılavuz ayrı: [KARDESIM-ICIN.md](KARDESIM-ICIN.md)

## Dosyalar ne işe yarıyor

| Dosya | Kimde | Ne yapar |
|---|---|---|
| `face_sorter.py` | ikisinde | Asıl motor: `scan` / `cluster` / `review` / `export` |
| `baslat.py` | ikisinde | Menü (kardeşin komut satırı görmez) |
| `guncelle.py` | ikisinde | Uzaktan güncelleme motoru |
| `kurulum_testi.py` | ikisinde | Kurulum sonrası doğrulama + model indirme |
| `KUR.bat` | kardeşinde | Tek tıkla kurulum (Python dahil) |
| `BASLAT.bat` | kardeşinde | Programı açar |
| `GUNCELLE.bat` | kardeşinde | Elle güncelleme kontrolü |
| `yayinla.py` | **sadece sende** | Yeni sürüm yayınlar |
| `paket_yap.py` | **sadece sende** | Kurulum ZIP'i üretir |
| `yayin/` | **sadece sende** | Yayınlanan sürümün dağıtım kopyası |

## Kurulumu kardeşine gönderme

```bash
python paket_yap.py https://raw.githubusercontent.com/erdemozerce/yuz-ayirici/main/yayin/surum.json
```

Oluşan `yuz-ayirici-kurulum.zip` (~17 KB) dosyasını gönder. Kardeşin ZIP'i açıp
`KUR.bat`'a çift tıklar; Python yoksa onu bile kendi kurar (winget ile).

## Güncelleme yayınlama

Kodda bir şey değiştirdikten sonra:

```bash
python yayinla.py 1.0.3 "Ne değişti kısa açıklama"
```

Sonra `yayin/` klasörünü GitHub'a it:

```bash
git add -A && git commit -m "surum 1.0.3" && git push
```

Kardeşin programı bir sonraki açışında "YENİ SÜRÜM VAR" uyarısını görür,
"E" der ve program kendini günceller. Günde bir kez sessizce kontrol eder;
internet yoksa hiçbir şey olmaz, program normal açılır.

## Güncelleme mekanizmasının güvenliği

- **Yalnız HTTPS.** `http://` adresi kodun içinde reddediliyor.
- **SHA-256 doğrulaması.** Her dosyanın özeti `surum.json` ile karşılaştırılır;
  tek bayt oynasa güncelleme iptal edilir ve yerel dosyalara dokunulmaz.
- **Önce indir, sonra değiştir.** Dosyalar geçici klasöre inip doğrulanmadan
  hiçbir şey değiştirilmez — yarım güncelleme oluşmaz.
- **Otomatik yedek.** Eski sürüm `yedek/<sürüm>_<tarih>` klasörüne kopyalanır.
- **Dosya adı kontrolü.** Manifest'teki `..\` gibi yol denemeleri reddedilir.

Bu testlerin hepsi geçti (sahte/kurcalanmış dosya reddi dahil).

## Dikkat: satır sonları

`.gitattributes` içindeki `* -text` satırına dokunma. Git, Windows'ta LF'yi CRLF'ye
çevirirse dosya özetleri tutmaz ve kardeşindeki güncelleme "kurcalanmış dosya"
diyerek reddedilir.

## `.bat` dosyaları güncellenmiyor

`KUR.bat`, `BASLAT.bat`, `GUNCELLE.bat` bilerek güncelleme listesinin dışında —
Windows çalışan bir batch dosyasını satır satır okur, ortasından değiştirilirse
tuhaf davranır. Bunlarda değişiklik gerekirse yeni ZIP göndermek gerekir
(nadiren olur; bu dosyalar sadece Python'u bulup çağırıyor).

## Ayar ipuçları

- Aynı kişi birden çok klasöre bölündü → `cluster --eps 0.58`
- Farklı kişiler karıştı → `cluster --eps 0.42`
- Çok fazla anlamsız grup → `--min-samples 4 --min-face 60`
- Kümeleme saniyeler sürer; `scan` tekrarlanmaz, istediğin kadar dene.

## Ölçülen performans (bu makine, GPU'suz)

- Tarama: ~3.6 fotoğraf/saniye → 10.000 fotoğraf ≈ 45–90 dakika
- NVIDIA kartı olan makinede `KUR.bat` otomatik olarak GPU sürümünü kurar, 5–10 kat hızlanır.
- Doğrulama testi: 2 kişi × 5 varyant (ölçek/parlaklık/kırpma/ayna) → %100 doğru ayrım.

## Dosya sistemi davranışı (v1.1.0)

`export --mode auto` (varsayılan) hedef klasörde gerçek bir sabit bağ denemesi yapar:

| Hedef | Sonuç | Yer |
|---|---|---|
| NTFS, aynı disk | sabit bağ | ~0 |
| exFAT / FAT32 | gerçek kopya | kopya sayısı kadar |
| Farklı disk | gerçek kopya | kopya sayısı kadar |

Tahmin yürütmez, deneyip görür — yani Mac'te takılı APFS/exFAT birimlerde de doğru davranır.
Dosya sistemi adı bilgi amaçlı ayrıca okunur (Windows'ta `GetVolumeInformationW`, diğerlerinde `df -T`).

Yazmadan önce özet ekranı + onay gelir; `--evet` ile otomasyonda atlanır, `--dry-run` hiç yazmaz.
Disk alanı yetmiyorsa işlem hiç başlamaz.

## İsim hafızası — kişi kütüphanesi (v1.5.0)

Bulut tabanlı tanıma **kaldırıldı** (`tanima.py` silindi, boto3 bağımlılığı çıktı).
Yerine tamamen yerel, öğrenen bir sistem geldi: `kutuphane.py` + `kisi_kutuphanesi.db`.

**Akış:** isimlendir → kütüphane öğrenir → sonraki işte otomatik tanır → yeni kişileri sorar.
`onayla` ve `export` adımlarının sonunda kütüphane kendiliğinden güncellenir.

**Neden güvenilir — ölçülen değerler:**

| | benzerlik |
|---|---|
| Aynı kişinin yüzleri arası | ~0.75 (küme içi) |
| Farklı kişiler arası | ~0.08 (en yüksek 0.19) |
| Eşik | **0.45** |

Arada çok geniş bir boşluk var, bu yüzden eşik güvenli. Ayrıca birinci aday ikinciyi
en az `0.06` geçmeli (`--fark`); iki kişiye birden benziyorsa program isim vermez.

**İki bölüm simülasyonuyla test edildi** (296 fotoğraf ikiye bölündü, her yarı ayrı
kümelendi — küme numaraları farklı, eşleşme yalnızca yüzlere dayandı):

- Tüm kişiler öğretildiğinde: **10/10 doğru**, benzerlikler 0.95–0.99, 0 yanlış
- Yalnızca 5 kişi öğretildiğinde: **5/5 doğru tanındı, 5/5 doğru şekilde "yeni kişi"**, 0 yanlış

Kişi başına en fazla 80 örnek saklanır; sınır aşılınca açgözlü *en-uzak-nokta* seçimiyle
en **çeşitli** örnekler tutulur (farklı açı/ışık), böylece tanıma zamanla iyileşir.

**Bilinen sınır:** test aynı çekimin iki yarısıyla yapıldı (aynı gün, aynı ışık, aynı kıyafet).
Farklı bölüm/sezonda saç-sakal-ışık değişince benzerlik düşer. ArcFace bu değişimlere
dayanıklıdır ama gerçek ikinci bölüm geldiğinde `--esik` gözden geçirilmeli.
Kütüphane her onaydan sonra yeni örneklerle zenginleştiği için bu sorun kendiliğinden azalır.

## Görsel arayüz (v1.6.0)

`arayuz.py` + `arayuz.html`. Python'un kendi `http.server`'ı ile 127.0.0.1'de rastgele
bir portta çalışır, tarayıcıda açılır. **Ek kütüphane yok.**

- Yalnızca `127.0.0.1`'e bağlanır; her oturumda rastgele bir anahtar üretilir ve
  anahtarsız/yanlış anahtarlı her istek **403** döner (test edildi).
- Uzun işler `face_sorter.py` alt süreci olarak çalışır; çıktısı satır satır okunup
  `[4120/10000] 0.49 foto/sn ... kalan: 3s 20dk` deseninden ilerleme çıkarılır.
- Klasör seçme pencereleri **ana iş parçacığında** açılır (tkinter thread-safe değil):
  HTTP isteği bir kuyruğa iş bırakır, ana döngü diyaloğu açıp sonucu geri verir.
- Yüz küçük resimleri base64 JPEG olarak gömülür, dosya sunulmaz.
- `BASLAT.bat` artık arayüzü açar; eski numaralı menü `MENU.bat` olarak duruyor.

Test edildi: tüm uçlar (`/`, `/api/durum`, `/api/kisiler`), 11 kişi × 5 küçük resim,
yetkisiz erişim reddi, canlı ilerleme gösterimi.

## Çoklu kaynak + alt klasör düzeni (v1.7.0)

`scan --src` artık `nargs="+"` — birden fazla ana klasör alır, her biri alt klasörleriyle
taranır. `files` tablosuna **`kok`** sütunu eklendi (dosyanın hangi kaynak klasörden geldiği);
eski veritabanları `db_connect` içinde `ALTER TABLE` ile otomatik yükseltilir.
İç içe seçilen klasörlerde aynı dosya iki kez taranmaz.

`export --duzen` üç seçenek sunar:

| değer | sonuç |
|---|---|
| `altklasor-kisi` *(varsayılan)* | `<çıktı>/<kaynaktaki bağıl yol>/<kişi>/foto.jpg` |
| `kisi-altklasor` | `<çıktı>/<kişi>/<kaynaktaki bağıl yol>/foto.jpg` |
| `duz` | `<çıktı>/<kişi>/foto.jpg` |

`--derinlik N` bağıl yolu ilk N seviyeye kırpar (0 = tamamı). Birden fazla kaynak kökü
varsa her kökün klasör adı bağıl yolun başına eklenir — farklı disklerden gelen aynı
isimli `Bolum1` klasörleri çakışmaz.

**Kümeleme her zaman küresel kalır** — klasör bölünmesi yalnızca çıktı düzenini etkiler,
kişi kimliğini değil. Aynı kişi tüm bölümlerde aynı küme numarasını alır.

Test edildi: 2 ayrı ana klasör, 3 farklı derinlikte alt klasör, 9 fotoğraf → 2 kişi
(küresel), üç düzenin üçü de doğru ağaç üretti; arayüzden uçtan uca çalıştırıldı.

## Metadata'ya isim yazma (v1.8.0)

`etiket.py` — `pyexiv2` (exiv2 0.28) ile üç biçim birden yazılır. ExifTool binary'si
gerekmez, saf Python bağımlılığı.

| biçim | anahtar | kim okur |
|---|---|---|
| Anahtar kelime | `Xmp.dc.subject`, `Xmp.lr.hierarchicalSubject` (`People|Ad`) | herkes |
| MWG bölgeleri | `Xmp.mwg-rs.Regions/...` (`stArea`, `stDim`) | Lightroom, Bridge, digiKam, XnView |
| ACDSee bölgeleri | `Xmp.acdsee-rs.Regions/...` (`acdsee-stArea`) | ACDSee Pro/Ultimate People paneli |

**Ad alanları** ExifTool kaynağından doğrulandı: `acdsee-rs` = `http://ns.acdsee.com/regions/`,
`acdsee-stArea` = `http://ns.acdsee.com/sType/Area#`, `acdsee-stDim` = `.../Dimensions#`.
ACDSee bölge yapısında alan adları `DLYArea` (görüntülenen/manuel) ve `ALGArea`
(algoritmanın bulduğu) — ikisi de yazılıyor. Koordinatlar her iki biçimde de
**merkez noktası + genişlik/yükseklik**, 0–1 oranında.

exiv2 yapılandırılmış XMP için önce tip bildirimi ister:
`"Xmp.mwg-rs.Regions": "type=Struct"`, `".../RegionList": "type=Bag"` — bunlar olmadan
*"Indexing applied to non-array"* hatası verir.

**Doğrulanan davranışlar (test edildi):**
- Mevcut yıldız / IPTC telif / eski anahtar kelimeler korunur, yeni isim **eklenir**
- İki kez çalıştırmak aynı ismi tekrar yazmaz
- Bir karede iki kişi → iki ayrı bölge, doğru ve farklı merkez koordinatları
- `.cr2` → gömme yapılmaz, `.cr2.xmp` yan dosyası yazılır, orijinalin boyutu değişmez
- İlk N dosyada yazım sonrası piksel verisi karşılaştırılır (`--dogrula`, varsayılan 5)
- Türkçe karakterli isimler doğru yazılıp okunuyor

**Bilinmeyen:** ACDSee'nin bu bölgeleri gerçekten People panelinde gösterip
göstermediği — burada ACDSee kurulu değil. Kardeşin 20 fotoğraflık denemeyle
doğrulamalı. Anahtar kelime kısmı her koşulda çalışır.

## Akıllı Uygulama Denetimi (Smart App Control) uyumu — v1.8.1

Windows 11'in SAC'ı imzasız `.bat` dosyalarını engelliyor ve SmartScreen'in aksine
"yine de çalıştır" seçeneği **vermiyor**. SAC bir kez kapatılırsa Windows yeniden
kurulmadan geri açılamaz — yani kullanıcıdan kapatmasını istemek doğru değil.

Çözüm: `.bat` bağımlılığını kaldırmak.

- **`kur.py`** — kurulumun tamamı saf Python. `py -3 kur.py` ile çalışır;
  `python.exe` Python Software Foundation tarafından imzalıdır, SAC engellemez.
- **`KUR.bat`** artık sadece ince bir sarmalayıcı: Python'u bulur/kurar, `kur.py`'yi çağırır.
  Çalıştığı makinelerde kolaylık, çalışmadığı yerde gereksiz.
- **Masaüstü kısayolu** artık `BASLAT.bat`'ı değil, doğrudan
  `python.exe "arayuz.py"` hedefini gösteriyor — günlük kullanımda da `.bat` devrede değil.
  Doğrulandı: hedef `...\Python312\python.exe`, imza durumu `Valid`, `CN=Python Software Foundation`.
- Kılavuzdaki "Yol B": Microsoft Store'dan Python + PowerShell'e `py -3` yazıp
  `kur.py` dosyasını pencereye **sürükle-bırak** (yol yazmaya gerek kalmaz).

## RAW desteği (v1.9.0)

`rawpy` (LibRaw 0.22) ile 18 ham format. `imread_unicode` RAW uzantılarını
`raw_oku`'ya yönlendirir: **önce gömülü önizleme** (`extract_thumb`), o yoksa/küçükse
`postprocess(half_size=True)`.

Ölçüm (bu makine):

| dosya | gömülü önizleme | tam çözümleme | kazanç |
|---|---|---|---|
| Canon CR2 (6.5 MB) | **0.01 sn** → 1936×1288 | 0.20 sn | 18× |
| Nikon NEF (10.2 MB) | **0.01 sn** → 4256×2832 | 0.83 sn | 74× |

Önizlemeler tam çözünürlükte geldiği için yüz tanıma kalitesi düşmüyor.

### RAW/JPEG çifti

`raw-jpeg` klasörlerinde aynı kare iki dosya olarak durur; ikisini de taramak yüzleri
ve kişi sayılarını **iki katına çıkarırdı**. `list_images` artık `(klasör, dosya gövdesi)`
anahtarıyla gruplar; `TARAMA_ONCELIGI` ile JPEG birincil seçilir (hızlı), RAW eş olarak
`files.esler` sütununa yazılır. Export ve `etiketle` eşleri de işler:

- klasörlemede eş, birincilin yanına aynı klasöre kopyalanır/bağlanır
- metadata yazımında eşe de aynı isimler yazılır (RAW → yan `.xmp`)

Test edildi: 4 dosya (1 çift + 1 tek RAW + 1 tek JPEG) → 3 tarama, çift doğru eşleşti,
NEF sorunsuz okundu, export'ta `.cr2` JPEG'iyle aynı kişi klasörüne gitti, metadata
hem JPEG'in içine hem `.cr2.xmp` yan dosyasına yazıldı.

## Küme düzeltme (v1.10.0)

Üç işlem — `birlestir`, `bol`, `cikar` — hem komut satırında hem arayüzde.

- **birlestir**: aynı insan iki gruba bölünmüşse tek kümede toplar (en küçük numarada).
- **bol**: bir kümede iki kişi varsa `AgglomerativeClustering` (cosine, average linkage,
  `distance_threshold`) ile ayırır. En kalabalık alt grup eski numarada kalır.
- **cikar**: tek tek yanlış yüzleri kümeden çıkarır (`cluster = -1`).

**Bölme eşiği gerçek veriyle kalibre edildi.** 75 ve 41 kişilik iki küme birleştirilip
geri bölünmeye çalışıldı:

| eşik | sonuç |
|---|---|
| 0.45 | 61+14+40 — aynı kişiyi de bölüyor |
| 0.50 / 0.55 | 75+40 |
| **0.60** | **75+41 — birebir doğru** |
| 0.65 | 75+41 |

Varsayılan **0.60**. Küçültmek daha çok parçaya böler.

Düzeltmeler `duzeltmeler` tablosuna loglanır; `cluster` yeniden çalıştırılmak istenirse
"%d elle düzeltme var, hepsi silinecek" uyarısı çıkar ve onay ister (`--evet` ile atlanır).

Arayüzde: kartlarda seçim kutusu → *Seçilenleri birleştir*; her kartta *Böl* düğmesi;
yüz küçük resmine tıklayınca o yüz gruptan çıkar. `kume_ornekleri` artık yüz id'si de
döndürüyor (arayüzün "bu kişi değil" işlemi için gerekli).

## Seçki + kişi seçimi (v1.11.0)

### Tarama sırasında ölçülenler (ek maliyet yok — model zaten üretiyor)

`faces`: `netlik` (yüz bölgesinin Laplacian varyansı), `goz` (göz açıklık oranı),
`yaw`/`pitch` (poz). `files`: `imza` (dHash), `zaman` (EXIF çekim zamanı).

### Göz açıklığı — indeksler ampirik olarak bulundu

106 noktalı modelde göz halkaları **33–42 (sol)** ve **87–96 (sağ)**. Doğrulama:
aynı yüzün 10 varyantında std **0.015** (kararlı); göz bölgesi yapay olarak
%60/%35 ezildiğinde değer 0.328 → 0.261 → 0.224 (doğru yönde).

**Kişiye göre değerlendirilir.** Ölçüldü: bir kişinin normali 0.33 iken başkasınınki
0.14 olabiliyor. Mutlak eşik o kişinin *tüm* karelerini "gözü kapalı" sayardı.
Kişi başına en az 5 kare yoksa **hiç işaretlenmez** — yanlış damga vurmaktansa atlar.

### Bulanıklık — yüzde-dilim değil, mutlak taban

Yüzde-dilim kullanmak her setin %15'ini hep işaretlerdi, hepsi net olsa bile.
Mutlak taban 22 (ölçüldü: net yüz 85–135, `GaussianBlur(31)` sonrası aynı yüz 10)
ve yalnızca **120 px'ten büyük** yüzlerde iddia edilir — küçük yüzler doğal olarak
düşük değer verir.

### Seri/tekrar kare

Aynı klasörde ardışık kareler dHash farkı ≤ 8 bit ise tek grup sayılır; grup içinde
netlik + göz + poz + tespit skorundan bileşik puan hesaplanır, **en iyisi kalır**,
diğerleri `tekrar` işaretlenir. Test: 4 kareli seri + 1 ayrı kare → seri doğru
gruplandı, bulanık kare en düşük puanı aldı, en net kare seçildi.

### Kişi seçimi

`export` ve `etiketle` artık `--kisi 3 7` ve `--sadece-isimli` alıyor;
`export --secki-atla` işaretli kareleri dışarıda bırakıyor. Arayüzde kartları
işaretleyip *Sadece bunları klasörle* / *Sadece bunlara isim yaz* denebiliyor.

## Onay/veto, künye ve teslim paketi (v1.12.0)

### 5 · Oyuncu onay/veto (kill list)

`onay` komutu + `onay` tablosu. Oyuncu/ajans genelde sadece **dosya adı** gönderir
(`DSC_1234.jpg`), tam yol değil — eşleştirme hem tam yolu hem adı hem uzantısız adı
dener, eşleşmeyenleri raporlar. Vetolu kareler `export`, `etiketle` ve `teslim`
adımlarında **otomatik dışarıda kalır** (`--vetoyu-yoksay` ile zorlanabilir).
Veto kişiye özel de olabilir (`--kisi 3`) ya da tüm kişiler için.

### 6 · Künye / caption şablonu

`etiketle --kunye`. Yer tutucular: `{yapim} {bolum} {sahne} {kisiler} {dosya} {klasor}`.
Yazılan alanlar — XMP: `dc.title`, `dc.description`, `dc.creator`, `dc.rights`,
`photoshop.Headline/Credit/Source`; IPTC: `ObjectName`, `Caption`, `Byline`,
`Copyright`, `Credit`, `Source` (IPTC uzunluk sınırları uygulanır).
Ayarlar `ayarlar.json` içindeki `kunye` bloğunda ya da komut satırından.

### 7 · Teslim paketi

`teslim` komutu + `teslim.py`. Uzun kenarı küçültür, filigran basar, **metadata'yı
yeni dosyaya taşır** (yüz bölgeleri 0–1 oranlı olduğu için küçültmede geçerli kalır),
Pillow ile **PDF kontak baskısı** üretir. Aynı kişi/seçki/veto filtrelerini kullanır.
Orijinal dosyalara dokunmaz.

---

## İKİ KRİTİK DÜZELTME (v1.12.0)

### Türkçe karakterli yollar — metadata hiç yazılamıyordu

`pyexiv2`/exiv2 dosya adını işletim sisteminin ANSI kod sayfasıyla açıyor; bu makinede
`cp1252` ve Türkçe `ı/ş/ğ` harflerini **temsil edemiyor**. Denenen tüm kodlamalar
(utf-8, cp1252, mbcs, cp1254, latin-1) başarısız oldu.

Kardeşin gerçek klasörü `E:\...\8-9-10 Şubat\9. Bölüm
aw-jpeg` — yani metadata
özelliği asıl arşivde **hiç çalışmayacaktı**. Testler ASCII yollarda yapıldığı için
gözden kaçmıştı.

Çözüm — `etiket.acilabilir()` üç kademeli:
1. Yol zaten ASCII → doğrudan (maliyet yok)
2. Windows 8.3 kısa yolu (`GetShortPathNameW`) → saf ASCII (maliyet yok)
3. 8.3 kapalıysa (exFAT'te olabilir) → geçici ASCII isimli kopya, işlem sonrası geri yazılır

### Dosya tarihi değişiyordu — her tarama baştan başlardı

Metadata yazımı `mtime`'ı güncelliyordu. `scan` artımlı çalışmak için `mtime`
karşılaştırıyor; yani `etiketle` sonrası bir sonraki tarama **10.000 fotoğrafı
yeniden tarardı (5–6 saat)**. `acilabilir()` çıkışta `os.utime` ile orijinal
tarihi geri yazıyor.

İkisi de kardeşinin klasör yapısı taklit edilerek doğrulandı
(`8-9-10 Şubat/9. Bölüm/raw-jpeg/DSC_öçşğı_01.jpg` + `.cr2` yan dosyası).

## Hız — ölçümler (v1.13.0)

8 çekirdekli makinede, 40 adet ~20 MP kare ile:

| ayar | foto/sn | 10.000 kare | bulunan yüz |
|---|---|---|---|
| varsayılan (det 640 / kenar 1600) | 1.00 | 2.8 saat | 40 |
| **det 512** | **1.36** | **2.0 saat** | 40 |
| kenar 1200 | 1.20 | 2.3 saat | 40 |

**Çoklu süreç denendi ve VAZGEÇİLDİ.** 1 süreç 1.14 foto/sn, 4 süreç 0.86 foto/sn —
yani yavaşlatıyor. Sebep: ONNX Runtime tek görüntü için zaten tüm çekirdekleri
kullanıyor; süreç başına `intra_op_num_threads=1` yapınca her kare 8× yavaşlıyor ve
4 süreç bunu telafi edemiyor. `--isci` seçeneği duruyor ama varsayılanı **1**.

`--hizli` (dedektör 512) seçenek olarak eklendi, varsayılan değil: bu test setinde
yüz kaybı olmadı ama kareler büyük ve yüzler belirgindi. Kalabalık sahnelerde arka
plandaki küçük yüzler kaçabilir — kullanıcı bilerek seçmeli.

**Gerçek büyük kazanç GPU'da.** NVIDIA kartı olan makinede `KUR.bat` otomatik olarak
`onnxruntime-gpu` kuruyor; beklenen kazanç 5–10 kat.

## Arama, istatistik, yedekleme ve macOS (v1.14.0)

### 10 · Rapor ve arama

`rapor` — kişi sayıları, **kim kiminle birlikte** (birlikte görünme sayıları),
klasör dağılımı, seçki/veto özeti.
`ara --kisi Ahmet Ayse` — hepsinin birden göründüğü kareler (`--herhangi` ile
en az biri). `--dosyaya liste.txt` çıktıyı dosyaya yazar; o dosya doğrudan
`onay --dosya` ya da teslim akışına verilebilir.

### 11 · Kütüphane yedekleme / taşıma

`kisiler --disa-aktar yedek.json` / `--ice-aktar yedek.json`.
Tek JSON dosyası, yüz vektörleri base64; **fotoğraf içermez**, geri fotoğrafa
çevrilemez. İçe aktarma **birleştirir**, üzerine yazmaz — aynı isim varsa örnekler
eklenir. Test: 2 kişi dışa aktarıldı (33 KB), boş kütüphaneye yüklendi, geri
yüklenen kütüphane iki kişiyi de tanıdı.

### 9 · macOS

- `kur.py` macOS'ta `.command` başlatıcı üretir ve Masaüstüne kısayol koyar
- Klasör açma `open` ile (Windows'ta `startfile`, Linux'ta `xdg-open`)
- `etiket.acilabilir()` macOS/Linux'ta gereksiz kopyalama yapmaz — Unicode dosya
  adı sorunu yalnızca Windows'un ANSI kod sayfasında var
- Kontak baskısı fontu birden çok yolda aranıyor (macOS'ta Arial farklı konumda)

**Not:** macOS'ta test edilmedi (elimizde Mac yok). Kod platform ayrımlarını
yapıyor ama gerçek makinede denenmeli.

## Masaüstü penceresi + görsel yenileme (v1.15.0)

**`pencere.py`** — arayüz artık tarayıcıda değil, **gerçek bir uygulama penceresinde**
açılıyor. `pywebview` ile işletim sisteminin kendi görüntüleme bileşeni kullanılıyor:
Windows'ta Edge WebView2 (Win11'de yerleşik, sürüm 151 doğrulandı), macOS'ta WKWebView.
Adres çubuğu, sekme, yer imi yok; kendi görev çubuğu girişi var.

Mimari değişmedi: yerel sunucu aynı, internet yok. `arayuz.py` iki parçaya ayrıldı —
`sunucu_baslat()` (arka planda) ve `dialog_dongusu(isleyici)` (ana iş parçacığı).
Pencere modunda klasör seçimi **işletim sisteminin kendi dialogu** ile açılıyor
(`create_file_dialog`), uygulamaya bağlı olduğu için "tarayıcının arkasında kalma"
sorunu ortadan kalkıyor.

pywebview ya da WebView bileşeni yoksa program **kendini tarayıcı moduna düşürüyor**;
hiçbir işlev kaybolmuyor. `BASLAT.bat`, `ARAYUZ.bat`, masaüstü kısayolu ve macOS
`.command` dosyası artık `pencere.py`'yi açıyor.

### Görsel yenileme

Tüm id/sınıf adları korunarak yalnızca stil katmanı yenilendi (JavaScript'e dokunulmadı):
yapışkan uygulama çubuğu, adım numaraları rozet olarak başlıklara gömüldü, daha derin
renk paleti ve yumuşak gölgeler, tabular rakamlar, ilerlemede yüzde göstergesi,
kart hover davranışları, daha büyük yüz küçük resimleri, gradyanlı seçim çubuğu,
ince kaydırma çubuğu.

## Kenar menü + Kişi kütüphanesi sayfası (v1.16.0)

Arayüz üç sayfaya ayrıldı: **Çalışma** (mevcut doğrusal akış — varsayılan),
**Kişi kütüphanesi**, **Rapor**. Menü solda yapışkan; dar ekranda yatay şeride dönüşür.

### Kütüphaneye kapak resmi

`kisiler` tablosuna `kapak` BLOB sütunu eklendi (eski kütüphaneler `ALTER TABLE` ile
otomatik yükseltilir). `kutuphaneye_isle` öğretirken kümenin **merkeze en yakın**
yüzünden 140×140 JPEG kapak üretiyor (~4 KB). Kütüphane artık görsel: kimin kayıtlı
olduğu bakışta görülüyor. Yedek dosyası da kapağı taşıyor (`surum: 2`).

### Kütüphane işlemleri

`kutuphane.py`: `yeniden_adlandir` (çakışma kontrollü — aynı isim varsa birleştirmeye
yönlendiriyor), `kisi_birlestir` (örnekler birleşir, kapak korunur), `kapak_al`.
Arayüzde: kart başına *seç / yeniden adlandır / sil*, iki veya daha fazla seçilince
**birleştirme kartı** beliriyor; ayrıca *Yedek al* ve *Yedekten geri yükle*.

Uçlar: `GET /api/kutuphane`, `GET /api/rapor`, `POST /api/kutuphane-islem`
(adlandir / birlestir / sil / yedekle / geri-yukle).

### Rapor sayfası

Kişi tablosu, birlikte en çok görünen ikililer, klasör dağılımı — `cmd_rapor`'un
verdiği bilgiler arayüzde tablo olarak.
