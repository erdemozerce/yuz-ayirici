#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
teslim.py — secilen kareleri kucultulmus, filigranli teslim paketine cevirir
ve istege bagli kontak baskisi (PDF) uretir.

Unit stills is akisinda gunun sonunda 300-1500 kareden 50-150 seckisi
kucultulup yapimin sistemine yuklenir. Bu modul o adimi yapar:
  - uzun kenar N piksele kucultur (varsayilan 2048)
  - istenirse filigran basar
  - metadata'yi (isimler, kunye, telif) yeni dosyaya TASIR
  - kontak baskisi PDF'i uretir

Orijinal dosyalara dokunulmaz.
"""

import math
import os
from pathlib import Path

import cv2
import numpy as np


def _oku(yol):
    import face_sorter
    return face_sorter.imread_unicode(yol)


def kucult(img, uzun_kenar):
    h, w = img.shape[:2]
    if max(h, w) <= uzun_kenar:
        return img
    o = uzun_kenar / float(max(h, w))
    return cv2.resize(img, (max(int(w * o), 1), max(int(h * o), 1)),
                      interpolation=cv2.INTER_AREA)


def filigran_bas(img, metin, saydamlik=0.38, konum="sag-alt"):
    """Kosede yari saydam metin. Goruntunun genisligine gore olceklenir."""
    if not metin:
        return img
    h, w = img.shape[:2]
    olcek = max(w / 1400.0, 0.5)
    kalinlik = max(int(2 * olcek), 1)
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), taban = cv2.getTextSize(metin, font, olcek, kalinlik)
    pay = int(18 * olcek)
    if konum == "sag-alt":
        x, y = w - tw - pay, h - pay
    elif konum == "sol-alt":
        x, y = pay, h - pay
    else:
        x, y = (w - tw) // 2, h - pay
    katman = img.copy()
    cv2.rectangle(katman, (x - pay // 2, y - th - pay // 2),
                  (x + tw + pay // 2, y + taban + pay // 4), (0, 0, 0), -1)
    img = cv2.addWeighted(katman, saydamlik * 0.6, img, 1 - saydamlik * 0.6, 0)
    katman = img.copy()
    cv2.putText(katman, metin, (x, y), font, olcek, (255, 255, 255), kalinlik, cv2.LINE_AA)
    return cv2.addWeighted(katman, saydamlik + 0.25, img, 0.75 - saydamlik, 0)


def jpeg_yaz(img, hedef, kalite=88):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(kalite)])
    if not ok:
        return False
    Path(hedef).parent.mkdir(parents=True, exist_ok=True)
    Path(hedef).write_bytes(buf.tobytes())
    return True


def metadata_tasi(kaynak, hedef):
    """Isimler, kunye ve telif bilgisini kucultulmus dosyaya kopyalar."""
    try:
        import etiket
        pyexiv2 = etiket.hazirla()
        okunacak = kaynak
        if Path(kaynak).suffix.lower() in etiket.YAN_DOSYA_GEREKTIREN:
            okunacak = etiket.yan_dosya_yolu(kaynak)
            if not Path(okunacak).exists():
                return False
        with etiket.acilabilir(okunacak) as acik:
            with pyexiv2.Image(acik) as im:
                xmp, iptc = im.read_xmp(), im.read_iptc()
        # bolge kutulari kucultmede gecerliligini korur (0-1 orani), aynen tasinir
        with etiket.acilabilir(hedef) as acik:
            with pyexiv2.Image(acik) as im:
                if xmp:
                    im.modify_xmp(xmp)
                if iptc:
                    try:
                        im.modify_iptc(iptc)
                    except Exception:
                        pass
        return True
    except Exception:
        return False


def kontak_baskisi(dosyalar, hedef_pdf, sutun=4, satir=5, kenar=90, baslik=""):
    """Kucuk resimlerden PDF kontak baskisi (Pillow ile, ek kutuphane yok)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return 0
    if not dosyalar:
        return 0

    SAYFA = (2480, 3508)                 # A4 @300dpi
    hucre_g = (SAYFA[0] - kenar * (sutun + 1)) // sutun
    hucre_y = (SAYFA[1] - kenar * (satir + 1) - 120) // satir
    yazi = baslik_yazi = None
    for ad in ("arial.ttf", "Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
               "/Library/Fonts/Arial.ttf", "DejaVuSans.ttf"):
        try:
            yazi = ImageFont.truetype(ad, 26)
            baslik_yazi = ImageFont.truetype(ad, 44)
            break
        except Exception:
            continue
    if yazi is None:
        yazi = baslik_yazi = ImageFont.load_default()

    sayfalar = []
    for basla in range(0, len(dosyalar), sutun * satir):
        obek = dosyalar[basla:basla + sutun * satir]
        sayfa = Image.new("RGB", SAYFA, "white")
        ciz = ImageDraw.Draw(sayfa)
        if baslik:
            ciz.text((kenar, 42), baslik, fill="black", font=baslik_yazi)
        for i, d in enumerate(obek):
            sut, sat = i % sutun, i // sutun
            x = kenar + sut * (hucre_g + kenar)
            y = 120 + kenar + sat * (hucre_y + kenar)
            try:
                with Image.open(str(d)) as im:
                    im = im.convert("RGB")
                    im.thumbnail((hucre_g, hucre_y - 40))
                    sayfa.paste(im, (x + (hucre_g - im.width) // 2, y))
                    ad = Path(d).name
                    if len(ad) > 30:
                        ad = ad[:29] + "…"
                    ciz.text((x, y + im.height + 8), ad, fill="black", font=yazi)
            except Exception:
                continue
        sayfalar.append(sayfa)

    if not sayfalar:
        return 0
    Path(hedef_pdf).parent.mkdir(parents=True, exist_ok=True)
    sayfalar[0].save(str(hedef_pdf), save_all=True, append_images=sayfalar[1:])
    return len(sayfalar)


def paket_yap(dosyalar, hedef_klasor, uzun_kenar=2048, kalite=88, filigran="",
              kontak=True, baslik="", log=print, alt_klasor=None):
    """
    dosyalar: [(kaynak_yol, hedef_alt_yol), ...]  hedef_alt_yol None ise duz.
    """
    hedef_klasor = Path(hedef_klasor)
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    uretilen, hata = [], 0

    for i, kayit in enumerate(dosyalar, 1):
        kaynak, alt = kayit if isinstance(kayit, (tuple, list)) else (kayit, None)
        img = _oku(kaynak)
        if img is None:
            hata += 1
            continue
        img = kucult(img, uzun_kenar)
        if filigran:
            img = filigran_bas(img, filigran)
        ad = Path(kaynak).stem + ".jpg"
        hedef = hedef_klasor / (alt or "") / ad if alt else hedef_klasor / ad
        k = 1
        while hedef.exists():
            hedef = hedef.with_name("%s_%d.jpg" % (Path(kaynak).stem, k))
            k += 1
        if jpeg_yaz(img, hedef, kalite):
            metadata_tasi(kaynak, hedef)
            uretilen.append(hedef)
        else:
            hata += 1
        if i % 25 == 0 or i == len(dosyalar):
            log("  [%d/%d] %d kare hazir" % (i, len(dosyalar), len(uretilen)))

    toplam_mb = sum(p.stat().st_size for p in uretilen) / 1048576 if uretilen else 0
    log("")
    log("Teslim paketi: %d kare, %.0f MB -> %s" % (len(uretilen), toplam_mb, hedef_klasor))
    if hata:
        log("  %d dosya islenemedi." % hata)

    if kontak and uretilen:
        pdf = hedef_klasor / "kontak-baskisi.pdf"
        n = kontak_baskisi(uretilen, pdf, baslik=baslik or hedef_klasor.name)
        if n:
            log("  Kontak baskisi: %d sayfa -> %s" % (n, pdf.name))
        else:
            log("  Kontak baskisi uretilemedi (Pillow gerekli).")
    return {"uretilen": len(uretilen), "hata": hata, "mb": toplam_mb}
