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

## İsim önerme (v1.3.0) — neden Google değil, AWS

**Google Vision `web detection` denendi ve elendi.** Gerçek fotoğraflarla test edildi:
o yöntem gönderdiğin **görseli** internette arar, **yüzü** tanımaz. Kardeşinin
yayınlanmamış kareleri için dönen sonuç: `bestGuessLabels: ['human']`,
tam eşleşen görsel 0, eşleşen sayfa 0. Dar/geniş kırpma fark etmedi.
Google'ın ayrı **Celebrity Recognition** özelliği ise 16 Eylül 2025'te kaldırıldı.

**AWS Rekognition `RecognizeCelebrities`** kullanılıyor: yüzü bir kişi veritabanıyla
karşılaştırır, fotoğrafın daha önce yayınlanmış olması gerekmez.

Tasarım kararları:
- **Kişi başına 3 kare**, tüm arşiv değil — 50 kişi ≈ 150 sorgu ≈ $0.15.
- **Oy birliği**: bir isim için en az 2 karede aynı kişi + `MatchConfidence ≥ %85`.
  Tek karede çıkan ya da kareler arası çelişen eşleşmeler reddedilir.
- **Öneri ≠ isim**: `isimler.csv` içinde `onerilen_isim` ve `isim` ayrı sütunlar.
  `export` sadece `isim` sütununu okur. Onaysız hiçbir klasör isimlenmez.
- IMDb bağlantısı da saklanır (`oneriler.sayfalar`) — şüpheli öneriyi doğrulamak için.
- Kimlik: env → `~/.aws/credentials` → `aws_anahtar.json` (gitignore'da).
  IAM kullanıcısına `AmazonRekognitionReadOnlyAccess` yeterli.

Test edildi (ağa çıkmadan, taklit cevaplarla): tutarlı+yüksek güvenli öneri kabul,
tutarsız / eşik altı / tanınmayan reddedildi, öneri otomatik isme dönüşmedi.
Türkçe karakterli isimler konsola sorunsuz basıldı.

**Henüz bilinmiyor:** AWS'in kişi veritabanının Türk dizi oyuncularını ne kadar
kapsadığı. `isimlendir --limit 3` ile küçük bir denemeyle ölçülmeli.

### Gerçek veriyle ölçüm (296 fotoğraf, 11 kişi)

| küme | öneri | güven | oy |
|---|---|---|---|
| 1 | Burak Hakkı | %99.7 | 3/3 |
| 7 | Troy Glaus *(yanlış — Amerikalı beyzbolcu)* | %87.2 | 2/3 |
| diğer 9 | tanınmadı | — | — |

İki ders çıktı:

**1. AWS Türk oyuncularını biliyor.** Kapsama tam değil (11 kişiden 1'i), ama çalışıyor.

**2. Kalabalık karelerde kırpma tuzağı var — düzeltildi.** Geniş kırpma yandaki kişinin
yüzünü de içine alıyordu ve AWS *onu* tanıyıp hedef kişiye yapıştırıyordu. Küme 2'de
"Burak Hakkı" kırpmanın sol kenarında (`Left=-0.00`) bulunmuştu; ortadaki asıl yüz ise
tanınmamıştı. Artık `yuz_kirp_jpeg` hedef yüzün kırpma içindeki kutusunu da döndürüyor,
AWS'in verdiği kutuyla IoU karşılaştırılıyor (`--ortusme`, varsayılan 0.35) ve
örtüşmeyen eşleşmeler eleniyor. Düzeltmeden sonra küme 2 doğru şekilde "tanınmadı" oldu.

**Eşik `--esik` varsayılanı 95** yapıldı: doğru eşleşme %99.7, yanlış eşleşme %87.2 geldi.
Bu iki veri noktasına dayanıyor — daha çok veri gelince gözden geçirilmeli.
