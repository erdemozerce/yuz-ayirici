#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kutuphane.py — kalici kisi kutuphanesi.

MANTIK
  Bir bolumun fotograflarini isimlendirdiginizde, o kisilerin yuz vektorleri
  'kisi_kutuphanesi.db' dosyasina kaydedilir. Sonraki bolumde ayni kisiler
  cikinca program onlari kendisi taniyip klasoru dogru isimle acar.

  Internet YOK, bulut YOK. Her sey bu bilgisayarda kalir. Kutuphane dosyasi
  fotograf icermez, sadece yuz vektorleri (geri fotografa cevrilemez sayilar).

NEDEN GUVENILIR
  Gercek veriyle olculdu: ayni kisinin yuzleri arasindaki benzerlik ~0.75,
  farkli kisiler arasindaki benzerlik ~0.08. Aradaki bosluk cok genis,
  bu yuzden 0.45 esigi rahatlikla ayirir.
"""

import sqlite3
import time
from pathlib import Path

import numpy as np

DOSYA_ADI = "kisi_kutuphanesi.db"
ESIK = 0.45          # bu benzerligin altinda "taninmadi" denir
FARK = 0.06          # birinci ile ikinci aday bu kadar ayrismali
ORNEK_SINIRI = 80    # kisi basina saklanacak en fazla yuz vektoru

SEMA = """
CREATE TABLE IF NOT EXISTS kisiler(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    isim       TEXT UNIQUE NOT NULL,
    eklenme    TEXT,
    guncelleme TEXT
);
CREATE TABLE IF NOT EXISTS ornekler(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kisi_id INTEGER NOT NULL,
    emb     BLOB NOT NULL,
    kaynak  TEXT,
    tarih   TEXT
);
CREATE INDEX IF NOT EXISTS idx_ornek_kisi ON ornekler(kisi_id);
"""


def _simdi():
    return time.strftime("%Y-%m-%d %H:%M")


def _birim(X):
    X = np.atleast_2d(np.asarray(X, dtype=np.float32))
    return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)


def ac(yol=None):
    yol = Path(yol) if yol else Path(__file__).resolve().parent / DOSYA_ADI
    con = sqlite3.connect(str(yol))
    con.executescript(SEMA)
    return con


def _cesitli_sec(X, adet):
    """En farkli 'adet' vektoru secer (acgozlu en-uzak-nokta). Cesitlilik = daha iyi tanima."""
    if len(X) <= adet:
        return X
    secili = [int(np.argmax(X @ X.mean(axis=0)))]     # once en temsili olan
    uzaklik = 1.0 - X @ X[secili[0]]
    while len(secili) < adet:
        y = int(np.argmax(uzaklik))
        secili.append(y)
        uzaklik = np.minimum(uzaklik, 1.0 - X @ X[y])
    return X[secili]


def ogret(con, isim, E, kaynak="", sinir=ORNEK_SINIRI):
    """Bir kisiye ait yuz vektorlerini kutuphaneye ekler. Eklenen sayiyi dondurur."""
    isim = (isim or "").strip()
    if not isim:
        return 0
    E = _birim(E)
    if E.size == 0:
        return 0

    satir = con.execute("SELECT id FROM kisiler WHERE isim = ?", (isim,)).fetchone()
    if satir:
        kisi_id = satir[0]
        con.execute("UPDATE kisiler SET guncelleme = ? WHERE id = ?", (_simdi(), kisi_id))
    else:
        cur = con.execute("INSERT INTO kisiler(isim, eklenme, guncelleme) VALUES(?,?,?)",
                          (isim, _simdi(), _simdi()))
        kisi_id = cur.lastrowid

    eski = _oku(con, kisi_id)
    hepsi = np.vstack([eski, E]) if len(eski) else E
    tutulacak = _cesitli_sec(hepsi, sinir)

    con.execute("DELETE FROM ornekler WHERE kisi_id = ?", (kisi_id,))
    con.executemany(
        "INSERT INTO ornekler(kisi_id, emb, kaynak, tarih) VALUES(?,?,?,?)",
        [(kisi_id, v.astype(np.float32).tobytes(), kaynak, _simdi()) for v in tutulacak],
    )
    con.commit()
    return len(tutulacak)


def _oku(con, kisi_id):
    rows = con.execute("SELECT emb FROM ornekler WHERE kisi_id = ?", (kisi_id,)).fetchall()
    if not rows:
        return np.zeros((0, 512), np.float32)
    return _birim(np.vstack([np.frombuffer(r[0], np.float32) for r in rows]))


def herkes(con):
    """[(isim, ornek_matrisi), ...]"""
    out = []
    for kisi_id, isim in con.execute("SELECT id, isim FROM kisiler ORDER BY isim"):
        E = _oku(con, kisi_id)
        if len(E):
            out.append((isim, E))
    return out


def liste(con):
    """[(isim, ornek_sayisi, eklenme, guncelleme), ...]"""
    return con.execute(
        "SELECT k.isim, COUNT(o.id), k.eklenme, k.guncelleme "
        "FROM kisiler k LEFT JOIN ornekler o ON o.kisi_id = k.id "
        "GROUP BY k.id ORDER BY COUNT(o.id) DESC"
    ).fetchall()


def sil(con, isim):
    satir = con.execute("SELECT id FROM kisiler WHERE isim = ?", (isim,)).fetchone()
    if not satir:
        return False
    con.execute("DELETE FROM ornekler WHERE kisi_id = ?", (satir[0],))
    con.execute("DELETE FROM kisiler WHERE id = ?", (satir[0],))
    con.commit()
    return True


def tani(kayitli, E, esik=ESIK, fark=FARK):
    """
    Yeni bir kumeyi kutuphaneyle karsilastirir.
    kayitli: herkes(con) ciktisi
    Dondurur: (isim veya None, benzerlik, ikinci_aday_benzerligi, gerekce)
    """
    if not kayitli:
        return None, 0.0, 0.0, "kutuphane bos"
    E = _birim(E)
    merkez = E.mean(axis=0)
    merkez /= np.linalg.norm(merkez) + 1e-9

    puanlar = []
    for isim, S in kayitli:
        s_merkez = S.mean(axis=0)
        s_merkez /= np.linalg.norm(s_merkez) + 1e-9
        merkez_ben = float(merkez @ s_merkez)
        capraz = E @ S.T
        # en iyi %10 eslesmenin ortalamasi: acidan/isiktan kaynakli sapmalari tolere eder
        k = max(1, int(0.10 * capraz.size))
        en_iyiler = float(np.sort(capraz, axis=None)[-k:].mean())
        puanlar.append((0.65 * merkez_ben + 0.35 * en_iyiler, isim, merkez_ben))

    puanlar.sort(reverse=True)
    en_iyi = puanlar[0]
    ikinci = puanlar[1][0] if len(puanlar) > 1 else 0.0

    if en_iyi[0] < esik:
        return None, en_iyi[0], ikinci, "benzerlik esigin altinda"
    if en_iyi[0] - ikinci < fark and len(puanlar) > 1:
        return None, en_iyi[0], ikinci, "iki kisiye birden benziyor, emin degil"
    return en_iyi[1], en_iyi[0], ikinci, "eslesti"


def disa_aktar(con, yol):
    """
    Kutuphaneyi tasinabilir tek dosyaya yazar (yuz vektorleri base64).
    Fotograf icermez; sadece sayilar - geri fotografa cevrilemez.
    """
    import base64
    import json
    veri = {"surum": 1, "tarih": _simdi(), "kisiler": []}
    for isim, E in herkes(con):
        veri["kisiler"].append({
            "isim": isim,
            "ornek": len(E),
            "vektorler": base64.b64encode(
                np.asarray(E, dtype=np.float32).tobytes()).decode("ascii"),
        })
    Path(yol).write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return len(veri["kisiler"])


def ice_aktar(con, yol):
    """Yedegi yukler. Ayni isim varsa ornekleri BIRLESTIRIR, ustune yazmaz."""
    import base64
    import json
    veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    mevcut = {i for i, _, _, _ in liste(con)}
    eklenen = guncellenen = 0
    for k in veri.get("kisiler", []):
        isim = (k.get("isim") or "").strip()
        if not isim:
            continue
        ham = base64.b64decode(k["vektorler"])
        E = np.frombuffer(ham, dtype=np.float32).reshape(-1, 512)
        ogret(con, isim, E, kaynak="yedek")
        if isim in mevcut:
            guncellenen += 1
        else:
            eklenen += 1
    return eklenen, guncellenen
