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
    "pencere.py",
    "arayuz.html",
    "kutuphane.py",
    "etiket.py",
    "teslim.py",
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


def _kapanmamis_dize(js):
    """
    JS blogunda satir ortasinda kesilmis bir dize var mi?

    Bu hata uc kez cikti: kaynak metin bir kabuk/heredoc uzerinden gecerken
    ters bolu yeniyor ve "\\n" gercek satir sonuna donuyor. Sonuc: butun
    script blogu ayrisamiyor, arayuzun her dugmesi oluyor ama dosyaya
    bakinca hicbir sey yanlis gorunmuyor.

    Tarayici olmadan yakalamak icin kucuk bir sozcuk cozumleyici. Onemli
    ayrinti: kisi kartlari ic ice sablon dizesi kullaniyor
    (`... ${ liste.map(x => `...`) } ...`), bu yuzden baglam bir YIGIN
    ile izleniyor - yoksa icteki ters tirnak distakini kapatiyor sanilir.

    JS'te ' ve " dizeleri satir sonunu gecemez; satir biterken hala
    dizenin icindeysek hata kesindir.
    """
    NL = chr(10)
    ONCE_KAR = set("(,=:[!&|?{};+-*%~^<>")
    ONCE_SOZ = {"return", "typeof", "case", "in", "of", "do", "else"}
    yigin = [{"tur": "kod", "suslu": 0}]
    n, i, satir = len(js), 0, 1
    onceki = ""

    while i < n:
        c = js[i]
        ust = yigin[-1]

        if c == NL:
            satir += 1
            i += 1
            continue

        if ust["tur"] == "kod":
            if c == chr(92):
                i += 2
                continue
            if c == "/" and i + 1 < n and js[i + 1] == "/":
                while i < n and js[i] != NL:
                    i += 1
                continue
            if c == "/" and i + 1 < n and js[i + 1] == "*":
                i += 2
                while i + 1 < n and not (js[i] == "*" and js[i + 1] == "/"):
                    if js[i] == NL:
                        satir += 1
                    i += 1
                i += 2
                continue
            if c == "/":
                sozcuk = re.search(r"([A-Za-z_$]+)\s*$", js[max(0, i - 12):i])
                regex_mi = (not onceki) or (onceki in ONCE_KAR) or \
                           (sozcuk is not None and sozcuk.group(1) in ONCE_SOZ)
                i += 1
                if regex_mi:                      # duzenli ifadeyi atla
                    while i < n and js[i] not in (chr(47), NL):
                        if js[i] == chr(92):
                            i += 1
                        i += 1
                    i += 1
                onceki = c
                continue
            if c in ("'", chr(34)):               # tek/cift tirnakli dize
                tirnak, bas = c, satir
                i += 1
                while i < n and js[i] != tirnak:
                    if js[i] == chr(92):
                        i += 2
                        continue
                    if js[i] == NL:               # dize satir sonunu gecti
                        return bas, js.split(NL)[bas - 1].strip()[:90]
                    i += 1
                i += 1
                onceki = tirnak
                continue
            if c == "`":
                yigin.append({"tur": "sablon"})
                i += 1
                continue
            if c == "{":
                ust["suslu"] += 1
            elif c == "}":
                if ust["suslu"] > 0:
                    ust["suslu"] -= 1
                elif len(yigin) > 1:
                    yigin.pop()               # ${ ... } bitti, sablona don
            if not c.isspace():
                onceki = c
            i += 1
            continue

        # sablon dizesi icindeyiz
        if c == chr(92):
            i += 2
            continue
        if c == "`":
            yigin.pop()
            onceki = "`"
            i += 1
            continue
        if c == "$" and i + 1 < n and js[i + 1] == "{":
            yigin.append({"tur": "kod", "suslu": 0})
            onceki = ""
            i += 2
            continue
        i += 1

    return None


def js_kontrol(yol):
    """
    arayuz.html icindeki <script> blogunda kaba sozdizimi kontrolu.
    Gerekce: bir kez ic ice tirnak kacisi bozuldu ve 1.12.1-1.12.4 arasi
    tum surumlerde arayuzun butun dugmeleri calismaz hale geldi. Bu kontrol
    o hatanin tekrar yayinlanmasini engeller.
    """
    import re
    metin = Path(yol).read_text(encoding="utf-8")
    m = re.search(r"<script>(.*?)</script>", metin, re.S)
    if not m:
        return ["arayuz.html icinde <script> blogu yok"]
    betik = m.group(1)
    hatalar = []

    # HTML dizesi icinde kacissiz tirnak: onclick="fn('x')" gibi
    for i, satir in enumerate(betik.splitlines(), 1):
        s = satir.strip()
        if "onclick=" in s and ("'" in s or '"' in s):
            # tek tirnakli JS dizesi icinde kacissiz tek tirnak var mi
            if re.search(r"'[^'\n]*onclick=\"[^\"]*\('", s):
                hatalar.append("satir %d: onclick icinde kacissiz tirnak -> %s"
                               % (i, s[:70]))
    # Kapanmamis dize: "\\n" gercek satir sonuna donerse butun blok olur.
    kesik = _kapanmamis_dize(betik)
    if kesik:
        hatalar.append("satir %d: dize satir ortasinda kesilmis (muhtemelen "
                       "kacis karakteri yenmis) -> %s" % kesik)

    # kaba denge kontrolu
    if betik.count("{") != betik.count("}"):
        hatalar.append("suslu parantez dengesiz: %d ac / %d kapa"
                       % (betik.count("{"), betik.count("}")))
    if betik.count("(") != betik.count(")"):
        hatalar.append("parantez dengesiz: %d ac / %d kapa"
                       % (betik.count("("), betik.count(")")))
    return hatalar


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

    arayuz = BASE / "arayuz.html"
    if arayuz.exists():
        hatalar = js_kontrol(arayuz)
        if hatalar:
            print("!! arayuz.html JavaScript kontrolu basarisiz - YAYINLANMADI:")
            for h in hatalar:
                print("   " + h)
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
