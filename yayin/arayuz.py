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
        "secki_atla": False, "hizli_tarama": False,
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
                     kalan="", satirlar=[], bitti="", hata="")

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


def kucuk_resim(kayit, boy=132):
    """Bir yuzu kirpip base64 JPEG dondurur. kayit = (yuz_id, yol, x1,y1,x2,y2)"""
    _, p, x1, y1, x2, y2 = kayit
    img = motor.imread_unicode(p)
    if img is None:
        return None
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
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")


def kisiler_listesi(adet=5):
    yol = Path(db_yolu())
    if not yol.exists():
        return []
    con = sqlite3.connect(str(yol))
    con.executescript(motor.DB_SCHEMA)
    isimler = motor.isim_csv_oku(BASE / "isimler.csv")
    oner = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "SELECT cluster, onerilen, puan, sayfalar FROM oneriler")}
    out = []
    for cid, nfoto, nyuz in con.execute(
        "SELECT cluster, COUNT(DISTINCT path), COUNT(*) FROM faces WHERE cluster>0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC"
    ):
        ornekler = motor.kume_ornekleri(con, cid, adet)
        resimler = []
        for k in ornekler:
            r = kucuk_resim(k)
            if r:
                resimler.append({"id": k[0], "resim": r})
        o = oner.get(cid) or (None, 0.0, "")
        out.append({
            "kume": cid, "fotograf": nfoto, "yuz": nyuz,
            "isim": isimler.get(cid, ""),
            "onerilen": o[0] or "",
            "benzerlik": round(float(o[1] or 0), 2),
            "resimler": resimler,
        })
    con.close()
    return out


def isim_kaydet(kume, isim):
    yol = BASE / "isimler.csv"
    con = sqlite3.connect(db_yolu())
    con.executescript(motor.DB_SCHEMA)
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
                      "secki_atla", "hizli_tarama"):
                if k in veri:
                    cfg[k] = veri[k]
            ayar_yaz(cfg)
            return self._json({"ok": True})

        if u.path == "/api/isim":
            isim_kaydet(veri.get("kume"), veri.get("isim", ""))
            return self._json({"ok": True})

        if u.path == "/api/duzelt":
            islem = veri.get("islem")
            db = cfg["db"]
            isimler = str(BASE / "isimler.csv")
            if islem == "birlestir":
                kumeler = [str(k) for k in (veri.get("kume") or [])]
                if len(kumeler) < 2:
                    return self._json({"hata": "En az iki kisi secin"}, 400)
                return self._json({"ok": is_calistir("Kisiler birlestiriliyor", [
                    "birlestir", "--db", db, "--names", isimler, "--kume"] + kumeler)})
            if islem == "bol":
                return self._json({"ok": is_calistir("Kisi bolunuyor", [
                    "bol", "--db", db, "--names", isimler,
                    "--kume", str(veri.get("kume")),
                    "--esik", str(veri.get("esik", 0.60))])})
            if islem == "cikar":
                yuzler = [str(y) for y in (veri.get("yuz") or [])]
                if not yuzler:
                    return self._json({"hata": "Yuz secilmedi"}, 400)
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
                if cfg.get("hizli_tarama"):
                    a += ["--hizli"]
                if veri.get("deneme"):
                    a += ["--limit", "300"]
                return self._json({"ok": is_calistir("Fotograflar taraniyor", a)})
            if adim == "grupla":
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
            hedef = cfg.get("hedef_klasor")
            if hedef and Path(hedef).exists():
                try:
                    os.startfile(hedef)
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


def main():
    if not (BASE / "arayuz.html").exists():
        print("arayuz.html bulunamadi.")
        return 1
    port = bos_port()
    sunucu = ThreadingHTTPServer(("127.0.0.1", port), Vekil)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    adres = "http://127.0.0.1:%d/?t=%s" % (port, ANAHTAR)
    print("Yuz Ayirici arayuzu calisiyor.")
    print("Tarayicida acilmadiysa su adresi yapistirin:")
    print("   " + adres)
    print()
    print("Bu pencereyi KAPATMAYIN - program burada calisiyor.")
    threading.Thread(target=guncelleme_ara, daemon=True).start()
    webbrowser.open(adres)

    # tkinter pencereleri ANA is parcaciginda acilmali
    while True:
        try:
            baslik, mevcut, cevap = dialog_kuyrugu.get(timeout=0.5)
        except queue.Empty:
            continue
        yol = ""
        try:
            import tkinter as tk
            from tkinter import filedialog
            kok = tk.Tk()
            kok.withdraw()
            # Pencere tarayicinin ARKASINDA kalmasin: gorunur yap, one al, odagi zorla
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
            if secim:
                yol = str(Path(secim))
        except Exception as _e:
            print("Klasor penceresi acilamadi:", _e)
            yol = None            # arayuz elle giris istesin
        cevap.put(yol)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        pass
