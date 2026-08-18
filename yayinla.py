#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
yayinla.py — SENIN bilgisayarinda calisir (kardesinin bilgisayarinda degil).

Programda degisiklik yaptiktan sonra bunu calistir:
    python yayinla.py 1.1.0 "Ne degisti kisa aciklama"

Yaptigi is:
  1. Surum numarasini face_sorter.py ve surum.txt icinde gunceller.
  2. Dagitilacak dosyalarin SHA-256 ozetini hesaplar.
  3. 'yayin' klasorune dosyalari + surum.json manifestini yazar.
  4. Bu klasoru nasil yayina alacagini ekrana yazar.

Kardesin programi actiginda surum.json'a bakar, yeni surumu gorur,
dosyalari indirir, ozetleri dogrular ve kendini gunceller.
"""

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
YAYIN = BASE / "yayin"

# Uzaktan guncellenecek dosyalar. .bat dosyalari bilerek disarida:
# calisirken degistirilmeleri Windows'ta sorun cikarir.
DOSYALAR = [
    "kur.py",
    "face_sorter.py",
    "arayuz.py",
    "arayuz.html",
    "kutuphane.py",
    "etiket.py",
    "baslat.py",
    "guncelle.py",
    "kurulum_testi.py",
    "gereksinimler.txt",
]


def sha256(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


def surum_yaz(yeni):
    (BASE / "surum.txt").write_text(yeni, encoding="utf-8")
    fs = BASE / "face_sorter.py"
    s = fs.read_text(encoding="utf-8")
    s2 = re.sub(r'__version__\s*=\s*"[^"]*"', '__version__ = "%s"' % yeni, s, count=1)
    if s2 != s:
        fs.write_text(s2, encoding="utf-8", newline="\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Simdiki surum:", (BASE / "surum.txt").read_text(encoding="utf-8").strip())
        return 1
    yeni = sys.argv[1].strip()
    notlar = sys.argv[2] if len(sys.argv) > 2 else ""
    if not re.match(r"^\d+\.\d+\.\d+$", yeni):
        print("Surum numarasi 1.2.3 seklinde olmali.")
        return 1

    surum_yaz(yeni)

    if YAYIN.exists():
        shutil.rmtree(YAYIN)
    YAYIN.mkdir(parents=True)

    kayitlar = []
    for ad in DOSYALAR:
        kaynak = BASE / ad
        if not kaynak.exists():
            print("!! bulunamadi, atlaniyor:", ad)
            continue
        shutil.copy2(kaynak, YAYIN / ad)
        kayitlar.append({"ad": ad, "url": ad, "sha256": sha256(kaynak)})
        print("  + %-22s %s" % (ad, kayitlar[-1]["sha256"][:16]))

    manifest = {"surum": yeni, "notlar": notlar, "dosyalar": kayitlar}
    (YAYIN / "surum.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nSurum %s hazir -> %s" % (yeni, YAYIN))
    print("""
SIMDI NE YAPACAKSIN
-------------------
'yayin' klasorunun TAMAMINI (surum.json dahil) yayin adresine yukle.
Kardesinin ayarlar.json dosyasindaki 'guncelleme_url' bu adresteki
surum.json dosyasini gostermeli. Dosya adresleri surum.json'a gore
gorece cozulur, yani hepsi ayni klasorde durmali.

  GitHub kullaniyorsan:
      git add -A && git commit -m "surum %s" && git push

  Kendi sunucunu kullaniyorsan:
      scp -P 443 yayin/* kullanici@sunucu:/var/www/yuz-ayirici/

Kardesin programi bir sonraki acisinda "YENI SURUM VAR" uyarisini gorecek.
""" % yeni)
    return 0


if __name__ == "__main__":
    sys.exit(main())
