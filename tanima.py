#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tanima.py — Google Cloud Vision "web detection" ile kisi ismi onerme.

ISTEGE BAGLI ozelliktir. Kullanilmadigi surece hicbir veri disari cikmaz.
Kullanildiginda SADECE kisi basina birkac yuz kirpmasi Google'a gonderilir,
tum arsiv degil.

Anahtar nereden okunur (sirasiyla):
  1. GOOGLE_API_KEY ortam degiskeni
  2. program klasorundeki google_anahtar.txt dosyasi

Anahtar hicbir zaman kodun icine yazilmaz, GitHub'a gitmez (.gitignore'da).
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://vision.googleapis.com/v1/images:annotate"
ZAMAN_ASIMI = 40

# Kisi ismi olmayan, sik donen genel terimler
GENEL = {
    "person", "people", "face", "facial expression", "portrait", "photograph", "photo",
    "photo shoot", "portrait photography", "hair", "hairstyle", "eyebrow", "chin",
    "forehead", "nose", "lip", "cheek", "smile", "beauty", "model", "fashion",
    "fashion model", "actor", "actress", "celebrity", "human", "head", "eye",
    "glasses", "eyewear", "t-shirt", "shirt", "jacket", "image", "stock photography",
    "selfie", "black hair", "long hair", "facial hair", "beard", "moustache",
    "public figure", "gesture", "event", "crowd", "audience", "news", "press",
    "journalist", "photography", "portrait art", "screenshot", "video", "film",
    "television", "movie", "series", "getty images", "shutterstock", "alamy",
}

# Bir ismin kelimesi olabilecek karakterler (Turkce dahil)
KELIME = re.compile(r"^[A-ZÇĞİÖŞÜ][a-zçğıöşü'\.\-]{1,}$")


def anahtar_bul(klasor=None):
    """API anahtarini ortam degiskeninden ya da yerel dosyadan okur."""
    for ad in ("GOOGLE_API_KEY", "GOOGLE_VISION_ANAHTARI"):
        v = os.environ.get(ad, "").strip()
        if v:
            return v
    klasor = Path(klasor or Path(__file__).resolve().parent)
    f = klasor / "google_anahtar.txt"
    if f.exists():
        v = f.read_text(encoding="utf-8").strip()
        if v:
            return v
    return ""


def anahtar_yardimi():
    return (
        "Google Vision anahtari bulunamadi.\n"
        "  1. console.cloud.google.com adresinden bir proje acin\n"
        "  2. 'Cloud Vision API' servisini etkinlestirin\n"
        "  3. APIs & Services > Credentials > Create credentials > API key\n"
        "  4. Anahtari program klasorundeki 'google_anahtar.txt' dosyasina yapistirin\n"
        "     (tek satir, baska bir sey yazmayin)\n"
        "Anahtar bu dosyada kalir, GitHub'a gonderilmez."
    )


def isim_gibi_mi(metin):
    """'Kivanc Tatlitug' evet; 'facial expression' hayir."""
    metin = (metin or "").strip()
    if not metin or metin.lower() in GENEL:
        return False
    if len(metin) < 5 or len(metin) > 48:
        return False
    kelimeler = metin.split()
    if not (2 <= len(kelimeler) <= 4):
        return False
    if any(k.lower() in GENEL for k in kelimeler):
        return False
    return all(KELIME.match(k) for k in kelimeler)


def web_tespiti(jpeg_baytlari, anahtar, maks=12):
    """Google Vision WEB_DETECTION cagrisi. webDetection sozlugunu dondurur."""
    govde = {
        "requests": [{
            "image": {"content": base64.b64encode(jpeg_baytlari).decode("ascii")},
            "features": [{"type": "WEB_DETECTION", "maxResults": maks}],
        }]
    }
    url = API + "?key=" + urllib.parse.quote(anahtar, safe="")
    istek = urllib.request.Request(
        url, data=json.dumps(govde).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "yuz-ayirici"},
    )
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as r:
            cevap = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detay = json.loads(e.read().decode("utf-8"))
            mesaj = detay.get("error", {}).get("message", "")
        except Exception:
            mesaj = ""
        # Anahtar hicbir zaman ekrana basilmaz
        raise RuntimeError("Google Vision hatasi (%s): %s" % (e.code, mesaj or "detay yok"))
    yanit = (cevap.get("responses") or [{}])[0]
    if "error" in yanit:
        raise RuntimeError("Google Vision hatasi: %s" % yanit["error"].get("message", ""))
    return yanit.get("webDetection", {}) or {}


def adaylari_puanla(wd):
    """webDetection sonucundan {isim: puan} cikarir."""
    puanlar = {}

    def ekle(ad, p):
        ad = ad.strip()
        if isim_gibi_mi(ad):
            puanlar[ad] = puanlar.get(ad, 0.0) + p

    # 'best guess' Google'in kendi tahmini - en guclu sinyal
    for bg in wd.get("bestGuessLabels", []) or []:
        ekle(str(bg.get("label", "")).title() if str(bg.get("label", "")).islower()
             else str(bg.get("label", "")), 3.0)

    # web varliklari - skorlariyla birlikte
    for e in wd.get("webEntities", []) or []:
        ekle(str(e.get("description", "")), min(float(e.get("score") or 0.0), 2.0))

    return puanlar


def sayfa_ornekleri(wd, adet=3):
    """Onerinin nereden geldigini gosteren ornek sayfa basliklari."""
    out = []
    for s in (wd.get("pagesWithMatchingImages") or [])[:adet]:
        baslik = (s.get("pageTitle") or "").strip()
        if baslik:
            out.append(re.sub(r"<[^>]+>", "", baslik)[:90])
    return out
