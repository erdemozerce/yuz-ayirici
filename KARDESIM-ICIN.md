# Yüz Ayırıcı — Kullanım Kılavuzu

Bu program, harddiskindeki fotoğrafları tarar, her fotoğraftaki kişileri tanır ve
her kişi için ayrı bir klasör açıp o kişinin göründüğü tüm fotoğrafları içine koyar.

**Orijinal fotoğraflarına hiçbir şey olmaz.** Program hiçbir dosyayı silmez, taşımaz,
değiştirmez — sadece okur.

---

## 1. Kurulum (bir kere)

1. Gelen klasörü masaüstüne çıkar (ZIP ise sağ tık → *Tümünü ayıkla*).
2. Klasördeki **KUR.bat** dosyasına çift tıkla.
3. Siyah bir pencere açılır ve her şeyi kendi kurar. **10–20 dakika sürebilir**, kapatma.
4. "KURULUM TAMAM" yazısını görünce Enter'a bas.

Masaüstünde **Yüz Ayırıcı** kısayolu oluşur.

> Windows "bilinmeyen uygulama" uyarısı verirse: *Ek bilgi* → *Yine de çalıştır*.

---

## 2. Kullanım

Masaüstündeki **Yüz Ayırıcı** kısayoluna çift tıkla. Bir menü açılır:

| Seçenek | Ne yapar |
|---|---|
| **1** | Fotoğrafların olduğu klasörü seç (harddiskteki ana fotoğraf klasörü) |
| **2** | Kişi klasörlerinin nereye oluşturulacağını seç |
| **8** | **Önce bunu yap:** ilk 300 fotoğrafla deneme turu (~2 dakika) |
| **3** | **Asıl iş:** hepsini tara, grupla ve klasörlere ayır |

### Önerilen sıra

1. **1**'e bas, fotoğraf klasörünü seç
2. **2**'ye bas, çıktı klasörünü seç (boş bir klasör olsun, örn. `E:\Kisiler`)
3. **8**'e bas → deneme turu. Tarayıcıda bir sayfa açılır, gruplar doğru mu bak
4. İyiyse **3**'e bas ve bırak çalışsın (10.000 fotoğraf ≈ 1–2 saat)

### Yazmadan önce ne oluyor?

Program **hiçbir şeyi sormadan yazmaz**. Klasörleri oluşturmadan hemen önce:

1. "Kişi klasörleri şu konuma yazılacak: ..." diye sorar — `E` onaylar, `D` başka klasör seçtirir, `I` iptal eder.
2. Sonra bir özet ekranı gösterir: kaç klasör açılacak, kaç dosya yazılacak, ne kadar yer gerekecek, diskte ne kadar boş var.
3. Ancak sen `E` dedikten sonra yazmaya başlar.

Disk doluysa hiç başlamaz, uyarıp durur.

### Disk formatı fark eder mi?

Hayır, kendisi anlar:

- **exFAT** disk (Windows + Mac birlikte kullanılan) → fotoğrafların **gerçek kopyası** oluşturulur. Bir fotoğrafta 3 kişi varsa 3 kopya olur, yer kaplar. Özet ekranı ne kadar yer gerektiğini önceden söyler.
- **NTFS** disk (sadece Windows) → **sabit bağ** kullanılır, fotoğraflar klasörlerde görünür ama neredeyse hiç yer kaplamaz.

Programa bir şey ayarlaman gerekmez, hedef diski görüp doğru yöntemi kendi seçer.

Program çalışırken bilgisayarı kullanabilirsin, sadece biraz yavaşlar.
Yarıda kesilirse sorun değil — tekrar **3**'e bastığında kaldığı yerden devam eder.

---

## 3. Kişilere isim vermek

İş bittiğinde klasörler `kisi_0001`, `kisi_0002` diye isimlenir.

Gerçek isim vermek istersen program klasöründeki **isimler.csv** dosyasını Excel'de aç:

| kume_no | fotograf_sayisi | isim |
|---|---|---|
| 1 | 312 | *(buraya yaz)* |
| 2 | 289 | *(buraya yaz)* |

Kimin kim olduğunu görmek için menüden **6**'ya bas — her grubun örnek yüzlerini
gösteren bir sayfa açılır. İsimleri yazıp kaydet, sonra menüden **7**'ye bas.
Klasörler `0001_Ahmet`, `0002_Ayşe` şeklinde yeniden oluşur.

---

## 4. Gruplar yanlış çıkarsa

Menüden **5**'e bas ve şu ayarı değiştir:

- **Aynı kişi birkaç klasöre bölünmüş** → sayıyı **büyüt**: `0.58`
- **Farklı kişiler aynı klasöre karışmış** → sayıyı **küçült**: `0.42`

Bu adım saniyeler sürer, baştan tarama gerekmez. İstediğin kadar dene,
sonra **6** ile sonucu kontrol et.

---

## 5. Güncellemeler

Program her açılışta yeni sürüm var mı diye bakar. Varsa sorar, "E" dersen
kendini günceller. İstersen **GUNCELLE.bat** ile elle de kontrol edebilirsin.
Güncellemeden önce eski dosyalar `yedek` klasörüne kopyalanır.

---

## Bir sorun olursa

Ekranın fotoğrafını çek ve abine gönder. Program klasöründeki `ayarlar.json`
ve `surum.txt` dosyaları da işine yarar.
