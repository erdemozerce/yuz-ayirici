# Yüz Ayırıcı — fotoğrafları kişilere göre klasörleyen bot

## 1) Kurulum (tek sefer)

Python 3.10–3.12 kurulu olmalı (python.org, kurulumda "Add python.exe to PATH" işaretli).

```
pip install insightface onnxruntime opencv-python numpy scikit-learn pillow pillow-heif
```

`insightface` kurulumu hata verirse (C derleyicisi ister):
Microsoft "Build Tools for Visual Studio" → "Desktop development with C++" kurulup tekrar dene.

NVIDIA ekran kartı varsa (çok daha hızlı):
```
pip uninstall onnxruntime
pip install onnxruntime-gpu
```
ve `scan` komutuna `--gpu` ekle.

## 2) Adımlar

Önce küçük bir denemeyle başla (300 fotoğraf):

```
cd %USERPROFILE%\Desktop\yuz-ayirici
python face_sorter.py scan --src "D:\Fotograflar" --db faces.db --limit 300
python face_sorter.py cluster --db faces.db
python face_sorter.py review --db faces.db --out inceleme.html
```

`inceleme.html` dosyasını tarayıcıda aç, gruplar doğru mu bak. İyiyse limitsiz tam tarama:

```
python face_sorter.py scan --src "D:\Fotograflar" --db faces.db
python face_sorter.py cluster --db faces.db
python face_sorter.py review --db faces.db --out inceleme.html
```

`isimler.csv` dosyasını Excel'de aç, tanıdığın kişilerin `isim` sütununu doldur (boş bırakılanlar `kisi_0001` gibi kalır). Sonra:

```
python face_sorter.py export --db faces.db --dst "D:\Kisiler" --mode hardlink
```

## 3) Ayar ipuçları

- **Aynı kişi birden çok klasöre bölündü** → `cluster --eps 0.58` (birleştirmeyi artırır)
- **Farklı kişiler aynı klasöre karıştı** → `cluster --eps 0.42` (ayrımı sertleştirir)
- **Çok fazla küçük/anlamsız grup** → `--min-samples 4 --min-face 60`
- Kümeleme saniyeler sürer; tarama (`scan`) tekrarlanmaz, istediğin kadar dene.

## 4) Notlar

- `--mode hardlink` (varsayılan): fotoğraflar **ekstra yer kaplamaz**, aynı dosya birden çok klasörde görünür. Aynı disk ve NTFS şart. Bir klasörden silmek orijinali silmez.
- `--mode copy`: gerçek kopya. Bir fotoğrafta 3 kişi varsa 3 kopya oluşur → disk 2–3 katı yer ister.
- Orijinal fotoğraflara **hiç dokunulmaz**, hiçbir şey silinmez/taşınmaz.
- `scan` kesilirse aynı komutu tekrar çalıştır, kaldığı yerden devam eder.
