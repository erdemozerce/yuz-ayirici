#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
guncelle.py — uzaktan guncelleme motoru.

Calisma mantigi:
  1. ayarlar.json icindeki 'guncelleme_url' adresinden surum.json cekilir (yalniz HTTPS).
  2. Uzak surum yereldekinden yeniyse dosyalar indirilir.
  3. Her dosyanin SHA-256 ozeti surum.json ile karsilastirilir; tutmuyorsa iptal.
  4. Eski dosyalar 'yedek/<surum>_<tarih>' klasorune kopyalanir, sonra degistirilir.
  5. Yeni surum numarasi surum.txt'e yazilir.

Tek basina da calisir:  python guncelle.py
"""

import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
SURUM_DOSYASI = BASE / "surum.txt"
AYARLAR = BASE / "ayarlar.json"
ZAMAN_ASIMI = 25


# ---------------------------------------------------------------- yardimcilar
def yerel_surum():
    if SURUM_DOSYASI.exists():
        s = SURUM_DOSYASI.read_text(encoding="utf-8").strip()
        if s:
            return s
    try:
        import re
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (BASE / "face_sorter.py").read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def surum_tuple(s):
    parts = []
    for p in str(s).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def ayarlari_oku():
    if AYARLAR.exists():
        try:
            return json.loads(AYARLAR.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def ayarlari_yaz(cfg):
    AYARLAR.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _indir(url):
    """Yalniz HTTPS. Bayt dizisi dondurur."""
    if not str(url).lower().startswith("https://"):
        raise ValueError("Guvenlik: sadece https:// adresleri kabul edilir -> " + str(url))
    req = urllib.request.Request(url, headers={"User-Agent": "yuz-ayirici-guncelleyici"})
    with urllib.request.urlopen(req, timeout=ZAMAN_ASIMI) as r:
        return r.read()


def _tam_url(manifest_url, dosya_url):
    if str(dosya_url).lower().startswith("https://"):
        return dosya_url
    return urllib.parse.urljoin(manifest_url, dosya_url)


# ------------------------------------------------------------------ kontrol
def kontrol_et(url=None):
    """Yeni surum varsa manifest dict'i, yoksa None dondurur."""
    cfg = ayarlari_oku()
    url = url or cfg.get("guncelleme_url", "")
    if not url:
        return None
    manifest = json.loads(_indir(url).decode("utf-8"))
    manifest["_url"] = url
    if surum_tuple(manifest.get("surum", "0")) > surum_tuple(yerel_surum()):
        return manifest
    return None


# -------------------------------------------------------------------- uygula
def uygula(manifest, log=print):
    """Manifestteki dosyalari indirir, dogrular ve yerine koyar."""
    manifest_url = manifest["_url"]
    yeni_surum = manifest.get("surum", "?")
    dosyalar = manifest.get("dosyalar", [])
    if not dosyalar:
        log("Guncellemede dosya yok.")
        return False

    # 1) hepsini once gecici klasore indir ve dogrula
    gecici = BASE / ".guncelleme_gecici"
    if gecici.exists():
        shutil.rmtree(gecici, ignore_errors=True)
    gecici.mkdir(parents=True)

    inen = []
    for d in dosyalar:
        ad = d["ad"]
        if "/" in ad or "\\" in ad or ad.startswith("."):
            raise ValueError("Guvenlik: gecersiz dosya adi -> " + ad)
        log(f"  indiriliyor: {ad}")
        veri = _indir(_tam_url(manifest_url, d["url"]))
        ozet = hashlib.sha256(veri).hexdigest()
        if ozet.lower() != str(d["sha256"]).lower():
            raise ValueError(f"Guvenlik: {ad} dosyasinin ozeti tutmuyor, guncelleme iptal.")
        (gecici / ad).write_bytes(veri)
        inen.append(ad)

    # 2) eskileri yedekle
    yedek = BASE / "yedek" / f"{yerel_surum()}_{time.strftime('%Y%m%d_%H%M%S')}"
    yedek.mkdir(parents=True, exist_ok=True)
    for ad in inen:
        eski = BASE / ad
        if eski.exists():
            shutil.copy2(eski, yedek / ad)

    # 3) yerine koy
    for ad in inen:
        shutil.copy2(gecici / ad, BASE / ad)
    shutil.rmtree(gecici, ignore_errors=True)

    SURUM_DOSYASI.write_text(str(yeni_surum), encoding="utf-8")
    log(f"Guncelleme tamam: surum {yeni_surum} ({len(inen)} dosya). Yedek: {yedek}")
    if manifest.get("notlar"):
        log("Degisiklikler: " + str(manifest["notlar"]))
    return True


# ------------------------------------------------------- sessiz gunluk kontrol
def gunluk_kontrol(log=print):
    """Gunde bir kez sessizce bakar. Internet yoksa sessizce gecer."""
    cfg = ayarlari_oku()
    if not cfg.get("otomatik_guncelleme", True) or not cfg.get("guncelleme_url"):
        return None
    if time.time() - float(cfg.get("son_kontrol", 0)) < 86400:
        return None
    try:
        m = kontrol_et(cfg["guncelleme_url"])
    except Exception:
        return None
    finally:
        cfg["son_kontrol"] = time.time()
        ayarlari_yaz(cfg)
    return m


def main():
    import sys as _sys
    bayraklar = {a.lower() for a in _sys.argv[1:]}
    yalniz_kontrol = "--kontrol" in bayraklar
    sormadan = bool({"--evet", "-y", "--yes"} & bayraklar)

    print("Yuz Ayirici guncelleme kontrolu...")
    print("Yerel surum:", yerel_surum())
    cfg = ayarlari_oku()
    if not cfg.get("guncelleme_url"):
        print("ayarlar.json icinde 'guncelleme_url' tanimli degil - guncelleme kapali.")
        return
    try:
        m = kontrol_et()
    except urllib.error.URLError as e:
        print("Internete ulasilamadi:", e)
        return
    except Exception as e:
        print("Hata:", e)
        return
    if not m:
        print("Program guncel.")
        return
    print(f"Yeni surum bulundu: {m.get('surum')}")
    if m.get("notlar"):
        print("Notlar:", m["notlar"])
    if yalniz_kontrol:
        print("(yalnizca kontrol edildi - guncellemek icin bayraksiz calistirin)")
        return
    if sormadan:
        uygula(m)
        return
    try:
        cevap = input("Guncellensin mi? (E/h): ").strip().lower()
    except EOFError:
        # Konsolsuz calistirildi (ornegin kisayoldan). Cokmek yerine anlat.
        print()
        print("Bu pencerede soru sorulamiyor.")
        print("Guncellemek icin: python guncelle.py --evet")
        print("Ya da programi acip sag ustteki 'Guncelleme var mi?' dugmesine basin.")
        return
    if cevap in ("", "e", "evet", "y", "yes"):
        uygula(m)
    else:
        print("Guncelleme atlandi.")


if __name__ == "__main__":
    main()
