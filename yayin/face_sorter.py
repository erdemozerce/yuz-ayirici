#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
face_sorter.py
==============
Bir klasordeki (veya harddiskteki) tum fotograflari tarar, yuzleri tanir,
ayni kisiye ait yuzleri gruplar ve her kisi icin ayri bir klasor acip
o kisinin gectigi tum fotograflari icine kopyalar/baglar.

Kullanim (sirasiyla):
  python face_sorter.py scan    --src "D:\\Fotograflar" --db faces.db
  python face_sorter.py cluster --db faces.db
  python face_sorter.py review  --db faces.db --out inceleme.html
  python face_sorter.py export  --db faces.db --dst "D:\\Kisiler" --mode hardlink

Notlar:
  - scan komutu kaldigi yerden devam eder (kesilirse tekrar calistir).
  - cluster/review/export adimlari saniyeler surer, parametre deneyerek
    tekrar tekrar calistirabilirsin. Yeniden tarama gerekmez.
"""

__version__ = "1.20.0"

import argparse
import base64
import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# Windows konsolu varsayilan olarak Turkce/Kiril karakterleri basamaz ve
# program cokerdi (UnicodeEncodeError). Ciktiyi UTF-8'e sabitliyoruz.
for _akis in (sys.stdout, sys.stderr):
    try:
        _akis.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

JPEG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif"}
# LibRaw ile okunan ham dosyalar - gomulu onizlemeleri kullanilir (cok hizli)
RAW_EXT = {".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".raf", ".rw2",
           ".orf", ".pef", ".dng", ".raw", ".3fr", ".iiq", ".x3f", ".mrw", ".srw"}
IMAGE_EXT = JPEG_EXT | RAW_EXT

# Ayni karenin hem RAW hem JPEG kopyasi varsa hangisi taranir (once gelen kazanir)
TARAMA_ONCELIGI = [".jpg", ".jpeg", ".tif", ".tiff", ".png"]

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
    path    TEXT PRIMARY KEY,
    mtime   REAL,
    size    INTEGER,
    n_faces INTEGER,
    status  TEXT,
    kok     TEXT,
    esler   TEXT,
    imza    TEXT,
    zaman   TEXT
);
CREATE TABLE IF NOT EXISTS faces(
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    det_score REAL,
    det_w     REAL,
    emb       BLOB,
    cluster   INTEGER DEFAULT -1,
    netlik    REAL,
    goz       REAL,
    yaw       REAL,
    pitch     REAL,
    supheli   REAL
);
CREATE INDEX IF NOT EXISTS idx_faces_path    ON faces(path);
CREATE INDEX IF NOT EXISTS idx_faces_cluster ON faces(cluster);
CREATE TABLE IF NOT EXISTS duzeltmeler(
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    islem  TEXT,
    detay  TEXT,
    tarih  TEXT
);
CREATE TABLE IF NOT EXISTS oneriler(
    cluster   INTEGER PRIMARY KEY,
    onerilen  TEXT,
    puan      REAL,
    ornek     INTEGER,
    toplam    INTEGER,
    sayfalar  TEXT
);
"""


# --------------------------------------------------------------------------
# yardimcilar
# --------------------------------------------------------------------------
def db_connect(path):
    con = sqlite3.connect(path)
    con.executescript(DB_SCHEMA)
    # eski veritabanlarina 'kok' sutununu ekle (hangi kaynak klasorden geldigi)
    sutunlar = {r[1] for r in con.execute("PRAGMA table_info(files)")}
    if "kok" not in sutunlar:
        con.execute("ALTER TABLE files ADD COLUMN kok TEXT")
        con.commit()
    if "esler" not in sutunlar:
        con.execute("ALTER TABLE files ADD COLUMN esler TEXT")
        con.commit()
    for ad, tur in (("imza", "TEXT"), ("zaman", "TEXT")):
        if ad not in sutunlar:
            con.execute("ALTER TABLE files ADD COLUMN %s %s" % (ad, tur))
    yuz_sutun = {r[1] for r in con.execute("PRAGMA table_info(faces)")}
    for ad in ("netlik", "goz", "yaw", "pitch", "supheli"):
        if ad not in yuz_sutun:
            con.execute("ALTER TABLE faces ADD COLUMN %s REAL" % ad)
    con.execute("""CREATE TABLE IF NOT EXISTS onay(
        path   TEXT NOT NULL,
        kisi   INTEGER,
        durum  TEXT NOT NULL,
        kaynak TEXT,
        tarih  TEXT,
        PRIMARY KEY (path, kisi)
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS secki(
        path   TEXT PRIMARY KEY,
        bayrak TEXT,
        puan   REAL,
        grup   INTEGER,
        en_iyi INTEGER DEFAULT 0
    )""")
    con.commit()
    return con


def _jpeg_uzun_kenar(data):
    """Dosyayi cozmeden uzun kenari okur (JPEG/PNG basligi)."""
    try:
        import io as _io
        from PIL import Image
        with Image.open(_io.BytesIO(data.tobytes() if hasattr(data, "tobytes") else data)) as im:
            return max(im.size)
    except Exception:
        return 0


def raw_oku(path, en_az=800):
    """
    RAW dosyayi LibRaw ile okur. ONCE gomulu onizlemeyi dener - olculdu:
    tam cozumlemeden 18-74 kat hizli ve tam cozunurlukte geliyor.
    Onizleme yoksa ya da cok kucukse yarim boy cozumlemeye duser.
    """
    try:
        import rawpy
    except ImportError:
        return None
    try:
        with rawpy.imread(str(path)) as raw:
            try:
                th = raw.extract_thumb()
                if th.format == rawpy.ThumbFormat.JPEG:
                    img = cv2.imdecode(np.frombuffer(th.data, np.uint8), cv2.IMREAD_COLOR)
                else:
                    img = cv2.cvtColor(th.data, cv2.COLOR_RGB2BGR)
                if img is not None and min(img.shape[:2]) >= en_az:
                    return img
            except Exception:
                pass
            rgb = raw.postprocess(half_size=True, use_camera_wb=True, output_bps=8)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def imread_unicode(path, kucult=0):
    """
    Turkce/Rusca karakterli dosya yollarini da okuyabilen imread.

    kucult: 0 = tam cozunurluk. >0 verilirse ve dosya cok buyukse JPEG
    codec'ine YARIM/CEYREK cozunurlukte cozdurulur - tam cozup sonra
    kucultmekten belirgin sekilde hizlidir (olculdu).
    Dondurur: (goruntu, olcek)  olcek = goruntu / orijinal
    """
    if Path(path).suffix.lower() in RAW_EXT:
        img = raw_oku(path)
        return (img, 1.0) if kucult else img
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if kucult:
            # Basliktan boyutu okuyup TEK seferde dogru olcekte cozuyoruz.
            # Onceden once /2 sonra /4 cozuluyordu; ayni dosya iki kez
            # cozuldugu icin okuma suresi %60 fazlaydi (10.2 sn -> 6.5 sn).
            en_uzun = _jpeg_uzun_kenar(data)
            bayrak, olcek = cv2.IMREAD_COLOR, 1.0
            if en_uzun:
                for b, o in ((cv2.IMREAD_REDUCED_COLOR_8, 0.125),
                             (cv2.IMREAD_REDUCED_COLOR_4, 0.25),
                             (cv2.IMREAD_REDUCED_COLOR_2, 0.5)):
                    if en_uzun * o >= kucult:
                        bayrak, olcek = b, o
                        break
            img = cv2.imdecode(data, bayrak)
            if img is None and bayrak != cv2.IMREAD_COLOR:
                img = cv2.imdecode(data, cv2.IMREAD_COLOR)
                olcek = 1.0
            return img, olcek
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:
        pass
    # HEIC / cv2'nin okuyamadigi formatlar icin PIL denemesi
    try:
        from PIL import Image
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:
            pass
        with Image.open(str(path)) as im:
            im = im.convert("RGB")
            sonuc = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
            return (sonuc, 1.0) if kucult else sonuc
    except Exception:
        return (None, 1.0) if kucult else None


def list_images(kaynaklar):
    """
    Bir ya da birden fazla klasoru (alt klasorleriyle birlikte) tarar.
    Dondurur: [(dosya_yolu, ait_oldugu_kaynak_klasor), ...]
    """
    if isinstance(kaynaklar, (str, Path)):
        kaynaklar = [kaynaklar]
    ham = {}                       # (klasor, dosya_adi_govdesi) -> [(yol, kok), ...]
    for kaynak in kaynaklar:
        kok = str(Path(kaynak).resolve())
        for root, dirs, names in os.walk(kok):
            dirs[:] = [d for d in dirs if not d.startswith((".", "$"))]
            for n in names:
                if Path(n).suffix.lower() in IMAGE_EXT:
                    p = str(Path(root) / n)
                    anahtar = (root.lower(), Path(n).stem.lower())
                    liste = ham.setdefault(anahtar, [])
                    if all(x[0] != p for x in liste):   # ic ice klasor tekrari
                        liste.append((p, kok))

    def sira(yol):
        u = Path(yol).suffix.lower()
        return TARAMA_ONCELIGI.index(u) if u in TARAMA_ONCELIGI else len(TARAMA_ONCELIGI)

    out = []
    for _, liste in ham.items():
        liste.sort(key=lambda t: (sira(t[0]), t[0]))
        birincil, kok = liste[0]
        esler = [y for y, _ in liste[1:]]        # ayni karenin diger kopyalari
        out.append((birincil, kok, esler))
    out.sort()
    return out


def bagil_klasor(yol, kok, derinlik=0):
    """Fotografin kaynak klasorune gore bagil alt klasor yolu."""
    try:
        bagil = Path(yol).parent.resolve().relative_to(Path(kok).resolve())
    except (ValueError, OSError):
        return Path(".")
    if derinlik and len(bagil.parts) > derinlik:
        bagil = Path(*bagil.parts[:derinlik])
    return bagil


def fmt_eta(seconds):
    seconds = int(max(seconds, 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}s {m:02d}dk" if h else f"{m}dk {s:02d}sn"


def safe_folder_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name)).strip(" .")
    return name[:80] or "isimsiz"


def load_embeddings(con, min_score, min_face):
    rows = con.execute(
        "SELECT id, emb FROM faces WHERE det_score >= ? AND det_w >= ?",
        (min_score, min_face),
    ).fetchall()
    if not rows:
        return np.array([]), np.zeros((0, 512), np.float32)
    ids = np.array([r[0] for r in rows], dtype=np.int64)
    X = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    # guvenlik: normalize
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    return ids, X


# --- secki olcumleri -------------------------------------------------------
# 106 noktali modelde goz cevresi indeksleri (ampirik olarak dogrulandi:
# ayni yuzun varyantlarinda std 0.015 -> kararli; goz daraldikca deger duser)
SOL_GOZ = list(range(33, 43))
SAG_GOZ = list(range(87, 97))


def yuz_netligi(img, bbox):
    """Yuz bolgesinin netligi (Laplacian varyansi). Bulanik kare ~10, net ~90+."""
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = img.shape[:2]
    kirpma = img[max(y1, 0):min(y2, h), max(x1, 0):min(x2, w)]
    if kirpma.size == 0:
        return 0.0
    gri = cv2.cvtColor(kirpma, cv2.COLOR_BGR2GRAY)
    if max(gri.shape) > 200:                 # olcekten bagimsiz olsun
        o = 200.0 / max(gri.shape)
        gri = cv2.resize(gri, (max(int(gri.shape[1] * o), 8), max(int(gri.shape[0] * o), 8)))
    return float(cv2.Laplacian(gri, cv2.CV_64F).var())


def goz_aciklik(f):
    """Goz yuksekligi / genisligi. Acik goz ~0.33, kisilmis ~0.22."""
    lm = getattr(f, "landmark_2d_106", None)
    if lm is None or len(lm) < 97:
        return None
    out = []
    for idx in (SOL_GOZ, SAG_GOZ):
        p = lm[idx]
        yatay = float(p[:, 0].max() - p[:, 0].min())
        dikey = float(p[:, 1].max() - p[:, 1].min())
        if yatay > 1:
            out.append(dikey / yatay)
    return float(np.mean(out)) if out else None


def gorsel_imza(img):
    """dHash - neredeyse ayni kareleri bulmak icin 64 bitlik parmak izi."""
    try:
        gri = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        k = cv2.resize(gri, (9, 8), interpolation=cv2.INTER_AREA)
        bit = k[:, 1:] > k[:, :-1]
        deger = 0
        for b in bit.flatten():
            deger = (deger << 1) | int(b)
        return "%016x" % deger
    except Exception:
        return None


def imza_farki(a, b):
    """Iki imza arasindaki bit farki (0 = ayni kare)."""
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def cekim_zamani(yol):
    try:
        import pyexiv2
        import etiket as _et
        with _et.acilabilir(yol) as _acik:
            with pyexiv2.Image(_acik) as im:
                e = im.read_exif()
        for k in ("Exif.Photo.DateTimeOriginal", "Exif.Image.DateTime"):
            if e.get(k):
                return e[k]
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# Coklu surec: her isci modeli bir kez yukler, ONNX'i tek is parcacigina sabitler
# (yoksa 8 isci x 8 is parcacigi = asiri abonelik, yavaslar).
# --------------------------------------------------------------------------
_ISCI = {}


def _isci_baslat(model, gpu, det_size, max_side):
    import onnxruntime
    from insightface.app import FaceAnalysis
    onnxruntime.set_default_logger_severity(3)
    secenek = onnxruntime.SessionOptions()
    secenek.intra_op_num_threads = 1
    secenek.inter_op_num_threads = 1
    cv2.setNumThreads(1)
    saglayici = (["CUDAExecutionProvider", "CPUExecutionProvider"] if gpu
                 else ["CPUExecutionProvider"])
    app = FaceAnalysis(name=model, providers=saglayici,
                       allowed_modules=["detection", "recognition",
                                        "landmark_2d_106", "landmark_3d_68"])
    app.prepare(ctx_id=0 if gpu else -1, det_size=(det_size, det_size))
    _ISCI["app"] = app
    _ISCI["max_side"] = max_side


def _isci_isle(gorev):
    """Tek fotografi isler. (yol, mtime, size, kok, esler) -> sonuc sozlugu."""
    path, mtime, size, kok, esler = gorev
    app = _ISCI["app"]
    max_side = _ISCI["max_side"]
    status, rows, imza = "ok", [], None
    try:
        img, oku_olcek = imread_unicode(path, kucult=max_side)
        if img is None:
            return {"path": path, "mtime": mtime, "size": size, "kok": kok,
                    "esler": esler, "status": "okunamadi", "rows": [], "imza": None}
        h, w = img.shape[:2]
        olcek = oku_olcek
        if max(h, w) > max_side:
            o = max_side / max(h, w)
            img = cv2.resize(img, (int(w * o), int(h * o)), interpolation=cv2.INTER_AREA)
            olcek *= o
        imza = gorsel_imza(img)
        for f in app.get(img):
            bb = f.bbox.astype(float)
            det_w = float(bb[2] - bb[0])
            x1, y1, x2, y2 = (bb / olcek).tolist()      # gercek orijinal koordinat
            poz = getattr(f, "pose", None)
            rows.append((path, x1, y1, x2, y2, float(f.det_score), det_w,
                         np.asarray(f.normed_embedding, dtype=np.float32).tobytes(),
                         yuz_netligi(img, bb), goz_aciklik(f),
                         float(poz[1]) if poz is not None else None,
                         float(poz[0]) if poz is not None else None))
    except Exception as e:
        status = "hata: %s" % type(e).__name__
    return {"path": path, "mtime": mtime, "size": size, "kok": kok, "esler": esler,
            "status": status, "rows": rows, "imza": imza}


# --------------------------------------------------------------------------
# 1) SCAN — yuzleri bul ve vektorlerini kaydet
# --------------------------------------------------------------------------
def cmd_scan(args):
    from insightface.app import FaceAnalysis

    con = db_connect(args.db)
    kaynaklar = args.src if isinstance(args.src, list) else [args.src]
    print("Dosyalar listeleniyor...")
    for k in kaynaklar:
        print("  kaynak: %s" % k)
    if getattr(args, "kalite", False):
        # Olculdu (7728x5152 kareler): 1600/640 ile 8 kare kacti, 2560/800 ile
        # 4'u kurtarildi ve hiz ayni kaldi (cift cozme duzeltildikten sonra).
        if args.det_size == 640:
            args.det_size = 800
        if args.max_side == 1600:
            args.max_side = 2560
        print("  Yuksek kalite taramasi: %d px / dedektor %d "
              "(kucuk ve uzaktaki yuzler de yakalanir)" % (args.max_side, args.det_size))
    elif getattr(args, "hizli", False) and args.det_size == 640:
        args.det_size = 512
        print("  Hizli tarama: dedektor 512 (kucuk/uzak yuzler kacirilabilir)")
    files = list_images(kaynaklar)
    if args.limit:
        files = files[: args.limit]
    print(f"  {len(files)} gorsel bulundu"
          f"{' (%d klasorden)' % len(kaynaklar) if len(kaynaklar) > 1 else ''}.")

    done = {r[0]: (r[1], r[2]) for r in con.execute("SELECT path, mtime, size FROM files")}
    todo = []
    es_sayisi = sum(len(e) for _, _, e in files)
    if es_sayisi:
        print(f"  {es_sayisi} dosya ayni karenin baska bicimi (RAW/JPEG cifti) - "
              f"bir kez taranacak, hepsi birlikte islenecek.")
    for f, kok, esler in files:
        try:
            st = os.stat(f)
        except OSError:
            continue
        prev = done.get(f)
        if prev is None or abs(prev[0] - st.st_mtime) > 1 or prev[1] != st.st_size:
            todo.append((f, st.st_mtime, st.st_size, kok, esler))
    print(f"  {len(todo)} dosya islenecek ({len(files) - len(todo)} tanesi zaten islenmis).")
    if not todo:
        return

    # Olculdu: coklu surec CPU'da YAVASLATIYOR (1.14 -> 0.86 foto/sn).
    # Sebep: ONNX Runtime tek goruntu icin zaten tum cekirdekleri kullaniyor;
    # surec basina tek is parcacigina inince kazanc degil kayip oluyor.
    # Secenek duruyor (GPU'lu ya da cok cekirdekli makinelerde denenebilir).
    isci = args.isci if args.isci > 0 else 1
    if len(todo) < 8:
        isci = 1
    print(f"Model yukleniyor ({args.model}, {'GPU' if args.gpu else 'CPU'}, "
          f"{isci} surec)...")

    def kaydet(sonuc, sayac):
        con.execute("DELETE FROM faces WHERE path = ?", (sonuc["path"],))
        if sonuc["rows"]:
            con.executemany(
                "INSERT INTO faces(path,x1,y1,x2,y2,det_score,det_w,emb,"
                "netlik,goz,yaw,pitch) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", sonuc["rows"])
        con.execute(
            "INSERT OR REPLACE INTO files(path,mtime,size,n_faces,status,kok,esler,"
            "imza,zaman) VALUES(?,?,?,?,?,?,?,?,?)",
            (sonuc["path"], sonuc["mtime"], sonuc["size"], len(sonuc["rows"]),
             sonuc["status"], sonuc["kok"],
             "|".join(sonuc["esler"]) if sonuc["esler"] else None,
             sonuc["imza"], cekim_zamani(sonuc["path"])))
        return sayac + len(sonuc["rows"])

    t0 = time.time()
    n_faces_total = 0
    i = 0

    if isci == 1:
        _isci_baslat(args.model, args.gpu, args.det_size, args.max_side)
        for gorev in todo:
            i += 1
            n_faces_total = kaydet(_isci_isle(gorev), n_faces_total)
            if i % 20 == 0 or i == len(todo):
                con.commit()
                hiz = i / (time.time() - t0)
                print(f"  [{i}/{len(todo)}] {hiz:.2f} foto/sn | {n_faces_total} yuz | "
                      f"tahmini kalan: {fmt_eta((len(todo) - i) / max(hiz, 1e-6))}", flush=True)
    else:
        import concurrent.futures as cf
        with cf.ProcessPoolExecutor(
                max_workers=isci, initializer=_isci_baslat,
                initargs=(args.model, args.gpu, args.det_size, args.max_side)) as havuz:
            for sonuc in havuz.map(_isci_isle, todo, chunksize=1):
                i += 1
                n_faces_total = kaydet(sonuc, n_faces_total)
                if i % 20 == 0 or i == len(todo):
                    con.commit()
                    hiz = i / (time.time() - t0)
                    print(f"  [{i}/{len(todo)}] {hiz:.2f} foto/sn | {n_faces_total} yuz | "
                          f"tahmini kalan: {fmt_eta((len(todo) - i) / max(hiz, 1e-6))}",
                          flush=True)

    con.commit()
    print(f"Bitti. Toplam {n_faces_total} yuz kaydedildi -> {args.db}")


# --------------------------------------------------------------------------
# 2) CLUSTER — ayni kisinin yuzlerini grupla
# --------------------------------------------------------------------------
def cmd_cluster(args):
    from sklearn.cluster import DBSCAN

    con = db_connect(args.db)
    n_duzeltme = duzeltme_sayisi(con)
    if n_duzeltme and not args.evet:
        print("DIKKAT: bu veritabaninda %d elle duzeltme var "
              "(birlestirme/bolme/cikarma)." % n_duzeltme)
        print("Yeniden gruplamak bu duzeltmelerin HEPSINI siler.")
        try:
            c = input("Devam edilsin mi? (E = evet / h = hayir): ").strip().lower()
        except EOFError:
            c = "h"
        if c not in ("", "e", "evet", "y", "yes"):
            print("Iptal edildi - kumeler oldugu gibi kaldi.")
            return
        con.execute("DELETE FROM duzeltmeler")
        con.commit()
    ids, X = load_embeddings(con, args.min_score, args.min_face)
    if len(ids) == 0:
        print("Kumelenecek yuz yok. Once 'scan' calistir.")
        return
    print(f"{len(ids)} yuz kumeleniyor (eps={args.eps}, min_samples={args.min_samples})...")

    labels = DBSCAN(eps=args.eps, min_samples=args.min_samples, metric="cosine", n_jobs=-1).fit(X).labels_

    # gurultu (label -1) yuzlerini, yeterince benziyorsa en yakin kumeye ata
    uniq = sorted(set(labels) - {-1})
    if uniq and args.claim > 0:
        cents = np.vstack([X[labels == c].mean(axis=0) for c in uniq])
        cents /= np.linalg.norm(cents, axis=1, keepdims=True) + 1e-9
        noise = np.where(labels == -1)[0]
        if len(noise):
            sims = X[noise] @ cents.T
            best = sims.argmax(axis=1)
            good = sims.max(axis=1) >= args.claim
            labels[noise[good]] = np.array(uniq)[best[good]]
            print(f"  {int(good.sum())} tekil yuz en yakin kisiye eklendi (benzerlik >= {args.claim}).")

    # --- KURTARMA GECISI ---------------------------------------------------
    # Kumeye giremeyen yuzler, kisi merkezine daha GEVSEK esikle bakilarak
    # en yakin kisiye atanir ve SUPHELI isaretlenir. Gerekce: fotografci icin
    # eksik kare, yanlis kareden pahali - yanlisi gorup siler, eksigi fark etmez.
    supheliler = {}
    if args.kurtar > 0:
        uniq2 = sorted(set(labels) - {-1})
        if uniq2:
            cents = np.vstack([X[labels == c].mean(axis=0) for c in uniq2])
            cents /= np.linalg.norm(cents, axis=1, keepdims=True) + 1e-9
            kalan = np.where(labels == -1)[0]
            if len(kalan):
                sims = X[kalan] @ cents.T
                best = sims.argmax(axis=1)
                deger = sims.max(axis=1)
                uygun = (deger >= args.kurtar) & (deger < args.claim if args.claim else True)
                for i, k in enumerate(kalan):
                    if uygun[i]:
                        labels[k] = np.array(uniq2)[best[i]]
                        supheliler[int(ids[k])] = float(deger[i])
                if supheliler:
                    print("  %d yuz kurtarildi (benzerlik %.2f-%.2f) ve SUPHELI "
                          "isaretlendi." % (len(supheliler),
                                            min(supheliler.values()),
                                            max(supheliler.values())))

    # kumeleri buyukten kucuge 1,2,3... diye yeniden numarala
    sizes = {}
    for l in labels:
        if l != -1:
            sizes[l] = sizes.get(l, 0) + 1
    order = sorted(sizes, key=lambda c: -sizes[c])
    remap = {old: new for new, old in enumerate(order, 1)}
    final = np.array([remap.get(l, -1) for l in labels], dtype=np.int64)

    con.execute("UPDATE faces SET cluster = -1, supheli = NULL")
    con.executemany(
        "UPDATE faces SET cluster = ? WHERE id = ?", [(int(c), int(i)) for i, c in zip(ids, final)]
    )
    if supheliler:
        con.executemany("UPDATE faces SET supheli = ? WHERE id = ?",
                        [(b, i) for i, b in supheliler.items()])
    con.commit()

    n_person = len(order)
    n_noise = int((final == -1).sum())
    print(f"Sonuc: {n_person} farkli kisi bulundu, {n_noise} yuz siniflandirilamadi.")
    if supheliler:
        print(f"       {len(supheliler)} yuz supheli olarak eklendi - arayuzde "
              f"isaretli gorunur, kontrol edip cikarabilirsiniz.")
    print("En kalabalik 15 kisi (kume no / yuz sayisi / fotograf sayisi):")
    for cid, cnt, ph in con.execute(
        "SELECT cluster, COUNT(*), COUNT(DISTINCT path) FROM faces WHERE cluster > 0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC LIMIT 15"
    ):
        print(f"  kisi_{cid:04d}  {cnt:5d} yuz  {ph:5d} fotograf")


def kume_ornekleri(con, cid, adet):
    """Bir kumenin merkezine en yakin (en temsili) yuzlerini dondurur."""
    rows = con.execute(
        "SELECT path,x1,y1,x2,y2,emb,id,supheli FROM faces WHERE cluster = ?", (cid,)
    ).fetchall()
    if not rows:
        return []
    E = np.vstack([np.frombuffer(r[5], np.float32) for r in rows])
    E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
    merkez = E.mean(axis=0)
    merkez /= np.linalg.norm(merkez) + 1e-9
    puan = E @ merkez
    # Kurtarma gecisinde SUPHELI isaretlenen yuzler karta mutlaka girsin ki
    # kullanici gorup tiklayarak cikarabilsin. Kalan yerler en temsili yuzlerle
    # dolar; boylece kart hem "bu kim" sorusunu hem de "sunu kontrol et"i gosterir.
    supheli = sorted((i for i, r in enumerate(rows) if r[7] is not None),
                     key=lambda i: puan[i])[:max(1, adet // 2)]
    sira = list(supheli)
    for i in np.argsort(-puan):
        if len(sira) >= adet:
            break
        if int(i) not in sira:
            sira.append(int(i))
    return [(rows[i][6],) + tuple(rows[i][:5]) + (rows[i][7],) for i in sira]


def kume_vektorleri(con, cid):
    """Bir kumenin tum yuz vektorleri."""
    rows = con.execute("SELECT emb FROM faces WHERE cluster = ?", (cid,)).fetchall()
    if not rows:
        return np.zeros((0, 512), np.float32)
    return np.vstack([np.frombuffer(r[0], np.float32) for r in rows])


def isim_csv_oku(yol):
    """Kullanicinin yazdigi kesin isimleri okur (varsa)."""
    mevcut = {}
    if yol and Path(yol).exists():
        try:
            with open(yol, newline="", encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh, delimiter=";"):
                    try:
                        mevcut[int(row["kume_no"])] = (row.get("isim") or "").strip()
                    except (KeyError, TypeError, ValueError):
                        continue
        except OSError:
            pass
    return mevcut


def isim_csv_yaz(con, yol):
    """isimler.csv dosyasini yeniden yazar; kullanicinin yazdigi isimleri KORUR."""
    mevcut = isim_csv_oku(yol)
    kumeler = con.execute(
        "SELECT cluster, COUNT(DISTINCT path), COUNT(*) FROM faces WHERE cluster > 0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC"
    ).fetchall()
    oner = {r[0]: r for r in con.execute(
        "SELECT cluster, onerilen, puan, ornek, toplam FROM oneriler")}
    with open(yol, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["kume_no", "fotograf_sayisi", "onerilen_isim", "benzerlik", "isim"])
        for cid, nfoto, _ in kumeler:
            o = oner.get(cid)
            benzerlik = ("%.2f" % o[2]) if o and o[1] else ""
            w.writerow([cid, nfoto, (o[1] if o else "") or "", benzerlik, mevcut.get(cid, "")])
    return len(kumeler)


def kume_kapagi(con, cid, boy=140):
    """Kumenin en temsili yuzunden kucuk bir kapak resmi (JPEG baytlari)."""
    try:
        ornekler = kume_ornekleri(con, cid, 1)
        if not ornekler:
            return None
        _, p, x1, y1, x2, y2 = ornekler[0]
        img = imread_unicode(p)
        if img is None:
            return None
        h, w = img.shape[:2]
        mx, my = (x2 - x1) * 0.35, (y2 - y1) * 0.35
        a1, b1 = max(int(x1 - mx), 0), max(int(y1 - my), 0)
        a2, b2 = min(int(x2 + mx), w), min(int(y2 + my), h)
        kirpma = img[b1:b2, a1:a2]
        if kirpma.size == 0:
            return None
        kirpma = cv2.resize(kirpma, (boy, boy), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", kirpma, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else None
    except Exception:
        return None


def kutuphaneye_isle(con, names_yol, kutuphane_yolu, kaynak="", sessiz=False):
    """isimler.csv'de ismi olan her kumeyi kalici kutuphaneye ogretir."""
    import kutuphane

    isimler = isim_csv_oku(names_yol)
    dolu = {k: v for k, v in isimler.items() if v}
    if not dolu:
        if not sessiz:
            print("Ogrenilecek isim yok (isimler.csv bos).")
        return 0
    kcon = kutuphane.ac(kutuphane_yolu)
    n = 0
    for cid, isim in sorted(dolu.items()):
        E = kume_vektorleri(con, cid)
        if not len(E):
            continue
        adet = kutuphane.ogret(kcon, isim, E, kaynak=kaynak,
                               kapak=kume_kapagi(con, cid))
        n += 1
        if not sessiz:
            print("  ogrenildi: %-28s (%d ornek saklaniyor)" % (isim, adet))
    kcon.close()
    if not sessiz:
        print("%d kisi kutuphaneye islendi." % n)
    return n


# --------------------------------------------------------------------------
# 3b) TANI - kalici kutuphaneden isim eslestir (internet YOK)
# --------------------------------------------------------------------------
def cmd_tani(args):
    import kutuphane

    con = db_connect(args.db)
    kcon = kutuphane.ac(args.kutuphane)
    kayitli = kutuphane.herkes(kcon)
    if not kayitli:
        print("Kisi kutuphanesi bos.")
        print("Once bir bolumu isimlendirin; isimler onaylanınca kutuphane kendiliginden olusur.")
        print("Sonraki bolumlerde ayni kisiler otomatik taninacak.")
        return

    kumeler = con.execute(
        "SELECT cluster, COUNT(DISTINCT path) FROM faces WHERE cluster > 0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC"
    ).fetchall()
    if not kumeler:
        print("Once 'cluster' calistirin.")
        return

    print()
    print("=" * 66)
    print("  KUTUPHANEDEN TANIMA  -  internete cikmaz")
    print("=" * 66)
    print("  Kutuphanedeki kisi : %d" % len(kayitli))
    print("  Karsilastirilacak  : %d kume" % len(kumeler))
    print("  Esik               : %.2f benzerlik" % args.esik)
    print("-" * 66)

    bulunan = 0
    for cid, nfoto in kumeler:
        E = kume_vektorleri(con, cid)
        isim, ben, ikinci, gerekce = kutuphane.tani(kayitli, E, args.esik, args.fark)
        if isim:
            bulunan += 1
            con.execute(
                "INSERT OR REPLACE INTO oneriler(cluster,onerilen,puan,ornek,toplam,sayfalar) "
                "VALUES(?,?,?,?,?,?)", (cid, isim, ben, len(E), len(E), "kutuphane"))
            print("  kisi_%04d (%3d foto) -> %-26s benzerlik %.2f" % (cid, nfoto, isim, ben))
        else:
            con.execute(
                "INSERT OR REPLACE INTO oneriler(cluster,onerilen,puan,ornek,toplam,sayfalar) "
                "VALUES(?,?,?,?,?,?)", (cid, None, ben, len(E), len(E), gerekce))
            print("  kisi_%04d (%3d foto) -> yeni kisi  (%s, en yakin %.2f)"
                  % (cid, nfoto, gerekce, ben))
    con.commit()
    kcon.close()

    yol = args.names or "isimler.csv"
    isim_csv_yaz(con, yol)
    print("-" * 66)
    print("%d kume kutuphaneden taniandi, %d kume yeni kisi."
          % (bulunan, len(kumeler) - bulunan))
    print("Oneriler %s dosyasina yazildi. Onaylamak icin: onayla" % yol)


# --------------------------------------------------------------------------
# 3d) OGREN / KISILER - kutuphane yonetimi
# --------------------------------------------------------------------------
def cmd_ogren(args):
    con = db_connect(args.db)
    kutuphaneye_isle(con, args.names or "isimler.csv", args.kutuphane,
                     kaynak=Path(args.db).name)


def cmd_kisiler(args):
    import kutuphane

    kcon = kutuphane.ac(args.kutuphane)

    if args.disa_aktar:
        n = kutuphane.disa_aktar(kcon, args.disa_aktar)
        print("%d kisi disa aktarildi -> %s" % (n, args.disa_aktar))
        print("Bu dosyayi baska bir bilgisayara tasiyip --ice-aktar ile yukleyebilirsiniz.")
        return
    if args.ice_aktar:
        eklenen, guncellenen = kutuphane.ice_aktar(kcon, args.ice_aktar)
        print("%d yeni kisi eklendi, %d kisi guncellendi." % (eklenen, guncellenen))
        return

    if args.sil:
        if kutuphane.sil(kcon, args.sil):
            print("Silindi: %s" % args.sil)
        else:
            print("Kutuphanede boyle bir kisi yok: %s" % args.sil)
        return
    satirlar = kutuphane.liste(kcon)
    if not satirlar:
        print("Kisi kutuphanesi bos.")
        return
    print()
    print("KISI KUTUPHANESI  (%d kisi)" % len(satirlar))
    print("-" * 66)
    print("  %-30s %8s  %-16s" % ("isim", "ornek", "son guncelleme"))
    for isim, adet, eklenme, guncelleme in satirlar:
        print("  %-30s %8d  %-16s" % (isim, adet, guncelleme or eklenme or ""))
    print("-" * 66)
    print("Bir kisiyi silmek icin:  python face_sorter.py kisiler --sil \"Isim Soyisim\"")


# --------------------------------------------------------------------------
# 3c) ONAYLA - onerileri tek tek gozden gecir
# --------------------------------------------------------------------------
def cmd_confirm(args):
    con = db_connect(args.db)
    yol = args.names or "isimler.csv"
    isim_csv_yaz(con, yol)
    mevcut = isim_csv_oku(yol)

    kumeler = con.execute(
        "SELECT cluster, COUNT(DISTINCT path) FROM faces WHERE cluster > 0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC"
    ).fetchall()
    oner = {r[0]: r for r in con.execute(
        "SELECT cluster, onerilen, puan, ornek, toplam FROM oneriler")}

    print()
    print("Her kisi icin: Enter = oneriyi kabul et, isim yaz = duzelt,")
    print("'-' = bos birak, 'q' = kaydet ve cik.")
    print("Yuzleri gormek icin inceleme.html sayfasini acik tutun.")
    print("-" * 64)

    for cid, nfoto in kumeler:
        if mevcut.get(cid) and not args.hepsi:
            continue
        o = oner.get(cid)
        onerilen = (o[1] if o else "") or ""
        etiket = "kisi_%04d  (%d fotograf)" % (cid, nfoto)
        if onerilen:
            print("\n%s\n   oneri: %s   (%d/%d karede)" % (etiket, onerilen, o[3], o[4]))
        else:
            print("\n%s\n   oneri yok" % etiket)
        try:
            c = input("   isim: ").strip()
        except EOFError:
            break
        if c.lower() == "q":
            break
        if c == "-":
            mevcut[cid] = ""
        elif c:
            mevcut[cid] = c
        elif onerilen:
            mevcut[cid] = onerilen

    # kullanicinin verdigi isimleri csv'ye isle
    isim_csv_yaz(con, yol)
    satirlar = []
    with open(yol, newline="", encoding="utf-8-sig") as fh:
        okuyucu = csv.DictReader(fh, delimiter=";")
        basliklar = okuyucu.fieldnames
        for row in okuyucu:
            k = int(row["kume_no"])
            row["isim"] = mevcut.get(k, row.get("isim", ""))
            satirlar.append(row)
    with open(yol, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=basliklar, delimiter=";")
        w.writeheader()
        w.writerows(satirlar)

    dolu = sum(1 for v in mevcut.values() if v)
    print()
    print("%d kisiye isim verildi -> %s" % (dolu, yol))
    if dolu:
        print()
        print("Kisi kutuphanesine isleniyor (sonraki bolumlerde otomatik taninacaklar):")
        kutuphaneye_isle(con, yol, getattr(args, "kutuphane", None), kaynak=Path(args.db).name)
    print()
    print("Klasorleri bu isimlerle olusturmak icin 'export' adimini calistirin.")


def duzeltme_yaz(con, islem, detay):
    con.execute("INSERT INTO duzeltmeler(islem, detay, tarih) VALUES(?,?,?)",
                (islem, detay, time.strftime("%Y-%m-%d %H:%M")))
    con.commit()


def duzeltme_sayisi(con):
    try:
        return con.execute("SELECT COUNT(*) FROM duzeltmeler").fetchone()[0]
    except Exception:
        return 0


def cmd_birlestir(args):
    """Iki ya da daha fazla kumeyi tek kisi yapar (ayni insan iki gruba bolunmusse)."""
    con = db_connect(args.db)
    kumeler = sorted(set(int(k) for k in args.kume))
    if len(kumeler) < 2:
        print("En az iki kume numarasi verin:  --kume 3 7")
        return
    var = {r[0] for r in con.execute("SELECT DISTINCT cluster FROM faces WHERE cluster > 0")}
    eksik = [k for k in kumeler if k not in var]
    if eksik:
        print("Bu kumeler yok: %s" % eksik)
        return

    hedef = kumeler[0]
    digerleri = kumeler[1:]
    say = con.execute(
        "SELECT COUNT(*) FROM faces WHERE cluster IN (%s)" % ",".join("?" * len(digerleri)),
        digerleri).fetchone()[0]
    con.execute("UPDATE faces SET cluster = ? WHERE cluster IN (%s)"
                % ",".join("?" * len(digerleri)), [hedef] + digerleri)
    con.commit()
    duzeltme_yaz(con, "birlestir", "%s -> %d" % (digerleri, hedef))

    toplam = con.execute("SELECT COUNT(DISTINCT path) FROM faces WHERE cluster = ?",
                         (hedef,)).fetchone()[0]
    print("Birlestirildi: kume %s -> kisi_%04d" % (digerleri, hedef))
    print("  %d yuz tasindi, kisi_%04d artik %d fotografta." % (say, hedef, toplam))
    isim_csv_yaz(con, args.names or "isimler.csv")
    print("  Not: bu kisiye isim verdiyseniz 'ogren' ile kutuphaneyi guncelleyin.")


def cmd_bol(args):
    """Bir kumede iki farkli insan varsa daha kati esikle ikiye/uce ayirir."""
    from sklearn.cluster import AgglomerativeClustering

    con = db_connect(args.db)
    cid = int(args.kume)
    rows = con.execute("SELECT id, emb FROM faces WHERE cluster = ?", (cid,)).fetchall()
    if len(rows) < 4:
        print("kisi_%04d icinde bolunecek kadar yuz yok (%d)." % (cid, len(rows)))
        return
    ids = np.array([r[0] for r in rows])
    X = np.vstack([np.frombuffer(r[1], np.float32) for r in rows])
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    model = AgglomerativeClustering(n_clusters=None, metric="cosine",
                                    linkage="average", distance_threshold=args.esik)
    etiket = model.fit_predict(X)
    gruplar = {}
    for e, i in zip(etiket, ids):
        gruplar.setdefault(int(e), []).append(int(i))
    gruplar = {k: v for k, v in gruplar.items() if len(v) >= args.min_yuz}
    if len(gruplar) < 2:
        print("kisi_%04d tek kisi gibi duruyor (esik %.2f ile bolunemedi)." % (cid, args.esik))
        print("Daha cok parcaya bolmek icin esigi dusurun:  --esik %.2f"
              % max(args.esik - 0.10, 0.20))
        return

    en_buyuk = max(gruplar, key=lambda k: len(gruplar[k]))
    yeni_no = (con.execute("SELECT MAX(cluster) FROM faces").fetchone()[0] or 0)
    olusan = []
    for g, uyeler in gruplar.items():
        if g == en_buyuk:
            hedef = cid                       # en kalabalik grup eski numarada kalir
        else:
            yeni_no += 1
            hedef = yeni_no
        con.executemany("UPDATE faces SET cluster = ? WHERE id = ?",
                        [(hedef, u) for u in uyeler])
        olusan.append((hedef, len(uyeler)))
    # hicbir gruba girmeyen yuzler siniflandirilmamis olsun
    kalanlar = set(int(i) for i in ids) - {u for v in gruplar.values() for u in v}
    if kalanlar:
        con.executemany("UPDATE faces SET cluster = -1 WHERE id = ?",
                        [(u,) for u in kalanlar])
    con.commit()
    duzeltme_yaz(con, "bol", "kume %d -> %s" % (cid, [o[0] for o in olusan]))

    print("kisi_%04d bolundu (esik %.2f):" % (cid, args.esik))
    for hedef, adet in sorted(olusan):
        foto = con.execute("SELECT COUNT(DISTINCT path) FROM faces WHERE cluster = ?",
                           (hedef,)).fetchone()[0]
        print("  kisi_%04d : %d yuz, %d fotograf" % (hedef, adet, foto))
    if kalanlar:
        print("  %d yuz siniflandirilamadi." % len(kalanlar))
    isim_csv_yaz(con, args.names or "isimler.csv")


def cmd_cikar(args):
    """Yanlis eslesmis tek tek yuzleri kumeden cikarir ('bu kisi degil')."""
    con = db_connect(args.db)
    yuzler = [int(y) for y in args.yuz]
    if not yuzler:
        print("Cikarilacak yuz numarasi verin:  --yuz 1234 1235")
        return
    var = con.execute("SELECT COUNT(*) FROM faces WHERE id IN (%s)"
                      % ",".join("?" * len(yuzler)), yuzler).fetchone()[0]
    con.executemany("UPDATE faces SET cluster = -1 WHERE id = ?", [(y,) for y in yuzler])
    con.commit()
    duzeltme_yaz(con, "cikar", str(yuzler))
    print("%d yuz kumesinden cikarildi (artik 'siniflandirilamayan')." % var)
    isim_csv_yaz(con, args.names or "isimler.csv")


# --------------------------------------------------------------------------
# 3) REVIEW — kimin kim oldugunu gormek icin HTML + isim dosyasi
# --------------------------------------------------------------------------
def _dosya_eslestir(con, satirlar):
    """
    Oyuncu/ajans genelde sadece dosya ADINI gonderir (DSC_1234.jpg).
    Tam yol da gelebilir. Ikisini de eslestirir.
    """
    tum = [r[0] for r in con.execute("SELECT path FROM files")]
    ad_haritasi = {}
    for p in tum:
        ad_haritasi.setdefault(os.path.basename(p).lower(), []).append(p)
        ad_haritasi.setdefault(os.path.splitext(os.path.basename(p))[0].lower(), []).append(p)
    tam = {p.lower(): p for p in tum}

    bulunan, bulunamayan = [], []
    for ham in satirlar:
        t = ham.strip().strip('"').strip()
        if not t or t.startswith("#"):
            continue
        if t.lower() in tam:
            bulunan.append(tam[t.lower()])
            continue
        anahtar = os.path.basename(t).lower()
        adaylar = ad_haritasi.get(anahtar) or ad_haritasi.get(os.path.splitext(anahtar)[0].lower())
        if adaylar:
            bulunan.extend(adaylar)
        else:
            bulunamayan.append(t)
    return sorted(set(bulunan)), bulunamayan


def cmd_onay(args):
    """Oyuncu vetosu (kill list) ve onay kayitlari."""
    con = db_connect(args.db)

    if args.liste:
        satirlar = con.execute(
            "SELECT durum, COUNT(*) FROM onay GROUP BY durum").fetchall()
        if not satirlar:
            print("Onay/veto kaydi yok.")
            return
        print()
        print("ONAY DURUMU")
        print("-" * 50)
        for durum, adet in satirlar:
            print("  %-10s %5d kare" % (durum, adet))
        print("-" * 50)
        for p, k, d, kay in con.execute(
                "SELECT path, kisi, durum, kaynak FROM onay ORDER BY durum, path LIMIT 15"):
            print("  %-9s %-28s %s" % (d, os.path.basename(p),
                                       ("kisi_%04d" % k) if k else "tum kisiler"))
        toplam = con.execute("SELECT COUNT(*) FROM onay").fetchone()[0]
        if toplam > 15:
            print("  ... ve %d kayit daha" % (toplam - 15))
        return

    if args.temizle:
        n = con.execute("SELECT COUNT(*) FROM onay").fetchone()[0]
        con.execute("DELETE FROM onay")
        con.commit()
        print("%d onay/veto kaydi silindi." % n)
        return

    durum = "red" if args.red else "onayli"
    kisi = int(args.kisi) if args.kisi else None

    yollar = []
    if args.kisi and args.hepsi:
        soru = "SELECT DISTINCT path FROM faces WHERE cluster = ?"
        yollar = [r[0] for r in con.execute(soru, (kisi,))]
        print("kisi_%04d icin %d kare isaretlenecek." % (kisi, len(yollar)))
    elif args.dosya:
        p = Path(args.dosya)
        if not p.exists():
            print("Liste dosyasi bulunamadi: %s" % p)
            return
        ham = p.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        yollar, eksik = _dosya_eslestir(con, ham)
        print("%d satirdan %d kare eslesti." % (len([x for x in ham if x.strip()]), len(yollar)))
        if eksik:
            print("Eslesmeyen %d satir (ilk 5):" % len(eksik))
            for e in eksik[:5]:
                print("   " + e)
    elif args.foto:
        yollar, eksik = _dosya_eslestir(con, args.foto)
        if eksik:
            print("Eslesmeyen: %s" % ", ".join(eksik))
    else:
        print("Ne isaretlenecegini belirtin:")
        print("  --dosya veto.txt            (oyuncudan gelen liste)")
        print("  --foto DSC_1234.jpg ...     (tek tek)")
        print("  --kisi 3 --hepsi            (o kisinin tum kareleri)")
        return

    if not yollar:
        print("Isaretlenecek kare bulunamadi.")
        return

    con.executemany(
        "INSERT OR REPLACE INTO onay(path,kisi,durum,kaynak,tarih) VALUES(?,?,?,?,?)",
        [(y, kisi, durum, args.kaynak or "", time.strftime("%Y-%m-%d %H:%M")) for y in yollar])
    con.commit()
    print("%d kare '%s' olarak isaretlendi%s."
          % (len(yollar), durum, (" (kisi_%04d)" % kisi) if kisi else ""))
    if durum == "red":
        print("Klasorleme ve isim yazmada bu kareler otomatik disarida birakilir.")
        print("(Zorlamak icin: --vetoyu-yoksay)")


def cmd_secki(args):
    """Bulanik, gozu kapali ve tekrar kareleri isaretler; her seride en iyiyi secer."""
    con = db_connect(args.db)
    kayitlar = con.execute(
        "SELECT f.path, f.imza, f.zaman, "
        "  MAX(y.netlik), MAX(y.goz), MAX(y.det_score), MIN(ABS(COALESCE(y.yaw,0))), "
        "  MAX(y.det_w) "
        "FROM files f LEFT JOIN faces y ON y.path = f.path "
        "WHERE f.n_faces > 0 GROUP BY f.path ORDER BY f.path").fetchall()
    if not kayitlar:
        print("Once tarama yapin.")
        return

    netlikler = [k[3] for k in kayitlar if k[3]]
    if not netlikler:
        print("Bu veritabaninda olcum yok. Yeni surumle yeniden tarayin "
              "(eski kayitlarda netlik/goz bilgisi yok).")
        return
    # Bulaniklik yuzde-dilimle olculmez: oyle olsa her setin %15'i hep isaretlenirdi,
    # hepsi net olsa bile. Mutlak taban kullanilir (olculdu: net yuz 85-135,
    # GaussianBlur(31) uygulanmis ayni yuz 10). Kucuk yuzler dogal olarak dusuk
    # deger verir, o yuzden yalnizca BUYUK yuzlerde bulaniklik iddia edilir.
    net_esik = args.netlik if args.netlik > 0 else 22.0

    # Goz aciklik KISIYE GORE degerlendirilir. Olculdu: bir kisinin normali 0.33
    # iken baska birinin normali 0.14 olabiliyor (goz sekli/aci farki). Mutlak
    # esik kullanmak o kisinin TUM karelerini "gozu kapali" sayardi.
    kisi_goz = {}
    try:
        for cid, g in con.execute(
                "SELECT cluster, goz FROM faces WHERE cluster > 0 AND goz IS NOT NULL"):
            kisi_goz.setdefault(cid, []).append(g)
    except Exception:
        pass
    kisi_taban = {cid: float(np.median(v)) for cid, v in kisi_goz.items()
                  if len(v) >= args.min_ornek}
    yol_kisi = {}
    try:
        for yol, cid in con.execute(
                "SELECT path, cluster FROM faces WHERE cluster > 0"):
            yol_kisi.setdefault(yol, cid)
    except Exception:
        pass
    genel_goz = [k[4] for k in kayitlar if k[4]]
    genel_taban = float(np.median(genel_goz)) if genel_goz else 0.0

    def goz_dusuk_mu(yol, deger):
        if deger is None:
            return False
        if args.goz > 0:                       # kullanici elle esik verdiyse
            return deger < args.goz
        cid = yol_kisi.get(yol)
        taban = kisi_taban.get(cid)
        if taban is None:
            # Bu kisi icin yeterli ornek yok. Baskasinin ortalamasiyla kiyaslamak
            # yanlis damga vurur (olculdu: bir kisinin normali 0.33, digerinin 0.14).
            return False
        return deger < taban * args.goz_orani

    print()
    print("=" * 66)
    print("  SECKI  -  %d fotograf inceleniyor" % len(kayitlar))
    print("=" * 66)
    print("  Netlik esigi     : %.0f  (%s, yalniz %d px'ten buyuk yuzlerde)"
          % (net_esik, "elle" if args.netlik > 0 else "varsayilan", args.min_yuz_px))
    if args.goz > 0:
        print("  Goz esigi        : %.3f (elle)" % args.goz)
    else:
        print("  Goz olcutu       : kisinin kendi ortalamasinin %%%.0f alti"
              % (args.goz_orani * 100))
        print("                     %d kisi icin taban var; taban olmayanlar "
              "isaretlenmez" % len(kisi_taban))
    print("  Tekrar kare farki: %d bit  (0 = birebir ayni)" % args.tekrar)
    print("-" * 66)

    # --- tekrar/seri gruplama: ayni klasorde, ardisik, gorsel olarak neredeyse ayni
    con.execute("DELETE FROM secki")
    grup_no = 0
    onceki = None
    gruplar = []
    for k in kayitlar:
        yol, imza = k[0], k[1]
        ayni_klasor = onceki and os.path.dirname(onceki[0]) == os.path.dirname(yol)
        if onceki and ayni_klasor and imza_farki(onceki[1], imza) <= args.tekrar:
            gruplar[-1].append(k)
        else:
            grup_no += 1
            gruplar.append([k])
        onceki = k

    def puan(k):
        netlik = k[3] or 0.0
        goz = k[4] or 0.0
        skor = k[5] or 0.0
        sapma = k[6] or 0.0
        return (min(netlik / max(net_esik * 2, 1), 2.0) * 2.0
                + min(goz / 0.33, 1.5) * 1.5
                + skor
                - min(abs(sapma) / 45.0, 1.0))

    bulanik = goz_kapali = tekrar = 0
    for i, g in enumerate(gruplar, 1):
        en_iyi = max(g, key=puan)
        for k in g:
            bayraklar = []
            buyuk_yuz = (k[7] or 0) >= args.min_yuz_px
            if buyuk_yuz and k[3] is not None and k[3] < net_esik:
                bayraklar.append("bulanik")
            if goz_dusuk_mu(k[0], k[4]):
                bayraklar.append("goz_kapali")
            if len(g) > 1 and k[0] != en_iyi[0]:
                bayraklar.append("tekrar")
            if "bulanik" in bayraklar:
                bulanik += 1
            if "goz_kapali" in bayraklar:
                goz_kapali += 1
            if "tekrar" in bayraklar:
                tekrar += 1
            con.execute(
                "INSERT OR REPLACE INTO secki(path,bayrak,puan,grup,en_iyi) VALUES(?,?,?,?,?)",
                (k[0], ",".join(bayraklar), puan(k), i, 1 if k[0] == en_iyi[0] else 0))
    con.commit()

    seri = sum(1 for g in gruplar if len(g) > 1)
    temiz = con.execute("SELECT COUNT(*) FROM secki WHERE bayrak = ''").fetchone()[0]
    print("  Seri/tekrar grubu : %d  (%d kare elendi, her seride en iyi kaldi)"
          % (seri, tekrar))
    print("  Bulanik           : %d" % bulanik)
    print("  Gozu kapali/kisik : %d" % goz_kapali)
    print("  Temiz kare        : %d / %d" % (temiz, len(kayitlar)))
    print("-" * 66)
    print("  Klasorlemede/etikette kullanmak icin:  --secki-atla")
    print("  Isaretler 'secki' tablosunda; bu komutu tekrar calistirmak zararsiz.")


def cmd_review(args):
    con = db_connect(args.db)
    clusters = con.execute(
        "SELECT cluster, COUNT(*), COUNT(DISTINCT path) FROM faces WHERE cluster > 0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC"
    ).fetchall()
    if not clusters:
        print("Kume yok. Once 'cluster' calistir.")
        return
    if args.max_clusters:
        clusters = clusters[: args.max_clusters]

    oneriler = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "SELECT cluster, onerilen, ornek, toplam FROM oneriler")}
    isimler = isim_csv_oku(Path(args.out).with_name("isimler.csv"))

    parts = [
        "<meta charset='utf-8'><title>Yuz kumeleri</title>",
        "<style>body{font-family:system-ui,sans-serif;background:#111;color:#eee;margin:24px}"
        ".k{margin:0 0 22px;padding:12px;background:#1c1c1c;border-radius:10px}"
        "h2{font-size:15px;margin:0 0 8px} img{border-radius:6px;margin-right:6px}"
        "</style>",
        f"<h1>{len(clusters)} kisi bulundu</h1>",
        "<p>Asagidaki kume numaralarini <b>isimler.csv</b> dosyasina yazip "
        "<code>export</code> komutunu calistir; klasorler o isimlerle acilir.</p>",
    ]

    for cid, n_face, n_photo in clusters:
        rows = con.execute(
            "SELECT path,x1,y1,x2,y2,emb FROM faces WHERE cluster = ?", (cid,)
        ).fetchall()
        E = np.vstack([np.frombuffer(r[5], np.float32) for r in rows])
        cent = E.mean(axis=0)
        cent /= np.linalg.norm(cent) + 1e-9
        best = np.argsort(-(E @ cent))[: args.samples]

        thumbs = []
        for j in best:
            p, x1, y1, x2, y2, _ = rows[j]
            img = imread_unicode(p)
            if img is None:
                continue
            h, w = img.shape[:2]
            mx, my = (x2 - x1) * 0.35, (y2 - y1) * 0.35
            cx1, cy1 = max(int(x1 - mx), 0), max(int(y1 - my), 0)
            cx2, cy2 = min(int(x2 + mx), w), min(int(y2 + my), h)
            crop = img[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                continue
            crop = cv2.resize(crop, (110, 110), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                thumbs.append(
                    f"<img src='data:image/jpeg;base64,{base64.b64encode(buf).decode()}'>"
                )
        o = oneriler.get(cid)
        ek = ""
        if o and o[0]:
            ek = (f" &nbsp;·&nbsp; <span style='color:#6cf'>oneri: {o[0]}</span>"
                  f" <span style='color:#888;font-size:12px'>({o[1]}/{o[2]} karede)</span>")
        if isimler.get(cid):
            ek += f" &nbsp;·&nbsp; <span style='color:#7d7'>isim: {isimler[cid]}</span>"
        parts.append(
            f"<div class='k'><h2>kisi_{cid:04d} &nbsp;—&nbsp; {n_photo} fotograf, {n_face} yuz{ek}</h2>"
            + "".join(thumbs)
            + "</div>"
        )

    Path(args.out).write_text("\n".join(parts), encoding="utf-8")

    csv_path = Path(args.out).with_name("isimler.csv")
    isim_csv_yaz(con, csv_path)
    print(f"Isim dosyasi guncellendi: {csv_path}")

    print(f"Inceleme sayfasi hazir: {args.out}  (tarayicida ac)")


def cmd_etiketle(args):
    """Kisi isimlerini fotograflarin metadata'sina yazar (kopya olusturmaz)."""
    import etiket

    try:
        etiket.hazirla()
    except RuntimeError as e:
        print(e)
        return

    print()
    print("=" * 66)
    print("  METADATA'YA ISIM YAZMA  -  kopya olusturulmaz")
    print("=" * 66)
    print("  Yazim yeri : %s" % ("dosyanin icine (gomulu)" if args.mod == "gomulu"
                                 else "yan .xmp dosyasina"))
    print("  Bicimler   : anahtar kelime + MWG bolgeleri + ACDSee bolgeleri")
    print("  Not        : goruntu verisine dokunulmaz, mevcut etiketler korunur.")
    print("               RAW dosyalarda her zaman yan .xmp yazilir.")
    if args.kisi:
        print("  Kisi filtresi: %s" % ", ".join("kisi_%04d" % int(k) for k in args.kisi))
    if args.limit:
        print("  DENEME     : yalnizca ilk %d fotograf" % args.limit)
    print("=" * 66)
    if not args.evet:
        try:
            print()
            c = input("  Devam edilsin mi? (E = evet / h = hayir): ").strip().lower()
        except EOFError:
            c = "h"
        if c not in ("", "e", "evet", "y", "yes"):
            print("  Iptal edildi - hicbir dosyaya dokunulmadi.")
            return
    print()
    kunye = None
    if args.kunye:
        kunye = dict(etiket.VARSAYILAN_KUNYE)
        try:
            ayar = json.loads(Path(args.ayarlar).read_text(encoding="utf-8"))
            kunye.update(ayar.get("kunye") or {})
        except Exception:
            pass
        kunye["aktif"] = True
        for alan in ("yapim", "bolum", "sahne", "fotografci", "telif", "kaynak"):
            deger = getattr(args, alan, "")
            if deger:
                kunye[alan] = deger
    etiket.etiketle(args.db, args.names or "isimler.csv", mod=args.mod,
                    limit=args.limit, dogrula_adet=args.dogrula,
                    kisiler=[int(k) for k in args.kisi] if args.kisi else None,
                    kunye=kunye)


# --------------------------------------------------------------------------
# 4) EXPORT — kisi klasorlerini olustur ve fotograflari yerlestir
# --------------------------------------------------------------------------
def dosya_sistemi(yol):
    """Hedefin dosya sistemi adi (NTFS / exFAT / FAT32 / APFS ...). Bulunamazsa ''."""
    try:
        if os.name == "nt":
            import ctypes

            kok = os.path.splitdrive(os.path.abspath(str(yol)))[0] + "\\"
            tampon = ctypes.create_unicode_buffer(256)
            ok = ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(kok), None, 0, None, None, None, tampon, 256
            )
            return tampon.value if ok else ""
        # macOS / Linux
        import subprocess

        cikti = subprocess.run(["df", "-T", str(yol)], capture_output=True, text=True).stdout
        satirlar = cikti.strip().splitlines()
        if len(satirlar) > 1:
            return satirlar[-1].split()[1]
    except Exception:
        pass
    return ""


def hardlink_denemesi(ornek_kaynak, hedef_dizin):
    """Hedef diskte sabit bag kurulabiliyor mu? (NTFS + ayni disk gerekir)"""
    t = Path(hedef_dizin) / ".baglanti_testi.tmp"
    try:
        if t.exists():
            t.unlink()
        os.link(ornek_kaynak, t)
        sonuc = True
    except OSError:
        sonuc = False
    try:
        t.unlink()
    except OSError:
        pass
    return sonuc


def cmd_rapor(args):
    """Kimler var, kim kiminle birlikte, hangi klasorde kac kare."""
    con = db_connect(args.db)
    isimler = isim_csv_oku(args.names or "isimler.csv")

    def ad(cid):
        return isimler.get(cid) or ("kisi_%04d" % cid)

    kisiler = con.execute(
        "SELECT cluster, COUNT(DISTINCT path), COUNT(*) FROM faces WHERE cluster > 0 "
        "GROUP BY cluster ORDER BY COUNT(DISTINCT path) DESC").fetchall()
    if not kisiler:
        print("Once tarama ve gruplama yapin.")
        return

    toplam_foto = con.execute("SELECT COUNT(*) FROM files WHERE n_faces > 0").fetchone()[0]
    tum_foto = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    print()
    print("=" * 70)
    print("  RAPOR")
    print("=" * 70)
    print("  Fotograf        : %d (yuz iceren: %d)" % (tum_foto, toplam_foto))
    print("  Kisi            : %d   (isim verilmis: %d)"
          % (len(kisiler), sum(1 for c, _, _ in kisiler if isimler.get(c))))
    try:
        s_ = con.execute("SELECT COUNT(*) FROM secki WHERE bayrak != ''").fetchone()[0]
        if s_:
            print("  Secki isaretli  : %d kare" % s_)
    except Exception:
        pass
    try:
        v = con.execute("SELECT COUNT(*) FROM onay WHERE durum='red'").fetchone()[0]
        if v:
            print("  Vetolu          : %d kare" % v)
    except Exception:
        pass

    print()
    print("  KISILER" + " " * 26 + "fotograf   yuz")
    print("  " + "-" * 66)
    for cid, nfoto, nyuz in kisiler[:args.limit or 25]:
        print("  %-40s %6d %6d" % (ad(cid)[:40], nfoto, nyuz))
    if len(kisiler) > (args.limit or 25):
        print("  ... ve %d kisi daha" % (len(kisiler) - (args.limit or 25)))

    # --- kim kiminle birlikte
    beraber = {}
    kare_kisi = {}
    for cid, yol in con.execute(
            "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"):
        kare_kisi.setdefault(yol, set()).add(cid)
    for kumeler in kare_kisi.values():
        k = sorted(kumeler)
        for i in range(len(k)):
            for j in range(i + 1, len(k)):
                beraber[(k[i], k[j])] = beraber.get((k[i], k[j]), 0) + 1
    if beraber:
        print()
        print("  BIRLIKTE EN COK GORUNENLER")
        print("  " + "-" * 66)
        for (a, b), adet in sorted(beraber.items(), key=lambda x: -x[1])[:10]:
            print("  %-30s + %-24s %5d kare" % (ad(a)[:30], ad(b)[:24], adet))

    # --- klasor dagilimi
    klasorler = {}
    for yol, in con.execute("SELECT path FROM files WHERE n_faces > 0"):
        klasorler[os.path.dirname(yol)] = klasorler.get(os.path.dirname(yol), 0) + 1
    if len(klasorler) > 1:
        print()
        print("  KLASOR DAGILIMI")
        print("  " + "-" * 66)
        for k, adet in sorted(klasorler.items(), key=lambda x: -x[1])[:10]:
            print("  %-58s %5d" % (("..." + k[-55:]) if len(k) > 58 else k, adet))


def cmd_ara(args):
    """Belirli kisilerin (hepsinin birden) gorundugu kareleri listeler."""
    con = db_connect(args.db)
    isimler = isim_csv_oku(args.names or "isimler.csv")
    ters = {}
    for cid, adi in isimler.items():
        if adi:
            ters.setdefault(adi.lower(), []).append(cid)

    aranan = []
    for t in args.kisi:
        t = str(t).strip()
        if t.isdigit():
            aranan.append(int(t))
            continue
        bulundu = []
        for adi, kumeler in ters.items():
            if t.lower() in adi:
                bulundu.extend(kumeler)
        if not bulundu:
            print("Bulunamadi: %s" % t)
            return
        aranan.extend(bulundu)

    kare_kisi = {}
    for cid, yol in con.execute(
            "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"):
        kare_kisi.setdefault(yol, set()).add(cid)

    istenen = set(aranan)
    if args.herhangi:
        sonuc = [y for y, k in kare_kisi.items() if k & istenen]
        kural = "herhangi biri"
    else:
        sonuc = [y for y, k in kare_kisi.items() if istenen <= k]
        kural = "hepsi birden"
    sonuc.sort()

    adlar = [isimler.get(c) or ("kisi_%04d" % c) for c in sorted(istenen)]
    print()
    print("Aranan (%s): %s" % (kural, ", ".join(adlar)))
    print("Bulunan kare : %d" % len(sonuc))
    print("-" * 66)
    for y in sonuc[:args.limit or 40]:
        print("  " + y)
    if len(sonuc) > (args.limit or 40):
        print("  ... ve %d kare daha" % (len(sonuc) - (args.limit or 40)))
    if args.dosyaya:
        Path(args.dosyaya).write_text("\n".join(sonuc), encoding="utf-8")
        print()
        print("Liste yazildi: %s" % args.dosyaya)
        print("(Bu dosyayi 'teslim' ya da 'onay' komutuna verebilirsiniz.)")


def cmd_teslim(args):
    """Secilen kareleri kucultup filigranlayarak teslim paketine cevirir."""
    import teslim as tp

    con = db_connect(args.db)
    isimler = isim_csv_oku(args.names or "isimler.csv")

    dosya_suzgeci = None
    if getattr(args, "dosya_listesi", ""):
        try:
            dosya_suzgeci = {x.strip() for x in
                             Path(args.dosya_listesi).read_text(encoding="utf-8").splitlines()
                             if x.strip()}
            print("Dosya listesi: %d kare ile sinirlandirildi." % len(dosya_suzgeci))
        except OSError:
            print("Dosya listesi okunamadi: %s" % args.dosya_listesi)

    secili = set(int(k) for k in (args.kisi or []))
    if args.sadece_isimli:
        isimliler = {c for c, ad in isimler.items() if ad}
        secili = (secili & isimliler) if secili else isimliler

    elenen = set()
    if not args.secki_yoksay:
        try:
            elenen = {r[0] for r in con.execute("SELECT path FROM secki WHERE bayrak != ''")}
        except Exception:
            elenen = set()
    veto = {}
    try:
        for p, k in con.execute("SELECT path, kisi FROM onay WHERE durum = 'red'"):
            veto.setdefault(p, set()).add(k)
    except Exception:
        pass

    dosya_suzgeci = None
    if getattr(args, "dosya_listesi", ""):
        try:
            dosya_suzgeci = {x.strip() for x in
                             Path(args.dosya_listesi).read_text(encoding="utf-8").splitlines()
                             if x.strip()}
            print("Dosya listesi: %d kare." % len(dosya_suzgeci))
        except OSError:
            pass

    kayitlar = {}
    for cid, yol in con.execute(
            "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"):
        if dosya_suzgeci is not None and yol not in dosya_suzgeci:
            continue
        if secili and cid not in secili:
            continue
        if yol in elenen:
            continue
        v = veto.get(yol)
        if v is not None and (None in v or cid in v):
            continue
        ad = isimler.get(cid) or ("kisi_%04d" % cid)
        kayitlar.setdefault(yol, []).append(ad)

    if not kayitlar:
        print("Teslim edilecek kare yok. Filtreleri gevsetin ya da once isimlendirin.")
        return

    dosyalar = []
    for yol, adlar in sorted(kayitlar.items()):
        alt = safe_folder_name(sorted(adlar)[0]) if args.kisiye_gore else None
        dosyalar.append((yol, alt))

    print()
    print("=" * 66)
    print("  TESLIM PAKETI")
    print("=" * 66)
    print("  Kare sayisi   : %d" % len(dosyalar))
    print("  Uzun kenar    : %d px   Kalite: %d" % (args.boyut, args.kalite))
    print("  Filigran      : %s" % (args.filigran or "yok"))
    print("  Duzen         : %s" % ("kisiye gore klasor" if args.kisiye_gore else "tek klasor"))
    print("  Kontak baskisi: %s" % ("evet (PDF)" if not args.kontak_yok else "hayir"))
    print("  Hedef         : %s" % args.dst)
    print("  Not           : orijinallere dokunulmaz, metadata yeni dosyalara tasinir.")
    print("=" * 66)
    if not args.evet:
        try:
            print()
            c = input("  Devam edilsin mi? (E = evet / h = hayir): ").strip().lower()
        except EOFError:
            c = "h"
        if c not in ("", "e", "evet", "y", "yes"):
            print("  Iptal edildi.")
            return
    print()
    tp.paket_yap(dosyalar, args.dst, uzun_kenar=args.boyut, kalite=args.kalite,
                 filigran=args.filigran, kontak=not args.kontak_yok,
                 baslik=args.baslik or Path(args.dst).name)


def cmd_export(args):
    con = db_connect(args.db)
    names = {}
    if args.names and Path(args.names).exists():
        with open(args.names, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                nm = (row.get("isim") or "").strip()
                if nm:
                    names[int(row["kume_no"])] = nm
        print(f"{len(names)} kisi ismi okundu.")

    elenen = set()
    veto = {}
    if not getattr(args, "vetoyu_yoksay", False):
        try:
            for p, k in con.execute("SELECT path, kisi FROM onay WHERE durum = 'red'"):
                veto.setdefault(p, set()).add(k)
        except Exception:
            veto = {}
        if veto:
            print("Veto: %d kare icin oyuncu onayi yok." % len(veto))

    if getattr(args, "secki_atla", False):
        try:
            elenen = {r[0] for r in con.execute(
                "SELECT path FROM secki WHERE bayrak != ''")}
        except Exception:
            elenen = set()
        if elenen:
            print("Secki: %d isaretli kare disarida birakiliyor." % len(elenen))
        else:
            print("Secki isareti yok - once 'secki' komutunu calistirin.")

    secili = set(int(k) for k in (args.kisi or []))
    if args.sadece_isimli:
        adlar = isim_csv_oku(args.names or "isimler.csv")
        isimliler = {c for c, ad in adlar.items() if ad}
        secili = (secili & isimliler) if secili else isimliler
        if not secili:
            print("Isim verilmis kisi yok - once isimlendirin.")
            return
    if secili:
        print("Yalnizca secilen %d kisi islenecek: %s"
              % (len(secili), ", ".join("kisi_%04d" % c for c in sorted(secili))))

    groups = {}
    for cid, path in con.execute(
        "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"
    ):
        if path in elenen:
            continue
        if dosya_suzgeci is not None and path not in dosya_suzgeci:
            continue
        if secili and cid not in secili:
            continue
        v = veto.get(path)
        if v is not None and (None in v or cid in v):
            continue                      # bu kare (bu kisi icin) vetolu
        groups.setdefault(cid, []).append(path)

    if args.export_unknown:
        unk = [r[0] for r in con.execute("SELECT DISTINCT path FROM faces WHERE cluster = -1")]
        if unk:
            groups["_bilinmeyen"] = unk
    if args.export_nofaces:
        nof = [r[0] for r in con.execute("SELECT path FROM files WHERE n_faces = 0")]
        if nof:
            groups["_yuz_yok"] = nof

    # --------------------------------------------- hangi dosya hangi kaynaktan
    koklar = {r[0]: (r[1] or "") for r in con.execute("SELECT path, kok FROM files")}
    bilinen_kokler = sorted({k for k in koklar.values() if k}, key=len, reverse=True)
    coklu_kaynak = len(bilinen_kokler) > 1

    def kok_bul(p):
        k = koklar.get(p, "")
        if k:
            return k
        for aday in bilinen_kokler:      # eski kayitlarda kok bos olabilir
            if p.startswith(aday):
                return aday
        return ""

    def hedef_dizin(p, kisi_klasor):
        if args.duzen == "duz":
            return dst / kisi_klasor
        kok = kok_bul(p)
        if not kok:
            return dst / kisi_klasor
        bagil = bagil_klasor(p, kok, args.derinlik)
        if coklu_kaynak:
            bagil = Path(Path(kok).name) / bagil
        parcalar = [x for x in bagil.parts if x not in (".", "")]
        if args.duzen == "kisi-altklasor":
            return dst.joinpath(kisi_klasor, *parcalar)
        return dst.joinpath(*parcalar, kisi_klasor)   # altklasor-kisi (varsayilan)

    # ------------------------------------------------------------ plan
    plan = []
    for cid, paths in sorted(groups.items(), key=lambda kv: (isinstance(kv[0], str), kv[0])):
        if isinstance(cid, int):
            if len(paths) < args.min_photos:
                continue
            folder = f"kisi_{cid:04d}"
            if cid in names:
                folder = f"{cid:04d}_{safe_folder_name(names[cid])}"
        else:
            folder = cid
        plan.append((folder, paths))

    if not plan:
        print("Yazilacak bir sey yok. Once 'cluster' calistirin.")
        return

    dst = Path(args.dst)
    zaten_vardi = dst.exists()
    dst.mkdir(parents=True, exist_ok=True)

    esler_tablo = {}
    for r in con.execute("SELECT path, esler FROM files WHERE esler IS NOT NULL"):
        esler_tablo[r[0]] = [x for x in (r[1] or "").split("|") if x]

    yazma_listesi = []          # (hedef_dizin, kaynak_dosya)
    for folder, paths in plan:
        for p in paths:
            d = hedef_dizin(p, folder)
            yazma_listesi.append((d, p))
            for es in esler_tablo.get(p, []):     # ayni karenin RAW/JPEG esi
                if os.path.exists(es):
                    yazma_listesi.append((d, es))
    toplam_dosya = len(yazma_listesi)
    toplam_bayt = 0
    for _, p in yazma_listesi:
        try:
            toplam_bayt += os.path.getsize(p)
        except OSError:
            pass
    hedef_klasorler = {d for d, _ in yazma_listesi}

    # --------------------------------------------- yontem ve yer kontrolu
    fs = dosya_sistemi(dst)
    baglanti_var = hardlink_denemesi(plan[0][1][0], dst)
    mod = args.mode
    if mod == "auto":
        mod = "hardlink" if baglanti_var else "copy"
        print("  Hedef disk: %s -> %s" % (
            fs or "bilinmiyor",
            "sabit bag kullanilacak (yer kaplamaz)" if baglanti_var
            else "gercek kopya olusturulacak"))
        if not baglanti_var:
            print("  (exFAT/FAT diskler ve farkli diskler sabit bag desteklemez - bu normaldir)")
    elif mod == "hardlink" and not baglanti_var:
        print("  ! Hedef disk (%s) sabit bag desteklemiyor, gercek kopyalamaya gecildi."
              % (fs or "bilinmiyor"))
        mod = "copy"

    bos = shutil.disk_usage(dst).free
    gereken = toplam_bayt if mod == "copy" else 0
    GB = float(2 ** 30)

    print()
    print("=" * 64)
    print("  YAZMA ONCESI OZET  -  henuz hicbir sey yazilmadi")
    print("=" * 64)
    duzen_adi = {"altklasor-kisi": "alt klasor > kisi",
                 "kisi-altklasor": "kisi > alt klasor",
                 "duz": "tek seviye (alt klasor yok)"}[args.duzen]
    print(f"  Hedef klasor    : {dst}")
    print(f"  Duzen           : {duzen_adi}")
    print(f"  Kisi sayisi     : {len(plan)}")
    print(f"  Olusacak klasor : {len(hedef_klasorler)} adet")
    print(f"  Yazilacak dosya : {toplam_dosya} adet")
    print(f"  Yontem          : {'GERCEK KOPYA' if mod == 'copy' else 'sabit bag (yer kaplamaz)'}")
    print(f"  Gereken alan    : {gereken / GB:.1f} GB")
    print(f"  Diskte bos alan : {bos / GB:.1f} GB")
    print("-" * 64)
    for folder, paths in plan[:6]:
        print(f"    {folder:<30} {len(paths):>5} fotograf")
    if len(plan) > 6:
        print(f"    ... ve {len(plan) - 6} kisi daha")
    if yazma_listesi:
        ornek = sorted(hedef_klasorler)[0]
        try:
            print("  Ornek yol: ...\\%s" % ornek.relative_to(dst.parent))
        except ValueError:
            print("  Ornek yol: %s" % ornek)
    print("=" * 64)

    if gereken > bos * 0.97:
        print("  !! YETERSIZ DISK ALANI - islem iptal edildi.")
        print("     Baska bir diski hedef gosterin ya da yer acin.")
        return

    if args.dry_run:
        print("  (deneme modu: hicbir dosya yazilmadi)")
        if not zaten_vardi:
            try:
                dst.rmdir()   # deneme modunda klasor de birakilmaz
            except OSError:
                pass
        return

    if not args.evet:
        try:
            print()
            cevap = input("  Bu klasore yazilsin mi? (E = evet / h = hayir): ").strip().lower()
        except EOFError:
            cevap = "h"
        if cevap not in ("", "e", "evet", "y", "yes"):
            print("  Iptal edildi - hicbir dosya yazilmadi.")
            return

    # ------------------------------------------------------------ yazma
    print()
    toplam = 0
    olusan = set()
    sayaclar = {}
    for out, p in yazma_listesi:
        if out not in olusan:
            out.mkdir(parents=True, exist_ok=True)
            olusan.add(out)
        if True:
            src = Path(p)
            target = out / src.name
            k = 1
            try:
                while target.exists() and target.stat().st_size != src.stat().st_size:
                    target = out / f"{src.stem}_{k}{src.suffix}"
                    k += 1
            except OSError:
                pass
            if target.exists():
                continue
            try:
                if mod == "hardlink":
                    os.link(src, target)
                else:
                    shutil.copy2(src, target)
                toplam += 1
                sayaclar[out] = sayaclar.get(out, 0) + 1
            except Exception as e:
                print(f"  ! {src.name}: {e}")
            if toplam % 200 == 0 and toplam:
                print("  ... %d/%d dosya" % (toplam, toplam_dosya), flush=True)

    for d in sorted(sayaclar):
        try:
            gosterim = d.relative_to(dst)
        except ValueError:
            gosterim = d
        print(f"  {gosterim}: {sayaclar[d]} fotograf")

    print()
    print(f"Tamam. {len(olusan)} klasor, {toplam} dosya -> {dst}")
    if mod == "hardlink":
        print("Not: sabit bag modunda fotograflar ekstra yer kaplamaz; bir klasordeki")
        print("dosyayi silmek orijinali silmez.")
    else:
        print("Not: gercek kopya olusturuldu; orijinal fotograflariniza dokunulmadi.")

    # klasor isimleri kesinlesti -> kutuphane bunlari ogrensin
    if not args.ogrenme_yok and names:
        print()
        print("Kisi kutuphanesi guncelleniyor...")
        kutuphaneye_isle(con, args.names, getattr(args, "kutuphane", None),
                         kaynak=Path(args.db).name)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Fotograflari yuz tanima ile kisi klasorlerine ayirir.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="fotograflari tara, yuzleri cikar")
    s.add_argument("--src", required=True, nargs="+",
                   help="bir ya da birden fazla klasor (alt klasorler dahil taranir)")
    s.add_argument("--db", default="faces.db")
    s.add_argument("--model", default="buffalo_l", help="buffalo_l (iyi) / buffalo_s (hizli)")
    s.add_argument("--gpu", action="store_true", help="NVIDIA GPU varsa (onnxruntime-gpu gerekir)")
    s.add_argument("--det-size", type=int, default=640)
    s.add_argument("--max-side", type=int, default=1600, help="isleme oncesi kucultme sinirini belirler")
    s.add_argument("--limit", type=int, default=0, help="deneme icin ilk N fotograf")
    s.add_argument("--isci", type=int, default=0,
                   help="es zamanli surec sayisi (0 = tek surec). Olculdu: CPU'da "
                        "coklu surec yavaslatiyor, ONNX zaten tum cekirdekleri kullaniyor.")
    s.add_argument("--kalite", action="store_true",
                   help="yuksek kalite taramasi: 2560 px / dedektor 800. Kucuk ve "
                        "uzaktaki yuzleri de yakalar; olculdu: kacan karelerin "
                        "yarisini kurtardi, hiz farki yok.")
    s.add_argument("--hizli", action="store_true",
                   help="hizli tarama: dedektor 512 (olculdu %36 hizli). "
                        "Kalabaligin arkasindaki KUCUK yuzleri kacirabilir.")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("cluster", help="yuzleri kisilere gore grupla")
    c.add_argument("--db", default="faces.db")
    c.add_argument("--eps", type=float, default=0.50, help="dusur = daha kati ayrim, yukselt = daha cok birlestirir")
    c.add_argument("--min-samples", type=int, default=3, help="bir kisi sayilmak icin gereken en az yuz")
    c.add_argument("--claim", type=float, default=0.55, help="tekil yuzleri en yakin kisiye ekleme esigi (0 = kapali)")
    c.add_argument("--min-score", type=float, default=0.60, help="yuz tespit guven esigi")
    c.add_argument("--min-face", type=float, default=45, help="cok kucuk yuzleri (piksel) ele")
    c.add_argument("--kurtar", type=float, default=0.35,
                   help="kumeye giremeyen yuzleri bu benzerligin uzerindeyse en yakin "
                        "kisiye SUPHELI olarak ekle (0 = kapali, varsayilan 0.35)")
    c.add_argument("--evet", action="store_true", help="elle duzeltme uyarisini atla")
    c.set_defaults(func=cmd_cluster)

    b = sub.add_parser("birlestir", help="iki kumeyi tek kisi yap (ayni insan bolunmusse)")
    b.add_argument("--db", default="faces.db")
    b.add_argument("--names", default="isimler.csv")
    b.add_argument("--kume", nargs="+", required=True, help="birlestirilecek kume numaralari")
    b.set_defaults(func=cmd_birlestir)

    bl = sub.add_parser("bol", help="bir kumede iki kisi varsa ayir")
    bl.add_argument("--db", default="faces.db")
    bl.add_argument("--names", default="isimler.csv")
    bl.add_argument("--kume", required=True, help="bolunecek kume numarasi")
    bl.add_argument("--esik", type=float, default=0.60,
                    help="dusurdukce daha cok parcaya boler (varsayilan 0.60). "
                         "Gercek veriyle olculdu: 0.60 ayri kisileri temiz ayirdi, "
                         "0.45 ayni kisiyi de bolmeye basladi.")
    bl.add_argument("--min-yuz", type=int, default=2, help="yeni kumede en az kac yuz olsun")
    bl.set_defaults(func=cmd_bol)

    ck = sub.add_parser("cikar", help="yanlis eslesen tek tek yuzleri kumeden cikar")
    ck.add_argument("--db", default="faces.db")
    ck.add_argument("--names", default="isimler.csv")
    ck.add_argument("--yuz", nargs="+", required=True, help="cikarilacak yuz id'leri")
    ck.set_defaults(func=cmd_cikar)

    on = sub.add_parser("onay", help="oyuncu onay/veto (kill) listesi")
    on.add_argument("--db", default="faces.db")
    on.add_argument("--dosya", default="", help="oyuncudan gelen liste dosyasi (her satir bir kare)")
    on.add_argument("--foto", nargs="+", default=None, help="tek tek dosya adlari")
    on.add_argument("--kisi", default="", help="hangi kisi icin (bos = tum kisiler)")
    on.add_argument("--hepsi", action="store_true", help="--kisi ile: o kisinin tum kareleri")
    on.add_argument("--red", action="store_true", help="vetola (varsayilan: onayla)")
    on.add_argument("--kaynak", default="", help="not: kimden geldi")
    on.add_argument("--liste", action="store_true", help="mevcut kayitlari goster")
    on.add_argument("--temizle", action="store_true", help="tum onay/veto kayitlarini sil")
    on.set_defaults(func=cmd_onay)

    sk = sub.add_parser("secki", help="bulanik / gozu kapali / tekrar kareleri isaretle")
    sk.add_argument("--db", default="faces.db")
    sk.add_argument("--netlik", type=float, default=0,
                    help="netlik esigi (0 = otomatik, en dusuk %15)")
    sk.add_argument("--goz", type=float, default=0,
                    help="mutlak goz esigi (0 = kisiye gore otomatik)")
    sk.add_argument("--goz-orani", type=float, default=0.72,
                    help="kisinin kendi ortalamasinin bu katinin alti 'gozu kapali' "
                         "sayilir (varsayilan 0.72)")
    sk.add_argument("--min-yuz-px", type=float, default=120,
                    help="bulaniklik yalnizca bu boyuttan buyuk yuzlerde iddia edilir")
    sk.add_argument("--min-ornek", type=int, default=5,
                    help="goz tabani icin kisi basina en az kac kare gerekli")
    sk.add_argument("--tekrar", type=int, default=8,
                    help="bu kadar bit fark altindaki ardisik kareler ayni sayilir")
    sk.set_defaults(func=cmd_secki)

    r = sub.add_parser("review", help="kumeleri gorsel olarak incele + isim sablonu")
    r.add_argument("--db", default="faces.db")
    r.add_argument("--out", default="inceleme.html")
    r.add_argument("--samples", type=int, default=8)
    r.add_argument("--max-clusters", type=int, default=0)
    r.add_argument("--overwrite-names", action="store_true")
    r.set_defaults(func=cmd_review)

    t = sub.add_parser("tani", help="kalici kutuphaneden isimleri esle (internetsiz)")
    t.add_argument("--db", default="faces.db")
    t.add_argument("--names", default="isimler.csv")
    t.add_argument("--kutuphane", default=None, help="kisi kutuphanesi dosyasi")
    t.add_argument("--esik", type=float, default=0.45,
                   help="tanima esigi (ayni kisi ~0.75, farkli kisi ~0.08 olcusuyle)")
    t.add_argument("--fark", type=float, default=0.06,
                   help="birinci ile ikinci aday arasindaki en az fark")
    t.set_defaults(func=cmd_tani)

    o = sub.add_parser("onayla", help="onerilen isimleri onayla/duzelt ve kutuphaneye ogret")
    o.add_argument("--db", default="faces.db")
    o.add_argument("--names", default="isimler.csv")
    o.add_argument("--kutuphane", default=None)
    o.add_argument("--hepsi", action="store_true", help="ismi olanlari da tekrar sor")
    o.set_defaults(func=cmd_confirm)

    g = sub.add_parser("ogren", help="isimler.csv'deki isimleri kutuphaneye isle")
    g.add_argument("--db", default="faces.db")
    g.add_argument("--names", default="isimler.csv")
    g.add_argument("--kutuphane", default=None)
    g.set_defaults(func=cmd_ogren)

    ks = sub.add_parser("kisiler", help="kutuphanedeki kisileri listele / sil")
    ks.add_argument("--kutuphane", default=None)
    ks.add_argument("--sil", default="", help="silinecek kisinin tam ismi")
    ks.add_argument("--disa-aktar", default="", help="kutuphaneyi dosyaya yedekle")
    ks.add_argument("--ice-aktar", default="", help="yedegi geri yukle / birlestir")
    ks.set_defaults(func=cmd_kisiler)

    m = sub.add_parser("etiketle", help="isimleri fotograf metadata'sina yaz (kopya olusturmaz)")
    m.add_argument("--db", default="faces.db")
    m.add_argument("--names", default="isimler.csv")
    m.add_argument("--mod", choices=["gomulu", "yan"], default="gomulu",
                   help="gomulu: dosyanin icine (ACDSee/Lightroom gorur). "
                        "yan: .xmp yan dosyasi (orijinale hic dokunulmaz)")
    m.add_argument("--kisi", nargs="+", default=None,
                   help="yalnizca bu kisi numaralarina isim yaz")
    m.add_argument("--limit", type=int, default=0, help="deneme icin ilk N fotograf")
    m.add_argument("--dogrula", type=int, default=5,
                   help="ilk N dosyada goruntu bozulmadi mi diye kontrol et")
    m.add_argument("--kunye", action="store_true",
                   help="yapim/bolum/telif/fotografci bilgisini de yaz (caption)")
    m.add_argument("--ayarlar", default="ayarlar.json", help="kunye ayarlarinin dosyasi")
    for _alan, _yardim in (("yapim", "dizi/film adi"), ("bolum", "bolum no/adi"),
                           ("sahne", "sahne"), ("fotografci", "fotografci adi"),
                           ("telif", "telif metni"), ("kaynak", "kaynak/kredi")):
        m.add_argument("--" + _alan, default="", help=_yardim + " (kunye icin)")
    m.add_argument("--evet", action="store_true", help="onay sormadan yaz")
    m.set_defaults(func=cmd_etiketle)

    rp = sub.add_parser("rapor", help="kimler var, kim kiminle, hangi klasorde kac kare")
    rp.add_argument("--db", default="faces.db")
    rp.add_argument("--names", default="isimler.csv")
    rp.add_argument("--limit", type=int, default=0)
    rp.set_defaults(func=cmd_rapor)

    ar = sub.add_parser("ara", help="belirli kisilerin gorundugu kareleri bul")
    ar.add_argument("--db", default="faces.db")
    ar.add_argument("--names", default="isimler.csv")
    ar.add_argument("--kisi", nargs="+", required=True,
                    help="isim parcasi ya da kume numarasi (or: Ahmet Ayse)")
    ar.add_argument("--herhangi", action="store_true",
                    help="hepsi yerine herhangi biri yeterli olsun")
    ar.add_argument("--limit", type=int, default=0)
    ar.add_argument("--dosyaya", default="", help="sonucu bu dosyaya yaz")
    ar.set_defaults(func=cmd_ara)

    tl = sub.add_parser("teslim", help="kucultulmus + filigranli teslim paketi ve kontak baskisi")
    tl.add_argument("--db", default="faces.db")
    tl.add_argument("--names", default="isimler.csv")
    tl.add_argument("--dst", required=True)
    tl.add_argument("--boyut", type=int, default=2048, help="uzun kenar (px)")
    tl.add_argument("--kalite", type=int, default=88, help="JPEG kalitesi")
    tl.add_argument("--filigran", default="", help="basilacak filigran metni")
    tl.add_argument("--baslik", default="", help="kontak baskisi basligi")
    tl.add_argument("--kisi", nargs="+", default=None, help="yalnizca bu kisiler")
    tl.add_argument("--dosya-listesi", default="",
                    help="yalnizca bu dosyadaki kareleri paketle")
    tl.add_argument("--sadece-isimli", action="store_true")
    tl.add_argument("--kisiye-gore", action="store_true", help="kisi adiyla alt klasorler")
    tl.add_argument("--secki-yoksay", action="store_true", help="secki isaretlerini dikkate alma")
    tl.add_argument("--kontak-yok", action="store_true", help="PDF kontak baskisi uretme")
    tl.add_argument("--evet", action="store_true")
    tl.set_defaults(func=cmd_teslim)

    e = sub.add_parser("export", help="kisi klasorlerini olustur")
    e.add_argument("--db", default="faces.db")
    e.add_argument("--dst", required=True)
    e.add_argument("--names", default="isimler.csv")
    e.add_argument("--duzen", choices=["altklasor-kisi", "kisi-altklasor", "duz"],
                   default="altklasor-kisi",
                   help="cikti duzeni: alt klasor > kisi (varsayilan), kisi > alt klasor, ya da duz")
    e.add_argument("--derinlik", type=int, default=0,
                   help="kac seviye alt klasor korunsun (0 = hepsi)")
    e.add_argument("--mode", choices=["auto", "hardlink", "copy"], default="auto",
                   help="auto: disk destekliyorsa sabit bag, yoksa kopya (onerilen)")
    e.add_argument("--min-photos", type=int, default=2)
    e.add_argument("--export-unknown", action="store_true", help="_bilinmeyen klasoru de olustur")
    e.add_argument("--export-nofaces", action="store_true", help="_yuz_yok klasoru de olustur")
    e.add_argument("--kisi", nargs="+", default=None,
                   help="yalnizca bu kisi numaralarini isle (or: --kisi 3 7)")
    e.add_argument("--dosya-listesi", default="",
                   help="yalnizca bu dosyadaki kareleri isle (her satir bir yol)")
    e.add_argument("--sadece-isimli", action="store_true",
                   help="yalnizca isim verilmis kisileri isle")
    e.add_argument("--vetoyu-yoksay", action="store_true",
                   help="oyuncu vetosunu dikkate alma (varsayilan: vetolular disarida)")
    e.add_argument("--secki-atla", action="store_true",
                   help="secki ile isaretlenen bulanik/tekrar/gozu kapali kareleri disarida birak")
    e.add_argument("--dry-run", action="store_true", help="dosya tasimadan sadece raporla")
    e.add_argument("--evet", action="store_true", help="onay sormadan yaz (otomasyon icin)")
    e.add_argument("--kutuphane", default=None)
    e.add_argument("--ogrenme-yok", action="store_true",
                   help="klasor isimlerini kutuphaneye ogretme")
    e.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
