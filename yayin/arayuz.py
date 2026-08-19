#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
arayuz.py — Yuz Ayirici'nin gorsel arayuzu.

Tarayicida acilan yerel bir panel. Internet YOK: sunucu yalniz 127.0.0.1
adresine baglanir, rastgele bir anahtarla korunur, disaridan erisilemez.
Ek kutuphane gerektirmez (Python'un kendi http.server'i kullanilir).

Calistirmak icin:  ARAYUZ.bat  ya da  python arayuz.py
"""

import base64
import json
import os
import queue
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import face_sorter as motor  # noqa: E402

ANAHTAR = secrets.token_urlsafe(16)
AYARLAR = BASE / "ayarlar.json"

# ---------------------------------------------------------------- durum
durum = {
    "calisiyor": False,
    "adim": "",
    "yapilan": 0,
    "toplam": 0,
    "hiz": 0.0,
    "kalan": "",
    "satirlar": [],
    "bitti": "",
    "hata": "",
    "son_kare": "",
}
kilit = threading.Lock()
dialog_kuyrugu = queue.Queue()
surec = {"p": None}


def surum_bilgisi():
    """Yerel surum ve (varsa) bekleyen guncelleme."""
    d = {"yerel": "?", "yeni": None, "notlar": "", "kontrol": False}
    try:
        import guncelle
        d["yerel"] = guncelle.yerel_surum()
        d["kontrol"] = bool(guncelle.ayarlari_oku().get("guncelleme_url"))
    except Exception:
        pass
    d.update(_guncelleme_durumu)
    return d


_guncelleme_durumu = {}


def guncelleme_ara(zorla=False):
    """Arka planda yeni surum var mi diye bakar; arayuze bildirir."""
    try:
        import guncelle
        m = guncelle.kontrol_et() if zorla else guncelle.gunluk_kontrol()
        if m:
            _guncelleme_durumu["yeni"] = m.get("surum")
            _guncelleme_durumu["notlar"] = m.get("notlar", "")
            _guncelleme_durumu["_manifest"] = m
        elif zorla:
            _guncelleme_durumu["yeni"] = None
            _guncelleme_durumu["notlar"] = ""
        return _guncelleme_durumu.get("yeni")
    except Exception as e:
        _guncelleme_durumu["hata"] = str(e)
        return None


def guncellemeyi_uygula():
    try:
        import guncelle
        m = _guncelleme_durumu.get("_manifest") or guncelle.kontrol_et()
        if not m:
            return False, "Guncel surum kullaniliyor."
        guncelle.uygula(m, log=lambda *x: None)
        _guncelleme_durumu.clear()
        return True, "Surum %s kuruldu. Programi kapatip yeniden acin." % m.get("surum")
    except Exception as e:
        return False, str(e)


def ayar_oku():
    varsayilan = {
        "kaynak_klasorler": [], "kaynak_klasor": "", "hedef_klasor": "",
        "db": str(BASE / "faces.db"),
        "eps": 0.50, "min_samples": 3, "mod": "auto",
        "duzen": "altklasor-kisi", "derinlik": 0, "etiket_mod": "gomulu",
        "secki_atla": False, "hizli_tarama": False, "kaliteli_tarama": False,
    "iki_asama": False, "tema": "sistem",
        "guncelleme_url": "", "otomatik_guncelleme": True, "son_kontrol": 0,
    }
    if AYARLAR.exists():
        try:
            varsayilan.update(json.loads(AYARLAR.read_text(encoding="utf-8")))
        except Exception:
            pass
    # eski tek klasorlu ayari listeye tasi
    if not varsayilan["kaynak_klasorler"] and varsayilan.get("kaynak_klasor"):
        varsayilan["kaynak_klasorler"] = [varsayilan["kaynak_klasor"]]
    return varsayilan


def ayar_yaz(cfg):
    AYARLAR.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- is calistirma
ILERLEME = re.compile(r"\[(\d+)/(\d+)\]\s+([\d.]+) foto/sn.*?kalan:\s*(.+?)\s*$")


def is_calistir(adim, argv):
    """face_sorter.py'yi alt surec olarak calistirir, ciktisini canli okur."""
    with kilit:
        if durum["calisiyor"]:
            return False
        durum.update(calisiyor=True, adim=adim, yapilan=0, toplam=0, hiz=0.0,
                     kalan="", satirlar=[], bitti="", hata="", son_kare="")

    def calis():
        try:
            p = subprocess.Popen(
                [sys.executable, "-u", str(BASE / "face_sorter.py")] + [str(a) for a in argv],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", cwd=str(BASE),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            surec["p"] = p
            for satir in p.stdout:
                satir = satir.rstrip()
                if not satir or satir.startswith(("Applied providers", "find model", "set det-size")):
                    continue
                if satir.startswith("::kare:: "):
                    with kilit:
                        durum["son_kare"] = satir[9:].strip()
                    continue
                m = ILERLEME.search(satir)
                with kilit:
                    if m:
                        durum["yapilan"] = int(m.group(1))
                        durum["toplam"] = int(m.group(2))
                        durum["hiz"] = float(m.group(3))
                        durum["kalan"] = m.group(4)
                    durum["satirlar"].append(satir)
                    durum["satirlar"] = durum["satirlar"][-14:]
            p.wait()
            with kilit:
                durum["bitti"] = adim
                if p.returncode != 0:
                    durum["hata"] = "Islem hata ile bitti (kod %s)" % p.returncode
        except Exception as e:
            with kilit:
                durum["hata"] = str(e)
        finally:
            with kilit:
                durum["calisiyor"] = False
            surec["p"] = None

    threading.Thread(target=calis, daemon=True).start()
    return True


def durdur():
    p = surec.get("p")
    if p and p.poll() is None:
        p.terminate()
        return True
    return False


# ---------------------------------------------------------------- veri okuma
def db_yolu():
    return ayar_oku().get("db") or str(BASE / "faces.db")


def ozet():
    yol = Path(db_yolu())
    d = {"fotograf": 0, "yuz": 0, "kisi": 0, "isimli": 0, "kutuphane": 0}
    if yol.exists():
        try:
            c = sqlite3.connect(str(yol))
            d["fotograf"] = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            d["yuz"] = c.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
            d["kisi"] = c.execute(
                "SELECT COUNT(DISTINCT cluster) FROM faces WHERE cluster>0").fetchone()[0]
            c.close()
        except Exception:
            pass
    d["isimli"] = sum(1 for v in motor.isim_csv_oku(BASE / "isimler.csv").values() if v)
    kut = BASE / "kisi_kutuphanesi.db"
    if kut.exists():
        try:
            c = sqlite3.connect(str(kut))
            d["kutuphane"] = c.execute("SELECT COUNT(*) FROM kisiler").fetchone()[0]
            c.close()
        except Exception:
            pass
    return d


_RESIM_BELLEK = {}      # yuz_id -> base64 kirpma (tarama degismedikce gecerli)


def kucuk_resim(kayit, boy=132):
    """Bir yuzu kirpip base64 JPEG dondurur. kayit = (yuz_id, yol, x1,y1,x2,y2, supheli)"""
    yuz_id, p, x1, y1, x2, y2 = kayit[0], kayit[1], kayit[2], kayit[3], kayit[4], kayit[5]
    anahtar = (db_yolu(), yuz_id)
    onbellek = _RESIM_BELLEK.get(anahtar)
    if onbellek is not None:
        return onbellek
    # 7728x5152'lik kareyi tam cozmek yuz basina ~0.7 sn suruyordu; kirpma
    # zaten 132 px'e inecegi icin JPEG'i dogrudan kucuk cozuyoruz.
    yuz_en = max(float(x2) - float(x1), 1.0)
    img, olcek = None, 1.0
    for bayrak, o in ((cv2.IMREAD_REDUCED_COLOR_4, 0.25),
                      (cv2.IMREAD_REDUCED_COLOR_2, 0.5)):
        if yuz_en * o >= boy * 0.70:
            try:
                veri = np.fromfile(str(p), dtype=np.uint8)
                img = cv2.imdecode(veri, bayrak)
            except Exception:
                img = None
            if img is not None:
                olcek = o
            break
    if img is None:
        img = motor.imread_unicode(p)
        olcek = 1.0
    if img is None:
        return None
    x1, y1, x2, y2 = (float(x1) * olcek, float(y1) * olcek,
                      float(x2) * olcek, float(y2) * olcek)
    h, w = img.shape[:2]
    mx, my = (x2 - x1) * 0.38, (y2 - y1) * 0.38
    a1, b1 = max(int(x1 - mx), 0), max(int(y1 - my), 0)
    a2, b2 = min(int(x2 + mx), w), min(int(y2 + my), h)
    kirpma = img[b1:b2, a1:a2]
    if kirpma.size == 0:
        return None
    kirpma = cv2.resize(kirpma, (boy, boy), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", kirpma, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        return None
    sonuc = "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")
    if len(_RESIM_BELLEK) < 4000:
        _RESIM_BELLEK[anahtar] = sonuc
    return sonuc


_KARE_BELLEK = {}       # dosya yolu -> base64 kucuk kare


def kare_onizleme(yol, boy=300):
    """Bir fotografin tamamini kucuk JPEG olarak dondurur (serit/canli onizleme)."""
    onbellek = _KARE_BELLEK.get(yol)
    if onbellek is not None:
        return onbellek
    try:
        img, _ = motor.imread_unicode(yol, kucult=boy)
    except Exception:
        return None
    if img is None:
        return None
    h, w = img.shape[:2]
    o = boy / max(h, w, 1)
    if o < 1:
        img = cv2.resize(img, (max(int(w * o), 1), max(int(h * o), 1)),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not ok:
        return None
    sonuc = "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")
    if len(_KARE_BELLEK) < 600:
        _KARE_BELLEK[yol] = sonuc
    return sonuc


def kisi_kareleri(cid, adet=12):
    """Bir kisinin karelerinden serit icin kucuk onizlemeler."""
    yol = Path(db_yolu())
    if not yol.exists():
        return []
    con = motor.db_connect(str(yol))
    try:
        satirlar = [r[0] for r in con.execute(
            "SELECT path FROM faces WHERE cluster=? GROUP BY path "
            "ORDER BY MAX(COALESCE(netlik,0)) DESC LIMIT ?", (cid, adet))]
    except Exception:
        satirlar = []
    con.close()
    cikti = []
    for yolu in satirlar:
        r = kare_onizleme(yolu)
        if r:
            cikti.append({"ad": os.path.basename(yolu), "klasor": os.path.dirname(yolu),
                          "resim": r})
    return cikti


def kutuphane_listesi():
    """Kutuphanedeki kisiler + kapak resimleri (base64)."""
    kut = BASE / "kisi_kutuphanesi.db"
    if not kut.exists():
        return []
    try:
        import kutuphane
        c = kutuphane.ac(kut)
        try:
            gorunum = {x["isim"]: x["gorunum"] for x in kutuphane.gorunum_ozeti(c)}
        except Exception:
            gorunum = {}
        out = []
        for isim, adet, eklenme, guncelleme, kapak in kutuphane.liste(c, kapakli=True):
            out.append({
                "isim": isim, "ornek": adet,
                "gorunum": gorunum.get(isim, 1),
                "eklenme": eklenme or "", "guncelleme": guncelleme or "",
                "kapak": ("data:image/jpeg;base64," + base64.b64encode(kapak).decode("ascii"))
                         if kapak else "",
            })
        c.close()
        return out
    except Exception:
        return []


# Kullanilabilirlik esikleri: secki (ayiklama) ile ayni degerler kullaniliyor
# ki rapor ile ayiklama ayni seyi "iyi kare" saysin.
NETLIK_TABAN = 22.0        # Laplacian varyansi - altinda gozle gorulur bulanik
MIN_YUZ_PX = 120.0         # bundan kucuk yuz baskiya/teslime uygun degil
GOZ_ORANI = 0.72           # kisinin kendi ortalamasinin altinda kalirsa goz kapali


def kapsama_verisi(con, ad_ver, en_az=5):
    """
    Kisi basina KULLANILABILIR kare sayisi.

    Neden: set fotografcisinin isi "her oyuncudan yayina girecek kare getirmek".
    Toplam kare sayisi yanilticidir - 40 karenin hepsi bulanik olabilir.
    Burada net, gozu acik ve yuzu yeterince buyuk kareleri sayiyoruz; sayisi
    dusuk olanlari isaretliyoruz ki set dagilmadan cekilebilsin.
    """
    satirlar = list(con.execute(
        "SELECT cluster, path, COALESCE(netlik,0), goz, (x2-x1) "
        "FROM faces WHERE cluster > 0"))
    if not satirlar:
        return []

    # goz acikligi kisiye gore degisiyor (birinin normali 0.14, digerinin 0.33),
    # bu yuzden mutlak esik degil, kisinin kendi ortancasi kullaniliyor.
    goz_kayit = {}
    for cid, _p, _n, g, _w in satirlar:
        if g is not None:
            goz_kayit.setdefault(cid, []).append(float(g))
    taban = {}
    for cid, degerler in goz_kayit.items():
        if len(degerler) >= 5:
            degerler = sorted(degerler)
            taban[cid] = degerler[len(degerler) // 2] * GOZ_ORANI

    toplam, iyi, kusur = {}, {}, {}
    for cid, p, netlik, goz, yuz_px in satirlar:
        toplam.setdefault(cid, set()).add(p)
        k = kusur.setdefault(cid, {"bulanik": 0, "kucuk": 0, "goz": 0})
        if netlik and netlik < NETLIK_TABAN:
            k["bulanik"] += 1
            continue
        if (yuz_px or 0) < MIN_YUZ_PX:
            k["kucuk"] += 1
            continue
        if cid in taban and goz is not None and float(goz) < taban[cid]:
            k["goz"] += 1
            continue
        iyi.setdefault(cid, set()).add(p)

    cikti = []
    for cid in sorted(toplam, key=lambda c: len(iyi.get(c, ()))):
        n_iyi = len(iyi.get(cid, ()))
        cikti.append({
            "kume": cid, "ad": ad_ver(cid),
            "kare": len(toplam[cid]), "kullanilabilir": n_iyi,
            "yetersiz": n_iyi < en_az,
            "bulanik": kusur[cid]["bulanik"], "kucuk": kusur[cid]["kucuk"],
            "goz": kusur[cid]["goz"],
        })
    return cikti


def topluluk_kareleri(kare_kisi, ad_ver, adet=15):
    """En cok oyuncunun bir arada oldugu kareler - tanitim/afis icin istenen."""
    sirali = sorted(kare_kisi.items(), key=lambda kv: -len(kv[1]))
    cikti = []
    for yolu, kumeler in sirali[:adet]:
        if len(kumeler) < 2:
            break
        cikti.append({"ad": os.path.basename(yolu), "klasor": os.path.dirname(yolu),
                      "kisi_sayisi": len(kumeler),
                      "kisiler": ", ".join(sorted(ad_ver(c) for c in kumeler))})
    return cikti


def _olculeri_tamamla(con, yollar, sinir=400):
    """
    Eksik en/boy bilgisini dosya BASLIGINDAN okur (kareyi cozmeden).
    Eski veritabanlarinda bu sutunlar bos; tek seferlik doldurulur.
    """
    eksik = [p for p in yollar if p]
    if not eksik:
        return
    try:
        from PIL import Image
    except Exception:
        return
    yazilacak = []
    for p in eksik[:sinir]:
        try:
            with Image.open(p) as im:
                try:                       # etiketli dikey kare gercekte dikeydir
                    yon = int((im.getexif() or {}).get(274, 1))
                except Exception:
                    yon = 1
                en, boy = im.size
                if yon in (5, 6, 7, 8):
                    en, boy = boy, en
            yazilacak.append((en, boy, p))
        except Exception:
            continue
    if yazilacak:
        con.executemany("UPDATE files SET en=?, boy=? WHERE path=?", yazilacak)
        con.commit()


def dikey_kapsama(con, kare_kisi, ad_ver):
    """
    Hangi oyuncunun hic DIKEY karesi yok? Sosyal medya dikey istiyor,
    yatay arsivden dikey kare uretilemiyor.
    """
    eksikler = [r[0] for r in con.execute(
        "SELECT path FROM files WHERE (en IS NULL OR boy IS NULL) AND n_faces > 0")]
    if eksikler:
        _olculeri_tamamla(con, eksikler)
    yon = {p: (en, boy) for p, en, boy in con.execute(
        "SELECT path, en, boy FROM files WHERE en IS NOT NULL AND boy IS NOT NULL")}
    if not yon:
        return []
    sayac = {}
    for yolu, kumeler in kare_kisi.items():
        olcu = yon.get(yolu)
        if not olcu:
            continue
        dikey = olcu[1] > olcu[0]
        for c in kumeler:
            k = sayac.setdefault(c, [0, 0])
            k[1 if dikey else 0] += 1
    return [{"kume": c, "ad": ad_ver(c), "yatay": v[0], "dikey": v[1],
             "yok": v[1] == 0}
            for c, v in sorted(sayac.items(), key=lambda kv: kv[1][1])]


GERI_AL_SEMA = """
CREATE TABLE IF NOT EXISTS geri_al(
    parti    INTEGER,
    zaman    TEXT,
    aciklama TEXT,
    yuz      INTEGER,
    kume     INTEGER
);
CREATE TABLE IF NOT EXISTS geri_al_isim(
    parti   INTEGER PRIMARY KEY,
    icerik  TEXT
);
"""


def geri_al_kaydet(aciklama, yuz_idler=None, kumeler=None):
    """
    Duzeltme oncesi durumu bir partiye yazar.

    yuz_idler verilirse o yuzler, kumeler verilirse o kumelerdeki tum yuzler
    kaydedilir. isimler.csv de saklanir cunku birlestirme isim satirlarini
    da degistiriyor.
    """
    yol = Path(db_yolu())
    if not yol.exists():
        return
    try:
        con = motor.db_connect(str(yol))
        con.executescript(GERI_AL_SEMA)
        if yuz_idler:
            satirlar = list(con.execute(
                "SELECT id, cluster FROM faces WHERE id IN (%s)"
                % ",".join("?" * len(yuz_idler)), [int(y) for y in yuz_idler]))
        elif kumeler:
            satirlar = list(con.execute(
                "SELECT id, cluster FROM faces WHERE cluster IN (%s)"
                % ",".join("?" * len(kumeler)), [int(k) for k in kumeler]))
        else:
            con.close()
            return
        if not satirlar:
            con.close()
            return
        parti = (con.execute("SELECT COALESCE(MAX(parti),0)+1 FROM geri_al").fetchone()[0])
        simdi = time.strftime("%Y-%m-%d %H:%M:%S")
        con.executemany("INSERT INTO geri_al(parti,zaman,aciklama,yuz,kume) "
                        "VALUES(?,?,?,?,?)",
                        [(parti, simdi, aciklama, y, k) for y, k in satirlar])
        isim_dosya = BASE / "isimler.csv"
        if isim_dosya.exists():
            con.execute("INSERT OR REPLACE INTO geri_al_isim(parti,icerik) VALUES(?,?)",
                        (parti, isim_dosya.read_text(encoding="utf-8-sig")))
        # gecmisi sinirli tut
        con.execute("DELETE FROM geri_al WHERE parti <= ?", (parti - 20,))
        con.execute("DELETE FROM geri_al_isim WHERE parti <= ?", (parti - 20,))
        con.commit()
        con.close()
    except Exception:
        pass


def geri_al_listesi():
    yol = Path(db_yolu())
    if not yol.exists():
        return []
    try:
        con = motor.db_connect(str(yol))
        con.executescript(GERI_AL_SEMA)
        satirlar = list(con.execute(
            "SELECT parti, zaman, aciklama, COUNT(*) FROM geri_al "
            "GROUP BY parti ORDER BY parti DESC LIMIT 10"))
        con.close()
        return [{"parti": p, "zaman": z, "aciklama": a, "yuz": n}
                for p, z, a, n in satirlar]
    except Exception:
        return []


def geri_al_uygula(parti=None):
    """Son (ya da belirtilen) partiyi geri yukler."""
    yol = Path(db_yolu())
    if not yol.exists():
        return False, "Once tarama yapin"
    try:
        con = motor.db_connect(str(yol))
        con.executescript(GERI_AL_SEMA)
        if parti is None:
            satir = con.execute("SELECT MAX(parti) FROM geri_al").fetchone()
            parti = satir[0] if satir else None
        if not parti:
            con.close()
            return False, "Geri alinacak islem yok"
        kayitlar = list(con.execute(
            "SELECT yuz, kume, aciklama FROM geri_al WHERE parti = ?", (parti,)))
        if not kayitlar:
            con.close()
            return False, "Bu islem bulunamadi"
        aciklama = kayitlar[0][2]
        con.executemany("UPDATE faces SET cluster = ? WHERE id = ?",
                        [(k, y) for y, k, _a in kayitlar])
        isim = con.execute("SELECT icerik FROM geri_al_isim WHERE parti = ?",
                           (parti,)).fetchone()
        if isim and isim[0]:
            (BASE / "isimler.csv").write_text(isim[0], encoding="utf-8-sig")
        con.execute("DELETE FROM geri_al WHERE parti >= ?", (parti,))
        con.execute("DELETE FROM geri_al_isim WHERE parti >= ?", (parti,))
        con.commit()
        con.close()
        _RESIM_BELLEK.clear()
        return True, "Geri alindi: %s (%d yuz)" % (aciklama, len(kayitlar))
    except Exception as e:
        return False, str(e)


def veritabani_yedegi(etiket=""):
    """
    Riskli islem oncesi veritabaninin kopyasini alir.

    Gerekce: 10.000 karelik tarama 5 saat suruyor. Dosya bozulursa ya da
    yanlis bir yeniden gruplama yapilirsa bu emek gider; kutuphanenin
    yedegi vardi ama taramanin yoktu.
    """
    yol = Path(db_yolu())
    if not yol.exists():
        return None
    try:
        klasor = yol.parent / "yedek"
        klasor.mkdir(exist_ok=True)
        ad = "%s-%s%s.db" % (yol.stem, time.strftime("%Y%m%d-%H%M%S"),
                             ("-" + etiket) if etiket else "")
        hedef = klasor / ad
        shutil.copy2(str(yol), str(hedef))
        # son 5 yedegi tut
        eskiler = sorted(klasor.glob(yol.stem + "-*.db"))
        for e in eskiler[:-5]:
            try:
                e.unlink()
            except OSError:
                pass
        return str(hedef)
    except Exception:
        return None


def neden_bu_kisi(yuz_id):
    """
    Bir yuzun neden bu kisiye konuldugunu gosterir: kisinin merkezine
    benzerligi, ayni kisiden en yakin ornekler ve BASKA kisilerden en yakin
    ornek. Boylece kullanici karari denetleyebilir.
    """
    yol = Path(db_yolu())
    if not yol.exists():
        return {}
    con = motor.db_connect(str(yol))
    satir = con.execute(
        "SELECT id, path, x1, y1, x2, y2, emb, cluster, supheli, netlik "
        "FROM faces WHERE id = ?", (int(yuz_id),)).fetchone()
    if not satir:
        con.close()
        return {}
    import numpy as _np
    hedef_emb = _np.frombuffer(satir[6], _np.float32)
    hedef_emb = hedef_emb / (_np.linalg.norm(hedef_emb) + 1e-9)
    cid = satir[7]

    isimler = motor.isim_csv_oku(BASE / "isimler.csv")

    def ad(c):
        return isimler.get(c) or ("kisi_%04d" % c)

    hepsi = list(con.execute(
        "SELECT id, path, x1, y1, x2, y2, emb, cluster FROM faces WHERE cluster > 0"))
    con.close()
    if not hepsi:
        return {}
    E = _np.vstack([_np.frombuffer(r[6], _np.float32) for r in hepsi])
    E = E / (_np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
    benzerlik = E @ hedef_emb

    ayni, baska = [], []
    for i, r in enumerate(hepsi):
        if r[0] == satir[0]:
            continue
        (ayni if r[7] == cid else baska).append((float(benzerlik[i]), i))
    ayni.sort(reverse=True)
    baska.sort(reverse=True)

    kendi = [i for i, r in enumerate(hepsi) if r[7] == cid]
    merkez = E[kendi].mean(axis=0)
    merkez /= _np.linalg.norm(merkez) + 1e-9

    def kart(b, i):
        r = hepsi[i]
        return {"benzerlik": round(b, 3), "ad": os.path.basename(r[1]),
                "kisi": ad(r[7]),
                "resim": kucuk_resim((r[0], r[1], r[2], r[3], r[4], r[5], None, None), 96)}

    return {
        "yuz": int(satir[0]),
        "kisi": ad(cid),
        "dosya": os.path.basename(satir[1]),
        "resim": kucuk_resim((satir[0], satir[1], satir[2], satir[3], satir[4],
                              satir[5], satir[8], satir[9]), 132),
        "merkeze": round(float(hedef_emb @ merkez), 3),
        "supheli": satir[8] is not None,
        "netlik": round(float(satir[9] or 0), 1),
        "ayni": [kart(b, i) for b, i in ayni[:4]],
        "baska": [kart(b, i) for b, i in baska[:3]],
    }


def rapor_verisi():
    """Rapor sayfasi icin ozet + birlikte gorunme."""
    yol = Path(db_yolu())
    if not yol.exists():
        return {}
    try:
        con = motor.db_connect(str(yol))
        isimler = motor.isim_csv_oku(BASE / "isimler.csv")

        def ad(cid):
            return isimler.get(cid) or ("kisi_%04d" % cid)

        kisiler = [{"kume": c, "ad": ad(c), "fotograf": f, "yuz": y}
                   for c, f, y in con.execute(
                       "SELECT cluster, COUNT(DISTINCT path), COUNT(*) FROM faces "
                       "WHERE cluster > 0 GROUP BY cluster ORDER BY COUNT(DISTINCT path) DESC")]

        kare_kisi = {}
        for cid, p in con.execute(
                "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"):
            kare_kisi.setdefault(p, set()).add(cid)
        beraber = {}
        for kumeler in kare_kisi.values():
            k = sorted(kumeler)
            for i in range(len(k)):
                for j in range(i + 1, len(k)):
                    beraber[(k[i], k[j])] = beraber.get((k[i], k[j]), 0) + 1
        ikili = [{"a": ad(x), "b": ad(y), "adet": n}
                 for (x, y), n in sorted(beraber.items(), key=lambda z: -z[1])[:30]]

        klasorler = {}
        for (p,) in con.execute("SELECT path FROM files WHERE n_faces > 0"):
            k = os.path.dirname(p)
            klasorler[k] = klasorler.get(k, 0) + 1
        dagilim = [{"klasor": k, "adet": n}
                   for k, n in sorted(klasorler.items(), key=lambda z: -z[1])[:12]]

        # --- BOLUM: kaynak klasore gore ilk alt klasor. Kardesin arsivi
        # "... / 9. Bolum / raw-jpeg" seklinde; bolum adi budur.
        # Kapsayici klasor adlari: bunlar bolum adi olamaz, arsivde her
        # bolumun altinda ayni isimle bulunurlar.
        KAPSAYICI = {"raw", "jpeg", "jpg", "rawjpeg", "raw-jpeg", "rawjpg",
                     "dcim", "export", "cikti", "foto", "fotograf", "fotograflar",
                     "images", "img", "photos", "orijinal", "original", "temp"}

        def bolum_adi(yol, kok):
            if not kok:
                return os.path.basename(os.path.dirname(yol)) or "(kok)"
            kok_adi = os.path.basename(os.path.normpath(kok)) or "(kok)"
            bagil = motor.bagil_klasor(yol, kok, 1)
            ad = str(bagil)
            if ad in (".", ""):
                return kok_adi
            sade = ad.lower().replace(" ", "").replace("_", "").replace("-", "")
            if sade in KAPSAYICI:
                # "9. Bolum/raw-jpeg" -> bolum adi "9. Bolum" olmali
                return kok_adi
            return ad

        kare_bolum, bolum_kare, bolum_yuzsuz = {}, {}, {}
        for yolu, kok, nf in con.execute("SELECT path, kok, n_faces FROM files"):
            b = bolum_adi(yolu, kok)
            kare_bolum[yolu] = b
            bolum_kare[b] = bolum_kare.get(b, 0) + 1
            if not nf:
                bolum_yuzsuz[b] = bolum_yuzsuz.get(b, 0) + 1

        # kisi x bolum caprazi
        capraz, bolum_kisi = {}, {}
        for cid, yolu in con.execute(
                "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"):
            b = kare_bolum.get(yolu) or "(bilinmiyor)"
            capraz[(cid, b)] = capraz.get((cid, b), 0) + 1
            bolum_kisi.setdefault(b, set()).add(cid)

        bolum_sira = sorted(bolum_kare, key=lambda b: -bolum_kare[b])
        bolumler = []
        for b in bolum_sira:
            enler = sorted(((c, n) for (c, bb), n in capraz.items() if bb == b),
                           key=lambda z: -z[1])[:3]
            bolumler.append({
                "bolum": b, "kare": bolum_kare[b],
                "kisi": len(bolum_kisi.get(b, ())),
                "yuzsuz": bolum_yuzsuz.get(b, 0),
                "enler": [{"ad": ad(c), "adet": n} for c, n in enler],
            })

        capraz_tablo = {
            "bolumler": bolum_sira[:12],
            "satirlar": [{"ad": ad(k["kume"]),
                          "hucreler": [capraz.get((k["kume"], b), 0)
                                       for b in bolum_sira[:12]],
                          "toplam": k["fotograf"]}
                         for k in kisiler[:40]],
        }

        # --- TARAMA KARNESI
        try:
            toplam_kare = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            yuzsuz = con.execute("SELECT COUNT(*) FROM files WHERE n_faces=0").fetchone()[0]
            toplam_yuz = con.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
            gruplanmayan = con.execute(
                "SELECT COUNT(*) FROM faces WHERE cluster <= 0").fetchone()[0]
            n_supheli = con.execute(
                "SELECT COUNT(*) FROM faces WHERE supheli IS NOT NULL").fetchone()[0]
        except Exception:
            toplam_kare = yuzsuz = toplam_yuz = gruplanmayan = n_supheli = 0
        karne = {
            "kare": toplam_kare, "yuzsuz": yuzsuz, "yuz": toplam_yuz,
            "gruplanmayan": gruplanmayan, "supheli": n_supheli,
            "kisi": len(kisiler),
            "yuzsuz_oran": round(100.0 * yuzsuz / toplam_kare, 1) if toplam_kare else 0.0,
            # yuz bulunamayan orani yuksek klasorler: yeniden taranmasi gerekebilir
            "zayif": sorted(
                ({"bolum": b, "kare": bolum_kare[b], "yuzsuz": bolum_yuzsuz.get(b, 0),
                  "oran": round(100.0 * bolum_yuzsuz.get(b, 0) / bolum_kare[b], 1)}
                 for b in bolum_sira if bolum_kare[b] >= 5),
                key=lambda z: -z["oran"])[:8],
        }

        # --- KAPSAMA / SAHNE / TOPLULUK / DIKEY
        kapsama = kapsama_verisi(con, ad)
        topluluk = topluluk_kareleri(kare_kisi, ad)
        dikey = dikey_kapsama(con, kare_kisi, ad)
        try:
            kare_sahne, sahne_ozet = motor.sahne_bloklari(con)
        except Exception:
            kare_sahne, sahne_ozet = {}, []
        for x in sahne_ozet:                      # her sahnede kimler var
            kumeler = set()
            for yolu, no in kare_sahne.items():
                if no == x["no"]:
                    kumeler |= kare_kisi.get(yolu, set())
            x["kisi"] = len(kumeler)
            x["kisiler"] = ", ".join(sorted(ad(c) for c in kumeler)[:6])

        # --- SUPHELI KARELER
        try:
            supheli_liste = [
                {"ad": os.path.basename(pp), "klasor": os.path.dirname(pp),
                 "kisi": ad(cc), "benzerlik": round(float(bb or 0), 3)}
                for pp, cc, bb in con.execute(
                    "SELECT path, cluster, supheli FROM faces "
                    "WHERE supheli IS NOT NULL ORDER BY supheli LIMIT 400")]
        except Exception:
            supheli_liste = []

        try:
            isaretli = con.execute(
                "SELECT COUNT(*) FROM secki WHERE bayrak != ''").fetchone()[0]
        except Exception:
            isaretli = 0
        try:
            vetolu = con.execute(
                "SELECT COUNT(*) FROM onay WHERE durum='red'").fetchone()[0]
        except Exception:
            vetolu = 0
        con.close()
        return {"kisiler": kisiler, "ikili": ikili, "dagilim": dagilim,
                "isaretli": isaretli, "vetolu": vetolu,
                "bolumler": bolumler, "capraz": capraz_tablo,
                "karne": karne, "supheli": supheli_liste,
                "kapsama": kapsama, "topluluk": topluluk, "dikey": dikey,
                "sahneler": sahne_ozet}
    except Exception:
        return {}


def _kare_kisi(con):
    d = {}
    for cid, p in con.execute(
            "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"):
        d.setdefault(p, set()).add(cid)
    return d


def arama_yap(kumeler, herhangi=False, sinir=400):
    """
    Secilen kisilerin birlikte (ya da herhangi biri) gorundugu kareler.
    Sonuc KLASORE GORE gruplanir; kucuk resim uretilmez - aninda doner.
    """
    yol = Path(db_yolu())
    if not yol.exists() or not kumeler:
        return {"adet": 0, "yollar": [], "gruplar": []}
    con = motor.db_connect(str(yol))
    istenen = set(int(k) for k in kumeler)
    kk = _kare_kisi(con)

    bulunan = ([p for p, s in kk.items() if s & istenen] if herhangi
               else [p for p, s in kk.items() if istenen <= s])
    bulunan.sort()

    elenen, veto = set(), set()
    try:
        elenen = {r[0] for r in con.execute("SELECT path FROM secki WHERE bayrak != ''")}
    except Exception:
        pass
    try:
        veto = {r[0] for r in con.execute("SELECT path FROM onay WHERE durum='red'")}
    except Exception:
        pass
    con.close()

    gruplar = {}
    for p in bulunan:
        gruplar.setdefault(os.path.dirname(p), []).append(p)

    cikti = []
    kalan = sinir
    for klasor in sorted(gruplar):
        dosyalar = gruplar[klasor]
        gosterilen = dosyalar[:max(kalan, 0)]
        kalan -= len(gosterilen)
        cikti.append({
            "klasor": klasor,
            "adet": len(dosyalar),
            "dosyalar": [{"ad": os.path.basename(p),
                          "isaretli": p in elenen,
                          "vetolu": p in veto} for p in gosterilen],
            "kirpildi": len(dosyalar) - len(gosterilen),
        })
        if kalan <= 0:
            break

    return {"adet": len(bulunan), "yollar": bulunan, "gruplar": cikti,
            "klasor_sayisi": len(gruplar),
            "isaretli": len([p for p in bulunan if p in elenen]),
            "vetolu": len([p for p in bulunan if p in veto])}


def kisiler_listesi(adet=5):
    yol = Path(db_yolu())
    if not yol.exists():
        return []
    con = motor.db_connect(str(yol))
    isimler = motor.isim_csv_oku(BASE / "isimler.csv")
    oner = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "SELECT cluster, onerilen, puan, sayfalar FROM oneriler")}
    out = []
    for cid, nfoto, nyuz in con.execute(
        "SELECT cluster, COUNT(DISTINCT path), COUNT(*) FROM faces WHERE cluster>0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC"
    ):
        ornekler = motor.kume_ornekleri(con, cid, adet)
        # En net yuz: kutuphaneye ogretirken kapak olarak bu kare secilir.
        netlikler = [(k[7] or 0.0) for k in ornekler]
        en_net_id = None
        if netlikler and max(netlikler) > 0:
            en_net_id = ornekler[netlikler.index(max(netlikler))][0]
        resimler = []
        for k in ornekler:
            r = kucuk_resim(k)
            if r:
                resimler.append({"id": k[0], "resim": r,
                                 "supheli": k[6] is not None,
                                 "ennet": k[0] == en_net_id})
        n_supheli = con.execute(
            "SELECT COUNT(DISTINCT path) FROM faces WHERE cluster=? AND supheli IS NOT NULL",
            (cid,)).fetchone()[0]
        o = oner.get(cid) or (None, 0.0, "")
        out.append({
            "kume": cid, "fotograf": nfoto, "yuz": nyuz,
            "isim": isimler.get(cid, ""),
            "onerilen": o[0] or "",
            "benzerlik": round(float(o[1] or 0), 2),
            "supheli": n_supheli,
            "resimler": resimler,
        })
    con.close()
    return out


def isim_kaydet(kume, isim):
    yol = BASE / "isimler.csv"
    con = motor.db_connect(db_yolu())
    motor.isim_csv_yaz(con, yol)          # eksik satirlari tamamla
    mevcut = motor.isim_csv_oku(yol)
    mevcut[int(kume)] = (isim or "").strip()

    import csv as _csv
    satirlar = []
    with open(yol, newline="", encoding="utf-8-sig") as fh:
        okuyucu = _csv.DictReader(fh, delimiter=";")
        basliklar = okuyucu.fieldnames
        for row in okuyucu:
            k = int(row["kume_no"])
            row["isim"] = mevcut.get(k, row.get("isim", ""))
            satirlar.append(row)
    with open(yol, "w", newline="", encoding="utf-8-sig") as fh:
        w = _csv.DictWriter(fh, fieldnames=basliklar, delimiter=";")
        w.writeheader()
        w.writerows(satirlar)
    con.close()
    return True


def kutuphane_isimleri():
    kut = BASE / "kisi_kutuphanesi.db"
    if not kut.exists():
        return []
    try:
        import kutuphane
        c = kutuphane.ac(kut)
        out = [r[0] for r in kutuphane.liste(c)]
        c.close()
        return out
    except Exception:
        return []


# ---------------------------------------------------------------- http
class Vekil(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _yetki(self, sorgu):
        return sorgu.get("t", [""])[0] == ANAHTAR

    def _json(self, veri, kod=200):
        govde = json.dumps(veri, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/" and self._yetki(q):
            govde = (BASE / "arayuz.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(govde)))
            self.end_headers()
            self.wfile.write(govde)
            return
        if not self._yetki(q):
            self.send_response(403)
            self.end_headers()
            return
        if u.path == "/api/durum":
            with kilit:
                d = dict(durum)
            d["ozet"] = ozet()
            d["ayar"] = ayar_oku()
            d["kutuphane_isimleri"] = kutuphane_isimleri()
            d["surum"] = surum_bilgisi()
            return self._json(d)
        if u.path == "/api/kisiler":
            return self._json({"kisiler": kisiler_listesi()})
        if u.path == "/api/neden":
            yuz = q.get("yuz", [""])[0]
            if not yuz:
                return self._json({})
            try:
                return self._json(neden_bu_kisi(int(yuz)))
            except Exception as e:
                return self._json({"hata": str(e)}, 400)

        if u.path == "/api/geri-al-liste":
            return self._json({"islemler": geri_al_listesi()})

        if u.path == "/api/son-kare":
            with kilit:
                yolu = durum.get("son_kare") or ""
            if not yolu or not os.path.exists(yolu):
                return self._json({"resim": "", "ad": ""})
            return self._json({"resim": kare_onizleme(yolu) or "",
                               "ad": os.path.basename(yolu)})

        if u.path == "/api/kisi-kareler":
            kume = q.get("kume", [""])[0]
            if not kume:
                return self._json({"kareler": []})
            return self._json({"kareler": kisi_kareleri(int(kume))})

        if u.path == "/api/supheli":
            kume = q.get("kume", [""])[0]
            yol = Path(db_yolu())
            if not yol.exists() or not kume:
                return self._json({"kareler": []})
            con = motor.db_connect(str(yol))
            try:
                satirlar = con.execute(
                    "SELECT path, supheli FROM faces WHERE cluster=? AND supheli IS NOT NULL "
                    "ORDER BY supheli", (int(kume),)).fetchall()
            except Exception:
                satirlar = []
            con.close()
            return self._json({"kareler": [
                {"ad": os.path.basename(p), "klasor": os.path.dirname(p),
                 "benzerlik": round(float(b or 0), 3)} for p, b in satirlar]})

        if u.path == "/api/benzer-kisiler":
            kut = BASE / "kisi_kutuphanesi.db"
            if not kut.exists():
                return self._json({"oneriler": []})
            try:
                import kutuphane
                c = kutuphane.ac(kut)
                oneriler = kutuphane.benzer_kisiler(c)
                c.close()
                return self._json({"oneriler": oneriler})
            except Exception as e:
                return self._json({"oneriler": [], "hata": str(e)})

        if u.path == "/api/kutuphane":
            return self._json({"kisiler": kutuphane_listesi()})
        if u.path == "/api/rapor":
            return self._json(rapor_verisi())
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._yetki(q):
            self.send_response(403)
            self.end_headers()
            return
        uzunluk = int(self.headers.get("Content-Length") or 0)
        try:
            veri = json.loads(self.rfile.read(uzunluk) or b"{}")
        except Exception:
            veri = {}
        cfg = ayar_oku()

        if u.path == "/api/klasor":
            tip = veri.get("tip", "kaynak")
            if tip == "kaynak_sil":
                i = int(veri.get("sira", -1))
                liste = cfg.get("kaynak_klasorler", [])
                if 0 <= i < len(liste):
                    liste.pop(i)
                    cfg["kaynak_klasorler"] = liste
                    cfg["kaynak_klasor"] = liste[0] if liste else ""
                    ayar_yaz(cfg)
                return self._json({"ok": True})

            if tip == "serbest":
                cevap = queue.Queue()
                dialog_kuyrugu.put(("Kaydedilecek klasoru secin",
                                    veri.get("baslangic") or "", cevap))
                try:
                    yol = cevap.get(timeout=300)
                except queue.Empty:
                    return self._json({"hata": "Klasor penceresi acilamadi"}, 500)
                if yol is None:
                    return self._json({"hata": "Klasor penceresi calismiyor"}, 500)
                return self._json({"yol": yol})

            hedef_mi = (tip == "hedef")

            # Kullanici yolu elle yapistirdiysa pencere acmaya gerek yok
            elle = (veri.get("yol") or "").strip().strip('"')
            if elle:
                if not os.path.isdir(elle):
                    return self._json({"hata": "Boyle bir klasor yok: %s" % elle}, 400)
                yol = str(Path(elle))
            else:
                baslangic = (cfg.get("hedef_klasor") if hedef_mi
                             else (cfg.get("kaynak_klasorler") or [""])[-1])
                cevap = queue.Queue()
                dialog_kuyrugu.put((
                    "Kisi klasorleri nereye olusturulsun?" if hedef_mi
                    else "Fotograf klasoru secin (alt klasorler de taranir)",
                    baslangic or "", cevap))
                try:
                    yol = cevap.get(timeout=300)
                except queue.Empty:
                    return self._json(
                        {"hata": "Klasor secme penceresi acilamadi. "
                                 "Yolu asagidaki kutuya elle yapistirabilirsiniz."}, 500)
                if yol is None:
                    return self._json(
                        {"hata": "Klasor secme penceresi bu bilgisayarda calismiyor. "
                                 "Yolu asagidaki kutuya elle yapistirin."}, 500)
            if yol:
                if hedef_mi:
                    cfg["hedef_klasor"] = yol
                else:
                    liste = cfg.get("kaynak_klasorler", [])
                    if yol not in liste:
                        liste.append(yol)
                    cfg["kaynak_klasorler"] = liste
                    cfg["kaynak_klasor"] = liste[0]
                ayar_yaz(cfg)
            return self._json({"yol": yol})

        if u.path == "/api/ayar":
            for k in ("eps", "min_samples", "mod", "duzen", "derinlik", "etiket_mod",
                      "secki_atla", "hizli_tarama", "kaliteli_tarama", "iki_asama",
                    "tema"):
                if k in veri:
                    cfg[k] = veri[k]
            ayar_yaz(cfg)
            return self._json({"ok": True})

        if u.path == "/api/isim":
            isim_kaydet(veri.get("kume"), veri.get("isim", ""))
            return self._json({"ok": True})

        if u.path == "/api/ara":
            sonuc = arama_yap(veri.get("kumeler") or [], bool(veri.get("herhangi")))
            Vekil.son_arama = sonuc["yollar"]
            return self._json({k: v for k, v in sonuc.items() if k != "yollar"})

        if u.path == "/api/ara-eylem":
            yollar = list(getattr(Vekil, "son_arama", []) or [])
            if not yollar:
                return self._json({"hata": "Once arama yapin"}, 400)
            islem = veri.get("islem")
            if islem == "liste":
                bicim = (veri.get("bicim") or "txt-tam").lower()
                klasor = (veri.get("klasor") or "").strip() or str(BASE)
                if not os.path.isdir(klasor):
                    return self._json({"hata": "Klasor bulunamadi: %s" % klasor}, 400)
                uzanti = ".csv" if bicim.startswith("csv") else ".txt"
                ad = (veri.get("ad") or "").strip() or ("arama-sonucu-" +
                                                        time.strftime("%Y%m%d-%H%M"))
                for kotu in '<>:"/\\|?*':
                    ad = ad.replace(kotu, "_")
                if not ad.lower().endswith(uzanti):
                    ad += uzanti
                hedef = Path(klasor) / ad

                if bicim == "txt-ad":
                    icerik = "\n".join(os.path.basename(p) for p in yollar)
                elif bicim.startswith("csv"):
                    import csv as _csv
                    import io as _io
                    con = motor.db_connect(db_yolu())
                    isimler = motor.isim_csv_oku(BASE / "isimler.csv")
                    kk = _kare_kisi(con)
                    try:
                        elenen = {r[0] for r in con.execute(
                            "SELECT path FROM secki WHERE bayrak != ''")}
                    except Exception:
                        elenen = set()
                    try:
                        veto = {r[0] for r in con.execute(
                            "SELECT path FROM onay WHERE durum='red'")}
                    except Exception:
                        veto = set()
                    con.close()
                    tampon = _io.StringIO()
                    w = _csv.writer(tampon, delimiter=";", lineterminator="\n")
                    w.writerow(["klasor", "dosya", "kisiler", "durum", "tam_yol"])
                    for p in yollar:
                        kisi = ", ".join(sorted(
                            isimler.get(c) or ("kisi_%04d" % c) for c in kk.get(p, [])))
                        durum = "vetolu" if p in veto else ("elenmis" if p in elenen else "")
                        w.writerow([os.path.dirname(p), os.path.basename(p), kisi, durum, p])
                    icerik = tampon.getvalue()
                else:
                    icerik = "\n".join(yollar)

                try:
                    # CSV Excel'de dogru acilsin diye BOM ile
                    kodlama = "utf-8-sig" if bicim.startswith("csv") else "utf-8"
                    hedef.write_text(icerik, encoding=kodlama)
                except OSError as e:
                    return self._json({"hata": "Yazilamadi: %s" % e}, 400)
                return self._json({"ok": True, "yol": str(hedef),
                                   "mesaj": "%d kare yazildi: %s" % (len(yollar), hedef.name)})
            if islem == "teslim":
                hedef = veri.get("hedef") or str(BASE / "teslim-arama")
                liste = BASE / ".arama-listesi.txt"
                liste.write_text("\n".join(yollar), encoding="utf-8")
                return self._json({"ok": is_calistir("Teslim paketi", [
                    "teslim", "--db", cfg["db"], "--names", str(BASE / "isimler.csv"),
                    "--dst", hedef, "--dosya-listesi", str(liste),
                    "--boyut", str(veri.get("boyut", 2048)), "--evet"])})
            if islem == "klasorle":
                if not cfg.get("hedef_klasor"):
                    return self._json({"hata": "Once cikti klasorunu secin"}, 400)
                liste = BASE / ".arama-listesi.txt"
                liste.write_text("\n".join(yollar), encoding="utf-8")
                return self._json({"ok": is_calistir("Klasorler olusturuluyor", [
                    "export", "--db", cfg["db"], "--dst", cfg["hedef_klasor"],
                    "--names", str(BASE / "isimler.csv"), "--mode", cfg["mod"],
                    "--duzen", cfg["duzen"], "--derinlik", cfg["derinlik"],
                    "--dosya-listesi", str(liste), "--evet"])})
            return self._json({"hata": "bilinmeyen islem"}, 400)

        if u.path == "/api/rapor-kaydet":
            import csv as _csv
            import io as _io
            tur = (veri.get("tur") or "").lower()
            bicim = (veri.get("bicim") or "csv").lower()
            klasor = (veri.get("klasor") or "").strip() or str(BASE)
            if not os.path.isdir(klasor):
                return self._json({"hata": "Klasor bulunamadi: %s" % klasor}, 400)
            d = rapor_verisi()
            if not d:
                return self._json({"hata": "Once tarama ve gruplama yapin"}, 400)

            basliklar, satirlar, varsayilan = [], [], tur
            if tur == "bolum":
                basliklar = ["bolum", "kare", "kisi", "yuz_bulunamayan", "en_cok_gorunen"]
                satirlar = [[b["bolum"], b["kare"], b["kisi"], b["yuzsuz"],
                             ", ".join("%s (%d)" % (e["ad"], e["adet"]) for e in b["enler"])]
                            for b in d.get("bolumler", [])]
                varsayilan = "bolum-ozeti"
            elif tur == "supheli":
                basliklar = ["kisi", "dosya", "benzerlik", "klasor"]
                satirlar = [[x["kisi"], x["ad"], x["benzerlik"], x["klasor"]]
                            for x in d.get("supheli", [])]
                varsayilan = "supheli-kareler"
            elif tur == "capraz":
                c = d.get("capraz", {})
                basliklar = ["kisi"] + list(c.get("bolumler", [])) + ["toplam"]
                satirlar = [[r["ad"]] + list(r["hucreler"]) + [r["toplam"]]
                            for r in c.get("satirlar", [])]
                varsayilan = "kisi-bolum-tablosu"
            elif tur == "ikili":
                basliklar = ["kisi", "kisi", "birlikte_kare"]
                satirlar = [[i["a"], i["b"], i["adet"]] for i in d.get("ikili", [])]
                varsayilan = "birlikte-gorunenler"
            elif tur == "kapsama":
                basliklar = ["kisi", "toplam_kare", "kullanilabilir", "yeterli_mi",
                             "bulanik", "kucuk_yuz", "goz_kapali"]
                satirlar = [[x["ad"], x["kare"], x["kullanilabilir"],
                             "AZ" if x["yetersiz"] else "yeterli",
                             x["bulanik"], x["kucuk"], x["goz"]]
                            for x in d.get("kapsama", [])]
                varsayilan = "kapsama-raporu"
            elif tur == "sahne":
                basliklar = ["sahne", "baslangic", "bitis", "dakika", "kare",
                             "kisi", "kimler", "klasor"]
                satirlar = [[x["no"], x["bas"], x["son"], x["dakika"], x["kare"],
                             x.get("kisi", 0), x.get("kisiler", ""), x.get("klasor", "")]
                            for x in d.get("sahneler", [])]
                varsayilan = "sahne-listesi"
            elif tur == "topluluk":
                basliklar = ["dosya", "kisi_sayisi", "kimler", "klasor"]
                satirlar = [[x["ad"], x["kisi_sayisi"], x["kisiler"], x["klasor"]]
                            for x in d.get("topluluk", [])]
                varsayilan = "topluluk-kareleri"
            elif tur == "dikey":
                basliklar = ["kisi", "yatay", "dikey", "durum"]
                satirlar = [[x["ad"], x["yatay"], x["dikey"],
                             "DIKEY YOK" if x["yok"] else "var"]
                            for x in d.get("dikey", [])]
                varsayilan = "dikey-kapsama"
            elif tur == "karne":
                k = d.get("karne", {})
                basliklar = ["olcum", "deger"]
                satirlar = [
                    ["taranan kare", k.get("kare", 0)],
                    ["yuz bulunan kare", k.get("kare", 0) - k.get("yuzsuz", 0)],
                    ["yuz bulunamayan kare", k.get("yuzsuz", 0)],
                    ["yuz bulunamayan oran %", k.get("yuzsuz_oran", 0)],
                    ["bulunan yuz", k.get("yuz", 0)],
                    ["gruplanamayan yuz", k.get("gruplanmayan", 0)],
                    ["supheli yuz", k.get("supheli", 0)],
                    ["ayirt edilen kisi", k.get("kisi", 0)],
                ] + [["zayif klasor: " + z["bolum"],
                      "%d karenin %d'sinde yuz yok (%%%s)" % (z["kare"], z["yuzsuz"], z["oran"])]
                     for z in k.get("zayif", [])]
                varsayilan = "tarama-karnesi"
            else:
                return self._json({"hata": "bilinmeyen rapor turu"}, 400)

            if not satirlar:
                return self._json({"hata": "Bu raporda gosterilecek satir yok"}, 400)

            uzanti = ".csv" if bicim.startswith("csv") else ".txt"
            ad = (veri.get("ad") or "").strip() or (
                varsayilan + "-" + time.strftime("%Y%m%d-%H%M"))
            for kotu in '<>:"/\\|?*':
                ad = ad.replace(kotu, "_")
            if not ad.lower().endswith(uzanti):
                ad += uzanti
            hedef = Path(klasor) / ad

            if bicim.startswith("csv"):
                tampon = _io.StringIO()
                w = _csv.writer(tampon, delimiter=";", lineterminator="\n")
                w.writerow(basliklar)
                for r in satirlar:
                    w.writerow(r)
                icerik = tampon.getvalue()
            else:
                genis = [max(len(str(basliklar[i])),
                             max((len(str(r[i])) for r in satirlar), default=0))
                         for i in range(len(basliklar))]
                cizgi = "  ".join("-" * g for g in genis)
                satir_yaz = lambda r: "  ".join(  # noqa: E731
                    str(r[i]).ljust(genis[i]) for i in range(len(basliklar)))
                icerik = "\n".join([satir_yaz(basliklar), cizgi]
                                    + [satir_yaz(r) for r in satirlar]) + "\n"

            try:
                hedef.write_text(icerik,
                                 encoding="utf-8-sig" if bicim.startswith("csv") else "utf-8")
            except OSError as e:
                return self._json({"hata": "Yazilamadi: %s" % e}, 400)
            return self._json({"ok": True, "yol": str(hedef),
                               "mesaj": "%d satir yazildi: %s" % (len(satirlar), hedef.name)})

        if u.path == "/api/kutuphane-islem":
            try:
                import kutuphane
            except Exception as e:
                return self._json({"hata": str(e)}, 500)
            kut = BASE / "kisi_kutuphanesi.db"
            c = kutuphane.ac(kut)
            islem = veri.get("islem")
            try:
                if islem == "adlandir":
                    ok, mesaj = kutuphane.yeniden_adlandir(
                        c, veri.get("eski", ""), veri.get("yeni", ""))
                elif islem == "birlestir":
                    ok, mesaj = kutuphane.kisi_birlestir(
                        c, veri.get("hedef", ""), veri.get("kaynaklar") or [])
                elif islem == "sil":
                    ok = kutuphane.sil(c, veri.get("isim", ""))
                    mesaj = ("Silindi: %s" % veri.get("isim")) if ok else "Kisi bulunamadi"
                elif islem == "yedekle":
                    hedef = BASE / ("kutuphane-yedek-%s.json" % time.strftime("%Y%m%d"))
                    n = kutuphane.disa_aktar(c, hedef)
                    ok, mesaj = True, "%d kisi yedeklendi: %s" % (n, hedef.name)
                elif islem == "geri-yukle":
                    p = (veri.get("yol") or "").strip().strip('"')
                    if not p or not os.path.isfile(p):
                        ok, mesaj = False, "Yedek dosyasi bulunamadi"
                    else:
                        e_, g_ = kutuphane.ice_aktar(c, p)
                        ok, mesaj = True, "%d yeni, %d guncellenen kisi" % (e_, g_)
                else:
                    ok, mesaj = False, "Bilinmeyen islem"
            except Exception as e:
                ok, mesaj = False, str(e)
            finally:
                c.close()
            return self._json({"ok": ok, "mesaj": mesaj}, 200 if ok else 400)

        if u.path == "/api/duzelt":
            islem = veri.get("islem")
            db = cfg["db"]
            isimler = str(BASE / "isimler.csv")
            if islem == "geri-al":
                ok, mesaj = geri_al_uygula(veri.get("parti"))
                return self._json({"ok": ok, "mesaj": mesaj} if ok else {"hata": mesaj},
                                  200 if ok else 400)
            if islem == "yedekle":
                yolu = veritabani_yedegi("elle")
                return self._json({"ok": bool(yolu), "yol": yolu or "",
                                   "mesaj": ("Yedek alindi: %s" % os.path.basename(yolu))
                                   if yolu else "Yedek alinamadi"})
            if islem == "birlestir":
                kumeler = [str(k) for k in (veri.get("kume") or [])]
                if len(kumeler) < 2:
                    return self._json({"hata": "En az iki kisi secin"}, 400)
                geri_al_kaydet("%d kisi birlestirildi" % len(kumeler),
                               kumeler=[int(k) for k in kumeler])
                return self._json({"ok": is_calistir("Kisiler birlestiriliyor", [
                    "birlestir", "--db", db, "--names", isimler, "--kume"] + kumeler)})
            if islem == "bol":
                geri_al_kaydet("kisi_%04d bolundu" % int(veri.get("kume") or 0),
                               kumeler=[int(veri.get("kume") or 0)])
                return self._json({"ok": is_calistir("Kisi bolunuyor", [
                    "bol", "--db", db, "--names", isimler,
                    "--kume", str(veri.get("kume")),
                    "--esik", str(veri.get("esik", 0.60))])})
            if islem == "cikar":
                yuzler = [str(y) for y in (veri.get("yuz") or [])]
                if not yuzler:
                    return self._json({"hata": "Yuz secilmedi"}, 400)
                geri_al_kaydet("%d yuz gruptan cikarildi" % len(yuzler),
                               yuz_idler=[int(y) for y in yuzler])
                return self._json({"ok": is_calistir("Yuz cikariliyor", [
                    "cikar", "--db", db, "--names", isimler, "--yuz"] + yuzler)})
            return self._json({"hata": "bilinmeyen islem"}, 400)

        if u.path == "/api/guncelle":
            if veri.get("islem") == "uygula":
                ok, mesaj = guncellemeyi_uygula()
                return self._json({"ok": ok, "mesaj": mesaj})
            yeni = guncelleme_ara(zorla=True)
            return self._json({"yeni": yeni,
                               "mesaj": ("Yeni surum: %s" % yeni) if yeni
                                        else "Program guncel."})

        if u.path == "/api/durdur":
            return self._json({"ok": durdur()})

        if u.path == "/api/baslat":
            adim = veri.get("adim")
            db = cfg["db"]
            isimler = str(BASE / "isimler.csv")
            if adim == "tara":
                kaynaklar = cfg.get("kaynak_klasorler") or []
                if not kaynaklar:
                    return self._json({"hata": "Once en az bir fotograf klasoru ekleyin"}, 400)
                a = ["scan", "--src"] + kaynaklar + ["--db", db]
                if cfg.get("kaliteli_tarama"):
                    a += ["--kalite"]
                elif cfg.get("iki_asama"):
                    a += ["--iki-asama"]
                elif cfg.get("hizli_tarama"):
                    a += ["--hizli"]
                if veri.get("deneme"):
                    a += ["--limit", "300"]
                return self._json({"ok": is_calistir("Fotograflar taraniyor", a)})
            if adim == "grupla":
                # Yeniden gruplama tum kume numaralarini degistirir; once yedek
                # al ki yanlis esikle calistirildiginda geri donulebilsin.
                veritabani_yedegi("gruplama-oncesi")
                return self._json({"ok": is_calistir("Kisiler gruplaniyor", [
                    "cluster", "--db", db, "--eps", cfg["eps"],
                    "--min-samples", cfg["min_samples"]])})
            if adim == "tani":
                return self._json({"ok": is_calistir("Kutuphaneden taniniyor", [
                    "tani", "--db", db, "--names", isimler])})
            if adim == "ogren":
                return self._json({"ok": is_calistir("Kutuphaneye ogretiliyor", [
                    "ogren", "--db", db, "--names", isimler])})
            if adim == "klasorle":
                if not cfg.get("hedef_klasor"):
                    return self._json({"hata": "Once cikti klasorunu secin"}, 400)
                a = ["export", "--db", db, "--dst", cfg["hedef_klasor"],
                     "--names", isimler, "--mode", cfg["mod"],
                     "--duzen", cfg["duzen"], "--derinlik", cfg["derinlik"], "--evet"]
                if veri.get("kisi"):
                    a += ["--kisi"] + [str(k) for k in veri["kisi"]]
                if veri.get("secki_atla") or cfg.get("secki_atla"):
                    a += ["--secki-atla"]
                return self._json({"ok": is_calistir("Klasorler olusturuluyor", a)})
            if adim == "etiketle":
                a = ["etiketle", "--db", db, "--names", isimler,
                     "--mod", cfg.get("etiket_mod", "gomulu"), "--evet"]
                if veri.get("kisi"):
                    a += ["--kisi"] + [str(k) for k in veri["kisi"]]
                if veri.get("deneme"):
                    a += ["--limit", "20"]
                return self._json({"ok": is_calistir("Metadata yaziliyor", a)})
            if adim == "secki":
                return self._json({"ok": is_calistir("Kareler degerlendiriliyor", [
                    "secki", "--db", db])})
            if adim == "onizleme":
                if not cfg.get("hedef_klasor"):
                    return self._json({"hata": "Once cikti klasorunu secin"}, 400)
                return self._json({"ok": is_calistir("Onizleme", [
                    "export", "--db", db, "--dst", cfg["hedef_klasor"],
                    "--names", isimler, "--mode", cfg["mod"],
                    "--duzen", cfg["duzen"], "--derinlik", cfg["derinlik"], "--dry-run"])})
            return self._json({"hata": "bilinmeyen adim"}, 400)

        if u.path == "/api/klasor-ac":
            hedef = (veri.get("yol") or "").strip() or cfg.get("hedef_klasor")
            if hedef and os.path.isfile(hedef):
                hedef = os.path.dirname(hedef)
            if hedef and Path(hedef).exists():
                try:
                    if os.name == "nt":
                        os.startfile(hedef)
                    elif sys.platform == "darwin":
                        subprocess.call(["open", hedef])
                    else:
                        subprocess.call(["xdg-open", hedef])
                except Exception:
                    pass
            return self._json({"ok": True})

        self.send_response(404)
        self.end_headers()


def bos_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def sunucu_baslat():
    """Yerel sunucuyu arka planda baslatir, (sunucu, adres) dondurur."""
    if not (BASE / "arayuz.html").exists():
        raise RuntimeError("arayuz.html bulunamadi.")
    port = bos_port()
    sunucu = ThreadingHTTPServer(("127.0.0.1", port), Vekil)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    threading.Thread(target=guncelleme_ara, daemon=True).start()
    return sunucu, "http://127.0.0.1:%d/?t=%s" % (port, ANAHTAR)


def klasor_dialogu(baslik, mevcut):
    """
    Klasor secme penceresi (tkinter). Pencere modunda bunun yerine
    isletim sisteminin kendi dialogu kullanilir - pencere.py devralir.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        kok = tk.Tk()
        kok.withdraw()
        kok.attributes("-topmost", True)
        kok.update_idletasks()
        kok.deiconify()
        kok.geometry("1x1+0+0")
        kok.lift()
        try:
            kok.focus_force()
        except Exception:
            pass
        kok.withdraw()
        secim = filedialog.askdirectory(
            title=baslik, initialdir=mevcut or str(Path.home()), parent=kok)
        try:
            kok.destroy()
        except Exception:
            pass
        return str(Path(secim)) if secim else ""
    except Exception as e:
        print("Klasor penceresi acilamadi:", e)
        return None


def dialog_dongusu(isleyici=None):
    """Kuyruga gelen klasor isteklerini karsilar (ANA is parcaciginda calismali)."""
    isleyici = isleyici or klasor_dialogu
    while True:
        try:
            baslik, mevcut, cevap = dialog_kuyrugu.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            cevap.put(isleyici(baslik, mevcut))
        except Exception:
            cevap.put(None)


def main():
    try:
        sunucu, adres = sunucu_baslat()
    except RuntimeError as e:
        print(e)
        return 1
    print("Yuz Ayirici arayuzu calisiyor.")
    print("Tarayicida acilmadiysa su adresi yapistirin:")
    print("   " + adres)
    print()
    print("Bu pencereyi KAPATMAYIN - program burada calisiyor.")
    webbrowser.open(adres)

    # klasor pencereleri ANA is parcaciginda acilmali
    dialog_dongusu()


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        pass
