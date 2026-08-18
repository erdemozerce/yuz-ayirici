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
