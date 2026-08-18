#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
baslat.py — komut satiri bilmeyen kullanici icin menu.
BASLAT.bat bu dosyayi calistirir.
"""

import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
AYARLAR = BASE / "ayarlar.json"
VARSAYILAN = {
    "kaynak_klasor": "",
    "hedef_klasor": "",
    "db": str(BASE / "faces.db"),
    "eps": 0.50,
    "min_samples": 3,
    "mod": "auto",
    "guncelleme_url": "",
    "otomatik_guncelleme": True,
    "son_kontrol": 0,
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def ayar_oku():
    cfg = dict(VARSAYILAN)
    if AYARLAR.exists():
        try:
            cfg.update(json.loads(AYARLAR.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def ayar_yaz(cfg):
    AYARLAR.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def klasor_sec(baslik, mevcut=""):
    try:
        import tkinter as tk
        from tkinter import filedialog

        kok = tk.Tk()
        kok.withdraw()
        kok.attributes("-topmost", True)
        p = filedialog.askdirectory(title=baslik, initialdir=mevcut or str(Path.home()))
        kok.destroy()
        if p:
            return str(Path(p))
    except Exception:
        pass
    return input(baslik + " (yolu yapistir): ").strip().strip('"')


def calistir(*argv):
    """face_sorter.py'yi alt surec olarak calistirir, ciktisini canli gosterir."""
    komut = [sys.executable, str(BASE / "face_sorter.py")] + [str(a) for a in argv]
    print("-" * 62)
    kod = subprocess.call(komut)
    print("-" * 62)
    if kod != 0:
        print("!! Islem hata ile bitti (kod %s)." % kod)
    return kod == 0


def durum(cfg):
    db = Path(cfg["db"])
    if not db.exists():
        return "henuz tarama yapilmadi"
    try:
        import sqlite3

        c = sqlite3.connect(db)
        nf = c.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        ny = c.execute("SELECT COUNT(*) FROM faces").fetchone()[0]
        nk = c.execute("SELECT COUNT(DISTINCT cluster) FROM faces WHERE cluster>0").fetchone()[0]
        c.close()
        return "%s fotograf tarandi, %s yuz, %s kisi" % (nf, ny, nk)
    except Exception:
        return "veritabani okunamadi"


def surum():
    try:
        import guncelle

        return guncelle.yerel_surum()
    except Exception:
        return "?"


def guncelleme_bak(sessiz=True):
    try:
        import guncelle
    except Exception:
        return
    try:
        m = guncelle.gunluk_kontrol() if sessiz else guncelle.kontrol_et()
    except Exception as e:
        if not sessiz:
            print("Guncelleme kontrolu basarisiz:", e)
        return
    if not m:
        if not sessiz:
            print("\nProgram guncel (surum %s)." % surum())
        return
    print("\n*** YENI SURUM VAR: %s (sizdeki: %s) ***" % (m.get("surum"), surum()))
    if m.get("notlar"):
        print("Yenilikler: %s" % m["notlar"])
    if input("Simdi guncellensin mi? (E/h): ").strip().lower() in ("", "e", "evet"):
        try:
            guncelle.uygula(m)
            print("\nGuncelleme tamam. Programi kapatip yeniden acin.")
            input("Devam icin Enter...")
        except Exception as e:
            print("Guncelleme basarisiz:", e)


def klasor_ac(yol):
    """Sonuc klasorunu isletim sistemine gore acar (Windows / macOS / Linux)."""
    try:
        if os.name == "nt":
            os.startfile(yol)
        elif sys.platform == "darwin":
            subprocess.call(["open", str(yol)])
        else:
            subprocess.call(["xdg-open", str(yol)])
    except Exception:
        pass


def hedef_onayla(cfg):
    """Yazma isleminden ONCE hedef klasoru sorar ve onaylatir."""
    while True:
        mevcut = cfg.get("hedef_klasor", "")
        if mevcut:
            print()
            print("  Kisi klasorleri su konuma yazilacak:")
            print("    %s" % mevcut)
            c = input("  [E] bu klasore yaz   [D] baska klasor sec   [I] iptal : ").strip().lower()
            if c in ("", "e", "evet"):
                return mevcut
            if c in ("i", "iptal"):
                print("  Iptal edildi.")
                return ""
        secim = klasor_sec("Kisi klasorleri nereye olusturulsun?", mevcut)
        if not secim:
            print("  Klasor secilmedi, iptal edildi.")
            return ""
        cfg["hedef_klasor"] = secim
        ayar_yaz(cfg)


def tam_akis(cfg):
    if not cfg["kaynak_klasor"]:
        print("Once fotograflarin bulundugu klasoru secin (1 numarali secenek).")
        return
    print("\n[1/5] Fotograflar taraniyor (en uzun adim, saatler surebilir)...")
    if not calistir("scan", "--src", cfg["kaynak_klasor"], "--db", cfg["db"]):
        return
    print("\n[2/5] Kisiler gruplaniyor...")
    if not calistir("cluster", "--db", cfg["db"], "--eps", cfg["eps"],
                    "--min-samples", cfg["min_samples"]):
        return
    print("\n[3/5] Daha once taninan kisiler kutuphaneden isimlendiriliyor...")
    calistir("tani", "--db", cfg["db"], "--names", str(BASE / "isimler.csv"))
    print("\n[4/5] Inceleme sayfasi hazirlaniyor...")
    calistir("review", "--db", cfg["db"], "--out", str(BASE / "inceleme.html"))
    hedef = hedef_onayla(cfg)
    if not hedef:
        return
    print("\n[5/5] Kisi klasorleri olusturuluyor...")
    calistir("export", "--db", cfg["db"], "--dst", hedef,
             "--names", str(BASE / "isimler.csv"), "--mode", cfg["mod"])
    print("\nBITTI! Klasorler: %s" % hedef)
    klasor_ac(hedef)


def menu():
    guncelleme_bak(sessiz=True)
    while True:
        cfg = ayar_oku()
        print("\n" + "=" * 62)
        print("   YUZ AYIRICI  (surum %s)" % surum())
        print("=" * 62)
        print("   Fotograf klasoru : %s" % (cfg["kaynak_klasor"] or "- secilmedi -"))
        print("   Cikti klasoru    : %s" % (cfg["hedef_klasor"] or "- secilmedi -"))
        print("   Durum            : %s" % durum(cfg))
        print("-" * 62)
        print("   1) Fotograf klasorunu sec")
        print("   2) Cikti klasorunu sec")
        print("   3) HEPSINI YAP  (tara -> grupla -> klasorle)")
        print("   4) Sadece tara")
        print("   5) Sadece grupla (ayar deneme)")
        print("   6) Inceleme sayfasini ac")
        print("   7) Klasorlere ayir")
        print("   8) Deneme turu (ilk 300 fotograf)")
        print("   9) Guncellemeleri kontrol et")
        print("  10) Taninan kisileri kutuphaneden isimlendir")
        print("  11) Isimleri onayla / duzelt  (kutuphane ogrenir)")
        print("  12) Kisi kutuphanesi - kimler kayitli")
        print("   0) Cikis")
        s = input("\nSeciminiz: ").strip()

        if s == "1":
            p = klasor_sec("Fotograflarin bulundugu klasoru secin", cfg["kaynak_klasor"])
            if p:
                cfg["kaynak_klasor"] = p
                ayar_yaz(cfg)
        elif s == "2":
            p = klasor_sec("Kisi klasorleri nereye olusturulsun?", cfg["hedef_klasor"])
            if p:
                cfg["hedef_klasor"] = p
                ayar_yaz(cfg)
        elif s == "3":
            tam_akis(cfg)
        elif s == "4":
            if cfg["kaynak_klasor"]:
                calistir("scan", "--src", cfg["kaynak_klasor"], "--db", cfg["db"])
            else:
                print("Once 1 ile klasor secin.")
        elif s == "5":
            print("Ayni kisi birden cok klasore bolunduyse eps'i YUKSELTIN (0.58),")
            print("farkli kisiler karistiysa DUSURUN (0.42). Simdiki deger: %s" % cfg["eps"])
            y = input("Yeni eps (bos birakirsaniz degismez): ").strip().replace(",", ".")
            if y:
                try:
                    cfg["eps"] = float(y)
                    ayar_yaz(cfg)
                except ValueError:
                    print("Gecersiz sayi, eski deger kullaniliyor.")
                    cfg = ayar_oku()
            calistir("cluster", "--db", cfg["db"], "--eps", cfg["eps"],
                     "--min-samples", cfg["min_samples"])
        elif s == "6":
            calistir("review", "--db", cfg["db"], "--out", str(BASE / "inceleme.html"))
            h = BASE / "inceleme.html"
            if h.exists():
                webbrowser.open(h.as_uri())
        elif s == "7":
            hedef = hedef_onayla(cfg)
            if hedef:
                calistir("export", "--db", cfg["db"], "--dst", hedef,
                         "--names", str(BASE / "isimler.csv"), "--mode", cfg["mod"])
        elif s == "8":
            if cfg["kaynak_klasor"]:
                calistir("scan", "--src", cfg["kaynak_klasor"],
                         "--db", str(BASE / "deneme.db"), "--limit", 300)
                calistir("cluster", "--db", str(BASE / "deneme.db"), "--min-samples", 2)
                calistir("review", "--db", str(BASE / "deneme.db"),
                         "--out", str(BASE / "deneme.html"))
                h = BASE / "deneme.html"
                if h.exists():
                    webbrowser.open(h.as_uri())
            else:
                print("Once 1 ile klasor secin.")
        elif s == "9":
            guncelleme_bak(sessiz=False)
        elif s == "10":
            calistir("tani", "--db", cfg["db"], "--names", str(BASE / "isimler.csv"))
        elif s == "11":
            calistir("onayla", "--db", cfg["db"], "--names", str(BASE / "isimler.csv"))
        elif s == "12":
            calistir("kisiler")
        elif s == "0":
            return
        else:
            print("Gecersiz secim.")


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nIptal edildi.")
    except Exception:
        import traceback

        traceback.print_exc()
        input("\nHata olustu. Ekran goruntusu alip abinize gonderin. Enter ile kapanir...")
