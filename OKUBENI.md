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
python paket_yap.py https://raw.githubusercontent.com/KULLANICI/DEPO/main/yayin/surum.json
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
