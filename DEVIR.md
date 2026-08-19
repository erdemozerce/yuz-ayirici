# Devir Notu

Projenin kardeşe devri. Bu belge **senin ve kardeşinin** okuyacağı belgedir;
Claude Code'un okuyacağı belge `CLAUDE.md`, kardeşinin kullanım kitapçığı
`KITAPCIK.md`.

Devir tarihi: 19 Ağustos 2026 · Devredilen sürüm: **1.20.3**

---

## 1. GitHub: hesap gerekiyor mu, ikiniz birden güncelleyebilir misiniz?

### Kısa cevap

- **Sadece güncelleme almak için kardeşinin GitHub hesabına gerek YOK.**
  Depo herkese açık; program dosyaları isimsiz olarak indiriyor.
- **Kendisi de değişiklik yayınlayacaksa hesap gerekiyor** (ücretsiz).
- **Evet, iki kişi aynı depoyu güncelleyebilir.** GitHub'ın normal çalışma
  biçimi budur.

### Önerim: depoyu SENDE bırak, kardeşini ortak yap

Depo şu an `erdemozerce/yuz-ayirici` adresinde ve programlar güncellemeyi
buradan alıyor. Depoyu kardeşine devredersen bu adres değişir; kurulu bütün
programların ayar dosyasını elle düzeltmek gerekir. Buna değmez.

**Yapılacak (5 dakika):**

1. Kardeşin github.com'a girip ücretsiz hesap açsın. Kullanıcı adını sana yazsın.
2. Sen şuraya git:
   `https://github.com/erdemozerce/yuz-ayirici/settings/access`
3. **Add people** → kardeşinin kullanıcı adını yaz → rolü **Write** seç → davet et.
4. Kardeşine gelen daveti kabul etsin.

Bu kadar. Artık ikiniz de değişiklik yayınlayabilirsiniz, güncelleme adresi
hiç değişmez, kardeşinin programı aynı yerden güncellenmeye devam eder.

### Elini çekmemiş olacaksın

Bu düzende:
- Kardeşin kendi Claude Code hesabıyla çalışır, kendi düzeltmelerini yayınlar
- **Sen de istediğin an aynı depoya girip düzeltme yayınlayabilirsin**
- İkinizin yaptığı her değişiklik kayıtlı (kim, ne zaman, ne değiştirdi)
- Bir şey bozulursa eski sürüme dönmek mümkün

### İkiniz aynı anda çalışırsanız

Nadiren "çakışma" olur. Basit kural: **işe başlamadan önce daima**

```bash
git pull
```

Claude Code bunu kendisi yapar zaten. Çakışma olursa Claude Code çözer.

### Yedek plan

Depo bir gün silinir ya da erişilemez olursa program çalışmaya devam eder —
sadece güncelleme alamaz. Kardeşinin bilgisayarındaki kurulum kendi başına
tamdır.

---

## 2. Kardeşin Claude Code'u kurunca ne yapmalı?

1. Claude Code'u kursun ve hesabını açsın.
2. Programın klasörünü açsın: `Desktop\yuz-ayirici`
3. Claude Code'u o klasörde başlatsın.

Claude Code `CLAUDE.md` dosyasını **kendiliğinden okur**. İçinde şunlar var:
projenin ne olduğu, kardeşinin kim olduğu ve nasıl konuşulması gerektiği,
dosya haritası, ölçülmüş sayılar, geçmişte yapılan hatalar ve yayın adımları.

Kardeşin ilk oturumda şunu yazabilir:

> "Bu klasördeki Yüz Ayırıcı programını devraldım. CLAUDE.md dosyasını oku
> ve bana programın ne yaptığını sade dille anlat."

### Kardeşinin Claude Code'a söyleyebileceği örnek istekler

- "Program taramada 5 saat sürüyor, hızlandırabilir miyiz?"
- "Rapor sayfasına şunu eklemek istiyorum..."
- "Şu hatayı alıyorum: ..." *(ekran görüntüsüyle)*
- "Bilgisayarımda ekran kartı var mı, varsa taramayı hızlandırabilir miyiz?"

---

## 3. Devredilen durum

**Sürüm 1.20.3** — GitHub'da yayında, indirilip doğrulandı.

### Doğruluk (88 karelik gerçek sınav, tek kişi)

| Ayar | Bulunan | Yanlış eşleşme |
|---|---|---|
| Normal | 80/88 = %90.9 | 0 |
| Yüksek kalite + kurtarma | **87/88 = %98.9** | **0** |

Kalan tek kare çözülemez: hedefin yüzü o karede gerçekten tespit edilemiyor.

### Hız

~1,8 sn/kare (yüksek kalite, bu makine, ekran kartı yok) → 10.000 kare ≈ 5 saat.

### Son turda düzeltilen ciddi hatalar

1. **Klasörleme 1.19.0'dan beri hiç çalışmıyordu** — "Klasörleri Oluştur"
   her seferinde çöküyordu. Kimse fark etmemişti.
2. **Metadata yazma çöküyordu** — fotoğrafta mevcut olandan az yüz bölgesi
   yazınca. Bir yüzü gruptan çıkarıp yeniden yazınca oluyordu.
3. **ACDSee yan dosyaları görmüyordu** — yanlış dosya adı biçimi. RAW
   dosyalara yazılan isimler ACDSee'de hiç görünmüyordu.
4. **Bölüm adı "raw-jpeg" çıkıyordu** — raporlarda hiçbir işe yaramıyordu.

### Test durumu

| Takım | Sonuç |
|---|---|
| Metadata yazma | 16/16 |
| Bölge yazma | 15/15 |
| Komutlar + eski veritabanı göçü | 23/23 |
| Uzaktan güncelleme | 14/14 |
| Güncelleme güvenliği | 10/10 |
| Uçtan uca (iki bölümlü arşiv) | 22/22 |
| Arayüz | 45/45 |

---

## 4. Yapılmayanlar — sıradaki adaylar

Sırası önem sırasına göre:

1. **Kıyafet/gövde eşleştirmesi.** Yüzü hiç tespit edilemeyen kareler
   (arkadan, profilden, hareket bulanıklığı) şu an kurtarılamıyor. Sette
   kostüm gün boyu sabit olduğu için gövde + renk imzasıyla eşleştirme
   alışılmadık derecede güvenilir çalışır. %98.9'u %100'e taşıyacak tek şey bu.

2. **Ekran kartı (GPU) desteği.** `--gpu` bayrağı motorda var ama
   `onnxruntime-gpu` kurulu değil ve arayüzde seçenek yok. Kardeşinin
   bilgisayarında NVIDIA kartı varsa 5 saatlik tarama ciddi kısalır.
   **İlk bakılacak şey bu** — donanımına bakmak lazım.

3. **Klavyeyle isimlendirme modu.** Tam ekran tek kişi, ok tuşlarıyla gez,
   ismi yaz, Enter. 30 kişiyi 2 dakikada isimlendirir.

4. **"Yeni bölüm ekle" tek tuş.** Parçaları var, tek akışta birleşmiş değil.

5. **Teslim dosya adı düzeni.** `Sumud_B09_AhmetYilmaz_0001.jpg` gibi —
   çoğu yapım şirketinin istediği şey. Şu an kişi adı yalnızca klasörde.

6. **Mac desteği.** Kardeşin MacBook da kullanıyor; program Windows'a bağlı.
   Tek başına diğerlerinin toplamı kadar iş.

7. **Seri çekimleri katlama.** Program benzer ardışık kareleri zaten buluyor
   ama arayüzde göstermiyor.

---

## 5. Belgeler

| Dosya | Kime |
|---|---|
| `KITAPCIK.md` | **Kardeşine** — sade dille başlangıç kitapçığı |
| `KARDESIM-ICIN.md` | Kardeşine — daha ayrıntılı kullanım kılavuzu |
| `CLAUDE.md` | Claude Code'a — proje notları, kendiliğinden okunur |
| `OKUBENI.md` | Teknik notlar, sürüm sürüm ne yapıldığı |
| `DEVIR.md` | Bu dosya |

---

## 6. Senin için hatırlatma

Bir düzeltme yayınlamak istediğinde:

```bash
git pull
python yayinla.py 1.21.0 "Ne değişti"
git add -A && git commit -m "surum 1.21.0: ..."
git push origin main
```

Sonra **mutlaka doğrula** — bir kez bozuk sürüm yayınlandı:

```bash
curl -s https://raw.githubusercontent.com/erdemozerce/yuz-ayirici/main/yayin/surum.json
```

Kardeşin programı açıp "Güncelleme var mı?" dediğinde yeni sürümü alır.
