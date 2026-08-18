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

__version__ = "1.0.1"

import argparse
import base64
import csv
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import cv2
import numpy as np

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
        parts.append(
            f"<div class='k'><h2>kisi_{cid:04d} &nbsp;—&nbsp; {n_photo} fotograf, {n_face} yuz</h2>"
            + "".join(thumbs)
            + "</div>"
        )

    Path(args.out).write_text("\n".join(parts), encoding="utf-8")

    csv_path = Path(args.out).with_name("isimler.csv")
    if not csv_path.exists() or args.overwrite_names:
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["kume_no", "fotograf_sayisi", "isim"])
            for cid, n_face, n_photo in clusters:
                w.writerow([cid, n_photo, ""])
        print(f"Isim sablonu yazildi: {csv_path}")
    print(f"Inceleme sayfasi hazir: {args.out}  (tarayicida ac)")


# --------------------------------------------------------------------------
# 4) EXPORT — kisi klasorlerini olustur ve fotograflari yerlestir
# --------------------------------------------------------------------------
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
        unk = [r[0] for r in con.execute(
            "SELECT DISTINCT path FROM faces WHERE cluster = -1")]
        if unk:
            groups["_bilinmeyen"] = unk
    if args.export_nofaces:
        nof = [r[0] for r in con.execute("SELECT path FROM files WHERE n_faces = 0")]
        if nof:
            groups["_yuz_yok"] = nof

    dst = Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)
    fallback_warned = [False]

    def place(src, target):
        if target.exists():
            return False
        if args.mode == "copy":
            import shutil
            shutil.copy2(src, target)
            return True
        try:
            os.link(src, target)          # sabit bag: yer kaplamaz (ayni disk, NTFS)
            return True
        except OSError:
            if not fallback_warned[0]:
                print("  ! sabit bag kurulamadi (farkli disk olabilir), kopyalamaya gecildi.")
                fallback_warned[0] = True
            import shutil
            shutil.copy2(src, target)
            return True

    total = 0
    for cid, paths in sorted(groups.items(), key=lambda kv: (isinstance(kv[0], str), kv[0])):
        if isinstance(cid, int):
            if len(paths) < args.min_photos:
                continue
            folder = f"kisi_{cid:04d}"
            if cid in names:
                folder = f"{cid:04d}_{safe_folder_name(names[cid])}"
        else:
            folder = cid
        out = dst / folder
        if args.dry_run:
            print(f"  [deneme] {folder}: {len(paths)} fotograf")
            total += len(paths)
            continue
        out.mkdir(exist_ok=True)
        for p in paths:
            src = Path(p)
            target = out / src.name
            k = 1
            while target.exists() and target.stat().st_size != src.stat().st_size:
                target = out / f"{src.stem}_{k}{src.suffix}"
                k += 1
            try:
                if place(src, target):
                    total += 1
            except Exception as e:
                print(f"  ! {src}: {e}")
        print(f"  {folder}: {len(paths)} fotograf")

    print(f"\nTamam. {len(groups)} klasor, {total} fotograf baglantisi -> {dst}")
    if args.mode == "hardlink" and not args.dry_run:
        print("Not: 'hardlink' modunda fotograflar ekstra yer kaplamaz; bir klasordeki "
              "dosyayi silmek orijinali silmez.")


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

    e = sub.add_parser("export", help="kisi klasorlerini olustur")
    e.add_argument("--db", default="faces.db")
    e.add_argument("--dst", required=True)
    e.add_argument("--names", default="isimler.csv")
    e.add_argument("--mode", choices=["hardlink", "copy"], default="hardlink")
    e.add_argument("--min-photos", type=int, default=2)
    e.add_argument("--export-unknown", action="store_true", help="_bilinmeyen klasoru de olustur")
    e.add_argument("--export-nofaces", action="store_true", help="_yuz_yok klasoru de olustur")
    e.add_argument("--dry-run", action="store_true", help="dosya tasimadan sadece raporla")
    e.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
