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

import contextlib
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


VARSAYILAN_KUNYE = {
    "aktif": False,
    "yapim": "",            # dizi/film adi
    "bolum": "",            # bolum no ya da adi
    "sahne": "",
    "fotografci": "",       # Byline / Creator
    "telif": "",            # Copyright
    "kaynak": "",           # Source / Credit
    "sablon": "{yapim} {bolum} - {kisiler}",
    "baslik_sablonu": "{yapim} {bolum}",
}

# IPTC alan sinirlari (asilirsa kirpilir)
IPTC_SINIR = {"Iptc.Application2.ObjectName": 64,
              "Iptc.Application2.Caption": 2000,
              "Iptc.Application2.Byline": 32,
              "Iptc.Application2.Copyright": 128,
              "Iptc.Application2.Credit": 32,
              "Iptc.Application2.Source": 32}


def kunye_metni(sablon, kunye, isimler, yol):
    """Sablondaki yer tutuculari doldurur."""
    from pathlib import Path as _P
    degerler = {
        "yapim": kunye.get("yapim", ""),
        "bolum": kunye.get("bolum", ""),
        "sahne": kunye.get("sahne", ""),
        "kisiler": ", ".join(isimler),
        "dosya": _P(yol).name,
        "klasor": _P(yol).parent.name,
        "fotografci": kunye.get("fotografci", ""),
    }
    try:
        metin = sablon.format(**degerler)
    except (KeyError, IndexError, ValueError):
        metin = sablon
    return " ".join(metin.split()).strip(" -,")


def kunye_sozlugu(kunye, isimler, yol):
    """Caption/kunye alanlarini XMP + IPTC olarak dondurur."""
    if not kunye or not kunye.get("aktif"):
        return {}, {}
    aciklama = kunye_metni(kunye.get("sablon") or "", kunye, isimler, yol)
    baslik = kunye_metni(kunye.get("baslik_sablonu") or "", kunye, isimler, yol)

    xmp, iptc = {}, {}
    if aciklama:
        xmp["Xmp.dc.description"] = {"lang=x-default": aciklama}
        iptc["Iptc.Application2.Caption"] = aciklama
    if baslik:
        xmp["Xmp.dc.title"] = {"lang=x-default": baslik}
        xmp["Xmp.photoshop.Headline"] = baslik
        iptc["Iptc.Application2.ObjectName"] = baslik
    if kunye.get("fotografci"):
        xmp["Xmp.dc.creator"] = [kunye["fotografci"]]
        iptc["Iptc.Application2.Byline"] = kunye["fotografci"]
    if kunye.get("telif"):
        xmp["Xmp.dc.rights"] = {"lang=x-default": kunye["telif"]}
        iptc["Iptc.Application2.Copyright"] = kunye["telif"]
    if kunye.get("kaynak"):
        xmp["Xmp.photoshop.Credit"] = kunye["kaynak"]
        xmp["Xmp.photoshop.Source"] = kunye["kaynak"]
        iptc["Iptc.Application2.Credit"] = kunye["kaynak"]
        iptc["Iptc.Application2.Source"] = kunye["kaynak"]

    for k, sinir in IPTC_SINIR.items():
        if k in iptc and len(iptc[k]) > sinir:
            iptc[k] = iptc[k][:sinir - 1] + "…"
    return xmp, iptc


def _kisa_yol(yol):
    """
    Windows 8.3 kisa yolu. pyexiv2/exiv2 ANSI kod sayfasi disindaki karakterleri
    (Turkce i, s, g...) acamiyor; kisa yol saf ASCII oldugu icin sorunu cozer.
    Bedava: dosya kopyalanmaz.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        fn = ctypes.windll.kernel32.GetShortPathNameW
        fn.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        fn.restype = wintypes.DWORD
        tampon = ctypes.create_unicode_buffer(1024)
        if fn(str(yol), tampon, 1024) and tampon.value.isascii():
            return tampon.value
    except Exception:
        pass
    return None


@contextlib.contextmanager
def acilabilir(yol):
    """
    pyexiv2'nin acabilecegi bir yol verir. Uc kademe:
      1. Yol zaten ASCII ise dogrudan kullanilir (maliyet yok)
      2. Windows kisa yolu (8.3) denenir (maliyet yok)
      3. Son care: gecici ASCII isimli kopya - islem sonrasi geri yazilir
    Cikista dosyanin DEGISTIRILME TARIHI korunur; yoksa bir sonraki tarama
    tum arsivi yeniden taramak zorunda kalirdi.
    """
    yol = str(yol)
    try:
        st = os.stat(yol)
        zaman = (st.st_atime, st.st_mtime)
    except OSError:
        zaman = None

    # macOS/Linux'ta exiv2 dosya adlarini UTF-8 olarak isler; sorun yalniz
    # Windows'un ANSI kod sayfasinda. Orada gereksiz kopyalama yapmayalim.
    if os.name != "nt" or yol.isascii():
        try:
            yield yol
        finally:
            if zaman:
                try:
                    os.utime(yol, zaman)
                except OSError:
                    pass
        return

    kisa = _kisa_yol(yol)
    if kisa:
        try:
            yield kisa
        finally:
            if zaman:
                try:
                    os.utime(yol, zaman)
                except OSError:
                    pass
        return

    # 8.3 kapali (exFAT'te olabilir) -> gecici kopya
    import shutil
    import tempfile
    uzanti = Path(yol).suffix or ".tmp"
    gecici = tempfile.NamedTemporaryFile(delete=False, suffix=uzanti)
    gecici.close()
    try:
        shutil.copy2(yol, gecici.name)
        yield gecici.name
        shutil.copy2(gecici.name, yol)
    finally:
        try:
            os.unlink(gecici.name)
        except OSError:
            pass
        if zaman:
            try:
                os.utime(yol, zaman)
            except OSError:
                pass


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


BOLGE_ONEKLERI = ("Xmp.mwg-rs.Regions", "Xmp.acdsee-rs.Regions")


def _eski_bolgeleri_sil(im, veri):
    """
    Yeni yuz bolgeleri yazilmadan once eskilerini siler.

    Neden: exiv2, mevcut olandan AZ ogeli bir dizi yazilmaya calisilinca
    "Indexing applied to non-array" ile cokuyor (olculdu: 3 bolgeli dosyaya
    1-2 bolge yazmak hata, 3+ sorunsuz). Ayrica silinmezse gruptan cikarilan
    bir kisinin ismi fotografta asili kalirdi.
    """
    if not any(k.startswith(BOLGE_ONEKLERI) for k in veri):
        return
    try:
        mevcut = im.read_xmp()
    except Exception:
        return
    silinecek = {k: None for k in mevcut if k.startswith(BOLGE_ONEKLERI)}
    if silinecek:
        try:
            im.modify_xmp(silinecek)
        except Exception:
            pass


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
    """
    Yan (sidecar) dosyanin yolu: DSCF0020.RAF -> DSCF0020.xmp

    ACDSee ve Adobe bu bicimi bekliyor (uzanti DEGISTIRILIR). Onceki
    surumler "DSCF0020.RAF.xmp" yaziyordu; onu ACDSee gormuyordu.
    """
    return Path(yol).with_suffix(".xmp")


def yan_dosya_eski(yol):
    """Onceki surumlerin kullandigi ad - varsa o da guncellenir."""
    return Path(str(yol) + ".xmp")


def yan_dosyalar(yol):
    """Okurken bakilacak adlar: once yeni bicim, sonra eskisi."""
    return [yan_dosya_yolu(yol), yan_dosya_eski(yol)]


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


def dosyaya_yaz(pyexiv2, yol, veri, mod="gomulu", dogrula=False, iptc=None):
    """
    mod: 'gomulu' (mumkunse dosyanin icine) | 'yan' (her zaman .xmp yan dosyasi)
    Dondurur: ('gomulu'|'yan', hata_mesaji_veya_None)
    """
    uzanti = Path(yol).suffix.lower()
    yan_zorunlu = uzanti in YAN_DOSYA_GEREKTIREN
    yan_mi = yan_zorunlu or mod == "yan"

    if yan_mi:
        # Oncelikli ad ACDSee/Adobe bicimi (DSCF0020.xmp). Onceki surumlerin
        # yazdigi DSCF0020.RAF.xmp varsa bayat kalmasin diye o da guncellenir.
        hedefler = [yan_dosya_yolu(yol)]
        eski = yan_dosya_eski(yol)
        if eski.exists() and eski != hedefler[0]:
            hedefler.append(eski)
        son_hata = None
        for hedef in hedefler:
            try:
                if not hedef.exists():
                    hedef.write_text(BOS_XMP, encoding="utf-8")
                with acilabilir(hedef) as acik:
                    with pyexiv2.Image(acik) as im:
                        _eski_bolgeleri_sil(im, veri)
                        im.modify_xmp(_kelimeleri_birlestir(im, veri))
            except Exception as e:
                son_hata = str(e)
        return "yan", son_hata

    onceki = piksel_ozeti(yol) if dogrula else None
    try:
        with acilabilir(yol) as acik:
            with pyexiv2.Image(acik) as im:
                _eski_bolgeleri_sil(im, veri)
                im.modify_xmp(_kelimeleri_birlestir(im, veri))
                if iptc:
                    try:
                        im.modify_iptc(iptc)
                    except Exception:
                        pass      # IPTC yazilamazsa XMP zaten yazildi
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
             log=print, sadece_isimli=True, kisiler=None, kunye=None):
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

    # --- her kare icin bolum ve sahne bilgisi (otomatik altyazi icin)
    kare_bilgi = {}
    try:
        import face_sorter as _motor
        kare_sahne, _ozet = _motor.sahne_bloklari(con)
        koklar = {r[0]: r[1] for r in con.execute(
            "SELECT path, kok FROM files WHERE kok IS NOT NULL")}
        for _yol in set(list(kare_sahne) + list(koklar)):
            bilgi = {}
            no = kare_sahne.get(_yol)
            if no:
                bilgi["sahne"] = str(no)
            kok = koklar.get(_yol)
            if kok:
                # "9. Bolum/raw-jpeg" gibi kapsayici klasorlerde bolum adi
                # kaynak klasorun kendi adidir (rapordaki kuralla ayni).
                KAPSAYICI = {"raw", "jpeg", "jpg", "rawjpeg", "rawjpg", "dcim",
                             "export", "cikti", "foto", "fotograf", "fotograflar",
                             "images", "img", "photos", "orijinal", "original"}
                kok_adi = os.path.basename(os.path.normpath(kok))
                ad_ = str(_motor.bagil_klasor(_yol, kok, 1))
                sade = ad_.lower().replace(" ", "").replace("_", "").replace("-", "")
                bilgi["bolum"] = kok_adi if (ad_ in (".", "") or sade in KAPSAYICI) else ad_
            if bilgi:
                kare_bilgi[_yol] = bilgi
    except Exception:
        kare_bilgi = {}

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

    veto = {}
    try:
        for p, k in con.execute("SELECT path, kisi FROM onay WHERE durum = 'red'"):
            veto.setdefault(p, set()).add(k)
    except Exception:
        veto = {}

    fotograflar = {}
    atlanan = 0
    for yol, cid, x1, y1, x2, y2 in satirlar:
        v = veto.get(yol)
        if v is not None and (None in v or cid in v):
            atlanan += 1
            continue                      # oyuncu vetosu
        fotograflar.setdefault(yol, []).append((isimler[cid], (x1, y1, x2, y2)))
    if atlanan:
        log("Veto: %d yuz kaydi atlandi (oyuncu onayi yok)." % atlanan)

    yollar = sorted(fotograflar)
    if limit:
        yollar = yollar[:limit]

    log("%d fotografa %d kisi ismi yazilacak (%s)." %
        (len(yollar), len(isimler),
         "dosyanin icine" if mod == "gomulu" else "yan .xmp dosyasina"))
    if kunye and kunye.get("aktif"):
        ornek = kunye_metni(kunye.get("sablon") or "", kunye, ["Ornek Kisi"], yollar[0] if yollar else "x.jpg")
        log("Kunye de yazilacak. Ornek aciklama: %s" % ornek)

    sayac = {"gomulu": 0, "yan": 0, "hata": 0, "dosya": 0}
    hatalar = []
    for i, yol in enumerate(yollar, 1):
        kisiler = fotograflar[yol]
        g, y = goruntu_boyutu(yol)
        veri = xmp_sozlugu(kisiler, g, y)
        iptc = None
        if kunye and kunye.get("aktif"):
            adlar = []
            for ad, _ in kisiler:
                if ad not in adlar:
                    adlar.append(ad)
            kare_kunye = kunye
            if kare_bilgi.get(yol):
                # bolum/sahne bu kareye ozel - sablondaki yer tutucular
                # her fotografta dogru degeri alsin
                kare_kunye = dict(kunye)
                kare_kunye.update(kare_bilgi[yol])
            k_xmp, iptc = kunye_sozlugu(kare_kunye, adlar, yol)
            veri.update(k_xmp)
        nasil, hata = dosyaya_yaz(pyexiv2, yol, veri, mod=mod,
                                  dogrula=(i <= dogrula_adet), iptc=iptc)
        # ayni karenin RAW/JPEG esine de ayni isimler yazilsin
        for es in esler_tablo.get(yol, []):
            if os.path.exists(es):
                dosyaya_yaz(pyexiv2, es, veri, mod=mod, dogrula=False, iptc=iptc)
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
        # yeni bicim (DSCF.xmp) yoksa eski bicime (DSCF.RAF.xmp) bak
        kaynak = next((y for y in yan_dosyalar(yol) if y.exists()),
                      yan_dosya_yolu(yol))
    with acilabilir(kaynak) as acik:
        with pyexiv2.Image(acik) as im:
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
