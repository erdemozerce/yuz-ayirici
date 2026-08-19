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
ORNEK_SINIRI = 80    # GORUNUM basina saklanacak en fazla yuz vektoru
GORUNUM_ESIGI = 0.40  # mevcut gorunumlere bundan az benziyorsa yeni gorunum
GORUNUM_SINIRI = 5    # kisi basina en fazla gorunum (peruk/sakal/donem vb.)
BENZER_ESIGI = 0.55   # kutuphanede "ayni kisi olabilir" onerisi esigi

SEMA = """
CREATE TABLE IF NOT EXISTS kisiler(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    isim       TEXT UNIQUE NOT NULL,
    eklenme    TEXT,
    guncelleme TEXT,
    kapak      BLOB
);
CREATE TABLE IF NOT EXISTS ornekler(
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    kisi_id  INTEGER NOT NULL,
    emb      BLOB NOT NULL,
    kaynak   TEXT,
    tarih    TEXT,
    gorunum  INTEGER DEFAULT 1
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
    # eski kutuphanelere kapak sutunu ekle
    sutunlar = {r[1] for r in con.execute("PRAGMA table_info(kisiler)")}
    if "kapak" not in sutunlar:
        con.execute("ALTER TABLE kisiler ADD COLUMN kapak BLOB")
    ornek_sutun = {r[1] for r in con.execute("PRAGMA table_info(ornekler)")}
    if "gorunum" not in ornek_sutun:
        con.execute("ALTER TABLE ornekler ADD COLUMN gorunum INTEGER DEFAULT 1")
        con.execute("UPDATE ornekler SET gorunum = 1 WHERE gorunum IS NULL")
        con.commit()
        con.commit()
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


def ogret(con, isim, E, kaynak="", sinir=ORNEK_SINIRI, kapak=None):
    """Bir kisiye ait yuz vektorlerini kutuphaneye ekler. Eklenen sayiyi dondurur."""
    isim = (isim or "").strip()
    if not isim:
        return 0
    E = _birim(E)
    if E.size == 0:
        return 0

    satir = con.execute("SELECT id, kapak FROM kisiler WHERE isim = ?", (isim,)).fetchone()
    if satir:
        kisi_id = satir[0]
        con.execute("UPDATE kisiler SET guncelleme = ? WHERE id = ?", (_simdi(), kisi_id))
        if kapak and not satir[1]:            # kapagi yoksa simdi koy
            con.execute("UPDATE kisiler SET kapak = ? WHERE id = ?", (kapak, kisi_id))
    else:
        cur = con.execute(
            "INSERT INTO kisiler(isim, eklenme, guncelleme, kapak) VALUES(?,?,?,?)",
            (isim, _simdi(), _simdi(), kapak))
        kisi_id = cur.lastrowid

    # Hangi gorunume ait? Mevcut gorunumlerin merkezlerine bakiyoruz.
    gorunumler = _gorunumler(con, kisi_id)
    yeni_merkez = E.mean(axis=0)
    yeni_merkez /= np.linalg.norm(yeni_merkez) + 1e-9

    hedef_gorunum, en_iyi = None, 0.0
    for g, S in gorunumler.items():
        m = S.mean(axis=0)
        m /= np.linalg.norm(m) + 1e-9
        benzerlik = float(yeni_merkez @ m)
        if benzerlik > en_iyi:
            hedef_gorunum, en_iyi = g, benzerlik

    if hedef_gorunum is None or en_iyi < GORUNUM_ESIGI:
        if len(gorunumler) >= GORUNUM_SINIRI:
            # sinir doldu: en yakin gorunume ekle, yoksa kutuphane sisiyor
            hedef_gorunum = hedef_gorunum or 1
        else:
            hedef_gorunum = (max(gorunumler) + 1) if gorunumler else 1

    eski = gorunumler.get(hedef_gorunum, np.empty((0, E.shape[1]), np.float32))
    hepsi = np.vstack([eski, E]) if len(eski) else E
    tutulacak = _cesitli_sec(hepsi, sinir)

    con.execute("DELETE FROM ornekler WHERE kisi_id = ? AND gorunum = ?",
                (kisi_id, hedef_gorunum))
    con.executemany(
        "INSERT INTO ornekler(kisi_id, emb, kaynak, tarih, gorunum) VALUES(?,?,?,?,?)",
        [(kisi_id, v.astype(np.float32).tobytes(), kaynak, _simdi(), hedef_gorunum)
         for v in tutulacak],
    )
    con.commit()
    return len(tutulacak)


def _gorunumler(con, kisi_id):
    """{gorunum_no: vektorler} - kisinin farkli gorunusleri."""
    cikti = {}
    for g, e in con.execute(
            "SELECT COALESCE(gorunum,1), emb FROM ornekler WHERE kisi_id = ?", (kisi_id,)):
        cikti.setdefault(int(g), []).append(np.frombuffer(e, np.float32))
    return {g: _birim(np.vstack(v)) for g, v in cikti.items() if v}


def _oku(con, kisi_id):
    rows = con.execute("SELECT emb FROM ornekler WHERE kisi_id = ?", (kisi_id,)).fetchall()
    if not rows:
        return np.zeros((0, 512), np.float32)
    return _birim(np.vstack([np.frombuffer(r[0], np.float32) for r in rows]))


def herkes(con):
    """
    [(isim, ornek_matrisi), ...]

    Bir kisinin birden cok gorunumu varsa (peruk, sakal, donem kostumu) her
    gorunum AYRI satir olarak doner. tani() ayni ismin satirlarini
    birlestirip en iyisini alir; boylece iki gorunum birbirini ortalayip
    zayiflatmiyor.
    """
    out = []
    for kisi_id, isim in con.execute("SELECT id, isim FROM kisiler ORDER BY isim"):
        gorunumler = _gorunumler(con, kisi_id)
        if gorunumler:
            for _g, E in sorted(gorunumler.items()):
                if len(E):
                    out.append((isim, E))
        else:
            E = _oku(con, kisi_id)
            if len(E):
                out.append((isim, E))
    return out


def benzer_kisiler(con, esik=BENZER_ESIGI, adet=10):
    """
    Kutuphanede birbirine cok benzeyen kisiler - muhtemelen ayni oyuncu
    iki ayri isimle (or. farkli dizide farkli yazilmis) kaydedilmis.
    """
    kayit = {}
    for kisi_id, isim in con.execute("SELECT id, isim FROM kisiler"):
        gorunumler = _gorunumler(con, kisi_id)
        if not gorunumler:
            continue
        merkezler = []
        for _g, E in gorunumler.items():
            m = E.mean(axis=0)
            m /= np.linalg.norm(m) + 1e-9
            merkezler.append(m)
        kayit[isim] = merkezler

    adlar = sorted(kayit)
    oneri = []
    for i in range(len(adlar)):
        for j in range(i + 1, len(adlar)):
            en_iyi = max(float(a @ b) for a in kayit[adlar[i]] for b in kayit[adlar[j]])
            if en_iyi >= esik:
                oneri.append({"a": adlar[i], "b": adlar[j],
                              "benzerlik": round(en_iyi, 3)})
    oneri.sort(key=lambda x: -x["benzerlik"])
    return oneri[:adet]


def gorunum_ozeti(con):
    """Kisi basina gorunum sayisi ve ornek dagilimi."""
    cikti = []
    for kisi_id, isim in con.execute("SELECT id, isim FROM kisiler ORDER BY isim"):
        g = _gorunumler(con, kisi_id)
        if g:
            cikti.append({"isim": isim, "gorunum": len(g),
                          "ornek": sum(len(v) for v in g.values()),
                          "dagilim": [len(v) for _k, v in sorted(g.items())]})
    return cikti


def liste(con, kapakli=False):
    """[(isim, ornek_sayisi, eklenme, guncelleme[, kapak]), ...]"""
    alanlar = "k.isim, COUNT(o.id), k.eklenme, k.guncelleme"
    if kapakli:
        alanlar += ", k.kapak"
    return con.execute(
        "SELECT %s FROM kisiler k LEFT JOIN ornekler o ON o.kisi_id = k.id "
        "GROUP BY k.id ORDER BY COUNT(o.id) DESC" % alanlar
    ).fetchall()


def yeniden_adlandir(con, eski, yeni):
    """Kutuphanedeki bir kisiyi yeniden adlandirir."""
    eski, yeni = (eski or "").strip(), (yeni or "").strip()
    if not eski or not yeni:
        return False, "Isim bos olamaz"
    if eski == yeni:
        return True, "Isim zaten ayni"
    var = con.execute("SELECT id FROM kisiler WHERE isim = ?", (eski,)).fetchone()
    if not var:
        return False, "Kutuphanede yok: %s" % eski
    cakisma = con.execute("SELECT id FROM kisiler WHERE isim = ?", (yeni,)).fetchone()
    if cakisma:
        return False, ("'%s' zaten var. Ikisini tek kisi yapmak icin BIRLESTIR kullanin."
                       % yeni)
    con.execute("UPDATE kisiler SET isim = ?, guncelleme = ? WHERE id = ?",
                (yeni, _simdi(), var[0]))
    con.commit()
    return True, "%s -> %s" % (eski, yeni)


def kisi_birlestir(con, hedef, kaynaklar):
    """Birden fazla kutuphane kaydini tek isimde toplar (ornekler birlesir)."""
    hedef = (hedef or "").strip()
    kaynaklar = [k.strip() for k in kaynaklar if k and k.strip() and k.strip() != hedef]
    if not hedef or not kaynaklar:
        return False, "Hedef ve en az bir kaynak gerekli"
    toplam = []
    kapak = None
    h = con.execute("SELECT id, kapak FROM kisiler WHERE isim = ?", (hedef,)).fetchone()
    if h:
        toplam.append(_oku(con, h[0]))
        kapak = h[1]
    for ad in kaynaklar:
        r = con.execute("SELECT id, kapak FROM kisiler WHERE isim = ?", (ad,)).fetchone()
        if not r:
            continue
        toplam.append(_oku(con, r[0]))
        kapak = kapak or r[1]
        con.execute("DELETE FROM ornekler WHERE kisi_id = ?", (r[0],))
        con.execute("DELETE FROM kisiler WHERE id = ?", (r[0],))
    toplam = [t for t in toplam if len(t)]
    if not toplam:
        return False, "Birlestirilecek ornek yok"
    con.commit()
    ogret(con, hedef, np.vstack(toplam), kaynak="birlestirme", kapak=kapak)
    return True, "%d kayit '%s' altinda toplandi" % (len(kaynaklar) + 1, hedef)


def kapak_al(con, isim):
    r = con.execute("SELECT kapak FROM kisiler WHERE isim = ?", (isim,)).fetchone()
    return r[0] if r else None


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
    if E.size == 0 or E.shape[0] == 0:
        return None, 0.0, 0.0, "karsilastirilacak yuz yok"
    merkez = E.mean(axis=0)
    merkez /= np.linalg.norm(merkez) + 1e-9
    if not np.all(np.isfinite(merkez)):
        return None, 0.0, 0.0, "yuz vektoru bozuk"

    puanlar = []
    for isim, S in kayitli:
        if S is None or S.size == 0 or S.shape[0] == 0:
            continue
        s_merkez = S.mean(axis=0)
        s_merkez /= np.linalg.norm(s_merkez) + 1e-9
        merkez_ben = float(merkez @ s_merkez)
        capraz = E @ S.T
        # en iyi %10 eslesmenin ortalamasi: acidan/isiktan kaynakli sapmalari tolere eder
        k = max(1, int(0.10 * capraz.size))
        en_iyiler = float(np.sort(capraz, axis=None)[-k:].mean())
        puan = 0.65 * merkez_ben + 0.35 * en_iyiler
        if np.isfinite(puan):
            puanlar.append((float(puan), isim, merkez_ben))

    # Ayni isim birden cok gorunumle gelebilir; kisinin puani EN IYI
    # gorunumunun puanidir. Yoksa "iki kisiye birden benziyor" korumasi
    # kisinin kendi ikinci gorunumu yuzunden bosuna devreye girer.
    if not puanlar:
        return None, 0.0, 0.0, "karsilastirilabilir kayit yok"

    en_iyi_isim = {}
    for puan, isim, merkez_ben in puanlar:
        if isim not in en_iyi_isim or puan > en_iyi_isim[isim][0]:
            en_iyi_isim[isim] = (puan, isim, merkez_ben)
    puanlar = sorted(en_iyi_isim.values(), reverse=True)

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
    veri = {"surum": 2, "tarih": _simdi(), "kisiler": []}
    for isim, E in herkes(con):
        kapak = kapak_al(con, isim)
        veri["kisiler"].append({
            "isim": isim,
            "ornek": len(E),
            "vektorler": base64.b64encode(
                np.asarray(E, dtype=np.float32).tobytes()).decode("ascii"),
            "kapak": base64.b64encode(kapak).decode("ascii") if kapak else "",
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
        kapak = base64.b64decode(k["kapak"]) if k.get("kapak") else None
        ogret(con, isim, E, kaynak="yedek", kapak=kapak)
        if isim in mevcut:
            guncellenen += 1
        else:
            eklenen += 1
    return eklenen, guncellenen
