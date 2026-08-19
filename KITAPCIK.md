# Yüz Ayırıcı — Başlangıç Kitapçığı

Bu kitapçık, bilgisayarla arası çok iyi olmayan biri için yazıldı. Acele
etme, sırayla oku. Yanlış bir şey yapıp programı bozman **mümkün değil** —
fotoğraflarına da hiçbir şey olmaz.

---

## En önce bilmen gereken üç şey

**1. Fotoğraflarına asla zarar gelmez.**
Program fotoğraflarını silmez, taşımaz, bozmaz. Sadece *okur* ve *kopyalar*.
Bir şey ters giderse orijinaller yerinde durur.

**2. Hiçbir şey internete gitmiyor.**
Fotoğraflar bilgisayarından çıkmıyor. Program interneti sadece "yeni sürüm
var mı" diye bakmak için kullanıyor.

**3. Yazma işleminden önce sana soruyor.**
Program kendi kendine bir şey yazmaz. Klasör oluşturmadan ya da fotoğrafın
içine isim yazmadan önce "şuraya şunu yazacağım, onaylıyor musun?" diye
sorar.

---

## 1. Programı açmak

Masaüstündeki **Yüz Ayırıcı** simgesine çift tıkla.

Bir pencere açılır. Üstte program adı, solda menü, ortada yapacağın işler
var. İlk açılışta biraz beklemesi normal (yaklaşık 10 saniye).

> **Açılmazsa:** bilgisayarı kapatıp aç, tekrar dene. Yine olmazsa
> abine yaz: "program açılmıyor" de, ekranın fotoğrafını çek.

---

## 2. Fotoğrafların nerede olduğunu göstermek

Sol menüde **Çalışma** yazan yerdesin.

1. **Fotoğraflar** kutusunu bul.
2. **+ Klasör ekle** düğmesine bas.
3. Fotoğrafların olduğu klasörü seç. Örneğin:
   `E:\Sumud Yedek\8-9-10 Şubat\9. Bölüm`
4. **Seç** de.

**Alt klasörler de taranır.** Yani `9. Bölüm` klasörünü seçersen içindeki
`raw-jpeg` klasörü de kendiliğinden taranır. Ayrıca seçmene gerek yok.

Birden fazla klasör ekleyebilirsin — mesela hem 9. hem 10. Bölüm. Hepsi
listede görünür.

---

## 3. Sonuçların nereye yazılacağını seçmek

Aynı sayfada **Çıktı** kutusu var. **Seç** düğmesine basıp klasörleri nereye
oluşturmasını istiyorsan orayı göster.

> **Tavsiye:** harici diskte, fotoğraflardan ayrı yeni bir klasör aç.
> Mesela `E:\Kisiler\9. Bölüm`. Böyle yaparsan karışmaz.

---

## 4. Taramayı başlatmak

Şimdi asıl iş. **Tarama** kutusunda düğmeler var:

### İlk seferinde: **Deneme (300 fotoğraf)**

Bu düğmeye bas. Program 300 fotoğrafa bakıp kişileri gruplar. Yaklaşık
10-15 dakika sürer. Amacı: doğru çalışıyor mu, bir bakalım.

Bittiğinde aşağıda **Kişiler** bölümünde kartlar belirir. Her kart bir
kişi. Kartlarda o kişinin yüzünden birkaç küçük resim görürsün.

Gruplar doğru görünüyorsa devam et.

### Sonra: **Hepsini Yap**

Bütün fotoğrafları tarar. **10.000 fotoğraf yaklaşık 5 saat sürer.**
Akşam başlat, sabah bak.

> **Önemli:** yarıda kesilirse hiçbir şey kaybolmaz. Programı tekrar açıp
> yeniden başlatırsan **kaldığı yerden** devam eder, baştan taramaz.

### Tarama seçenekleri

Üç kutucuk var, üçü de isteğe bağlı:

| Kutucuk | Ne yapar | Ne zaman işaretle |
|---|---|---|
| **Yüksek kalite taraması** | Küçük ve uzaktaki yüzleri de yakalar. Testte kaçan 8 karenin 7'sini kurtardı. %20 daha uzun sürer. | **Genelde işaretle.** En doğru sonucu verir. |
| İki aşamalı tarama | İnsansız kareleri (set detayı, klaket) hızlı geçer | Acele ediyorsan |
| Hızlı tarama | Üçte bir hızlı biter ama küçük yüzleri kaçırır | Sadece kabaca bakacaksan |

Emin değilsen: **sadece "Yüksek kalite taraması"nı işaretle**, diğerlerine dokunma.

---

## 5. Kişilere isim vermek

Tarama bitince aşağıda kartlar olur: `kisi_0001`, `kisi_0002`...

Her kartta:
- Kişinin yüzünden 5 küçük resim
- **Bu kişinin adı** yazan bir kutu
- Birkaç düğme

**Yapman gereken:** kartın yüzlerine bak, kim olduğunu tanı, isim kutusuna
adını yaz ve **Enter'a bas**. Enter'a basınca kendiliğinden bir sonraki
kişinin kutusuna geçer — böylece hızlıca hepsini isimlendirirsin.

### Kartlardaki işaretler

| İşaret | Anlamı | Ne yapmalısın |
|---|---|---|
| **Yeşil "en net"** | Bu kişinin en net karesi | Bir şey yapma. Program bunu hatırlayacak. |
| **Turuncu çerçeve** | Program bu yüzden tam emin değil | Bak: bu kişi mi? Değilse yüze tıkla, gruptan çıkar. |
| **⚠ N şüpheli** düğmesi | O kartta N tane emin olunmayan kare var | Basarsan hangileri olduğunu listeler |
| **kütüphaneden** etiketi | İsmi program kendisi buldu | Doğruysa **kabul et** de |

### Kart düğmeleri

- **Kareler** — o kişinin fotoğraflarını şerit halinde gösterir. Kim olduğunu
  çıkaramıyorsan buna bas.
- **Neden?** — "programın bu yüzü neden bu kişiye koyduğunu" gösterir.
  Sayılar verir: kendi kişisine ne kadar benziyor, başkasına ne kadar.
  Aradaki fark büyükse karar sağlam demektir.
- **Böl** — kartta iki farklı kişi karışmışsa ayırmayı dener.

### Bir şeyi yanlış yaparsan

Sağ üstteki **↶ Geri al** düğmesine bas. Son yaptığın birleştirme, bölme ya
da çıkarma işlemini geri alır. Fotoğraflara zaten dokunulmuyor.

---

## 6. Program isimleri hatırlıyor

Bir kişiye isim verdiğinde program o yüzü **kütüphanesine** kaydeder.
Sonraki bölümü taradığında aynı kişiyi **kendisi tanır** ve ismini önerir.

Yani 9. Bölüm'de bir kere isim verirsen, 10. Bölüm'de tekrar uğraşmazsın.

Sol menüdeki **Kişi kütüphanesi** sayfasından kimlerin kayıtlı olduğunu
görebilirsin. Orada:
- İsim düzeltebilirsin
- Aynı kişi iki isimle kaydolduysa **Birleştir** ile tek isimde toplarsın
- **Benzer kişileri bul** düğmesi "bunlar aynı kişi olabilir" diye aday gösterir
- **Yedek al** ile kütüphaneni dosyaya kaydedersin

> Bir oyuncu peruk taksa ya da sakal bıraksa program onu ayrı bir "görünüm"
> olarak öğrenir; ikisini de tanır.

---

## 7. Klasörleri oluşturmak

İsimleri verdikten sonra **Klasörleme** kutusuna in.

1. Önce **Önce hesapla (hiçbir şey yazmaz)** düğmesine bas.
   Sana kaç klasör açacağını, kaç dosya kopyalayacağını ve ne kadar yer
   kaplayacağını gösterir. **Hiçbir şey yazmaz**, sadece hesap yapar.
2. Sonuç uygunsa **Klasörleri Oluştur** düğmesine bas.
3. Onay penceresi çıkar, **Oluştur** de.

Bitince **Çıktı klasörünü aç** düğmesiyle sonuca bakabilirsin.

### Çıktı düzeni

Üç seçenek var, **Çıktı düzeni** kutusundan seçiyorsun:

- **Alt klasör → kişi** *(önerilen)*: `9. Bölüm / Ahmet Yılmaz / foto.jpg`
  Kaynaktaki klasör yapın birebir korunur.
- **Kişi → alt klasör**: `Ahmet Yılmaz / 9. Bölüm / foto.jpg`
- **Düz**: `Ahmet Yılmaz / foto.jpg`

### Yer kaplar mı?

- Harici disk **exFAT** ise: gerçek kopya oluşur, yer kaplar.
- Disk **NTFS** ise: bağlantı kurulur, neredeyse hiç yer kaplamaz.

Program hangi diskte olduğunu kendisi anlar, senin bir şey yapman gerekmez.

---

## 8. İsimleri fotoğrafın içine yazmak

Klasör açmak istemiyorsan (ya da ek olarak) isimleri fotoğrafın kendi etiket
alanına yazdırabilirsin. **ACDSee bunları görür.**

**İsimleri fotoğrafın içine yaz** kutusunda:

1. **Yazım yeri** seç:
   - *Fotoğrafın içine göm* — ACDSee ve Lightroom görür (önerilen)
   - *Yan .xmp dosyasına* — orijinale hiç dokunulmaz, yanına küçük bir dosya yazılır
2. Önce **Önce 20 fotoğrafta dene** de.
3. ACDSee'yi açıp o 20 fotoğrafa bak, isimler göründü mü kontrol et.
4. Doğruysa **Hepsine yaz** de.

**Ne değişir, ne değişmez:**
- Değişmez: görüntünün kendisi, yıldızların, telifin, eski anahtar kelimelerin
- Değişir: sadece isim etiketleri eklenir
- Kopya oluşmaz, disk dolmaz

> RAW dosyalarda orijinal hiç açılmaz, yanına ayrı bir `.xmp` dosyası yazılır.

---

## 9. Arama — kimler aynı karede?

Sol menüde **Arama** var. "Şu üç kişinin birlikte olduğu kareler hangileri?"
sorusunu buradan sorarsın.

1. Kişileri işaretle (birden fazla seçebilirsin)
2. Sonuç: klasör klasör, dosya adlarıyla listelenir
3. İstersen **listeyi dosyaya kaydet** — nereye, hangi adla, hangi biçimde
   (Excel için CSV ya da düz metin) sen seçersin

---

## 10. Rapor sayfası

Sol menüdeki **Rapor** sayfası çekimin karnesini verir. Yedi bölüm var:

| Bölüm | Ne söyler |
|---|---|
| **Tarama karnesi** | Kaç kare tarandı, kaç yüz bulundu, kaç kare boş çıktı |
| **Kimden yeterince kare yok?** | **En işe yarayanı.** Her oyuncudan kaç *kullanılabilir* (net, gözü açık, yüzü büyük) kare var. Azsa sarı işaretle uyarır — set dağılmadan çekersin. |
| **Sahneler** | Çekim saatine bakıp sahneleri ayırır |
| **Topluluk kareleri** | En çok oyuncunun bir arada olduğu kareler (afiş için) |
| **Dikey kare kapsaması** | Kimin hiç dikey karesi yok (sosyal medya için) |
| **Bölüm özeti** | Her bölümde kaç kare, kaç kişi |
| **Birlikte görünenler** | En çok kim kiminle çıkmış |

Her bölümün **Dosyaya kaydet** düğmesi var — Excel'de açılır.

---

## 11. Güncelleme

Abin programa yeni özellik eklediğinde ya da bir hatayı düzelttiğinde,
sağ üstte **Güncelleme var mı?** düğmesine bas. Varsa indirir ve kurar.

Güncelleme senin hiçbir şeyini silmez: isimlerin, kütüphanen, ayarların,
taraman aynen kalır.

---

## Bir şey ters giderse

| Sorun | Çözüm |
|---|---|
| Program açılmıyor | Bilgisayarı kapat-aç, tekrar dene |
| Düğmeler tepki vermiyor | Programı kapat, tekrar aç. Olmazsa **Güncelleme var mı?** de |
| "Bağlantı yok" yazıyor | Program arka planda kapanmış. Kapat, tekrar aç |
| Tarama çok yavaş | Normal. 10.000 kare 5 saat. Bilgisayarı açık bırak |
| Yanlış kişileri birleştirdim | **↶ Geri al** düğmesi |
| Gruplar çok karışık | **Yeniden grupla** düğmesi. Öncesinde program kendiliğinden yedek alır |
| Bir kart iki kişi içeriyor | Kartta **Böl** düğmesi |
| Aynı kişi iki kartta | İkisini de işaretle, **Seçilenleri birleştir** de |

### Abine yazarken

Şu üçünü gönder, çok işine yarar:
1. Ekranın fotoğrafı
2. Ne yapmaya çalışıyordun
3. Sağ üstteki sürüm numarası (mesela "sürüm 1.20.3")

---

## Önerilen çalışma sırası (her bölüm için)

1. **+ Klasör ekle** → yeni bölümün klasörünü göster
2. **Çıktı** klasörünü seç
3. **Yüksek kalite taraması**nı işaretle
4. **Hepsini Yap** → akşam başlat, sabah bak
5. Kartlara isim ver (Enter ile hızlıca geç). Tanıdıklarını program zaten önerir
6. **Rapor** sayfasına bak: kimden yeterince kare yok?
7. **Önce hesapla** → **Klasörleri Oluştur**
8. İstersen **İsimleri fotoğrafın içine yaz**

---

## Kısa sözlük

| Terim | Anlamı |
|---|---|
| **Tarama** | Programın fotoğraflara bakıp yüzleri bulması |
| **Gruplama** | Aynı kişinin yüzlerini bir araya toplaması |
| **Küme / kişi kartı** | Bir kişiye ait yüzlerin listesi |
| **Kütüphane** | Programın isimleri hatırladığı yer |
| **Metadata / etiket** | Fotoğrafın içinde saklanan bilgi (isim, telif, tarih) |
| **XMP** | Metadata'nın yazıldığı biçim. ACDSee bunu okur |
| **Şüpheli** | Programın emin olmadığı eşleşme |
| **Kapsama** | Bir oyuncudan kaç kullanılabilir kare olduğu |
