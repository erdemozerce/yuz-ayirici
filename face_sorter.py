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

__version__ = "1.6.0"

import argparse
import base64
import csv
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

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif"}

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS files(
    path    TEXT PRIMARY KEY,
    mtime   REAL,
    size    INTEGER,
    n_faces INTEGER,
    status  TEXT
);
CREATE TABLE IF NOT EXISTS faces(
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    det_score REAL,
    det_w     REAL,
    emb       BLOB,
    cluster   INTEGER DEFAULT -1
);
CREATE INDEX IF NOT EXISTS idx_faces_path    ON faces(path);
CREATE INDEX IF NOT EXISTS idx_faces_cluster ON faces(cluster);
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
    return con


def imread_unicode(path):
    """Turkce/Rusca karakterli dosya yollarini da okuyabilen imread."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
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
            return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def list_images(src):
    src = Path(src)
    out = []
    for root, dirs, names in os.walk(src):
        dirs[:] = [d for d in dirs if not d.startswith((".", "$"))]
        for n in names:
            if Path(n).suffix.lower() in IMAGE_EXT:
                out.append(str(Path(root) / n))
    out.sort()
    return out


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


# --------------------------------------------------------------------------
# 1) SCAN — yuzleri bul ve vektorlerini kaydet
# --------------------------------------------------------------------------
def cmd_scan(args):
    from insightface.app import FaceAnalysis

    con = db_connect(args.db)
    print("Dosyalar listeleniyor...")
    files = list_images(args.src)
    if args.limit:
        files = files[: args.limit]
    print(f"  {len(files)} gorsel bulundu.")

    done = {r[0]: (r[1], r[2]) for r in con.execute("SELECT path, mtime, size FROM files")}
    todo = []
    for f in files:
        try:
            st = os.stat(f)
        except OSError:
            continue
        prev = done.get(f)
        if prev is None or abs(prev[0] - st.st_mtime) > 1 or prev[1] != st.st_size:
            todo.append((f, st.st_mtime, st.st_size))
    print(f"  {len(todo)} dosya islenecek ({len(files) - len(todo)} tanesi zaten islenmis).")
    if not todo:
        return

    providers = (
        ["CUDAExecutionProvider", "CPUExecutionProvider"] if args.gpu else ["CPUExecutionProvider"]
    )
    print(f"Model yukleniyor ({args.model}, {'GPU' if args.gpu else 'CPU'})...")
    app = FaceAnalysis(name=args.model, providers=providers)
    app.prepare(ctx_id=0 if args.gpu else -1, det_size=(args.det_size, args.det_size))

    t0 = time.time()
    n_faces_total = 0
    for i, (path, mtime, size) in enumerate(todo, 1):
        status, faces = "ok", []
        img = imread_unicode(path)
        if img is None:
            status = "okunamadi"
        else:
            try:
                h, w = img.shape[:2]
                scale = 1.0
                if max(h, w) > args.max_side:
                    scale = args.max_side / max(h, w)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                faces = app.get(img)
            except Exception as e:
                status = f"hata: {type(e).__name__}"

        rows = []
        for f in faces:
            bb = f.bbox.astype(float)
            det_w = float(bb[2] - bb[0])                 # islenen goruntudeki genislik
            x1, y1, x2, y2 = (bb / scale).tolist()       # orijinal koordinatlara geri
            emb = np.asarray(f.normed_embedding, dtype=np.float32)
            rows.append((path, x1, y1, x2, y2, float(f.det_score), det_w, emb.tobytes()))

        con.execute("DELETE FROM faces WHERE path = ?", (path,))
        if rows:
            con.executemany(
                "INSERT INTO faces(path,x1,y1,x2,y2,det_score,det_w,emb) VALUES(?,?,?,?,?,?,?,?)", rows
            )
        con.execute(
            "INSERT OR REPLACE INTO files(path,mtime,size,n_faces,status) VALUES(?,?,?,?,?)",
            (path, mtime, size, len(rows), status),
        )
        n_faces_total += len(rows)

        if i % 20 == 0 or i == len(todo):
            con.commit()
            hiz = i / (time.time() - t0)
            kalan = (len(todo) - i) / max(hiz, 1e-6)
            print(
                f"  [{i}/{len(todo)}] {hiz:.2f} foto/sn | {n_faces_total} yuz | "
                f"tahmini kalan: {fmt_eta(kalan)}",
                flush=True,
            )
    con.commit()
    print(f"Bitti. Toplam {n_faces_total} yuz kaydedildi -> {args.db}")


# --------------------------------------------------------------------------
# 2) CLUSTER — ayni kisinin yuzlerini grupla
# --------------------------------------------------------------------------
def cmd_cluster(args):
    from sklearn.cluster import DBSCAN

    con = db_connect(args.db)
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

    # kumeleri buyukten kucuge 1,2,3... diye yeniden numarala
    sizes = {}
    for l in labels:
        if l != -1:
            sizes[l] = sizes.get(l, 0) + 1
    order = sorted(sizes, key=lambda c: -sizes[c])
    remap = {old: new for new, old in enumerate(order, 1)}
    final = np.array([remap.get(l, -1) for l in labels], dtype=np.int64)

    con.execute("UPDATE faces SET cluster = -1")
    con.executemany(
        "UPDATE faces SET cluster = ? WHERE id = ?", [(int(c), int(i)) for i, c in zip(ids, final)]
    )
    con.commit()

    n_person = len(order)
    n_noise = int((final == -1).sum())
    print(f"Sonuc: {n_person} farkli kisi bulundu, {n_noise} yuz siniflandirilamadi.")
    print("En kalabalik 15 kisi (kume no / yuz sayisi / fotograf sayisi):")
    for cid, cnt, ph in con.execute(
        "SELECT cluster, COUNT(*), COUNT(DISTINCT path) FROM faces WHERE cluster > 0 "
        "GROUP BY cluster ORDER BY COUNT(*) DESC LIMIT 15"
    ):
        print(f"  kisi_{cid:04d}  {cnt:5d} yuz  {ph:5d} fotograf")


def kume_ornekleri(con, cid, adet):
    """Bir kumenin merkezine en yakin (en temsili) yuzlerini dondurur."""
    rows = con.execute(
        "SELECT path,x1,y1,x2,y2,emb FROM faces WHERE cluster = ?", (cid,)
    ).fetchall()
    if not rows:
        return []
    E = np.vstack([np.frombuffer(r[5], np.float32) for r in rows])
    E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
    merkez = E.mean(axis=0)
    merkez /= np.linalg.norm(merkez) + 1e-9
    sira = np.argsort(-(E @ merkez))[:adet]
    return [rows[i][:5] for i in sira]


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
        adet = kutuphane.ogret(kcon, isim, E, kaynak=kaynak)
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


# --------------------------------------------------------------------------
# 3) REVIEW — kimin kim oldugunu gormek icin HTML + isim dosyasi
# --------------------------------------------------------------------------
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

    groups = {}
    for cid, path in con.execute(
        "SELECT cluster, path FROM faces WHERE cluster > 0 GROUP BY cluster, path"
    ):
        groups.setdefault(cid, []).append(path)

    if args.export_unknown:
        unk = [r[0] for r in con.execute("SELECT DISTINCT path FROM faces WHERE cluster = -1")]
        if unk:
            groups["_bilinmeyen"] = unk
    if args.export_nofaces:
        nof = [r[0] for r in con.execute("SELECT path FROM files WHERE n_faces = 0")]
        if nof:
            groups["_yuz_yok"] = nof

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

    toplam_dosya = sum(len(p) for _, p in plan)
    toplam_bayt = 0
    for _, paths in plan:
        for p in paths:
            try:
                toplam_bayt += os.path.getsize(p)
            except OSError:
                pass

    dst = Path(args.dst)
    zaten_vardi = dst.exists()
    dst.mkdir(parents=True, exist_ok=True)

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
    print(f"  Hedef klasor    : {dst}")
    print(f"  Olusacak klasor : {len(plan)} kisi")
    print(f"  Yazilacak dosya : {toplam_dosya} adet")
    print(f"  Yontem          : {'GERCEK KOPYA' if mod == 'copy' else 'sabit bag (yer kaplamaz)'}")
    print(f"  Gereken alan    : {gereken / GB:.1f} GB")
    print(f"  Diskte bos alan : {bos / GB:.1f} GB")
    print("-" * 64)
    for folder, paths in plan[:8]:
        print(f"    {folder:<30} {len(paths):>5} fotograf")
    if len(plan) > 8:
        print(f"    ... ve {len(plan) - 8} klasor daha")
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
    for folder, paths in plan:
        out = dst / folder
        out.mkdir(exist_ok=True)
        for p in paths:
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
            except Exception as e:
                print(f"  ! {src.name}: {e}")
        print(f"  {folder}: {len(paths)} fotograf")

    print()
    print(f"Tamam. {len(plan)} klasor, {toplam} dosya -> {dst}")
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
    s.add_argument("--src", required=True, help="fotograflarin bulundugu klasor / surucu")
    s.add_argument("--db", default="faces.db")
    s.add_argument("--model", default="buffalo_l", help="buffalo_l (iyi) / buffalo_s (hizli)")
    s.add_argument("--gpu", action="store_true", help="NVIDIA GPU varsa (onnxruntime-gpu gerekir)")
    s.add_argument("--det-size", type=int, default=640)
    s.add_argument("--max-side", type=int, default=1600, help="isleme oncesi kucultme sinirini belirler")
    s.add_argument("--limit", type=int, default=0, help="deneme icin ilk N fotograf")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("cluster", help="yuzleri kisilere gore grupla")
    c.add_argument("--db", default="faces.db")
    c.add_argument("--eps", type=float, default=0.50, help="dusur = daha kati ayrim, yukselt = daha cok birlestirir")
    c.add_argument("--min-samples", type=int, default=3, help="bir kisi sayilmak icin gereken en az yuz")
    c.add_argument("--claim", type=float, default=0.55, help="tekil yuzleri en yakin kisiye ekleme esigi (0 = kapali)")
    c.add_argument("--min-score", type=float, default=0.60, help="yuz tespit guven esigi")
    c.add_argument("--min-face", type=float, default=45, help="cok kucuk yuzleri (piksel) ele")
    c.set_defaults(func=cmd_cluster)

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
    ks.set_defaults(func=cmd_kisiler)

    e = sub.add_parser("export", help="kisi klasorlerini olustur")
    e.add_argument("--db", default="faces.db")
    e.add_argument("--dst", required=True)
    e.add_argument("--names", default="isimler.csv")
    e.add_argument("--mode", choices=["auto", "hardlink", "copy"], default="auto",
                   help="auto: disk destekliyorsa sabit bag, yoksa kopya (onerilen)")
    e.add_argument("--min-photos", type=int, default=2)
    e.add_argument("--export-unknown", action="store_true", help="_bilinmeyen klasoru de olustur")
    e.add_argument("--export-nofaces", action="store_true", help="_yuz_yok klasoru de olustur")
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
