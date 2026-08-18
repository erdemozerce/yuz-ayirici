#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
paket_yap.py — kardesine gonderilecek kurulum ZIP'ini uretir.

    python paket_yap.py                          (guncelleme kapali)
    python paket_yap.py https://.../surum.json   (guncelleme adresi gomulu)

GitHub kullaniyorsan adres su kaliptadir:
    https://raw.githubusercontent.com/KULLANICI/DEPO/main/yayin/surum.json
"""

import json
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
CIKTI = BASE / "yuz-ayirici-kurulum.zip"

# ZIP'e girecek dosyalar (yayinla.py, yayin/, .git disarida - onlar senin tarafin)
ICERIK = [
    "KUR.bat",
    "BASLAT.bat",
    "GUNCELLE.bat",
    "KARDESIM-ICIN.md",
    "face_sorter.py",
    "kutuphane.py",
    "baslat.py",
    "guncelle.py",
    "kurulum_testi.py",
    "gereksinimler.txt",
    "surum.txt",
]


def main():
    url = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if url and not url.lower().startswith("https://"):
        print("!! Guncelleme adresi https:// ile baslamali.")
        return 1
    if url and not url.lower().endswith(".json"):
        print("!! Adres surum.json dosyasini gostermeli.")
        return 1

    ayarlar = {
        "kaynak_klasor": "",
        "hedef_klasor": "",
        "db": "faces.db",
        "eps": 0.50,
        "min_samples": 3,
        "mod": "hardlink",
        "guncelleme_url": url,
        "otomatik_guncelleme": True,
        "son_kontrol": 0,
    }

    eksik = [a for a in ICERIK if not (BASE / a).exists()]
    if eksik:
        print("!! Eksik dosyalar:", ", ".join(eksik))
        return 1

    with zipfile.ZipFile(CIKTI, "w", zipfile.ZIP_DEFLATED) as z:
        for ad in ICERIK:
            z.write(BASE / ad, "yuz-ayirici/" + ad)
        z.writestr("yuz-ayirici/ayarlar.json",
                   json.dumps(ayarlar, ensure_ascii=False, indent=2))

    boyut = CIKTI.stat().st_size / 1024
    print("Paket hazir: %s  (%.0f KB)" % (CIKTI, boyut))
    print("Surum       : %s" % (BASE / "surum.txt").read_text(encoding="utf-8").strip())
    print("Guncelleme  : %s" % (url if url else "KAPALI (adres verilmedi)"))
    print("\nBu ZIP'i kardesine gonder. Acip KUR.bat'a cift tiklamasi yeterli.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
