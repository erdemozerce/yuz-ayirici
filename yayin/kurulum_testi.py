#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Kurulumdan sonra her seyin calistigini dogrular ve modeli indirir."""

import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    print("  - paketler kontrol ediliyor...")
    try:
        import cv2
        import numpy as np
        import sklearn
        import onnxruntime
        import insightface
    except ImportError as e:
        print("  !! Eksik paket:", e)
        return 1
    print("     python %s | opencv %s | numpy %s | onnxruntime %s | insightface %s"
          % (sys.version.split()[0], cv2.__version__, np.__version__,
             onnxruntime.__version__, insightface.__version__))

    gpu = (BASE / "gpu_var.txt").exists()
    saglayicilar = (["CUDAExecutionProvider", "CPUExecutionProvider"] if gpu
                    else ["CPUExecutionProvider"])

    print("  - yuz tanima modeli yukleniyor (ilk seferde indirir, sabir)...")
    from insightface.app import FaceAnalysis

    t0 = time.time()
    app = FaceAnalysis(name="buffalo_l", providers=saglayicilar)
    app.prepare(ctx_id=0 if gpu else -1, det_size=(640, 640))
    print("     model hazir (%.0f sn)" % (time.time() - t0))

    print("  - hiz olculuyor...")
    import numpy as np

    deneme = (np.random.rand(1200, 1600, 3) * 255).astype(np.uint8)
    t1 = time.time()
    tur = 3
    for _ in range(tur):
        app.get(deneme)
    saniye = (time.time() - t1) / tur
    hiz = 1.0 / max(saniye, 1e-6)
    print("     yaklasik %.1f fotograf/saniye" % hiz)
    print("     10.000 fotograf tahmini: %.1f saat" % (10000 / hiz / 3600))

    # ilk ayar dosyalari
    ayar = BASE / "ayarlar.json"
    if not ayar.exists():
        ayar.write_text(json.dumps({
            "kaynak_klasor": "",
            "hedef_klasor": "",
            "db": str(BASE / "faces.db"),
            "eps": 0.50,
            "min_samples": 3,
            "mod": "hardlink",
            "guncelleme_url": "",
            "otomatik_guncelleme": True,
            "son_kontrol": 0,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("  - ayarlar.json olusturuldu")

    surum = BASE / "surum.txt"
    if not surum.exists():
        surum.write_text("1.0.0", encoding="utf-8")

    print("\n  TEST BASARILI - program calismaya hazir.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
