#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pencere.py — Yuz Ayirici'yi GERCEK BIR MASAUSTU PENCERESINDE acar.

Tarayici acilmaz: adres cubugu, sekme, yer imleri yok. Kendi simgesi ve
gorev cubugu girisi olan normal bir uygulama gibi calisir.

NASIL
  Arayuz yine yerel sunucudan gelir (hicbir sey degismedi, internet yok),
  ama tarayici yerine isletim sisteminin kendi goruntuleme bileseninde
  gosterilir: Windows'ta Edge WebView2, macOS'ta WKWebView.

  Klasor secme pencereleri de isletim sisteminin KENDI dialogu ile acilir -
  uygulamaya bagli oldugu icin arkada kalma sorunu olmaz.

pywebview yoksa ya da WebView bileseni bulunamazsa program kendini
tarayici moduna dusurur; hicbir islev kaybolmaz.
"""

import sys
import threading
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def tarayici_moduna_dus(sebep):
    print("Pencere modu kullanilamadi (%s)." % sebep)
    print("Tarayici modunda aciliyor...")
    import arayuz
    return arayuz.main()


def main():
    try:
        import webview
    except ImportError:
        return tarayici_moduna_dus("pywebview kurulu degil")

    import arayuz

    try:
        sunucu, adres = arayuz.sunucu_baslat()
    except Exception as e:
        print("Sunucu baslatilamadi:", e)
        return 1

    pencere = webview.create_window(
        "Yüz Ayırıcı",
        adres,
        width=1320,
        height=900,
        min_size=(960, 640),
        background_color="#0f1115",
        text_select=False,
        confirm_close=False,
    )

    def klasor_sor(baslik, mevcut):
        """Isletim sisteminin kendi klasor secme penceresi."""
        try:
            sonuc = pencere.create_file_dialog(
                webview.FOLDER_DIALOG, directory=mevcut or str(Path.home()))
            if not sonuc:
                return ""
            yol = sonuc[0] if isinstance(sonuc, (list, tuple)) else sonuc
            return str(Path(yol))
        except Exception as e:
            print("Klasor penceresi:", e)
            return None

    threading.Thread(target=arayuz.dialog_dongusu, args=(klasor_sor,),
                     daemon=True).start()

    try:
        webview.start()          # pencere kapanana kadar burada bekler
    except Exception as e:
        return tarayici_moduna_dus(str(e))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        pass
