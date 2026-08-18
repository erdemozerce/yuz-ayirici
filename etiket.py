#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
etiket.py — kisi isimlerini fotografin METADATA'sina yazar.

NEDEN
  Klasorleme her fotografin kopyasini olusturur (exFAT'te 10.000 kare ~750 GB).
  Metadata yontemi hicbir kopya olusturmaz: isim dosyanin kendi etiket alanina
  yazilir, ACDSee / Lightroom / Bridge / XnView fotografi acinca kisiyi gorur.

UC BICIM BIRDEN YAZILIR (birbirini bozmaz)
  1. Anahtar kelime (dc:subject + lr:hierarchicalSubject "People|Isim")
     -> her programda arama/filtrede calisir. En garantili olan budur.
  2. XMP-mwg-rs bolgeleri  -> Lightroom, Bridge, digiKam, XnView
  3. XMP-acdsee-rs bolgeleri -> ACDSee'nin kendi bicimi (Ultimate/Pro'da People paneli)

KOORDINAT
  Her iki bicim de MERKEZ noktasi + genislik/yukseklik kullanir, 0-1 oraninda.

GUVENLIK
  - Goruntu verisine dokunulmaz, yalniz etiket alani degisir.
  - Mevcut metadata (yildiz, etiket, duzenleme) korunur - uzerine yazilmaz.
  - RAW dosyalara gomme yapilamaz; yanlarina .xmp dosyasi yazilir, orijinal
    dosyaya hic dokunulmaz.
  - --dogrula ile yazim sonrasi goruntu tekrar acilip piksel verisi karsilastirilir.
"""

import csv
import os
import sqlite3
import sys
from pathlib import Path

# gomme yapilamayan (RAW vb.) uzantilar -> yan .xmp dosyasi
YAN_DOSYA_GEREKTIREN = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".rw2",
    ".orf", ".pef", ".dng", ".raw", ".3fr", ".iiq", ".x3f", ".heic", ".heif",
}

BOS_XMP = ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
           '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
           '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           '<rdf:Description rdf:about=""/></rdf:RDF></x:xmpmeta>'
           '<?xpacket end="w"?>')


def hazirla():
    """pyexiv2'yi yukler ve ACDSee ad alanlarini kaydeder."""
    try:
        import pyexiv2
    except ImportError:
        raise RuntimeError(
            "'pyexiv2' kutuphanesi kurulu degil. Su komutu calistirin:\n"
            "    pip install pyexiv2")
    for uri, on in (("http://ns.acdsee.com/regions/", "acdsee-rs"),
                    ("http://ns.acdsee.com/sType/Area#", "acdsee-stArea"),
                    ("http://ns.acdsee.com/sType/Dimensions#", "acdsee-stDim")):
        try:
            pyexiv2.registerNs(uri, on)
        except Exception:
            pass          # zaten kayitliysa sorun degil
    return pyexiv2


def goruntu_boyutu(yol):
    """Dosyayi tam okumadan genislik/yukseklik. Basarisizsa (0,0)."""
    try:
        from PIL import Image
        with Image.open(str(yol)) as im:
            return im.size
    except Exception:
        try:
            import cv2
            import numpy as np
            img = cv2.imdecode(np.fromfile(str(yol), np.uint8), cv2.IMREAD_REDUCED_COLOR_8)
            if img is not None:
                h, w = img.shape[:2]
                return w * 8, h * 8
        except Exception:
            pass
    return 0, 0


def xmp_sozlugu(kisiler, genislik, yukseklik):
    """
    kisiler: [(isim, (x1,y1,x2,y2)), ...]  - piksel koordinatlari
    Uc bicimi birden iceren pyexiv2 sozlugu dondurur.
    """
    isimler = []
    for isim, _ in kisiler:
        if isim not in isimler:
            isimler.append(isim)

    veri = {
        "Xmp.dc.subject": isimler,
        "Xmp.lr.hierarchicalSubject": ["People|" + i for i in isimler],
    }
    if not genislik or not yukseklik:
        return veri            # boyut bilinmiyorsa yalniz anahtar kelime

    M = "Xmp.mwg-rs.Regions"
    A = "Xmp.acdsee-rs.Regions"
    veri.update({
        M: "type=Struct",
        M + "/mwg-rs:AppliedToDimensions": "type=Struct",
        M + "/mwg-rs:AppliedToDimensions/stDim:w": str(genislik),
        M + "/mwg-rs:AppliedToDimensions/stDim:h": str(yukseklik),
        M + "/mwg-rs:AppliedToDimensions/stDim:unit": "pixel",
        M + "/mwg-rs:RegionList": "type=Bag",
        A: "type=Struct",
        A + "/acdsee-rs:AppliedToDimensions": "type=Struct",
        A + "/acdsee-rs:AppliedToDimensions/acdsee-stDim:w": str(genislik),
        A + "/acdsee-rs:AppliedToDimensions/acdsee-stDim:h": str(yukseklik),
        A + "/acdsee-rs:AppliedToDimensions/acdsee-stDim:unit": "pixel",
        A + "/acdsee-rs:RegionList": "type=Bag",
    })

    for i, (isim, kutu) in enumerate(kisiler, 1):
        x1, y1, x2, y2 = kutu
        gen = max(x2 - x1, 1) / genislik
        yuk = max(y2 - y1, 1) / yukseklik
        mx = ((x1 + x2) / 2.0) / genislik          # merkez
        my = ((y1 + y2) / 2.0) / yukseklik
        # 0-1 disina tasmasin
        mx, my = min(max(mx, 0.0), 1.0), min(max(my, 0.0), 1.0)
        gen, yuk = min(gen, 1.0), min(yuk, 1.0)
        d = lambda v: "%.6f" % v                                    # noqa: E731

        mk = "%s/mwg-rs:RegionList[%d]" % (M, i)
        veri.update({
            mk: "type=Struct",
            mk + "/mwg-rs:Name": isim,
            mk + "/mwg-rs:Type": "Face",
            mk + "/mwg-rs:Area": "type=Struct",
            mk + "/mwg-rs:Area/stArea:x": d(mx),
            mk + "/mwg-rs:Area/stArea:y": d(my),
            mk + "/mwg-rs:Area/stArea:w": d(gen),
            mk + "/mwg-rs:Area/stArea:h": d(yuk),
            mk + "/mwg-rs:Area/stArea:unit": "normalized",
        })

        ak = "%s/acdsee-rs:RegionList[%d]" % (A, i)
        veri.update({
            ak: "type=Struct",
            ak + "/acdsee-rs:Name": isim,
            ak + "/acdsee-rs:Type": "Face",
        })
        for alan in ("DLYArea", "ALGArea"):
            veri.update({
                "%s/acdsee-rs:%s" % (ak, alan): "type=Struct",
                "%s/acdsee-rs:%s/acdsee-stArea:x" % (ak, alan): d(mx),
                "%s/acdsee-rs:%s/acdsee-stArea:y" % (ak, alan): d(my),
                "%s/acdsee-rs:%s/acdsee-stArea:w" % (ak, alan): d(gen),
                "%s/acdsee-rs:%s/acdsee-stArea:h" % (ak, alan): d(yuk),
            })
    return veri


def _kelimeleri_birlestir(im, veri):
    """
    Fotografta zaten yazili anahtar kelimeler varsa (bolum adi, telif, konu...)
    onlarin UZERINE YAZMAZ - yeni isimleri sonuna ekler. Tekrar calistirilirsa
    ayni isim iki kez yazilmaz.
    """
    veri = dict(veri)
    try:
        mevcut = im.read_xmp()
    except Exception:
        return veri
    for anahtar in ("Xmp.dc.subject", "Xmp.lr.hierarchicalSubject"):
        yeni = veri.get(anahtar)
        if not yeni:
            continue
        eski = mevcut.get(anahtar) or []
        if isinstance(eski, str):
            eski = [eski]
        veri[anahtar] = list(dict.fromkeys(list(eski) + list(yeni)))
    return veri


def yan_dosya_yolu(yol):
    return Path(str(yol) + ".xmp")


def piksel_ozeti(yol):
    try:
        import hashlib
        import cv2
        import numpy as np
        img = cv2.imdecode(np.fromfile(str(yol), np.uint8), cv2.IMREAD_REDUCED_COLOR_4)
        if img is None:
            return None
        return hashlib.sha256(img.tobytes()).hexdigest()
    except Exception:
        return None


def dosyaya_yaz(pyexiv2, yol, veri, mod="gomulu", dogrula=False):
    """
    mod: 'gomulu' (mumkunse dosyanin icine) | 'yan' (her zaman .xmp yan dosyasi)
    Dondurur: ('gomulu'|'yan', hata_mesaji_veya_None)
    """
    uzanti = Path(yol).suffix.lower()
    yan_zorunlu = uzanti in YAN_DOSYA_GEREKTIREN
    yan_mi = yan_zorunlu or mod == "yan"

    if yan_mi:
        hedef = yan_dosya_yolu(yol)
        try:
            if not hedef.exists():
                hedef.write_text(BOS_XMP, encoding="utf-8")
            with pyexiv2.Image(str(hedef)) as im:
                im.modify_xmp(_kelimeleri_birlestir(im, veri))
            return "yan", None
        except Exception as e:
            return "yan", str(e)

    onceki = piksel_ozeti(yol) if dogrula else None
    try:
        with pyexiv2.Image(str(yol)) as im:
            im.modify_xmp(_kelimeleri_birlestir(im, veri))
    except Exception as e:
        return "gomulu", str(e)
    if dogrula:
        sonraki = piksel_ozeti(yol)
        if onceki and sonraki and onceki != sonraki:
            return "gomulu", "GORUNTU DEGISTI - bu dosya icin yazim geri alinmali!"
        if sonraki is None:
            return "gomulu", "yazim sonrasi goruntu acilamadi!"
    return "gomulu", None


# --------------------------------------------------------------------------
def etiketle(db_yolu, isimler_csv, mod="gomulu", limit=0, dogrula_adet=5,
             log=print, sadece_isimli=True, kisiler=None):
    """Veritabanindaki isimlendirilmis kisileri fotograflarin metadata'sina yazar."""
    pyexiv2 = hazirla()

    # isimler.csv -> {kume: isim}
    isimler = {}
    p = Path(isimler_csv)
    if p.exists():
        with open(p, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                try:
                    ad = (row.get("isim") or "").strip()
                    if ad:
                        isimler[int(row["kume_no"])] = ad
                except (KeyError, TypeError, ValueError):
                    continue
    if kisiler:
        secili = set(int(k) for k in kisiler)
        isimler = {c: a for c, a in isimler.items() if c in secili}
        log("Yalnizca secilen %d kisi icin yazilacak." % len(isimler))
    if not isimler:
        log("isimler.csv icinde (secilen kisilerde) isim yok.")
        return {"dosya": 0}

    con = sqlite3.connect(str(db_yolu))
    esler_tablo = {}
    try:
        for r in con.execute("SELECT path, esler FROM files WHERE esler IS NOT NULL"):
            esler_tablo[r[0]] = [x for x in (r[1] or "").split("|") if x]
    except Exception:
        pass
    kumeler = tuple(isimler)
    soru = ",".join("?" * len(kumeler))
    satirlar = con.execute(
        "SELECT path, cluster, x1, y1, x2, y2 FROM faces "
        "WHERE cluster IN (%s) ORDER BY path" % soru, kumeler).fetchall()
    con.close()

    fotograflar = {}
    for yol, cid, x1, y1, x2, y2 in satirlar:
        fotograflar.setdefault(yol, []).append((isimler[cid], (x1, y1, x2, y2)))

    yollar = sorted(fotograflar)
    if limit:
        yollar = yollar[:limit]

    log("%d fotografa %d kisi ismi yazilacak (%s)." %
        (len(yollar), len(isimler),
         "dosyanin icine" if mod == "gomulu" else "yan .xmp dosyasina"))

    sayac = {"gomulu": 0, "yan": 0, "hata": 0, "dosya": 0}
    hatalar = []
    for i, yol in enumerate(yollar, 1):
        kisiler = fotograflar[yol]
        g, y = goruntu_boyutu(yol)
        veri = xmp_sozlugu(kisiler, g, y)
        nasil, hata = dosyaya_yaz(pyexiv2, yol, veri, mod=mod,
                                  dogrula=(i <= dogrula_adet))
        # ayni karenin RAW/JPEG esine de ayni isimler yazilsin
        for es in esler_tablo.get(yol, []):
            if os.path.exists(es):
                dosyaya_yaz(pyexiv2, es, veri, mod=mod, dogrula=False)
        if hata:
            sayac["hata"] += 1
            if len(hatalar) < 5:
                hatalar.append("%s -> %s" % (Path(yol).name, hata))
        else:
            sayac[nasil] += 1
            sayac["dosya"] += 1
        if i % 100 == 0 or i == len(yollar):
            log("  [%d/%d] %d dosyaya yazildi, %d hata"
                % (i, len(yollar), sayac["dosya"], sayac["hata"]))

    log("")
    log("Tamam. %d dosyanin icine, %d yan dosyaya yazildi, %d hata."
        % (sayac["gomulu"], sayac["yan"], sayac["hata"]))
    if hatalar:
        log("Ilk hatalar:")
        for h in hatalar:
            log("   " + h)
    if dogrula_adet:
        log("Ilk %d dosyada goruntu verisi degismedigi dogrulandi." % min(dogrula_adet, len(yollar)))
    return sayac


def oku(yol):
    """Bir dosyada hangi kisiler yazili? (kontrol icin)"""
    pyexiv2 = hazirla()
    kaynak = yol
    if Path(yol).suffix.lower() in YAN_DOSYA_GEREKTIREN:
        kaynak = yan_dosya_yolu(yol)
    with pyexiv2.Image(str(kaynak)) as im:
        x = im.read_xmp()
    return {
        "anahtar_kelime": x.get("Xmp.dc.subject", []),
        "mwg": [v for k, v in x.items() if k.endswith("mwg-rs:Name")],
        "acdsee": [v for k, v in x.items() if k.endswith("acdsee-rs:Name")],
    }


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(sys.argv) > 2 and sys.argv[1] == "oku":
        print(oku(sys.argv[2]))
    else:
        print(__doc__)
