# Yüz Ayırıcı — Claude Code için proje notları

Bu dosyayı Claude Code her oturumda kendiliğinden okur. Projeyi devralan
oturumun bilmesi gereken her şey burada.

---

## Bu program ne yapıyor?

Bir fotoğraf arşivindeki yüzleri bulur, aynı kişileri gruplar, her kişi için
klasör açar ve o kişinin geçtiği kareleri içine kopyalar. Bir karede üç kişi
varsa o kare üç klasöre birden girer. İsimler fotoğrafın metadata'sına da
yazılabilir (ACDSee/Lightroom görür).

Her şey **bilgisayarda, çevrimdışı** çalışır. Hiçbir fotoğraf, hiçbir veri
internete gönderilmez. Bu bir tasarım kararıdır, bozulmamalı.

## Kullanıcı kim?

Türk dizilerinde çalışan bir **set fotoğrafçısı**. Bir bölüm çekiminde
yaklaşık 10.000 kare üretiyor. Fujifilm kullanıyor (RAF + JPEG), fotoğrafları
**ACDSee Ultimate** ile yönetiyor. Arşiv düzeni:

```
E:\...\8-9-10 Şubat\9. Bölüm\raw-jpeg\DSCF1234.JPG
```

**Bilgisayar ve yapay zekâ bilgisi sınırlı.** Bu yüzden:

- Türkçe ve **sade** konuş. Terim kullanma; kullanman gerekiyorsa hemen açıkla.
- "Şu komutu çalıştır" deme; mümkünse sen çalıştır ya da tıklanacak yeri tarif et.
- Ona bir şey silmesini/taşımasını söylemeden önce yedeği olduğundan emin ol.
- Hata mesajını olduğu gibi yapıştırırsa bu normaldir; suçlayıcı olma.

## Değişmez kurallar

1. **Orijinal fotoğraflara zarar verilmez.** Silinmez, taşınmaz, görüntü
   verisi değiştirilmez. Metadata yazarken bile dosya tarihi (mtime) korunur —
   yoksa program 10.000 kareyi baştan tarar (5 saat).
2. **Yazma işleminden önce onay sorulur.** Klasörleme ve metadata yazma
   öncesi kullanıcıya nereye ne yazılacağı gösterilir.
3. **İnternete veri gitmez.** Tek istisna: güncelleme kontrolü (GitHub'dan
   sürüm dosyası indirir).
4. **`yayin/` klasörü elle düzenlenmez.** `yayinla.py` üretir.

---

## Dosya haritası

| Dosya | İşi |
|---|---|
| `face_sorter.py` | Motor. 17 alt komut: `scan, cluster, birlestir, bol, cikar, onay, secki, review, tani, onayla, ogren, kisiler, etiketle, rapor, ara, teslim, export` |
| `arayuz.py` | Yerel HTTP sunucusu (127.0.0.1 + rastgele token). Arayüzün beyni. |
| `arayuz.html` | Arayüzün tamamı — tek dosya, tek `<script>` bloğu |
| `pencere.py` | pywebview ile masaüstü penceresi (Edge WebView2) |
| `kutuphane.py` | Kişi kütüphanesi: isimleri bölümler arası hatırlar |
| `etiket.py` | Metadata yazma (XMP/IPTC, MWG + ACDSee yüz bölgeleri) |
| `teslim.py` | Teslim paketi: küçültme, filigran, PDF kontak baskısı |
| `yayinla.py` | **Sürüm yayınlama.** JS sözdizimi kilidi burada. |
| `guncelle.py` | Uzaktan güncelleme (SHA-256 doğrulamalı) |
| `kur.py`, `kurulum_testi.py`, `baslat.py`, `paket_yap.py` | Kurulum ve paketleme |

**Veritabanı:** `faces.db` (SQLite). Tablolar: `files`, `faces`, `oneriler`,
`secki`, `onay`, `duzeltmeler`, `geri_al`.
**Kütüphane:** `kisi_kutuphanesi.db` — ayrı dosya, fotoğraf içermez.

Şema göçü **yalnızca `motor.db_connect()`** içinde yapılır. Veritabanına
her bağlanışta bunu kullan; ham `sqlite3.connect` kullanma (bu yüzden bir
hata çıkmıştı, aşağıda).

---

## Teknik seçimler (ölçülmüş)

- **Model:** InsightFace `buffalo_l` (ArcFace 512 boyutlu vektör), onnxruntime CPU
- **Gruplama:** DBSCAN (kosinüs, eps 0.50, min_samples 3)
- **Ölçülen ayrım:** aynı kişi ~0.75 benzerlik, farklı kişiler ~0.08 (en fazla 0.19)
- **Hız:** ~1.8 sn/kare yüksek kalitede → 10.000 kare ≈ 5 saat (bu makinede, GPU yok)

**Doğruluk (88 karelik gerçek sınav, tek kişi):**

| Ayar | Bulunan | Yanlış |
|---|---|---|
| Normal (1600 px / dedektör 640) | 80/88 = %90.9 | 0 |
| `--kalite` + `--kurtar 0.35` | **87/88 = %98.9** | **0** |

Kalan tek kare (DSCF1158) çözülemez: hedefin yüzü o karede gerçekten tespit
edilemiyor (en iyi benzerlik 0.108 — rastgele bir yüz kadar uzak).

---

## Acı deneyimle öğrenilenler — bunları tekrarlama

### 1. Bash heredoc ters bölüyü yiyor

`arayuz.html` veya `.py` dosyalarına heredoc (`<<'PY'`) ile yama uygulama.
`"\n"` gerçek satır sonuna dönüşüyor, JS dizesi ortadan kesiliyor ve
**bütün arayüz ölüyor** — hiçbir düğme çalışmıyor, görünürde hiçbir şey
yanlış değil. Bu üç kez oldu (1.12.x ve 1.20.0 yayınlandı, ikisi de bozuktu).

**Kural:** yamayı ayrı bir `.py` dosyasına yaz, sonra onu çalıştır.

### 2. `yayinla.py` yayını engelleyebilir — bu iyi bir şey

`js_kontrol()` içinde `_kapanmamis_dize()` var: dize/şablon/düzenli
ifade/yorum ayırt eden yığın tabanlı bir tarayıcı. Kişi kartları **iç içe
şablon dizesi** kullandığı için basit sayaç yetmiyor. Bu kilit yukarıdaki
hatayı yakalar. Şikâyet ederse yayınlama, düzelt.

Makinede node/deno/bun yok, o yüzden elle yazıldı.

### 3. OpenCV EXIF dönmesini zaten uyguluyor

OpenCV 5.0.0 ile ölçüldü: `imdecode` etiketi `IMREAD_COLOR` **ve**
`REDUCED_2/4/8` yollarının hepsinde uyguluyor. Ek döndürme yapma — kare iki
kez döner ve yan yatar (yan yatmış karede yüz tespiti %54-60 düşüyor).
PIL yedek yolu (HEIC) farklı: orada `ImageOps.exif_transpose` gerekli.

### 4. Metadata: az bölge yazmak çöküyordu

Fotoğrafta mevcut olandan **az** yüz bölgesi yazmak
`XMP Toolkit error 102: Indexing applied to non-array` veriyordu (3 bölgeli
dosyaya 1-2 bölge → hata; 3+ → sorunsuz). Çözüm: `_eski_bolgeleri_sil()`
yeni bölgeler yazılmadan önce eskileri siliyor. Bunu kaldırma.

### 5. ACDSee yan dosya adı

ACDSee ve Adobe `DSCF0020.xmp` bekliyor (uzantı **değiştirilir**), program
eskiden `DSCF0020.RAF.xmp` yazıyordu ve ACDSee hiç görmüyordu. `yan_dosya_yolu()`
artık `with_suffix(".xmp")` kullanıyor.

### 6. Türkçe yollar ve pyexiv2

pyexiv2 `ı ş ğ` içeren yolları açamıyor (cp1252). `etiket.acilabilir()` üç
kademeli çözüm uyguluyor: ASCII → 8.3 kısa yol → geçici kopya (mtime geri
yükleniyor). Arşivin gerçek yolu `9. Bölüm` — bu olmadan metadata özelliği
sessizce hiç çalışmazdı.

### 7. Çoklu işlem taramayı YAVAŞLATIYOR

ONNX zaten bütün çekirdekleri kullanıyor. `--isci 2` ile hız 1.14 → 0.86
foto/sn'ye düştü. Varsayılan `--isci 1`, böyle kalsın.

### 8. Arayüzde "çalışıyor ama görünmüyor" tuzağı

Dört kez oldu: iş bitiyor ama kullanıcı hiçbir şey görmüyor. Her işlemin
görünür bir sonucu olmalı (köşe bildirimi, ortadaki sonuç penceresi ya da
sayaç değişimi). Durum yoklaması 1,2 saniyede bir; aynı hatayı her seferinde
göstermemek için `sonHata` ile karşılaştırılıyor.

---

## Test etme — zorunlu asgari

Arayüzü tıklamak **yetmez**. Dosyaya yazan komutlar gerçek fotoğraflarla,
üstelik **önceden metadata'sı olan** karelerle çalıştırılmalı. İlk turda
temiz kopyalarla test ettiğim için her şey "0 hata" diyordu; hatalar ancak
gerçek arşiv kareleriyle ortaya çıktı.

Yayın öncesi en az bunlar:

```bash
python -c "import ast,glob,io; [ast.parse(io.open(f,encoding='utf-8').read()) for f in glob.glob('*.py')]"
python -c "import sys; sys.path.insert(0,'.'); import yayinla; print(yayinla.js_kontrol('arayuz.html') or 'TEMIZ')"
python kurulum_testi.py
python face_sorter.py export --db ... --dst ... --dry-run --evet    # klasörleme GERÇEKTEN çalışıyor mu
python face_sorter.py etiketle --db ... --limit 4 --evet             # metadata GERÇEKTEN yazılıyor mu
```

Son turda çalıştırılan takımlar: metadata 16, bölge yazma 15, komutlar+göç 23,
uzaktan güncelleme 14, güncelleme güvenliği 10, uçtan uca 22, arayüz 45.

---

## Yeni sürüm yayınlama

```bash
python yayinla.py 1.21.0 "Ne değişti, kısa açıklama"
git add -A && git commit -m "surum 1.21.0: ..."
git push origin main
```

`yayinla.py` sürüm numarasını `face_sorter.py` ve `surum.txt` içine yazar,
SHA-256 özetlerini hesaplar, `yayin/` klasörünü ve `surum.json` manifestini
üretir. Kullanıcı programı açtığında "yeni sürüm var" uyarısını görür.

**Yayınlamadan önce GitHub'dan indirip doğrula** — sadece "push ettim" demek
yetmez, bir kez bozuk sürüm yayınlandı:

```bash
curl -s https://raw.githubusercontent.com/erdemozerce/yuz-ayirici/main/yayin/surum.json
```

`.bat` dosyaları bilerek güncellenmez (çalışırken değiştirilmeleri Windows'ta
sorun çıkarır).

---

## Gizli bilgi kuralı

`.gitignore` şunları dışarıda tutar ve **bu böyle kalmalı**:
`*.db`, `ayarlar.json`, `isimler.csv`, `python_yolu.txt`, `yedek/`,
`google_anahtar.txt`, `aws_anahtar.json`.

Depo **herkese açık** olmalı — özel yapılırsa `raw.githubusercontent.com`
üzerinden güncelleme çalışmaz. Bu yüzden depoya asla anahtar, şifre, kişisel
fotoğraf ya da isim listesi girmemeli.

Kullanıcıdan API anahtarı, şifre ya da kart bilgisi isteme; sohbete
yapıştırırsa uyar ve iptal etmesini söyle.

---

## Bilinen sınırlar

- **Mac desteği yok.** Program Windows'a bağlı (`.bat` dosyaları, kurulum akışı).
  Diskler exFAT olduğu için Mac'te fotoğraflar okunur ama program çalışmaz.
- **GPU kullanılmıyor.** `--gpu` bayrağı var ama `onnxruntime-gpu` kurulu
  değil ve arayüzde seçenek yok. NVIDIA kartı varsa tarama ciddi kısalır.
- **Yüzü hiç tespit edilemeyen kare kurtarılamaz** (arkadan, profilden,
  hareket bulanıklığı). Kıyafet/gövde eşleştirmesi bunu çözebilir — yapılmadı.
- **Kütüphane görünümleri** peruk/sakal/dönem kostümü için çalışıyor
  (ölçüldü: 0.549 → 0.851) ama kişi başına en fazla 5 görünüm tutuyor.
